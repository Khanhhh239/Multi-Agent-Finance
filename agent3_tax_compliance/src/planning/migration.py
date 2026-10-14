"""Explicit import migration for historical direction UNKNOWN, without DB writes."""
from copy import deepcopy


def migrate_legacy_direction(payload):
    result=deepcopy(payload)
    field=result.get('derived',{}).get('invoice_direction')
    if field and field.get('value')=='UNKNOWN':
        field.update(value=None,status='AMBIGUOUS',confidence=None,confidence_basis='UNAVAILABLE')
        provenance=field.get('provenance',{})
        refs=list(provenance.get('derived_from',[]))
        refs.append('legacy-direction-unknown-v1:raw-value-UNKNOWN')
        provenance['derived_from']=refs
        field['provenance']=provenance
    return result
