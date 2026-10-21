"""Sinh bốn thế giới lớn có resume, kiểm dung lượng và giới hạn tiến trình."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
# Áp trước khi import NumPy/LightGBM, kể cả khi Windows spawn tiến trình con.
os.environ.update(AGENT1_THREADS='2', OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2')
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent1.paths import SYNTH, OUT
from agent1.synth.world import WorldConfig, World
from agent1.data.contracts import validate_world


def configurations(firms=150, count=4, prefix='big'):
    if firms < 1 or not 1 <= count <= 4 or prefix not in {'big', 'big_smoke'}:
        raise ValueError('Cần 1–4 thế giới, số công ty dương, prefix big hoặc big_smoke')
    calibration = json.loads((SYNTH/'calibration_fit.json').read_text(encoding='utf-8'))
    return [WorldConfig(name=f'{prefix}_{i:03d}', seed=81000+i, n_firms=firms, write_xml=0,
        rng_version=2, tail=['atradius','uk','coface','atradius'][i], late_scale=[1.,1.,1.,1.35][i],
        ontime_shift=calibration['ontime_shift'], pd_mult=calibration['pd_mult']) for i in range(count)]


def merge_shards(parts, target):
    """Ghép theo thứ tự công ty, không giữ toàn bộ thế giới trong RAM."""
    target.mkdir(parents=True,exist_ok=True)
    for table_path in sorted(parts[0].glob('*.parquet')):
        name=table_path.name
        sources=parts[:1] if name=='macro.parquet' else parts
        schemas=[pq.ParquetFile(part/name).schema_arrow for part in sources]
        fields=[]
        for field in schemas[0]:
            choices=[schema.field(field.name).type for schema in schemas]
            concrete=[kind for kind in choices if not pa.types.is_null(kind)]
            kind=concrete[0] if concrete else field.type
            if any(pa.types.is_timestamp(c) and c.unit=='ns' for c in concrete):kind=pa.timestamp('ns')
            fields.append(pa.field(field.name,kind,nullable=True))
        schema=pa.schema(fields);offset=0
        temporary=target/(name+'.tmp')
        with pq.ParquetWriter(temporary,schema,compression='snappy') as writer:
            for source in sources:
                for batch in pq.ParquetFile(source/name).iter_batches(batch_size=65536):
                    data=pa.Table.from_batches([batch])
                    if name=='payments.parquet':
                        index=data.schema.get_field_index('payment_id')
                        data=data.set_column(index,'payment_id',pa.array([f'P{i:08d}' for i in range(offset,offset+len(data))]))
                        offset+=len(data)
                    writer.write_table(data.cast(schema))
        temporary.replace(target/name)


def build(config, shard_size=12):
    os.environ.update(AGENT1_THREADS='2', OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2')
    began=time.monotonic(); path=SYNTH/config.name
    if (path/'config.json').exists():
        existing=json.loads((path/'config.json').read_text(encoding='utf-8'))
        expected=json.loads(json.dumps(asdict(config)))
        if existing != expected:
            raise ValueError(f'{config.name}: cấu hình khác dữ liệu hiện có; không ghi đè')
        validate_world(path)
        resumed=True
    else:
        parts=[]
        for start in range(0,config.n_firms,shard_size):
            indices=list(range(start,min(start+shard_size,config.n_firms)))
            part=path/'.parts'/f'{start:04d}';marker=part/'shard_indices.json'
            if not marker.exists():
                World(config).run(part,firm_indices=indices)
                marker.write_text(json.dumps(indices),encoding='utf-8')
            elif json.loads(marker.read_text())!=indices:
                raise ValueError('Shard hiện có khác phạm vi công ty yêu cầu')
            validate_world(part)
            parts.append(part)
        merge_shards(parts,path)
        validate_world(path)
        (path/'config.json').write_text(json.dumps(asdict(config),indent=2),encoding='utf-8')
        resumed=False
    digest=hashlib.sha256()
    files=sorted(path.glob('*.parquet'))
    for file in files:
        with file.open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024*1024), b''):digest.update(chunk)
    return dict(world=config.name,n_firms=config.n_firms,
        n_invoices=pq.ParquetFile(path/'invoices.parquet').metadata.num_rows,
        bytes=sum(file.stat().st_size for file in files),tables_sha256=digest.hexdigest(),
        seconds=time.monotonic()-began,resumed=resumed,contracts_passed=True,timing_valid=True,
        seed=config.seed,shard_size=shard_size,measurement_version='big-world-rng2-v3-streamed-timing')


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--firms',type=int,default=150)
    parser.add_argument('--count',type=int,default=4);parser.add_argument('--workers',type=int,default=1)
    parser.add_argument('--prefix',default='big',choices=['big','big_smoke'])
    args=parser.parse_args()
    configs=configurations(args.firms,args.count,args.prefix)
    pending=[c for c in configs if not (SYNTH/c.name/'config.json').exists()]
    # Ước lượng bảo thủ; không xóa cache/dữ liệu để lấy chỗ trống.
    required=1024**3+sum(c.n_firms for c in pending)*2_000_000
    free_disk=shutil.disk_usage(SYNTH).free
    free_ram=None
    if os.name=='nt':
        import ctypes
        class MemoryStatus(ctypes.Structure):
            _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong),
                *[(name,ctypes.c_ulonglong) for name in ['total_phys','avail_phys','total_page','avail_page','total_virtual','avail_virtual','extended']]]
        status=MemoryStatus();status.length=ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):free_ram=status.avail_phys
    required_ram=max(768*1024**2,args.firms*8*1024**2)*max(1,min(args.workers,args.count,4))
    capacity=dict(free_disk=free_disk,required_disk=required,free_ram=free_ram,required_ram=required_ram,
        can_start=free_disk>=required and (free_ram is None or free_ram>=required_ram),
        estimate='Conservative planning estimate; not a measured performance result')
    (OUT/'data').mkdir(exist_ok=True)
    (OUT/'data/build_big_capacity.json').write_text(json.dumps(capacity,indent=2),encoding='utf-8')
    if not capacity['can_start']:
        raise SystemExit('Chưa đủ tài nguyên an toàn cho cấu hình này: '+json.dumps(capacity))
    rows=[]; directory=OUT/'data';directory.mkdir(exist_ok=True)
    output=directory/('big_worlds_smoke.csv' if args.prefix=='big_smoke' else 'big_worlds.csv')
    with ProcessPoolExecutor(max_workers=max(1,min(args.workers,4))) as executor:
        jobs={executor.submit(build,config):config.name for config in configs}
        for future in as_completed(jobs):
            row=future.result();rows.append(row)
            pd.DataFrame(rows).sort_values('world').to_csv(output,index=False)
            print(json.dumps(row),flush=True)


if __name__=='__main__':main()
