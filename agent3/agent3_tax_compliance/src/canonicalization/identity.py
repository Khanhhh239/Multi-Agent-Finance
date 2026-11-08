"""Allocate once; re-extraction mappings are explicit, never based on text/row number."""
from uuid import uuid4
from ..extraction.contracts import IdentityMap,IdentityEntry,ItemLineage

def allocate(anchors,previous=None,mapping=None,lineage=()):
    anchors=tuple(anchors)
    if len(set(anchors))!=len(anchors): raise ValueError('duplicate row anchors')
    if previous is None:
        if mapping is not None or lineage: raise ValueError('lineage requires previous identity map')
        mapping={a:'item-'+uuid4().hex for a in anchors}
    else:
        if mapping is None or set(mapping)!=set(anchors):
            raise ValueError('re-extraction requires a complete explicit anchor-to-item mapping')
        old={e.item_id for e in previous.entries};new=set(mapping.values())
        removed=old-new;added=new-old
        if removed or added:
            if not lineage: raise ValueError('changed identity sets require split/merge lineage')
            used_old=[];used_new=[]
            for change in lineage:
                change=ItemLineage.model_validate(change)
                if change.operation=='SPLIT' and (len(change.previous_ids)!=1 or len(change.new_ids)<2):
                    raise ValueError('split requires one old and multiple new IDs')
                if change.operation=='MERGE' and (len(change.previous_ids)<2 or len(change.new_ids)!=1):
                    raise ValueError('merge requires multiple old and one new ID')
                used_old.extend(change.previous_ids);used_new.extend(change.new_ids)
            if set(used_old)!=removed or set(used_new)!=added or len(set(used_old))!=len(used_old) or len(set(used_new))!=len(used_new):
                raise ValueError('lineage must account for every changed identity exactly once')
    return IdentityMap(entries=tuple(IdentityEntry(anchor_id=a,item_id=mapping[a]) for a in anchors),
                       lineage=tuple(previous.lineage if previous else ())+tuple(lineage))
