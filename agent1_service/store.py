"""SQLite local mã hoá nội dung bản ghi; nhật ký chỉ giữ loại thao tác và số lượng."""

import json
import hashlib
from datetime import date
from pathlib import Path
import sqlite3
import threading
from cryptography.fernet import Fernet

VERSIONED_KINDS = {"customers", "promises", "outflows"}


def observation_day(row, kind):
    """Day the observation was known; future scheduled outflows are allowed."""
    business = (
        row.get("made_date")
        if kind == "promises"
        else row.get("date")
        if kind == "outflows"
        else None
    )
    values = [
        row.get("available_on") or row.get("known_at") or business or "0001-01-01"
    ]
    if row.get("known_at"):
        values.append(row["known_at"])
    return max(date.fromisoformat(str(value)[:10]).isoformat() for value in values)


class Store:
    def __init__(self, path, key):
        self.path = Path(path).resolve()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.RLock()
        self.cipher = Fernet(key)
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS records (firm TEXT, kind TEXT, id TEXT, payload BLOB, PRIMARY KEY(firm,kind,id))"
        )
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS audit (at TEXT DEFAULT CURRENT_TIMESTAMP, firm TEXT, action TEXT, count INTEGER)"
        )
        self.connection.commit()

    def put(self, firm, kind, records):
        self.put_many(firm, {kind: records})

    def put_many(self, firm, batches):
        """Commit related T0 records in one SQLite transaction."""
        with self.lock, self.connection:
            for kind, records in batches.items():
                if kind in VERSIONED_KINDS:
                    self._preserve_versions(firm, kind, records)
                for row in records:
                    identifier = str(row["id"])
                    payload = self.cipher.encrypt(
                        json.dumps(row, ensure_ascii=False, allow_nan=False).encode()
                    )
                    self.connection.execute(
                        "INSERT OR REPLACE INTO records VALUES (?,?,?,?)",
                        (firm, kind, identifier, payload),
                    )
                self.connection.execute(
                    "INSERT INTO audit(firm,action,count) VALUES (?,?,?)",
                    (firm, "put:" + kind, len(records)),
                )

    def _preserve_versions(self, firm, kind, records):
        current = {str(row["id"]): row for row in self.get(firm, kind)}
        history_kind = kind + "_versions"
        history = self.get(firm, history_kind)
        versions = {}
        for entry in history:
            versions[entry["record_id"]] = max(
                versions.get(entry["record_id"], 0), entry["revision"]
            )
        seen = set()
        for row in records:
            identifier = str(row["id"])
            if identifier in seen:
                raise ValueError("Trùng ID trong lô quan sát")
            seen.add(identifier)
            known = observation_day(row, kind)
            old = current.get(identifier)
            if old is not None and old == row:
                continue
            if old is not None and known <= observation_day(old, kind):
                raise ValueError(
                    "Bản sửa cần ngày biết mới hơn bản trước; không ghi đè lịch sử cùng ngày"
                )
            pending = []
            # Preserve a legacy current row on its first update as well.
            if old is not None and identifier not in versions:
                pending.append(old)
            pending.append(row)
            for observation in pending:
                revision = versions.get(identifier, 0) + 1
                entry = dict(
                    id=hashlib.sha256(identifier.encode()).hexdigest()
                    + f":{revision:012d}",
                    record_id=identifier,
                    revision=revision,
                    available_on=observation_day(observation, kind),
                    record=observation,
                )
                payload = self.cipher.encrypt(
                    json.dumps(entry, ensure_ascii=False, allow_nan=False).encode()
                )
                self.connection.execute(
                    "INSERT INTO records VALUES (?,?,?,?)",
                    (firm, history_kind, entry["id"], payload),
                )
                versions[identifier] = revision

    def as_of(self, firm, kind, cutoff):
        """Select a complete observation revision, never filter only the latest row."""
        if kind not in VERSIONED_KINDS:
            raise ValueError("Bảng không có lịch sử quan sát")
        cutoff = date.fromisoformat(str(cutoff)[:10]).isoformat()
        with self.lock:
            history = self.get(firm, kind + "_versions")
            historical_ids = {entry["record_id"] for entry in history}
            selected = {}
            for entry in history:
                identifier = entry["record_id"]
                if entry["available_on"] <= cutoff and (
                    identifier not in selected
                    or entry["revision"] > selected[identifier]["revision"]
                ):
                    selected[identifier] = entry
            rows = {
                identifier: entry["record"] for identifier, entry in selected.items()
            }
            for row in self.get(firm, kind):
                identifier = str(row["id"])
                if (
                    identifier not in historical_ids
                    and observation_day(row, kind) <= cutoff
                ):
                    rows[identifier] = row
            return [rows[identifier] for identifier in sorted(rows)]

    def get(self, firm, kind):
        with self.lock:
            rows = self.connection.execute(
                "SELECT payload FROM records WHERE firm=? AND kind=? ORDER BY id",
                (firm, kind),
            ).fetchall()
        return [json.loads(self.cipher.decrypt(row[0])) for row in rows]

    def one(self, firm, kind, identifier):
        with self.lock:
            row = self.connection.execute(
                "SELECT payload FROM records WHERE firm=? AND kind=? AND id=?",
                (firm, kind, identifier),
            ).fetchone()
        return json.loads(self.cipher.decrypt(row[0])) if row else None

    def ids(self, firm, kind):
        with self.lock:
            return [
                r[0]
                for r in self.connection.execute(
                    "SELECT id FROM records WHERE firm=? AND kind=?", (firm, kind)
                )
            ]

    def remove(self, firm, entries):
        with self.lock, self.connection:
            for kind, identifier in entries:
                self.connection.execute(
                    "DELETE FROM records WHERE firm=? AND kind=? AND id=?",
                    (firm, kind, identifier),
                )
                self.connection.execute(
                    "INSERT INTO audit(firm,action,count) VALUES (?,?,1)",
                    (firm, "delete:" + kind),
                )

    def delete_firm(self, firm):
        with self.lock, self.connection:
            self.connection.execute("DELETE FROM records WHERE firm=?", (firm,))
            self.connection.execute(
                "INSERT INTO audit(firm,action,count) VALUES (?,?,?)",
                (firm, "delete", 0),
            )
        # Sau xoá, VACUUM loại trang chứa bản mã cũ khỏi DB chính.
        with self.lock:
            self.connection.execute("VACUUM")
