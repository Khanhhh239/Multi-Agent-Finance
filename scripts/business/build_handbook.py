"""Build the offline handbook and the customer web guide from the same source."""

import base64
from pathlib import Path
import re
import markdown

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs/06_Pilot"
PUBLIC = ROOT / "agent1_service/ui/workspace/manual"
IMG = "../../agent1_service/ui/workspace/manual/img/"
# View boxes around the relevant controls in the original 1265 × 712 screenshots.
SCREENSHOT_VIEWS = {
    "10-connect.png": (375, 175, 505, 365),
    "11-import.png": (209, 59, 615, 463),
    "12-preview.png": (209, 113, 1019, 320),
    "13-pending.png": (209, 213, 1019, 470),
    "15-train.png": (0, 73, 581, 557),
    "16-version.png": (579, 231, 648, 354),
    "17-forecast-form.png": (207, 131, 293, 486),
    "18-base-result.png": (512, 201, 714, 509),
    "19-weekly.png": (512, 326, 714, 342),
    "20-collections.png": (512, 325, 714, 339),
    "21-custom.png": (209, 274, 287, 272),
    "22-scenario.png": (512, 202, 714, 505),
    "23-export.png": (209, 134, 1019, 53),
}
STYLE = """
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#f6f4ed;color:#172e27;font:17px/1.65 'Segoe UI',Arial,sans-serif}main{max-width:1120px;background:#fffefa;margin:auto;padding:32px clamp(16px,5vw,65px) 64px}h1,h2,h3{line-height:1.22;color:#123c30;text-wrap:balance}h1{font-family:Georgia,serif;font-size:clamp(31px,5vw,57px);margin:24px 0}h2{font-size:32px;margin-top:52px;border-top:2px solid #30604e;padding-top:24px}h3{font-size:23px;margin-top:38px}p,li{max-width:93ch}a{color:#125a46}nav{display:flex;flex-wrap:wrap;gap:8px 24px;border-bottom:1px solid #cad6cb;padding:0 0 15px}nav a{font-weight:600}code{background:#f0f2ed;padding:.1em .3em;overflow-wrap:anywhere}table{border-collapse:collapse;width:100%;font-size:15px;line-height:1.5}th,td{text-align:left;vertical-align:top;padding:12px;border-bottom:1px solid #cad6cb}th{background:#183e32;color:white}td:first-child{font-weight:650;width:20%}tbody tr:nth-child(even){background:#f4f7f1}figure{margin:18px 0 24px;padding:12px;border:1px solid #ccdad0;border-radius:6px;background:#f7f9f5}figure img{display:block;max-width:100%;height:auto;margin:auto}figcaption{margin:10px 0 0;text-align:center;font-size:14px;color:#3d554b}.money-figure{padding:10px 20px;background:#edf3e8;border-left:5px solid #56815a}.money-figure p{display:flex;flex-wrap:wrap;align-items:center;gap:7px 12px}.money-figure b{min-width:95px}.money-figure span,.money-figure strong{padding:6px 10px;background:white;border:1px solid #c1d3c3}.money-figure strong{background:#184632;color:white}footer{margin-top:40px;font-size:14px;color:#485b50}ul{padding-left:24px}.table-frame{overflow-x:auto}
@media(max-width:650px){body{font-size:16px}main{padding:18px 14px}h2{font-size:25px}.table-frame table{min-width:690px}figure{padding:5px}}
@media print{body,main{background:white;padding:0;font-size:10pt}nav{display:none}table{font-size:8.7pt}tr,figure,.money-figure{break-inside:avoid}h2,h3{break-after:avoid}figure img{max-height:16cm}a{color:inherit}}
figure svg{display:block;width:100%;height:auto;max-width:100%;max-height:480px;margin:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f0f2ed;padding:10px 12px}
"""


def render(source, internal):
    text = markdown.markdown(source, extensions=["tables", "toc", "fenced_code"])

    def image(match):
        alt, filename = match.groups()
        path = PUBLIC / "img" / filename
        src = (
            ("data:image/png;base64," + base64.b64encode(path.read_bytes()).decode())
            if internal
            else "img/" + filename
        )
        if filename in SCREENSHOT_VIEWS:
            x, y, width, height = SCREENSHOT_VIEWS[filename]
            clip = f"view-{Path(filename).stem}"
            visual = (
                f'<svg role="img" aria-label="{alt}" width="{width}" height="{height}" '
                f'viewBox="{x} {y} {width} {height}">'
                f'<defs><clipPath id="{clip}"><rect x="{x}" y="{y}" width="{width}" '
                f'height="{height}"/></clipPath></defs>'
                f'<image href="{src}" width="1265" height="712" clip-path="url(#{clip})"/></svg>'
            )
        else:
            visual = f'<img src="{src}" alt="{alt}">'
        return f'<figure data-shot="{filename}">{visual}<figcaption>{alt}</figcaption></figure>'

    text = re.sub(
        r'<p><img alt="([^"]*)" src="' + re.escape(IMG) + r'([\w-]+\.png)"\s*/></p>',
        image,
        text,
    )
    if IMG in text:
        raise RuntimeError("Unresolved screenshot path")
    headings = re.findall(r'<h[23] id="([^"]+)">([^<]+)</h[23]>', text)
    links = (
        [(i, t) for i, t in headings if t[:1].isdigit()]
        if internal
        else [(i, t.split(" · ")[0]) for i, t in headings if t.startswith("Bước")]
    )
    nav = "".join(f'<a href="#{i}">{t}</a>' for i, t in links)
    title = "Agent1 · Sổ tay prototype" if internal else "Hướng dẫn sử dụng Agent1"
    text = text.replace("<table>", '<div class="table-frame"><table>').replace(
        "</table>", "</table></div>"
    )
    return f'<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><style>{STYLE}</style><main><nav aria-label="Mục lục">{nav}</nav>{text}<footer>Agent1 · Bản ngày 07-11-26 · Ảnh chụp từ kho Đại Phát.</footer></main></html>'


if __name__ == "__main__":
    source = (DOCS / "SO_TAY_AGENT1.md").read_text(encoding="utf-8")
    guide = source.split("<!-- PUBLIC_GUIDE -->")[1].replace(
        "## 3. Hướng dẫn sử dụng trên web", "# Hướng dẫn sử dụng Agent1", 1
    )
    (DOCS / "SO_TAY_AGENT1.html").write_text(render(source, True), encoding="utf-8")
    (PUBLIC / "index.html").write_text(render(guide, False), encoding="utf-8")
