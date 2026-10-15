"""Turn cases.csv into one offline HTML page a non-technical owner or chief accountant can work through.

    python -m agent2.review_page --cases work/runs/s205/cases.csv --out work/runs/s205/review.html [--limit 60]

Each case shows a plain Vietnamese reason, a suggested action and three one-click verdicts. Verdicts are kept in the
browser (localStorage) and can be downloaded as CSV; that CSV is what `agent2.feedback_sim` models as reviewer input.
No data leaves the machine.
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

import pandas as pd

TEMPLATE = """<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hàng đợi rà soát rủi ro</title><style>
:root{--bg:#f6f7f9;--card:#fff;--ink:#1d2330;--mut:#5f6b7a;--line:#e2e6ec;--hi:#c0392b;--md:#d68910;--lo:#2e7d5b;--acc:#2456b8}
@media (prefers-color-scheme:dark){:root{--bg:#12151b;--card:#1b2029;--ink:#e8ecf2;--mut:#98a3b3;--line:#2a3140;--hi:#ff7b6b;--md:#f0b45a;--lo:#5fd0a0;--acc:#7aa2ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,"Segoe UI",Roboto,sans-serif}
header{padding:20px 16px 8px;max-width:920px;margin:auto}h1{font-size:1.35rem;margin:0 0 4px}p.note{color:var(--mut);margin:0 0 12px;font-size:.93rem}
.bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;max-width:920px;margin:auto;padding:0 16px 12px}
select,input,button{font:inherit;padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink)}
main{max-width:920px;margin:auto;padding:0 16px 40px;display:grid;gap:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}.card.done{opacity:.62}
.top{display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap}.chip{font-size:.8rem;border-radius:999px;padding:2px 10px;border:1px solid currentColor;white-space:nowrap}
.cao_nhat{color:var(--hi)}.cao{color:var(--md)}.trung_binh{color:var(--lo)}
.meta{color:var(--mut);font-size:.88rem}ul{margin:8px 0;padding-left:20px}.act{background:var(--bg);border-radius:8px;padding:8px 10px;font-size:.93rem}
.btns{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}.btns button{cursor:pointer}.btns button.sel{border-color:var(--acc);color:var(--acc);font-weight:600}
.sum{max-width:920px;margin:auto;padding:0 16px 10px;color:var(--mut);font-size:.9rem}
</style></head><body><header><h1>Hàng đợi rà soát rủi ro</h1>
<p class="note">Hệ thống chỉ gợi ý những khoản cần xem; quyết định cuối cùng thuộc về con người. Một cảnh báo không phải là kết luận về cá nhân nào.</p></header>
<div class="bar"><select id="co"><option value="">Mọi công ty</option></select><select id="pr"><option value="">Mọi mức ưu tiên</option>
<option value="cao_nhat">Cao nhất</option><option value="cao">Cao</option><option value="trung_binh">Trung bình</option></select>
<select id="st"><option value="">Mọi trạng thái</option><option value="open">Chưa xử lý</option><option value="done">Đã xử lý</option></select>
<input id="q" placeholder="Tìm theo nhà cung cấp, nhân viên, lý do"><button id="dl">Tải phản hồi (.csv)</button></div>
<div class="sum" id="sum"></div><main id="list"></main>
<script>
const CASES=__DATA__;const KEY="agent2_verdicts_v1";let V={};try{V=JSON.parse(localStorage.getItem(KEY)||"{}")}catch(e){}
const PR={cao_nhat:"Cao nhất",cao:"Cao",trung_binh:"Trung bình"};const OPT=[["confirmed","Xác nhận bất thường thật"],["false_positive","Không phải, bỏ qua"],["information_gap","Cần thêm thông tin"]];
const money=n=>new Intl.NumberFormat("vi-VN").format(n)+" đ";const $=id=>document.getElementById(id);
[...new Set(CASES.map(c=>c.company_id))].forEach(c=>$("co").insertAdjacentHTML("beforeend",`<option>${c}</option>`));
function save(){try{localStorage.setItem(KEY,JSON.stringify(V))}catch(e){}}
function render(){const co=$("co").value,pr=$("pr").value,st=$("st").value,q=$("q").value.toLowerCase();let shown=0;
$("list").innerHTML=CASES.filter(c=>(!co||c.company_id==co)&&(!pr||c.priority==pr)&&(!st||(st=="done")==!!V[c.case_id])&&(!q||(c.entity+c.reason).toLowerCase().includes(q))).map(c=>{shown++;
const reasons=c.reason.split(/ \\| |; /).filter(Boolean).map(r=>`<li>${r}</li>`).join("");const v=V[c.case_id];
const hit=c.estimated_hit_rate?`<span class="meta"> · tỷ lệ gặp vấn đề thật trong dữ liệu mô phỏng khoảng ${Math.round(c.estimated_hit_rate*100)}%</span>`:"";
return `<div class="card ${v?"done":""}"><div class="top"><strong>${c.entity.split(":").pop()} <span class="meta">(${c.company_id})</span></strong><span class="chip ${c.priority}">${PR[c.priority]}</span></div>
<div class="meta">${c.opened_at.slice(0,10)} · ${c.rows} giao dịch · tổng ${money(c.total_amount_vnd)}${hit}</div><ul>${reasons}</ul><div class="act">${c.action_vi}</div>
<div class="btns">${OPT.map(([k,t])=>`<button class="${v&&v.d==k?"sel":""}" data-c="${c.case_id}" data-d="${k}">${t}</button>`).join("")}</div></div>`}).join("");
const n=Object.keys(V).length;$("sum").textContent=`Đang hiển thị ${shown}/${CASES.length} hồ sơ · đã xử lý ${n}`}
document.addEventListener("click",e=>{const b=e.target.closest("button[data-c]");if(!b)return;V[b.dataset.c]={d:b.dataset.d,t:new Date().toISOString()};save();render()});
["co","pr","st","q"].forEach(i=>$(i).addEventListener("input",render));
$("dl").onclick=()=>{const rows=["case_id,decision,decided_at"].concat(Object.entries(V).map(([k,v])=>`${k},${v.d},${v.t}`));
const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([rows.join("\\n")],{type:"text/csv"}));a.download="agent2_phan_hoi.csv";a.click()};render();
</script></body></html>"""


def build(cases_csv: Path, out: Path, limit: int | None = 60):
    cases = pd.read_csv(cases_csv)
    cases = cases.head(limit) if limit else cases
    keep = ["case_id", "company_id", "entity", "priority", "case_score", "reason", "action_vi", "total_amount_vnd", "rows", "opened_at"]
    if "estimated_hit_rate" in cases:
        keep.append("estimated_hit_rate")
    cases["reason"] = cases["reason"].fillna("").map(html.escape)
    data = cases[keep].fillna("").to_dict(orient="records")
    out.write_text(TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False)), encoding="utf-8")
    return len(data)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cases", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--limit", type=int, default=60)
    a = p.parse_args()
    print("cases rendered:", build(a.cases, a.out, a.limit))


if __name__ == "__main__":
    main()
