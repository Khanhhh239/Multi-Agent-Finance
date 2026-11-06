"""Frozen per-company, equal-capacity model comparison and human review collection.

The source SQLite connection is read-only. No model is activated, operational
queue changed, human outcome guessed, or useful alert converted into a fraud label.
"""
import argparse
from contextlib import closing
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import time

from .company_ml import decode_snapshot, runtime, labels_csv
import joblib
import numpy as np
from .feature_contract import current_contract, digest, sha
from .ml_estimators import CompanyEstimator, ALGORITHMS, catalog
from .shadow_scoring import guarded, instant

VERSION='company-ml-comparison-v1'
SOURCE_FIELDS=('transaction_id','company_id','posted_at','created_at','approved_at','txn_type',
    'amount_vnd','approval_limit_vnd','vendor_id','employee_id','customer_id','creator_id','approver_id',
    'recipient_account','recipient_bank_code','debit_account','credit_account','journal_signature',
    'accounting_purpose','business_purpose','payment_channel')
IDENTITY=('review_id','company_id','transaction_id','evidence_sha256')
REVIEW_FIELDS=(*IDENTITY,'useful','business_action','rationale','evidence_refs',
               'active_review_minutes','timing_method','reviewer_id','reviewed_at','human_verified')


def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def write_csv(path,rows,fields):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for row in rows:
            # Even user-supplied IDs and notes must remain text in spreadsheet apps.
            writer.writerow({k:("'"+str(row.get(k,'')) if str(row.get(k,'')).lstrip().startswith(('=','+','-','@'))
                                else row.get(k,'')) for k in fields})


def read_snapshots(database,companies,scenario):
    if scenario=='005':raise ValueError('Không sử dụng holdout 005 trong so sánh ML.')
    database=guarded(database)
    if not database.is_file(): raise ValueError('Không tìm thấy database ML.')
    result={}
    with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)) as db:
        db.row_factory=sqlite3.Row;db.execute('BEGIN')
        for company in companies:
            revision,meta,records,x,labels=decode_snapshot(db.execute(
                'SELECT * FROM company_ml_data WHERE company_id=?',(company,)).fetchone())
            if scenario=='005' or meta['scenario']!=scenario:
                raise ValueError('Snapshot cần đúng bộ dữ liệu đang đánh giá; không dùng holdout 005.')
            contract=current_contract()
            if meta['feature_fingerprint']!=contract['fingerprint'] or meta['columns']!=contract['columns']:
                raise ValueError('Feature snapshot không còn khớp hợp đồng hiện hành; cập nhật dữ liệu trước.')
            if (not records or len(records)>100000 or x.shape!=(len(records),len(meta['columns']))
                    or not np.isfinite(x).all() or len({r['transaction_id'] for r in records})!=len(records)
                    or any(r['company_id']!=company for r in records)):
                raise ValueError('Snapshot sai phạm vi, trùng mã, sai matrix hoặc vượt 100.000 dòng.')
            # Stored labels came through the reviewed-label CSV gate. Revalidate its
            # normalized provenance; never consult benchmark labels/splits/oracles.
            label_rows=[dict(company_id=company,transaction_id=tid,verified='1',**value) for tid,value in labels.items()]
            if label_rows:
                stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=('company_id','transaction_id','label','reviewer_id','reviewed_at','evidence_ref','verified'))
                writer.writeheader();writer.writerows(label_rows)
                labels=labels_csv(stream.getvalue(),company,records,datetime.now(timezone.utc))
            active=db.execute('SELECT version_id FROM company_ml_bindings WHERE company_id=?',(company,)).fetchone()
            result[company]=dict(revision=revision,metadata=meta,records=records,x=x,labels=labels,
                                 active_version=active[0] if active else None)
    return result


def partition(records,windows):
    start,first,second,end=[instant(windows[k]) for k in ('train_start','train_end','calibration_end','evaluation_end')]
    if not start<first<second<end: raise ValueError('Cần train_start < train_end < calibration_end < evaluation_end.')
    timestamps=[instant(r['posted_at']) for r in records]
    groups=[[i for i,t in enumerate(timestamps) if a<=t<b] for a,b in ((start,first),(first,second),(second,end))]
    if any(len(g)<minimum for g,minimum in zip(groups,(5,2,2))):
        raise ValueError('Mỗi doanh nghiệp cần ít nhất 5 train, 2 calibration, 2 evaluation trong cùng kỳ.')
    if len(groups[0])>20000 or len(groups[2])>10000:
        raise ValueError('So sánh cục bộ giới hạn 20.000 train và 10.000 evaluation mỗi doanh nghiệp.')
    return [np.asarray(g,dtype=int) for g in groups]


def catboost_reason(records,labels,train,train_end,installed):
    if not installed:return 'Chưa cài CatBoost trong môi trường đánh giá.'
    eligible=[i for i in train if records[i]['transaction_id'] in labels
              and instant(labels[records[i]['transaction_id']]['reviewed_at'])<instant(train_end)]
    if len(eligible)!=len(train):
        return f'Chỉ {len(eligible)}/{len(train)} dòng train có nhãn đã xác minh và đã biết trước cuối kỳ train.'
    if {labels[records[i]['transaction_id']]['label'] for i in train}!={0,1}:
        return 'Train cần cả hai lớp 0 và 1 đã xác minh.'
    return None


def compare(database,output,*,companies,scenario,windows,review_count,calibration_rate=.1,
            source_kind='unspecified',algorithms=None,seed=20261104):
    database,output=guarded(database),guarded(output)
    if output.exists() or output.is_relative_to(database.parent) or database.parent.is_relative_to(output):
        raise ValueError('Output phải là thư mục mới, tách khỏi database và dữ liệu nguồn.')
    if (not companies or len(set(companies))!=len(companies) or type(review_count) is not int
            or not 1<=review_count<=1000 or type(calibration_rate) not in (int,float)
            or not 0<calibration_rate<=.2 or source_kind not in {'synthetic_demo','business','unspecified'}):
        raise ValueError('Chọn doanh nghiệp không trùng, ngân sách 1–1.000 giao dịch và tỷ lệ calibration (0,20%].')
    algorithms=list(ALGORITHMS) if algorithms is None else algorithms
    if not algorithms or len(set(algorithms))!=len(algorithms) or any(a not in ALGORITHMS for a in algorithms):
        raise ValueError('Danh sách thuật toán không hợp lệ.')
    snapshots=read_snapshots(database,companies,scenario)
    splits={company:partition(s['records'],windows) for company,s in snapshots.items()}
    if any(len(groups[2])<review_count for groups in splits.values()):
        raise ValueError('Kỳ evaluation có ít giao dịch hơn ngân sách; giảm cùng ngân sách trước khi chạy.')
    installed={r['id']:r['installed'] for r in catalog()}
    public,selection,predictions,models,artifacts=[],[],[],[],{}
    plan=dict(version=VERSION,created_at=datetime.now(timezone.utc).isoformat(),source_kind=source_kind,
              implementation_sha256={name:sha(Path(__file__).with_name(name)) for name in ('company_ml_comparison.py','company_ml.py','ml_estimators.py')},
              companies=companies,scenario=scenario,windows=windows,review_count_per_company_model=review_count,
              review_unit='transaction',review_minutes_cap=None,calibration_rate=calibration_rate,seed=seed,
              algorithms=algorithms,selection_policy='top_k_all_evaluation_transactions',
              tie_policy='descending_score_then_SHA256(seed,company,transaction_id)',
              actual_human_minutes=None,automatic_model_activation=False,
              source_snapshots={c:dict(revision=s['revision'],active_version=s['active_version'],
                  dataset_version=s['metadata']['dataset_version'],feature_fingerprint=s['metadata']['feature_fingerprint']) for c,s in snapshots.items()})
    unit_map={}
    for company,snapshot in snapshots.items():
        records,x,labels=snapshot['records'],snapshot['x'],snapshot['labels']
        train,cal,test=splits[company]
        # Hashes bind the exact ordered population, not merely equal row counts.
        population={name:digest([records[i]['transaction_id'] for i in indices]) for name,indices in zip(('train','calibration','evaluation'),(train,cal,test))}
        for algorithm in algorithms:
            meta=dict(company_id=company,algorithm=algorithm,algorithm_label=ALGORITHMS[algorithm],
                data_revision=snapshot['revision'],population_sha256=population,train_rows=len(train),
                calibration_rows=len(cal),evaluation_rows=len(test),review_budget=review_count)
            reason=catboost_reason(records,labels,train,windows['train_end'],installed[algorithm]) if algorithm=='catboost' else None
            if reason:
                models.append(dict(meta,status='skipped',reason=reason));continue
            y=np.asarray([labels[records[i]['transaction_id']]['label'] for i in train]) if algorithm=='catboost' else None
            started=time.perf_counter()
            estimator=CompanyEstimator(algorithm).fit(x[train],y)
            threshold=float(np.quantile(estimator.score(x[cal]),1-calibration_rate,method='higher'))
            scores=estimator.score(x[test]);seconds=time.perf_counter()-started
            order=sorted(range(len(test)),key=lambda j:(-float(scores[j]),digest([seed,company,records[test[j]]['transaction_id']])))
            chosen=set(order[:review_count]);selected_ids=[]
            for j,i in enumerate(test):
                row=dict(company_id=company,algorithm=algorithm,transaction_id=records[i]['transaction_id'],
                         posted_at=records[i]['posted_at'],score=float(scores[j]),above_calibration_threshold=bool(scores[j]>threshold),
                         selected_for_review=j in chosen)
                predictions.append(row)
            for rank,j in enumerate(order[:review_count],1):
                record=records[test[j]];tid=record['transaction_id'];key=company,tid
                if key not in unit_map:
                    review_id='R'+digest([seed,company,snapshot['revision'],tid,windows])[:20]
                    evidence=dict(review_id=review_id,company_id=company,transaction_id=tid,
                        review_cutoff_exclusive=windows['evaluation_end'],source_kind=source_kind,
                        source_record={k:record[k] for k in SOURCE_FIELDS if k in record},
                        limitations=['Chỉ có dữ liệu giao dịch đã nạp; chưa đính kèm chứng từ gốc hoặc danh mục đầy đủ.',
                                     'Cần đối chiếu nguồn để kết luận hữu ích; chưa đủ căn cứ thì ghi unknown.'])
                    evidence_sha=digest(evidence)
                    unit_map[key]=dict(review_id=review_id,company_id=company,transaction_id=tid,evidence_sha256=evidence_sha)
                    public.append(dict(unit_map[key],evidence=evidence))
                identity=unit_map[key];selected_ids.append(identity['review_id'])
                selection.append(dict(identity,algorithm=algorithm,rank=rank,score=float(scores[j]),
                                      above_calibration_threshold=bool(scores[j]>threshold)))
            artifact=dict(format=VERSION,company_id=company,algorithm=algorithm,estimator=estimator,
                columns=snapshot['metadata']['columns'],feature_fingerprint=snapshot['metadata']['feature_fingerprint'],
                data_revision=snapshot['revision'],windows=windows,threshold=threshold,runtime=runtime(algorithm))
            stream=io.BytesIO();joblib.dump(artifact,stream);payload=stream.getvalue()
            restored=joblib.load(io.BytesIO(payload))
            if not np.allclose(restored['estimator'].score(x[test]),scores,rtol=1e-10,atol=1e-10):
                raise ValueError('Artifact so sánh không tái hiện được điểm; chưa xuất kết quả.')
            # Company IDs are data, never filesystem paths.
            artifact_path='private/models/'+digest([company,algorithm])[:24]+'.joblib'
            artifacts[artifact_path]=payload
            known=[i for i in test if records[i]['transaction_id'] in labels]
            models.append(dict(meta,status='evaluated',selected_review_ids=selected_ids,selected_for_review=review_count,
                runtime=artifact['runtime'],
                threshold=threshold,calibration_threshold_alerts=int((scores>threshold).sum()),fit_score_seconds=round(seconds,6),
                converged=getattr(estimator,'converged_',True),artifact_path=artifact_path,artifact_sha256=hashlib.sha256(payload).hexdigest(),
                verified_evaluation_labels=len(known),useful_alerts=None,actual_review_minutes=None))
    # Another session changing data during fitting invalidates the comparison.
    after=read_snapshots(database,companies,scenario)
    if any(after[c]['revision']!=s['revision'] or after[c]['active_version']!=s['active_version'] for c,s in snapshots.items()):
        raise RuntimeError('Dữ liệu/model nguồn đổi trong lúc so sánh. Chạy lại trên snapshot đã khóa.')
    output.mkdir(parents=True)
    report=dict(plan=plan,models=models,review_units=len(public),completed_human_reviews=0,
                business_winner=None,selection_sha256=digest(selection),predictions_sha256=digest(predictions))
    write_json(output/'private/comparison.json',report)
    write_csv(output/'private/selection.csv',selection,(*IDENTITY,'algorithm','rank','score','above_calibration_threshold'))
    write_csv(output/'private/predictions.csv',predictions,('company_id','algorithm','transaction_id','posted_at','score','above_calibration_threshold','selected_for_review'))
    for name,payload in artifacts.items():
        target=output/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(payload)
    public.sort(key=lambda u:digest([seed,'blind-order',u['review_id']]))
    for unit in public:write_json(output/'public/evidence'/ (unit['review_id']+'.json'),unit['evidence'])
    write_csv(output/'human_reviews.csv',[{k:u[k] for k in IDENTITY} for u in public],REVIEW_FIELDS)
    (output/'public').mkdir(exist_ok=True)
    (output/'public/README.md').write_text('''# Phiếu rà cảnh báo ML

Rà các giao dịch trong `evidence/`, điền `../human_reviews.csv`. Giữ tên model, điểm và thứ hạng trong `../private/` kín với người rà cho đến khi khóa phiếu.

- `useful`: yes nếu có hành động nghiệp vụ cụ thể có căn cứ; no nếu đã đủ căn cứ nhưng không cần hành động; unknown nếu chưa đủ tài liệu. Yêu cầu tài liệu chung chung chưa chứng minh cảnh báo hữu ích.
- Điền business_action (bắt buộc khi yes), rationale và evidence_refs. Hữu ích không phải nhãn gian lận.
- active_review_minutes: phút kiểm tra thực tế, loại thời gian nghỉ; timing_method: stopwatch hoặc contemporaneous_log. Không điền thời gian model chạy hoặc số phút phỏng đoán.
- Điền reviewer_id, reviewed_at (ISO có múi giờ) và human_verified=1 sau khi người rà xác nhận. Chưa rà thì để trống toàn bộ các ô kết quả.

Đây là phép so sánh ngân sách số giao dịch, chưa có hạn mức phút đã được duyệt. Một giao dịch trùng giữa các model chỉ cần rà một lần; thời gian được quy về từng danh sách model khi tổng hợp, tổng công sức thực tế tính theo giao dịch duy nhất.
''',encoding='utf-8')
    frozen={str(p.relative_to(output)).replace('\\','/'):sha(p) for p in output.rglob('*') if p.is_file() and p.name!='human_reviews.csv'}
    write_json(output/'manifest.json',dict(version=VERSION,files=frozen,comparison_sha256=sha(output/'private/comparison.json')))
    return report


def collect(comparison_root,reviews,output,*,now=None):
    root,output=guarded(comparison_root),guarded(output);reviews=Path(reviews).resolve()
    if output.exists() or output.is_relative_to(root) or root.is_relative_to(output):
        raise ValueError('Kết quả rà phải nằm trong thư mục mới, ngoài gói so sánh đã khóa.')
    from .ml_review_packets import load_packet, review_metrics
    packet=load_packet(root);report=packet['report']
    identities={rid:{k:unit[k] for k in IDENTITY} for rid,unit in packet['units'].items()}
    with reviews.open(encoding='utf-8-sig',newline='') as stream:
        reader=csv.DictReader(stream)
        if reader.fieldnames!=list(REVIEW_FIELDS):raise ValueError('Phiếu rà cần giữ nguyên cột và thứ tự của mẫu.')
        rows=list(reader)
    entered={};seen=set();now=now or datetime.now(timezone.utc)
    for row in rows:
        if None in row or any(v is None for v in row.values()):raise ValueError('Phiếu rà có dòng thừa/thiếu ô so với tiêu đề.')
        rid=row.get('review_id')
        if rid in identities:
            for key,value in identities[rid].items():
                if str(value).lstrip().startswith(('=','+','-','@')) and row.get(key)=="'"+str(value):row[key]=value
        if rid in seen or rid not in identities or any(row.get(k)!=v for k,v in identities.get(rid,{}).items()):
            raise ValueError('Phiếu rà bị trùng mã hoặc sai công ty/giao dịch/bằng chứng.')
        seen.add(rid)
        if not any(row.get(k,'') for k in REVIEW_FIELDS if k not in IDENTITY):continue
        try:minutes=float(row['active_review_minutes'])
        except (ValueError,TypeError) as exc:raise ValueError('Cần phút kiểm tra thực tế dạng số.') from exc
        if (row['useful'] not in {'yes','no','unknown'} or not np.isfinite(minutes) or not 0<minutes<=1440
                or row['timing_method'] not in {'stopwatch','contemporaneous_log'} or row['human_verified']!='1'
                or not all(row[k].strip() for k in ('reviewer_id','rationale','evidence_refs'))
                or (row['useful']=='yes' and not row['business_action'].strip())
                or instant(row['reviewed_at'])>now
                or instant(row['reviewed_at'])<instant(report['plan']['created_at'])):
            raise ValueError('Phiếu cần kết luận/căn cứ, hành động khi hữu ích, người rà, xác nhận, thời điểm hợp lệ và phút đo thực tế.')
        entered[rid]=dict(row,active_review_minutes=minutes)
    metrics=review_metrics(report,entered)
    result=dict(version=VERSION,source_comparison_sha256=packet['packet_id'],source_reviews_sha256=sha(reviews),
        source_kind=report['plan']['source_kind'],metrics=metrics,review_units=len(identities),completed_human_reviews=len(entered),
        total_unique_review_minutes=sum(r['active_review_minutes'] for r in entered.values()),business_winner=None,
        note='Phiếu do người rà xác nhận; không suy hữu ích thành gian lận, không tự chọn hoặc kích hoạt model.')
    output.mkdir(parents=True);write_json(output/'review_results.json',result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);commands=parser.add_subparsers(dest='command',required=True)
    run=commands.add_parser('run');run.add_argument('--database',type=Path,required=True);run.add_argument('--output',type=Path,required=True)
    run.add_argument('--companies',nargs='+',required=True);run.add_argument('--scenario',default='003')
    for field in ('train-start','train-end','calibration-end','evaluation-end'):run.add_argument('--'+field,required=True)
    run.add_argument('--review-count',type=int,required=True);run.add_argument('--calibration-rate',type=float,default=.1)
    run.add_argument('--source-kind',choices=('synthetic_demo','business','unspecified'),default='unspecified')
    summarize=commands.add_parser('collect');summarize.add_argument('--comparison',type=Path,required=True)
    summarize.add_argument('--reviews',type=Path,required=True);summarize.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='run':
        windows={k:getattr(args,k) for k in ('train_start','train_end','calibration_end','evaluation_end')}
        result=compare(args.database,args.output,companies=args.companies,scenario=args.scenario,windows=windows,
                       review_count=args.review_count,calibration_rate=args.calibration_rate,source_kind=args.source_kind)
        print(json.dumps(dict(output=str(args.output),models=len(result['models']),review_units=result['review_units']),ensure_ascii=False))
    else:
        result=collect(args.comparison,args.reviews,args.output)
        print(json.dumps(dict(output=str(args.output),completed_human_reviews=result['completed_human_reviews']),ensure_ascii=False))


if __name__=='__main__':main()
