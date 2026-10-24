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
ROUND = {"name": "v5", "title": "Kết quả R2 v5 trên dữ liệu tổng hợp", "registration": "08_dang_ky_truoc_v5.md",
         "final": "", "clause": "mục 5 và mục 7 của "}


def write(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))   # LF on every platform


def gate_table(gate):
    rows = ["| Điều kiện | Giá trị | Ngưỡng | Đạt |", "|---|---:|---:|:-:|"]
    rows += [f"| {k} | {pct(v.get('value'))} | {pct(v.get('minimum'))} | {'Có' if v['passed'] else 'Không'} |"
             for k, v in gate["checks"].items()]
    return rows + [""]


def cap_stats(name, reuse=None):
    """Worlds over the 15 percent hard-negative cap and the worst rate, from per-world summaries (screening tier)."""
    dirs = [R2 / "screening" / name]
    if name == "L4-FB-PU" and reuse:
        dirs.insert(0, R2 / reuse / name)
    for d in dirs:
        files = sorted(d.glob("s*/summary.json"))
        if files:
            rates = [max(json.loads(f.read_text(encoding="utf-8"))["hard_negative_rates"].values()) for f in files]
            return sum(x > .15 for x in rates), len(rates), max(rates)
    return None


def outcome(sel, cold, sc=None, pu=None):
    """Registration section 7 when the supervised gate failed; None when R3 may proceed."""
    if sel is None or sel["gate"]["passed"]:
        return None
    md = ["# Kết quả v5: chốt chặn trước niêm phong KHÔNG ĐẠT, không sinh và không chấm niêm phong", "",
          "Tự sinh bởi `scripts/report_r2.py`. Mọi số là **dữ liệu tổng hợp**. Theo " + ROUND["clause"] + "đăng ký "
          f"(`docs/05_ke_hoach_giao_viec/{ROUND['registration']}`): giữ nguyên kết quả, không sửa rồi chấm lại, "
          f"{ROUND['final'] or 'không mở vòng v6, '}**không sinh và không chấm thế giới niêm phong {ROUND['name']}**.", "",
          f"## 1. Ứng viên S2 đã chọn: {sel['chosen'] or 'không có (không ứng viên nào hợp lệ)'}", ""]
    md += gate_table(sel["gate"]) if "checks" in sel["gate"] else ["Không còn ứng viên hợp lệ dưới trần ca khó 15%.", ""]
    if sc:
        w = (pu or {}).get("w") if (pu or {}).get("w") is not None else sc.get("w")
        reuse = f"hn_{sc['hn']}" if sc.get("hn") is not None else f"pu_w{w}"
        md += ["## Bằng chứng: tầng sàng lọc (8 thế giới, seed 0)", "",
               "| Cấu hình | R trung bình | R nhỏ nhất | B trung bình | Thế giới vượt trần 15% | Mức cảnh báo nhầm cao nhất | Hợp lệ |",
               "|---|---:|---:|---:|---:|---:|:-:|"]
        for name, c in sc["candidates"].items():
            cap = cap_stats(name, reuse)
            over = f"{cap[0]} trên {cap[1]}" if cap else ""
            md.append(f"| {name} | {pct(c['R_mean'])} | {pct(c['R_min'])} | {pct(c['B_mean'])} | {over} | "
                      f"{pct(cap[2]) if cap else ''} | {'Có' if c['eligible'] else 'Không'} |")
        md += ["", "Recall chung và recall nhánh bị ẩn của cả bốn ứng viên đều cao hơn ngưỡng chốt chặn (65% và 40%), nhưng "
               "**không ứng viên nào giữ được cảnh báo nhầm trên ca hợp lệ khó dưới 15% ở mọi thế giới và mọi giao thức**. "
               "Trần này là điều kiện hợp lệ trước mọi so sánh, nên không có ứng viên vào tầng chọn. Đây là số trên dữ liệu "
               "phát triển; kinh nghiệm v4 cho thấy điểm niêm phong thường thấp hơn nhiều.", ""]
    if cold:
        state = "đạt" if cold.get("gate") and cold["gate"]["passed"] else "không đạt"
        rows = ["| Cold | R trung bình | R nhỏ nhất | B trung bình | Hợp lệ |", "|---|---:|---:|---:|:-:|"]
        rows += [f"| {n} | {pct(c['R_mean'])} | {pct(c['R_min'])} | {pct(c['B_mean'])} | {'Có' if c['eligible'] else 'Không'} |"
                 for n, c in cold["candidates"].items()]
        md += ["## Cold (không nhãn, 20 thế giới)", ""] + rows + [""]
        md += [f"Chốt chặn Cold (R từ 40%, B từ 33%, thế giới tệ nhất từ 30%, trần 15%) {state}: không ứng viên Cold nào hợp lệ. "
               "Vì S2 không đạt, Cold không được chào bán riêng và cũng không được chấm niêm phong.", ""]
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
    md = [f"# {ROUND['title']}", "",
          "Tự sinh bởi `scripts/report_r2.py` từ `" + R2.as_posix() + "/`. Mọi số là **dữ liệu tổng hợp**; quy tắc theo đăng ký "
          "R1 v1.2. R = recall@B3 ở S2; B = trung bình recall các nhánh ACFE bị ẩn (gộp nhánh nhỏ); Q = (R + B) / 2; "
          "J = trung bình Q của 20% thế giới thấp nhất.", ""]
    pu = load("PU_locked.json")
    if pu and "J" not in pu:
        md += ["## 1. Trọng số PU", "", f"w = {pu['w']} kế thừa từ vòng v5 (trạng thái `{pu['status']}`), không chọn lại.", ""]
    elif pu:
        md += ["## 1. Chọn trọng số PU (L4-FB-PU, 8 thế giới sàng lọc, seed 0)", "",
               "| w | J | Hợp lệ |", "|---:|---:|:-:|"]
        md += [f"| {w} | {pct(pu['J'][w])} | {'Có' if pu['eligible'][w] else 'Không'} |" for w in pu["J"]]
        locked = pu["w"] if pu["w"] is not None else max(pu["J"], key=lambda k: pu["J"][k])
        note = ("" if pu["w"] is not None else " Không w nào hợp lệ theo trần ca khó 15%; áp mục Làm rõ khóa w của đăng ký "
                "(w có J cao nhất, trần không đổi).")
        md += ["", f"Khóa: **w = {locked}** (trạng thái `{pu['status']}`).{note}", ""]
    hn = load("HN_locked.json")
    if hn:
        md += ["## 1b. Chọn trọng số ca hợp lệ khó h (L4-FB-PU, 8 thế giới sàng lọc, w = %s)" % hn["w"], "",
               "| h | J | R trung bình | B trung bình | Hợp lệ |", "|---:|---:|---:|---:|:-:|"]
        md += [f"| {k} | {pct(hn['J'][k])} | {pct(hn['R_mean'][k])} | {pct(hn['B_mean'][k])} | "
               f"{'Có' if hn['eligible'][k] else 'Không'} |" for k in hn["J"]]
        md += ["", f"Khóa: **h = {hn['h']}** (trạng thái `{hn['status']}`).", ""]
    sc = load("screening_summary.json")
    if sc:
        md += [f"## 2. Sàng lọc {len(sc['candidates'])} ứng viên có giám sát", "", table(sc["candidates"], cols),
               f"Vào tầng chọn theo kết quả sàng lọc: **{', '.join(sc['roster']['supervised']) or 'không có'}**.", ""]
        if ROUND["name"] == "v6":
            md += ["Theo sửa đổi v6.1 của đăng ký (chủ dự án chỉ đạo, ghi trước mọi kết quả tầng chọn), `L3-PU` bị loại khỏi tầng chọn vì thời gian chạy; "
                   "chỉ `L4-FB-PU` và `L4-PU-E2-AR` được chạy ở tầng chọn.", ""]
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
    stop = outcome(sel, cold, sc, pu)
    if stop:
        write(OUTCOME, stop)
        print(OUTCOME)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--round", choices=["v5", "v6"], default="v5")
    a = ap.parse_args()
    if a.round == "v6":
        R2 = Path("results/v6/R6")
        OUT = Path("docs/03_danh_gia_va_hieu_qua_kinh_te/12_ket_qua_R6_v6.md")
        OUTCOME = Path("docs/03_danh_gia_va_hieu_qua_kinh_te/13_ket_qua_niem_phong_v6.md")
        ROUND.update(name="v6", title="Kết quả R6 v6 trên dữ liệu tổng hợp", registration="11_dang_ky_truoc_v6.md", clause="",
                     final="đây là vòng cuối, không mở v7, ")
    main()
