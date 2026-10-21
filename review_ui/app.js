"use strict";
const $ = (id) => document.getElementById(id);
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const money = value => new Intl.NumberFormat("vi-VN", {maximumFractionDigits:0}).format(Number(value || 0)) + " ₫";
const number = value => new Intl.NumberFormat("vi-VN").format(Number(value || 0));
const date = value => value ? new Date(value).toLocaleDateString("vi-VN", {timeZone:"Asia/Ho_Chi_Minh"}) : "—";
const datetime = value => value ? new Date(value).toLocaleString("vi-VN", {timeZone:"Asia/Ho_Chi_Minh", hour:"2-digit", minute:"2-digit", day:"2-digit", month:"2-digit", year:"numeric"}) : "—";
const priorities = {cao_nhat:"Cao nhất", cao:"Cao", trung_binh:"Trung bình", thap:"Thấp"};
const statuses = {new:"Chưa rà soát", awaiting_information:"Chờ bổ sung", closed:"Đã kết luận"};
const decisions = {confirmed_suspicion:"Xác nhận nghi vấn",false_positive:"Hợp lệ / báo động giả", information_gap:"Cần bổ sung bằng chứng", non_compliance:"Vi phạm kiểm soát", confirmed_fraud:"Xác nhận gian lận"};
const types = {vendor_payment:"Thanh toán NCC", payroll:"Chi lương", advance_review:"Rà soát số dư tạm ứng", advance_writeoff:"Xóa nợ tạm ứng", adjustment:"Điều chỉnh", advance_issue:"Chi tạm ứng", advance_settlement:"Hoàn ứng"};
const fields = {count:"Số lần",total_vnd:"Tổng giá trị",approval_limit_vnd:"Hạn mức duyệt",window_days:"Cửa sổ (ngày)",invoice_number:"Số hóa đơn",invoice_gross_vnd:"Giá trị hóa đơn",cumulative_paid_vnd:"Tổng đã thanh toán",excess_vnd:"Phần thanh toán vượt",employee_ids:"Nhân viên liên quan",recipient_account:"Tài khoản thụ hưởng",related_party_disclosed:"Đã công bố bên liên quan",field_count:"Số trường trùng",vendor_age_days:"Tuổi NCC (ngày)",amount_vnd:"Giá trị nghiệp vụ",risky_at_invoice:"Rủi ro ngày phát hành",registry_risky_now:"Rủi ro ngày thanh toán",invoice_issued_at:"Ngày phát hành",change_id:"Mã thay đổi",effective_at:"Thời điểm hiệu lực",verified_at:"Thời điểm xác minh",approver_id:"Người duyệt",created_at:"Thời điểm lập",approved_at:"Thời điểm duyệt",saturday_operations:"Có vận hành thứ Bảy",self_approval_limit_vnd:"Hạn mức tự duyệt",approval_seconds:"Thời gian duyệt (giây)",payroll_period:"Kỳ lương",attendance_days:"Ngày công quan sát",alternative_work_evidence:"Bằng chứng thay chấm công",employee_id:"Nhân viên",recipient_employee_bank_count:"Nhân viên cùng tài khoản",days_before_close:"Ngày trước khóa sổ",materiality_vnd:"Mức trọng yếu",advance_id:"Mã tạm ứng",overdue_days:"Số ngày quá hạn",open_fraction:"Tỷ lệ dư nợ",extension_known:"Đã có gia hạn",evidence_on_file:"Có hồ sơ đối chiếu",prior_balance_fraction:"Tỷ lệ dư nợ trước sự kiện",baseline_rows:"Số mẫu lịch sử",baseline_mean_vnd:"Trung bình lịch sử",baseline_sd_vnd:"Độ lệch chuẩn",z:"Độ lệch so với lịch sử",direct_matches:"Thông tin trùng trực tiếp",vendor_ids:"NCC liên quan",shared_fields:"Trường định danh chung",matched_vendor_count:"Tên NCC tương tự",idle_days:"Ngày không giao dịch",prior_p90_vnd:"Phân vị 90 lịch sử"};
let state = {scenario:"003", offset:0, limit:20, selected:null, tab:"overview", meta:null, detail:null, request:0, coverage:[]};
let openGeneration=0, feedbackSaving=false, documentRequestSaving=false;
let caseRouteReady=false, caseRouteKey=null;
const caseKey=(scenario,id)=>JSON.stringify([scenario,id||""]);
function writeCaseLocation(scenario,id,replace=false) {
  const route=new URLSearchParams({scenario});if(id)route.set("case",id);
  const hash="#"+route;
  if(window.location.hash!==hash)window.history[replace?"replaceState":"pushState"](null,"",hash);
}
function clearCaseDetail(message="Chọn một hồ sơ trong hàng đợi để xem bằng chứng.") {
  state.selected=null;state.detail=null;state.tab="overview";
  CaseGraph.dispose("relationship-graph");CaseGraph.dispose("entity-network-graph");
  if($("modal").open)$("modal").close();
  $("detail-panel").innerHTML=`<div class="detail-placeholder"><h2>Hồ sơ rà soát</h2><p>${esc(message)}</p></div>`;
  document.querySelectorAll("[data-case]").forEach(button=>{button.classList.toggle("selected",false);button.setAttribute("aria-pressed","false");});
}
async function applyCaseLocation(force=false) {
  if(!caseRouteReady)return;
  const route=new URLSearchParams(window.location.hash.slice(1)),scenario=route.get("scenario")||state.meta.default_scenario,id=route.get("case")||null;
  const key=caseKey(scenario,id);if(!force&&key===caseRouteKey)return;
  caseRouteKey=key;const generation=++openGeneration;
  clearCaseDetail(id?"Đang nạp hồ sơ…":undefined);hideNotice();
  if(!state.meta.scenarios.includes(scenario)){notice("Không tìm thấy bộ dữ liệu trong liên kết.");return;}
  const changed=scenario!==state.scenario;
  state.scenario=scenario;$("scenario").value=scenario;
  if(changed){state.offset=0;state.request++;$("case-list").innerHTML='<div class="empty-state">Đang nạp hồ sơ…</div>';}
  if(changed||!id||force)await loadQueue();
  if(generation!==openGeneration)return;
  if(id)await openCase(id,{updateLocation:false});
}
const quickReasons = {
  suspicion_document:["confirmed_suspicion","Đã đối chiếu; chứng từ hiện có chưa giải trình được dấu hiệu. Chuyển kiểm tra sâu."],
  suspicion_relation:["confirmed_suspicion","Đã đối chiếu quan hệ và nghiệp vụ liên quan; cần chuyển kiểm tra sâu."],
  valid_document:["false_positive","Đã đối chiếu chứng từ gốc và nghĩa vụ chi; nghiệp vụ phù hợp, dấu hiệu đã được giải trình."],
  valid_authority:["false_positive","Đã đối chiếu thẩm quyền và hồ sơ phê duyệt; nghiệp vụ đúng phạm vi được phép."]
};
async function quickFeedback(decision) {
  if(feedbackSaving)return;
  const selected=quickReasons[$("quick-reason").value], written=$("reason").value.trim();
  if(!written && (!selected || selected[0]!==decision)){notice("Chọn lý do phù hợp hoặc nhập lý do đã đối chiếu.");return;}
  if(!$("reviewer").value.trim()){notice("Nhập tên người rà soát trước khi lưu kết luận.");$("reviewer").focus();return;}
  document.querySelector(`input[name="decision"][value="${decision}"]`).checked=true;
  if(!written)$("reason").value=selected[1];
  await saveFeedback({preventDefault(){}});
}

async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {method:"POST", headers:{"Content-Type":"application/json", "X-CSRF-Token":state.meta.csrf_token}, body:JSON.stringify(body)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Chưa thực hiện được thao tác.");
  return result;
}
function notice(message, success=false) { $("notice").textContent=message; $("notice").className="notice"+(success?" success":""); }
function hideNotice() { $("notice").className="notice hidden"; }
function params() { return new URLSearchParams({scenario:state.scenario,company:$("company").value,status:$("status").value,priority:$("priority").value,category:$("category").value,rule:$("rule").value,q:$("search").value,offset:state.offset,limit:state.limit,daily:$("daily-only").checked?"1":"0"}); }
function headline(row) {
  const rules = row.rule_ids;
  if(row.case_type==="information_request") return "Chi tiền mặt · Cần bổ sung bằng chứng";
  if(row.case_type==="pattern") return "Mẫu khoản chi cận hạn mức · A4";
  if(rules.includes("F3")) return "Khoảng trống dải số chứng từ";
  if(rules.includes("F4")) return "Công nợ quá hạn cần đối chiếu";
  if(rules.includes("P1")) return "Thanh toán vượt giá trị hóa đơn";
  if(rules.includes("T2")) return "Xóa nợ tạm ứng thiếu hồ sơ";
  if(rules.includes("B1") || rules.includes("B2")) return "Đối tác có liên hệ với nhân viên";
  if(rules.includes("E1")) return "Chi lương cần đối chiếu nhân sự";
  if(rules.includes("B7")) return "Thay đổi tài khoản cần xác minh";
  if(rules.includes("C2") || rules.includes("F1")) return "Phê duyệt hoặc điều chỉnh cần đối chiếu";
  if(rules.includes("B4")) return "Hóa đơn có dấu hiệu rủi ro";
  if(rules.includes("T1")) return "Tạm ứng còn dư nợ quá hạn";
  if(rules.includes("A3")) return "Các khoản chi qua người nhận liên kết";
  if(rules.includes("A1") || rules.includes("A2")) return "Chuỗi khoản chi cần kiểm tra hạn mức";
  if(rules.includes("P2")) return "Chi tiền mặt · Đối chiếu hạn mức và chứng từ";
  return "Nghiệp vụ cần đối chiếu bổ sung";
}
async function loadQueue() {
  const request = ++state.request;
  try {
    const result = await api("/api/cases?"+params());
    if(request!==state.request) return;
    $("stat-new").textContent=number(result.counts.backlog);
    $("stat-high").textContent=number(result.counts.high_priority);
    $("stat-gap").textContent=number(result.counts.awaiting_information);
    $("stat-closed").textContent=number(result.counts.closed);
    $("queue-total").textContent=number(result.total);
    const selectedCompany=$("company").value;
    const usedCases=selectedCompany?Number(result.budget.used_by_company[selectedCompany]||0):Object.values(result.budget.used_by_company).reduce((sum,value)=>sum+Number(value),0);
    const usedMinutes=selectedCompany?Number(result.budget.used_minutes_by_company[selectedCompany]||0):Object.values(result.budget.used_minutes_by_company).reduce((sum,value)=>sum+Number(value),0);
    const companyLabel=selectedCompany?"công ty":"các công ty đang hiển thị";
    $("queue-note").textContent=`Tồn ${number(result.counts.backlog)} hồ sơ / ${number(result.counts.backlog_minutes)} phút; ${number(result.counts.source)} hồ sơ nguồn, ${number(result.counts.rereview)} chờ tái rà soát. Đã phân bổ ${number(usedCases)} lượt / ${number(usedMinutes)} phút cho ${companyLabel}; hạn mức mỗi công ty ${result.budget.limit} lượt / ${result.budget.capacity_minutes} phút/ngày.`;
    $("case-list").innerHTML=result.items.length ? result.items.map(row=>`<button class="case-card ${row.case_id===state.selected?"selected":""} ${row.case_type==="source"?"source-case":""}" data-case="${esc(row.case_id)}" aria-pressed="${row.case_id===state.selected}"><div class="case-top"><span class="chip priority-${esc(row.priority)}">● ${esc(priorities[row.priority])}</span><span class="score">${row.case_type==="source"?row.estimated_minutes:row.max_score}<small>${row.case_type==="source"?"phút":"điểm"}</small></span></div><div class="case-title">${esc(headline(row))}</div><p class="case-summary">${esc(row.explanation_vi)}</p><div class="case-sub">${esc(row.company_id)} · ${row.case_type==="source"?"hồ sơ nguồn "+esc(row.source_scope):row.observation_count+" nghiệp vụ"} · ${esc(statuses[row.status])}</div>${row.collection_summary?.active_count?`<div class="collection-badge">${row.collection_summary.ready_for_rereview?"Đã nhận · chờ rà lại":"Chờ bổ sung"} · ${row.collection_summary.active_count} yêu cầu${row.collection_summary.overdue_count?" · quá hạn "+row.collection_summary.overdue_count:""}</div>`:""}<div class="case-bottom"><div>${row.rule_ids.slice(0,3).map(code=>`<span class="rule-tag">${esc(code)}</span>`).join("")}${row.requires_rereview?'<span class="rule-tag rereview-tag">Tái rà soát</span>':""}</div><span class="case-time">${date(row.opened_at)}</span></div><div class="case-bottom"><span class="case-code">${esc(row.case_id)}</span>${row.admitted_today?`<span class="admitted-label">Đã phân bổ ${row.estimated_minutes} phút ✓</span>`:""}</div></button>`).join("") : '<div class="empty-state">Không có hồ sơ phù hợp bộ lọc.<br>Thử đổi trạng thái hoặc nội dung tìm kiếm.</div>';
    $("page-range").textContent=result.total ? `${state.offset+1}–${Math.min(state.offset+state.limit,result.total)} / ${number(result.total)} hồ sơ` : "0 hồ sơ";
    $("previous").disabled=state.offset===0;
    $("next").disabled=state.offset+state.limit>=result.total;
    document.querySelectorAll("[data-case]").forEach(button=>button.addEventListener("click",()=>openCase(button.dataset.case)));
  } catch(error) { if(request!==state.request)return;notice(error.message);$("case-list").innerHTML='<div class="empty-state">Không thể đọc hàng đợi. Kiểm tra thông báo và thử lại.</div>';for(const id of ["stat-new","stat-high","stat-gap","stat-closed"])$(id).textContent="—";$("queue-total").textContent="—";$("previous").disabled=true;$("next").disabled=true;state.selected=null;state.detail=null;$("detail-panel").innerHTML='<div class="detail-placeholder"><h2>Tạm dừng rà soát</h2><p>Chưa đọc được dữ liệu hoặc nhật ký. Tải lại sau khi đã kiểm tra thông báo.</p></div>'; }
}
async function openCase(identifier,{updateLocation=true}={}) {
  const scenario=state.scenario, request=++openGeneration;
  caseRouteKey=caseKey(scenario,identifier);
  if(updateLocation)writeCaseLocation(scenario,identifier);
  clearCaseDetail("Đang nạp hồ sơ…");
  try {
    hideNotice();
    const detail=await api("/api/case?"+new URLSearchParams({scenario,id:identifier}));
    if(request!==openGeneration||scenario!==state.scenario)return;
    if(!detail.case.archived) await api("/api/admit",{scenario,case_id:detail.case.case_id});
    if(request!==openGeneration||scenario!==state.scenario)return;
    state.selected=detail.case.case_id; state.detail=detail; state.tab="overview";
    caseRouteKey=caseKey(scenario,state.selected);writeCaseLocation(scenario,state.selected,true);
    renderDetail(); await loadQueue();
    if(window.innerWidth<820) $("detail-panel").scrollIntoView({behavior:"smooth",block:"start"});
  } catch(error) {
    if(request===openGeneration&&scenario===state.scenario){
      clearCaseDetail("Chưa mở được hồ sơ. Kiểm tra thông báo phía trên, hoặc chọn hồ sơ khác trong hàng đợi.");
      notice(error.message);
    }
  }
}
function renderDetail() {
  const data=state.detail, row=data.case;
  const source=row.case_type==="source";
  const paid=data.transactions.filter(tx=>Number(tx.is_financial_entry)===1 && ["bank","cash"].includes(tx.payment_channel) && tx.txn_type!=="customer_receipt").reduce((sum,tx)=>sum+tx.amount_vnd,0);
  const tabs=source?[["overview","Tổng quan"],["source","Hồ sơ nguồn"],["requests","Bổ sung tài liệu"],["history","Nhật ký"]]:[["overview","Tổng quan"],["transactions","Giao dịch"],["evidence","Bằng chứng"],["requests","Bổ sung tài liệu"],["history","Nhật ký"]];
  const unit=source?`hồ sơ nguồn · ${esc(row.source_scope)}`:`${row.case_type==="pattern"?"Mẫu A4 · ":row.case_type==="batch"?"Lô ":""}${row.observation_count} nghiệp vụ`;
  const scoreValue=source?row.estimated_minutes:row.max_score;
  const scoreLabel=source?"Phút xử lý ước tính":"Điểm ưu tiên rà soát";
  const scoreDetail=source?(row.requires_rereview?`Cần tái rà soát từ ${date(row.rereview_due_at)}`:"Rà soát nguồn một lần"):(paid?"Chi trả trong hồ sơ: "+money(paid):"Chủ yếu là bút toán hoặc rà soát số dư");
  $("detail-panel").innerHTML=`<div class="detail-header"><div class="detail-overline"><span class="chip priority-${esc(row.priority)}">● Ưu tiên ${esc(priorities[row.priority].toLowerCase())}</span><span class="detail-id">${esc(row.case_id)}</span></div><h2>${esc(headline(row))}</h2><div class="detail-meta"><span>${esc(row.company_id)} · ${unit}</span><span>Mở ${date(row.opened_at)}</span><span>${esc(statuses[row.status])}</span></div><div class="detail-score"><div class="score-circle">${scoreValue}</div><div class="score-caption">${scoreLabel}<br><strong>${scoreDetail}</strong></div></div></div><nav class="detail-tabs" aria-label="Các phần hồ sơ">${tabs.map(([id,label])=>`<button data-tab="${id}" class="${state.tab===id?"active":""}">${label}</button>`).join("")}</nav><div class="detail-content" id="detail-content"></div><form id="feedback-form" class="feedback-form"><h3>Ghi nhận kết luận rà soát</h3><div class="form-note">Lưu kết luận sau khi đối chiếu. Phần còn thiếu có thể tiếp tục bổ sung ở lần rà soát sau.</div><div class="decision-options">${Object.entries(decisions).map(([value,label])=>`<label><input type="radio" name="decision" value="${value}" required ${row.feedback?.decision===value?"checked":""}>${label}</label>`).join("")}</div><label class="field">Người rà soát<input type="text" id="reviewer" maxlength="100" required placeholder="Họ và tên người thực hiện" value="${esc(localStorage.getItem("reviewer_name")||"")}"></label><label class="field">Lý do nhanh<select id="quick-reason"><option value="">Chọn lý do đã kiểm tra…</option><optgroup label="Xác nhận nghi vấn"><option value="suspicion_document">Chứng từ chưa giải trình được dấu hiệu</option><option value="suspicion_relation">Quan hệ cần chuyển kiểm tra sâu</option></optgroup><optgroup label="Bỏ qua, hợp lệ"><option value="valid_document">Chứng từ và nghĩa vụ chi khớp</option><option value="valid_authority">Đúng thẩm quyền, có phê duyệt</option></optgroup></select></label><div class="quick-feedback"><button type="button" id="confirm-suspicion" class="primary-button">Xác nhận nghi vấn</button><button type="button" id="dismiss-valid" class="icon-button">Bỏ qua, hợp lệ</button></div><label class="field">Lý do / chứng từ đã đối chiếu<textarea id="reason" maxlength="2000" rows="3" required placeholder="Nêu nội dung đã kiểm tra hoặc bằng chứng cần bổ sung…"></textarea></label><div class="form-bottom"><span class="save-note">Mỗi lần lưu được ghi vào lịch sử.<br>Hồ sơ thiếu bằng chứng tiếp tục mở và tính công tái rà soát.</span><button type="submit" class="primary-button" id="save-feedback">Lưu kết luận →</button></div></form>`;
  document.querySelectorAll("[data-tab]").forEach(button=>button.addEventListener("click",()=>{state.tab=button.dataset.tab; document.querySelectorAll("[data-tab]").forEach(b=>b.classList.toggle("active",b.dataset.tab===state.tab)); renderTab();}));
  if(row.archived) $("feedback-form").remove();
  else {
    if(data.information_requests?.active_count) $("feedback-form").insertAdjacentHTML("afterbegin",`<p class="source-banner source-gap">Còn ${data.information_requests.active_count} yêu cầu tài liệu. Rà lại hoặc hủy từng yêu cầu có lý do trước khi kết luận cuối. Có thể ghi “Cần bổ sung bằng chứng” để tiếp tục theo dõi.</p>`);
    $("feedback-form").addEventListener("submit",saveFeedback);
    $("confirm-suspicion").addEventListener("click",()=>quickFeedback("confirmed_suspicion"));
    $("dismiss-valid").addEventListener("click",()=>quickFeedback("false_positive"));
  }
  renderTab();
}
function caseSupportingEvidence(data) {
  const support=data.review_support||{},invoices=support.invoices||[];
  const invoiceHtml=data.transactions.map(tx=>{
    const invoice=invoices.find(r=>r.company_id===tx.company_id&&r.invoice_id===tx.invoice_id);
    if(!invoice&&!tx.invoice_issued_at)return "";
    const late=Date.parse(tx.invoice_issued_at)>Date.parse(tx.posted_at);
    return `<details class="source-block"><summary>Thời điểm hóa đơn · ${esc(tx.transaction_id)}</summary>${evidenceFacts([["Chi / ghi sổ lúc",datetime(tx.posted_at)],["Hóa đơn phát hành lúc",datetime(tx.invoice_issued_at||invoice?.issued_at)],["Mốc ghi nhận trên nguồn",datetime(invoice?.recorded_at)]])}${late?"<p>Hóa đơn phát hành sau lúc chi; không coi là bằng chứng đã có ở quá khứ.</p>":""}${invoice?ReviewExplanations.invoiceVersions({...invoice,currency:tx.currency||invoice.currency},support.invoice_versions||[],tx.posted_at):""}${!(support.invoice_versions||[]).some(v=>v.company_id===tx.company_id&&v.invoice_id===tx.invoice_id)?"<p>Nếu chỉ có bản cập nhật cuối, chưa đủ xác nhận thời điểm nhận hóa đơn lần đầu; cần lịch sử phiên bản nguồn.</p>":""}</details>`;
  }).join("");
  const returns=(support.transactions||[]).filter(r=>r.original_transaction_id);
  const hasReturns=(support.document_links||[]).some(r=>["cash_return_of","reversal_of"].includes(r.link_type))||returns.length;
  const refund=hasReturns?`<div class="source-block"><strong>Chi gốc và hoàn / đảo liên quan</strong>${(support.transactions||[]).map(tx=>evidenceFacts([["Giao dịch",tx.transaction_id],["Tham chiếu chi gốc",tx.original_transaction_id||"Xem liên kết chứng từ"],["Giá trị theo nguồn",tx.currency&&tx.currency!=="VND"?`${tx.amount_vnd} · chưa xác minh VND`:money(tx.amount_vnd)],["Kênh",tx.payment_channel==="journal"?"Đảo / điều chỉnh sổ; chưa xác nhận nhận tiền thực":tx.payment_channel],["Ghi sổ lúc",datetime(tx.posted_at)]])+`<button class="link-button" data-transaction="${esc(tx.transaction_id)}">Đối chiếu giao dịch →</button>`).join("")}<p>Chứng từ hoàn/đảo phát sinh sau không được dùng để xóa hit lịch sử hoặc tự bù trừ VAT. Điểm hồ sơ vẫn theo snapshot; người rà đối chiếu trước khi ghi kết luận.</p></div>`:"";
  return invoiceHtml+refund;
}
function requestLocalTime(value){return value?new Date(new Date(value).getTime()+7*3600000).toISOString().slice(0,16):"";}
function renderInformationRequests(data,container){
  const info=data.information_requests||{requests:[],history:[]},labels={open:"Chờ bổ sung",received:"Đã nhận · chờ rà lại",reviewed:"Đã đối chiếu tài liệu",cancelled:"Đã hủy có lý do"},actions={create:"Tạo yêu cầu",assign:"Đổi người phụ trách / hạn",receive:"Nhận tài liệu",review:"Rà lại tài liệu",reopen:"Yêu cầu bổ sung tiếp",cancel:"Hủy có lý do"};
  const fields=(row=null)=>`<label class="field">Người phụ trách<input name="owner" maxlength="100" required value="${esc(row?.owner||"")}"></label><label class="field">Hạn bổ sung · giờ Việt Nam<input name="due" type="datetime-local" required value="${requestLocalTime(row?.due_at)}"></label>${row?`<label class="field">Thao tác<select name="action">${(row.status==="open"?[["receive","Đã nhận tài liệu"],["assign","Đổi người phụ trách / hạn"],["cancel","Hủy yêu cầu có lý do"]]:[["review","Đã rà lại tài liệu"],["reopen","Cần bổ sung tiếp"],["assign","Đổi người phụ trách / hạn"],["cancel","Hủy yêu cầu có lý do"]]).map(([k,v])=>`<option value="${k}">${v}</option>`).join("")}</select></label><label class="field">Mã chứng từ đã nhận · mỗi dòng một mã<textarea name="refs" maxlength="6000">${esc((row.evidence_refs||[]).join("\n"))}</textarea></label>`:'<label class="field">Tài liệu cần bổ sung<textarea name="documents" maxlength="2000" required></textarea></label>'}<label class="field">Người thực hiện<input name="actor" maxlength="100" required value="${esc(localStorage.getItem("reviewer_name")||"")}"></label><label class="field">Lý do / nội dung đã đối chiếu<textarea name="reason" maxlength="2000" required></textarea></label><button type="submit" class="primary-button">${row?"Lưu cập nhật":"Tạo yêu cầu tài liệu"}</button>`;
  container.innerHTML=`<div class="source-banner source-gap"><strong>Thu thập tài liệu tách khỏi điểm rủi ro</strong>Hạn và tuổi yêu cầu tính từ lúc người dùng tạo yêu cầu, không lấy ngày giao dịch mô phỏng. Đã nhận tài liệu chưa đồng nghĩa hợp lệ hoặc đủ mẫu A5. Các mã nhập ở đây là tham chiếu do người dùng ghi, chưa được detector chấm lại.</div>${!data.case.archived&&data.case.status!=="closed"?`<form class="document-request-form" data-request=""><h3>Yêu cầu bổ sung</h3>${fields()}</form>`:data.case.archived?"<p>Hồ sơ lịch sử chỉ đọc. Mở hồ sơ kế thừa để rà phạm vi hiện hành.</p>":"<p>Hồ sơ đã kết luận. Ghi quyết định cần bổ sung để mở lại trước khi tạo yêu cầu mới.</p>"}${(info.requests||[]).map(row=>`<div class="source-block"><strong>${esc(labels[row.status]||row.status)}${row.overdue?" · Quá hạn bổ sung":""}</strong>${evidenceFacts([["Yêu cầu",row.requested_documents],["Người phụ trách",row.owner],["Hạn bổ sung",datetime(row.due_at)],["Tạo yêu cầu lúc",datetime(row.created_at)],["Tuổi yêu cầu",`${row.age_hours} giờ`],["Tham chiếu đã nhận",(row.evidence_refs||[]).join(", ")||"Chưa có"]])}${!row.applies_to_current_scope?"<p>Phạm vi đã đổi; yêu cầu này chỉ đọc, không tự áp dụng cho hồ sơ mới.</p>":row.active&&!data.case.archived&&data.case.status!=="closed"?`<form class="document-request-form" data-request="${esc(row.request_id)}">${fields(row)}</form>`:""}</div>`).join("")||"<p>Chưa có yêu cầu tài liệu được ghi riêng.</p>"}<details class="source-block"><summary>Lịch sử yêu cầu tài liệu · không thay nhật ký kết luận</summary>${(info.history||[]).map(e=>`<div class="timeline-entry"><strong>${esc(actions[e.action]||e.action)} · ${esc(e.actor)}</strong><p>${esc(e.reason)}</p><small>${datetime(e.event_at)} · ${esc(e.request_id)}</small></div>`).join("")||"Chưa có sự kiện"}</details><p>Nhận tài liệu → rà lại → chuyển sang phần Kết luận và ghi lý do. Nếu cần đánh giá detector với nguồn mới, cập nhật nguồn đúng quy trình và tạo snapshot mới; không sửa bằng chứng cũ.</p>`;
  container.querySelectorAll(".document-request-form").forEach(form=>form.addEventListener("submit",event=>saveInformationRequest(event,form)));
}
async function saveInformationRequest(event,form){
  event.preventDefault();if(documentRequestSaving)return;
  const value=name=>form.elements.namedItem(name)?.value||"",id=form.dataset.request,scenario=state.scenario,caseId=state.selected,generation=openGeneration;
  const old=state.detail.information_requests?.requests.find(r=>r.request_id===id),action=id?value("action"):"create";
  const body={scenario,case_id:caseId,case_scope_hash:state.detail.case.review_scope_hash,request_id:id,action,
    expected_hash:old?.event_hash||"",owner:value("owner").trim(),due_at:value("due")?value("due")+(value("due").length===16?":00":"")+"+07:00":"",
    actor:value("actor").trim(),reason:value("reason").trim(),requested_documents:value("documents").trim(),
    evidence_refs:value("refs").split(/\r?\n/).map(r=>r.trim()).filter(Boolean)};
  documentRequestSaving=true;const button=form.querySelector('button[type="submit"]');button.disabled=true;
  try{await api("/api/information-requests",body);if(state.scenario===scenario&&state.selected===caseId&&generation===openGeneration){const refreshed=await api("/api/case?"+new URLSearchParams({scenario,id:caseId}));if(state.scenario===scenario&&state.selected===caseId&&generation===openGeneration){state.detail=refreshed;state.tab="requests";renderDetail();await loadQueue();}}notice("Đã lưu yêu cầu tài liệu. Điểm, quy tắc và bằng chứng lịch sử giữ nguyên.",true);}catch(error){notice(error.message);}finally{documentRequestSaving=false;button.disabled=false;}
}
function sourceSummary(data) {
  const finding=data.source_finding||{}, evidence=finding.evidence||{}, rule=finding.rule_id;
  const status=finding.status==="information_gap"?"Thiếu bằng chứng nguồn":finding.signal?"Có điều kiện cần rà soát":"Đã đánh giá, không có tín hiệu";
  const subject=rule==="F3"?(evidence.series?.series_id||data.case.source_scope):(evidence.invoice?.invoice_id||data.case.source_scope);
  return `<div class="detail-context">${esc(data.case.explanation_vi)}.</div><div class="source-banner ${finding.status==="information_gap"?"source-gap":"source-signal"}"><strong>${esc(status)}</strong><span>${esc(rule||data.case.rule_ids[0])} · ${esc(subject)}</span></div><div class="summary-grid">${[["Công ty",finding.company_id||data.case.company_id],["Phạm vi nguồn",finding.scope||data.case.source_scope],["Thời điểm chốt",datetime(finding.cutoff_at||data.case.last_seen_at)],["Công sức ước tính",`${data.case.estimated_minutes} phút`],["Hạn xử lý",datetime(data.case.sla_due_at)],["Tái rà soát",data.case.requires_rereview?date(data.case.rereview_due_at):"Không"]].map(([label,value])=>`<div><span>${esc(label)}</span>${esc(value)}</div>`).join("")}</div><p class="graph-caption">Hồ sơ này được tạo từ sổ nguồn, không gắn cảnh báo vào một giao dịch bất kỳ và không cộng điểm giao dịch.</p>`;
}
function compactList(values, empty="Không có") {
  return values?.length?values.slice(0,20).map(value=>esc(typeof value==="object"?(value.document_id||value.allocation_id||value.explanation_id||JSON.stringify(value)):value)).join(", ")+(values.length>20?` … (${number(values.length)})`:""):empty;
}
function patternSummary(data) {
  const scope=JSON.parse(data.case.pattern_scope), members=new Set(data.transactions.map(tx=>tx.transaction_id));
  const rows=[...data.transactions,...(data.context_transactions||[])].sort((a,b)=>a.posted_at.localeCompare(b.posted_at)||a.transaction_id.localeCompare(b.transaction_id));
  return `<div class="detail-context">Mẫu A4 của ${esc(scope.maker_id)} trong ${esc(scope.period)} · ${esc(scope.company_id)}.</div><p class="graph-caption">Rà chuỗi cận hạn mức chung, đối chiếu riêng từng NCC và nghĩa vụ chi. Phạm vi này chưa xác nhận các khoản cùng nghĩa vụ hoặc các người nhận có liên hệ. Kết luận tại đây không đóng hồ sơ liên quan.</p><div class="section-label">Khoản phát hiện và ngữ cảnh theo từng nghĩa vụ</div><div class="data-table-wrap"><table class="data-table"><thead><tr><th>Khoản / vai trò</th><th>Người nhận</th><th>Ngân hàng / tài khoản</th><th>Hóa đơn</th><th>Giá trị</th></tr></thead><tbody>${rows.map(tx=>`<tr><td><button class="link-button" data-transaction="${esc(tx.transaction_id)}">${esc(tx.transaction_id)}</button><br>${members.has(tx.transaction_id)?"Trong hồ sơ":"Ngữ cảnh trước phát hiện"} · ${date(tx.posted_at)}</td><td>${esc(tx.vendor_name||tx.employee_name||tx.vendor_id||tx.employee_id||"—")}</td><td>${esc(tx.recipient_bank_code||"Chưa xác nhận ngân hàng")}<br>${esc(tx.recipient_account||"Không có tài khoản nhận")}</td><td>${esc(tx.invoice_number||"Thiếu số hóa đơn")}</td><td class="amount">${money(tx.amount_vnd)}</td></tr>`).join("")}</tbody></table></div>`;
}
function sourceEvidence(data) {
  const finding=data.source_finding||{}, evidence=finding.evidence||{};
  if(finding.rule_id==="F3") {
    const series=evidence.series||{};
    return `<div class="section-label">Sổ đăng ký dải số chứng từ</div><div class="summary-grid">${[["Mã dải",series.series_id||"—"],["Loại chứng từ",series.document_type||"—"],["Dải đã đóng",series.start_number!==undefined?`${series.start_number}–${series.closed_through_number}`:"—"],["Ngày đóng",datetime(series.closed_at)],["Nhật ký hủy đầy đủ",Number(series.cancellation_log_complete)===1?"Có":"Không / chưa xác nhận"],["Số lượng số trống",number((evidence.missing_numbers||[]).length)]].map(([label,value])=>`<div><span>${esc(label)}</span>${esc(value)}</div>`).join("")}</div><div class="source-block"><span>Số chứng từ chưa giải trình</span><strong>${compactList(evidence.missing_numbers||[])}</strong></div><div class="source-block"><span>Chứng từ hủy đã phê duyệt</span><strong>${compactList(evidence.cancellations||[])}</strong></div><p class="graph-caption">Đối chiếu sổ đăng ký, nhật ký hủy và chứng từ gốc trong đúng dải đã đóng.</p>`;
  }
  const invoice=evidence.invoice||{}, customer=data.entities?.[invoice.customer_id]||{};
  return `<div class="section-label">Sổ chi tiết công nợ và thu tiền</div><div class="summary-grid">${[["Hóa đơn",invoice.invoice_id||"—"],["Khách hàng",customer.name||invoice.customer_id||"—"],["Giá trị hóa đơn",money(invoice.gross_vnd)],["Ngày đến hạn",date(invoice.due_at)],["Đã thu được xác minh",money(evidence.known_paid_vnd)],["Dư còn lại",money(evidence.outstanding_vnd)],["Số ngày quá hạn",number(evidence.overdue_days)],["Coverage thu tiền",(evidence.receipt_coverage||[]).length?"Đủ hồ sơ khai báo":"Thiếu / chưa xác nhận"]].map(([label,value])=>`<div><span>${esc(label)}</span>${esc(value)}</div>`).join("")}</div><div class="source-block"><span>Phân bổ tiền thu hợp lệ</span><strong>${compactList(evidence.receipt_allocations||[])}</strong></div><div class="source-block"><span>Phân bổ không hợp lệ</span><strong>${compactList(evidence.invalid_allocation_ids||[])}</strong></div><div class="source-block"><span>Giải trình còn hiệu lực</span><strong>${compactList(evidence.approved_explanations||[])}</strong></div><p class="graph-caption">Đối chiếu hóa đơn, giao dịch thu tiền, phân bổ đã xác minh, coverage nguồn và giải trình công nợ tại thời điểm chốt.</p>`;
}
function batchEvidence(data) {
  const events=data.batch_events||[];
  if(!events.length)return "";
  return `<div class="section-label">Đối chiếu các khoản cùng thời điểm</div>${events.map(event=>{
    const facts=Object.entries(event.evidence).filter(([key])=>fields[key]);
    const identifiers=[...event.transaction_ids,...event.related_transaction_ids];
    return `<details class="evidence-card" open><summary><span class="evidence-head"><span class="rule-tag">${esc(event.rule_id)}</span>${esc(event.rule_name)}<span class="evidence-points">${esc(event.points)} điểm</span></span></summary><div class="evidence-body"><div class="graph-caption">Chốt ${datetime(event.detected_at)} · ${event.transaction_ids.length} khoản cùng thời điểm, ${event.related_transaction_ids.length} khoản lịch sử cần đối chiếu.</div><div class="evidence-facts">${facts.map(([key,value])=>`<div><span>${esc(fields[key])}</span>${esc(factValue(key,value))}</div>`).join("")}</div><div>${identifiers.map(id=>`<button class="link-button" data-transaction="${esc(id)}">${esc(id)}</button>`).join(" · ")}</div></div></details>`;
  }).join("")}`;
}
function renderLineage(data, container) {
  const labels={equivalent:"Đổi định danh, giữ cùng phạm vi",split:"Tách hồ sơ",merged:"Gộp hồ sơ",split_merge:"Tách và gộp hồ sơ",changed:"Thay đổi phạm vi hoặc bằng chứng",retired:"Không còn trong snapshot hiện tại"};
  const relations=data.case_lineage||[], history=data.related_feedback_history||[];
  if(!relations.length&&!history.length&&!data.feedback_history.some(event=>event.applies_to_current_scope===false)) return;
  const link=id=>id?`<button class="link-button" data-lineage-case="${esc(id)}">${esc(id)}</button>`:"—";
  container.insertAdjacentHTML("afterbegin",`<div class="section-label">Liên kết hồ sơ qua các lần cập nhật</div>${relations.map(item=>`<div class="timeline-entry"><strong>${esc(labels[item.relation]||item.relation)}</strong>${link(item.old_case_id)} → ${link(item.new_case_id)}</div>`).join("")}${history.map(event=>`<div class="timeline-entry"><strong>Kết luận tại hồ sơ trước: ${esc(decisions[event.decision])}</strong>${esc(event.case_id)} · ${esc(event.reason)}<br><small>${esc(event.reviewer)} · ${datetime(event.reviewed_at)}</small></div>`).join("")}<div class="graph-caption">Kết luận cũ chỉ áp dụng khi phạm vi và bằng chứng vẫn tương đương. Hồ sơ tách/gộp hoặc đổi bằng chứng cần được rà soát lại.</div>`);
  container.querySelectorAll("[data-lineage-case]").forEach(button=>button.addEventListener("click",()=>openCase(button.dataset.lineageCase)));
}
function renderTab() {
  CaseGraph.dispose("relationship-graph");
  const data=state.detail, container=$("detail-content");
  if(state.tab==="requests") {renderInformationRequests(data,container);renderLineage(data,container);return;}
  if(data.case.archived) {
    container.innerHTML=`<div class="integrity">${esc(data.archive_notice)}</div><div class="section-label">Kết luận tại snapshot cũ</div>${data.feedback_history.map(event=>`<div class="timeline-entry"><strong>${esc(decisions[event.decision])}</strong>${esc(event.reason)}<br><small>${esc(event.reviewer)} · ${datetime(event.reviewed_at)}</small></div>`).join("")||'<div class="graph-caption">Chưa có kết luận được lưu cho hồ sơ này.</div>'}`;
    renderLineage(data,container);
    return;
  }
  if(data.case.case_type==="source") {
    if(state.tab==="overview") container.innerHTML=sourceSummary(data);
    else if(state.tab==="source") container.innerHTML=sourceEvidence(data);
    else container.innerHTML=`<div class="integrity">✓ Nhật ký kết luận đã kiểm tra tính liên tục.</div><div class="section-label">Kết luận của người rà soát</div>${data.feedback_history.length?data.feedback_history.slice().reverse().map(event=>`<div class="timeline-entry"><strong>${esc(decisions[event.decision])}</strong>${esc(event.reason)}<br><small>${esc(event.reviewer)} · ${datetime(event.reviewed_at)}</small></div>`).join(""):'<div class="graph-caption">Hồ sơ chưa có kết luận của người rà soát.</div>'}<div class="section-label">Lịch sử hồ sơ nguồn</div>${data.case_events.map(event=>`<div class="timeline-entry"><strong>${event.event==="opened"?"Mở hồ sơ nguồn":"Nguồn đã thay đổi trạng thái"}</strong>${esc(data.case.source_scope)}<br><small>${datetime(event.event_at)}</small></div>`).join("")}<div class="graph-caption">Hạn rà soát gợi ý: ${datetime(data.case.sla_due_at)}. ${data.case.requires_rereview?`Lịch tái rà soát: ${datetime(data.case.rereview_due_at)}.`:""}</div>`;
    renderLineage(data,container);
    return;
  }
  if(state.tab==="overview") {
    const unique=[]; const seen=new Set();
    for(const hit of data.hits) if((hit.points>0||hit.rule_id==="P2")&&!seen.has(hit.rule_id)){unique.push(hit);seen.add(hit.rule_id);}
    container.innerHTML=`<div class="detail-context">${esc(data.case.explanation_vi)}.</div><div class="graph-toolbar"><div class="section-label">Quan hệ cần đối chiếu</div><div class="graph-actions"><button class="icon-button" id="zoom-out" aria-label="Thu nhỏ sơ đồ">−</button><button class="icon-button" id="zoom-in" aria-label="Phóng to sơ đồ">+</button><button class="icon-button" id="zoom-reset">Đặt lại</button></div></div><div class="graph-wrap"><div id="relationship-graph" class="cy-graph" role="group" aria-label="Sơ đồ quan hệ của hồ sơ"></div><div class="graph-legend"><span><i class="legend-vendor"></i>Đối tác / nghiệp vụ</span><span><i class="legend-bank"></i>TK / SĐT</span><span><i class="legend-employee"></i>Nhân sự</span></div></div><div class="graph-caption" id="graph-caption">Chọn một nút để xem chi tiết. Có thể phóng to và kéo sơ đồ.</div><div id="node-detail" class="node-detail hidden"></div><div class="section-label">Bằng chứng chính</div>${unique.slice(0,3).map(h=>evidenceCard(h,true)).join("")}<button class="text-button" id="all-evidence">Xem toàn bộ ${data.hits.length} dấu hiệu và ngoại lệ →</button>`;
    if(data.case.case_type==="pattern") container.innerHTML=patternSummary(data)+`<div class="section-label">Bằng chứng chính</div>${unique.slice(0,3).map(h=>evidenceCard(h,true)).join("")}<button class="text-button" id="all-evidence">Xem toàn bộ ${data.hits.length} dấu hiệu và ngoại lệ →</button>`;
    $("all-evidence").addEventListener("click",()=>{state.tab="evidence";document.querySelectorAll("[data-tab]").forEach(b=>b.classList.toggle("active",b.dataset.tab===state.tab));renderTab();});
    if(data.case.case_type!=="pattern") drawGraph(data);
  } else if(state.tab==="transactions") {
    container.innerHTML=`<div class="section-label">${data.transactions.length} nghiệp vụ trong hồ sơ</div><div class="data-table-wrap"><table class="data-table"><thead><tr><th>Ngày / nghiệp vụ</th><th>Giá trị</th><th>Nợ / Có</th><th>Chi tiết</th></tr></thead><tbody>${data.transactions.map(tx=>`<tr><td>${date(tx.posted_at)}<br>${esc(types[tx.txn_type]||tx.txn_type)}</td><td class="amount">${money(tx.amount_vnd)}</td><td>${esc(tx.debit_account||"—")} / ${esc(tx.credit_account||"—")}</td><td><button class="link-button" data-transaction="${esc(tx.transaction_id)}">${esc(tx.transaction_id)}</button></td></tr>`).join("")}</tbody></table></div><div class="section-label">Chứng từ kế toán liên quan</div>${data.documents.map(item=>`<div class="document-title">${esc(item.document.document_id)} · ${esc(item.document.purpose)} · ${date(item.document.posted_at)}</div><div class="data-table-wrap"><table class="data-table"><thead><tr><th>Tài khoản</th><th>Nợ</th><th>Có</th></tr></thead><tbody>${item.lines.map(line=>`<tr><td>${esc(line.account_code)}</td><td class="amount">${money(line.debit_vnd)}</td><td class="amount">${money(line.credit_vnd)}</td></tr>`).join("")}</tbody></table></div>`).join("")||'<p class="graph-caption">Sự kiện rà soát số dư có thể không phát sinh bút toán.</p>'}`;
  } else if(state.tab==="evidence") {
    container.innerHTML=`<div class="section-label">Dấu hiệu đã ghi nhận tại thời điểm giao dịch</div><div class="graph-caption">Mỗi dấu hiệu có dữ kiện và giao dịch ngữ cảnh riêng. Ngoại lệ không đóng góp điểm.</div>${data.hits.map(h=>evidenceCard(h,false)).join("")}`;
  } else {
    container.innerHTML=`<div class="integrity">✓ Nhật ký kết luận đã kiểm tra tính liên tục.</div><div class="section-label">Kết luận của người rà soát</div>${data.feedback_history.length?data.feedback_history.slice().reverse().map(event=>`<div class="timeline-entry"><strong>${esc(decisions[event.decision])}</strong>${esc(event.reason)}<br><small>${esc(event.reviewer)} · ${datetime(event.reviewed_at)}</small></div>`).join(""):'<div class="graph-caption">Hồ sơ chưa có kết luận của người rà soát.</div>'}<div class="section-label">Lịch sử cảnh báo mô phỏng</div>${data.case_events.map(event=>`<div class="timeline-entry"><strong>${event.event==="opened"?"Mở hồ sơ":event.event==="batch_closed"?"Đối chiếu lô hoàn tất":"Nâng mức ưu tiên"}</strong>Ưu tiên ${esc(priorities[event.priority])} · ${event.rule_score} điểm<br><small>${datetime(event.event_at)} · ${esc(event.transaction_id)}</small></div>`).join("")}<div class="graph-caption">Hạn rà soát gợi ý từ snapshot: ${datetime(data.case.sla_due_at)}. Đây là lịch của dữ liệu mô phỏng.</div>`;
  }
  if(["overview","evidence","transactions"].includes(state.tab))container.insertAdjacentHTML("afterbegin",a5Status(data.a5_evaluations||[]));
  if(state.tab==="overview"||state.tab==="evidence")container.insertAdjacentHTML("afterbegin",ReviewExplanations.score(data.case,data.hits,data.review_support?.rule_scores||[])+caseSupportingEvidence(data)+batchEvidence(data));
  if(data.linked_cases?.length)container.insertAdjacentHTML("afterbegin",`<div class="section-label">Hồ sơ liên quan, kết luận riêng</div>${data.linked_cases.map(row=>`<button class="link-button" data-linked-case="${esc(row.case_id)}">${esc(row.case_id)} · ${esc(priorities[row.priority])} · ${row.max_score} điểm</button>`).join(" · ")}`);
  renderLineage(data,container);
  container.querySelectorAll("[data-linked-case]").forEach(button=>button.addEventListener("click",()=>openCase(button.dataset.linkedCase)));
  container.querySelectorAll("[data-related]").forEach(button=>button.addEventListener("click",()=>relatedModal(Number(button.dataset.related))));
  container.querySelectorAll("[data-transaction]").forEach(button=>button.addEventListener("click",()=>transactionModal(button.dataset.transaction)));
}
function factValue(key,value) {
  if(value==null || value==="") return "Chưa có thông tin";
  if(key.endsWith("_vnd")) return money(value);
  if(key.endsWith("_at")) return datetime(value);
  if(typeof value==="object") return Array.isArray(value)?value.slice(0,5).join(", ")+(value.length>5?`… (${value.length})`:""):Object.entries(value).map(([k,v])=>`${k}: ${Array.isArray(v)?v.join(", "):v}`).join("; ");
  if(["open_fraction","prior_balance_fraction"].includes(key)) return `${Math.round(value*100)}%`;
  return String(value);
}
function evidenceFacts(items) {
  return `<div class="evidence-facts">${items.map(([label,value])=>`<div><span>${esc(label)}</span>${esc(value==null||value===""?"Chưa có thông tin":value)}</div>`).join("")}</div>`;
}
function evidenceSource(label, record, items=[]) {
  if(!record)return `<p class="graph-caption">${esc(label)}: chưa có bản ghi nguồn trong bằng chứng này.</p>`;
  return `<details class="source-block"><summary>${esc(label)}</summary>${evidenceFacts([...items,["Mã bằng chứng",record.evidence_id],["Trạng thái nguồn",record.status==="approved"?"Đã duyệt":record.status||"Không khai báo"],["Người duyệt",record.approver_id],["Phê duyệt lúc",datetime(record.approved_at)],["Nguồn được biết lúc",datetime(record.observed_at)]])}</details>`;
}
function leaveEvidence(proof) {
  const groups=[["Thao tác cần đối chiếu",proof.violations||[]],["Thao tác có quyền làm việc trong kỳ nghỉ",proof.authorized_actions||[]]];
  const actionNames={maker:"Lập bút toán",approver:"Duyệt bút toán",all:"Mọi thao tác"};
  const content=groups.map(([label,rows])=>rows.map(row=>{
    const action=row.action||{},leave=row.leave||{},permissions=row.authorizations||[];
    return `<div class="source-block"><strong>${esc(label)}</strong>${evidenceFacts([["Nhân viên thao tác",action.employee_id],["Thao tác",actionNames[action.action]||action.action],["Thời điểm thao tác",datetime(action.action_at)],["Mã hành động",action.action_id],["Kỳ nghỉ bắt đầu",datetime(leave.starts_at)],["Kỳ nghỉ kết thúc",datetime(leave.ends_at)],["Mã kỳ nghỉ",leave.leave_id]])}${evidenceSource("Nguồn thao tác",row.action,[["Mã hành động",action.action_id],["Giao dịch",action.transaction_id]])}${evidenceSource("Nguồn nghỉ phép",row.leave,[["Mã kỳ nghỉ",leave.leave_id],["Nhân viên nghỉ phép",leave.employee_id]])}${permissions.length?permissions.map(p=>evidenceSource("Quyền làm việc trong kỳ nghỉ",p,[["Mã quyền",p.authorization_id],["Phạm vi thao tác",actionNames[p.action]||p.action],["Hiệu lực từ",datetime(p.starts_at)],["Hiệu lực đến",datetime(p.ends_at)]])).join(""):"<p>Chưa thấy quyền làm việc trong kỳ nghỉ phù hợp trong bằng chứng của thao tác này.</p>"}</div>`;
  }).join("")).join("");
  return (content||'<div class="source-banner source-gap">Chưa có chi tiết thao tác/nghỉ phép trong bằng chứng này.</div>')+'<p class="graph-caption">Các mốc lấy từ snapshot bằng chứng của lần đánh giá. Đối chiếu người thực hiện và quyền làm việc; dấu hiệu này chưa phải kết luận gian lận.</p>';
}
function employmentEvidence(proof) {
  const event=proof.employment_event||{},settlement=proof.settlement||{};
  const status={confirmed_post_termination_salary:"Nguồn ghi nhận lương thường kỳ cho giai đoạn sau chấm dứt",approved_final_payment:"Khoản quyết toán/truy lĩnh được giải trình theo nguồn",information_gap:"Chưa đủ bằng chứng về loại khoản chi hoặc kỳ phục vụ"};
  const kinds={regular_salary:"Lương thường kỳ",backpay:"Truy lĩnh",final_settlement:"Quyết toán cuối cùng",severance:"Trợ cấp thôi việc",bonus:"Thưởng"};
  return `<div class="source-banner ${proof.evidence_status==="information_gap"?"source-gap":"source-signal"}"><strong>${esc(status[proof.evidence_status]||"Chưa có trạng thái xác nhận nguồn")}</strong></div>${evidenceFacts([["Nhân viên",event.employee_id||settlement.employee_id],["Sự kiện lao động",({termination:"Chấm dứt hợp đồng",rehire:"Tái tuyển dụng"})[event.event_type]||event.event_type],["Ngày hiệu lực",date(event.effective_date)],["Loại khoản chi",kinds[settlement.payment_kind]||settlement.payment_kind],["Kỳ lương",settlement.payroll_period],["Kỳ phục vụ từ",date(settlement.service_period_start)],["Kỳ phục vụ đến",date(settlement.service_period_end)],["Số tiền được duyệt",factValue("amount_vnd",settlement.authorized_amount_vnd)]])}${evidenceSource("Nguồn sự kiện lao động",proof.employment_event,[["Mã sự kiện",event.employment_event_id]])}${evidenceSource("Nguồn khoản chi lương",proof.settlement,[["Mã khoản chi",settlement.settlement_id],["Giao dịch",settlement.transaction_id]])}<p class="graph-caption">Các mốc lấy từ snapshot bằng chứng của lần đánh giá. Đối chiếu quyết định gốc, tái tuyển và quyết toán trước khi kết luận.</p>`;
}
function closingEvidence(proof) {
  const records=proof.source_records||[],audit=proof.audit_id&&records.find(r=>r.audit_id===proof.audit_id),closing=proof.closing_id&&records.find(r=>r.closing_id===proof.closing_id),policy=proof.policy_id&&records.find(r=>r.policy_id===proof.policy_id);
  const days=proof.days_before_close==null?"Chưa có thông tin":new Intl.NumberFormat("vi-VN",{maximumFractionDigits:2}).format(proof.days_before_close)+" ngày";
  return `<div class="source-banner ${proof.evidence_status==="confirmed_sources"?"source-signal":"source-gap"}"><strong>${proof.evidence_status==="confirmed_sources"?"Có nguồn xác nhận nhập thủ công, lịch khóa sổ và mức trọng yếu":"Chưa thấy bộ nguồn xác nhận đầy đủ trong bằng chứng này"}</strong></div>${evidenceFacts([["Giá trị bút toán",factValue("amount_vnd",proof.amount_vnd)],["Mức trọng yếu",factValue("materiality_vnd",proof.materiality_vnd)],["Nhập sổ lúc",datetime(proof.entered_at)],["Khóa sổ lúc",datetime(proof.closing_at)],["Cách thời điểm khóa sổ",days],["Mã nhật ký nhập sổ",proof.audit_id],["Mã lịch khóa sổ",proof.closing_id],["Mã chính sách trọng yếu",proof.policy_id]])}${evidenceSource("Nhật ký nhập sổ",audit,[["Mã nhật ký",proof.audit_id],["Người nhập",audit?.employee_id],["Nguồn nhập",audit?.entry_origin==="manual"?"Nhập thủ công":audit?.entry_origin]])}${evidenceSource("Lịch khóa sổ",closing,[["Mã lịch",proof.closing_id],["Kỳ bắt đầu",date(closing?.period_start)],["Kỳ kết thúc",date(closing?.period_end)]])}${evidenceSource("Chính sách trọng yếu",policy,[["Mã chính sách",proof.policy_id],["Hiệu lực từ",date(policy?.effective_from)],["Hiệu lực đến",date(policy?.effective_to)]])}<p class="graph-caption">Tham chiếu lấy từ snapshot bằng chứng của lần đánh giá, không thay thế tài liệu gốc. Nhập thủ công gần khóa sổ chưa chứng minh bút toán sai.</p>`;
}
function evidenceCard(hit, open) {
  const index=state.detail.hits.indexOf(hit);
  const proof=hit.evidence||{};
  const known=Object.entries(proof).filter(([key,value])=>fields[key]&&!(key==="window_days"&&value==null&&proof.period)).slice(0,8);
  if(hit.rule_id==="A4"&&proof.period)known.unshift(["period",proof.period]);
  const codes=[hit.rule_id,...(hit.aliases||[])].join(" / ");
  const role=hit.suppressed_reason?"Ngoại lệ":hit.scoring_role==="information_request"?"Cần bổ sung · 0 điểm":hit.scoring_role==="master_quality"?"Chất lượng danh mục":hit.scoring_role==="context"?"Thông tin ngữ cảnh":"Thông tin";
  const facts=hit.rule_id==="C4"&&("violations" in proof||"authorized_actions" in proof)?leaveEvidence(proof):hit.rule_id==="E2"&&("employment_event" in proof||"settlement" in proof)?employmentEvidence(proof):hit.rule_id==="F1"?closingEvidence(proof):hit.rule_id==="A5"&&proof.selected_parameter?a5Threshold(proof):hit.rule_id==="P2"&&proof.review_category?cashEvidence(proof):evidenceFacts(known.map(([key,value])=>[key==="period"?"Kỳ tháng":fields[key],factValue(key,value)]));
  return `<details class="evidence-card" ${open?"open":""}><summary><span class="evidence-head"><span class="rule-tag">${esc(codes)}</span>${esc(hit.rule_name)} <span class="evidence-points">${hit.points>0?"+"+hit.points+" điểm":role}</span></span></summary><div class="evidence-body">${hit.suppressed_reason?`<div class="suppression">✓ ${esc(hit.suppressed_reason)}</div>`:""}${facts}${ReviewExplanations.exception(hit,state.detail.review_support||{})}${hit.rule_id==="P2"?ReviewExplanations.cashSentence(hit):""}<div class="graph-caption">${datetime(hit.detected_at)} · ${esc(hit.transaction_id)}</div>${hit.related_transaction_ids.length?`<button class="link-button" data-related="${index}">Đối chiếu ${hit.related_transaction_ids.length} giao dịch ngữ cảnh →</button>`:""}</div></details>`;
}
function a5Threshold(proof) {
  return ReviewExplanations.a5(proof);
}
function a5Status(rows) {
  if(!rows.length)return '<div class="source-banner source-gap"><strong>A5 · Chưa có bản đo theo giao dịch trong snapshot này.</strong> Chạy lại bản xuất độ phủ để biết có đủ lịch sử hay không.</div>';
  const ready=rows.filter(r=>r.ready).length, eligible=rows.filter(r=>r.eligible).length;
  const labels={ready:"Đủ lịch sử",partial_history:"Đủ một phần · còn tài khoản thiếu mẫu",insufficient_history:"Thiếu mẫu · chưa đánh giá được",not_applicable:"Ngoài phạm vi nguồn A5",not_observed_at_cutoff:"Nguồn chưa được biết lúc ghi sổ"};
  return `<details class="source-block"><summary><strong>A5 · ${ready}/${eligible} giao dịch có nguồn đủ lịch sử (${rows.length} giao dịch trong hồ sơ)</strong></summary><p>Thiếu mẫu hoặc không có hit không phải kết luận hợp lệ. Điều kiện A5 còn yêu cầu bút toán tài chính và số tiền tròn nghìn.</p>${rows.map(r=>`<div class="coverage-item"><strong>${esc(r.transaction_id)} · ${esc(labels[r.status]||r.status)}</strong><small>${r.a5_gate?"Đạt điều kiện bút toán/số tròn":"Ngoài điều kiện bút toán/số tròn"} · ${r.ready_candidate_count}/${r.candidate_count} phép đo đủ mẫu${r.suppressed_reason?" · Ngoại lệ đã duyệt":""}</small>${r.observations.map(o=>`<small>TK ${esc(o.account_code)} · ${esc(o.measurement)} · ${o.sample_count}/${o.minimum_samples} mẫu (${o.window_days} ngày) · ${o.threshold_vnd==null?"Chưa có ngưỡng":money(o.threshold_vnd)} · ${o.phase==="all_days"?"Toàn bộ ngày":esc(o.phase)}</small>`).join("")}</div>`).join("")}</details>`;
}
function a5CoverageSummary(data) {
  if(!data.available)return '<div class="source-banner source-gap"><strong>A5 · Chưa có bản đo độ phủ theo giao dịch.</strong> Không suy ra độ phủ từ bảng tham số.</div>';
  const n=data.totals, pct=v=>v==null?"Chưa có mẫu số":(v*100).toFixed(2)+"%";
  return `<div class="source-block"><strong>A5 · Độ phủ tại thời điểm ghi sổ</strong><p>${number(n.ready_transactions)}/${number(n.eligible_transactions)} giao dịch có nguồn đủ lịch sử: ${pct(n.ready_over_eligible)}. Trên toàn bộ dữ liệu: ${number(n.ready_transactions)}/${number(n.transactions)} (${pct(n.ready_over_all)}).</p><p>Thiếu mẫu: ${number(n.insufficient_transactions)}. Đủ một phần: ${number(n.partial_transactions)}. Ngoài phạm vi nguồn/chưa biết nguồn: ${number(n.unavailable_transactions)}.</p><p>Riêng bút toán tài chính có số tiền tròn nghìn: ${number(n.a5_gate_ready_transactions)}/${number(n.a5_gate_eligible_transactions)} giao dịch có nguồn đủ mẫu (${pct(n.a5_gate_ready_over_eligible)}).</p><div class="data-table-wrap"><table class="data-table"><thead><tr><th>Công ty</th><th>Đủ lịch sử / có nguồn</th><th>Độ phủ</th></tr></thead><tbody>${data.groups.filter(g=>g.dimension==="company").map(g=>`<tr><td>${esc(g.value)}</td><td>${number(g.ready_transactions)} / ${number(g.eligible_transactions)}</td><td>${pct(g.ready_over_eligible)}</td></tr>`).join("")}</tbody></table></div><p class="graph-caption">Một giao dịch được tính đủ lịch sử khi ít nhất một phép đo được chọn có ngưỡng; phép đo còn thiếu mẫu được hiển thị riêng. Số dòng tham số không phải mẫu số giao dịch. Không có hit không đồng nghĩa không có rủi ro.</p></div>`;
}
function cashEvidence(proof) {
  const missing={invoice_identity:"Mã hoặc số hóa đơn",invoice_issued_at:"Ngày hóa đơn",invoice_gross_vnd:"Tổng tiền hóa đơn",invoice_issued_at_not_in_future:"Hóa đơn đã có tại thời điểm chi",verified_vnd_amount:"Số tiền VND đã xác minh",internal_limit_verification:"Nguồn và hiệu lực xác minh hạn mức nội bộ"};
  const internal={not_configured:"Chưa khai báo",not_exceeded:"Không ghi nhận vượt",not_evaluable:"Chưa đủ dữ kiện để so hạn mức",unverified_limit:"Chưa xác minh",not_known_at_payment:"Chưa có xác minh tại thời điểm chi",outside_effective_period:"Ngoài kỳ hiệu lực",verified_breach:"Đã xác minh vượt hạn mức"};
  const labels={information_request:"Yêu cầu bổ sung bằng chứng",verified_internal_breach:"Vượt hạn mức nội bộ đã xác minh",vat_document_review:"Đối chiếu chứng từ thanh toán/VAT"};
  const amount=proof.currency&&proof.currency!=="VND"?`${number(proof.amount)} · Nguồn ghi ${proof.currency}; chưa xác minh giá trị VND`:money(proof.cash_amount_vnd??proof.amount);
  const facts=[["Nhóm xử lý",labels[proof.review_category]||proof.review_category],["Số tiền chi",amount],["Hóa đơn",proof.invoice_number||proof.invoice_id||"Chưa có thông tin"],["Giá trị hóa đơn",proof.invoice_gross_vnd?money(proof.invoice_gross_vnd):"Chưa có thông tin"],["Hạn mức nội bộ",proof.internal_cash_limit_vnd?money(proof.internal_cash_limit_vnd):"Chưa khai báo"],["Xác minh hạn mức",internal[proof.internal_limit_status]||"Chưa xác minh"]];
  if(proof.vat_non_cash_threshold_vnd)facts.push(["Ngưỡng đối chiếu theo thời điểm",money(proof.vat_non_cash_threshold_vnd)]);
  if(proof.internal_limit_evidence)facts.push(["Nguồn hạn mức",proof.internal_limit_evidence.source_ref],["Người xác minh",proof.internal_limit_evidence.verified_by],["Xác minh lúc",datetime(proof.internal_limit_evidence.verified_at)]);
  return `<div class="source-banner ${proof.review_category==="information_request"?"source-gap":"source-signal"}"><strong>${esc(proof.summary_vi)}</strong></div><div class="evidence-facts">${facts.map(([label,value])=>`<div><span>${esc(label)}</span>${esc(value)}</div>`).join("")}</div>${proof.missing_fields?.length?`<p><strong>Cần bổ sung:</strong> ${proof.missing_fields.map(field=>esc(missing[field]||field)).join("; ")}.</p>`:""}<p>${esc(proof.next_action_vi)}</p><p class="graph-caption">${esc(proof.conclusion)}</p>`;
}
function showModal(title, content) { CaseGraph.dispose("entity-network-graph"); $("modal-title").textContent=title; $("modal-body").innerHTML=content; $("modal").showModal(); }
async function transactionModal(identifier) {
  try {
    const tx=await api("/api/transaction?"+new URLSearchParams({scenario:state.scenario,id:identifier}));
    showModal("Chi tiết nghiệp vụ",`<div class="summary-grid">${[["Mã giao dịch",tx.transaction_id],["Thời điểm",datetime(tx.posted_at)],["Loại",types[tx.txn_type]||tx.txn_type],["Giá trị",money(tx.amount_vnd)],["Nợ / Có",`${tx.debit_account||"—"} / ${tx.credit_account||"—"}`],["Hóa đơn",tx.invoice_number||"—"],["Giá trị hóa đơn",money(tx.invoice_gross_vnd)],["Người lập / duyệt",`${tx.creator_id} / ${tx.approver_id}`],["Người nhận",tx.vendor_id||tx.employee_id||"—"],["Tài khoản thụ hưởng",tx.recipient_account||"Không có chi tiền"],["Hồ sơ hỗ trợ",tx.support_doc_count],["Nội dung",tx.business_purpose]].map(([label,value])=>`<div><span>${label}</span>${esc(value)}</div>`).join("")}</div>${a5Status(tx.a5_evaluation?[tx.a5_evaluation]:[])}`);
  } catch(error){notice(error.message);}
}
function relatedModal(index) {
  const hit=state.detail.hits[index];
  showModal("Giao dịch ngữ cảnh · "+hit.rule_id,`<p>Những giao dịch này có trước dấu hiệu đang được rà soát. Chọn mã để đối chiếu nội dung.</p><div class="data-table-wrap"><table class="data-table"><thead><tr><th>Mã giao dịch</th><th>Tra cứu</th></tr></thead><tbody>${hit.related_transaction_ids.map(id=>`<tr><td>${esc(id)}</td><td><button class="link-button" data-modal-transaction="${esc(id)}">Xem chi tiết →</button></td></tr>`).join("")}</tbody></table></div>`);
  document.querySelectorAll("[data-modal-transaction]").forEach(button=>button.addEventListener("click",()=>{$("modal").close();transactionModal(button.dataset.modalTransaction);}));
}
async function saveFeedback(event) {
  event.preventDefault(); if(feedbackSaving)return; const button=$("save-feedback");
  const scenario=state.scenario, identifier=state.selected;
  const selected=document.querySelector('input[name="decision"]:checked');
  if(!selected || !$("reviewer").value.trim() || !$("reason").value.trim()){notice("Chọn kết luận và nhập người rà soát cùng lý do.");return;}
  const reviewer=$("reviewer").value.trim(), reason=$("reason").value.trim();
  feedbackSaving=true; document.querySelectorAll("#feedback-form button").forEach(b=>b.disabled=true);button.textContent="Đang lưu…";
  try {
    await api("/api/feedback",{scenario,case_id:identifier,decision:selected.value,reviewer,reason,expected_hash:state.detail.case.feedback?.event_hash||""});
    localStorage.setItem("reviewer_name",reviewer);
    if(scenario!==state.scenario||identifier!==state.selected){notice("Đã lưu kết luận cho hồ sơ "+identifier+" ở bộ dữ liệu trước.",true);return;}
    state.detail=await api("/api/case?"+new URLSearchParams({scenario,id:identifier}));
    state.tab="history";renderDetail();await loadQueue();notice("Đã lưu kết luận và lý do vào lịch sử hồ sơ.",true);
  } catch(error){notice(error.message);button.textContent="Lưu kết luận →";}
  finally {feedbackSaving=false;document.querySelectorAll("#feedback-form button").forEach(b=>b.disabled=false);}
}
function showEntityNetwork(network) {
  const scope=network.scope;
  showModal("Mạng lưới thực thể liên quan",`<p class="graph-caption">Quan hệ tại ${esc(datetime(scope.as_of))}. Kéo nút, phóng to hoặc chọn nút/cạnh để xem dữ kiện.</p><button class="icon-button" id="network-fit">Vừa khung</button><div id="entity-network-graph" class="cy-graph cy-network" role="group" aria-label="Mạng lưới sáu loại thực thể"></div><div id="network-node-detail" class="node-detail hidden"></div><p class="graph-caption">${number(scope.returned_nodes)} nút${scope.truncated?` / ${number(scope.candidate_nodes)} nút trong phạm vi · Đã giới hạn sơ đồ`:""}. Quan hệ chung định danh cần đối chiếu nghiệp vụ trước khi kết luận.</p><div class="entity-network-findings">${network.findings.map(f=>`<div class="source-block">${esc({vendor_employee_shared_bank_account:"NCC và nhân viên chung tài khoản",vendor_employee_shared_phone:"NCC và nhân viên chung SĐT",vendors_shared_bank_account:"Các NCC chung tài khoản",vendors_shared_address:"Các NCC chung địa chỉ"}[f.type]||f.type)}<br><strong>${esc(f.vendor_ids.join(", "))}${f.employee_ids.length?" ↔ "+esc(f.employee_ids.join(", ")):""}</strong></div>`).join("")||"Chưa có nhóm trùng định danh đầy đủ trong phạm vi."}</div>`);
  const graph=CaseGraph.mount($("entity-network-graph"),CaseGraph.networkElements(network),$("network-node-detail"),true);
  $("network-fit").addEventListener("click",()=>graph?.fit(undefined,35));
}
function drawGraph(data) {
  const container=$("relationship-graph"), model=CaseGraph.evidenceElements(data);
  const graph=CaseGraph.mount(container,model.elements,$("node-detail"));
  $("zoom-in").onclick=()=>{if(graph)graph.zoom(graph.zoom()*1.2);};
  $("zoom-out").onclick=()=>{if(graph)graph.zoom(graph.zoom()/1.2);};
  $("zoom-reset").onclick=()=>graph?.fit(undefined,35);
  if(model.total>model.shown)$("graph-caption").textContent=`Hiển thị ${model.shown}/${model.total} nút; xem đầy đủ trong phần Giao dịch và Bằng chứng.`;
  if(data.entity_network?.nodes.length){const action=document.createElement("button");action.className="link-button entity-network-action";action.textContent="Mở mạng lưới thực thể liên quan →";action.addEventListener("click",()=>showEntityNetwork(data.entity_network));container.parentElement.append(action);}
}
const notificationStatuses={pending:"Chờ gửi",sending:"Đang xử lý",simulated:"Đã giả lập",sent:"Đã nhận bởi dịch vụ",failed:"Cần xử lý lỗi",uncertain:"Chưa rõ kết quả",cancelled:"Đã hủy"};
function notificationJob(job) {
  const body=job.preview_body??job.body,links=new Set((job.case_links||[]).map(link=>link.url));
  const content=body.split(/(https?:\/\/[^\s]+)/g).map(part=>links.has(part)?`<a href="${esc(part)}">${esc(part)}</a>`:esc(part)).join("");
  const historical=body!==job.body?`<p class="graph-caption">Bản xem trước dùng URL hiện tại. Nội dung đã mô phỏng được giữ trong lịch sử bên dưới.</p>`:"";
  return `<article class="notification-job"><div class="case-top"><strong>${esc(job.company_id)} · ${job.channel==="email"?"Email":"Zalo OA"} · ${job.kind==="weekly"?"Tóm tắt tuần":"Ưu tiên cao"}</strong><span>${esc(notificationStatuses[job.status]||job.status)}</span></div>${historical}<pre>${content}</pre>${body!==job.body?`<details><summary>Nội dung đã mô phỏng trước đây · ${esc(datetime(job.created_at))}</summary><pre>${esc(job.body)}</pre></details>`:""}${job.error_code?`<p>${esc(job.error_code)}</p>`:""}</article>`;
}
async function notificationsModal(run=false) {
  try {
    const result=run?await api("/api/notifications/preview",{scenario:state.scenario}):await api("/api/notifications?scenario="+state.scenario);
    showModal("Thông báo Zalo / Email",`<div class="integrity">${result.mode==="dry_run"?"GIẢ LẬP · Không gửi ra ngoài":"Worker gửi thật được cấu hình riêng"}</div><p>Tối đa ${result.daily_case_limit} hồ sơ / công ty / ngày, dùng chung cho hai kênh và tóm tắt tuần. Đã chọn hôm nay: ${esc(Object.entries(result.used_by_company).map(([c,n])=>c+": "+n).join(" · ")||"0")}.</p><p>Tóm tắt tuần từ thứ ${result.weekly_weekday===6?"Chủ nhật":result.weekly_weekday+2}, ${result.weekly_hour}:00 (giờ Việt Nam). Hồ sơ đóng được loại trước lúc gửi.</p><p>${esc(Object.entries(result.counts).map(([status,count])=>(notificationStatuses[status]||status)+": "+count).join(" · "))}</p>${result.mode==="dry_run"?'<button id="notification-preview" class="primary-button">Chạy luồng giả lập</button>':""}<div class="notification-jobs">${result.items.map(notificationJob).join("")||'<p class="graph-caption">Chưa có thông báo. Chạy giả lập để xem luồng từ hồ sơ đang mở.</p>'}</div>`);
    $("modal-body").querySelectorAll(".notification-job a").forEach(link=>link.addEventListener("click",()=>$("modal").close()));
    $("notification-preview")?.addEventListener("click",async()=>{$("notification-preview").disabled=true;await notificationsModal(true);});
  } catch(error){notice(error.message);}
}
async function coverageModal(){try{const [coverage,a5]=await Promise.all([api("/api/coverage?scenario="+state.scenario),api("/api/a5-coverage?scenario="+state.scenario)]);showModal("Phạm vi các quy tắc",`${a5CoverageSummary(a5)}<p>Một số quy tắc chưa đủ nguồn để đánh giá. Không có dữ liệu không đồng nghĩa với không có vi phạm.</p>${coverage.map(row=>`<div class="coverage-item"><span class="coverage-status">${{implemented:"Đã triển khai",partial:"Có giới hạn",not_evaluable:"Thiếu dữ liệu"}[row.status]}</span><strong>${esc(row.rule_id)} · ${esc(row.name)}</strong><small>${esc(row.note|| (row.scope==="aggregate_diagnostic"?"Chẩn đoán theo tập giao dịch, không cộng điểm từng giao dịch.":"Đánh giá từ thông tin đã biết tại thời điểm nghiệp vụ."))}</small></div>`).join("")}`);}catch(error){notice(error.message);}}
async function boot(){try{state.meta=await api("/api/meta");$("p2-controls-nav")?.classList.toggle("hidden",!state.meta.p2_controls_available);state.scenario=state.meta.default_scenario;$("scenario").innerHTML=state.meta.scenarios.map(tag=>`<option value="${tag}">Mô phỏng ${(Number(tag)/10).toLocaleString("vi-VN")}%</option>`).join("");$("scenario").value=state.scenario;$("budget").value=state.meta.daily_budget;$("company").innerHTML='<option value="">Tất cả công ty</option>'+state.meta.companies.map(row=>`<option value="${esc(row.company_id)}">${esc(row.company_id)} · ${esc(row.name)}</option>`).join("");$("environment-label").textContent=state.meta.qa?"KIỂM THỬ GIAO DIỆN":"Dữ liệu mô phỏng · 2024–2025";state.coverage=await api("/api/coverage?scenario="+state.scenario);$("rule").innerHTML='<option value="">Mọi quy tắc</option>'+state.coverage.filter(row=>["transaction","source_diagnostic"].includes(row.scope)&&row.status!=="not_evaluable"&&row.scoring_role!=="master_quality").map(row=>`<option value="${esc(row.rule_id)}">${esc(row.rule_id)} · ${esc(row.name)}</option>`).join("");caseRouteReady=true;await applyCaseLocation(true);}catch(error){notice(error.message);$("case-list").innerHTML='<div class="empty-state">Chưa nạp được hàng đợi. Kiểm tra thông báo phía trên và thử Làm mới.</div>';}}
$("scenario").addEventListener("change",()=>{writeCaseLocation($("scenario").value,null);return applyCaseLocation();});
window.addEventListener("hashchange",()=>applyCaseLocation());
window.addEventListener("popstate",()=>applyCaseLocation());
for(const id of ["company","status","priority","category","rule","daily-only"])$(id).addEventListener("change",()=>{if(id==="category"&&$(id).value==="information_request")$("daily-only").checked=false;state.offset=0;loadQueue();});
let searchTimer;$("search").addEventListener("input",()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>{state.offset=0;loadQueue();},200);});
$("previous").addEventListener("click",()=>{state.offset=Math.max(0,state.offset-state.limit);loadQueue();});$("next").addEventListener("click",()=>{state.offset+=state.limit;loadQueue();});$("refresh").addEventListener("click",async()=>{hideNotice();await loadQueue();if(state.selected)try{const scenario=state.scenario,identifier=state.selected;const detail=await api("/api/case?"+new URLSearchParams({scenario,id:identifier}));if(scenario===state.scenario&&identifier===state.selected){state.detail=detail;renderDetail();}}catch(error){notice(error.message);}});
$("budget").addEventListener("change",async()=>{try{const changed=await api("/api/budget",{daily_budget:Number($("budget").value)});await loadQueue();notice(`Đã cập nhật ngân sách: ${changed.daily_budget} lượt / ${changed.daily_capacity_minutes} phút cho mỗi công ty mỗi ngày. Phân bổ hôm nay được giữ lại.`,true);}catch(error){notice(error.message);}});
$("export").addEventListener("click",()=>{const query=params();query.delete("offset");query.delete("limit");window.location.href="/api/export?"+query;});
$("notifications-nav").addEventListener("click",()=>notificationsModal());
$("notifications-mobile").addEventListener("click",()=>notificationsModal());
$("coverage-nav").addEventListener("click",coverageModal);$("help-nav").addEventListener("click",()=>showModal("Cách rà soát một hồ sơ","<p><strong>1. Chọn hồ sơ ưu tiên.</strong> Hàng đợi gồm cảnh báo giao dịch và hồ sơ nguồn F3/F4. Hạn mức đồng thời theo số lượt và tổng phút cho từng công ty mỗi ngày.</p><p><strong>2. Đối chiếu bằng chứng.</strong> Với F3, kiểm sổ đăng ký, dải số và nhật ký hủy. Với F4, kiểm hóa đơn, thu tiền, phân bổ, coverage và giải trình công nợ. Hồ sơ giao dịch tiếp tục hiển thị định khoản và sơ đồ quan hệ.</p><p><strong>3. Ghi nhận kết luận.</strong> Chọn Cần bổ sung nếu nguồn chưa đủ; hồ sơ tiếp tục nằm trong tồn đọng và lần mở ngày sau được tính là tái rà soát. Các kết luận còn lại đóng hồ sơ nhưng vẫn đọc được.</p><p>Đây là bản thử nội bộ trên dữ liệu tổng hợp 2024–2025; có luồng thông báo Zalo/Email ở chế độ giả lập. Xem mục Thông báo để kiểm tra; không gửi dữ liệu ra ngoài.</p>"));
$("queue-nav").addEventListener("click",()=>{state.offset=0;loadQueue();});$("modal-close").addEventListener("click",()=>$("modal").close());$("modal").addEventListener("close",()=>CaseGraph.dispose("entity-network-graph"));
boot();
