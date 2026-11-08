"""Aggregate persisted before/after artifacts; never derive labels from output."""
import json
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data invoice/real_invoice_pilot_v1'
PUBLIC=ROOT/'docs/agent3/plans/evidence/real_invoice_pilot_v1'


def read(path):return json.loads(path.read_text(encoding='utf-8'))


def score(artifact,labels):
    counts=Counter();record=artifact['record']
    for path,expected in labels['fields'].items():
        field=record
        for part in path.split('.'):field=field.get(part) if field else None
        status=field['status'] if field else 'NO_RECORD'
        outcome=('CORRECT' if field['value']==expected else 'WRONG') if status=='PRESENT' else status
        counts[outcome]+=1
    return dict(counts)


def main():
    PUBLIC.mkdir(parents=True,exist_ok=True)
    gold=read(DATA/'labels.json');rows=[];fingerprints={}
    for phase,folder in [('before','before_labeled'),('after','verified_all_fields')]:
        fingerprints[phase]=set()
        for file in sorted((DATA/folder).glob('*.json')):
            if file.name=='summary.json':continue
            artifact=read(file)
            case=next((name for name in gold if file.stem.startswith(name+'-')),None)
            if not case:continue
            mode=file.stem[len(case)+1:]
            if phase=='before' and mode!='native_only':continue
            fingerprints[phase].add(artifact['extractor_sha256'])
            label=gold[case];record=artifact['record']
            rows.append(dict(phase=phase,case=case,mode=mode,
                group='unverified_training_source' if case.startswith('accounting_training') else 'public_document_pilot',
                counts=score(artifact,label),expected_items=label.get('item_count'),
                discovered_items=len(record['items']) if record else None,
                item_discovery_status=record['item_discovery_status'] if record else None))
    if any(len(values)!=1 for values in fingerprints.values()):raise ValueError('Mixed extractor versions in a comparison phase')
    result=dict(label_method='agent visual transcription; no independent human adjudication',
        label_scope='Selected names, tax IDs, invoice identifiers/date, printed totals and explicit currency. Addresses excluded from metric.',
        number_locale='VI explicitly configured in both phases; application default remains AUTO',
        extractor_fingerprints={k:next(iter(v)) for k,v in fingerprints.items()},
        scan_origin='Rasterized copies of 3 native PDFs, not 3 additional real scans',rows=rows,aggregates=[])
    for phase,mode,group in sorted({(r['phase'],r['mode'],r['group']) for r in rows}):
        matching=[r for r in rows if (r['phase'],r['mode'],r['group'])==(phase,mode,group)]
        counts=Counter()
        for row in matching:counts.update(row['counts'])
        result['aggregates'].append(dict(phase=phase,mode=mode,group=group,documents=len(matching),counts=dict(counts)))
    sources=read(DATA/'sources.json')
    result['sources']=[{k:v for k,v in row.items() if k!='page_inventory'} for row in sources]
    (PUBLIC/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result['aggregates'],indent=2))


if __name__=='__main__':main()
