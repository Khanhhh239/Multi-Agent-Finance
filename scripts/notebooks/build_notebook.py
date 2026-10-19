"""
build_notebook.py — dựng lại notebook tham khảo .ipynb ĐÃ CHẠY (kèm output).

Vì sao tồn tại: notebook 11 và 12 được viết dưới dạng .py để chạy được từ dòng lệnh và để
diff được bằng git, nhưng phần còn lại của project dùng .ipynb. File này giữ hai bản đồng bộ:
nguồn duy nhất là .py, .ipynb là bản dựng lại có output trong reference_notebooks/.
Đây là công cụ tái lập thí nghiệm cũ, không phải pipeline cho code T1 mới.

Cách dùng:
    python scripts/notebooks/build_notebook.py 11_extended_window_retraining
    python scripts/notebooks/build_notebook.py 12_oof_survival_boost
"""

import sys
from pathlib import Path

import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[2]
NOTEBOOKS = ROOT / "reference_notebooks"


def split_cells(text):
    cells, kind, buf = [], "code", []
    for line in text.splitlines():
        if line.startswith("# %%"):
            if buf:
                cells.append((kind, "\n".join(buf).strip("\n")))
            kind = "markdown" if "[markdown]" in line else "code"
            buf = []
            continue
        buf.append(line)
    if buf:
        cells.append((kind, "\n".join(buf).strip("\n")))

    out = []
    for kind, src in cells:
        if not src.strip():
            continue
        if kind == "markdown":
            src = "\n".join(l[2:] if l.startswith("# ") else l.lstrip("#") if l.strip() == "#" else l
                            for l in src.splitlines())
        out.append((kind, src))
    return out


def main(stem):
    py = NOTEBOOKS / f"{stem}.py"
    nb = nbformat.v4.new_notebook()
    nb.cells = [nbformat.v4.new_markdown_cell(s) if k == "markdown" else nbformat.v4.new_code_cell(s)
                for k, s in split_cells(py.read_text(encoding="utf-8"))]
    nb.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}

    print(f"{py.name}: {len(nb.cells)} cell — đang chạy...")
    NotebookClient(nb, timeout=7200, kernel_name="python3",
                   resources={"metadata": {"path": str(ROOT)}}).execute()
    out = NOTEBOOKS / f"{stem}.ipynb"
    nbformat.write(nb, out)
    print(f"→ {out}")


if __name__ == "__main__":
    main(sys.argv[1])
