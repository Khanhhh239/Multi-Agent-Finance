"""Read-only FATURA2 download audit; writes metadata reports, never imports data."""
from pathlib import Path, PurePosixPath
from collections import Counter, defaultdict
from hashlib import md5, sha256
import ast
import csv
import json
import re
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
INCOMING = ROOT / 'data invoice/plan00_incoming'
ARCHIVE = INCOMING / 'FATURA2.zip'
EXTRACTED = INCOMING / 'FATURA2'
DATA = EXTRACTED / 'invoices_dataset_final'
OUTPUT = ROOT / 'docs/agent3/plans/evidence/plan00/fatura_download_check.json'
EXPECTED_MD5 = '4c9404462f22c5241eb1a290a02eb2a2'


def main():
    h = md5(); s = sha256()
    with ARCHIVE.open('rb') as f:
        for blob in iter(lambda: f.read(1024*1024), b''):
            h.update(blob); s.update(blob)
    print('Archive hashed', flush=True)
    errors = []
    counts = Counter(); classes = Counter(); field_coverage = Counter()
    image_ids = defaultdict(set); annotation_ids = defaultdict(set)
    shape_examples = {}
    issue_counts = Counter(); issue_examples = defaultdict(list)
    def issue(code, path):
        issue_counts[code] += 1
        if len(issue_examples[code]) < 5:
            issue_examples[code].append(path)
    with zipfile.ZipFile(ARCHIVE) as z:
        members = [i for i in z.infolist() if not i.is_dir()]
        bad = z.testzip()
        if bad: errors.append({'code':'ZIP_CRC_ERROR','path':bad})
        print('Archive CRC checked; verifying extracted files', flush=True)
        member_names = {i.filename for i in members}
        for n, info in enumerate(members):
            name = info.filename
            parts = PurePosixPath(name)
            if parts.is_absolute() or '..' in parts.parts:
                errors.append({'code':'UNSAFE_ARCHIVE_PATH','path':name}); continue
            path = EXTRACTED.joinpath(*parts.parts)
            if not path.is_file():
                errors.append({'code':'MISSING_EXTRACTED_FILE','path':name}); continue
            blob = path.read_bytes()
            if len(blob)!=info.file_size or zlib.crc32(blob)!=info.CRC:
                errors.append({'code':'EXTRACTION_CONTENT_MISMATCH','path':name}); continue
            counts[path.suffix.lower()] += 1
            match = re.search(r'Template(\d+)_Instance(\d+)', path.name)
            logical = f'Template{match[1]}_Instance{match[2]}' if match else None
            if path.suffix.lower()=='.jpg':
                family = path.parent.name
                image_ids[family].add(logical)
                # Header dimensions, not OCR or full pixel decoding.
                from PIL import Image
                try:
                    with Image.open(path) as im:
                        if im.width<=0 or im.height<=0: raise ValueError('bad dimensions')
                        shape_examples.setdefault(family, list(im.size))
                except Exception as exc:
                    errors.append({'code':'IMAGE_HEADER_ERROR','path':name,'type':type(exc).__name__})
            if path.suffix.lower()=='.json':
                fmt = path.parent.name
                annotation_ids[fmt].add(logical)
                try: obj=json.loads(blob)
                except Exception:
                    errors.append({'code':'INVALID_JSON','path':name}); continue
                shape_examples.setdefault(fmt, {'keys':list(obj) if isinstance(obj,dict) else 'list'})
                if fmt=='Original_Format':
                    for key,value in obj.items():
                        classes[key]+=1
                        if isinstance(value,dict) and value.get('text'):
                            field_coverage[key]+=1
                        if isinstance(value,dict) and isinstance(value.get('bbox'),list):
                            box=value['bbox']
                            if len(box)==2 and all(isinstance(p,list) and len(p)==2 for p in box):
                                (x0,y0),(x1,y1)=box
                                if x0>x1 or y0>y1: issue('ORIGINAL_REVERSED_BBOX',name)
                else:
                    boxes=obj.get('boxes',[])
                    labels=obj.get('class_labels',obj.get('labels',[]))
                    if labels and len(boxes)!=len(labels): issue('BOX_LABEL_LENGTH_MISMATCH',name)
                    if any(len(b)!=4 for b in boxes): issue('BOX_WRONG_LENGTH',name)
            if n and n%10000==0: print(f'Verified {n} extracted files',flush=True)
        extras = sum(1 for p in EXTRACTED.rglob('*') if p.is_file() and p.relative_to(EXTRACTED).as_posix() not in member_names)
    white=image_ids['images']
    for kind,ids in [*image_ids.items(),*annotation_ids.items()]:
        if ids!=white:
            errors.append({'code':'IMAGE_ANNOTATION_IDS_MISMATCH','kind':kind,'missing':len(white-ids),'extra':len(ids-white)})
    template_counts=Counter(re.match(r'Template(\d+)_',name)[1] for name in white)
    strat1={}; strat1_templates={}
    for split in ['train','dev','test']:
        with (DATA/f'strat1_{split}.csv').open(encoding='utf-8-sig',newline='') as f:
            rows=list(csv.DictReader(f))
        ids={Path(r['img_path']).stem for r in rows}
        strat1[split]=ids
        strat1_templates[split]={re.match(r'Template(\d+)_',x)[1] for x in ids}
        if len(ids)!=len(rows) or not ids<=white:
            errors.append({'code':'INVALID_STRAT1_MEMBERS','split':split})
        if any(Path(r['annot_path']).stem!=Path(r['img_path']).stem for r in rows):
            errors.append({'code':'STRAT1_PAIR_MISMATCH','split':split})
    strat2={}
    for line in (DATA/'Strat2_Split.txt').read_text(encoding='utf-8').splitlines():
        if not line.strip():continue
        key,expr=line.split('=',1);key=key.strip();expr=expr.strip()
        strat2[key]=list(strat2[expr]) if expr in strat2 else ast.literal_eval(expr)
    intersections={f'{a}_{b}':len(strat1[a]&strat1[b]) for a,b in [('train','dev'),('train','test'),('dev','test')]}
    if any(intersections.values()) or set.union(*strat1.values())!=white:
        errors.append({'code':'STRAT1_PARTITION_ERROR'})
    passed = h.hexdigest()==EXPECTED_MD5 and not errors
    report={
        'schema_version':'1.0.0','checked_date':'2026-10-11',
        'source_url':'https://zenodo.org/records/10371464',
        'script_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),
        'archive':{'path':ARCHIVE.relative_to(ROOT).as_posix(),'size_bytes':ARCHIVE.stat().st_size,
                   'md5':h.hexdigest(),'expected_md5':EXPECTED_MD5,'md5_matches':h.hexdigest()==EXPECTED_MD5,'sha256':s.hexdigest(),
                   'crc_pass':bad is None,'files':len(members)},
        'extracted_files_match_archive':not errors,'extra_extracted_files':extras,
        'file_counts_by_extension':dict(counts),'images_by_variant':{k:len(v) for k,v in image_ids.items()},
        'annotations_by_format':{k:len(v) for k,v in annotation_ids.items()},
        'logical_invoice_instances':len(white),'templates':len(template_counts),
        'instances_per_template_range':[min(template_counts.values()),max(template_counts.values())],
        'documentation_files':[n for n in member_names if any(w in Path(n).name.lower() for w in ['readme','license','licence','copying'])],
        'original_field_presence':dict(field_coverage),'original_class_keys':sorted(classes),
        'shape_examples':shape_examples,'annotation_issue_counts':dict(issue_counts),
        'strat1_counts':{k:len(v) for k,v in strat1.items()},'strat1_instance_overlap':intersections,
        'strat1_templates_per_split':{k:len(v) for k,v in strat1_templates.items()},
        'strat2_template_counts':{k:len(v) for k,v in strat2.items()},
        'strat2_dev_test_template_overlap':len(set(strat2['dev_inds'])&set(strat2['test_inds'])),
        'download_integrity':'PASS' if passed else 'FAIL','errors':errors,
        'license_status':'NOT_CONFIRMED_FROM_LOCAL_ARCHIVE_OR_RENDERED_RECORD',
        'pipeline_imported':False,'ocr_or_training_run':False,
        'scope_limitations':['GENERATED_INTERNATIONAL_INVOICES_NOT_REAL_VIETNAMESE_TAX_INVOICES','NO_PDF','NO_INDEPENDENT_ANNOTATION_REVIEW','FORMAT_MAPPING_AND_COORDINATE_AUDIT_REQUIRED']}
    OUTPUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    local=ROOT/'data invoice/plan00_local/fatura_annotation_issue_examples.json'
    local.write_text(json.dumps(dict(issue_examples),indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True),flush=True)
    raise SystemExit(0 if passed else 1)


if __name__=='__main__':main()
