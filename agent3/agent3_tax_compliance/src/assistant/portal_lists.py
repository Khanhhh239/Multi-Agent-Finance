"""One explicitly active, validated portal list; original uploads are retained."""
import hashlib
import json
from pathlib import Path

from .sources import read_portal_list, SourceError


def _folder(ws):
    folder = Path(ws).resolve() / 'portal'
    if folder.resolve() != folder:
        raise SourceError('Thư mục bảng kê không được là liên kết ra ngoài workspace.')
    return folder


def candidates(ws):
    return sorted(p for p in _folder(ws).glob('*') if p.is_file() and not p.is_symlink() and p.suffix.lower() in ('.csv', '.xlsx'))


def content_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def active_path(ws, pack):
    folder = _folder(ws)
    manifest = folder / 'active.json'
    if manifest.exists():
        m = json.loads(manifest.read_text(encoding='utf-8'))
        if not isinstance(m, dict) or not isinstance(m.get('name'), str) or not isinstance(m.get('sha256'), str):
            raise SourceError('Manifest bảng kê không hợp lệ; chọn lại bản nguồn.')
        name = m['name']
        path = folder / name
        if Path(name).name != name or path.suffix.lower() not in ('.csv', '.xlsx') or path.is_symlink() or not path.is_file() or content_hash(path) != m['sha256']:
            raise SourceError('Bản bảng kê đang dùng bị thiếu hoặc thay đổi; chọn lại bản nguồn.')
        return path
    files = candidates(ws)
    if len(files) <= 1:
        return files[0] if files else None
    normalized = [json.dumps(sorted([{k: v for k, v in r.items() if k != 'source'} for r in read_portal_list(p, pack)], key=lambda r: r['key']), sort_keys=True, default=str) for p in files]
    if len(set(normalized)) != 1:
        raise SourceError('Có nhiều bảng kê khác nhau; chọn bản đang hoạt động trong Ngân hàng và dữ liệu Agent 3.')
    return files[0]


def select(ws, path, pack):
    folder = _folder(ws)
    if path.parent.resolve() != folder.resolve() or path.is_symlink() or path.suffix.lower() not in ('.csv', '.xlsx'):
        raise SourceError('Đường dẫn bảng kê không hợp lệ.')
    rows = read_portal_list(path, pack)  # Validate the entire table before publishing the pointer.
    if not rows:
        raise SourceError('Bảng kê không có dòng hợp lệ.')
    manifest = dict(name=path.name, sha256=content_hash(path))
    tmp = folder / 'active.json.tmp'
    tmp.write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
    tmp.replace(folder / 'active.json')
    return rows


def ingest(ws, source, pack):
    rows = read_portal_list(source, pack)
    if not rows:
        raise SourceError('Bảng kê không có dòng hợp lệ.')
    folder = _folder(ws)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / ('purchase_list_' + content_hash(source) + source.suffix.lower())
    if not target.exists():
        tmp = target.with_suffix(target.suffix + '.tmp')
        tmp.write_bytes(source.read_bytes())
        tmp.replace(target)
    select(ws, target, pack)
    return target
