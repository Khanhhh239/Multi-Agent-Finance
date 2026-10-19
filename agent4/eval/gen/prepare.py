import hashlib,json


def save_dataset(folder,name,rows):
    payload=''.join(json.dumps(r,ensure_ascii=False,default=str)+'\n' for r in rows)
    (folder/f'{name}.jsonl').write_text(payload,encoding='utf8')
    return {'n':len(rows),'sha256':hashlib.sha256(payload.encode()).hexdigest()}
