"""Versioned diagnostics and conservative recommendations, never confirmations."""
import re
import unicodedata
from ..quality.completeness import flatten
from .regions import supported,plan_regions
from ..review.contracts import ReviewError

VERSION='recovery-policy-v1'
MAX_FIELDS=2
MAX_CROPS=4


def text_key(text):
    return ' '.join(unicodedata.normalize('NFC',str(text or '')).casefold().split())


def deduplicated_tail(text):
    words=str(text or '').split()
    for size in range(min(4,len(words)//2),0,-1):
        left=' '.join(words[-2*size:-size]);right=' '.join(words[-size:])
        # Never propose removing repeated numbers or short company initials.
        if text_key(left)==text_key(right) and len(re.sub(r'\W','',right))>=4 and not re.search(r'\d',right):
            return ' '.join(words[:-size])
    return None


def diagnose(record,artifact,normalized):
    entries=[];eligible=[]
    conflicts={b.block_id for p in normalized.pages for b in p.blocks if b.conflict_with}
    for path,field in flatten(record).items():
        if field.confidence_basis=='HUMAN_CONFIRMED' or field.status=='NOT_APPLICABLE':continue
        codes=[]
        if field.status in ('MISSING','AMBIGUOUS'):codes.append('FIELD_'+getattr(field.status,'value',str(field.status)))
        if deduplicated_tail(field.value):codes.append('REPEATED_SUFFIX')
        if '\ufffd' in str(field.value or ''):codes.append('UNREADABLE_CHARACTER')
        if any(e.block_id in conflicts for e in field.provenance.evidence):codes.append('SOURCE_CONFLICT')
        if not codes:continue
        entry={'field_path':path,'issue_codes':codes,'state':'REVIEW','reason':'UNSUPPORTED_FIELD','crop_count':0}
        if supported(path):
            try:
                _,regions=plan_regions(record,artifact,normalized,path)
                entry.update(state='ELIGIBLE',reason=None,crop_count=len(regions));eligible.append(entry)
            except ReviewError as exc:entry['reason']=exc.code
        entries.append(entry)
    eligible.sort(key=lambda e:(0 if 'REPEATED_SUFFIX' in e['issue_codes'] else 1,e['field_path']))
    used=0;selected=0
    for entry in eligible:
        if selected>=MAX_FIELDS or used+entry['crop_count']>MAX_CROPS:
            entry.update(state='DEFERRED',reason='RUN_BUDGET')
        else:
            entry['state']='SCHEDULED';selected+=1;used+=entry['crop_count']
    return {'policy_version':VERSION,'max_fields':MAX_FIELDS,'max_crops':MAX_CROPS,'entries':entries,
            'scheduled_fields':selected,'scheduled_crops':used,'human_confirmed_fields_skipped':True}


def select_candidate(field,entry,recovery):
    base={'decision':'REVIEW','reason':'UNPROVEN_CHANGE','selected_value':None,'review_required':True}
    if field.confidence_basis=='HUMAN_CONFIRMED':return {**base,'reason':'HUMAN_VALUE_PROTECTED'}
    if recovery.get('status')!='CANDIDATE' or not recovery.get('suggested_value'):return {**base,'reason':'INCOMPLETE_READ'}
    value=recovery['suggested_value']
    if text_key(value)==text_key(field.value):return {**base,'decision':'UNCHANGED','reason':'SAME_READING'}
    expected=deduplicated_tail(field.value)
    if ('REPEATED_SUFFIX' in entry['issue_codes'] and 'SOURCE_CONFLICT' not in entry['issue_codes']
            and expected and text_key(value)==text_key(expected)):
        return {**base,'decision':'RECOMMENDED','reason':'EXACT_SUFFIX_REPAIR','selected_value':value}
    return base
