"""Validate the exact frozen review population before CLI/web ingestion."""
import csv
import hashlib
import io
import json
from pathlib import Path, PurePosixPath

from .feature_contract import digest, sha
from .shadow_scoring import guarded

VERSION='company-ml-comparison-v1'
SELECTION_FIELDS=('review_id','company_id','transaction_id','evidence_sha256','algorithm','rank','score','above_calibration_threshold')


def packet_json(payload,name):
    def unique_pairs(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('Trùng khóa JSON: '+key)
            result[key]=value
        return result
    try:
        value=json.loads(payload.decode('utf-8'),object_pairs_hook=unique_pairs)
        if not isinstance(value,dict):raise ValueError('Cần một đối tượng JSON.')
        return value
    except (UnicodeError,ValueError) as error:
        raise ValueError('JSON của gói không hợp lệ: '+name) from error


def evidence_files(root):
    directory=root/'public/evidence'
    if directory.exists() and not directory.is_dir():
        raise ValueError('Thư mục bằng chứng không hợp lệ.')
    # Every evidence file is locked, including nested files and non-JSON names.
    return {p.relative_to(root).as_posix() for p in directory.rglob('*') if p.is_file()}


def load_packet(root):
    root=guarded(root)
    manifest_bytes=(root/'manifest.json').read_bytes()
    manifest_hash=hashlib.sha256(manifest_bytes).hexdigest()
    manifest=packet_json(manifest_bytes,'manifest.json')
    if manifest.get('version')!=VERSION or not isinstance(manifest.get('files'),dict):
        raise ValueError('Sai phiên bản hoặc danh sách tệp của gói so sánh.')
    files=manifest['files']
    if not {'private/comparison.json','private/selection.csv'}<=files.keys():
        raise ValueError('Gói so sánh thiếu kế hoạch hoặc tập chọn đã khóa.')
    paths={};canonical=set()
    for name,checksum in files.items():
        relative=PurePosixPath(name)
        if (relative.is_absolute() or name!=relative.as_posix() or '..' in relative.parts
                or '\\' in name or ':' in name or name.casefold() in canonical
                or not isinstance(checksum,str) or len(checksum)!=64
                or any(c not in '0123456789abcdef' for c in checksum)):
            raise ValueError('Tên tệp hoặc checksum không hợp lệ trong manifest: '+name)
        canonical.add(name.casefold())
        path=(root/name).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError('Gói so sánh đã thay đổi: '+name)
        paths[name]=path
    listed={name for name in files if name.startswith('public/evidence/')}
    if any(len(PurePosixPath(name).parts)!=3 or not name.endswith('.json') for name in listed):
        raise ValueError('Bằng chứng phải là tệp JSON trực tiếp trong public/evidence của gói đã khóa.')
    actual=evidence_files(root)
    if listed!=actual:raise ValueError('Bằng chứng thừa/thiếu so với manifest; không nhận tệp ngoài gói đã khóa.')
    needed=listed|{'private/comparison.json','private/selection.csv'};payloads={}
    for name,path in paths.items():
        if name in needed:
            payload=path.read_bytes();checksum=hashlib.sha256(payload).hexdigest()
            payloads[name]=payload
        else:checksum=sha(path)
        if checksum!=files[name]:raise ValueError('Gói so sánh đã thay đổi: '+name)
    # Parse the exact bytes just checked, never reopen JSON/CSV after verification.
    report=packet_json(payloads['private/comparison.json'],'private/comparison.json')
    checksum=files['private/comparison.json']
    if checksum!=manifest.get('comparison_sha256'):
        raise ValueError('Kế hoạch không khớp checksum đã khóa.')
    plan=report.get('plan',{})
    if not isinstance(plan,dict):raise ValueError('Kế hoạch gói phiếu không hợp lệ.')
    if plan.get('scenario')=='005':raise ValueError('Không nhập phiếu từ holdout 005.')
    companies=plan.get('companies');budget=plan.get('review_count_per_company_model')
    if (not isinstance(companies,list) or not companies or any(not isinstance(c,str) or not c for c in companies)
            or len(set(companies))!=len(companies) or type(budget) is not int or not 1<=budget<=1000
            or not isinstance(report.get('models'),list) or type(report.get('review_units')) is not int):
        raise ValueError('Kế hoạch thiếu phạm vi doanh nghiệp, ngân sách hoặc số phiếu hợp lệ.')
    units={};transactions=set()
    for name in sorted(listed):
        evidence=packet_json(payloads[name],name);rid=evidence.get('review_id')
        company,tid=evidence.get('company_id'),evidence.get('transaction_id')
        source=evidence.get('source_record')
        if (not isinstance(rid,str) or rid!=Path(name).stem or rid in units
                or company not in companies or not isinstance(tid,str) or not tid
                or (company,tid) in transactions or not isinstance(source,dict)
                or source.get('company_id')!=company or source.get('transaction_id')!=tid):
            raise ValueError('Mã phiếu/giao dịch bị trùng hoặc sai công ty/tệp bằng chứng.')
        transactions.add((company,tid))
        units[rid]=dict(review_id=rid,company_id=evidence['company_id'],transaction_id=evidence['transaction_id'],
                        evidence_sha256=digest(evidence),evidence=evidence)
    models={};selected=set()
    for model in report['models']:
        if not isinstance(model,dict) or model.get('status') not in {'evaluated','skipped'}:
            raise ValueError('Thông tin model trong gói không hợp lệ.')
        if model['status']!='evaluated':continue
        company,algorithm=model.get('company_id'),model.get('algorithm');ids=model.get('selected_review_ids')
        key=company,algorithm
        if (not isinstance(company,str) or company not in companies or not isinstance(algorithm,str) or not algorithm
                or not isinstance(ids,list) or any(not isinstance(rid,str) for rid in ids)
                or key in models or len(ids)!=len(set(ids)) or len(ids)!=model.get('selected_for_review')
                or len(ids)!=budget
                or any(rid not in units or units[rid]['company_id']!=model['company_id'] for rid in ids)):
            raise ValueError('Tập chọn model trùng hoặc sai ngân sách/phạm vi doanh nghiệp.')
        models[key]=model;selected.update(ids)
    if selected!=set(units) or len(units)!=report['review_units']:
        raise ValueError('Bằng chứng không khớp chính xác tập phiếu đã chọn.')
    reader=csv.DictReader(io.StringIO(payloads['private/selection.csv'].decode('utf-8-sig'),newline=''))
    if reader.fieldnames!=list(SELECTION_FIELDS):raise ValueError('Sai các cột của tập chọn đã khóa.')
    rows=list(reader)
    seen=set()
    for row in rows:
        if None in row or any(value is None for value in row.values()):raise ValueError('Dòng chọn thừa/thiếu ô so với các cột đã khóa.')
        rid=row['review_id'];unit=units.get(rid);key=row['company_id'],row['algorithm']
        # CSV exports protect spreadsheet formula cells; compare to their exact encoding.
        if unit:
            for name in ('company_id','transaction_id'):
                value=unit[name]
                if str(value).lstrip().startswith(('=','+','-','@')) and row[name]=="'"+value:row[name]=value
            key=row['company_id'],row['algorithm']
        if (not unit or key not in models or (key,rid) in seen
                or any(row[name]!=unit[name] for name in ('company_id','transaction_id','evidence_sha256'))
                or rid not in models[key]['selected_review_ids']
                or row['rank']!=str(models[key]['selected_review_ids'].index(rid)+1)):
            raise ValueError('Dòng chọn không khớp phiếu/công ty/model đã khóa.')
        seen.add((key,rid))
    if len(seen)!=sum(len(m['selected_review_ids']) for m in models.values()):
        raise ValueError('Thiếu dòng trong tập chọn đã khóa.')
    if (evidence_files(root)!=listed or sha(root/'manifest.json')!=manifest_hash
            or any(not (root/name).resolve().is_relative_to(root) or sha(root/name)!=files[name] for name in needed)):
        raise ValueError('Gói bằng chứng thay đổi trong lúc kiểm tra; không nhận phiếu, hãy kiểm tra lại gói đã khóa.')
    return dict(packet_id=checksum,manifest_sha256=manifest_hash,report=report,units=units)


def review_metrics(report,entered,companies=None):
    metrics=[]
    for model in report['models']:
        if model['status']!='evaluated' or (companies is not None and model['company_id'] not in companies):continue
        selected=model['selected_review_ids'];done=[entered[rid] for rid in selected if rid in entered]
        useful=sum(r['useful']=='yes' for r in done);unknown=sum(r['useful']=='unknown' for r in done)
        complete=len(done)==len(selected);minutes=sum(r['active_review_minutes'] for r in done)
        metrics.append(dict(company_id=model['company_id'],algorithm=model['algorithm'],selected=len(selected),
            reviewed=len(done),useful=useful,unknown=unknown,unreviewed=len(selected)-len(done),
            useful_rate_among_decidable=useful/(len(done)-unknown) if len(done)>unknown else None,
            useful_at_budget=useful if complete else None,observed_review_minutes=minutes,
            full_budget_review_minutes=minutes if complete else None))
    return metrics
