from .contracts import RuleFamily


def select(family:RuleFamily,on_date):
    if on_date is None:return None,'UNKNOWN','DATE_UNAVAILABLE'
    if not family.supported_from<=on_date<family.supported_to:
        return None,'UNKNOWN','DATE_OUTSIDE_SUPPORTED_HISTORY'
    found=[v for v in family.versions if v.effective_from<=on_date<v.effective_to]
    if len(found)!=1:return None,'UNKNOWN','VERSION_GAP' if not found else 'VERSION_OVERLAP'
    return found[0],'MATCH','VERSION_SELECTED'
