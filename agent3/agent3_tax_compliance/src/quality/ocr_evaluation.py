"""Local evaluation contracts. Labels never enter capture or correction data."""
import hashlib
import json
import math
import re
import unicodedata
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

VERSION='ocr-evaluation-v1'
HEADER_FIELDS=tuple('parties.'+role+'.'+name for role in ('seller','buyer') for name in ('name','tax_id','address'))+(
    'invoice.number','invoice.series','invoice.issue_date','currency','totals.net','totals.vat','totals.gross')
ITEM_FIELDS=('description','quantity','unit_price','net','vat_treatment','vat_rate')
KINDS=('pdf_text','pdf_scan','photo')


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def file_hash(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def local_file(root,path):
    root=Path(root).resolve();resolved=(root/path).resolve()
    if not resolved.is_relative_to(root) or not resolved.is_file():raise ValueError('Input must be a file inside the workspace')
    return resolved


def validate_labels(labels):
    if not isinstance(labels,dict):raise ValueError('Labels must be an object')
    if type(labels.get('complete',False)) is not bool:raise ValueError('complete must be boolean')
    if labels.get('review_status','DRAFT') not in ('DRAFT','VERIFIED'):raise ValueError('Invalid label review status')
    if labels.get('review_status')=='VERIFIED' and not str(labels.get('reviewer','')).strip():raise ValueError('Verified labels require a reviewer')
    fields=labels.get('fields',{});items=labels.get('items',[])
    if not isinstance(fields,dict) or not isinstance(items,list):raise ValueError('Invalid label structure')
    for mapping,allowed in [(fields,HEADER_FIELDS),*((item,ITEM_FIELDS) for item in items)]:
        if not isinstance(mapping,dict) or set(mapping)-set(allowed):raise ValueError('Unknown labeled field')
        if any(value is not None and not isinstance(value,str) for value in mapping.values()):
            raise ValueError('Labels must use strings (including decimal values) or null for not printed')
        for path,value in mapping.items():
            if value is not None:canonical(value,path)
    if labels.get('complete'):
        if set(fields)!=set(HEADER_FIELDS) or any(set(item)!=set(ITEM_FIELDS) for item in items):
            raise ValueError('Complete labels require all header fields and all cells of every printed row')


def seal_dataset(entries,root,used_groups=()):
    """Explicit splits, with transitive source/layout/invoice/hash leakage checks."""
    rows=[];ids=set();members={};hash_groups={};used=set(used_groups)
    for entry in entries:
        row=dict(entry);identifier=row['case_id']
        if not isinstance(identifier,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',identifier) or identifier in ids:
            raise ValueError('Case IDs must be unique safe names')
        ids.add(identifier)
        if row.get('input_kind') not in KINDS or row.get('split') not in ('dev','test'):raise ValueError('Declare input_kind and dev/test split')
        if row.get('number_locale','AUTO') not in ('VI','EN','AUTO'):raise ValueError('Invalid number locale')
        groups=[row.get(key) for key in ('group_id','source_group','layout_group')]
        if any(not isinstance(group,str) or not group.strip() for group in groups):raise ValueError('Declare invoice, source and layout groups')
        if row['split']=='test' and (row.get('used_for_tuning',False) or used.intersection(groups+[identifier])):
            raise ValueError('Previously used development groups cannot become test data')
        digest=file_hash(local_file(root,row['path']))
        if digest in hash_groups and hash_groups[digest]!=row['group_id']:raise ValueError('Duplicate files must share the same invoice group')
        hash_groups[digest]=row['group_id']
        if row['split']=='test' and digest in used:raise ValueError('Previously used development file cannot become test data')
        if row.get('sha256',digest)!=digest:raise ValueError('Input changed after seal')
        for member in groups+[digest]:
            if member in members and members[member]!=row['split']:raise ValueError('Source/layout/invoice/duplicate overlaps dev and test')
            members[member]=row['split']
        labels=row.get('labels',{})
        validate_labels(labels)
        row.update(sha256=digest,number_locale=row.get('number_locale','AUTO'),labels=labels)
        rows.append(row)
    payload={'version':VERSION,'entries':rows,'used_groups':sorted(used),
             'status':'SEALED' if rows else 'PENDING_UNSEEN_DATA'}
    return {**payload,'manifest_sha256':fingerprint(payload)}


def verify_dataset(manifest,root):
    payload={key:value for key,value in manifest.items() if key!='manifest_sha256'}
    if manifest.get('manifest_sha256')!=fingerprint(payload):raise ValueError('Manifest changed after seal')
    if manifest!=seal_dataset(manifest['entries'],root,manifest['used_groups']):raise ValueError('Dataset changed after seal')
    return True


def canonical(value,path):
    text=' '.join(unicodedata.normalize('NFC',str(value)).split())
    if path.startswith('totals.') or path.rsplit('.',1)[-1] in ('quantity','unit_price','net','vat_rate'):
        try:
            number=Decimal(text)
            if not number.is_finite():raise ValueError('Nonfinite label')
            return number  # Decimal comparison never rounds via the ambient context.
        except InvalidOperation:raise ValueError('Numeric labels must be canonical decimal strings') from None
    return text


def score_record(record,labels):
    """Rows align in printed order; extra/missing rows invalidate whole invoices."""
    validate_labels(labels)
    data=record.model_dump(mode='json') if record else {}
    def at(path):
        value=data
        for part in path.split('.'):
            value=value.get(part) if isinstance(value,dict) else None
        return value
    observations=[(path,expected,at(path)) for path,expected in labels.get('fields',{}).items()]
    items=sorted(data.get('items',[]),key=lambda item:item['line_number'])
    for index,item in enumerate(labels.get('items',[])):
        for name,expected in item.items():
            observations.append((f'items.{index+1}.{name}',expected,items[index].get(name) if index<len(items) else None))
    outcomes=[]
    for path,expected,field in observations:
        status=(field or {}).get('status','MISSING');value=(field or {}).get('value')
        present=status=='PRESENT' and value is not None
        correct=(not present and status!='AMBIGUOUS') if expected is None else (present and canonical(value,path)==canonical(expected,path))
        outcomes.append({'field_path':path,'outcome':'CORRECT' if correct else 'WRONG_PRESENT' if present else 'MISSING_OR_AMBIGUOUS',
                         'critical':path.endswith('.tax_id') or path=='invoice.number' or path.startswith('totals.')})
    complete=bool(labels.get('complete'))
    count_correct=len(items)==len(labels['items']) if complete else None
    return {'outcomes':outcomes,'labeled':len(outcomes),'correct':sum(row['outcome']=='CORRECT' for row in outcomes),
            'wrong_present':sum(row['outcome']=='WRONG_PRESENT' for row in outcomes),
            'item_count_correct':count_correct,'whole_invoice_correct':bool(record and count_correct and all(row['outcome']=='CORRECT' for row in outcomes)) if complete else None,
            'labels_verified':labels.get('review_status')=='VERIFIED','labels_complete':complete}


def percentile(values,fraction):
    values=sorted(values)
    return values[max(0,math.ceil(len(values)*fraction)-1)] if values else None


def summarize(cases,workload_controlled=False):
    groups=defaultdict(lambda:{'cases':0,'labeled':0,'correct':0,'wrong_present':0,'failed':0})
    fields=defaultdict(lambda:{'labeled':0,'correct':0,'wrong_present':0})
    for case in cases:
        row=groups[case['input_kind']];row['cases']+=1;row['failed']+=case['state']!='REVIEW'
        for key in ('labeled','correct','wrong_present'):row[key]+=case['score'][key]
        for outcome in case['score']['outcomes']:
            path=outcome['field_path'];category='items.'+path.rsplit('.',1)[-1] if path.startswith('items.') else path
            field=fields[category];field['labeled']+=1;field['correct']+=outcome['outcome']=='CORRECT';field['wrong_present']+=outcome['outcome']=='WRONG_PRESENT'
    for row in groups.values():row['exact_match']=row['correct']/row['labeled'] if row['labeled'] else None
    timings=[p['elapsed_seconds'] for c in cases for p in c.get('timings',[]) if p['stage']=='ocr_page' and p['route'] in ('OCR','HYBRID')]
    # Page OCR timing alone is not end-to-end latency. Gate uses single-page jobs.
    eligible=[c for c in cases if c.get('page_count')==1 and c['input_kind']!='pdf_text']
    jobs=[c['elapsed_seconds'] for c in eligible]
    independent_groups=len({c.get('group_id',c['case_id']) for c in eligible})
    failures=sum(c['state']!='REVIEW' for c in cases)
    return {'by_input_kind':dict(groups),'by_field':dict(fields),'cases':len(cases),'failed':failures,
            'ocr_page_p50_seconds':percentile(timings,.5),'ocr_page_p95_seconds':percentile(timings,.95),
            'single_page_job_samples':len(jobs),'single_page_invoice_groups':independent_groups,'single_page_job_p95_seconds':percentile(jobs,.95),
            'latency_gate':'FAIL' if failures or (jobs and percentile(jobs,.95)>180) else 'PENDING_SAMPLE_SIZE' if independent_groups<20 else 'PENDING_CONTROLLED_WORKLOAD' if not workload_controlled else 'PASS',
            'whole_invoice_labeled':sum(c['score']['whole_invoice_correct'] is not None for c in cases),
            'whole_invoice_correct':sum(c['score']['whole_invoice_correct'] is True for c in cases),
            'quality_acceptance':'PENDING' if not cases or any(not c['score']['labels_verified'] or not c['score']['labels_complete'] for c in cases) else 'READY_FOR_REVIEW',
            'release_approved':False}


def compare_runs(baseline,candidate):
    for run in (baseline,candidate):
        if run.get('run_state')!='COMPLETED' or run.get('dataset_validated_at_end') is not True:
            raise ValueError('Only completed runs with verified final input hashes can be compared')
    if any(baseline.get(key)!=candidate.get(key) for key in ('manifest_sha256','split')):raise ValueError('Compare the same frozen dataset and split')
    old={c['case_id']:c for c in baseline['cases']};new={c['case_id']:c for c in candidate['cases']}
    if not old or old.keys()!=new.keys():raise ValueError('Comparison requires identical nonempty case coverage')
    if set(old)!=set(baseline['expected_cases']) or set(new)!=set(candidate['expected_cases']):
        raise ValueError('Run is missing expected dataset cases')
    errors_before=errors_after=0;regressions=[];table_regression=False;address_regression=False
    for identifier,before in old.items():
        after=new[identifier]
        previous={row['field_path']:row for row in before['score']['outcomes']}
        current={row['field_path']:row for row in after['score']['outcomes']}
        if previous.keys()!=current.keys():raise ValueError('Labeled coverage changed')
        for path,row in previous.items():
            result=current[path];errors_before+=row['outcome']!='CORRECT';errors_after+=result['outcome']!='CORRECT'
            if result['critical'] and result['outcome']=='WRONG_PRESENT' and row['outcome']!='WRONG_PRESENT':regressions.append({'case_id':identifier,'field_path':path})
            if row['outcome']=='CORRECT' and result['outcome']!='CORRECT':
                table_regression|=path.startswith('items.');address_regression|=path.endswith('.address')
        table_regression|=before['score']['item_count_correct'] is True and after['score']['item_count_correct'] is not True
    improvement=(errors_before-errors_after)/errors_before if errors_before else None
    gates={'error_reduction_30pct':improvement is not None and improvement>=.3,
           'complete_label_coverage':all(c['score'].get('labels_complete') for c in [*old.values(),*new.values()]),
           'no_new_critical_wrong_present':not regressions,'no_table_regression':not table_regression,
           'no_address_regression':not address_regression,'latency':candidate['summary']['latency_gate']=='PASS',
           'no_processing_failures':not candidate['summary']['failed']}
    return {'errors_before':errors_before,'errors_after':errors_after,'relative_error_reduction':improvement,
            'new_critical_wrong_present':regressions,'gates':gates,'technical_gate_passed':all(gates.values()),
            'quality_acceptance':candidate['summary']['quality_acceptance'],'release_approved':False}
