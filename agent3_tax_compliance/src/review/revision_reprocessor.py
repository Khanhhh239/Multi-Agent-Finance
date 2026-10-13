"""Pure observed edits and dependency-aware rederivation; immutable raw data."""
from datetime import datetime,timezone
from ..domain.cfr import CanonicalFinancialRecord
from ..canonicalization.derive import rederive,affected_nodes
from .contracts import ReviewError

HEADER={'parties.'+party+'.'+field for party in ('seller','buyer') for field in ('name','tax_id','address')}
HEADER.update({'invoice.number','invoice.series','invoice.issue_date','currency','totals.net','totals.vat','totals.gross'})
ITEM={'description','quantity','unit_price','net','vat_treatment','vat_rate'}

def field_slot(data,path):
    parts=path.split('.')
    if path in HEADER:
        node=data
        for part in parts[:-1]:
            if node.get(part) is None: node[part]={}
            node=node[part]
        return node,parts[-1]
    if len(parts)==3 and parts[0]=='items' and parts[2] in ITEM:
        item=next((i for i in data['items'] if i['item_id']==parts[1]),None)
        if item is not None: return item,parts[2]
    raise ReviewError('INVALID_FIELD','Only observed fields and existing immutable item IDs can be edited.')

def canonical_path(path):
    return 'parties.'+path if path.startswith(('seller.','buyer.')) else path

def apply(record,artifact,master,command,event_id,page_indices,created_at=None):
    data=record.model_dump(mode='json');changes=[]
    def write(path,value,status,evidence=None):
        node,key=field_slot(data,path);before=node.get(key)
        proof=(evidence if evidence is not None else (before or {}).get('provenance',{}).get('evidence',[]))
        after={'value':value,'status':status,'source':'human-review','confidence':None,'confidence_basis':'HUMAN_CONFIRMED',
            'provenance':{'method':'human-review-v1','adapter_version':'review-v1','review_event_id':event_id,'evidence':proof},
            'candidates':(before or {}).get('candidates',[])}
        node[key]=after
        prior=next((c for c in changes if c['field_path']==path),None)
        if prior: prior['after']=after
        else: changes.append({'field_path':path,'before':before,'after':after})
    for change in command.changes:
        node,key=field_slot(data,change.field_path);before=node.get(key);value=change.new_value;evidence=None
        if change.selected_candidate_id:
            candidate=next((c for c in artifact.candidates if c.candidate_id==change.selected_candidate_id
                            and canonical_path(c.semantic_field)==change.field_path),None)
            if candidate is None: raise ReviewError('CANDIDATE_OWNERSHIP','Candidate does not belong to this record and field.')
            value=candidate.normalized_value;evidence=[e.model_dump(mode='json') for e in candidate.evidence_refs]
        if change.operation=='CONFIRM':
            if not before or before['status']!='PRESENT': raise ReviewError('NOT_PRESENT','Only a present value can be confirmed.')
            value=before['value']
        write(change.field_path,value,'MISSING' if change.operation=='CLEAR' else 'PRESENT',evidence)
    # Exempt treatments are semantic enums; never turn them into rate zero.
    for item in data['items']:
        treatment=(item.get('vat_treatment') or {}).get('value')
        treatment_path='items.'+item['item_id']+'.vat_treatment';rate_path='items.'+item['item_id']+'.vat_rate'
        if treatment in ('KCT','KKKNT') and any(c.field_path==treatment_path for c in command.changes):
            if any(c.field_path==rate_path and c.operation!='CLEAR' for c in command.changes):
                raise ReviewError('VAT_CONTRADICTION','KCT/KKKNT cannot carry a numeric VAT rate.')
            write(rate_path,None,'NOT_APPLICABLE')
    if command.confirm_items_complete:
        if command.expected_item_count!=len(record.items) or set(command.verified_pages)!=set(page_indices) or len(command.verified_pages)!=len(page_indices):
            raise ReviewError('COMPLETENESS_PROOF','Confirm the exact existing row count and every source page.')
        changes.append({'field_path':'item_discovery_status','before':data['item_discovery_status'],'after':'COMPLETE'})
        data['item_discovery_status']='COMPLETE'
    data.update(revision=record.revision+1,creator='reviewer',stage='review',config_version='review-v1',
                created_at=(created_at or datetime.now(timezone.utc)).isoformat())
    updated=CanonicalFinancialRecord.model_validate(data)
    updated,manifest,issues=rederive(updated,master,artifact.profile)
    return updated,changes,manifest,affected_nodes(manifest,[c['field_path'] for c in changes])
