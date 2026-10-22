"""Prepare blinded as-of evidence and validate human ML-comparison reviews.

No model fit/scoring, outcome fabrication, production feedback or external sends.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime
import html
import json
import math
from pathlib import Path
import zipfile

from .compare_shadow import build_snapshots, pending, read_csv, read_json, write_csv, write_json
from .feature_contract import digest, sha
from .shadow_scoring import guarded, instant, source_checks, output_guard
from .generate import TZ

VERSION = 'independent-ml-review-v1'
KNOWLEDGE_FIELDS = ('observed_at', 'recorded_at', 'verified_at', 'approved_at', 'action_at', 'posted_at', 'issued_at', 'closed_at')
STATIC_TABLES = {'calendar'}
FORBIDDEN = {'arm','rank','priority','rule_score','max_score','base_score','points','hard_trigger',
             'if_score','ml_score','anomaly_score','is_fraud','fraud_type','label','expected','signal',
             'predicted_fraud','selection_reason','estimated_minutes','amount_scale'}
FORM_ID = ['review_unit_id','company_code','cutoff_exclusive','evidence_sha256']
PRIMARY_FIELDS = FORM_ID + ['condition_present','actionable','document_request_needed','missing_evidence',
    'business_action','rationale','evidence_refs','timing_method','active_review_minutes','started_at','finished_at',
    'paused_minutes','primary_reviewer_id','reviewed_at','independent_of_development','blind_to_arm_and_score']
ADJ_FIELDS = FORM_ID + ['adjudication_status','condition_present','actionable','document_request_needed',
    'missing_evidence','business_action','rationale','evidence_refs','timing_method','active_adjudication_minutes',
    'started_at','finished_at','paused_minutes',
    'adjudicator_id','adjudicated_at','independent_of_development','blind_to_arm_and_score']


def unit_key(cohort, case_id, scope_hash, cutoff):
    return digest([cohort, case_id, scope_hash, instant(cutoff).isoformat()])


def plan_for(sources, seed=20261022):
    return dict(version=VERSION, seed=seed, primary_comparison_capacity=dict(cases=5, minutes=120),
        forced_sample='All same-day symmetric-difference review work from the frozen primary comparison',
        reference_strata=['cohort','company_id','common_selected_or_neither_selected_pending'],
        references_per_stratum=1, reference_draw='Smallest SHA256(seed,stratum,unit_key), no replacement',
        exclude_forced_units_from_reference=True, sampling_unit='Case snapshot at an exclusive daily cutoff',
        reference_universe='Baseline-admitted case scopes pending in at least one study ledger; not all source transactions',
        public_order='SHA256 independent ordering; opaque IDs; groups/arms/scores/ranks kept private',
        source_origin='synthetic_process_simulation', source_and_comparison_sha256=sources,
        review_outcomes_entered=0, model_fit=False, model_scored=False, queue_write=False, external_sends=0,
        actual_time='Human active minutes; reference and adjudication effort reported separately',
        actionable_definition='A justified specific business/control action beyond a generic missing-document request; not a fraud label',
        missing_evidence_definition='Record needed documents separately; unknown is not a negative',
        reviewer_requirements='Human primary and a different human adjudicator, independent of development; blind attestations required',
        statistical_limits='Stratified diagnostic sample; no field fraud precision/recall or unapproved population benefit estimator')


def choose_units(snapshots, selection_rows, cohort, *, seed):
    """Reconstruct frozen pending ledgers, census disagreement, draw unbiased hash ranks."""
    by_day = defaultdict(list)
    for row in selection_rows:
        by_day[row['day']].append(row)
    forced_keys = set()
    for rows in by_day.values():
        keys = {arm: {r['work_key'] for r in rows if r['arm'] == arm} for arm in ('baseline','if_shadow')}
        different = keys['baseline'] ^ keys['if_shadow']
        forced_keys.update(unit_key(cohort, r['case_id'], r['case_scope_hash'], r['cutoff_exclusive'])
                           for r in rows if r['work_key'] in different)
    ledgers = {arm: dict(done=set(), case_ids=set()) for arm in ('baseline','if_shadow')}
    first_seen, chosen, reservoirs, populations = {}, {}, {}, Counter()
    for snapshot in snapshots:
        day, cutoff, cases = snapshot['day'], snapshot['cutoff'], snapshot['cases']
        for case in cases:
            first_seen.setdefault(case['base_work_key'], day)
        candidates = {arm: {t['key']: t for t in pending(cases, ledger, first_seen, day)}
                      for arm, ledger in ledgers.items()}
        selected = {arm: [] for arm in ledgers}
        for row in by_day[day.isoformat()]:
            arm = row['arm']
            if arm not in candidates or row['work_key'] not in candidates[arm]:
                raise ValueError('Frozen selected work is absent from its causal pending ledger')
            task = candidates[arm][row['work_key']]
            if (task['case']['case_id'] != row['case_id'] or task['case']['production_scope_hash'] != row['case_scope_hash']
                    or instant(cutoff) != instant(row['cutoff_exclusive']) or task['minutes'] != int(row['estimated_minutes'])):
                raise ValueError('Frozen review scope/cost/cutoff differs from reconstruction')
            selected[arm].append(row)
        selected_units = {arm: {unit_key(cohort,r['case_id'],r['case_scope_hash'],cutoff) for r in rows}
                          for arm,rows in selected.items()}
        available = {}
        for tasks in candidates.values():
            for task in tasks.values():
                case = task['case']
                key = unit_key(cohort,case['case_id'],case['production_scope_hash'],cutoff)
                available[key] = dict(cohort=cohort,company_id=case['company_id'],case_id=case['case_id'],
                    cutoff_exclusive=cutoff,case_scope_hash=case['production_scope_hash'],case=case,
                    selected_events=[dict(row) for rows in selected.values() for row in rows
                                     if row['case_id']==case['case_id'] and row['case_scope_hash']==case['production_scope_hash']])
        for key, descriptor in available.items():
            if key in forced_keys:
                chosen[key] = dict(descriptor, sample_group='disagreement', inclusion_probability=1.0)
                continue
            status = ('common_selected' if key in selected_units['baseline'] & selected_units['if_shadow'] else
                      'neither_selected' if key not in selected_units['baseline'] | selected_units['if_shadow'] else None)
            if status is None:
                continue
            stratum = (cohort,descriptor['company_id'],status)
            populations[stratum] += 1
            rank = digest([seed,list(stratum),key])
            if stratum not in reservoirs or rank < reservoirs[stratum][0]:
                reservoirs[stratum] = (rank,key,descriptor)
        for arm, rows in selected.items():
            for row in rows:
                if row['work_key'] in ledgers[arm]['done']:
                    raise ValueError('Repeated unchanged selected work in frozen ledger')
                ledgers[arm]['done'].add(row['work_key']);ledgers[arm]['case_ids'].add(row['case_id'])
    if set(chosen) != forced_keys:
        raise ValueError('Some disagreement units could not be reconstructed')
    for stratum,(_,key,descriptor) in reservoirs.items():
        chosen[key] = dict(descriptor,sample_group='reference_'+stratum[2],
                          reference_stratum=list(stratum),stratum_population=populations[stratum],
                          inclusion_probability=1/populations[stratum])
    return chosen, {json.dumps(list(k)):v for k,v in sorted(populations.items())}


def row_available(row, table, cutoff):
    clocks = [row[f] for f in KNOWLEDGE_FIELDS if row.get(f)]
    if not clocks:
        return table in STATIC_TABLES
    try:
        return all(instant(value) < cutoff for value in clocks)
    except ValueError:
        return False


def public_row(row, company_code):
    clean = {k:v for k,v in row.items() if k not in FORBIDDEN and not k.startswith(('fraud_','ml_','expected_'))}
    if 'company_id' in clean:
        clean['company_id'] = company_code
    return clean


def evidence_for(descriptor, tables, company_code):
    case, cutoff = descriptor['case'], instant(descriptor['cutoff_exclusive'])
    members = set(json.loads(case['transaction_ids']) if isinstance(case['transaction_ids'],str) else case['transaction_ids'])
    transaction_rows = [r for r in tables['transactions'] if r['transaction_id'] in members]
    if any(r['company_id'] != descriptor['company_id'] or not row_available(r,'transactions',cutoff) for r in transaction_rows):
        raise ValueError('Review members have foreign-company or future source evidence')
    if {r['transaction_id'] for r in transaction_rows} != members:
        raise ValueError('A review member is missing from source')
    invoice_ids = {r['invoice_id'] for r in transaction_rows if r.get('invoice_id')}
    if case['source_scope'].startswith('invoice:'):
        invoice_ids.add(case['source_scope'].split(':',1)[1])
    vendor_ids = {r['vendor_id'] for r in transaction_rows if r.get('vendor_id')}
    employee_ids = {r['employee_id'] for r in transaction_rows if r.get('employee_id')}
    advance_ids = {r['advance_id'] for r in transaction_rows if r.get('advance_id')}
    receipt_ids = {r['receipt_transaction_id'] for r in tables.get('receipt_allocations',[])
                   if r.get('invoice_id') in invoice_ids and row_available(r,'receipt_allocations',cutoff)}
    related = [r for r in tables['transactions'] if r['company_id']==descriptor['company_id']
               and (r.get('invoice_id') in invoice_ids or r.get('vendor_id') in vendor_ids
                    or r.get('employee_id') in employee_ids or r.get('advance_id') in advance_ids
                    or r['transaction_id'] in receipt_ids)
               and r['transaction_id'] not in members and row_available(r,'transactions',cutoff)]
    invoice_ids.update(r['invoice_id'] for r in related if r.get('invoice_id'))
    tx_ids = members | {r['transaction_id'] for r in related}
    doc_ids = {r.get(k) for r in transaction_rows+related for k in ('journal_document_id','linked_document_id') if r.get(k)}
    evidence = dict(member_transactions=[public_row(r,company_code) for r in transaction_rows],
                    related_transactions=[public_row(r,company_code) for r in related])
    for table,rows in tables.items():
        if table == 'transactions':
            continue
        selected = []
        for row in rows:
            if row.get('company_id') and row['company_id'] != descriptor['company_id']:
                continue
            if table in {'journal_lines','journal_documents','account_flow_edges','document_links'}:
                if not (row.get('transaction_id') in tx_ids or row.get('document_id') in doc_ids
                        or row.get('source_document_id') in doc_ids or row.get('target_document_id') in doc_ids):
                    continue
            if table in {'invoices','receivable_invoices','receipt_allocations','receivable_explanations'} and row.get('invoice_id') not in invoice_ids:
                continue
            if not row_available(row,table,cutoff):
                continue
            selected.append(public_row(row,company_code))
        if selected:
            evidence[table] = selected
    return dict(company_code=company_code,cutoff_exclusive=descriptor['cutoff_exclusive'],
        source_origin='synthetic_process_simulation', scope_transaction_ids=sorted(members),
        source_object=case['source_scope'],tables=evidence,
        source_limitations=['Source rows are simulated attestations, not scans of original documents',
            'Company-scoped context is supplied; unavailable/future/unversioned rows are not backfilled',
            'Availability at daily cutoff does not prove validity or availability at each original payment',
            'No counts or identities of future excluded records are disclosed'])


def card_markdown(review_id, evidence):
    def cell(value):
        return html.escape(str(value)).replace('|','\\|').replace('\n',' ')
    rows = evidence['tables']['member_transactions']
    vn_cutoff = instant(evidence['cutoff_exclusive']).astimezone(TZ).isoformat()
    text = ['# Phiếu '+review_id,'',f"Công ty: **{evidence['company_code']}**. Mốc đối chiếu (loại trừ), giờ Việt Nam: **{vn_cutoff}**.",
        '', '**Nguồn mô phỏng.** Đánh giá theo bằng chứng đính kèm; không suy thiếu dữ liệu thành hợp lệ hoặc gian lận.',
        '', '## Giao dịch thuộc mẫu','', '| ID | Thời điểm | Loại | Số tiền VND | Nợ / Có | Kênh |', '|---|---|---|---:|---|---|']
    for row in rows:
        text.append('| '+' | '.join(cell(row.get(k,'')) for k in ('transaction_id','posted_at','txn_type','amount_vnd'))+
                    ' | '+cell(row.get('debit_account','')+'/'+row.get('credit_account',''))+' | '+cell(row.get('payment_channel',''))+' |')
    if not rows:
        text += ['', 'Đối tượng nguồn: '+cell(evidence['source_object'])+'. Không có giao dịch thành viên trong scope này.']
    text += ['', '## Bằng chứng và cách ghi kết luận','',
        '[Bảng dữ kiện theo thời điểm](evidence.json) giữ giao dịch, chứng từ và ngữ cảnh công ty đã biết trước cutoff. Tên bảng trong JSON là mã tham chiếu bằng chứng để ghi vào phiếu.',
        '', 'Ghi riêng: điều kiện nghiệp vụ có/không/chưa đủ căn cứ; hành động cụ thể cần thực hiện; tài liệu còn thiếu; lý do và tham chiếu; phút rà thực tế có loại thời gian nghỉ.',
        '', 'Cờ evidence_on_file trong nguồn là lời khai mô phỏng, không phải file chứng từ gốc. Tài liệu không đủ thì ghi unknown; không ghi no chỉ để hoàn tất phiếu.',
        '', 'Điền phiếu primary_reviews.csv. Không mở thư mục private hoặc các báo cáo mô hình trước khi ký xác nhận rà mù.']
    return '\n'.join(text)+'\n'


def load_tables(dataset):
    metadata = read_json(dataset/'manifest.json')
    source_checks(dataset,metadata)
    tables = {}
    for name in metadata['files']:
        if name in {'features.csv','labels.csv','splits.csv'} or not name.endswith('.csv'):
            continue
        tables[Path(name).stem] = read_csv(dataset/name)
    return tables


def prepare_review(comparison_root, output, *, seed=20261022):
    comparison_root,output = guarded(comparison_root),guarded(output)
    if output.exists():
        raise FileExistsError('Review preparation requires a fresh output directory')
    output_guard(output,comparison_root,comparison_root/'unused-model')
    if output.is_relative_to(comparison_root) or comparison_root.is_relative_to(output):
        raise ValueError('Review output must be separate from frozen comparisons')
    root = Path(__file__).resolve().parents[1]
    inputs = {str(Path(__file__).resolve()):sha(__file__)}
    runs = read_json(comparison_root/'verification.json')['runs']
    if len(runs)!=2 or {r.get('tag') for r in runs}!={'001','003'}:
        raise ValueError('Review preparation accepts frozen reporting cohorts 001/003 only')
    for run in runs:
        target = comparison_root/('sme_fraud_'+run['tag'])
        commitment = read_json(target/'predictions_frozen.json')
        for name,expected in commitment.items():
            path = guarded(target/name)
            if not path.is_relative_to(target) or sha(path)!=expected:
                raise ValueError('Frozen comparison checksum differs')
            inputs[str(path)] = expected
        inputs[str(target/'predictions_frozen.json')] = sha(target/'predictions_frozen.json')
        source = root/'data/synthetic_sources_20261017_v2'/('sme_fraud_'+run['tag'])
        metadata = read_json(source/'manifest.json')
        if metadata.get('role')!='reporting' or metadata.get('is_synthetic') is not True:
            raise ValueError('This prepared review requires synthetic reporting provenance')
        inputs[str(source/'manifest.json')] = sha(source/'manifest.json')
        inputs.update({str(source/name):h for name,h in source_checks(source,metadata).items()})
    output.mkdir(parents=True)
    private,public = output/'private',output/'public'
    private.mkdir();public.mkdir()
    write_json(private/'selection_plan.json',plan_for(inputs,seed))
    chosen, populations, table_cache = {}, {}, {}
    for run in runs:
        cohort = run['tag']
        source = root/'data/synthetic_sources_20261017_v2'/('sme_fraud_'+cohort)
        target = comparison_root/('sme_fraud_'+cohort)
        comparison_plan = read_json(target/'evaluation_plan.json')
        if any(sha(p)!=h for p,h in comparison_plan['code_sha256'].items()):
            raise ValueError('Comparison reconstruction code changed before reviewer sampling')
        inputs[str(source/'manifest.json')] = sha(source/'manifest.json')
        shadow = read_csv(target/'if_scores/shadow_scores.csv')
        scores = {r['transaction_id']:float(r['anomaly_score']) for r in shadow}
        snapshots,_,_ = build_snapshots(source,root/'reports/pipeline_rehearsal_20261018_v2'/('sme_fraud_'+cohort),comparison_plan['scope'],scores)
        units,pool_counts = choose_units(snapshots,read_csv(target/'budget_5/selections.private.csv'),cohort,seed=seed)
        chosen.update(units);populations.update(pool_counts)
        table_cache[cohort] = load_tables(source)
        print(cohort+': disagreement census and stratified references selected',flush=True)
    company_pairs = sorted({(d['cohort'],d['company_id']) for d in chosen.values()},key=lambda p:digest([seed,list(p)]))
    aliases = {pair:'DN'+str(i+1).zfill(2) for i,pair in enumerate(company_pairs)}
    order = sorted(chosen,key=lambda k:digest(['public_order',seed,k]))
    units, mapping, readonly = [], [], {}
    for i,key in enumerate(order,1):
        descriptor = chosen[key]
        review_id = 'MRV_'+digest(['opaque_review',seed,key])[:16]
        alias = aliases[(descriptor['cohort'],descriptor['company_id'])]
        folder = public/'evidence'/review_id;folder.mkdir(parents=True)
        evidence = evidence_for(descriptor,table_cache[descriptor['cohort']],alias)
        write_json(folder/'evidence.json',evidence)
        (folder/'review.md').write_text(card_markdown(review_id,evidence),encoding='utf-8')
        for name in ('evidence.json','review.md'):
            path = folder/name;readonly[path.relative_to(public).as_posix()] = sha(path)
        record = dict(review_unit_id=review_id,company_code=alias,cutoff_exclusive=descriptor['cutoff_exclusive'],
                      evidence_sha256=sha(folder/'evidence.json'),evidence_ref='evidence/'+review_id+'/review.md')
        units.append(record)
        mapping.append(dict(review_unit_id=review_id,unit_key=key,**{k:v for k,v in descriptor.items() if k!='case'}))
    write_csv(public/'primary_reviews.csv',units,PRIMARY_FIELDS)
    write_csv(public/'adjudications.csv',units,ADJ_FIELDS)
    instructions = '''# Hướng dẫn rà độc lập

Đây là bộ nguồn **mô phỏng**, không phải chứng từ SME thật. Chỉ giao thư mục public hoặc reviewer_packet.zip cho người rà. Các nhóm lựa chọn đã được trộn, không được cung cấp điểm mô hình, nhánh hoặc thứ hạng.

1. Mở REVIEW_INDEX.md rồi phiếu và evidence.json của từng mã. Chỉ dùng nguồn đã đóng băng tại cutoff; các cờ evidence_on_file không thay cho scan chứng từ gốc.
2. Điền primary_reviews.csv: condition_present/actionable là true, false hoặc unknown; document_request_needed là true/false. Có tài liệu thiếu phải ghi missing_evidence. Hành động hữu ích phải cụ thể, có căn cứ vượt ngoài yêu cầu tài liệu chung; không phải nhãn gian lận. actionable=true cần business_action. Thiếu căn cứ thì unknown, không tự biến thành false.
3. Ghi rationale và evidence_refs (tên các bảng trong evidence.json, cách nhau bằng dấu chấm phẩy). timing_method là measured_stopwatch hoặc measured_interval, không chấp nhận estimated. Ghi active_review_minutes đo thực tế, không dùng ước lượng mô phỏng. Với measured_interval, started_at/finished_at phải có múi giờ và paused_minutes; phút active phải khớp thời gian đã trừ nghỉ. Với đồng hồ bấm giờ có thể để cặp timestamp trống. Phút phân xử được ghi riêng theo cùng nguyên tắc.
4. Ghi primary_reviewer_id, reviewed_at và xác nhận independent_of_development=true, blind_to_arm_and_score=true chỉ khi đúng thực tế. Người đã phát triển/chọn model hoặc đã thấy nhánh/điểm của mẫu không ký như reviewer độc lập/mù.
5. Người phân xử khác người rà chính điền adjudications.csv, không xem nhánh/điểm. adjudication_status là confirmed/revised/unresolved. Mỗi kết luận cần căn cứ, phút phân xử thực tế, adjudicator_id và adjudicated_at. Chưa phân xử thì để trống, không sao chép máy móc kết luận.

Không điền 0 vào phút để thay cho thiếu dữ liệu. Không điền ký tên thay người khác. Mẫu đang thiếu tài liệu hoặc unresolved được báo riêng. Nguồn mô phỏng có review người thật vẫn chưa đóng cổng hiệu quả trên SME thật.
'''
    (public/'README.md').write_text(instructions,encoding='utf-8')
    index = ['# Danh sách phiếu rà','', '| Mã phiếu | Công ty | Cutoff loại trừ | Mở bằng chứng |','|---|---|---|---|']
    index += [f"| {u['review_unit_id']} | {u['company_code']} | {u['cutoff_exclusive']} | [Mở]({u['evidence_ref']}) |" for u in units]
    (public/'REVIEW_INDEX.md').write_text('\n'.join(index)+'\n',encoding='utf-8')
    for name in ('README.md','REVIEW_INDEX.md'):
        readonly[name] = sha(public/name)
    manifest = dict(version=VERSION,status='awaiting_human_independent_review',source_origin='synthetic_process_simulation',
                    units=units,readonly_sha256=readonly,forms_mutable=True,independent_reviews=0)
    write_json(public/'review_manifest.json',manifest)
    write_json(private/'unit_mapping.json',mapping)
    write_json(private/'sampling_populations.json',populations)
    write_json(private/'reviewer_assignment.json',dict(status='unassigned',primary_reviewer_id=None,adjudicator_id=None,
                                                     source='Awaiting user-provided human assignments'))
    if any(sha(p)!=h for p,h in inputs.items()):
        raise ValueError('Frozen preparation inputs changed')
    with zipfile.ZipFile(output/'reviewer_packet.zip','w',compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(public.rglob('*')):
            if path.is_file():
                archive.write(path,path.relative_to(public).as_posix())
    summary = dict(version=VERSION,status='prepared_awaiting_human_review',units=len(units),
                   sample_groups=dict(Counter(d['sample_group'] for d in chosen.values())),
                   source_origin='synthetic_process_simulation',independent_reviews=0,real_sme_reviews=0,
                   actionable_gain=None,actual_review_minutes=None,primary_reviewer_assigned=False,
                   adjudicator_assigned=False,model_fit=False,model_scored=False,queue_changed=False,
                   plan_sha256=sha(private/'selection_plan.json'),public_manifest_sha256=sha(public/'review_manifest.json'),
                   reviewer_zip_sha256=sha(output/'reviewer_packet.zip'),inputs_unchanged=True)
    write_json(output/'summary.json',summary)
    write_json(private/'prepared_commitment.json',dict(public_manifest_sha256=summary['public_manifest_sha256'],
               mapping_sha256=sha(private/'unit_mapping.json'),input_sha256=inputs))
    return summary


def _flag(value):
    if value not in {'true','false'}:
        raise ValueError('Use true or false explicitly')
    return value=='true'


def _minutes(value):
    number = float(value)
    if not math.isfinite(number) or number<=0:
        raise ValueError('Measured active minutes must be positive and finite')
    return number


def _measured_time(row,field,signed_at,cutoff):
    if row.get('timing_method') not in {'measured_stopwatch','measured_interval'}:
        raise ValueError('Actual timing must use measured_stopwatch or measured_interval, never an estimate')
    minutes = _minutes(row.get(field))
    if row.get('timing_method')=='measured_interval' or row.get('started_at') or row.get('finished_at'):
        start,end = instant(row.get('started_at')),instant(row.get('finished_at'))
        paused = float(row.get('paused_minutes'))
        if not math.isfinite(paused) or paused<0 or end<=start or end>signed_at or start<cutoff:
            raise ValueError('Invalid measured review interval or pauses')
        if abs((end-start).total_seconds()/60-paused-minutes)>.1:
            raise ValueError('Active minutes do not match elapsed time minus pauses')
    return minutes


def validate_reviews(prepared, primary_path, adjudication_path, output):
    prepared,output = guarded(prepared),guarded(output)
    if output.exists():
        raise FileExistsError('Validation output must be new')
    if output.is_relative_to(prepared/'public'):
        raise ValueError('Private validation results must not be published in the reviewer packet')
    manifest = read_json(prepared/'public/review_manifest.json')
    commitment = read_json(prepared/'private/prepared_commitment.json')
    if sha(prepared/'public/review_manifest.json')!=commitment['public_manifest_sha256']:
        raise ValueError('Review manifest changed after preparation')
    if any(sha(prepared/'public'/p)!=h for p,h in manifest['readonly_sha256'].items()):
        raise ValueError('Readonly reviewer evidence changed')
    mapping_path = prepared/'private/unit_mapping.json'
    if sha(mapping_path)!=commitment['mapping_sha256']:
        raise ValueError('Private sampling mapping changed')
    units = {u['review_unit_id']:u for u in manifest['units']}
    groups = {m['review_unit_id']:m['sample_group'] for m in read_json(mapping_path)}
    assignment = read_json(prepared/'private/reviewer_assignment.json')
    outcomes,errors,pending_ids = [],[],[]
    forms = {}
    for kind,path in (('primary',primary_path),('adjudication',adjudication_path)):
        rows = read_csv(guarded(path))
        indexed = {}
        for row in rows:
            rid = row.get('review_unit_id')
            if rid not in units or rid in indexed:
                raise ValueError('Unknown or duplicate review unit in '+kind)
            if any(row.get(f)!=str(units[rid][f]) for f in FORM_ID):
                raise ValueError('Immutable review identity/evidence binding changed')
            indexed[rid] = row
        forms[kind] = indexed
    for rid,unit in units.items():
        p,a = forms['primary'].get(rid,{}),forms['adjudication'].get(rid,{})
        if not p.get('primary_reviewer_id') or not a.get('adjudicator_id'):
            pending_ids.append(rid);continue
        try:
            if (not assignment.get('primary_reviewer_id') or not assignment.get('adjudicator_id')
                or p['primary_reviewer_id']!=assignment['primary_reviewer_id']
                or a['adjudicator_id']!=assignment['adjudicator_id'] or p['primary_reviewer_id']==a['adjudicator_id']
                or any(token in identifier.upper() for identifier in (p['primary_reviewer_id'],a['adjudicator_id'])
                       for token in ('ASSISTANT','BOT','AUTOMATION','SIM_'))):
                raise ValueError('Different assigned human reviewers are required')
            for row in (p,a):
                if not _flag(row.get('independent_of_development')) or not _flag(row.get('blind_to_arm_and_score')):
                    raise ValueError('Independent and blind attestations are required')
                if row.get('condition_present') not in {'true','false','unknown'} or row.get('actionable') not in {'true','false','unknown'}:
                    raise ValueError('Outcome must be true, false or unknown')
                requested = _flag(row.get('document_request_needed'))
                if requested and not row.get('missing_evidence','').strip():
                    raise ValueError('Missing documents must be specified')
                if row['actionable']=='true' and not row.get('business_action','').strip():
                    raise ValueError('Useful business action must be specific')
                if not row.get('rationale','').strip():
                    raise ValueError('Accounting rationale is required')
                refs = {s.strip() for s in row.get('evidence_refs','').split(';') if s.strip()}
                evidence = read_json(prepared/'public/evidence'/rid/'evidence.json')
                if not refs or not refs<=set(evidence['tables']):
                    raise ValueError('Evidence references must identify supplied source tables')
            if a.get('adjudication_status') not in {'confirmed','revised','unresolved'}:
                raise ValueError('Adjudication status is required')
            if a['adjudication_status']=='confirmed' and any(p.get(f)!=a.get(f) for f in ('condition_present','actionable','document_request_needed')):
                raise ValueError('Confirmed adjudication must agree with the primary outcome')
            if a['adjudication_status']=='unresolved' and a['actionable']!='unknown':
                raise ValueError('Unresolved adjudication cannot become a known outcome')
            reviewed,adjudicated = instant(p.get('reviewed_at')),instant(a.get('adjudicated_at'))
            if reviewed<instant(unit['cutoff_exclusive']) or adjudicated<reviewed:
                raise ValueError('Review/adjudication timestamps are inconsistent')
            minutes = _measured_time(p,'active_review_minutes',reviewed,instant(unit['cutoff_exclusive']))
            adj_minutes = _measured_time(a,'active_adjudication_minutes',adjudicated,instant(unit['cutoff_exclusive']))
            outcomes.append(dict(review_unit_id=rid,sample_group=groups[rid],condition_present=a['condition_present'],
                actionable=a['actionable'],missing_evidence=a.get('missing_evidence',''),
                document_request_needed=a['document_request_needed'],business_action=a.get('business_action',''),
                primary_minutes=minutes,adjudication_minutes=adj_minutes,adjudication_status=a['adjudication_status']))
        except (ValueError,TypeError,KeyError) as error:
            errors.append(dict(review_unit_id=rid,error=str(error)))
    result = dict(version=VERSION,status='pending_independent_reviews' if pending_ids or errors else 'reviews_validated',
        prepared_units=len(units),validated_independent_units=len(outcomes),
        known_actionable_outcomes=sum(r['actionable']!='unknown' for r in outcomes),
        unresolved_outcomes=sum(r['actionable']=='unknown' for r in outcomes),
        actionable_true=sum(r['actionable']=='true' for r in outcomes),
        missing_evidence_units=sum(r['document_request_needed']=='true' for r in outcomes),
        measured_primary_minutes=sum(r['primary_minutes'] for r in outcomes) if outcomes else None,
        measured_adjudication_minutes=sum(r['adjudication_minutes'] for r in outcomes) if outcomes else None,
        reference_review_minutes=sum(r['primary_minutes'] for r in outcomes if r['sample_group'].startswith('reference_')) if outcomes else None,
        pending_units=len(pending_ids),invalid_units=len(errors),errors=errors,
        actionable_gain=None,fraud_precision=None,fraud_recall=None,real_sme_reviews=0,
        source_origin=manifest['source_origin'],queue_changed=False,model_changed=False)
    output.mkdir(parents=True)
    write_json(output/'review_status.json',result)
    write_csv(output/'validated_outcomes.private.csv',outcomes,list(outcomes[0]) if outcomes else ['review_unit_id','actionable'])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command',required=True)
    prepare = commands.add_parser('prepare')
    prepare.add_argument('--comparison-root',type=Path,required=True)
    prepare.add_argument('--output',type=Path,required=True)
    prepare.add_argument('--seed',type=int,default=20261022)
    validate = commands.add_parser('validate')
    validate.add_argument('--prepared',type=Path,required=True)
    validate.add_argument('--primary',type=Path,required=True)
    validate.add_argument('--adjudications',type=Path,required=True)
    validate.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    if args.command=='prepare':
        result = prepare_review(args.comparison_root,args.output,seed=args.seed)
    else:
        result = validate_reviews(args.prepared,args.primary,args.adjudications,args.output)
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    main()
