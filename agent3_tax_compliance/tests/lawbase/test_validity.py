"""End dates read from the replacing act's own effect clause; texts are the real clauses of 108/2025/QH15, 109/2025/QH15, 48/2024/QH15."""
import json
import sqlite3
import time

from src.lawbase import sync as S
from src.lawbase import validity as V

QLT = ('3. Luật Quản lý thuế số 38/2019/QH14 đã được sửa đổi, bổ sung một số điều theo Luật số 56/2024/QH15 (sau đây gọi là Luật Quản lý '
       'thuế số 38/2019/QH14) hết hiệu lực thi hành kể từ ngày Luật này có hiệu lực thi hành, trừ quy định tại khoản 1 và khoản 3 Điều 53 '
       'của Luật này; riêng quy định tại Điều 51 của Luật Quản lý thuế số 38/2019/QH14 hết hiệu lực thi hành kể từ ngày 01 tháng 01 năm 2026.')
TNCN = ('3. Luật Thuế thu nhập cá nhân số 04/2007/QH12 đã được sửa đổi, bổ sung một số điều theo Luật số 26/2012/QH13, Luật số 71/2014/QH13, '
        'Luật số 48/2024/QH15 hết hiệu lực kể từ ngày Luật này có hiệu lực thi hành')


def test_whole_act_with_exception_and_partial_statement():
    fs = V.read_clause(QLT, '2026-07-01')
    full = [f for f in fs if f.kind == 'FULL' and f.role == 'primary']
    assert [(f.target, f.eff_to) for f in full] == [('38/2019/QH14', '2026-07-01')]
    assert 'Điều 53' in full[0].exception
    part = [f for f in fs if f.kind == 'PARTIAL']
    assert [(f.target, f.eff_to) for f in part] == [('38/2019/QH14', '2026-01-01')]


def test_only_dedicated_amending_acts_end_with_the_act():
    assert V.dedicated_amendment('Luật Sửa đổi, bổ sung một số Điều của Luật Thuế thu nhập cá nhân số 26/2012/QH13', 'Thuế thu nhập cá nhân')
    assert not V.dedicated_amendment('Luật Thuế giá trị gia tăng số 48/2024/QH15', 'Thuế thu nhập cá nhân')
    assert not V.dedicated_amendment('Luật Sửa đổi, bổ sung một số điều của các luật về thuế số 71/2014/QH13', 'Thuế thu nhập cá nhân')
    assert not V.dedicated_amendment('Luật sửa đổi, bổ sung một số điều của Luật Chứng khoán, Luật Kế toán, Luật Quản lý thuế', 'Quản lý thuế')


def _db(tmp_path):
    db = sqlite3.connect(tmp_path / 'c.sqlite3')
    db.executescript("""CREATE TABLE documents(doc_id TEXT PRIMARY KEY, doc_num TEXT, title TEXT, eff_from TEXT, indexed INTEGER,
                          eff_to TEXT, doc_type TEXT);
                        CREATE TABLE provisions(doc_id TEXT, prov_id TEXT, text TEXT, level INTEGER, parent TEXT, ord INTEGER);""")
    docs = [('qlt25', '108/2025/QH15', 'Luật Quản lý thuế số 108/2025/QH15', '2026-07-01', 1),
            ('qlt19', '38/2019/QH14', 'Luật Quản lý thuế số 38/2019/QH14', '2020-07-01', 1),
            ('vbhn', '29/VBHN-VPQH', 'Văn bản hợp nhất số 29/VBHN-VPQH Luật Quản lý thuế số 38/2019/QH14', None, 1),
            ('tncn25', '109/2025/QH15', 'Luật Thuế thu nhập cá nhân số 109/2025/QH15', '2026-07-01', 1),
            ('tncn07', '04/2007/QH12', 'Luật Thuế thu nhập cá nhân số 04/2007/QH12', '2009-01-01', 1),
            ('sd12', '26/2012/QH13', 'Luật Sửa đổi, bổ sung một số Điều của Luật Thuế thu nhập cá nhân số 26/2012/QH13', '2013-07-01', 1),
            ('gtgt24', '48/2024/QH15', 'Luật Thuế giá trị gia tăng số 48/2024/QH15', '2025-07-01', 1)]
    db.executemany("INSERT INTO documents VALUES(?,?,?,?,?,NULL,'Luật')", docs)
    db.executemany('INSERT INTO provisions VALUES(?,?,?,4,NULL,1)', [('qlt25', 'k3', QLT), ('tncn25', 'k3', TNCN)])
    return db


def test_derive_on_a_small_corpus(tmp_path):
    db = _db(tmp_path)
    out = V.derive(db)
    ended = dict(db.execute('SELECT doc_id, eff_to FROM validity').fetchall())
    assert ended == {'qlt19': '2026-07-01', 'vbhn': '2026-07-01', 'tncn07': '2026-07-01', 'sd12': '2026-07-01'}
    assert 'gtgt24' not in ended                       # the VAT law only amended a few articles of the old PIT law
    kinds = {r[0]: r[1] for r in db.execute('SELECT doc_id, kind FROM validity_notes')}
    assert kinds.get('gtgt24') == 'AMENDING_KEPT'
    assert out['ended'] == 4 and len(out['changed']) == 4
    assert V.derive(db)['changed'] == []               # recomputing gives the same result


def test_index_decision_by_issue_year_and_status():
    scope = dict(min_year=2013, keep_expired_after='2023-01-01')
    old_circular = dict(issue_date='1990-03-05', doc_type='Thông tư', status_name='Còn hiệu lực', eff_to=None)
    old_law_in_force = dict(issue_date='2009-11-25', doc_type='Luật', status_name='Còn hiệu lực', eff_to=None)
    old_law_partly = dict(issue_date='2006-11-29', doc_type='Luật', status_name='Hết hiệu lực một phần', eff_to=None)
    assert S.index_decision(old_circular, False, scope)[0] is False
    assert S.index_decision(old_law_in_force, False, scope)[0] is True
    assert S.index_decision(old_law_partly, False, scope)[0] is False
    assert S.index_decision(old_circular, True, scope)[0] is True
    assert S.index_decision(dict(issue_date='2020-01-01', eff_to='2021-01-01'), False, scope)[0] is False


def test_sync_lock_is_seen_and_goes_stale(tmp_path):
    db = tmp_path / 'c.sqlite3'
    assert S.running_sync(db) is None
    S.lock_path(db).write_text(json.dumps(dict(pid=1, done=3)), encoding='utf-8')
    assert S.running_sync(db)['done'] == 3
    old = time.time() - S.LOCK_STALE_SECONDS - 5
    import os
    os.utime(S.lock_path(db), (old, old))
    assert S.running_sync(db) is None


def test_decomposed_diacritics_are_normalised():
    from src.lawbase.vbpl import flight_text
    nfd = 'self.__next_f.push([1,"Thu\u0065\u0302\u0301 gia\u0301 tri\u0323"])'
    assert flight_text(nfd) == 'Thuế giá trị'


def test_article_amending_an_ended_act_goes_stale(tmp_path):
    db = _db(tmp_path)
    db.execute("INSERT INTO documents VALUES('sd24','56/2024/QH15','Luật sửa đổi, bổ sung một số điều của Luật Chứng khoán, Luật Kế toán, Luật Quản lý thuế',"
               "'2025-01-01',1,NULL,'Luật')")
    db.execute("INSERT INTO documents VALUES('kt15','88/2015/QH13','Luật Kế toán số 88/2015/QH13','2017-01-01',1,NULL,'Luật')")
    rows = [('a2', 3, 'Điều 2. Sửa đổi, bổ sung một số điều của Luật Kế toán', None, 1), ('a2k1', 4, '1. Sửa đổi khoản 1 Điều 9', 'a2', 2),
            ('a6', 3, 'Điều 6. Sửa đổi, bổ sung một số điều của Luật Quản lý thuế', None, 3), ('a6k1', 4, '1. Sửa đổi Điều 31', 'a6', 4)]
    db.executemany("INSERT INTO provisions VALUES('sd24',?,?,?,?,?)", [(r[0], r[2], r[1], r[3], r[4]) for r in rows])
    V.derive(db)
    stale = {r[0]: (r[1], r[2]) for r in db.execute("SELECT prov_id, ended_on, target_num FROM stale_provisions WHERE doc_id='sd24'")}
    assert stale == {'a6': ('2026-07-01', '38/2019/QH14'), 'a6k1': ('2026-07-01', '38/2019/QH14')}   # Luật Kế toán is still in force


def test_replace_and_repeal_lists_from_the_2026_decrees():
    items = [('a', 'a) Nghị định số 126/2020/NĐ-CP ngày 19 tháng 10 năm 2020 của Chính phủ quy định chi tiết một số điều của Luật Quản lý thuế;'),
             ('b', 'b) Nghị định số 91/2022/NĐ-CP ngày 30 tháng 10 năm 2022 của Chính phủ sửa đổi, bổ sung một số điều của Nghị định số 126/2020/NĐ-CP')]
    got = [(f.target, f.kind, f.eff_to, p) for f, p in V.read_replace_clause('3. Nghị định này thay thế:', items, '2026-07-01')]
    assert got == [('126/2020/NĐ-CP', 'FULL', '2026-07-01', 'a'), ('91/2022/NĐ-CP', 'FULL', '2026-07-01', 'b')]
    inline = V.read_replace_clause('2. Nghị định này thay thế Nghị định số 65/2013/NĐ-CP ngày 27 tháng 6 năm 2013 của Chính phủ', [], '2026-07-01')
    assert [(f.target, f.kind) for f, _ in inline] == [('65/2013/NĐ-CP', 'FULL')]
    part = V.read_replace_clause('4. Thông tư này bãi bỏ nội dung tại các Thông tư sau:',
                                 [('a', 'a) Điều 7 Thông tư số 43/2023/TT-BTC ngày 27 tháng 6 năm 2023')], '2026-07-01')
    assert [(f.target, f.kind) for f, _ in part] == [('43/2023/TT-BTC', 'PARTIAL')]
    point = V.read_replace_clause('3. Thông tư này bãi bỏ:', [('d', 'đ) Điểm a và điểm c khoản 2; khoản 3 Điều 4 Thông tư số 18/2026/TT-BTC')], '2026-07-01')
    assert [(f.target, f.kind) for f, _ in point] == [('18/2026/TT-BTC', 'PARTIAL')]
    assert V.read_replace_clause('5. Thông tư này thay thế mẫu số 01/TKN-CNKD kèm theo Thông tư số 50/2026/TT-BTC', [], '2026-07-01') == []


def test_list_of_expired_decrees_from_254_2026():
    head = '2. Kể từ ngày Nghị định này có hiệu lực thi hành, các Nghị định sau đây hết hiệu lực thi hành:'
    items = [('a', 'a) Nghị định số 123/2020/NĐ-CP ngày 19 tháng 10 năm 2020 của Chính phủ quy định về hóa đơn, chứng từ;'),
             ('b', 'b) Điều 1 Nghị định số 41/2022/NĐ-CP ngày 20 tháng 6 năm 2022 của Chính phủ sửa đổi, bổ sung một số điều của Nghị định số 123/2020/NĐ-CP'),
             ('c', 'c) Nghị định số 70/2025/NĐ-CP ngày 20 tháng 3 năm 2025 của Chính phủ sửa đổi, bổ sung một số điều của Nghị định số 123/2020/NĐ-CP')]
    got = [(f.target, f.kind) for f, _ in V.read_replace_clause(head, items, '2026-07-01')]
    assert got == [('123/2020/NĐ-CP', 'FULL'), ('41/2022/NĐ-CP', 'PARTIAL'), ('70/2025/NĐ-CP', 'FULL')]
    assert V.read_clause(head, '2026-07-01') == []       # no number before "hết hiệu lực": not read twice
