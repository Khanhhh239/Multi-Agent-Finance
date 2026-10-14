from ..canonicalization.derive import sha
from ..domain.money import decimal_string
from .contracts import EvaluationUnit


def discover(record,kind):
    if kind=='RECORD':return (EvaluationUnit(unit_type=kind,unit_id=record.record_id,discovery='COMPLETE'),)
    if not record.items:
        return (EvaluationUnit(unit_type=kind,unit_id=record.record_id+'.discovery',discovery='UNKNOWN'),)
    if kind=='ITEM':
        units=[EvaluationUnit(unit_type=kind,unit_id=i.item_id,item_refs=(i.item_id,),discovery='COMPLETE')
               for i in sorted(record.items,key=lambda i:i.item_id)]
    else:
        groups={}
        for item in record.items:
            treatment=item.vat_treatment.value if item.vat_treatment and item.vat_treatment.status=='PRESENT' else None
            rate=decimal_string(item.vat_rate.value) if item.vat_rate and item.vat_rate.status=='PRESENT' else None
            groups.setdefault((treatment,rate),[]).append(item.item_id)
        units=[]
        for key,refs in groups.items():
            refs=tuple(sorted(refs))
            identifier='vat-group-'+sha([key,refs])[:24]
            units.append(EvaluationUnit(unit_type=kind,unit_id=identifier,item_refs=refs,discovery='COMPLETE'))
    if record.item_discovery_status!='COMPLETE':
        units.append(EvaluationUnit(unit_type=kind,unit_id=record.record_id+'.discovery',discovery=record.item_discovery_status))
    return tuple(sorted(units,key=lambda u:u.unit_id))
