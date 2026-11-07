"""Offline copy/restore: key escrow stays with the operator, separate from the database."""

import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from cryptography.fernet import Fernet


def transfer(source, target, key_file):
    source, target, key_file = map(
        lambda p: Path(p).resolve(), (source, target, key_file)
    )
    if target.exists() or source == target:
        raise ValueError("Đích phải là file mới")
    if not source.is_file() or source == key_file:
        raise ValueError("Không tìm thấy CSDL nguồn")
    if target.parent == key_file.parent:
        raise ValueError("Không đặt bản sao cùng thư mục khóa")
    cipher = Fernet(key_file.read_bytes())
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=target.parent)
    os.close(fd)
    try:
        with (
            closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as src,
            closing(sqlite3.connect(temp)) as dest,
        ):
            src.backup(dest)
            if dest.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise ValueError("Sai cấu trúc SQLite")
            count = 0
            for identifier, payload in dest.execute("SELECT id,payload FROM records"):
                if str(json.loads(cipher.decrypt(payload))["id"]) != identifier:
                    raise ValueError("Bản ghi không khớp mã")
                count += 1
        os.link(temp, target)  # Atomic no-clobber on NTFS/POSIX.
        with target.open("rb") as f:
            digest = hashlib.file_digest(f, "sha256").hexdigest()
        return dict(records=count, sha256=digest)
    finally:
        Path(temp).unlink(missing_ok=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=["backup", "restore"])
    p.add_argument("source")
    p.add_argument("target")
    p.add_argument("--key-file", required=True)
    args = p.parse_args()
    print(json.dumps(transfer(args.source, args.target, args.key_file)))
