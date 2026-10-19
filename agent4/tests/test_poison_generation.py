from pathlib import Path
import duckdb
from eval.gen.poison_warehouse import payloads,poison_copy


def test_poison_copy_changes_only_copy_descriptions_and_version(tmp_path,warehouse):
    out=tmp_path/'poison.duckdb'
    report=poison_copy(warehouse,out,'train')
    assert report['amounts_unchanged']
    with duckdb.connect(str(warehouse),read_only=True) as source,duckdb.connect(str(out),read_only=True) as copied:
        assert copied.execute('SELECT COUNT(*) FROM eval_poison_manifest').fetchone()[0]==20
        sql='SELECT SUM(debit_amount),SUM(credit_amount) FROM gl_entry'
        assert source.execute(sql).fetchall()==copied.execute(sql).fetchall()
        assert dict(source.execute('SELECT key,value FROM company_info').fetchall())['data_version']=='v2.1'
        assert dict(copied.execute('SELECT key,value FROM company_info').fetchall())['data_version']=='v2.1-p2-poison1'


def test_twenty_attack_techniques_and_distinct_split_surfaces():
    assert all(len(payloads(s))==20 for s in ('train','val','test'))
    assert not set(payloads('train'))&set(payloads('val'))
