"""Package the checked-in rehearsal and blank forms without reading company storage."""

from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "pilot"
TARGET = ROOT / "agent1_service/ui/workspace/agent1-pilot.zip"
FILES = (
    "BO_PILOT_SME.md",
    "README.md",
    "quyet_dinh.md",
    "uat_observations.csv",
    "shadow_runs.csv",
    "fixtures/invoices.csv",
    "fixtures/bank.csv",
    "fixtures/statements.csv",
    "fixtures/outflows.csv",
)

if __name__ == "__main__":
    with ZipFile(TARGET, "w", ZIP_DEFLATED) as archive:
        for name in FILES:
            data = (SOURCE / name).read_text(encoding="utf-8-sig")
            if name in ("uat_observations.csv", "shadow_runs.csv"):
                data = data.splitlines()[0] + "\n"
            archive.writestr(
                name, data.encode("utf-8-sig" if name.endswith(".csv") else "utf-8")
            )
        archive.writestr(
            "BAT_DAU.txt",
            """BỘ DIỄN TẬP AGENT1

1. Giải nén toàn bộ thư mục. Mở BO_PILOT_SME.md bằng Notepad hoặc trình đọc Markdown.
2. Trong một không gian thử riêng, mở trang Dữ liệu. Nạp lần lượt bốn file trong fixtures theo hướng dẫn.
3. Đối soát một khoản thu với hai hóa đơn, lưu dự báo và so với sao kê.
4. Khi có đối tác, chốt phạm vi trong quyet_dinh.md. Ghi thao tác vào uat_observations.csv và các kỳ dự báo vào shadow_runs.csv.

Chỉ các file trong fixtures là dữ liệu minh họa. Giữ kết quả người dùng thật ở kho riêng của doanh nghiệp.
""".encode("utf-8-sig"),
        )
