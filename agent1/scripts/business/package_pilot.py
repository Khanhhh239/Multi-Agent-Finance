"""Package the checked-in rehearsal and blank forms without reading company storage."""

from pathlib import Path
import csv
from io import BytesIO, StringIO
import re
from tempfile import NamedTemporaryFile
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "pilot"
TARGET = ROOT / "agent1_service/ui/workspace/agent1-pilot.zip"
FILES = (
    "BO_PILOT_SME.md",
    "README.md",
    "quyet_dinh.md",
    "fixtures/invoices.csv",
    "fixtures/bank.csv",
    "fixtures/statements.csv",
    "fixtures/outflows.csv",
)

FORM_FIELDS = {
    "uat_observations.csv": (
        "participant_code role first_or_returning task start_time end_time seconds "
        "completed_without_help help_step attempts misunderstanding quote_anonymous followup"
    ).split(),
    "shadow_runs.csv": (
        "firm_alias forecast_id created_at cutoff dataset_hash model_version account_scope "
        "opening_vnd floor_vnd baseline_ref horizon_week actual_known_at forecast_in_vnd "
        "actual_in_vnd forecast_out_vnd actual_out_vnd forecast_balance_vnd baseline_balance_vnd "
        "actual_balance_vnd p10_vnd p90_vnd alert shortfall lead_weeks baseline_minutes "
        "agent_minutes compute_cost_vnd usage_count reason_missing"
    ).split(),
}


def package(target=TARGET):
    """Build from source before replacing the download; never package filled forms."""
    payload = BytesIO()
    with ZipFile(payload, "w", ZIP_DEFLATED) as archive:
        for name in FILES:
            data = (SOURCE / name).read_text(encoding="utf-8-sig")
            if name.endswith(".md"):
                # Repository-only documents are not available in the standalone kit.
                def link(match):
                    label, destination = match.groups()
                    return match[0] if destination.split("#", 1)[0] in FILES else label

                data = re.sub(r"\[([^\]]+)\]\((?!https?://)([^)]+)\)", link, data)
            archive.writestr(
                name, data.encode("utf-8-sig" if name.endswith(".csv") else "utf-8")
            )
        for name, fields in FORM_FIELDS.items():
            text = StringIO(newline="")
            csv.writer(text).writerow(fields)
            archive.writestr(name, text.getvalue().encode("utf-8-sig"))
        archive.writestr(
            "BAT_DAU.txt",
            """BỘ DIỄN TẬP AGENT1

1. Giải nén toàn bộ thư mục. Mở BO_PILOT_SME.md bằng Notepad hoặc trình đọc Markdown.
2. Trong một không gian thử riêng, mở trang Dữ liệu. Nạp lần lượt bốn file trong fixtures theo hướng dẫn.
3. Đối soát một khoản thu với hai hóa đơn, lưu dự báo và so với sao kê.
4. Khi có đối tác, chốt phạm vi trong quyet_dinh.md. Ghi thao tác vào uat_observations.csv và các kỳ dự báo vào shadow_runs.csv.

Chỉ các file trong fixtures là dữ liệu minh họa. Giữ kết quả người dùng thật ở kho riêng của doanh nghiệp.
Các hướng dẫn Đại Phát/UAT và tài liệu kỹ thuật được nhắc trong README thuộc repository, không nằm trong ZIP nhỏ này.
""".encode("utf-8-sig"),
        )
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=target.parent, suffix=".zip", delete=False) as temporary:
        temporary_path = Path(temporary.name)
        temporary.write(payload.getvalue())
    try:
        temporary_path.replace(target)
    finally:
        temporary_path.unlink(missing_ok=True)


if __name__ == "__main__":
    package()
