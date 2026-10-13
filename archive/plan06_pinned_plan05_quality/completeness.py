from .contracts import Coverage

def flatten(record):
    result={}
    def visit(value,path):
        if hasattr(value,'status') and hasattr(value,'provenance'): result[path]=value;return
        if hasattr(type(value),'model_fields'):
            for name in type(value).model_fields:
                child=getattr(value,name)
                if path=='derived' or name=='derived': continue
                if name=='items':
                    for item in child: visit(item,'items.'+item.item_id)
                elif child is not None: visit(child,path+'.'+name if path else name)
    visit(record,'')
    return result

def coverage(paths,fields):
    statuses=[fields[path].status.value if path in fields else 'MISSING' for path in paths]
    na=statuses.count('NOT_APPLICABLE');np=statuses.count('NOT_PROVIDED_BY_SOURCE')
    denominator=len(paths)-na-np;present=statuses.count('PRESENT')
    return Coverage(expected=len(paths),denominator=denominator,present=present,
        excluded_not_applicable=na,excluded_not_provided=np,ratio=present/denominator if denominator else None)

def completeness(record,profile,fields):
    expected=list(profile.expected_fields)
    expected.extend('items.'+item.item_id+'.'+name for item in record.items for name in profile.item_fields)
    # Empty discovery is reported independently; zero rows cannot yield COMPLETE.
    return coverage(expected,fields),coverage(profile.critical_fields,fields),tuple(expected)
