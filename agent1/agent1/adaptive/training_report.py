"""Password-encrypted, self-contained training reports; no raw records or weights."""

import base64, json, os
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


def report_data(bundle, data, identifier):
    def estimator(model):
        if hasattr(model, "members"):
            return {"ensemble": [estimator(m) for m in model.members]}
        obj = getattr(model, "estimator", None)
        return {
            "method": getattr(model, "variant", getattr(model, "name", None)),
            "parameters": obj.get_params(deep=True) if obj is not None else {},
        }

    dates = [r["issue_date"] for r in data.get("invoices", [])]
    return dict(
        version=identifier,
        synthetic=bool(bundle.get("synthetic_sandbox")),
        dataset=dict(
            counts={k: len(v) for k, v in data.items()},
            customers=len({r["customer_id"] for r in data.get("invoices", [])}),
            issue_date_min=min(dates, default=None),
            issue_date_max=max(dates, default=None),
            sha256=bundle.get("dataset_hash"),
        ),
        training={
            k: bundle.get(k)
            for k in [
                "asof",
                "windows",
                "train_n",
                "validation_n",
                "selection",
                "selected_method",
                "selected_weight",
                "audit",
                "collection_evaluation",
                "code_hash",
                "dependencies",
                "algorithm_version",
                "limitation",
            ]
        },
        training_seconds=bundle.get("training_seconds"),
        deployed=estimator(bundle["model"]),
        risk={k: v for k, v in bundle.get("risk", {}).items() if k != "model"},
        operating={
            k: v
            for k, v in (bundle.get("operating") or {}).items()
            if k in ["name", "validation", "unavailable", "audit_mae", "reference_mae"]
        },
        compute_budget=dict(
            neural_max_iter=os.environ.get("AGENT1_NEURAL_MAX_ITER", "100"),
            neural_batch_size=os.environ.get("AGENT1_NEURAL_BATCH_SIZE", "128"),
        ),
        explanation="Selection/tuning use validation only; audit is an acceptance gate. Synthetic results with a bounded demo budget do not establish real-world accuracy or convergence.",
    )


def encrypt_report(report, password):
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=32, salt=salt, iterations=600000
    ).derive(password.encode())
    payload = json.dumps(report, ensure_ascii=False, default=str).encode()
    ciphertext = AESGCM(key).encrypt(nonce, payload, None)
    packed = json.dumps(
        {
            k: base64.b64encode(v).decode()
            for k, v in dict(salt=salt, nonce=nonce, ciphertext=ciphertext).items()
        }
    )
    return """<!doctype html><html lang="vi"><meta charset="utf-8"><title>Báo cáo huấn luyện Agent1</title><style>body{max-width:1000px;margin:40px auto;padding:20px;font:16px/1.6 Segoe UI,sans-serif}input,button{padding:12px;font:inherit}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f1f4f3;padding:20px}</style><h1>Báo cáo huấn luyện Agent1</h1><p>Nội dung được mã hóa. Nhập mật khẩu để xem thông tin dữ liệu, chia tập, tuning và kiểm định.</p><form id="unlock"><input id="password" type="password" autocomplete="off" aria-label="Mật khẩu" required><button>Mở báo cáo</button></form><p id="message"></p><pre id="report" hidden></pre><script>
const encrypted=PACKED;
const bytes=s=>Uint8Array.from(atob(s),c=>c.charCodeAt(0));
document.querySelector('#unlock').onsubmit=async e=>{e.preventDefault();try{
const input=document.querySelector('#password');
const material=await crypto.subtle.importKey('raw',new TextEncoder().encode(input.value),'PBKDF2',false,['deriveKey']);
input.value='';
const key=await crypto.subtle.deriveKey({name:'PBKDF2',salt:bytes(encrypted.salt),iterations:600000,hash:'SHA-256'},material,{name:'AES-GCM',length:256},false,['decrypt']);
const plain=await crypto.subtle.decrypt({name:'AES-GCM',iv:bytes(encrypted.nonce)},key,bytes(encrypted.ciphertext));
const report=document.querySelector('#report');report.textContent=JSON.stringify(JSON.parse(new TextDecoder().decode(plain)),null,2);report.hidden=false;document.querySelector('#message').textContent='Đã mở báo cáo. Đóng trang để kết thúc xem.';
}catch(error){document.querySelector('#report').hidden=true;document.querySelector('#report').textContent='';document.querySelector('#message').textContent='Không mở được: kiểm tra mật khẩu hoặc trình duyệt hỗ trợ Web Crypto.';}};
</script></html>""".replace("PACKED", packed)


def save_training_report(bundle, data, identifier):
    password_file = os.environ.get("AGENT1_REPORT_PASSWORD_FILE")
    directory = os.environ.get("AGENT1_REPORT_DIR")
    if not password_file or not directory:
        return None
    password = Path(password_file).read_text(encoding="utf-8-sig").strip()
    if not password:
        raise ValueError("Chưa cấu hình mật khẩu báo cáo")
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"Agent1_train_{identifier}.html"
    target.write_text(
        encrypt_report(report_data(bundle, data, identifier), password),
        encoding="utf-8",
    )
    return str(target)
