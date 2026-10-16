"use strict";
const $ = id => document.getElementById(id);
const labels = {new:"Chưa rà soát",worth_review:"Đáng kiểm tra",legitimate:"Hợp lệ",suspected:"Nghi vấn",confirmed:"Xác nhận"};
const priorities = {cao_nhat:"Ưu tiên cao nhất",cao:"Ưu tiên cao",trung_binh:"Trong tuần"};
let cases = [], selected = null, revision = 0;
const money = value => new Intl.NumberFormat("vi-VN", {style:"currency",currency:"VND",maximumFractionDigits:0}).format(Number(value || 0));
function notice(text, error=false) { $("notice").textContent=text; $("notice").classList.toggle("error",error); }
async function api(path, options={}) {
  const headers = {Authorization:`Bearer ${$("token").value.trim()}`, ...(options.headers || {})};
  const response = await fetch(path, {...options,headers});
  let data;
  try { data=await response.json(); } catch { throw new Error(`Máy chủ trả phản hồi không hợp lệ (${response.status}).`); }
  if (!response.ok) throw new Error(data.error || `Không thực hiện được yêu cầu (${response.status}).`);
  return data;
}
function node(tag, className, text) { const n=document.createElement(tag); if(className)n.className=className; if(text!==undefined)n.textContent=text; return n; }
function showCase(item) {
  selected=item; $("empty-detail").hidden=!!item; $("case-detail").hidden=!item;
  if (!item) return;
  $("priority").textContent=priorities[item.priority] || "Rà soát"; $("priority").className=`badge ${item.priority || ""}`;
  $("case-status").textContent=labels[item.status] || item.status;
  $("case-title").textContent=`Hồ sơ · ${item.entity || "Giao dịch"}`;
  $("case-id").textContent=item.case_id;
  $("case-week").textContent=item.iso_week || String(item.week ?? "—");
  $("deadline").textContent=item.sla_due_at ? new Date(item.sla_due_at).toLocaleString("vi-VN",{timeZone:"Asia/Ho_Chi_Minh"}) : "Chưa có";
  $("case-amount").textContent=money(item.total_amount_vnd);
  $("reason").textContent=item.explanation_vi || item.reason || "Cần đối chiếu chứng từ gốc.";
  $("action").textContent=item.action_vi || "Đối chiếu bằng chứng và ghi nhận kết luận.";
  $("transactions").textContent=Array.isArray(item.transaction_ids) ? item.transaction_ids.join(", ") : String(item.transaction_ids || "");
  $("decision-reason").value=""; $("review-minutes").value="0"; $("worth").value="";
  $("conclusion").value=item.status === "new" ? "worth_review" : item.status;
  renderList();
}
function renderList() {
  const list=$("case-list"); list.replaceChildren();
  if (!cases.length) { list.append(node("p","empty","Không có hồ sơ phù hợp. Nhập dữ liệu hoặc đổi bộ lọc để tiếp tục.")); return; }
  for (const item of cases) {
    const button=node("button",`case-button${selected?.case_id===item.case_id ? " selected" : ""}`);
    button.type="button";
    const top=node("span","top"); top.append(node("span","title",item.entity || item.source_case_id || "Hồ sơ"),node("span",`badge ${item.priority || ""}`,priorities[item.priority] || "Rà soát"));
    button.append(top,node("span","summary",item.explanation_vi || item.reason || "Cần đối chiếu chứng từ."),node("span","meta",`${item.iso_week || ""} · ${labels[item.status] || item.status} · ${money(item.total_amount_vnd)}`));
    button.addEventListener("click",()=>showCase(item)); list.append(button);
  }
}
async function refresh() {
  if (!$("token").value.trim()) throw new Error("Nhập mã truy cập công ty trước.");
  const version=revision;
  const status=$("status").value;
  const [report, queue] = await Promise.all([api("/report"),api(`/cases${status ? `?status=${encodeURIComponent(status)}` : ""}`)]);
  if (version!==revision) return;
  cases=queue.cases; $("company").textContent=`Công ty ${report.company_id}`;
  $("new-count").textContent=report.cases_by_status.new; $("total-count").textContent=report.cases;
  $("minutes").textContent=new Intl.NumberFormat("vi-VN").format(report.review_minutes);
  $("worth-rate").textContent=report.worth_review_rate===null ? "Chưa đo" : `${(100*report.worth_review_rate).toFixed(0)}% · ${report.worth_review_cases_measured} hồ sơ`;
  const previous=selected && cases.find(c=>c.case_id===selected.case_id);
  showCase(previous || null); renderList();
  notice(`Đã mở ${cases.length} hồ sơ của công ty ${report.company_id}.`);
}
function safely(fn) { return async event => { try { await fn(event); } catch(error) { notice(error.message,true); } }; }
$("token").addEventListener("input",()=>{
  revision++; cases=[]; showCase(null); renderList(); $("ingest-id").value="";
  $("company").textContent="Chưa kết nối công ty";
  for(const id of ["new-count","total-count","minutes"]) $(id).textContent="—";
  $("worth-rate").textContent="Chưa đo";
});
$("connect").addEventListener("click",safely(refresh));
$("refresh").addEventListener("click",safely(refresh));
$("status").addEventListener("change",safely(refresh));
$("ingest-form").addEventListener("submit",safely(async event=>{
  event.preventDefault(); const version=revision, button=event.submitter;
  const data=new FormData(); data.append("file",$("data-file").files[0]); data.append("mapping",$("mapping-file").files[0]);
  button.disabled=true; notice("Đang kiểm tra và nhập dữ liệu…");
  try {
    const result=await api("/ingest",{method:"POST",body:data});
    if(version!==revision)return;
    $("ingest-id").value=result.ingest_id;
    notice(result.input_report.status==="reduced" ? "Đã nhập dữ liệu cơ bản. Còn thiếu bằng chứng cho một số năng lực; xem báo cáo đầu vào trước khi chấm." : "Dữ liệu đã qua kiểm tra. Chọn đúng tuần dữ liệu để chấm.");
  } finally { button.disabled=false; }
}));
$("score-form").addEventListener("submit",safely(async event=>{
  event.preventDefault(); const version=revision, button=event.submitter; button.disabled=true;
  notice(`Đang chấm tuần ${$("week").value}. Kết quả sẽ hiển thị sau khi hoàn tất…`);
  try {
    const result=await api(`/score?week=${encodeURIComponent($("week").value)}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({ingest_id:$("ingest-id").value.trim()})});
    if(version!==revision)return;
    await refresh(); notice(result.cached ? "Đã mở lại kết quả cùng dữ liệu, tuần và cấu hình; không tạo hồ sơ trùng." : `Đã chấm tuần đã chọn: ${result.report.alert_rows} dòng cảnh báo, ${result.cases} hồ sơ.`);
  } finally { button.disabled=false; }
}));
$("decision-form").addEventListener("submit",safely(async event=>{
  event.preventDefault(); if(!selected) return;
  const reviewer=$("reviewer").value.trim(); if(!reviewer)throw new Error("Nhập người rà soát trước khi lưu phản hồi.");
  const version=revision, identifier=selected.case_id, button=event.submitter;
  const payload={reviewer_id:reviewer,conclusion:$("conclusion").value,reason:$("decision-reason").value.trim(),review_minutes:Number($("review-minutes").value),worth_review:$("worth").value==="" ? null : $("worth").value==="true"};
  button.disabled=true;
  try { await api(`/cases/${encodeURIComponent(identifier)}/decision`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)}); if(version!==revision)return; await refresh(); notice("Đã ghi thêm phản hồi vào lịch sử rà soát."); }
  finally { button.disabled=false; }
}));
fetch("/health").then(r=>r.json()).then(data=>{$("week").value=data.current_week;if(data.synthetic_demo)$("environment").textContent="Bản thử · Dữ liệu tổng hợp";}).catch(()=>{});
