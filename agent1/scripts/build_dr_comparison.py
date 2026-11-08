"""WP-3.3: nguồn 1×400 và 20×20, shard nhỏ; không nhập toàn bộ thế giới vào RAM."""
from dataclasses import asdict
import gc
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
os.environ.update(AGENT1_THREADS='2',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='1')
import pandas as pd
import pyarrow.parquet as pq
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.paths import SYNTH,OUT,ROOT,RAW
from agent1.synth.world import World,WorldConfig
from agent1.data.contracts import validate_world
from agent1.data.dr_comparison import choose_shard_size
from build_multiworld import design


def hash_file(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def available_ram():
    if os.name!='nt':return None
    import ctypes
    class Memory(ctypes.Structure):
        _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong),
            *[(name,ctypes.c_ulonglong) for name in ['total','available','total_page','available_page','total_virtual','available_virtual','extended']]]
    state=Memory();state.length=ctypes.sizeof(state)
    return state.available if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)) else None


def configurations():
    control=WorldConfig(name='dr_cmp_control_400',seed=74001,n_firms=400,rng_version=2,write_xml=0)
    randomized=design(20,20,73)
    for index,config in enumerate(randomized):
        config.name=f'dr_cmp_multi_{index:03d}';config.rng_version=2
    return [('one_world',control),*[('twenty_worlds',config) for config in randomized]]


def main():
    directory=SYNTH/'dr_comparison_v1';directory.mkdir(exist_ok=True)
    output=OUT/'data';output.mkdir(exist_ok=True)
    configs=configurations();shard_size=8
    sources=[ROOT/p for p in [
        'agent1/synth/world.py','agent1/synth/names.py','agent1/calendar_vn.py','agent1/data/contracts.py',
        'scripts/build_multiworld.py','requirements-lock.txt','agent1/synth/calibration_vn.json']]
    sources.extend(sorted((ROOT/'agent1/rules').glob('*.json')))
    sources.extend([RAW/'oxcgrt/OxCGRT_compact_national_v1.csv',RAW/'wdi_vn/wdi_vietnam.csv'])
    source_hashes={str(p.relative_to(ROOT)):hash_file(p) if p.exists() else 'missing' for p in sources}
    fingerprint=hashlib.sha256(json.dumps(source_hashes,sort_keys=True).encode()).hexdigest()
    pd.DataFrame([dict(arm=arm,name=config.name,n_firms=config.n_firms,seed=config.seed,
        config=json.dumps(asdict(config))) for arm,config in configs]).to_csv(output/'DR_comparison_design.csv',index=False)
    manifest=dict(complete=False,max_shard_size=shard_size,adaptive_shards=True,generator_fingerprint=fingerprint,source_hashes=source_hashes,worlds=[],
        sampling='Raw worlds differ in invoice counts; comparison stage matches per-firm invoice quotas before feature construction',
        storage='Logical worlds stored in firm shards; local payment identity is (world,part,payment_id); feature cohorts namespace firm/invoice identities',
        test_used_for_selection=False)
    path=directory/'manifest.json'
    path.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    for arm,config in configs:
        world=dict(arm=arm,name=config.name,n_firms=config.n_firms,parts=[],config=asdict(config))
        start=0
        while start<config.n_firms:
            shard=directory/config.name/f'{start:04d}';marker=shard/'complete.json'
            if marker.exists():
                prior=json.loads(marker.read_text(encoding='utf-8'))
                indices=prior['signature']['indices']
                if not indices or indices!=list(range(start,start+len(indices))) or indices[-1]>=config.n_firms:
                    raise ValueError('Phạm vi checkpoint không liên tiếp')
                expected=dict(config=json.loads(json.dumps(asdict(config))),indices=indices,generator_fingerprint=fingerprint)
                if prior['signature']!=expected:raise ValueError('Shard khác cấu hình/mã; không ghi đè dữ liệu')
                for name,digest in prior['sha256'].items():
                    if hash_file(shard/name)!=digest:raise ValueError('Shard hỏng hash: '+str(shard/name))
                metadata=prior['metadata']
            else:
                if shutil.disk_usage(directory).free<2*1024**3:raise RuntimeError('Cần ít nhất 2 GiB dung lượng trống')
                while (available:=available_ram()) is not None and available<512*1024**2:
                    print('waiting for RAM',available,flush=True);time.sleep(15)
                size=choose_shard_size(available)
                indices=list(range(start,min(start+size,config.n_firms)))
                expected=dict(config=json.loads(json.dumps(asdict(config))),indices=indices,generator_fingerprint=fingerprint)
                began=time.monotonic();World(config).run(shard,firm_indices=indices,verbose=False)
                checks=validate_world(shard)
                firms=pd.read_parquet(shard/'firms.parquet',columns=['firm_id'])
                if set(firms.firm_id)!={f'F{i:03d}' for i in indices}:raise ValueError('Shard thiếu/sai mã công ty')
                metadata=dict(path=str(shard.relative_to(SYNTH)),n_firms=len(firms),
                    n_invoices=pq.ParquetFile(shard/'invoices.parquet').metadata.num_rows,
                    checks=len(checks),passed=int(checks.passed.sum()),seconds=time.monotonic()-began)
                marker.write_text(json.dumps(dict(signature=expected,metadata=metadata,
                    sha256={p.name:hash_file(p) for p in shard.glob('*.parquet')}),indent=2),encoding='utf-8')
            world['parts'].append(metadata)
            snapshot=dict(manifest,current_world=world)
            path.write_text(json.dumps(snapshot,indent=2),encoding='utf-8')
            print(config.name,start+len(indices),'/',config.n_firms,flush=True);gc.collect()
            start+=len(indices)
        if sum(part['n_firms'] for part in world['parts'])!=config.n_firms:raise ValueError('Thiếu công ty')
        manifest['worlds'].append(world)
        path.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        pd.DataFrame([dict(arm=w['arm'],world=w['name'],n_firms=w['n_firms'],n_invoices=sum(p['n_invoices'] for p in w['parts']),
            contracts_passed=all(p['checks']==p['passed'] for p in w['parts']),validation_scope='per firm shard; logical IDs namespaced',measurement_version='DR-400-firms-sharded-v1')
            for w in manifest['worlds']]).to_csv(output/'DR_comparison_build.csv',index=False)
    totals=pd.DataFrame(manifest['worlds']).groupby('arm').n_firms.sum()
    if set(totals.index)!={'one_world','twenty_worlds'} or not totals.eq(400).all():raise ValueError('Cần đúng 400 DN mỗi nhánh')
    manifest['complete']=True
    path.write_text(json.dumps(manifest,indent=2),encoding='utf-8')


if __name__=='__main__':main()
