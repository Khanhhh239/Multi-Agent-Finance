import pandas as pd
import pytest
from agent1.data.dr_comparison import paired_quotas,sample_company_invoices


def test_matched_invoice_counts_and_all_companies_are_preserved():
    left=pd.DataFrame(dict(company_key=['a','b','c'],n_invoices=[12,4,9]))
    right=pd.DataFrame(dict(company_key=['x','y','z'],n_invoices=[9,12,5]))
    paired=paired_quotas(left,right)
    assert paired.n_invoices.tolist()==[9,4,5]
    assert paired.n_invoices.sum()==18
    right.loc[0,'n_invoices']=0
    with pytest.raises(ValueError,match='origin'):paired_quotas(left,right)


def test_sampling_is_reproducible_and_future_invoices_cannot_enter_pool():
    inv=pd.DataFrame(dict(invoice_id=[f'i{x:02d}' for x in range(21)],firm_id=['f']*10+['g']*10+['f'],
        issue_date=pd.to_datetime(['2024-01-01']*20+['2025-01-01'])))
    quotas={'w/f':3,'w/g':5}
    first=sample_company_invoices(inv,quotas,'w','2024-07-01')
    second=sample_company_invoices(inv.iloc[:20],quotas,'w','2024-07-01')
    pd.testing.assert_frame_equal(first,second)
    assert first.groupby('firm_id').size().to_dict()=={'f':3,'g':5}


def test_shard_size_shrinks_under_memory_pressure():
    from agent1.data.dr_comparison import choose_shard_size
    assert choose_shard_size(600*1024**2)==2
    assert choose_shard_size(1500*1024**2)==4
    assert choose_shard_size(3*1024**3)==8


def test_snapshot_resume_matches_uninterrupted_run_and_rejects_corruption(tmp_path,monkeypatch):
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
    import run_dr_comparison as dr
    monkeypatch.setattr(dr,'SYNTH',tmp_path)
    worlds=[dict(name='w',parts=[dict(path='a'),dict(path='b')])]
    quotas={f'w/f{i}':1 for i in range(400)}
    for index,name in enumerate(['a','b']):
        directory=tmp_path/name;directory.mkdir()
        frame=pd.DataFrame(dict(invoice_id=[f'i{i}' for i in range(index*200,(index+1)*200)],
            firm_id=[f'f{i}' for i in range(index*200,(index+1)*200)],issue_date=pd.Timestamp('2019-01-01')))
        frame.to_parquet(directory/'invoices.parquet')
        frame[['invoice_id']].to_parquet(directory/'payments.parquet')
        frame[['invoice_id']].to_parquet(directory/'promises.parquet')
    class Builder:
        calls=0
        interrupt=True
        def __init__(self,inv,pay,prom):
            Builder.calls+=1
            if Builder.interrupt and Builder.calls==2:raise RuntimeError('interrupted')
            self.inv=inv
        def snapshot(self,cutoff):
            return self.inv[['invoice_id','firm_id']].assign(cutoff=cutoff,
                label_date=pd.Timestamp('2019-01-12'),writeoff_date=pd.NaT)
    monkeypatch.setattr(dr,'SnapshotBuilder',Builder)
    cache=tmp_path/'resumed.parquet'
    with pytest.raises(RuntimeError,match='interrupted'):
        dr.prepare_arm(worlds,quotas,pd.Timestamp('2019-01-15'),cache)
    Builder.interrupt=False;Builder.calls=0
    resumed=dr.prepare_arm(worlds,quotas,pd.Timestamp('2019-01-15'),cache)
    assert Builder.calls==1  # Mảnh đầu được đọc lại từ checkpoint đã kiểm hash.
    fresh=dr.prepare_arm(worlds,quotas,pd.Timestamp('2019-01-15'),tmp_path/'fresh.parquet')
    pd.testing.assert_frame_equal(resumed,fresh)
    cache.unlink()
    next((tmp_path/'resumed_parts').glob('*.parquet')).write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='checkpoint hash'):
        dr.prepare_arm(worlds,quotas,pd.Timestamp('2019-01-15'),cache)
