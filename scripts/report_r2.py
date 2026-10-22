"""Write docs/03_danh_gia_va_hieu_qua_kinh_te/10_ket_qua_R2_v5.md from results/v5/R2 (dữ liệu tổng hợp).

If the supervised pre-seal gate failed, also write 09_ket_qua_niem_phong_v5.md as registration section 7
requires: no sealed v5 world is generated or scored, and the product pivot is stated.
"""
import json
from pathlib import Path

R2 = Path("results/v5/R2")
OUT = Path("docs/03_danh_gia_va_hieu_qua_kinh_te/10_ket_qua_R2_v5.md")
OUTCOME = Path("docs/03_danh_gia_va_hieu_qua_kinh_te/09_ket_qua_niem_phong_v5.md")
PIVOT = "../01_phan_tich_kinh_te_va_nghiep_vu/09_de_xuat_doi_huong_dich_vu_ra_soat.md"


def write(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))   # LF on every platform


def gate_table(gate):
    rows = ["| Điều kiện | Giá trị | Ngưỡng | Đạt |", "|---|---:|---:|:-:|"]
    rows += [f"| {k} | {pct(v.get('value'))} | {pct(v.get('minimum'))} | {'Có' if v['passed'] else 'Không'} |"
             for k, v in gate["checks"].items()]
    return rows + [""]


def outcome(sel, cold):
    """Registration section 7 when the supervised gate failed; None when R3 may proceed."""
    if sel is None or sel["gate"]["passed"]:
        return None
    md = ["# Kết quả v5: chốt chặn trước niêm phong KHÔNG ĐẠT, không sinh và không chấm niêm phong", "",
          "Tự sinh bởi `scripts/report_r2.py`. Mọi số là **dữ liệu tổng hợp**. Theo mục 5 và mục 7 của đăng ký "
          "(`docs/05_ke_hoach_giao_viec/08_dang_ky_truoc_v5.md`): giữ nguyên kết quả, không sửa rồi chấm lại, "
          "không mở vòng v6, **không sinh và không chấm thế giới niêm phong v5**.", "",
          f"## 1. Ứng viên S2 đã chọn: {sel['chosen']}", ""]
    md += gate_table(sel["gate"]) if "checks" in sel["gate"] else ["Không còn ứng viên hợp lệ dưới trần ca khó 15%.", ""]
    if cold:
        state = "đạt" if cold.get("gate") and cold["gate"]["passed"] else "không đạt"
        md += [f"Cold đã chọn: **{cold.get('chosen')}**, chốt chặn Cold {state}. Vì S2 không đạt, Cold không được chào "
               "bán riêng và cũng không được chấm niêm phong.", ""]
    md += ["## 2. Đề xuất đổi hướng", "",
           "Hướng trình chủ dự án là **dịch vụ rà soát định kỳ cho đơn vị kế toán**: quy tắc bằng chứng rõ, đối chiếu "
           "chứng từ, hàng đợi để con người quyết định. Chưa quảng bá phát hiện gian lận tự động hoặc thu hồi tổn thất "
           f"dựa trên dữ liệu tổng hợp. Chi tiết: [đề xuất đổi hướng]({PIVOT}).", "",
           "| Nội dung mục 7 yêu cầu | Ở đâu trong đề xuất |", "|---|---|",
           "| Công việc kế toán được hỗ trợ | Mục 2 |", "| Phần vẫn phải do con người | Mục 3 |",
           "| Ngân sách cảnh báo và thời gian | Mục 4 |",
           "| Phép đo đáng kiểm tra, thời gian rà soát, mức sẵn lòng trả cần thu trong thí điểm | Mục 5 |", "",
           "Các con số thí điểm chỉ được xác lập sau đồng ý pháp lý và doanh nghiệp; không thay bằng số tổng hợp.", ""]
    return md


def load(name):
    p = R2 / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def pct(x):
    return "" if x is None else f"{100 * x:.1f}".replace(".", ",")


def table(cands, cols):
    head = "| Cấu hình | " + " | ".join(c for c, _ in cols) + " |\n|---|" + "---:|" * len(cols) + "\n"
    rows = ""
    for name, v in cands.items():
        cells = []
        for _, key in cols:
            val = v.get(key)
            cells.append(("Có" if val else "Không") if isinstance(val, bool) else pct(val) if isinstance(val, (int, float)) else str(val))
        rows += f"| {name} | " + " | ".join(cells) + " |\n"
    return head + rows


def worlds_table(base):
    lines = ["| Thế giới | Cấu hình | R | B | Q | Ca khó tối đa | Hợp lệ |", "|---|---|---:|---:|---:|---:|:-:|"]
    for cand_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        for w in sorted(cand_dir.glob("s*/summary.json")):
            s = json.loads(w.read_text(encoding="utf-8"))
            lines.append(f"| {w.parent.name[1:]} | {cand_dir.name} | {pct(s['R'])} | {pct(s['B'])} | {pct(s['Q'])} | "
                         f"{pct(max(s['hard_negative_rates'].values()))} | {'Có' if s['eligible'] else 'Không'} |")
    return "\n".join(lines)


def main():
    cols = [("J", "J"), ("Q nhỏ nhất", "Q_min"), ("Q trung bình", "Q_mean"), ("R trung bình", "R_mean"),
            ("R nhỏ nhất", "R_min"), ("B trung bình", "B_mean"), ("Hợp lệ (ca khó ≤ 15%)", "eligible")]
    md = ["# Kết quả R2 v5 trên dữ liệu tổng hợp", "",
          "Tự sinh bởi `scripts/report_r2.py` từ `results/v5/R2/`. Mọi số là **dữ liệu tổng hợp**; quy tắc theo đăng ký "
          "R1 v1.2. R = recall@B3 ở S2; B = trung bình recall các nhánh ACFE bị ẩn (gộp nhánh nhỏ); Q = (R + B) / 2; "
          "J = trung bình Q của 20% thế giới thấp nhất.", ""]
    pu = load("PU_locked.json")
    if pu:
        md += ["## 1. Chọn trọng số PU (L4-FB-PU, 8 thế giới sàng lọc, seed 0)", "",
               "| w | J | Hợp lệ |", "|---:|---:|:-:|"]
        md += [f"| {w} | {pct(pu['J'][w])} | {'Có' if pu['eligible'][w] else 'Không'} |" for w in pu["J"]]
        md += ["", f"Khóa: **w = {pu['w']}** (trạng thái `{pu['status']}`).", ""]
    sc = load("screening_summary.json")
    if sc:
        md += ["## 2. Sàng lọc 4 ứng viên có giám sát", "", table(sc["candidates"], cols),
               f"Ba ứng viên vào tầng chọn: **{', '.join(sc['roster']['supervised']) or 'không có'}**.", ""]
    cold = load("cold_selection.json")
    if cold:
        md += ["## 3. Cold (không nhãn), 20 thế giới", "", table(cold["candidates"], cols[:6] + cols[6:]),
               f"Chọn: **{cold['chosen']}**. Chốt chặn Cold: **{'đạt' if cold['gate'] and cold['gate']['passed'] else 'không đạt'}**.", ""]
        if cold["gate"]:
            md += gate_table(cold["gate"])
    sel = load("selection_summary.json")
    if sel:
        md += ["## 4. Tầng chọn có giám sát (20 thế giới, 5 seed)", "", table(sel["candidates"], cols),
               f"Chọn: **{sel['chosen']}**. Chốt chặn trước niêm phong: **{'ĐẠT' if sel['gate']['passed'] else 'KHÔNG ĐẠT'}** "
               f"(quyết định `{sel['gate']['decision']}`).", ""]
        if "checks" in sel["gate"]:
            md += gate_table(sel["gate"])
    for tier in ("screening", "selection"):
        if (R2 / tier).exists():
            md += [f"## Phụ lục: từng thế giới, tầng {tier}", "", worlds_table(R2 / tier), ""]
    write(OUT, md)
    print(OUT)
    stop = outcome(sel, cold)
    if stop:
        write(OUTCOME, stop)
        print(OUTCOME)


if __name__ == "__main__":
    main()
