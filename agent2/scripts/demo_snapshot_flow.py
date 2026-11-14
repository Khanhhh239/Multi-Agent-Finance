"""Run the real HTTP snapshot flow on synthetic C001, in a separate local demo DB."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import http.client
import json
from pathlib import Path
import secrets
import sqlite3
import sys
import tempfile
import threading
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sme_fraud.auth import FileAuthorizer
from sme_fraud.import_files import canonical, digest
from sme_fraud.review_server import make_server
from sme_fraud.snapshots import SnapshotStore


def main():
    database = ROOT/".runtime/snapshot_demo/snapshots.sqlite3"
    store = SnapshotStore(database)
    data = json.loads((ROOT/"tests/fixtures/input_contract_v1.json").read_text("utf-8"))
    for table, rows in data.items():
        if isinstance(rows, list):
            data[table] = [r for r in rows if r["company_id"] == "C001"]
    run = uuid.uuid4().hex
    token = secrets.token_urlsafe(32)
    with tempfile.TemporaryDirectory(prefix="agent2_snapshot_demo_") as temporary:
        auth_file = Path(temporary)/"policy.json"
        auth_file.write_bytes(canonical(dict(policy_version="1.0.0", principals=[dict(
            actor_id="snapshot-demo", tenant_id="demo", token_sha256=hashlib.sha256(token.encode()).hexdigest(),
            status="active", expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),
            memberships=[dict(company_id="C001", role="accountant", status="active", permissions=["data.import"])])])))
        server = make_server(0, FileAuthorizer(auth_file), store)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()

        def request(method, path, body=None, raw=None, **headers):
            values = {"Authorization":"Bearer "+token, "Content-Type":"application/json", **headers}
            payload = raw if raw is not None else canonical(body) if body is not None else None
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=30)
            try:
                connection.request(method,"/api/v1/companies/C001/"+path,payload,values)
                response = connection.getresponse(); content = response.read()
                if response.status >= 400:
                    raise RuntimeError(f"HTTP {response.status}: "+content.decode("utf-8"))
                return json.loads(content)
            finally:
                connection.close()

        try:
            print("Demo dữ liệu mô phỏng C001; kho riêng, không dùng DB đang vận hành.")
            draft = request("POST","imports/upload",raw=canonical(data), **{"Idempotency-Key":run+"-upload","X-File-Name":"demo-c001.json"})
            print("1. Đã tải tệp:",draft["import_id"])
            path = "imports/"+draft["import_id"]
            preview = request("POST",path+"/preview",dict(expected_revision=1))
            print("2. Kết quả:",preview["status"],"·",preview["counts"]["transactions"],"giao dịch")
            print("   Cảnh báo nguồn:",len(preview["warnings"]),"— xem analysis_limits trước khi sử dụng.")
            body = {name:preview[name] for name in ("preview_id","source_hash","mapping_hash","report_hash","context_hash")}
            body.update(expected_revision=1,acknowledge=True)
            saved = request("POST",path+"/commit",body,**{"Idempotency-Key":run+"-commit"})
            snapshot = saved["snapshot"]
            print("3. Đã xác nhận và lưu:",snapshot["snapshot_id"])
            print("   Checksum dữ liệu:",snapshot["data_checksum"])
            print("   Checksum manifest:",snapshot["checksum"])
            for _ in range(10):
                retried = request("POST",path+"/commit",body,**{"Idempotency-Key":run+"-commit"})
                assert retried == saved
            print("4. Gửi lại 10 lần: vẫn cùng một snapshot.")
            with closing(sqlite3.connect(database)) as conn:
                row = conn.execute("SELECT data_json FROM snapshots WHERE snapshot_id=?",(snapshot["snapshot_id"],)).fetchone()
                assert digest(row[0]) == snapshot["data_checksum"]
            print("DB demo được giữ tại:",database)
            print("Credential thử đã được dọn; để phục vụ API lâu dài cần auth policy của backend.")
        finally:
            server.shutdown(); server.server_close(); thread.join(5)


if __name__ == "__main__":
    main()
