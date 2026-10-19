"""Explicit sealed-test access and an exclusive final-run journal."""
import hashlib,json
from pathlib import Path


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def config_digest(config):
    return hashlib.sha256(json.dumps(config,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def require_split_access(split,final=False):
    if split=='test' and not final:raise ValueError('Sealed test: --final and a frozen B* are required before reading rows.')


def freeze(path,config,model_digest,data_hashes,source_hash):
    lock={'report_notice':'formulas not accountant-approved','G0_7':'OPEN / CHƯA ĐẠT',
          'config_sha256':config_digest(config),'config':config,'model_digest':model_digest,'data_hashes':data_hashes,'source_hash':source_hash}
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf8') as f:json.dump(lock,f,ensure_ascii=False,indent=2)
    return lock


def start_final(folder,lock,config,model_digest,data_hashes,source_hash,resume=False):
    for key,actual in [('config_sha256',config_digest(config)),('model_digest',model_digest),('data_hashes',data_hashes),('source_hash',source_hash)]:
        if lock[key]!=actual:raise ValueError('Final frozen contract mismatch: '+key)
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);marker=folder/'STARTED.json'
    if marker.exists():
        if not resume:raise ValueError('Final already started; only resume the same journal without repeating cases.')
        if json.loads(marker.read_text(encoding='utf8'))!=lock:raise ValueError('Final marker mismatch')
    else:
        with marker.open('x',encoding='utf8') as f:json.dump(lock,f,ensure_ascii=False,indent=2)


def started_ids(path):
    return {json.loads(line)['id'] for line in Path(path).read_text(encoding='utf8').splitlines()} if Path(path).exists() else set()


def claim_final(path,folder,resume=False):
    """One final run across output folders, not merely one per folder."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    owner={'output':str(Path(folder).resolve())}
    if path.exists():
        if not resume or json.loads(path.read_text(encoding='utf8'))!=owner:
            raise ValueError('Final already claimed; resume the original output only.')
    else:
        with path.open('x',encoding='utf8') as f:json.dump(owner,f)
