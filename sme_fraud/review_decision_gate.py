"""One authoritative request store and final-decision gate for web and CLI."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import uuid

from .case_identity import digest, scope_hash
from .information_requests import ACTIVE,InformationRequests

BINDING_FILE='review_store_binding.json'


def read_binding(directory):
    path=Path(directory)/BINDING_FILE
    if not path.is_file():
        raise RuntimeError('Chưa xác định SQLite có thẩm quyền. Chuẩn bị/khôi phục ReviewStore trước khi kết luận cuối.')
    binding=json.loads(path.read_text(encoding='utf-8'))
    checksum=binding.pop('checksum',None)
    if checksum!=digest(binding) or binding.get('version')!=1:
        raise ValueError('Liên kết kho rà soát không hợp lệ; kiểm tra bản sao lưu.')
    return dict(binding,checksum=checksum)


def write_binding(directory,binding):
    directory=Path(directory)
    binding={k:v for k,v in binding.items() if k!='checksum'}
    binding['checksum']=digest(binding)
    temporary=directory/('.binding-'+uuid.uuid4().hex+'.json')
    try:
        with temporary.open('x',encoding='utf-8') as stream:
            stream.write(json.dumps(binding,ensure_ascii=False,indent=2)+'\n');stream.flush();os.fsync(stream.fileno())
        temporary.replace(directory/BINDING_FILE)
    finally:temporary.unlink(missing_ok=True)
    return binding


def assert_binding(db,directory,database,scenario):
    binding=read_binding(directory)
    if (binding['scenario']!=scenario or Path(binding['database']).resolve()!=Path(database).resolve() or
            Path(binding['report_path']).resolve()!=Path(directory).resolve()):
        raise RuntimeError('Thư mục hồ sơ đã gắn với SQLite/phạm vi khác. Dùng đúng kho hoặc khôi phục sang thư mục mới.')
    proof=db.execute('SELECT value FROM settings WHERE key=?',('review_binding:'+scenario,)).fetchone()
    if not proof or proof[0]!=binding['binding_id']:
        raise RuntimeError('SQLite không khớp liên kết hồ sơ; không coi DB trống là không có yêu cầu tài liệu.')
    return binding


def bind_store(db,directory,database,scenario):
    """Caller holds feedback_lock and its normal SQLite transaction."""
    path=Path(directory)/BINDING_FILE
    proof=db.execute('SELECT value FROM settings WHERE key=?',('review_binding:'+scenario,)).fetchone()
    if path.exists():return assert_binding(db,directory,database,scenario)
    if proof:
        raise RuntimeError('Thiếu file liên kết kho rà soát; khôi phục file từ bản sao lưu.')
    binding=dict(version=1,binding_id=uuid.uuid4().hex,scenario=scenario,
        database=str(Path(database).resolve()),report_path=str(Path(directory).resolve()))
    db.execute('INSERT INTO settings VALUES(?,?)',('review_binding:'+scenario,binding['binding_id']))
    return write_binding(directory,binding)


def check_decision(directory,case,decision,*,expected_database=None):
    """Called under feedback_lock until the decision has been appended and fsynced."""
    try:binding=read_binding(directory)
    except RuntimeError:
        # An unmanaged historical report can still collect missing-information
        # notes. It cannot assert a final verdict without knowing its request DB.
        if decision=='information_gap' and not (Path(directory)/'case_identity.json').is_file():return
        raise
    database=Path(binding['database']).resolve()
    if expected_database is not None and database!=Path(expected_database).resolve():
        raise RuntimeError('Web/CLI đang dùng SQLite khác kho đã gắn với hồ sơ.')
    if not database.is_file():raise RuntimeError('Không tìm thấy SQLite rà soát; khôi phục trước khi ghi kết luận.')
    with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True,timeout=15)) as db:
        db.row_factory=sqlite3.Row;db.execute('BEGIN')
        assert_binding(db,directory,database,binding['scenario'])
        saved=db.execute('SELECT data FROM cases WHERE scenario=? AND case_id=?',(binding['scenario'],case['case_id'])).fetchone()
        if not saved or scope_hash(json.loads(saved[0]))!=scope_hash(case):
            raise RuntimeError('Phạm vi hồ sơ và SQLite không khớp; tải/chuẩn bị lại snapshot trước khi lưu.')
        history=InformationRequests.history(db)
        current_scope=scope_hash(case)
        latest={e['request_id']:e for e in history if e['scenario']==binding['scenario'] and
                e['company_id']==case['company_id'] and e['case_scope_hash']==current_scope}
        if decision!='information_gap' and any(e['status'] in ACTIVE for e in latest.values()):
            raise RuntimeError('Còn yêu cầu tài liệu đang mở/đã nhận. Rà lại hoặc hủy có lý do trước khi kết luận.')
