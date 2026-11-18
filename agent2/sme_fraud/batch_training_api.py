"""Portal coordinator and HTTP API for multi-batch encrypted HE training."""
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from numbers import Real
from pathlib import Path
import math
import os
import re
import shutil
import sqlite3
import threading

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from finance_input import AccessScope
from finance_input.json_io import loads
from .auth import AuthError
from .import_files import ImportFailure, canonical, digest, fail
from .label_packets import source_packet
from .rule_snapshot_features import SOURCE_CONTRACT, build_from_rule_snapshot
from .snapshot_features import build_from_snapshot, utc
from .snapshots import APPLICATION_ID as SNAPSHOT_APP_ID
from .validation_api import RequestFailure, respond_failure
from experiments.he_training import (
    EXECUTION_MODE_NATIVE,
    EXECUTION_MODE_VERIFIED,
    PROFILE_VERSION,
    resolve_quantization_profile,
)
from experiments.he_training.batch_enterprise import BatchEnterprise
from experiments.he_training.batch_plan import VERSION as PLAN_VERSION, prepare_batch_plan
from experiments.he_training.protocol import TrainingError, sha, strict_json, verify
from experiments.he_training.runtime import ENV_HE_AGGREGATOR_URL, resolve_he_runtime
from experiments.he_training.snapshot_adapter import (
    COLUMNS as ADAPTER_COLUMNS,
    MAPPING_VERSION,
    ReadOnlySnapshots,
    TEXT as ADAPTER_TEXT,
    _source_modes,
    mapping_contract,
)

APPLICATION_ID = 1093817145
PORTAL_VERSION = "portal-batch-training/0.1.0"
SHADOW_RUN_VERSION = "portal-shadow-snapshot-run/0.1.0"
MAX_SHADOW_BATCH_ROWS = 64
COMPANY_RE = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")
KEY_RE = re.compile(r"[A-Za-z0-9_.:-]{8,128}\Z")
HASH_RE = re.compile(r"[a-f0-9]{64}\Z")
SHADOW_RUN_ID_RE = re.compile(r"shrun_[0-9]+_[a-f0-9]{16}\Z")
ROUTE_RE = re.compile(
    r"/api/v1/companies/([A-Za-z0-9_.:-]{1,128})/batch-training"
    r"(?:/(preview|create-labels|confirm|resume|receive|evaluate|approve|shadow|shadow-runs)"
    r"(?:/([A-Za-z0-9_.:-]{1,128}))?)?\Z"
)

PHASE_LABELS = {
    "plan_rejected": "Kế hoạch bị từ chối — cần xử lý lỗi nguồn/feature",
    "plan_ready": "Đã ghim kế hoạch — chờ xác minh nhãn",
    "labels_pending": "Đang chờ xác minh và khóa nhãn",
    "labels_ready": "Nhãn đã khóa đủ điều kiện — sẵn sàng xác nhận train",
    "preparing": "Đang chuẩn bị",
    "uploading": "Đang gửi",
    "training": "Đang train",
    "interrupted": "Bị gián đoạn",
    "completed_waiting_receive": "Hoàn tất — chờ nhận model",
    "model_received": "Model ứng viên đã nhận và kiểm tra kỹ thuật",
    "holdout_evaluated": "Đã đánh giá trên tập giữ riêng — chờ phê duyệt shadow",
    "shadow_approved": "Đã phê duyệt dùng đối chiếu shadow",
    "failed": "Lỗi",
}

TRAINING_ERRORS = {
    "MODEL_FIT_DENIED": (403, "Tài khoản không có quyền model.fit.", "Đăng nhập tài khoản có quyền huấn luyện/phê duyệt model của đúng doanh nghiệp."),
    "MODEL_READ_DENIED": (403, "Tài khoản không có quyền đọc dữ liệu/model.", "Dùng tài khoản có quyền data.import đúng doanh nghiệp."),
    "BATCH_PLAN_VERSION": (400, "Phiên bản kế hoạch batch không hợp lệ.", "Dùng đúng version snapshot-he-batch-plan/0.1.0."),
    "BATCH_TIME_SPLIT": (400, "Kỳ train và kỳ đánh giá không hợp lệ hoặc chồng lấn thời gian.", "Đảm bảo training_start < training_end <= evaluation_start < evaluation_end <= as_of."),
    "BATCH_COUNT": (400, "Số lượng batch train vượt ngoài phạm vi cho phép (2–4 batch).", "Chọn từ 2 đến 4 batch train, mỗi batch đúng 4 giao dịch."),
    "EVALUATION_BATCH_COUNT": (400, "Số lượng batch đánh giá vượt ngoài phạm vi cho phép (1–4 batch).", "Chọn từ 1 đến 4 batch đánh giá, mỗi batch đúng 4 giao dịch."),
    "BATCH_ROWS_EXACTLY_FOUR": (400, "Mỗi batch phải có đúng 4 giao dịch.", "Kiểm tra lại danh sách giao dịch trong từng batch train và đánh giá."),
    "TRAINING_ROWS_REQUIRED_EXACTLY_FOUR": (400, "Mỗi batch phải có đúng 4 giao dịch.", "Chọn đúng 4 giao dịch cho mỗi batch."),
    "TRAIN_EVALUATION_OVERLAP_OR_DUPLICATE": (400, "Giao dịch bị trùng lặp hoặc vừa nằm ở tập train vừa nằm ở tập đánh giá.", "Tách biệt hoàn toàn giao dịch giữa các batch train và batch đánh giá."),
    "BATCH_DUPLICATE_ROWS": (400, "Có giao dịch trùng lặp trong cùng một batch.", "Mỗi giao dịch chỉ xuất hiện một lần."),
    "DUPLICATE_TRAINING_TRANSACTION": (400, "Có giao dịch trùng lặp trong cùng một batch.", "Mỗi giao dịch chỉ xuất hiện một lần."),
    "SNAPSHOT_ID_INVALID": (400, "Mã snapshot không hợp lệ.", "Chọn đúng snapshot đã chốt của doanh nghiệp."),
    "TRAINING_WINDOW_INVALID": (400, "Khoảng thời gian không hợp lệ.", "Đảm bảo start < end <= as_of."),
    "BATCH_SNAPSHOT_NOT_READY": (409, "Kế hoạch dữ liệu chưa đạt kiểm tra nguồn/feature.", "Xem lỗi nguồn trên từng giao dịch và chọn lại trước khi tiếp tục."),
    "BATCH_PREVIEW_STALE": (409, "Kế hoạch đã thay đổi so với bản đã kiểm tra.", "Kiểm tra và ghim lại kế hoạch trước khi thực hiện bước tiếp theo."),
    "BATCH_LABEL_LOCKS_REQUIRED": (409, "Thiếu thông tin gói nhãn đã khóa cho các batch train.", "Tạo, xác minh và khóa đầy đủ gói nhãn của mọi batch train."),
    "LABEL_PACKET_NOT_LOCKED": (409, "Gói nhãn chưa được khóa hoặc đã bị mở khóa lại.", "Mở màn hình xác minh nhãn, hoàn tất xác minh và khóa gói nhãn trước khi train."),
    "LABEL_PACKET_REVISION_STALE": (409, "Phiên bản gói nhãn đã thay đổi sau khi tạo/khóa.", "Tải lại trạng thái nhãn mới nhất và kiểm tra lại trước khi xác nhận train."),
    "LABEL_LOCK_HASH_MISMATCH": (409, "Mã khóa gói nhãn (lock_sha256) không khớp với kho nhãn trên server.", "Kiểm tra lại phiên bản và mã khóa của gói nhãn."),
    "BATCH_LABEL_SOURCE_MISMATCH": (409, "Gói nhãn không thuộc đúng kế hoạch/batch dữ liệu đã ghim.", "Tạo lại gói nhãn từ đúng kế hoạch hiện tại."),
    "BATCH_LABEL_MODE_FEATURE_MISMATCH": (409, "Chế độ nguồn hoặc trạng thái feature của gói nhãn không hợp lệ.", "Chỉ xác nhận train khi các batch đạt trạng thái ready và đồng nhất chế độ nguồn."),
    "BATCH_LABEL_ROW_ORDER": (409, "Danh sách hoặc thứ tự giao dịch trong gói nhãn không khớp kế hoạch.", "Không sửa đổi danh sách giao dịch ngoài kế hoạch đã ghim."),
    "BATCH_LABELS_INCOMPLETE": (409, "Còn giao dịch chưa có nhãn xác minh (đang để trống/null).", "Xác minh đầy đủ nhãn cho cả 4 giao dịch trong mỗi batch train và khóa lại."),
    "BOTH_LABEL_CLASSES_REQUIRED": (409, "Toàn bộ tập train chỉ có một lớp nhãn.", "Tập train tổng hợp cần có đủ cả hai lớp (verified_fraud và verified_non_fraud)."),
    "BATCH_UPDATE_LIMIT": (400, "Tổng số bước cập nhật (số batch train × số epoch) vượt giới hạn 4 cập nhật của circuit.", "Giảm số batch train hoặc chọn 1 epoch để tổng số cập nhật <= 4."),
    "BATCH_TRAINING_NOT_COMPLETED": (409, "Quá trình train trên worker chưa hoàn tất đủ số bước cập nhật.", "Chờ hoặc tiếp tục chạy hết các bước cập nhật trước khi nhận model."),
    "BATCH_DECRYPTED_PARITY_FAILED": (409, "Kiểm tra đối chiếu kỹ thuật sau giải mã không khớp oracle.", "Từ chối nhận model ứng viên và kiểm tra lại môi trường thực thi."),
    "BATCH_MODEL_NOT_RECEIVED": (409, "Chưa nhận và kiểm tra kỹ thuật model ứng viên tại doanh nghiệp.", "Thực hiện bước Nhận model sau khi worker hoàn tất train."),
    "BATCH_HOLDOUT_EVALUATION_REQUIRED": (409, "Model ứng viên chưa được đánh giá trên tập giữ riêng.", "Thực hiện bước Đánh giá trên tập giữ riêng trước khi phê duyệt shadow."),
    "BATCH_APPROVAL_MODEL_MISMATCH": (409, "Hash bản mã model không khớp với model ứng viên hiện tại.", "Kiểm tra lại thông tin model trước khi phê duyệt."),
    "BATCH_APPROVAL_PLAN_MISMATCH": (409, "Hash kế hoạch dữ liệu không khớp với phiên train hiện tại.", "Kiểm tra lại kế hoạch trước khi phê duyệt."),
    "BATCH_APPROVAL_EVALUATION_MISMATCH": (409, "Hash kết quả đánh giá holdout không khớp với bản đánh giá hiện tại.", "Chạy lại hoặc tải lại kết quả đánh giá trước khi phê duyệt."),
    "BATCH_APPROVAL_CONFLICT": (409, "Model đã được phê duyệt với thông tin khác.", "Không ghi đè bản phê duyệt đã ký."),
    "APPROVAL_REASON_REQUIRED": (400, "Lý do phê duyệt cần từ 10 đến 1000 ký tự.", "Nhập rõ căn cứ phê duyệt dùng đối chiếu shadow (tối thiểu 10 ký tự)."),
    "BATCH_MODEL_NOT_APPROVED": (409, "Model ứng viên chưa được phê duyệt để chạy đối chiếu shadow.", "Hoàn tất bước Phê duyệt dùng shadow trước khi chấm đối chiếu."),
    "SNAPSHOT_FEATURE_MAPPING_REQUIRED": (409, "Mapping fingerprint không khớp với hợp đồng feature của phiên train.", "Dùng đúng mapping fingerprint từ kế hoạch snapshot đã ghim."),
    "EVALUATION_SOURCE_MISMATCH": (409, "Nguồn đánh giá holdout không khớp cam kết ban đầu.", "Đánh giá đúng trên tập giữ riêng đã khóa trong kế hoạch."),
    "AUTH_CONTEXT_CHANGED": (409, "Ngữ cảnh quyền đã thay đổi trong lúc xử lý.", "Tải lại trang và thực hiện lại thao tác."),
    "TIMESTAMP_INVALID": (400, "Thời điểm chốt as_of không hợp lệ.", "Nhập thời điểm as_of theo định dạng ISO-8601 có múi giờ (ví dụ 2026-03-31T00:00:00Z)."),
    "FEATURE_DOMAIN": (400, "Vector feature nằm ngoài miền {0, 1} hoặc vượt quá giới hạn 1..64 dòng mỗi lần gọi.", "Kiểm tra nguồn dữ liệu hoặc chia lô tối đa 64 dòng mỗi lần chấm."),
    "SHADOW_ROW_IDS_INVALID": (400, "Danh sách mã giao dịch row_ids không hợp lệ.", "Đảm bảo mỗi dòng có record_id hợp lệ."),
    "LEGACY_MODEL_PROFILE_MISMATCH": (409, "Model hoặc bản mã thuộc profile lượng tử hóa cũ (legacy_s2_v1) không khớp với fhe_sgd_s16_v2.", "Không giải mã model scale=2 bằng scale=16; chọn đúng build/model cùng profile_version."),
}


def _translate_training_error(exc):
    code = str(exc)
    for key, (status, message, remediation) in TRAINING_ERRORS.items():
        if key in code:
            fail(status, key, message, remediation)
    fail(409, code if re.fullmatch(r"[A-Z0-9_]{3,64}", code) else "BATCH_TRAINING_ERROR",
         f"Không thể thực hiện bước huấn luyện batch ({code}).",
         "Kiểm tra lại kế hoạch, trạng thái gói nhãn và kết nối worker rồi thử lại.")


def _copy_company_crypto(base_dir, session_dir):
    base_dir = Path(base_dir).resolve()
    session_dir = Path(session_dir).resolve()
    if session_dir == base_dir or (session_dir / "enterprise.json").is_file():
        return
    if not (base_dir / "enterprise.json").is_file():
        return
    session_dir.mkdir(parents=True, exist_ok=True)
    for name in ("enterprise.json", "wrapping.dpapi.json", "node-signing.dpapi.json"):
        shutil.copy2(base_dir / name, session_dir / name)
    crypto_dest = session_dir / "crypto"
    crypto_dest.mkdir(exist_ok=True)
    for name in ("context.sealed", "evaluation.keys"):
        src = base_dir / "crypto" / name
        dst = crypto_dest / name
        if src.is_file() and not dst.exists():
            try:
                dst.hardlink_to(src)
            except OSError:
                shutil.copy2(src, dst)


def _sync_base_crypto(base_dir, session_dir):
    base_dir = Path(base_dir).resolve()
    session_dir = Path(session_dir).resolve()
    if session_dir == base_dir or (base_dir / "enterprise.json").is_file() or not (session_dir / "enterprise.json").is_file():
        return
    base_dir.mkdir(parents=True, exist_ok=True)
    for name in ("enterprise.json", "wrapping.dpapi.json", "node-signing.dpapi.json"):
        shutil.copy2(session_dir / name, base_dir / name)
    crypto_dest = base_dir / "crypto"
    crypto_dest.mkdir(exist_ok=True)
    for name in ("context.sealed", "evaluation.keys"):
        src = session_dir / "crypto" / name
        dst = crypto_dest / name
        if src.is_file() and not dst.exists():
            try:
                dst.hardlink_to(src)
            except OSError:
                shutil.copy2(src, dst)


def _summarize_plan(plan):
    batches = []
    issues = []
    for partition in ("training", "evaluation"):
        for idx, item in enumerate(plan["parts"][partition]):
            cplan = item["plan"]
            creq = item["request"]
            b_issues = []
            for row in cplan.get("rows", []):
                for issue in row.get("issues", []):
                    entry = dict(
                        partition=partition,
                        batch_index=idx,
                        record_id=row["record_id"],
                        revision=row["revision"],
                        code=issue["code"],
                        message=issue["message"],
                        remediation=issue["remediation"],
                    )
                    b_issues.append(entry)
                    issues.append(entry)
            batches.append(dict(
                partition=partition,
                batch_index=idx,
                status=cplan["status"],
                row_count=len(creq["rows"]),
                row_ids=[r["record_id"] for r in creq["rows"]],
                rows=cplan.get("rows", []),
                x=cplan.get("x"),
                issues=b_issues,
                child_plan_sha256=cplan["plan_sha256"],
                child_request=creq,
            ))
    req = plan["request"]
    return dict(
        version=plan["version"],
        status=plan["status"],
        plan_sha256=plan["plan_sha256"],
        tenant_id=plan["tenant_id"],
        company_id=plan["company_id"],
        snapshot=plan["snapshot"],
        simulated=plan["simulated"],
        mapping_fingerprint=plan["mapping_fingerprint"],
        training_rows=plan["training_rows"],
        evaluation_rows=plan["evaluation_rows"],
        training_batch_count=len(plan["parts"]["training"]),
        evaluation_batch_count=len(plan["parts"]["evaluation"]),
        evaluation_sent_to_training_worker=plan["evaluation_sent_to_training_worker"],
        labels_included=plan["labels_included"],
        windows=dict(
            training_start=req["training_start"],
            training_end=req["training_end"],
            evaluation_start=req["evaluation_start"],
            evaluation_end=req["evaluation_end"],
            as_of=req["as_of"],
        ),
        batches=batches,
        issues=issues,
    )


class BatchTrainingManager:
    """Encrypted append-only Portal coordinator for multi-batch HE training."""

    def __init__(
        self,
        db_path,
        key,
        *,
        snapshot_store=None,
        label_store=None,
        enterprise_root=None,
        build=None,
        worker_url=None,
        worker_verify_key=None,
        linux_python=None,
        distro=None,
        runtime_config_path=None,
        node_factory=None,
        clock=None,
    ):
        if not isinstance(key, (bytes, bytearray)) or len(key) != 32:
            raise ValueError("BatchTrainingManager requires a 32-byte key")
        self.path = Path(db_path).resolve()
        self.key = bytes(key)
        self.snapshot_store = snapshot_store
        self.label_store = label_store
        self.enterprise_root = Path(enterprise_root).resolve() if enterprise_root else self.path.parent / "batch-enterprise"
        self.build = Path(build).resolve() if build else None
        self.worker_url = worker_url
        self.worker_verify_key = worker_verify_key
        self.linux_python = linux_python
        self.distro = distro
        self.runtime_config_path = Path(runtime_config_path).resolve() if runtime_config_path else None
        self.node_factory = node_factory
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = threading.Lock()
        self._company_locks = {}
        self._active_runners = {}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            app = conn.execute("PRAGMA application_id").fetchone()[0]
            ver = conn.execute("PRAGMA user_version").fetchone()[0]
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
            if (app == 0 and tables) or app not in {0, APPLICATION_ID} or (app == APPLICATION_ID and ver != 1):
                fail(503, "BATCH_TRAINING_STORAGE_VERSION", "Kho điều phối train nhiều batch không đúng phiên bản.", "Dùng đúng kho batch-training.sqlite3 của Agent2.")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(f"""
                BEGIN IMMEDIATE;
                PRAGMA application_id={APPLICATION_ID};
                PRAGMA user_version=1;
                CREATE TABLE IF NOT EXISTS batch_training_journal(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT NOT NULL,
                    company_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    nonce BLOB NOT NULL,
                    ciphertext BLOB NOT NULL,
                    UNIQUE(tenant_id, company_id, revision)
                );
                CREATE TABLE IF NOT EXISTS batch_training_receipts(
                    tenant_id TEXT NOT NULL,
                    company_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    request_sha256 TEXT NOT NULL,
                    nonce BLOB NOT NULL,
                    ciphertext BLOB NOT NULL,
                    PRIMARY KEY(tenant_id, company_id, idempotency_key)
                );
                CREATE TRIGGER IF NOT EXISTS batch_training_journal_update BEFORE UPDATE ON batch_training_journal BEGIN SELECT RAISE(ABORT, 'immutable batch training journal'); END;
                CREATE TRIGGER IF NOT EXISTS batch_training_journal_delete BEFORE DELETE ON batch_training_journal BEGIN SELECT RAISE(ABORT, 'immutable batch training journal'); END;
                CREATE TRIGGER IF NOT EXISTS batch_training_receipts_update BEFORE UPDATE ON batch_training_receipts BEGIN SELECT RAISE(ABORT, 'immutable batch training receipt'); END;
                CREATE TRIGGER IF NOT EXISTS batch_training_receipts_delete BEFORE DELETE ON batch_training_receipts BEGIN SELECT RAISE(ABORT, 'immutable batch training receipt'); END;
                CREATE TABLE IF NOT EXISTS batch_shadow_runs(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    shadow_run_id TEXT NOT NULL UNIQUE,
                    tenant_id TEXT NOT NULL,
                    company_id TEXT NOT NULL,
                    model_run_id TEXT NOT NULL,
                    snapshot_id TEXT NOT NULL,
                    as_of TEXT NOT NULL,
                    request_fingerprint TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    nonce BLOB NOT NULL,
                    ciphertext BLOB NOT NULL,
                    UNIQUE(tenant_id, company_id, idempotency_key),
                    UNIQUE(tenant_id, company_id, request_fingerprint)
                );
                CREATE TRIGGER IF NOT EXISTS batch_shadow_runs_update BEFORE UPDATE ON batch_shadow_runs BEGIN SELECT RAISE(ABORT, 'immutable batch shadow run'); END;
                CREATE TRIGGER IF NOT EXISTS batch_shadow_runs_delete BEFORE DELETE ON batch_shadow_runs BEGIN SELECT RAISE(ABORT, 'immutable batch shadow run'); END;
                COMMIT;
            """)

    @classmethod
    def from_config(cls, config_path, *, snapshot_store=None, label_store=None):
        cfg = strict_json(Path(config_path).read_bytes())
        from experiments.he_inference.key_manager import PROVIDER, load_key
        raw = load_key(cfg["node_state_key_file"], required_provider=PROVIDER).material
        # The embedded Portal derives from the job-store MAC subkey. Earlier
        # explicit configs derived directly from the wrapping key. Authenticate
        # an existing row read-only to preserve either historical format; never
        # reset or migrate ciphertext when changing startup mode.
        job_keys = HKDF(algorithm=hashes.SHA256(), length=64, salt=b"he-node-jobs-v1", info=b"enterprise-storage-and-idempotency").derive(raw)
        derived = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"agent2-batch-training-v1", info=b"enterprise-batch-training").derive(job_keys[32:])
        legacy = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"agent2-batch-training-v1", info=b"enterprise-batch-training").derive(raw)
        storage_path = Path(cfg.get("batch_training_db", Path(config_path).resolve().parent / "batch-training.sqlite3")).resolve()
        if storage_path.is_file():
            with closing(sqlite3.connect(storage_path.as_uri()+"?mode=ro", uri=True)) as probe:
                probe.row_factory = sqlite3.Row
                if probe.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID:
                    fail(503, 'BATCH_TRAINING_STORAGE_VERSION', 'Kho train không đúng phiên bản.', 'Chọn đúng DB; không ghi đè kho hiện có.')
                row = probe.execute('SELECT * FROM batch_training_journal ORDER BY id LIMIT 1').fetchone()
                if row is not None:
                    aad = canonical(dict(app=APPLICATION_ID, kind='journal', tenant_id=row['tenant_id'], company_id=row['company_id'], ref=row['revision']))
                    matches = []
                    for key in (derived, legacy):
                        try:
                            value = loads(AESGCM(key).decrypt(bytes(row['nonce']), bytes(row['ciphertext']), aad))
                            if value.get('tenant_id') == row['tenant_id'] and value.get('company_id') == row['company_id'] and value.get('revision') == row['revision']:
                                matches.append(key)
                        except Exception:
                            continue
                    if len(matches) != 1:
                        fail(503, 'BATCH_TRAINING_STATE_KEY_MISMATCH', 'Khóa không mở được nhật ký train đã lưu.', 'Khôi phục đúng khóa/kho; dữ liệu hiện có được giữ nguyên.')
                    derived = matches[0]
        if snapshot_store is None and cfg.get("snapshot_db"):
            snapshot_store = ReadOnlySnapshots(cfg["snapshot_db"])
        if label_store is None and cfg.get("label_db"):
            from .label_packets import LabelStore
            label_store = LabelStore.from_state_key(cfg["label_db"], cfg["node_state_key_file"])
        return cls(
            storage_path,
            derived,
            snapshot_store=snapshot_store,
            label_store=label_store,
            enterprise_root=cfg.get("enterprise_root"),
            build=cfg.get("build"),
            worker_url=cfg.get("worker_url") or os.environ.get(ENV_HE_AGGREGATOR_URL, "").strip() or None,
            worker_verify_key=cfg.get("worker_verify_key"),
            linux_python=cfg.get("linux_python"),
            distro=cfg.get("distro"),
            runtime_config_path=config_path,
        )

    def set_worker(self, worker_url, worker_verify_key, *, build=None, enterprise_root=None):
        self.worker_url = worker_url
        self.worker_verify_key = worker_verify_key
        if build is not None:
            self.build = Path(build).resolve()
        if enterprise_root is not None:
            self.enterprise_root = Path(enterprise_root).resolve()

    def _runtime_settings(self):
        build = self.build
        root = self.enterprise_root
        url = self.worker_url or os.environ.get(ENV_HE_AGGREGATOR_URL, "").strip() or None
        pub = self.worker_verify_key
        py = self.linux_python
        distro = self.distro
        if self.runtime_config_path and self.runtime_config_path.is_file():
            try:
                cfg = strict_json(self.runtime_config_path.read_bytes())
                build = Path(cfg["build"]).resolve() if cfg.get("build") else build
                root = Path(cfg["enterprise_root"]).resolve() if cfg.get("enterprise_root") else root
                url = cfg.get("worker_url") or url
                pub = cfg.get("worker_verify_key") or pub
                py = cfg.get("linux_python", py)
                distro = cfg.get("distro", distro)
            except Exception:
                pass
        if build is None or not Path(build).is_dir() or not url or not pub:
            fail(503, "BATCH_WORKER_UNAVAILABLE", "Chưa cấu hình hoặc chưa kết nối được worker huấn luyện mã hóa.", "Kiểm tra cấu hình build/worker của luồng huấn luyện mã hóa trước khi thực hiện.")
        return Path(root).resolve(), Path(build).resolve(), url, pub, py, distro

    def _snapshots(self):
        if self.snapshot_store is None:
            fail(503, "SNAPSHOT_STORE_UNAVAILABLE", "Chưa cấu hình kho snapshot.", "Khởi tạo kho snapshot trước khi lập kế hoạch train.")
        if isinstance(self.snapshot_store, ReadOnlySnapshots):
            return self.snapshot_store
        return ReadOnlySnapshots(self.snapshot_store.path)

    def _labels(self):
        if self.label_store is None:
            fail(503, "LABEL_STORE_UNAVAILABLE", "Chưa cấu hình kho xác minh nhãn.", "Khởi tạo kho nhãn xác minh trước khi thực hiện.")
        return self.label_store

    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA synchronous=FULL")
        return conn

    def _now(self):
        return self.clock().astimezone(timezone.utc).isoformat()

    @staticmethod
    def _scope(scope, permission="data.import"):
        if not isinstance(scope, AccessScope) or len(scope.company_ids) != 1 or not scope.actor_id:
            fail(403, "ACCESS_DENIED", "Cần phạm vi đúng một doanh nghiệp.", "Đăng nhập và chọn đúng một doanh nghiệp.")
        if permission not in scope.permissions:
            if permission == "model.fit":
                fail(403, "MODEL_FIT_DENIED", "Tài khoản không có quyền model.fit.", "Dùng tài khoản được cấp quyền model.fit cho doanh nghiệp này.")
            if permission == "evidence.verify":
                fail(403, "LABEL_VERIFY_DENIED", "Tài khoản không có quyền xác minh nhãn.", "Dùng tài khoản được cấp quyền evidence.verify cho doanh nghiệp này.")
            fail(403, "ACCESS_DENIED", "Không đủ quyền truy cập.", "Kiểm tra lại quyền của tài khoản.")
        return scope.tenant_id, next(iter(scope.company_ids)), scope.actor_id

    @contextmanager
    def _tx(self, scope, recheck=None, permission="data.import"):
        self._scope(scope, permission)
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            if recheck is not None and recheck() != scope:
                fail(409, "AUTH_CONTEXT_CHANGED", "Ngữ cảnh quyền đã thay đổi.", "Tải lại trang và thử lại.")
            yield conn
            if recheck is not None and recheck() != scope:
                fail(409, "AUTH_CONTEXT_CHANGED", "Ngữ cảnh quyền đã thay đổi trước khi lưu.", "Tải lại trang và thử lại.")
            conn.execute("COMMIT")
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def _aad(self, kind, tenant, company, ref):
        return canonical(dict(app=APPLICATION_ID, kind=kind, tenant_id=tenant, company_id=company, ref=ref))

    def _seal(self, kind, tenant, company, ref, payload):
        nonce = os.urandom(12)
        return nonce, AESGCM(self.key).encrypt(nonce, canonical(payload), self._aad(kind, tenant, company, ref))

    def _open(self, kind, tenant, company, ref, nonce, ciphertext):
        try:
            return loads(AESGCM(self.key).decrypt(bytes(nonce), bytes(ciphertext), self._aad(kind, tenant, company, ref)))
        except Exception:
            fail(503, "BATCH_TRAINING_STORAGE_CORRUPT", "Bản ghi trạng thái huấn luyện batch không toàn vẹn.", "Kiểm tra khóa trạng thái hoặc nhật ký lưu trữ của doanh nghiệp.")

    def _latest(self, conn, tenant, company):
        row = conn.execute(
            "SELECT * FROM batch_training_journal WHERE tenant_id=? AND company_id=? ORDER BY revision DESC LIMIT 1",
            (tenant, company),
        ).fetchone()
        if row is None:
            return None
        state = self._open("journal", tenant, company, row["revision"], row["nonce"], row["ciphertext"])
        if state.get("tenant_id") != tenant or state.get("company_id") != company or state.get("revision") != row["revision"]:
            fail(503, "BATCH_TRAINING_STORAGE_CORRUPT", "Bản ghi phiên huấn luyện không khớp ngữ cảnh.", "Kiểm tra lại kho lưu trữ batch-training.")
        return state

    def _append(self, conn, tenant, company, state):
        revision = int(state["revision"])
        nonce, ct = self._seal("journal", tenant, company, revision, state)
        conn.execute(
            "INSERT INTO batch_training_journal(tenant_id,company_id,revision,nonce,ciphertext) VALUES (?,?,?,?,?)",
            (tenant, company, revision, nonce, ct),
        )
        return state

    def _receipt(self, conn, tenant, company, idem_key, req_hash, value=None):
        if not isinstance(idem_key, str) or KEY_RE.fullmatch(idem_key) is None:
            fail(400, "IDEMPOTENCY_KEY_REQUIRED", "Cần Idempotency-Key hợp lệ (8–128 ký tự).", "Gửi kèm header Idempotency-Key cho thao tác ghi.")
        row = conn.execute(
            "SELECT * FROM batch_training_receipts WHERE tenant_id=? AND company_id=? AND idempotency_key=?",
            (tenant, company, idem_key),
        ).fetchone()
        if row is not None:
            if row["request_sha256"] != req_hash:
                fail(409, "IDEMPOTENCY_CONFLICT", "Idempotency-Key đã được dùng cho nội dung yêu cầu khác.", "Tạo Idempotency-Key mới cho yêu cầu mới.")
            return self._open("receipt", tenant, company, idem_key, row["nonce"], row["ciphertext"])
        if value is not None:
            nonce, ct = self._seal("receipt", tenant, company, idem_key, value)
            conn.execute(
                "INSERT INTO batch_training_receipts VALUES (?,?,?,?,?,?)",
                (tenant, company, idem_key, req_hash, nonce, ct),
            )
        return value

    @staticmethod
    def _expect_revision(current_state, expected_revision):
        actual = 0 if current_state is None else int(current_state["revision"])
        if type(expected_revision) is not int or expected_revision < 0:
            fail(400, "EXPECTED_REVISION_REQUIRED", "Cần gửi expected_revision là số nguyên không âm.", "Tải lại trạng thái hiện tại và gửi đúng expected_revision.")
        if expected_revision != actual:
            fail(409, "REVISION_CONFLICT", "Trạng thái phiên huấn luyện đã thay đổi trên server.", "Tải lại trạng thái mới nhất rồi thực hiện lại thao tác.")

    def _company_lock(self, tenant, company):
        with self._lock:
            key = (tenant, company)
            if key not in self._company_locks:
                self._company_locks[key] = threading.Lock()
            return self._company_locks[key]

    def _is_running(self, tenant, company, run_id):
        with self._lock:
            t = self._active_runners.get((tenant, company, run_id))
            return bool(t and t.is_alive())

    def _start_background_run(self, scope, tenant, company, actor, run_id, fallback_job):
        run_scope = AccessScope(scope.tenant_id, scope.company_ids, scope.actor_id, frozenset(scope.permissions) | {"data.import", "model.fit"})

        def _worker():
            import time as _time
            _time.sleep(0.15)
            try:
                node, url, pub = self._node_for_session(run_scope, company, run_id, None)
                done_job, _ = node.access_batches(url, pub, "run")
                next_phase = (
                    "completed_waiting_receive"
                    if done_job.get("status") == "completed" and done_job.get("completed_updates") == done_job.get("total_updates")
                    else "interrupted"
                )
                err_info = None
            except Exception as exc:
                done_job = fallback_job
                try:
                    node, url, pub = self._node_for_session(run_scope, company, run_id, None)
                    done_job, _ = node.access_batches(url, pub, "status")
                except Exception:
                    pass
                next_phase = "interrupted"
                err_info = str(exc)
            try:
                with self._tx(run_scope, None, "model.fit") as conn:
                    latest = self._latest(conn, tenant, company)
                    if latest is not None and latest.get("run_id") == run_id and not latest.get("candidate"):
                        final_state = dict(
                            latest,
                            revision=latest["revision"] + 1,
                            phase=next_phase,
                            worker_job=done_job,
                            last_error=err_info,
                            updated_at=self._now(),
                            updated_by=actor,
                        )
                        self._append(conn, tenant, company, final_state)
            except Exception:
                pass

        with self._lock:
            key = (tenant, company, run_id)
            cur = self._active_runners.get(key)
            if cur is None or not cur.is_alive():
                t = threading.Thread(target=_worker, daemon=True)
                self._active_runners[key] = t
                t.start()
            return self._active_runners[key]

    def _node_for_session(self, scope, company, run_id, recheck=None):
        if self.node_factory is not None:
            session_dir = self.enterprise_root / "_sessions" / f"{scope.tenant_id}_{company}" / run_id
            return self.node_factory(session_dir, scope, company, recheck)
        root, build, url, pub, py, distro = self._runtime_settings()
        base_dir = root / company
        session_dir = root / "_sessions" / f"{scope.tenant_id}_{company}" / run_id
        _copy_company_crypto(base_dir, session_dir)
        node = BatchEnterprise(session_dir, build, scope, recheck=recheck, python=py, distro=distro)
        _sync_base_crypto(base_dir, session_dir)
        return node, url, pub

    def _list_company_snapshots(self, scope, recheck=None):
        if self.snapshot_store is None or not Path(self.snapshot_store.path).is_file():
            return []
        snapshots = self._snapshots()
        tenant, company, _ = self._scope(scope, "data.import")
        items = []
        with snapshots._transaction(scope, recheck) as conn:
            rows = conn.execute(
                "SELECT snapshot_id FROM snapshots WHERE tenant_id=? AND company_id=? ORDER BY rowid DESC",
                (tenant, company),
            ).fetchall()
            for row in rows:
                manifest, raw = snapshots._read_snapshot(conn, scope, row["snapshot_id"])
                payload = loads(raw)
                if "source" in payload and "tables" in payload.get("source", {}):
                    src = payload["source"]
                    source_as_of = src.get("as_of") or manifest.get("created_at")
                    snap_simulated = src.get("is_simulated")
                    txs = [
                        dict(
                            record_id=tx.get("transaction_id") or tx.get("record_id"),
                            revision=tx.get("revision", 1),
                            occurred_at=tx.get("posted_at") or tx.get("occurred_at") or tx.get("effective_at"),
                            available_at=tx.get("observed_at") or src.get("as_of"),
                            amount=tx.get("amount_vnd") if "amount_vnd" in tx else tx.get("amount"),
                            simulated=src.get("is_simulated"),
                        )
                        for tx in src["tables"].get("transactions", [])
                    ]
                else:
                    txs = [
                        dict(
                            record_id=tx["record_id"],
                            revision=tx["revision"],
                            occurred_at=tx.get("effective_at") or tx.get("occurred_at"),
                            available_at=tx.get("observed_at") or (tx.get("source") or {}).get("available_at"),
                            amount=tx.get("amount_vnd") if "amount_vnd" in tx else tx.get("amount"),
                            simulated=(tx.get("source") or {}).get("is_simulated"),
                        )
                        for tx in payload.get("transactions", [])
                        if tx.get("company_id") == company
                    ]
                    avail_times = [str(tx.get("available_at")) for tx in txs if tx.get("available_at")]
                    source_as_of = max(avail_times) if avail_times else manifest.get("created_at")
                    sim_modes = {tx.get("simulated") for tx in txs if type(tx.get("simulated")) is bool}
                    snap_simulated = next(iter(sim_modes)) if len(sim_modes) == 1 else None
                txs.sort(key=lambda r: (str(r.get("occurred_at") or ""), str(r.get("record_id") or "")))
                items.append(dict(
                    snapshot_id=manifest["snapshot_id"],
                    contract_version=manifest.get("contract_version"),
                    created_at=manifest.get("created_at"),
                    source_as_of=source_as_of,
                    simulated=snap_simulated,
                    data_checksum=manifest.get("data_checksum"),
                    checksum=manifest.get("checksum"),
                    transaction_count=len(txs),
                    transactions=txs,
                ))
        return items

    def _compute_label_status(self, scope, state, recheck=None):
        packets = state.get("packets") or []
        plan_summary = state.get("plan_summary") or {}
        expected_train_batches = int(plan_summary.get("training_batch_count") or 0)
        expected_eval_batches = int(plan_summary.get("evaluation_batch_count") or 0)
        if not packets or self.label_store is None:
            return dict(
                created=False,
                training_packets=[],
                evaluation_packets=[],
                training_all_locked=False,
                training_all_complete=False,
                training_classes=[],
                training_both_classes=False,
                evaluation_all_locked=False,
                evaluation_all_complete=False,
                stale_after_lock=False,
                ready_to_confirm=False,
                recommended_locks=[],
                recommended_evaluation_locks=[],
                blocking_reasons=["Chưa tạo gói xác minh nhãn cho các batch trong kế hoạch."],
            )
        labels = self._labels()
        train_items = []
        eval_items = []
        train_classes = set()
        stale_after_lock = False
        pinned_by_id = {p["packet_id"]: p for p in (state.get("locks") or [])}
        for binding in packets:
            pkt = labels.get(scope, binding["packet_id"], recheck)
            rows = pkt.get("labels") or pkt.get("rows") or []
            outcomes = [r.get("outcome") for r in rows]
            fraud_count = sum(v == "verified_fraud" for v in outcomes)
            non_fraud_count = sum(v == "verified_non_fraud" for v in outcomes)
            labelled_count = fraud_count + non_fraud_count
            missing_count = len(rows) - labelled_count
            complete = len(rows) == 4 and missing_count == 0
            source_matches = pkt.get("binding", {}).get("source_plan_sha256") == binding.get("source_plan_sha256")
            pin = pinned_by_id.get(pkt["packet_id"])
            pin_stale = bool(pin and (not pkt["locked"] or pkt["revision"] != pin["revision"] or pkt["lock_sha256"] != pin["lock_sha256"]))
            if pin_stale:
                stale_after_lock = True
            info = dict(
                partition=binding["partition"],
                batch_index=binding["batch_index"],
                packet_id=pkt["packet_id"],
                revision=pkt["revision"],
                locked=bool(pkt["locked"]),
                lock_sha256=pkt.get("lock_sha256"),
                locked_at=pkt.get("locked_at"),
                locked_by=pkt.get("locked_by"),
                row_count=len(rows),
                row_ids=[r["record_id"] for r in rows],
                rows=rows,
                labelled_count=labelled_count,
                fraud_count=fraud_count,
                non_fraud_count=non_fraud_count,
                missing_count=missing_count,
                complete=complete,
                source_matches=source_matches,
                pin_stale=pin_stale,
            )
            if binding["partition"] == "training":
                train_items.append(info)
                if fraud_count > 0:
                    train_classes.add(1)
                if non_fraud_count > 0:
                    train_classes.add(0)
            else:
                eval_items.append(info)
        train_items.sort(key=lambda x: x["batch_index"])
        eval_items.sort(key=lambda x: x["batch_index"])
        training_all_locked = len(train_items) == expected_train_batches and all(p["locked"] and p["source_matches"] for p in train_items)
        training_all_complete = len(train_items) == expected_train_batches and all(p["complete"] for p in train_items)
        training_both_classes = train_classes == {0, 1}
        evaluation_all_locked = len(eval_items) == expected_eval_batches and all(p["locked"] and p["source_matches"] for p in eval_items)
        evaluation_all_complete = len(eval_items) == expected_eval_batches and all(p["complete"] for p in eval_items)
        blocking = []
        if plan_summary.get("status") != "ready":
            blocking.append("Kế hoạch dữ liệu chưa ở trạng thái ready.")
        if len(train_items) != expected_train_batches:
            blocking.append("Chưa tạo đủ gói xác minh nhãn cho các batch train.")
        if not training_all_complete:
            blocking.append("Còn giao dịch trong batch train chưa được gán nhãn xác minh (đang để null).")
        if not training_all_locked:
            blocking.append("Cần khóa tất cả gói nhãn của các batch train trước khi xác nhận train.")
        if not training_both_classes:
            blocking.append("Tổng hợp các batch train cần có đủ cả 2 lớp nhãn (verified_fraud và verified_non_fraud).")
        if stale_after_lock:
            blocking.append("Gói nhãn đã bị mở khóa hoặc chỉnh sửa sau khi ghim; cần khóa lại và xác nhận lại.")
        ready_to_confirm = len(blocking) == 0
        rec_locks = [
            dict(packet_id=p["packet_id"], revision=p["revision"], lock_sha256=p["lock_sha256"])
            for p in train_items if p["locked"] and p.get("lock_sha256")
        ]
        rec_eval_locks = [
            dict(packet_id=p["packet_id"], revision=p["revision"], lock_sha256=p["lock_sha256"])
            for p in eval_items if p["locked"] and p.get("lock_sha256")
        ]
        return dict(
            created=True,
            training_packets=train_items,
            evaluation_packets=eval_items,
            training_all_locked=training_all_locked,
            training_all_complete=training_all_complete,
            training_classes=sorted(train_classes),
            training_both_classes=training_both_classes,
            evaluation_all_locked=evaluation_all_locked,
            evaluation_all_complete=evaluation_all_complete,
            stale_after_lock=stale_after_lock,
            ready_to_confirm=ready_to_confirm,
            recommended_locks=rec_locks,
            recommended_evaluation_locks=rec_eval_locks,
            blocking_reasons=blocking,
        )

    def _enrich_session(self, scope, state, recheck=None, *, poll_worker=True):
        if state is None:
            return None
        view = dict(state)
        phase = view.get("phase", "plan_ready")
        plan_stale = False
        if view.get("request") and self.snapshot_store is not None and phase in ("plan_ready", "plan_rejected", "labels_pending", "labels_ready"):
            try:
                fresh = prepare_batch_plan(self._snapshots(), scope, view["request"], recheck)
                plan_stale = fresh["plan_sha256"] != view.get("plan_sha256") or fresh["status"] != view.get("plan_summary", {}).get("status")
            except Exception:
                plan_stale = True
        view["plan_stale"] = plan_stale
        label_status = self._compute_label_status(scope, view, recheck)
        if plan_stale:
            label_status["ready_to_confirm"] = False
            label_status["blocking_reasons"].insert(0, "Kế hoạch dữ liệu không còn khớp với snapshot hiện tại; cần kiểm tra lại kế hoạch.")
        view["label_status"] = label_status
        if phase in ("plan_ready", "labels_pending", "labels_ready") and view.get("packets"):
            phase = "labels_ready" if label_status["ready_to_confirm"] else "labels_pending"
        if view.get("job_id") and phase in ("training", "interrupted", "completed_waiting_receive"):
            is_running = self._is_running(view["tenant_id"], view["company_id"], view["run_id"])
            if poll_worker:
                try:
                    _, company, _ = self._scope(scope, "data.import")
                    node, url, pub = self._node_for_session(scope, company, view["run_id"], recheck)
                    live_job, _ = node.access_batches(url, pub, "status")
                    view["worker_job"] = live_job
                    view["worker_reachable"] = True
                    if live_job.get("status") == "completed" and live_job.get("completed_updates") == live_job.get("total_updates"):
                        if not view.get("candidate"):
                            phase = "completed_waiting_receive"
                    elif is_running:
                        phase = "training"
                    else:
                        phase = "interrupted"
                except Exception as exc:
                    view["worker_reachable"] = False
                    view["worker_status_error"] = str(exc)
                    if phase == "training":
                        phase = "interrupted"
            else:
                view["worker_reachable"] = True
        view["phase"] = phase
        view["status_label"] = PHASE_LABELS.get(phase, phase)
        return view

    def _list_company_runs(self, conn, tenant, company):
        rows = conn.execute(
            "SELECT revision, nonce, ciphertext FROM batch_training_journal WHERE tenant_id=? AND company_id=? ORDER BY revision ASC",
            (tenant, company),
        ).fetchall()
        runs_by_id = {}
        ordered_ids = []
        for row in rows:
            st = self._open("journal", tenant, company, row["revision"], row["nonce"], row["ciphertext"])
            rid = st.get("run_id")
            if not rid:
                continue
            if rid not in runs_by_id:
                ordered_ids.append(rid)
            runs_by_id[rid] = st
        ordered_ids.reverse()
        return runs_by_id, ordered_ids

    def _extract_model_info(self, scope, company, state, recheck=None):
        run_id = state.get("run_id")
        if not run_id:
            raise TrainingError("BATCH_MODEL_NOT_APPROVED")
        node, _, _ = self._node_for_session(scope, company, run_id, recheck)
        for fname in ("batch-source.json", "batch-candidate.json", "batch-approval.json"):
            if not (node.root / fname).is_file():
                raise TrainingError("BATCH_MODEL_NOT_APPROVED")
        source = node.saved("batch-source.json")
        candidate = node.saved("batch-candidate.json")["candidate"]
        raw_approval = strict_json((node.root / "batch-approval.json").read_bytes())
        approval = verify(raw_approval, node.public_key)
        candidate_sha256 = sha(canonical(candidate))
        approval_sha256 = sha(canonical(raw_approval))
        if (
            approval.get("status") != "approved_for_shadow_evaluation"
            or approval.get("candidate_sha256") != candidate_sha256
            or approval.get("model_cipher_sha256") != candidate.get("model_cipher_sha256")
            or approval.get("tenant_id") != scope.tenant_id
            or approval.get("company_id") != company
        ):
            raise TrainingError("BATCH_MODEL_NOT_APPROVED")
        provenance = source["content"].get("provenance") or {}
        first_train_plan = (((provenance.get("parts") or {}).get("training") or [{}])[0].get("plan")) or {}
        source_fc = first_train_plan.get("source_feature_contract") or {}
        model_mapping = first_train_plan.get("mapping") or (mapping_contract(source_fc) if source_fc else {})
        mapping_fp = provenance.get("mapping_fingerprint") or model_mapping.get("fingerprint")
        train_row_ids = [rid for b in source["content"].get("training", []) for rid in b.get("row_ids", [])]
        eval_row_ids = [rid for b in source["content"].get("evaluation", []) for rid in b.get("row_ids", [])]
        train_snap = provenance.get("snapshot") or (state.get("plan_summary") or {}).get("snapshot") or {}
        windows = (state.get("plan_summary") or {}).get("windows") or {}
        if not windows and isinstance(provenance.get("request"), dict):
            preq = provenance["request"]
            windows = dict(
                training_start=preq.get("training_start"),
                training_end=preq.get("training_end"),
                evaluation_start=preq.get("evaluation_start"),
                evaluation_end=preq.get("evaluation_end"),
                as_of=preq.get("as_of"),
            )
        info = dict(
            model_run_id=run_id,
            tenant_id=scope.tenant_id,
            company_id=company,
            dataset_id=source["dataset_id"],
            job_id=candidate["job_id"],
            consent_sha256=candidate["consent_sha256"],
            model_cipher_sha256=candidate["model_cipher_sha256"],
            candidate_sha256=candidate_sha256,
            approval_sha256=approval_sha256,
            approved_by=approval.get("actor_id"),
            approved_at=approval.get("at"),
            approval_reason=approval.get("reason"),
            approved_for_shadow=True,
            shadow_only=True,
            operational_activation=False,
            active_model_replaced=False,
            operational_queue_changed=False,
            training_plan_sha256=approval.get("plan_sha256") or provenance.get("plan_sha256"),
            evaluation_sha256=approval.get("evaluation_sha256"),
            training_commitment=candidate.get("training_commitment"),
            evaluation_commitment=candidate.get("evaluation_commitment"),
            training_snapshot_id=train_snap.get("snapshot_id"),
            training_snapshot_contract_version=train_snap.get("contract_version"),
            training_snapshot_checksum=train_snap.get("checksum"),
            training_snapshot_data_checksum=train_snap.get("data_checksum"),
            training_windows=windows,
            simulated=source["content"].get("simulated"),
            mapping_fingerprint=mapping_fp,
            mapping=dict(
                version=model_mapping.get("version", MAPPING_VERSION),
                columns=list(model_mapping.get("columns") or list(ADAPTER_COLUMNS)),
                domains=model_mapping.get("domains", [[0, 1], [0, 1]]),
                output_dtype=model_mapping.get("output_dtype", "int64"),
                missing_policy=model_mapping.get("missing_policy", "reject_entire_training_batch; no imputation"),
                source_contract_version=model_mapping.get("source_contract_version") or source_fc.get("version"),
                source_contract_fingerprint=model_mapping.get("source_contract_fingerprint") or source_fc.get("fingerprint"),
                fingerprint=mapping_fp,
            ),
            feature_contract=dict(
                version=source_fc.get("version") or model_mapping.get("source_contract_version"),
                fingerprint=source_fc.get("fingerprint") or model_mapping.get("source_contract_fingerprint"),
                feature_count=source_fc.get("feature_count"),
            ),
            profile_version=candidate.get("profile_version", PROFILE_VERSION),
            training_execution_mode=candidate.get("execution_mode", EXECUTION_MODE_VERIFIED),
            native_fhe_executed=bool(candidate.get("execution_mode") == EXECUTION_MODE_NATIVE),
            weight_scale=candidate.get("weight_scale", 16),
            bias_scale=candidate.get("bias_scale", 16),
            probability_scale=candidate.get("probability_scale", 16),
            weights_code=candidate.get("weights_code"),
            coefficients=candidate.get("coefficients"),
            intercept=candidate.get("intercept"),
            training_rows=candidate.get("training_rows"),
            evaluation_rows=candidate.get("evaluation_rows"),
            completed_updates=candidate.get("completed_updates"),
            training_row_ids=train_row_ids,
            evaluation_row_ids=eval_row_ids,
        )
        return info, node

    def _list_approved_models(self, conn, scope, tenant, company, recheck=None):
        runs_by_id, ordered_ids = self._list_company_runs(conn, tenant, company)
        models = []
        for rid in ordered_ids:
            st = runs_by_id[rid]
            if st.get("phase") != "shadow_approved" or not st.get("approval"):
                continue
            try:
                info, _ = self._extract_model_info(scope, company, st, recheck)
                models.append(info)
            except Exception:
                continue
        return models

    def _list_saved_shadow_runs(self, conn, tenant, company):
        rows = conn.execute(
            "SELECT shadow_run_id, nonce, ciphertext FROM batch_shadow_runs WHERE tenant_id=? AND company_id=? ORDER BY id DESC",
            (tenant, company),
        ).fetchall()
        items = []
        for row in rows:
            run_doc = self._open("shadow_run", tenant, company, row["shadow_run_id"], row["nonce"], row["ciphertext"])
            items.append(run_doc)
        return items

    def _response(self, scope, state, recheck=None, *, include_snapshots=True, poll_worker=True, conn=None):
        tenant, company, actor = self._scope(scope, "data.import")
        session = self._enrich_session(scope, state, recheck, poll_worker=poll_worker)
        if conn is not None:
            approved_models = self._list_approved_models(conn, scope, tenant, company, recheck)
            shadow_runs = self._list_saved_shadow_runs(conn, tenant, company)
        else:
            with closing(self._connect()) as c:
                approved_models = self._list_approved_models(c, scope, tenant, company, recheck)
                shadow_runs = self._list_saved_shadow_runs(c, tenant, company)
        rt_info = resolve_he_runtime(
            python=self.linux_python,
            distro=self.distro,
            aggregator_url=self.worker_url,
        )
        prof_meta = resolve_quantization_profile(PROFILE_VERSION)
        res = dict(
            version=PORTAL_VERSION,
            profile_version=PROFILE_VERSION,
            execution_mode=rt_info["execution_mode"],
            fhe_runtime=dict(
                profile_version=PROFILE_VERSION,
                weight_scale=prof_meta["weight_scale"],
                bias_scale=prof_meta["bias_scale"],
                probability_scale=prof_meta["probability_scale"],
                execution_mode=rt_info["execution_mode"],
                native_fhe_available=rt_info["native_fhe_available"],
                aggregator_url=rt_info["aggregator_url"],
            ),
            tenant_id=tenant,
            company_id=company,
            actor_id=actor,
            permissions=dict(
                can_import="data.import" in scope.permissions,
                can_verify="evidence.verify" in scope.permissions,
                can_fit="model.fit" in scope.permissions,
            ),
            revision=0 if session is None else session["revision"],
            session=session,
            approved_models=approved_models,
            shadow_runs=shadow_runs,
        )
        if include_snapshots:
            res["snapshots"] = self._list_company_snapshots(scope, recheck)
        return res

    def status(self, scope, recheck=None):
        tenant, company, _ = self._scope(scope, "data.import")
        with self._tx(scope, recheck, "data.import") as conn:
            state = self._latest(conn, tenant, company)
        return self._response(scope, state, recheck, include_snapshots=True)

    def preview(self, scope, payload, idem_key, recheck=None):
        if not isinstance(payload, dict) or "request" not in payload or "expected_revision" not in payload:
            fail(400, "BATCH_PREVIEW_FIELDS", "Cần gửi expected_revision và request kế hoạch batch.", "Gửi đầy đủ expected_revision và request theo mẫu snapshot-he-batch-plan/0.1.0.")
        req = dict(payload["request"]) if isinstance(payload["request"], dict) else None
        if req is None:
            fail(400, "BATCH_REQUEST_INVALID", "Nội dung request kế hoạch không hợp lệ.", "Gửi đối tượng JSON chứa thông tin snapshot, kỳ train/đánh giá và danh sách batch.")
        req.setdefault("version", PLAN_VERSION)
        req_hash = digest(canonical(dict(action="preview", expected_revision=payload["expected_revision"], request=req)))
        tenant, company, actor = self._scope(scope, "data.import")
        with self._tx(scope, recheck, "data.import") as conn:
            prior = self._receipt(conn, tenant, company, idem_key, req_hash)
            if prior is not None:
                return self._response(scope, prior, recheck, include_snapshots=False)
            current = self._latest(conn, tenant, company)
            self._expect_revision(current, payload["expected_revision"])
            try:
                plan = prepare_batch_plan(self._snapshots(), scope, req, recheck)
            except TrainingError as exc:
                _translate_training_error(exc)
            summary = _summarize_plan(plan)
            if current is not None and current.get("plan_sha256") == plan["plan_sha256"]:
                next_state = dict(
                    current,
                    revision=current["revision"] + 1,
                    request=req,
                    plan_summary=summary,
                    updated_at=self._now(),
                    updated_by=actor,
                )
            else:
                if current is not None and current.get("phase") in ("preparing", "uploading", "training"):
                    fail(409, "BATCH_JOB_IN_PROGRESS", "Đang có phiên train mã hóa đang chạy cho doanh nghiệp này.", "Chờ hoặc hoàn tất phiên hiện tại trước khi đổi sang kế hoạch khác.")
                next_rev = 1 if current is None else current["revision"] + 1
                next_state = dict(
                    version=PORTAL_VERSION,
                    tenant_id=tenant,
                    company_id=company,
                    revision=next_rev,
                    run_id=f"btrun_{next_rev}_{plan['plan_sha256'][:20]}",
                    phase="plan_ready" if plan["status"] == "ready" else "plan_rejected",
                    request=req,
                    plan_sha256=plan["plan_sha256"],
                    plan_summary=summary,
                    packets=[],
                    locks=None,
                    evaluation_locks=None,
                    epochs=None,
                    dataset_id=None,
                    job_id=None,
                    consent_sha256=None,
                    worker_job=None,
                    candidate=None,
                    evaluation=None,
                    evaluation_sha256=None,
                    approval=None,
                    shadow=None,
                    last_error=None,
                    created_at=self._now(),
                    updated_at=self._now(),
                    updated_by=actor,
                )
            self._append(conn, tenant, company, next_state)
            self._receipt(conn, tenant, company, idem_key, req_hash, next_state)
        return self._response(scope, next_state, recheck, include_snapshots=False)

    def create_labels(self, scope, payload, idem_key, recheck=None):
        if not isinstance(payload, dict) or "expected_revision" not in payload or "expected_plan_sha256" not in payload:
            fail(400, "BATCH_CREATE_LABELS_FIELDS", "Cần gửi expected_revision và expected_plan_sha256.", "Kiểm tra lại kế hoạch trước khi tạo gói xác minh nhãn.")
        expected_plan_sha256 = payload["expected_plan_sha256"]
        include_eval = bool(payload.get("include_evaluation", True))
        req_hash = digest(canonical(dict(action="create_labels", expected_revision=payload["expected_revision"], expected_plan_sha256=expected_plan_sha256, include_evaluation=include_eval)))
        tenant, company, actor = self._scope(scope, "evidence.verify")
        self._scope(scope, "data.import")
        with self._tx(scope, recheck, "evidence.verify") as conn:
            prior = self._receipt(conn, tenant, company, idem_key, req_hash)
            if prior is not None:
                return self._response(scope, prior, recheck, include_snapshots=False)
            current = self._latest(conn, tenant, company)
            self._expect_revision(current, payload["expected_revision"])
            if current is None or not current.get("request"):
                fail(409, "BATCH_PLAN_REQUIRED", "Chưa có kế hoạch dữ liệu được ghim.", "Thực hiện Bước 1 để kiểm tra và ghim kế hoạch trước.")
            try:
                plan = prepare_batch_plan(self._snapshots(), scope, current["request"], recheck)
            except TrainingError as exc:
                _translate_training_error(exc)
            if plan["status"] != "ready":
                fail(409, "BATCH_SNAPSHOT_NOT_READY", "Kế hoạch dữ liệu chưa đạt kiểm tra nguồn/feature.", "Xử lý hết lỗi nguồn ở Bước 1 trước khi tạo gói nhãn.")
            if plan["plan_sha256"] != expected_plan_sha256 or current.get("plan_sha256") != expected_plan_sha256:
                fail(409, "BATCH_PREVIEW_STALE", "Kế hoạch đã thay đổi so với bản đã xem.", "Kiểm tra và ghim lại kế hoạch trước khi tạo gói nhãn.")
            labels = self._labels()
            snapshots = self._snapshots()
            packets = []
            partitions = ("training", "evaluation") if include_eval else ("training",)
            for part_name in partitions:
                for idx, child in enumerate(plan["parts"][part_name]):
                    pkt = labels.create(scope, source_packet(snapshots, scope, child["request"], recheck), recheck)
                    packets.append(dict(
                        partition=part_name,
                        batch_index=idx,
                        packet_id=pkt["packet_id"],
                        source_plan_sha256=child["plan"]["plan_sha256"],
                        row_ids=[r["record_id"] for r in child["request"]["rows"]],
                    ))
            next_state = dict(
                current,
                revision=current["revision"] + 1,
                phase="labels_pending",
                packets=packets,
                updated_at=self._now(),
                updated_by=actor,
            )
            self._append(conn, tenant, company, next_state)
            self._receipt(conn, tenant, company, idem_key, req_hash, next_state)
        return self._response(scope, next_state, recheck, include_snapshots=False)

    def _validate_training_locks(self, scope, plan, locks, epochs, recheck=None):
        count = len(plan["parts"]["training"])
        if type(epochs) is not int or epochs < 1 or count * epochs > 4:
            _translate_training_error(TrainingError("BATCH_UPDATE_LIMIT"))
        if not isinstance(locks, list) or len(locks) != count:
            _translate_training_error(TrainingError("BATCH_LABEL_LOCKS_REQUIRED"))
        labels = self._labels()
        all_classes = set()
        for pin, child in zip(locks, plan["parts"]["training"]):
            if not isinstance(pin, dict) or not {"packet_id", "revision", "lock_sha256"}.issubset(pin.keys()):
                _translate_training_error(TrainingError("BATCH_LABEL_LOCKS_REQUIRED"))
            exported = labels.export(scope, pin["packet_id"], pin["revision"], pin["lock_sha256"], recheck)
            current_pkt = labels.get(scope, pin["packet_id"], recheck)
            if current_pkt["locked"] is not True:
                _translate_training_error(TrainingError("LABEL_PACKET_NOT_LOCKED"))
            if current_pkt["revision"] != pin["revision"] or current_pkt["lock_sha256"] != pin["lock_sha256"]:
                _translate_training_error(TrainingError("LABEL_PACKET_REVISION_STALE"))
            if exported["binding"]["source_plan_sha256"] != child["plan"]["plan_sha256"]:
                _translate_training_error(TrainingError("BATCH_LABEL_SOURCE_MISMATCH"))
            if exported["binding"]["simulated"] != plan["simulated"] or exported["binding"]["feature_status"] != "ready":
                _translate_training_error(TrainingError("BATCH_LABEL_MODE_FEATURE_MISMATCH"))
            if [r["record_id"] for r in exported["labels"]] != child["plan"]["row_ids"] or [r["revision"] for r in exported["labels"]] != [r["revision"] for r in child["request"]["rows"]]:
                _translate_training_error(TrainingError("BATCH_LABEL_ROW_ORDER"))
            if not all(r["outcome"] in ("verified_fraud", "verified_non_fraud") for r in exported["labels"]):
                _translate_training_error(TrainingError("BATCH_LABELS_INCOMPLETE"))
            all_classes.update(int(r["outcome"] == "verified_fraud") for r in exported["labels"])
        if all_classes != {0, 1}:
            _translate_training_error(TrainingError("BOTH_LABEL_CLASSES_REQUIRED"))

    def confirm(self, scope, payload, idem_key, recheck=None):
        if not isinstance(payload, dict) or "expected_revision" not in payload or "expected_plan_sha256" not in payload:
            fail(400, "BATCH_CONFIRM_FIELDS", "Cần gửi expected_revision và expected_plan_sha256.", "Kiểm tra lại thông tin trước khi xác nhận train.")
        expected_plan_sha256 = payload["expected_plan_sha256"]
        epochs = payload.get("epochs", 1)
        locks = payload.get("locks")
        run_mode = payload.get("run_mode", "complete")
        if run_mode not in ("complete", "confirm_only", "async"):
            fail(400, "BATCH_RUN_MODE_INVALID", "Chế độ chạy không hợp lệ.", "Chỉ hỗ trợ complete, confirm_only hoặc async.")
        req_hash = digest(canonical(dict(
            action="confirm",
            expected_revision=payload["expected_revision"],
            expected_plan_sha256=expected_plan_sha256,
            epochs=epochs,
            locks=locks,
            run_mode=run_mode,
        )))
        tenant, company, actor = self._scope(scope, "model.fit")
        self._scope(scope, "data.import")
        with self._company_lock(tenant, company):
            with self._tx(scope, recheck, "model.fit") as conn:
                prior = self._receipt(conn, tenant, company, idem_key, req_hash)
                if prior is not None:
                    latest = self._latest(conn, tenant, company)
                    base_state = latest if latest is not None and latest.get("run_id") == prior.get("run_id") else prior
                    return self._response(scope, base_state, recheck, include_snapshots=False)
                current = self._latest(conn, tenant, company)
                if current is None or not current.get("request"):
                    fail(409, "BATCH_PLAN_REQUIRED", "Chưa có kế hoạch dữ liệu được ghim.", "Thực hiện Bước 1 trước khi xác nhận train.")
                if current.get("plan_sha256") != expected_plan_sha256:
                    fail(409, "BATCH_PREVIEW_STALE", "Mã kế hoạch (plan_sha256) không khớp với phiên hiện tại.", "Kiểm tra lại kế hoạch ở Bước 1.")
                # If a prior confirm for this exact plan/epochs already created job_id (e.g., lost browser response),
                # return the existing job idempotently without creating a duplicate job.
                if current.get("job_id") and current.get("epochs") == epochs and (locks is None or current.get("locks") == locks):
                    if type(payload["expected_revision"]) is int and payload["expected_revision"] <= current["revision"]:
                        self._receipt(conn, tenant, company, idem_key, req_hash, current)
                        if run_mode == "async" and current.get("phase") in ("training", "interrupted"):
                            self._start_background_run(scope, tenant, company, actor, current["run_id"], current.get("worker_job"))
                        return self._response(scope, current, recheck, include_snapshots=False)
                self._expect_revision(current, payload["expected_revision"])
                try:
                    plan = prepare_batch_plan(self._snapshots(), scope, current["request"], recheck)
                except TrainingError as exc:
                    _translate_training_error(exc)
                if plan["status"] != "ready":
                    fail(409, "BATCH_SNAPSHOT_NOT_READY", "Kế hoạch dữ liệu chưa đạt điều kiện ready.", "Xử lý lỗi nguồn ở Bước 1.")
                if plan["plan_sha256"] != expected_plan_sha256:
                    fail(409, "BATCH_PREVIEW_STALE", "Kế hoạch dữ liệu đã thay đổi so với bản đã ghim.", "Kiểm tra và ghim lại kế hoạch.")
                if locks is None:
                    label_status = self._compute_label_status(scope, current, recheck)
                    t_pkts = label_status["training_packets"]
                    if len(t_pkts) != len(plan["parts"]["training"]):
                        _translate_training_error(TrainingError("BATCH_LABEL_LOCKS_REQUIRED"))
                    if any(not p["complete"] for p in t_pkts):
                        _translate_training_error(TrainingError("BATCH_LABELS_INCOMPLETE"))
                    if any(not p["locked"] for p in t_pkts):
                        _translate_training_error(TrainingError("LABEL_PACKET_NOT_LOCKED"))
                    locks = label_status["recommended_locks"]
                self._validate_training_locks(scope, plan, locks, epochs, recheck)
                node, url, pub = self._node_for_session(scope, company, current["run_id"], recheck)
                try:
                    source = node.prepare_snapshot_batches(self._snapshots(), current["request"], expected_plan_sha256=expected_plan_sha256)
                    node.upload_batches(url, pub)
                    job = node.confirm_locked_batches(url, pub, self._labels(), locks, epochs=epochs)
                except TrainingError as exc:
                    _translate_training_error(exc)
                confirmed_state = dict(
                    current,
                    revision=current["revision"] + 1,
                    phase="training",
                    locks=locks,
                    epochs=epochs,
                    dataset_id=source["dataset_id"],
                    job_id=job["job_id"],
                    consent_sha256=job["consent_sha256"],
                    worker_job=job,
                    last_error=None,
                    updated_at=self._now(),
                    updated_by=actor,
                )
                self._append(conn, tenant, company, confirmed_state)
                if run_mode in ("confirm_only", "async"):
                    self._receipt(conn, tenant, company, idem_key, req_hash, confirmed_state)
            if run_mode in ("confirm_only", "async"):
                resp = self._response(scope, confirmed_state, recheck, include_snapshots=False, poll_worker=False)
                if run_mode == "async":
                    self._start_background_run(scope, tenant, company, actor, confirmed_state["run_id"], job)
                return resp
            t = self._start_background_run(scope, tenant, company, actor, confirmed_state["run_id"], confirmed_state["worker_job"])
            t.join()
            with self._tx(scope, recheck, "model.fit") as conn:
                final_state = self._latest(conn, tenant, company)
                self._receipt(conn, tenant, company, idem_key, req_hash, final_state)
            return self._response(scope, final_state, recheck, include_snapshots=False)

    def resume(self, scope, payload, idem_key, recheck=None):
        if not isinstance(payload, dict) or "expected_revision" not in payload:
            fail(400, "BATCH_RESUME_FIELDS", "Cần gửi expected_revision.", "Tải lại trạng thái hiện tại trước khi tiếp tục.")
        run_mode = payload.get("run_mode", "complete")
        if run_mode not in ("complete", "async"):
            fail(400, "BATCH_RUN_MODE_INVALID", "Chế độ chạy không hợp lệ.", "Chỉ hỗ trợ complete hoặc async.")
        req_hash = digest(canonical(dict(action="resume", expected_revision=payload["expected_revision"], run_mode=run_mode)))
        tenant, company, actor = self._scope(scope, "model.fit")
        self._scope(scope, "data.import")
        with self._company_lock(tenant, company):
            with self._tx(scope, recheck, "model.fit") as conn:
                prior = self._receipt(conn, tenant, company, idem_key, req_hash)
                if prior is not None:
                    latest = self._latest(conn, tenant, company)
                    base_state = latest if latest is not None and latest.get("run_id") == prior.get("run_id") else prior
                    return self._response(scope, base_state, recheck, include_snapshots=False)
                current = self._latest(conn, tenant, company)
                if current is None or not current.get("job_id"):
                    fail(409, "BATCH_JOB_NOT_STARTED", "Chưa có yêu cầu train nào được xác nhận để tiếp tục.", "Thực hiện Bước 3 Xác nhận train trước.")
                if type(payload["expected_revision"]) is not int or payload["expected_revision"] < 1 or payload["expected_revision"] > current["revision"]:
                    self._expect_revision(current, payload["expected_revision"])
                if run_mode == "async":
                    resuming_state = dict(
                        current,
                        revision=current["revision"] + 1,
                        phase="training",
                        last_error=None,
                        updated_at=self._now(),
                        updated_by=actor,
                    )
                    self._append(conn, tenant, company, resuming_state)
                    self._receipt(conn, tenant, company, idem_key, req_hash, resuming_state)
            if run_mode == "async":
                resp = self._response(scope, resuming_state, recheck, include_snapshots=False, poll_worker=False)
                self._start_background_run(scope, tenant, company, actor, current["run_id"], current.get("worker_job"))
                return resp
            with self._tx(scope, recheck, "model.fit") as conn:
                node, url, pub = self._node_for_session(scope, company, current["run_id"], recheck)
                try:
                    done_job, _ = node.access_batches(url, pub, "run")
                except TrainingError as exc:
                    _translate_training_error(exc)
                next_phase = current["phase"]
                if done_job.get("status") == "completed" and done_job.get("completed_updates") == done_job.get("total_updates"):
                    if not current.get("candidate"):
                        next_phase = "completed_waiting_receive"
                else:
                    next_phase = "interrupted"
                next_state = dict(
                    current,
                    revision=current["revision"] + 1,
                    phase=next_phase,
                    worker_job=done_job,
                    last_error=None,
                    updated_at=self._now(),
                    updated_by=actor,
                )
                self._append(conn, tenant, company, next_state)
                self._receipt(conn, tenant, company, idem_key, req_hash, next_state)
            return self._response(scope, next_state, recheck, include_snapshots=False)

    def receive(self, scope, payload, idem_key, recheck=None):
        if not isinstance(payload, dict) or "expected_revision" not in payload:
            fail(400, "BATCH_RECEIVE_FIELDS", "Cần gửi expected_revision.", "Tải lại trạng thái hiện tại trước khi nhận model.")
        req_hash = digest(canonical(dict(action="receive", expected_revision=payload["expected_revision"])))
        tenant, company, actor = self._scope(scope, "data.import")
        with self._tx(scope, recheck, "data.import") as conn:
            prior = self._receipt(conn, tenant, company, idem_key, req_hash)
            if prior is not None:
                return self._response(scope, prior, recheck, include_snapshots=False)
            current = self._latest(conn, tenant, company)
            if current is None or not current.get("job_id"):
                fail(409, "BATCH_JOB_NOT_STARTED", "Chưa có công việc train mã hóa nào được khởi tạo.", "Thực hiện Bước 3 và Bước 4 trước khi nhận model.")
            if type(payload["expected_revision"]) is not int or payload["expected_revision"] < 1 or payload["expected_revision"] > current["revision"]:
                self._expect_revision(current, payload["expected_revision"])
            node, url, pub = self._node_for_session(scope, company, current["run_id"], recheck)
            try:
                candidate = node.receive_batches(url, pub)
                live_job, _ = node.access_batches(url, pub, "status")
            except TrainingError as exc:
                _translate_training_error(exc)
            candidate_view = dict(
                candidate,
                candidate_sha256=sha(canonical(candidate)),
                status_label="Model ứng viên đã nhận và kiểm tra kỹ thuật",
                approved_for_shadow=False,
                operational_activation=False,
            )
            next_state = dict(
                current,
                revision=current["revision"] + 1,
                phase="model_received",
                worker_job=live_job,
                candidate=candidate_view,
                updated_at=self._now(),
                updated_by=actor,
            )
            self._append(conn, tenant, company, next_state)
            self._receipt(conn, tenant, company, idem_key, req_hash, next_state)
        return self._response(scope, next_state, recheck, include_snapshots=False)

    def evaluate(self, scope, payload, idem_key, recheck=None):
        if not isinstance(payload, dict) or "expected_revision" not in payload:
            fail(400, "BATCH_EVALUATE_FIELDS", "Cần gửi expected_revision.", "Tải lại trạng thái hiện tại trước khi đánh giá holdout.")
        eval_locks = payload.get("evaluation_locks")
        use_locked_eval = bool(payload.get("use_locked_evaluation_labels", False))
        req_hash = digest(canonical(dict(
            action="evaluate",
            expected_revision=payload["expected_revision"],
            evaluation_locks=eval_locks,
            use_locked_evaluation_labels=use_locked_eval,
        )))
        tenant, company, actor = self._scope(scope, "data.import")
        with self._tx(scope, recheck, "data.import") as conn:
            prior = self._receipt(conn, tenant, company, idem_key, req_hash)
            if prior is not None:
                return self._response(scope, prior, recheck, include_snapshots=False)
            current = self._latest(conn, tenant, company)
            self._expect_revision(current, payload["expected_revision"])
            if current is None or not current.get("candidate"):
                fail(409, "BATCH_MODEL_NOT_RECEIVED", "Chưa nhận model ứng viên tại doanh nghiệp.", "Thực hiện Bước 5 Nhận model trước khi đánh giá trên tập giữ riêng.")
            if eval_locks is None and use_locked_eval:
                lstatus = self._compute_label_status(scope, current, recheck)
                if lstatus["evaluation_all_locked"]:
                    eval_locks = lstatus["recommended_evaluation_locks"]
            node, _, _ = self._node_for_session(scope, company, current["run_id"], recheck)
            try:
                evaluation = node.evaluate_holdout(
                    label_store=self._labels() if eval_locks is not None else None,
                    evaluation_locks=eval_locks,
                )
            except TrainingError as exc:
                _translate_training_error(exc)
            eval_sha256 = sha(canonical(evaluation))
            next_state = dict(
                current,
                revision=current["revision"] + 1,
                phase="holdout_evaluated",
                evaluation_locks=eval_locks,
                evaluation=evaluation,
                evaluation_sha256=eval_sha256,
                updated_at=self._now(),
                updated_by=actor,
            )
            self._append(conn, tenant, company, next_state)
            self._receipt(conn, tenant, company, idem_key, req_hash, next_state)
        return self._response(scope, next_state, recheck, include_snapshots=False)

    def approve(self, scope, payload, idem_key, recheck=None):
        if not isinstance(payload, dict) or "expected_revision" not in payload or "reason" not in payload:
            fail(400, "BATCH_APPROVE_FIELDS", "Cần gửi expected_revision và reason.", "Nhập lý do phê duyệt và gửi kèm các hash đã đối chiếu.")
        reason = payload["reason"]
        exp_model = payload.get("expected_model_cipher_sha256")
        exp_plan = payload.get("expected_plan_sha256")
        exp_eval = payload.get("expected_evaluation_sha256")
        req_hash = digest(canonical(dict(
            action="approve",
            expected_revision=payload["expected_revision"],
            reason=reason,
            expected_model_cipher_sha256=exp_model,
            expected_plan_sha256=exp_plan,
            expected_evaluation_sha256=exp_eval,
        )))
        tenant, company, actor = self._scope(scope, "model.fit")
        self._scope(scope, "data.import")
        with self._tx(scope, recheck, "model.fit") as conn:
            prior = self._receipt(conn, tenant, company, idem_key, req_hash)
            if prior is not None:
                return self._response(scope, prior, recheck, include_snapshots=False)
            current = self._latest(conn, tenant, company)
            self._expect_revision(current, payload["expected_revision"])
            if current is None or not current.get("candidate"):
                fail(409, "BATCH_MODEL_NOT_RECEIVED", "Chưa nhận model ứng viên.", "Thực hiện Bước 5 Nhận model trước.")
            if not current.get("evaluation"):
                fail(409, "BATCH_HOLDOUT_EVALUATION_REQUIRED", "Chưa đánh giá model trên tập giữ riêng.", "Thực hiện Bước 6 Đánh giá trên tập giữ riêng trước khi phê duyệt shadow.")
            node, _, _ = self._node_for_session(scope, company, current["run_id"], recheck)
            try:
                signed_approval = node.approve_batches(
                    reason,
                    expected_model_cipher_sha256=exp_model or current["candidate"]["model_cipher_sha256"],
                    expected_plan_sha256=exp_plan or current["plan_sha256"],
                    expected_evaluation_sha256=exp_eval or current["evaluation_sha256"],
                )
                approval_body = dict(
                    verify(signed_approval, node.public_key),
                    approval_sha256=sha(canonical(signed_approval)),
                    approved_for_shadow=True,
                )
            except TrainingError as exc:
                _translate_training_error(exc)
            candidate_view = dict(current["candidate"], approved_for_shadow=True)
            next_state = dict(
                current,
                revision=current["revision"] + 1,
                phase="shadow_approved",
                candidate=candidate_view,
                approval=approval_body,
                updated_at=self._now(),
                updated_by=actor,
            )
            self._append(conn, tenant, company, next_state)
            self._receipt(conn, tenant, company, idem_key, req_hash, next_state)
        return self._response(scope, next_state, recheck, include_snapshots=False)

    def shadow(self, scope, payload, idem_key, recheck=None):
        if not isinstance(payload, dict) or "expected_revision" not in payload:
            fail(400, "BATCH_SHADOW_FIELDS", "Cần gửi expected_revision.", "Tải lại trạng thái hiện tại trước khi chạy đối chiếu shadow.")
        custom_x = payload.get("x")
        custom_rows = payload.get("row_ids")
        custom_fp = payload.get("mapping_fingerprint")
        req_hash = digest(canonical(dict(
            action="shadow",
            expected_revision=payload["expected_revision"],
            x=custom_x,
            row_ids=custom_rows,
            mapping_fingerprint=custom_fp,
        )))
        tenant, company, actor = self._scope(scope, "data.import")
        with self._tx(scope, recheck, "data.import") as conn:
            prior = self._receipt(conn, tenant, company, idem_key, req_hash)
            if prior is not None:
                return self._response(scope, prior, recheck, include_snapshots=False, conn=conn)
            current = self._latest(conn, tenant, company)
            self._expect_revision(current, payload["expected_revision"])
            if current is None or not current.get("candidate"):
                fail(409, "BATCH_MODEL_NOT_RECEIVED", "Chưa nhận model ứng viên.", "Thực hiện Bước 5 Nhận model trước.")
            if not current.get("approval"):
                fail(409, "BATCH_MODEL_NOT_APPROVED", "Model ứng viên chưa được phê duyệt để chạy đối chiếu shadow.", "Hoàn tất Bước 7 Phê duyệt dùng shadow trước khi chấm đối chiếu.")
            node, _, _ = self._node_for_session(scope, company, current["run_id"], recheck)
            try:
                if custom_x is not None:
                    shadow_res = node.predict_batch_shadow(
                        custom_x,
                        row_ids=custom_rows,
                        mapping_fingerprint=custom_fp or current.get("plan_summary", {}).get("mapping_fingerprint"),
                    )
                    shadow_res["input_mode"] = "technical_manual_features_test_only"
                else:
                    shadow_res = node.evaluate_shadow_holdout()
                    shadow_res["input_mode"] = "training_holdout_replay"
            except TrainingError as exc:
                _translate_training_error(exc)
            next_state = dict(
                current,
                revision=current["revision"] + 1,
                shadow=shadow_res,
                updated_at=self._now(),
                updated_by=actor,
            )
            self._append(conn, tenant, company, next_state)
            self._receipt(conn, tenant, company, idem_key, req_hash, next_state)
        return self._response(scope, next_state, recheck, include_snapshots=False)

    def _load_model_for_shadow(self, conn, scope, tenant, company, payload, recheck=None):
        if not isinstance(payload, dict):
            fail(400, "SHADOW_RUN_FIELDS", "Nội dung yêu cầu chấm shadow không hợp lệ.", "Gửi đối tượng JSON chứa model_run_id, snapshot_id và as_of.")
        if "x" in payload or "features" in payload:
            fail(
                400,
                "SHADOW_MANUAL_FEATURES_FORBIDDEN",
                "Luồng chấm shadow nghiệp vụ trên snapshot không nhận feature nhập tay (x/features).",
                "Chọn snapshot đã lưu để backend tự trích xuất feature tại thời điểm chốt as_of.",
            )
        model_run_id = payload.get("model_run_id")
        if not isinstance(model_run_id, str) or not model_run_id.strip():
            fail(
                400,
                "SHADOW_MODEL_SELECTION_REQUIRED",
                "Chưa chọn phiên bản model đã phê duyệt để chấm đối chiếu shadow.",
                "Chọn rõ một phiên bản model đã phê duyệt shadow của doanh nghiệp trước khi thực hiện.",
            )
        model_run_id = model_run_id.strip()
        runs_by_id, _ = self._list_company_runs(conn, tenant, company)
        st = runs_by_id.get(model_run_id)
        if st is None:
            fail(
                404,
                "SHADOW_MODEL_NOT_FOUND",
                "Không tìm thấy phiên bản model thuộc doanh nghiệp hiện tại.",
                "Chọn đúng model đã được huấn luyện và phê duyệt của doanh nghiệp này.",
            )
        if not st.get("candidate"):
            fail(
                409,
                "BATCH_MODEL_NOT_RECEIVED",
                "Model ứng viên chưa được nhận tại doanh nghiệp.",
                "Hoàn tất Bước 5 Nhận model, Bước 6 Đánh giá holdout và Bước 7 Phê duyệt dùng shadow.",
            )
        if st.get("phase") != "shadow_approved" or not st.get("approval"):
            fail(
                409,
                "BATCH_MODEL_NOT_APPROVED",
                "Model ứng viên chưa được phê duyệt để chạy đối chiếu shadow.",
                "Hoàn tất Bước 7 Phê duyệt dùng shadow trước khi chấm đối chiếu trên snapshot mới.",
            )
        try:
            info, node = self._extract_model_info(scope, company, st, recheck)
        except TrainingError as exc:
            _translate_training_error(exc)
        exp_cipher = payload.get("expected_model_cipher_sha256")
        if exp_cipher is not None and exp_cipher != info["model_cipher_sha256"]:
            fail(
                409,
                "SHADOW_MODEL_PIN_MISMATCH",
                "Mã băm bản mã model (model_cipher_sha256) không khớp với phiên bản model đã chọn.",
                "Tải lại danh sách model đã duyệt và chọn lại đúng phiên bản model.",
            )
        exp_approval = payload.get("expected_approval_sha256")
        if exp_approval is not None and exp_approval != info["approval_sha256"]:
            fail(
                409,
                "SHADOW_MODEL_PIN_MISMATCH",
                "Mã băm phê duyệt shadow (approval_sha256) không khớp với phiên bản model đã chọn.",
                "Tải lại danh sách model đã duyệt và chọn lại đúng phiên bản model.",
            )
        return info, node

    def _evaluate_snapshot_for_model(self, scope, model_info, node, snapshot_id, as_of_raw, recheck=None, *, execute_scoring=True):
        if not isinstance(snapshot_id, str) or not snapshot_id.startswith("snp_") or len(snapshot_id) != 36:
            fail(400, "SNAPSHOT_ID_INVALID", "Mã snapshot không hợp lệ.", "Chọn đúng snapshot đã chốt của doanh nghiệp.")
        snapshots = self._snapshots()
        manifest = snapshots.get_snapshot(scope, snapshot_id, recheck)
        raw = loads(snapshots.get_snapshot(scope, snapshot_id, recheck, data=True))
        company = model_info["company_id"]
        if manifest["contract_version"] == SOURCE_CONTRACT:
            source_as_of = (raw.get("source") or {}).get("as_of") or manifest.get("created_at")
        else:
            avail_list = [
                str(tx.get("observed_at") or (tx.get("source") or {}).get("available_at"))
                for tx in raw.get("transactions", [])
                if tx.get("company_id") == company and (tx.get("observed_at") or (tx.get("source") or {}).get("available_at"))
            ]
            source_as_of = max(avail_list) if avail_list else manifest.get("created_at")
        effective_as_of = as_of_raw if (isinstance(as_of_raw, str) and as_of_raw.strip()) else source_as_of
        if not isinstance(effective_as_of, str) or not effective_as_of.strip():
            fail(400, "TIMESTAMP_INVALID", "Thiếu thời điểm chốt as_of.", "Nhập thời điểm chốt as_of hợp lệ theo định dạng ISO-8601 có múi giờ.")
        try:
            as_of_dt = utc(effective_as_of.strip())
        except Exception:
            fail(400, "TIMESTAMP_INVALID", "Thời điểm chốt as_of không hợp lệ.", "Nhập thời điểm as_of theo chuẩn ISO-8601 có múi giờ (ví dụ 2026-03-31T00:00:00Z).")
        as_of_iso = as_of_dt.isoformat()

        if manifest["contract_version"] == SOURCE_CONTRACT:
            frame = build_from_rule_snapshot(
                snapshots,
                scope,
                snapshot_id,
                as_of_iso,
                recheck,
                candidates_only=False,
                require_exact_source_cutoff=False,
            )
        else:
            frame = build_from_snapshot(snapshots, scope, snapshot_id, as_of_iso, recheck)

        target_mapping = mapping_contract(frame["contract"])
        frame_by_key = {(r["record_id"], r["revision"]): r for r in frame["rows"]}
        frame_by_rid = {r["record_id"]: r for r in frame["rows"]}

        all_txs = []
        if manifest["contract_version"] == SOURCE_CONTRACT:
            src = raw["source"]
            for tx in src["tables"].get("transactions", []):
                rid = tx.get("transaction_id") or tx.get("record_id")
                rev = int(tx.get("revision", 1)) if type(tx.get("revision")) is int and tx.get("revision") >= 1 else 1
                all_txs.append(dict(
                    record_id=rid,
                    revision=rev,
                    occurred_at=tx.get("posted_at") or tx.get("occurred_at") or tx.get("effective_at"),
                    available_at=tx.get("observed_at") or src.get("as_of"),
                    amount_vnd=tx.get("amount_vnd") if "amount_vnd" in tx else tx.get("amount"),
                    currency=tx.get("currency", "VND"),
                    transaction_type=tx.get("txn_type") or tx.get("transaction_type") or tx.get("type"),
                    description=tx.get("description"),
                    created_by=tx.get("creator_id") or tx.get("created_by"),
                    simulated=src.get("is_simulated"),
                ))
        else:
            grouped = {}
            for tx in raw.get("transactions", []):
                if tx.get("company_id") == company:
                    grouped.setdefault(tx["record_id"], []).append(tx)
            for rid, revs in grouped.items():
                if rid in frame_by_rid:
                    wanted_rev = frame_by_rid[rid]["revision"]
                    chosen = next((t for t in revs if t.get("revision") == wanted_rev), revs[-1])
                else:
                    revs_sorted = sorted(revs, key=lambda t: (str(t.get("effective_at") or t.get("occurred_at") or ""), int(t.get("revision", 1))))
                    chosen = revs_sorted[0]
                all_txs.append(dict(
                    record_id=rid,
                    revision=int(chosen.get("revision", 1)),
                    occurred_at=chosen.get("effective_at") or chosen.get("occurred_at"),
                    available_at=chosen.get("observed_at") or (chosen.get("source") or {}).get("available_at"),
                    amount_vnd=chosen.get("amount_vnd") if "amount_vnd" in chosen else chosen.get("amount"),
                    currency=chosen.get("currency", "VND"),
                    transaction_type=chosen.get("kind") or chosen.get("type"),
                    description=chosen.get("description"),
                    created_by=(chosen.get("created_by_ref") or {}).get("record_id") or chosen.get("created_by"),
                    simulated=(chosen.get("source") or {}).get("is_simulated"),
                ))

        all_txs.sort(key=lambda r: (str(r.get("occurred_at") or ""), str(r.get("record_id") or ""), int(r.get("revision") or 1)))

        modes = set()
        for frow in frame["rows"]:
            modes.update(_source_modes(raw, frame, frow))
        if not modes:
            modes.update(tx["simulated"] for tx in all_txs if type(tx.get("simulated")) is bool)
        target_simulated = next(iter(modes)) if len(modes) == 1 else None

        model_map = model_info["mapping"]
        mismatches = []
        if model_map.get("source_contract_version") != target_mapping.get("source_contract_version"):
            mismatches.append(dict(
                field="source_contract_version",
                expected=model_map.get("source_contract_version"),
                actual=target_mapping.get("source_contract_version"),
                message=(
                    f"Phiên bản hợp đồng 33 feature của snapshot ({target_mapping.get('source_contract_version')}) "
                    f"không khớp với hợp đồng khi huấn luyện model ({model_map.get('source_contract_version')})."
                ),
            ))
        if model_map.get("source_contract_fingerprint") != target_mapping.get("source_contract_fingerprint"):
            mismatches.append(dict(
                field="source_contract_fingerprint",
                expected=model_map.get("source_contract_fingerprint"),
                actual=target_mapping.get("source_contract_fingerprint"),
                message="Fingerprint hợp đồng 33 feature của snapshot không khớp với hợp đồng đã ghim của model.",
            ))
        if model_map.get("version") != target_mapping.get("version"):
            mismatches.append(dict(
                field="mapping_version",
                expected=model_map.get("version"),
                actual=target_mapping.get("version"),
                message=f"Phiên bản bộ ánh xạ feature ({target_mapping.get('version')}) không khớp với model ({model_map.get('version')}).",
            ))
        if list(model_map.get("columns") or []) != list(target_mapping.get("columns") or []):
            mismatches.append(dict(
                field="columns",
                expected=list(model_map.get("columns") or []),
                actual=list(target_mapping.get("columns") or []),
                message="Danh sách hoặc thứ tự cột feature không khớp với hợp đồng của model.",
            ))
        if model_map.get("domains") != target_mapping.get("domains") or model_map.get("missing_policy") != target_mapping.get("missing_policy"):
            mismatches.append(dict(
                field="domain_or_missing_policy",
                expected=dict(domains=model_map.get("domains"), missing_policy=model_map.get("missing_policy")),
                actual=dict(domains=target_mapping.get("domains"), missing_policy=target_mapping.get("missing_policy")),
                message="Miền giá trị hoặc chính sách xử lý thiếu nguồn không khớp với hợp đồng của model.",
            ))
        if model_info.get("mapping_fingerprint") != target_mapping.get("fingerprint"):
            mismatches.append(dict(
                field="mapping_fingerprint",
                expected=model_info.get("mapping_fingerprint"),
                actual=target_mapping.get("fingerprint"),
                message="Mapping fingerprint của snapshot không khớp với mapping fingerprint đã ghim của model.",
            ))
        if len(modes) != 1 or (model_info.get("simulated") is not None and target_simulated != model_info.get("simulated")):
            mismatches.append(dict(
                field="simulated",
                expected=model_info.get("simulated"),
                actual=target_simulated if len(modes) == 1 else "mixed_or_unknown",
                message=(
                    f"Chế độ nguồn is_simulated của snapshot ({target_simulated if len(modes) == 1 else 'trộn/chưa xác định'}) "
                    f"không khớp với chế độ nguồn khi huấn luyện model ({model_info.get('simulated')})."
                ),
            ))

        compatible = len(mismatches) == 0
        compatibility = dict(
            compatible=compatible,
            status="compatible" if compatible else "incompatible_model",
            code="COMPATIBLE" if compatible else "MODEL_CONTRACT_INCOMPATIBLE",
            message=(
                "Hợp đồng feature (33 cột), bộ ánh xạ 2 biến nhị phân, miền giá trị {0, 1}, chính sách không tự điền 0 và chế độ nguồn hoàn toàn tương thích với model đã duyệt."
                if compatible
                else "Model đã chọn không tương thích hợp đồng feature/mapping với snapshot mục tiêu; không thực hiện chấm điểm."
            ),
            remediation=(
                None
                if compatible
                else "Chọn snapshot cùng profile hợp đồng feature/mapping với model đã duyệt, hoặc chọn model được huấn luyện trên đúng hợp đồng nguồn này."
            ),
            checked_fields=[
                "source_contract_version",
                "source_contract_fingerprint",
                "mapping_version",
                "columns",
                "domain_or_missing_policy",
                "mapping_fingerprint",
                "simulated",
            ],
            mismatches=mismatches,
            expected_mapping=model_map,
            actual_mapping=target_mapping,
        )

        coverage_known = True
        if manifest["contract_version"] == SOURCE_CONTRACT:
            cov = raw["source"]["coverage"].get("transactions")
            coverage_known = bool(cov and utc(cov["observed_at"]) <= as_of_dt)

        train_set = set(model_info.get("training_row_ids") or [])
        eval_set = set(model_info.get("evaluation_row_ids") or [])
        columns = frame["contract"]["columns"]

        rows = []
        eligible_indices = []
        for order_idx, tx_item in enumerate(all_txs, 1):
            rid = tx_item["record_id"]
            rev = tx_item["revision"]
            if rid in train_set:
                history_status = "seen_in_training"
                history_label = "Đã dùng trong tập train của model"
                is_new = False
            elif rid in eval_set:
                history_status = "seen_in_evaluation"
                history_label = "Đã dùng trong tập đánh giá giữ riêng (holdout)"
                is_new = False
            else:
                history_status = "new_transaction"
                history_label = "Giao dịch mới (ngoài tập train/holdout)"
                is_new = True

            frow = frame_by_key.get((rid, rev)) or frame_by_rid.get(rid)
            feat_dict = {col: None for col in ADAPTER_COLUMNS}
            miss_reasons = {}
            if frow is not None:
                at_idx = frow["row_index"]
                for col_name in ADAPTER_COLUMNS:
                    if col_name in columns:
                        cidx = columns.index(col_name)
                        feat_dict[col_name] = frame["features"][at_idx][cidx]
                        rsn = frame["evidence"][at_idx]["missing_reasons"].get(col_name)
                        if rsn:
                            miss_reasons[col_name] = rsn

            row_issues = []
            vec = []
            if not compatible:
                for m in mismatches:
                    row_issues.append(dict(
                        code="MODEL_CONTRACT_INCOMPATIBLE",
                        field=m["field"],
                        reason="model_contract_incompatible",
                        message=m["message"],
                        remediation=compatibility["remediation"],
                    ))
                row_status = "incompatible_model"
                status_label = "Không chấm — sai hợp đồng model/snapshot"
                available = False
            elif frow is None:
                msg, act = ADAPTER_TEXT["ROW_NOT_AVAILABLE_AT_AS_OF"]
                row_issues.append(dict(
                    code="ROW_NOT_AVAILABLE_AT_AS_OF",
                    field=None,
                    reason="row_not_available_at_as_of",
                    message=f"{msg} Giao dịch {rid} có thời điểm hiệu lực hoặc ghi nhận sau mốc as_of ({as_of_iso}).",
                    remediation=act,
                ))
                row_status = "unavailable"
                status_label = "Unavailable — giao dịch sau mốc as_of"
                available = False
            else:
                at_idx = frow["row_index"]
                for col_name in ADAPTER_COLUMNS:
                    if col_name not in columns:
                        msg, act = ADAPTER_TEXT["FEATURE_OUT_OF_DOMAIN"]
                        row_issues.append(dict(
                            code="FEATURE_CONTRACT_INCOMPATIBLE",
                            field=col_name,
                            reason="column_missing_in_contract",
                            message=f"Thiếu cột {col_name} trong hợp đồng feature.",
                            remediation=act,
                        ))
                        continue
                    cidx = columns.index(col_name)
                    val = frame["features"][at_idx][cidx]
                    is_missing = frame["missing"][at_idx][cidx] or val is None
                    reason_code = frame["evidence"][at_idx]["missing_reasons"].get(col_name)
                    if not coverage_known:
                        msg, act = ADAPTER_TEXT["FEATURE_SOURCE_NOT_KNOWN_AT_AS_OF"]
                        row_issues.append(dict(
                            code="FEATURE_SOURCE_NOT_KNOWN_AT_AS_OF",
                            field=col_name,
                            reason="transactions_coverage_not_known_at_as_of",
                            message=f"{msg} (cột {col_name}).",
                            remediation=act,
                        ))
                    elif is_missing:
                        msg, act = ADAPTER_TEXT["FEATURE_MISSING"]
                        row_issues.append(dict(
                            code="FEATURE_MISSING",
                            field=col_name,
                            reason=reason_code or "source_missing",
                            message=f"{msg} Cột {col_name} bị thiếu nguồn ({reason_code or 'source_missing'}); giữ nguyên null, không tự điền 0.",
                            remediation=act,
                        ))
                    elif isinstance(val, bool) or not isinstance(val, Real) or not math.isfinite(val) or val not in (0, 1):
                        msg, act = ADAPTER_TEXT["FEATURE_OUT_OF_DOMAIN"]
                        row_issues.append(dict(
                            code="FEATURE_OUT_OF_DOMAIN",
                            field=col_name,
                            reason="value_outside_binary_domain",
                            message=f"{msg} Giá trị cột {col_name}={val} nằm ngoài miền {{0, 1}}.",
                            remediation=act,
                        ))
                    else:
                        vec.append(int(val))
                if row_issues:
                    row_status = "unavailable"
                    status_label = "Unavailable — thiếu nguồn feature tại as_of"
                    available = False
                else:
                    row_status = "scored" if execute_scoring else "ready_to_score"
                    status_label = "Đã chấm điểm shadow" if execute_scoring else "Đủ điều kiện chấm shadow"
                    available = True
                    eligible_indices.append(len(rows))

            rows.append(dict(
                snapshot_order=order_idx,
                score_rank=None,
                chunk_index=None,
                record_id=rid,
                revision=rev,
                occurred_at=tx_item["occurred_at"],
                available_at=tx_item["available_at"],
                event_at=frow["event_at"] if frow is not None else tx_item["occurred_at"],
                knowledge_at=frow["as_of"] if frow is not None else tx_item["available_at"],
                amount_vnd=tx_item["amount_vnd"],
                currency=tx_item["currency"],
                transaction_type=tx_item["transaction_type"],
                description=tx_item["description"],
                created_by=tx_item["created_by"],
                history_status=history_status,
                history_label=history_label,
                is_new_transaction=is_new,
                available=available,
                status=row_status,
                status_label=status_label,
                features=feat_dict,
                feature_vector=vec if available else None,
                missing_reasons=miss_reasons,
                score=None,
                uncalibrated=True,
                model_run_id=model_info["model_run_id"],
                model_cipher_sha256=model_info["model_cipher_sha256"],
                approval_sha256=model_info["approval_sha256"],
                issues=row_issues,
            ))

        chunk_meta = []
        if compatible and execute_scoring and eligible_indices:
            try:
                for chunk_idx, start in enumerate(range(0, len(eligible_indices), MAX_SHADOW_BATCH_ROWS)):
                    slice_indices = eligible_indices[start:start + MAX_SHADOW_BATCH_ROWS]
                    chunk_x = [rows[idx]["feature_vector"] for idx in slice_indices]
                    chunk_rids = [rows[idx]["record_id"] for idx in slice_indices]
                    pred = node.predict_batch_shadow(
                        chunk_x,
                        row_ids=chunk_rids,
                        mapping_fingerprint=target_mapping["fingerprint"],
                    )
                    for idx, pred_row in zip(slice_indices, pred["rows"]):
                        rows[idx]["score"] = pred_row["score"]
                        rows[idx]["chunk_index"] = chunk_idx
                    chunk_meta.append(dict(
                        chunk_index=chunk_idx,
                        row_count=len(slice_indices),
                        first_record_id=chunk_rids[0],
                        last_record_id=chunk_rids[-1],
                    ))
            except TrainingError as exc:
                _translate_training_error(exc)

            ranked_indices = sorted(
                eligible_indices,
                key=lambda i: (-float(rows[i]["score"]), int(rows[i]["snapshot_order"]), str(rows[i]["record_id"])),
            )
            for rank_num, r_idx in enumerate(ranked_indices, 1):
                rows[r_idx]["score_rank"] = rank_num

        scored_count = sum(r["status"] == "scored" for r in rows)
        ready_count = sum(r["status"] in ("scored", "ready_to_score") for r in rows)
        unavail_count = sum(r["status"] == "unavailable" for r in rows)
        incompat_count = sum(r["status"] == "incompatible_model" for r in rows)
        post_cutoff_count = sum(any(i["code"] == "ROW_NOT_AVAILABLE_AT_AS_OF" for i in r["issues"]) for r in rows)
        missing_feat_count = sum(
            any(i["code"] in ("FEATURE_MISSING", "FEATURE_SOURCE_NOT_KNOWN_AT_AS_OF", "FEATURE_OUT_OF_DOMAIN") for i in r["issues"])
            for r in rows
        )
        new_tx_count = sum(r["history_status"] == "new_transaction" for r in rows)
        seen_train_count = sum(r["history_status"] == "seen_in_training" for r in rows)
        seen_eval_count = sum(r["history_status"] == "seen_in_evaluation" for r in rows)
        scores_only = [r["score"] for r in rows if r["score"] is not None]

        if not compatible:
            overall_status = "incompatible_model"
            overall_label = "Không tương thích hợp đồng feature/mapping — không chấm điểm"
        elif not execute_scoring:
            overall_status = "compatible_ready" if unavail_count == 0 else "compatible_with_unavailable_rows"
            overall_label = (
                f"Tương thích hợp đồng — {ready_count}/{len(rows)} giao dịch đủ điều kiện chấm shadow"
                if unavail_count == 0
                else f"Tương thích hợp đồng — {ready_count}/{len(rows)} đủ điều kiện, {unavail_count} dòng unavailable"
            )
        elif unavail_count == 0:
            overall_status = "completed"
            overall_label = f"Hoàn tất chấm shadow ({scored_count}/{len(rows)} giao dịch)"
        else:
            overall_status = "completed_with_unavailable_rows"
            overall_label = f"Hoàn tất chấm shadow ({scored_count} đã chấm, {unavail_count} unavailable)"

        request_fingerprint = digest(canonical(dict(
            tenant_id=model_info["tenant_id"],
            company_id=company,
            model_run_id=model_info["model_run_id"],
            model_cipher_sha256=model_info["model_cipher_sha256"],
            approval_sha256=model_info["approval_sha256"],
            snapshot_id=manifest["snapshot_id"],
            snapshot_data_checksum=manifest["data_checksum"],
            as_of=as_of_iso,
        )))

        return dict(
            version=SHADOW_RUN_VERSION,
            tenant_id=model_info["tenant_id"],
            company_id=company,
            status=overall_status,
            status_label=overall_label,
            request_fingerprint=request_fingerprint,
            snapshot=dict(
                snapshot_id=manifest["snapshot_id"],
                contract_version=manifest["contract_version"],
                checksum=manifest["checksum"],
                data_checksum=manifest["data_checksum"],
                created_at=manifest.get("created_at"),
                source_as_of=source_as_of,
                as_of=as_of_iso,
                simulated=target_simulated,
                same_as_training_snapshot=bool(manifest["snapshot_id"] == model_info.get("training_snapshot_id")),
                transaction_count=len(rows),
            ),
            model=dict(
                model_run_id=model_info["model_run_id"],
                dataset_id=model_info["dataset_id"],
                job_id=model_info["job_id"],
                consent_sha256=model_info["consent_sha256"],
                model_cipher_sha256=model_info["model_cipher_sha256"],
                candidate_sha256=model_info["candidate_sha256"],
                approval_sha256=model_info["approval_sha256"],
                approved_by=model_info["approved_by"],
                approved_at=model_info["approved_at"],
                approval_reason=model_info["approval_reason"],
                approved_for_shadow=True,
                training_snapshot_id=model_info["training_snapshot_id"],
                training_snapshot_contract_version=model_info["training_snapshot_contract_version"],
                training_snapshot_data_checksum=model_info["training_snapshot_data_checksum"],
                training_plan_sha256=model_info["training_plan_sha256"],
                evaluation_sha256=model_info["evaluation_sha256"],
                training_windows=model_info["training_windows"],
                weights_code=model_info["weights_code"],
                coefficients=model_info["coefficients"],
                intercept=model_info["intercept"],
                training_rows=model_info["training_rows"],
                evaluation_rows=model_info["evaluation_rows"],
            ),
            feature_contract=dict(
                version=frame["contract"]["version"],
                fingerprint=frame["contract"]["fingerprint"],
                feature_count=frame["contract"].get("feature_count", len(frame["contract"].get("columns", []))),
            ),
            mapping=target_mapping,
            mapping_fingerprint=target_mapping["fingerprint"],
            compatibility=compatibility,
            batch_execution=dict(
                input_mode="backend_snapshot_feature_builder",
                manual_features_accepted=False,
                max_rows_per_call=MAX_SHADOW_BATCH_ROWS,
                training_four_row_limit_applied=False,
                truncated_to_64=False,
                eligible_rows=len(eligible_indices),
                scored_rows=scored_count,
                call_count=len(chunk_meta),
                chunks=chunk_meta,
            ),
            disclosures=dict(
                execution_location="enterprise_node_decrypted_candidate",
                execution_location_label=(
                    "Chấm điểm tại node doanh nghiệp bằng model ứng viên đã giải mã và được phê duyệt shadow "
                    "(không gửi dữ liệu giao dịch bản rõ lên worker đám mây; không phải suy luận HE trên cloud)."
                ),
                profile_version=model_info.get("profile_version", PROFILE_VERSION),
                training_execution_mode=model_info.get("training_execution_mode", EXECUTION_MODE_VERIFIED),
                native_fhe_training_executed=bool(model_info.get("native_fhe_executed", False)),
                cloud_he_inference_performed=False,
                uncalibrated=True,
                uncalibrated_label=(
                    "Điểm đối chiếu chưa hiệu chuẩn xác suất (uncalibrated); chỉ dùng để xếp hạng ưu tiên rà soát, "
                    "không có ngưỡng tự động kết luận gian lận."
                ),
                fraud_verdicts=False,
                shadow_only=True,
                operational_activation=False,
                active_model_replaced=False,
                operational_queue_changed=False,
            ),
            summary=dict(
                total_rows=len(rows),
                eligible_rows=ready_count,
                scored_rows=scored_count,
                unavailable_rows=unavail_count,
                incompatible_rows=incompat_count,
                post_cutoff_rows=post_cutoff_count,
                missing_feature_rows=missing_feat_count,
                new_transaction_rows=new_tx_count,
                seen_in_training_rows=seen_train_count,
                seen_in_evaluation_rows=seen_eval_count,
                min_score=min(scores_only) if scores_only else None,
                max_score=max(scores_only) if scores_only else None,
            ),
            rows=rows,
        )

    def list_shadow_runs(self, scope, recheck=None):
        tenant, company, actor = self._scope(scope, "data.import")
        with self._tx(scope, recheck, "data.import") as conn:
            approved_models = self._list_approved_models(conn, scope, tenant, company, recheck)
            shadow_runs = self._list_saved_shadow_runs(conn, tenant, company)
        return dict(
            version=SHADOW_RUN_VERSION,
            tenant_id=tenant,
            company_id=company,
            actor_id=actor,
            approved_models=approved_models,
            snapshots=self._list_company_snapshots(scope, recheck),
            shadow_runs=shadow_runs,
        )

    def get_shadow_run(self, scope, shadow_run_id, recheck=None):
        if not isinstance(shadow_run_id, str) or SHADOW_RUN_ID_RE.fullmatch(shadow_run_id) is None:
            fail(400, "SHADOW_RUN_ID_INVALID", "Mã lần chạy shadow không hợp lệ.", "Chọn đúng lần chạy shadow đã lưu của doanh nghiệp.")
        tenant, company, actor = self._scope(scope, "data.import")
        with self._tx(scope, recheck, "data.import") as conn:
            row = conn.execute(
                "SELECT shadow_run_id, nonce, ciphertext FROM batch_shadow_runs WHERE tenant_id=? AND company_id=? AND shadow_run_id=?",
                (tenant, company, shadow_run_id),
            ).fetchone()
            if row is None:
                fail(404, "SHADOW_RUN_NOT_FOUND", "Không tìm thấy lần chạy shadow của doanh nghiệp hiện tại.", "Chọn đúng lần chạy shadow trong lịch sử của doanh nghiệp này.")
            run_doc = self._open("shadow_run", tenant, company, row["shadow_run_id"], row["nonce"], row["ciphertext"])
        return dict(
            version=SHADOW_RUN_VERSION,
            tenant_id=tenant,
            company_id=company,
            actor_id=actor,
            shadow_run=run_doc,
        )

    def check_shadow_run(self, scope, payload, recheck=None):
        tenant, company, actor = self._scope(scope, "data.import")
        with self._tx(scope, recheck, "data.import") as conn:
            model_info, node = self._load_model_for_shadow(conn, scope, tenant, company, payload, recheck)
            evaluation = self._evaluate_snapshot_for_model(
                scope,
                model_info,
                node,
                payload.get("snapshot_id"),
                payload.get("as_of"),
                recheck,
                execute_scoring=False,
            )
            existing = conn.execute(
                "SELECT shadow_run_id FROM batch_shadow_runs WHERE tenant_id=? AND company_id=? AND request_fingerprint=?",
                (tenant, company, evaluation["request_fingerprint"]),
            ).fetchone()
            evaluation["existing_shadow_run_id"] = existing["shadow_run_id"] if existing is not None else None
            evaluation["checked_at"] = self._now()
            evaluation["checked_by"] = actor
        return dict(
            version=SHADOW_RUN_VERSION,
            tenant_id=tenant,
            company_id=company,
            actor_id=actor,
            check=evaluation,
        )

    def create_shadow_run(self, scope, payload, idem_key, recheck=None):
        if not isinstance(idem_key, str) or KEY_RE.fullmatch(idem_key) is None:
            fail(400, "IDEMPOTENCY_KEY_REQUIRED", "Cần Idempotency-Key hợp lệ (8–128 ký tự).", "Gửi kèm header Idempotency-Key cho thao tác chạy và lưu kết quả shadow.")
        tenant, company, actor = self._scope(scope, "data.import")
        with self._company_lock(tenant, company):
            with self._tx(scope, recheck, "data.import") as conn:
                model_info, node = self._load_model_for_shadow(conn, scope, tenant, company, payload, recheck)
                evaluation = self._evaluate_snapshot_for_model(
                    scope,
                    model_info,
                    node,
                    payload.get("snapshot_id"),
                    payload.get("as_of"),
                    recheck,
                    execute_scoring=True,
                )
                req_fp = evaluation["request_fingerprint"]

                by_idem = conn.execute(
                    "SELECT shadow_run_id, request_fingerprint, nonce, ciphertext FROM batch_shadow_runs WHERE tenant_id=? AND company_id=? AND idempotency_key=?",
                    (tenant, company, idem_key),
                ).fetchone()
                if by_idem is not None:
                    if by_idem["request_fingerprint"] != req_fp:
                        fail(409, "IDEMPOTENCY_CONFLICT", "Idempotency-Key đã được dùng cho yêu cầu chấm shadow khác.", "Tạo Idempotency-Key mới cho lần chạy shadow mới.")
                    saved_doc = self._open("shadow_run", tenant, company, by_idem["shadow_run_id"], by_idem["nonce"], by_idem["ciphertext"])
                    all_runs = self._list_saved_shadow_runs(conn, tenant, company)
                    return dict(
                        version=SHADOW_RUN_VERSION,
                        tenant_id=tenant,
                        company_id=company,
                        actor_id=actor,
                        reused_existing=True,
                        shadow_run=saved_doc,
                        shadow_runs=all_runs,
                    )

                receipt_prior = self._receipt(conn, tenant, company, idem_key, req_fp)
                if receipt_prior is not None and isinstance(receipt_prior, dict) and receipt_prior.get("shadow_run_id"):
                    all_runs = self._list_saved_shadow_runs(conn, tenant, company)
                    return dict(
                        version=SHADOW_RUN_VERSION,
                        tenant_id=tenant,
                        company_id=company,
                        actor_id=actor,
                        reused_existing=True,
                        shadow_run=receipt_prior,
                        shadow_runs=all_runs,
                    )

                by_fp = conn.execute(
                    "SELECT shadow_run_id, nonce, ciphertext FROM batch_shadow_runs WHERE tenant_id=? AND company_id=? AND request_fingerprint=?",
                    (tenant, company, req_fp),
                ).fetchone()
                if by_fp is not None:
                    saved_doc = self._open("shadow_run", tenant, company, by_fp["shadow_run_id"], by_fp["nonce"], by_fp["ciphertext"])
                    self._receipt(conn, tenant, company, idem_key, req_fp, saved_doc)
                    all_runs = self._list_saved_shadow_runs(conn, tenant, company)
                    return dict(
                        version=SHADOW_RUN_VERSION,
                        tenant_id=tenant,
                        company_id=company,
                        actor_id=actor,
                        reused_existing=True,
                        shadow_run=saved_doc,
                        shadow_runs=all_runs,
                    )

                next_num = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM batch_shadow_runs").fetchone()[0]
                shadow_run_id = f"shrun_{next_num}_{req_fp[:16]}"
                created_at = self._now()
                run_doc = dict(
                    evaluation,
                    shadow_run_id=shadow_run_id,
                    actor_id=actor,
                    idempotency_key=idem_key,
                    created_at=created_at,
                )
                nonce, ct = self._seal("shadow_run", tenant, company, shadow_run_id, run_doc)
                conn.execute(
                    """
                    INSERT INTO batch_shadow_runs(
                        shadow_run_id, tenant_id, company_id, model_run_id, snapshot_id,
                        as_of, request_fingerprint, idempotency_key, created_at, nonce, ciphertext
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        shadow_run_id,
                        tenant,
                        company,
                        model_info["model_run_id"],
                        evaluation["snapshot"]["snapshot_id"],
                        evaluation["snapshot"]["as_of"],
                        req_fp,
                        idem_key,
                        created_at,
                        nonce,
                        ct,
                    ),
                )
                self._receipt(conn, tenant, company, idem_key, req_fp, run_doc)
                all_runs = self._list_saved_shadow_runs(conn, tenant, company)
        return dict(
            version=SHADOW_RUN_VERSION,
            tenant_id=tenant,
            company_id=company,
            actor_id=actor,
            reused_existing=False,
            shadow_run=run_doc,
            shadow_runs=all_runs,
        )


def _read_json_body(handler):
    try:
        length = int(handler.headers.get("Content-Length", "0"))
    except ValueError:
        fail(400, "CONTENT_LENGTH", "Content-Length không hợp lệ.", "Gửi yêu cầu HTTP hợp lệ.")
    if length <= 0 or length > 262_144:
        fail(400, "PAYLOAD_SIZE", "Nội dung JSON trống hoặc vượt quá 256 KB.", "Gửi nội dung JSON hợp lệ.")
    if not (handler.headers.get("Content-Type") or "").lower().startswith("application/json"):
        fail(415, "CONTENT_TYPE", "Yêu cầu phải có Content-Type: application/json.", "Đặt header Content-Type là application/json.")
    try:
        return loads(handler.rfile.read(length))
    except Exception:
        fail(400, "INVALID_JSON", "Nội dung JSON không hợp lệ.", "Kiểm tra cú pháp JSON của yêu cầu.")


def handle_batch_training(handler, authorizer, manager, method):
    if "?" in handler.path:
        return False
    match = ROUTE_RE.fullmatch(handler.path)
    if not match:
        return False
    company, action, subaction = match.groups()
    if action != "shadow-runs" and subaction is not None:
        return False
    try:
        if manager is None:
            fail(503, "BATCH_TRAINING_UNAVAILABLE", "Chưa bật bộ điều phối huấn luyện nhiều batch.", "Khởi tạo dịch vụ với kho snapshot, kho nhãn và cấu hình huấn luyện batch.")
        check = lambda: authorizer.authorize(handler.headers.get("Authorization"), company)
        scope = check()
        if action is None:
            if method == "GET":
                handler.respond(200, manager.status(scope, check))
                return True
        elif action == "shadow-runs":
            if subaction is None:
                if method == "GET":
                    handler.respond(200, manager.list_shadow_runs(scope, check))
                    return True
                if method == "POST":
                    body = _read_json_body(handler)
                    idem = handler.headers.get("Idempotency-Key")
                    res = manager.create_shadow_run(scope, body, idem, check)
                    handler.respond(200 if res.get("reused_existing") else 201, res)
                    return True
            elif subaction == "check":
                if method == "POST":
                    body = _read_json_body(handler)
                    handler.respond(200, manager.check_shadow_run(scope, body, check))
                    return True
            else:
                if method == "GET":
                    handler.respond(200, manager.get_shadow_run(scope, subaction, check))
                    return True
        elif method == "POST" and action in ("preview", "create-labels", "confirm", "resume", "receive", "evaluate", "approve", "shadow"):
            body = _read_json_body(handler)
            idem = handler.headers.get("Idempotency-Key")
            dispatch = {
                "preview": manager.preview,
                "create-labels": manager.create_labels,
                "confirm": manager.confirm,
                "resume": manager.resume,
                "receive": manager.receive,
                "evaluate": manager.evaluate,
                "approve": manager.approve,
                "shadow": manager.shadow,
            }[action]
            code = 201 if action in ("preview", "create-labels", "confirm", "approve") else 200
            handler.respond(code, dispatch(scope, body, idem, check))
            return True
        handler.respond(405, dict(error=dict(code="METHOD_NOT_ALLOWED", message="Phương thức không được hỗ trợ.", remediation="Dùng đúng GET/POST cho đường dẫn batch-training.")))
        return True
    except (AuthError, RequestFailure, ImportFailure) as exc:
        respond_failure(handler, exc)
        return True
