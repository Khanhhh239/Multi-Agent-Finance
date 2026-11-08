"""Copy a reviewed ML workspace into an empty destination, preserving case data."""
import hashlib
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3

TABLES=('company_ml_data','company_ml_versions','company_ml_bindings','company_ml_events',
        'company_ml_runs','company_ml_imports','company_ml_label_changes',
        'ml_review_packets','ml_review_units','ml_review_work','ml_review_events')


@contextmanager
def readonly(path):
    path=Path(path).resolve()
    if not path.is_file() or any(part.casefold() in {'005','sme_fraud_005'} for part in path.parts):
        raise ValueError('Chọn database hiện có, ngoài holdout 005.')
    db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=30)
    db.row_factory=sqlite3.Row
    try:yield db
    finally:db.close()


@contextmanager
def _writable(path):
    db=sqlite3.connect(Path(path).resolve(),timeout=30)
    try:
        with db:yield db
    finally:db.close()


def inventory(db):
    result={}
    for table in TABLES:
        columns=[row[1] for row in db.execute('PRAGMA table_info("'+table+'")')]
        if not columns:raise ValueError('Database thiếu bảng ML: '+table)
        hashes=[]
        for row in db.execute('SELECT * FROM "'+table+'"'):
            values=[{'blob_sha256':hashlib.sha256(v).hexdigest()} if isinstance(v,bytes) else v for v in row]
            hashes.append(hashlib.sha256(json.dumps(values,ensure_ascii=False,separators=(',',':')).encode()).hexdigest())
        result[table]=dict(columns=columns,rows=len(hashes),sha256=hashlib.sha256(''.join(sorted(hashes)).encode()).hexdigest())
    return result


def _plan(source,target,source_db,target_db):
    incoming,current=inventory(source_db),inventory(target_db)
    if any(incoming[t]['columns']!=current[t]['columns'] for t in TABLES):
        raise ValueError('Schema ML của hai phiên không khớp; chưa chuyển dữ liệu.')
    if incoming==current:action='already_present'
    elif any(current[t]['rows'] for t in TABLES):
        raise ValueError('Phiên đích đã có dữ liệu ML khác. Chưa ghi đè hoặc trộn các tập dữ liệu.')
    else:action='copy'
    for row in source_db.execute('SELECT company_id,metadata FROM company_ml_data'):
        scenario=json.loads(row['metadata'])['scenario']
        if scenario=='005' or not target_db.execute('SELECT 1 FROM companies WHERE scenario=? AND company_id=?',(scenario,row['company_id'])).fetchone():
            raise ValueError('Dữ liệu ML ngoài phạm vi doanh nghiệp/bộ dữ liệu của phiên đích.')
    for row in source_db.execute('SELECT metadata FROM ml_review_packets'):
        meta=json.loads(row['metadata'])
        for company in meta['companies']:
            if meta['scenario']=='005' or not target_db.execute('SELECT 1 FROM companies WHERE scenario=? AND company_id=?',(meta['scenario'],company)).fetchone():
                raise ValueError('Gói phiếu rà ngoài phạm vi doanh nghiệp của phiên đích.')
    return dict(version='ml-workspace-merge-v1',source=str(Path(source).resolve()),target=str(Path(target).resolve()),
                action=action,source_tables=incoming,target_tables=current)


def plan_merge(source,target):
    if Path(source).resolve()==Path(target).resolve():raise ValueError('Nguồn và đích phải khác nhau.')
    with readonly(source) as source_db,readonly(target) as target_db:
        source_db.execute('BEGIN');target_db.execute('BEGIN')
        return _plan(source,target,source_db,target_db)


def merge_workspace(source,target,*,expected_plan):
    """The whole copy commits once, or leaves every destination row unchanged."""
    if Path(source).resolve()==Path(target).resolve():raise ValueError('Nguồn và đích phải khác nhau.')
    # Refuse missing targets before sqlite3.connect could create an empty file.
    with readonly(target):pass
    with readonly(source) as source_db,_writable(target) as target_db:
        source_db.execute('BEGIN');target_db.execute('BEGIN IMMEDIATE');target_db.row_factory=sqlite3.Row
        current=_plan(source,target,source_db,target_db)
        if current!=expected_plan:raise RuntimeError('Dữ liệu đổi sau khi lập kế hoạch. Kiểm tra và sao lưu lại trước khi chuyển.')
        if current['action']=='copy':
            for table in TABLES:
                columns=current['source_tables'][table]['columns']
                statement='INSERT INTO "'+table+'"('+','.join('"'+c.replace('"','""')+'"' for c in columns)+') VALUES('+','.join('?' for _ in columns)+')'
                target_db.executemany(statement,source_db.execute('SELECT * FROM "'+table+'"'))
        after=inventory(target_db)
        if after!=current['source_tables']:raise ValueError('Kết quả chuyển không khớp bản đã đối chiếu; hủy toàn bộ thay đổi.')
    return dict(current,after=after,rows_copied=sum(v['rows'] for v in after.values()) if current['action']=='copy' else 0)
