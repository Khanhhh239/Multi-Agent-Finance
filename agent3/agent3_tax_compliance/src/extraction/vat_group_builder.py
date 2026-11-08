from ..canonicalization.derive import derived_field,sha
from ..canonicalization.normalize import exact_sum
from .candidates import provenance
from .contracts import VATGroup
from ..domain.field import FieldObject

def build_groups(items,discovery):
    buckets={}
    for item in items:
        treatment=item.vat_treatment.value if item.vat_treatment else None
        rate=item.vat_rate.value if item.vat_rate else None
        buckets.setdefault((treatment,rate),[]).append(item)
    groups=[]
    for (treatment,rate),members in buckets.items():
        refs=tuple(i.item_id for i in members)
        amounts=[i.net.value if i.net else None for i in members]
        total=exact_sum(amounts) if all(a is not None for a in amounts) else None
        groups.append(VATGroup(group_id='vat-'+sha(sorted(refs))[:32],item_refs=refs,treatment=treatment,rate=rate,
            category=FieldObject(status='MISSING',source='document',provenance=provenance(method='taxonomy-not-yet-available')),
            net=derived_field(total,tuple('items.'+i.item_id+'.net' for i in members)),discovery_status=discovery))
    return tuple(groups)
