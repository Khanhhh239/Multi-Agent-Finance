"""Pure rederivation after observed corrections; no OCR, DB or clock access."""
import hashlib,json
from decimal import Decimal
from ..domain.cfr import CanonicalFinancialRecord,Derived,Totals
from ..domain.field import FieldObject
from ..domain.evidence import Provenance
from ..domain.taxpayer import identity_match,TaxpayerMaster,BranchRelation
from ..extraction.contracts import DerivationManifest,DerivationNode,ExtractionIssue
from .normalize import exact_sum,exact_product

def sha(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

def derived_field(value,inputs,status='MISSING'):
    return FieldObject(value=value,status='PRESENT' if value is not None else status,source='derived',
        confidence_basis='DETERMINISTIC',provenance=Provenance(method='derive-v1',adapter_version='extractor-v1',
            deterministic_policy_version='derive-v1',derived_from=tuple(inputs)))

def rederive(record,master,profile,relations=()):
    record=CanonicalFinancialRecord.model_validate_json(record.model_dump_json())
    master=TaxpayerMaster.model_validate_json(master.model_dump_json())
    relations=tuple(BranchRelation.model_validate_json(r.model_dump_json()) for r in relations)
    if (record.tenant_id,record.taxpayer_id,record.taxpayer_master_revision)!=(master.tenant_id,master.taxpayer_id,master.revision):
        raise ValueError('pinned taxpayer master mismatch')
    if any(r.tenant_id!=record.tenant_id for r in relations): raise ValueError('cross-tenant relation')
    deps=('parties.seller.tax_id','parties.buyer.tax_id','invoice.issue_date','master','relations')
    get=lambda f:f.value if f else None
    seller=get(record.parties.seller.tax_id);buyer=get(record.parties.buyer.tax_id)
    on_date=get(record.invoice.issue_date) if record.invoice else None
    # Normalize the optional branch separator, preserving all 13 digits.
    canonical_master=master.model_copy(update={'tax_code':master.tax_code.replace('-','')})
    canonical_relations=tuple(r.model_copy(update={'parent_tax_code':r.parent_tax_code.replace('-',''),
        'branch_tax_code':r.branch_tax_code.replace('-','')}) for r in relations)
    sm=identity_match(seller.replace('-',''),canonical_master,on_date,canonical_relations) if seller else 'UNKNOWN'
    bm=identity_match(buyer.replace('-',''),canonical_master,on_date,canonical_relations) if buyer else 'UNKNOWN'
    direction='OUTPUT' if (sm,bm)==('MATCH','NO_MATCH') else 'INPUT' if (sm,bm)==('NO_MATCH','MATCH') else None
    counterparty=record.parties.buyer if direction=='OUTPUT' else record.parties.seller if direction=='INPUT' else None
    nodes=[DerivationNode(path='derived.invoice_direction',inputs=deps),
           DerivationNode(path='derived.counterparty',inputs=('derived.invoice_direction','parties.seller','parties.buyer'))]
    complete=record.item_discovery_status=='COMPLETE' and bool(record.items)
    nets=[get(i.net) for i in record.items]
    net=exact_sum(nets) if complete and all(n is not None for n in nets) else None
    taxes=[]
    for item in record.items:
        treatment=get(item.vat_treatment);rate=get(item.vat_rate);amount=get(item.net)
        taxes.append(Decimal('0') if treatment in ('KCT','KKKNT') else exact_product(amount,rate)
                     if treatment=='TAXABLE_RATE' and amount is not None and rate is not None else None)
    vat=exact_sum(taxes) if complete and all(t is not None for t in taxes) else None
    gross=exact_sum((net,vat)) if net is not None and vat is not None else None
    net_deps=('item_discovery_status',)+tuple('items.'+i.item_id+'.net' for i in record.items)
    vat_deps=net_deps+tuple('items.'+i.item_id+'.'+f for i in record.items for f in ('vat_treatment','vat_rate'))
    nodes.extend((DerivationNode(path='derived.totals.net',inputs=net_deps),
                  DerivationNode(path='derived.totals.vat',inputs=vat_deps),
                  DerivationNode(path='derived.totals.gross',inputs=('derived.totals.net','derived.totals.vat'))))
    totals=Totals(net=derived_field(net,net_deps),vat=derived_field(vat,vat_deps),
                  gross=derived_field(gross,('derived.totals.net','derived.totals.vat')))
    issues=[]
    for name in ('net','vat','gross'):
        observed=get(getattr(record.totals,name));computed=get(getattr(totals,name))
        if observed is not None and computed is not None and observed!=computed:
            issues.append(ExtractionIssue(code='TOTAL_MISMATCH',field_path='totals.'+name,
                message='Observed total differs from exact item-derived total; neither was overwritten.'))
    if direction is None: issues.append(ExtractionIssue(code='UNKNOWN_DIRECTION',field_path='derived.invoice_direction',message='Party identities/date do not establish a unique direction.'))
    updated=record.model_copy(update={'derived':Derived(invoice_direction=derived_field(direction,deps,'AMBIGUOUS'),counterparty=counterparty,totals=totals)})
    manifest=DerivationManifest(observed_sha256=sha(record.model_dump(mode='json',exclude={'derived'})),
        master_sha256=sha(master.model_dump(mode='json')),relations_sha256=sha([r.model_dump(mode='json') for r in relations]),
        profile_version=profile.version,nodes=tuple(nodes))
    return updated,manifest,tuple(issues)

def affected_nodes(manifest,changed_paths):
    affected=set(changed_paths);result=set()
    def related(a,b): return a==b or a.startswith(b+'.') or b.startswith(a+'.')
    while True:
        new={n.path for n in manifest.nodes if any(related(parent,changed) for parent in n.inputs for changed in affected)}-result
        if not new: return tuple(sorted(result))
        result.update(new);affected.update(new)
