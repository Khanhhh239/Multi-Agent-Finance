"""Seal unseen source/layout groups; never rebrand a development pilot as test."""
import hashlib
import json
from pathlib import Path


def seal(entries,used_groups,root):
    root=Path(root).resolve();seen=set();rows=[]
    for entry in entries:
        group=entry['group_id'];layout=entry['layout_group'];source=entry['source_group']
        if any(value in used_groups for value in (group,layout,source)):
            raise ValueError('Development source/layout overlaps holdout')
        path=(root/entry['path']).resolve()
        if not path.is_relative_to(root) or not path.is_file():raise ValueError('Invalid holdout file')
        if entry.get('split')!='test':raise ValueError('Holdout must explicitly declare test split')
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in seen:raise ValueError('Duplicate/derived invoice must share one evaluation group')
        seen.add(digest)
        rows.append({**entry,'sha256':digest})
    payload={'version':'ocr-holdout-v1','entries':rows,'used_groups':sorted(used_groups),
        'status':'SEALED_UNSCORED' if rows else 'PENDING_UNSEEN_DATA',
        'independent_label_acceptance':False,'accuracy_evaluated':False}
    payload['manifest_sha256']=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return payload


def verify(manifest,root):
    copy=dict(manifest);expected=copy.pop('manifest_sha256')
    if hashlib.sha256(json.dumps(copy,sort_keys=True,separators=(',',':')).encode()).hexdigest()!=expected:
        raise ValueError('Holdout manifest changed')
    current=seal([{k:v for k,v in row.items() if k!='sha256'} for row in manifest['entries']],set(manifest['used_groups']),root)
    if current!=manifest:raise ValueError('Holdout inputs changed after seal')
    return True
