"""Write docs/03_danh_gia_va_hieu_qua_kinh_te/10_ket_qua_R2_v5.md from results/v5/R2 (dữ liệu tổng hợp)."""
import json
from pathlib import Path

R2 = Path("results/v5/R2")
OUT = Path("docs/03_danh_gia_va_hieu_qua_kinh_te/10_ket_qua_R2_v5.md")


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
            md += ["| Điều kiện | Giá trị | Ngưỡng | Đạt |", "|---|---:|---:|:-:|"]
            md += [f"| {k} | {pct(v.get('value'))} | {pct(v.get('minimum'))} | {'Có' if v['passed'] else 'Không'} |"
                   for k, v in cold["gate"]["checks"].items()]
            md += [""]
    sel = load("selection_summary.json")
    if sel:
        md += ["## 4. Tầng chọn có giám sát (20 thế giới, 5 seed)", "", table(sel["candidates"], cols),
               f"Chọn: **{sel['chosen']}**. Chốt chặn trước niêm phong: **{'ĐẠT' if sel['gate']['passed'] else 'KHÔNG ĐẠT'}** "
               f"(quyết định `{sel['gate']['decision']}`).", ""]
        if "checks" in sel["gate"]:
            md += ["| Điều kiện | Giá trị | Ngưỡng | Đạt |", "|---|---:|---:|:-:|"]
            md += [f"| {k} | {pct(v.get('value'))} | {pct(v.get('minimum'))} | {'Có' if v['passed'] else 'Không'} |"
                   for k, v in sel["gate"]["checks"].items()]
            md += [""]
    for tier in ("screening", "selection"):
        if (R2 / tier).exists():
            md += [f"## Phụ lục: từng thế giới, tầng {tier}", "", worlds_table(R2 / tier), ""]
    OUT.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
