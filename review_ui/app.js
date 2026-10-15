"use strict";
const $ = (id) => document.getElementById(id);
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const money = value => new Intl.NumberFormat("vi-VN", {maximumFractionDigits:0}).format(Number(value || 0)) + " ₫";
const number = value => new Intl.NumberFormat("vi-VN").format(Number(value || 0));
const date = value => value ? new Date(value).toLocaleDateString("vi-VN", {timeZone:"Asia/Ho_Chi_Minh"}) : "—";
const datetime = value => value ? new Date(value).toLocaleString("vi-VN", {timeZone:"Asia/Ho_Chi_Minh", hour:"2-digit", minute:"2-digit", day:"2-digit", month:"2-digit", year:"numeric"}) : "—";
const priorities = {cao_nhat:"Cao nhất", cao:"Cao", trung_binh:"Trung bình", thap:"Thấp"};
const statuses = {new:"Chưa rà soát", awaiting_information:"Chờ bổ sung", closed:"Đã kết luận"};
const decisions = {false_positive:"Hợp lệ / báo động giả", information_gap:"Cần bổ sung bằng chứng", non_compliance:"Vi phạm kiểm soát", confirmed_fraud:"Xác nhận gian lận"};
const types = {vendor_payment:"Thanh toán NCC", payroll:"Chi lương", advance_review:"Rà soát số dư tạm ứng", advance_writeoff:"Xóa nợ tạm ứng", adjustment:"Điều chỉnh", advance_issue:"Chi tạm ứng", advance_settlement:"Hoàn ứng"};
const fields = {count:"Số lần",total_vnd:"Tổng giá trị",approval_limit_vnd:"Hạn mức duyệt",window_days:"Cửa sổ (ngày)",invoice_number:"Số hóa đơn",invoice_gross_vnd:"Giá trị hóa đơn",cumulative_paid_vnd:"Tổng đã thanh toán",excess_vnd:"Phần thanh toán vượt",employee_ids:"Nhân viên liên quan",recipient_account:"Tài khoản thụ hưởng",related_party_disclosed:"Đã công bố bên liên quan",field_count:"Số trường trùng",vendor_age_days:"Tuổi NCC (ngày)",amount_vnd:"Giá trị nghiệp vụ",risky_at_invoice:"Rủi ro ngày phát hành",registry_risky_now:"Rủi ro ngày thanh toán",invoice_issued_at:"Ngày phát hành",change_id:"Mã thay đổi",effective_at:"Thời điểm hiệu lực",verified_at:"Thời điểm xác minh",approver_id:"Người duyệt",created_at:"Thời điểm lập",approved_at:"Thời điểm duyệt",saturday_operations:"Có vận hành thứ Bảy",self_approval_limit_vnd:"Hạn mức tự duyệt",approval_seconds:"Thời gian duyệt (giây)",payroll_period:"Kỳ lương",attendance_days:"Ngày công quan sát",alternative_work_evidence:"Bằng chứng thay chấm công",employee_id:"Nhân viên",recipient_employee_bank_count:"Nhân viên cùng tài khoản",days_before_close:"Ngày trước khóa sổ",materiality_vnd:"Mức trọng yếu",advance_id:"Mã tạm ứng",overdue_days:"Số ngày quá hạn",open_fraction:"Tỷ lệ dư nợ",extension_known:"Đã có gia hạn",evidence_on_file:"Có hồ sơ đối chiếu",prior_balance_fraction:"Tỷ lệ dư nợ trước sự kiện",baseline_rows:"Số mẫu lịch sử",baseline_mean_vnd:"Trung bình lịch sử",baseline_sd_vnd:"Độ lệch chuẩn",z:"Độ lệch so với lịch sử",direct_matches:"Thông tin trùng trực tiếp",vendor_ids:"NCC liên quan",shared_fields:"Trường định danh chung",matched_vendor_count:"Tên NCC tương tự",idle_days:"Ngày không giao dịch",prior_p90_vnd:"Phân vị 90 lịch sử"};
let state = {scenario:"003", offset:0, limit:20, selected:null, tab:"overview", meta:null, detail:null, request:0, coverage:[]};
let openGeneration=0;

async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {method:"POST", headers:{"Content-Type":"application/json", "X-CSRF-Token":state.meta.csrf_token}, body:JSON.stringify(body)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Chưa thực hiện được thao tác.");
  return result;
}
function notice(message, success=false) { $("notice").textContent=message; $("notice").className="notice"+(success?" success":""); }
function hideNotice() { $("notice").className="notice hidden"; }
function params() { return new URLSearchParams({scenario:state.scenario,company:$("company").value,status:$("status").value,priority:$("priority").value,rule:$("rule").value,q:$("search").value,offset:state.offset,limit:state.limit}); }
function headline(row) {
  const rules = row.rule_ids;
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
  return "Nghiệp vụ cần đối chiếu bổ sung";
}
async function loadQueue() {
  const request = ++state.request;
  try {
    const result = await api("/api/cases?"+params());
    if(request!==state.request) return;
    $("stat-new").textContent=number(result.counts.new);
    $("stat-high").textContent=number(result.counts.high_priority);
    $("stat-gap").textContent=number(result.counts.awaiting_information);
    $("stat-closed").textContent=number(result.counts.closed);
    $("queue-total").textContent=number(result.total);
    $("queue-note").textContent=`Ưu tiên theo mức rủi ro, điểm và ngày mở. Mỗi công ty tối đa ${result.budget.limit} hồ sơ mới/ngày.`;
    $("case-list").innerHTML=result.items.length ? result.items.map(row=>`<button class="case-card ${row.case_id===state.selected?"selected":""}" data-case="${esc(row.case_id)}" aria-pressed="${row.case_id===state.selected}"><div class="case-top"><span class="chip priority-${esc(row.priority)}">● ${esc(priorities[row.priority])}</span><span class="score">${row.max_score}<small>điểm</small></span></div><div class="case-title">${esc(headline(row))}</div><div class="case-sub">${esc(row.company_id)} · ${row.observation_count} nghiệp vụ · ${esc(statuses[row.status])}</div><div class="case-bottom"><div>${row.rule_ids.slice(0,3).map(code=>`<span class="rule-tag">${esc(code)}</span>`).join("")}${row.rule_ids.length>3?`<span class="rule-tag">+${row.rule_ids.length-3}</span>`:""}</div><span class="case-time">${date(row.opened_at)}</span></div><div class="case-bottom"><span class="case-code">${esc(row.case_id)}</span>${row.admitted_today?'<span class="admitted-label">Đã mở hôm nay ✓</span>':""}</div></button>`).join("") : '<div class="empty-state">Không có hồ sơ phù hợp bộ lọc.<br>Thử đổi trạng thái hoặc nội dung tìm kiếm.</div>';
    $("page-range").textContent=result.total ? `${state.offset+1}–${Math.min(state.offset+state.limit,result.total)} / ${number(result.total)} hồ sơ` : "0 hồ sơ";
    $("previous").disabled=state.offset===0;
    $("next").disabled=state.offset+state.limit>=result.total;
    document.querySelectorAll("[data-case]").forEach(button=>button.addEventListener("click",()=>openCase(button.dataset.case)));
  } catch(error) { if(request!==state.request)return;notice(error.message);$("case-list").innerHTML='<div class="empty-state">Không thể đọc hàng đợi. Kiểm tra thông báo và thử lại.</div>';for(const id of ["stat-new","stat-high","stat-gap","stat-closed"])$(id).textContent="—";$("queue-total").textContent="—";$("previous").disabled=true;$("next").disabled=true;state.selected=null;state.detail=null;$("detail-panel").innerHTML='<div class="detail-placeholder"><h2>Tạm dừng rà soát</h2><p>Chưa đọc được dữ liệu hoặc nhật ký. Tải lại sau khi đã kiểm tra thông báo.</p></div>'; }
}
async function openCase(identifier) {
  const scenario=state.scenario, request=++openGeneration;
  try {
    hideNotice();
    await api("/api/admit",{scenario,case_id:identifier});
    const detail=await api("/api/case?"+new URLSearchParams({scenario,id:identifier}));
    if(request!==openGeneration||scenario!==state.scenario)return;
    state.selected=identifier; state.detail=detail; state.tab="overview";
    renderDetail(); await loadQueue();
    if(window.innerWidth<820) $("detail-panel").scrollIntoView({behavior:"smooth",block:"start"});
  } catch(error) { if(request===openGeneration&&scenario===state.scenario)notice(error.message); }
}
function renderDetail() {
  const data=state.detail, row=data.case;
  const paid=data.transactions.filter(tx=>Number(tx.is_financial_entry)===1 && ["bank","cash"].includes(tx.payment_channel) && tx.txn_type!=="customer_receipt").reduce((sum,tx)=>sum+tx.amount_vnd,0);
  $("detail-panel").innerHTML=`<div class="detail-header"><div class="detail-overline"><span class="chip priority-${esc(row.priority)}">● Ưu tiên ${esc(priorities[row.priority].toLowerCase())}</span><span class="detail-id">${esc(row.case_id)}</span></div><h2>${esc(headline(row))}</h2><div class="detail-meta"><span>${esc(row.company_id)} · ${row.observation_count} nghiệp vụ</span><span>Mở ${date(row.opened_at)}</span><span>${esc(statuses[row.status])}</span></div><div class="detail-score"><div class="score-circle">${row.max_score}</div><div class="score-caption">Điểm ưu tiên rà soát<br><strong>${paid?"Chi trả trong hồ sơ: "+money(paid):"Chủ yếu là bút toán hoặc rà soát số dư"}</strong></div></div></div><nav class="detail-tabs" aria-label="Các phần hồ sơ">${[["overview","Tổng quan"],["transactions","Giao dịch"],["evidence","Bằng chứng"],["history","Nhật ký"]].map(([id,label])=>`<button data-tab="${id}" class="${state.tab===id?"active":""}">${label}</button>`).join("")}</nav><div class="detail-content" id="detail-content"></div><form id="feedback-form" class="feedback-form"><h3>Ghi nhận kết luận rà soát</h3><div class="form-note">Lưu kết luận sau khi đối chiếu. Phần còn thiếu có thể tiếp tục bổ sung ở lần rà soát sau.</div><div class="decision-options">${Object.entries(decisions).map(([value,label])=>`<label><input type="radio" name="decision" value="${value}" required ${row.feedback?.decision===value?"checked":""}>${label}</label>`).join("")}</div><label class="field">Người rà soát<input type="text" id="reviewer" maxlength="100" required placeholder="Họ và tên người thực hiện" value="${esc(localStorage.getItem("reviewer_name")||"")}"></label><label class="field">Lý do / chứng từ đã đối chiếu<textarea id="reason" maxlength="2000" rows="3" required placeholder="Nêu nội dung đã kiểm tra hoặc bằng chứng cần bổ sung…"></textarea></label><div class="form-bottom"><span class="save-note">Mỗi lần lưu được ghi vào lịch sử.<br>Hồ sơ thiếu bằng chứng tiếp tục mở.</span><button type="submit" class="primary-button" id="save-feedback">Lưu kết luận →</button></div></form>`;
  document.querySelectorAll("[data-tab]").forEach(button=>button.addEventListener("click",()=>{state.tab=button.dataset.tab; document.querySelectorAll("[data-tab]").forEach(b=>b.classList.toggle("active",b.dataset.tab===state.tab)); renderTab();}));
  $("feedback-form").addEventListener("submit",saveFeedback);
  renderTab();
}
function renderTab() {
  const data=state.detail, container=$("detail-content");
  if(state.tab==="overview") {
    const unique=[]; const seen=new Set();
    for(const hit of data.hits) if(hit.points>0&&!seen.has(hit.rule_id)){unique.push(hit);seen.add(hit.rule_id);}
    container.innerHTML=`<div class="detail-context">${esc(data.case.explanation_vi)}.</div><div class="graph-toolbar"><div class="section-label">Quan hệ cần đối chiếu</div><div class="graph-actions"><button class="icon-button" id="zoom-out" aria-label="Thu nhỏ sơ đồ">−</button><button class="icon-button" id="zoom-in" aria-label="Phóng to sơ đồ">+</button><button class="icon-button" id="zoom-reset">Đặt lại</button></div></div><div class="graph-wrap"><svg id="relationship-graph" viewBox="0 0 640 280" role="group" aria-label="Sơ đồ quan hệ của hồ sơ"></svg><div class="graph-legend"><span><i class="legend-vendor"></i>Đối tác / nghiệp vụ</span><span><i class="legend-bank"></i>TK / SĐT</span><span><i class="legend-employee"></i>Nhân sự</span></div></div><div class="graph-caption" id="graph-caption">Chọn một nút để xem chi tiết. Có thể phóng to và kéo sơ đồ.</div><div id="node-detail" class="node-detail hidden"></div><div class="section-label">Bằng chứng chính</div>${unique.slice(0,3).map(h=>evidenceCard(h,true)).join("")}<button class="text-button" id="all-evidence">Xem toàn bộ ${data.hits.length} dấu hiệu và ngoại lệ →</button>`;
    $("all-evidence").addEventListener("click",()=>{state.tab="evidence";document.querySelectorAll("[data-tab]").forEach(b=>b.classList.toggle("active",b.dataset.tab===state.tab));renderTab();});
    drawGraph(data);
  } else if(state.tab==="transactions") {
    container.innerHTML=`<div class="section-label">${data.transactions.length} nghiệp vụ trong hồ sơ</div><div class="data-table-wrap"><table class="data-table"><thead><tr><th>Ngày / nghiệp vụ</th><th>Giá trị</th><th>Nợ / Có</th><th>Chi tiết</th></tr></thead><tbody>${data.transactions.map(tx=>`<tr><td>${date(tx.posted_at)}<br>${esc(types[tx.txn_type]||tx.txn_type)}</td><td class="amount">${money(tx.amount_vnd)}</td><td>${esc(tx.debit_account||"—")} / ${esc(tx.credit_account||"—")}</td><td><button class="link-button" data-transaction="${esc(tx.transaction_id)}">${esc(tx.transaction_id)}</button></td></tr>`).join("")}</tbody></table></div><div class="section-label">Chứng từ kế toán liên quan</div>${data.documents.map(item=>`<div class="document-title">${esc(item.document.document_id)} · ${esc(item.document.purpose)} · ${date(item.document.posted_at)}</div><div class="data-table-wrap"><table class="data-table"><thead><tr><th>Tài khoản</th><th>Nợ</th><th>Có</th></tr></thead><tbody>${item.lines.map(line=>`<tr><td>${esc(line.account_code)}</td><td class="amount">${money(line.debit_vnd)}</td><td class="amount">${money(line.credit_vnd)}</td></tr>`).join("")}</tbody></table></div>`).join("")||'<p class="graph-caption">Sự kiện rà soát số dư có thể không phát sinh bút toán.</p>'}`;
  } else if(state.tab==="evidence") {
    container.innerHTML=`<div class="section-label">Dấu hiệu đã ghi nhận tại thời điểm giao dịch</div><div class="graph-caption">Mỗi dấu hiệu có dữ kiện và giao dịch ngữ cảnh riêng. Ngoại lệ không đóng góp điểm.</div>${data.hits.map(h=>evidenceCard(h,false)).join("")}`;
  } else {
    container.innerHTML=`<div class="integrity">✓ Nhật ký kết luận đã kiểm tra tính liên tục.</div><div class="section-label">Kết luận của người rà soát</div>${data.feedback_history.length?data.feedback_history.slice().reverse().map(event=>`<div class="timeline-entry"><strong>${esc(decisions[event.decision])}</strong>${esc(event.reason)}<br><small>${esc(event.reviewer)} · ${datetime(event.reviewed_at)}</small></div>`).join(""):'<div class="graph-caption">Hồ sơ chưa có kết luận của người rà soát.</div>'}<div class="section-label">Lịch sử cảnh báo mô phỏng</div>${data.case_events.map(event=>`<div class="timeline-entry"><strong>${event.event==="opened"?"Mở hồ sơ":"Nâng mức ưu tiên"}</strong>Ưu tiên ${esc(priorities[event.priority])} · ${event.rule_score} điểm<br><small>${datetime(event.event_at)} · ${esc(event.transaction_id)}</small></div>`).join("")}<div class="graph-caption">Hạn rà soát gợi ý từ snapshot: ${datetime(data.case.sla_due_at)}. Đây là lịch của dữ liệu mô phỏng.</div>`;
  }
  container.querySelectorAll("[data-related]").forEach(button=>button.addEventListener("click",()=>relatedModal(Number(button.dataset.related))));
  container.querySelectorAll("[data-transaction]").forEach(button=>button.addEventListener("click",()=>transactionModal(button.dataset.transaction)));
}
function factValue(key,value) {
  if(key.endsWith("_vnd")) return money(value);
  if(key.endsWith("_at")) return datetime(value);
  if(typeof value==="object") return Array.isArray(value)?value.slice(0,5).join(", ")+(value.length>5?`… (${value.length})`:""):Object.entries(value).map(([k,v])=>`${k}: ${Array.isArray(v)?v.join(", "):v}`).join("; ");
  if(["open_fraction","prior_balance_fraction"].includes(key)) return `${Math.round(value*100)}%`;
  return String(value);
}
function evidenceCard(hit, open) {
  const index=state.detail.hits.indexOf(hit);
  const known=Object.entries(hit.evidence).filter(([key])=>fields[key]).slice(0,8);
  return `<details class="evidence-card" ${open?"open":""}><summary><span class="evidence-head"><span class="rule-tag">${esc(hit.rule_id)}</span>${esc(hit.rule_name)} <span class="evidence-points">${hit.points>0?"+"+hit.points+" điểm":"Ngoại lệ / thông tin"}</span></span></summary><div class="evidence-body">${hit.suppressed_reason?`<div class="suppression">✓ ${esc(hit.suppressed_reason)}</div>`:""}<div class="evidence-facts">${known.map(([key,value])=>`<div><span>${esc(fields[key])}</span>${esc(factValue(key,value))}</div>`).join("")}</div><div class="graph-caption">${datetime(hit.detected_at)} · ${esc(hit.transaction_id)}</div>${hit.related_transaction_ids.length?`<button class="link-button" data-related="${index}">Đối chiếu ${hit.related_transaction_ids.length} giao dịch ngữ cảnh →</button>`:""}</div></details>`;
}
function showModal(title, content) { $("modal-title").textContent=title; $("modal-body").innerHTML=content; $("modal").showModal(); }
async function transactionModal(identifier) {
  try {
    const tx=await api("/api/transaction?"+new URLSearchParams({scenario:state.scenario,id:identifier}));
    showModal("Chi tiết nghiệp vụ",`<div class="summary-grid">${[["Mã giao dịch",tx.transaction_id],["Thời điểm",datetime(tx.posted_at)],["Loại",types[tx.txn_type]||tx.txn_type],["Giá trị",money(tx.amount_vnd)],["Nợ / Có",`${tx.debit_account||"—"} / ${tx.credit_account||"—"}`],["Hóa đơn",tx.invoice_number||"—"],["Giá trị hóa đơn",money(tx.invoice_gross_vnd)],["Người lập / duyệt",`${tx.creator_id} / ${tx.approver_id}`],["Người nhận",tx.vendor_id||tx.employee_id||"—"],["Tài khoản thụ hưởng",tx.recipient_account||"Không có chi tiền"],["Hồ sơ hỗ trợ",tx.support_doc_count],["Nội dung",tx.business_purpose]].map(([label,value])=>`<div><span>${label}</span>${esc(value)}</div>`).join("")}</div>`);
  } catch(error){notice(error.message);}
}
function relatedModal(index) {
  const hit=state.detail.hits[index];
  showModal("Giao dịch ngữ cảnh · "+hit.rule_id,`<p>Những giao dịch này có trước dấu hiệu đang được rà soát. Chọn mã để đối chiếu nội dung.</p><div class="data-table-wrap"><table class="data-table"><thead><tr><th>Mã giao dịch</th><th>Tra cứu</th></tr></thead><tbody>${hit.related_transaction_ids.map(id=>`<tr><td>${esc(id)}</td><td><button class="link-button" data-modal-transaction="${esc(id)}">Xem chi tiết →</button></td></tr>`).join("")}</tbody></table></div>`);
  document.querySelectorAll("[data-modal-transaction]").forEach(button=>button.addEventListener("click",()=>{$("modal").close();transactionModal(button.dataset.modalTransaction);}));
}
async function saveFeedback(event) {
  event.preventDefault(); const button=$("save-feedback");
  const scenario=state.scenario, identifier=state.selected;
  const selected=document.querySelector('input[name="decision"]:checked');
  if(!selected || !$("reviewer").value.trim() || !$("reason").value.trim()){notice("Chọn kết luận và nhập người rà soát cùng lý do.");return;}
  const reviewer=$("reviewer").value.trim(), reason=$("reason").value.trim();
  button.disabled=true;button.textContent="Đang lưu…";
  try {
    await api("/api/feedback",{scenario,case_id:identifier,decision:selected.value,reviewer,reason,expected_hash:state.detail.case.feedback?.event_hash||""});
    localStorage.setItem("reviewer_name",reviewer);
    if(scenario!==state.scenario||identifier!==state.selected){notice("Đã lưu kết luận cho hồ sơ "+identifier+" ở bộ dữ liệu trước.",true);return;}
    state.detail=await api("/api/case?"+new URLSearchParams({scenario,id:identifier}));
    state.tab="history";renderDetail();await loadQueue();notice("Đã lưu kết luận và lý do vào lịch sử hồ sơ.",true);
  } catch(error){notice(error.message);button.disabled=false;button.textContent="Lưu kết luận →";}
}
function drawGraph(data) {
  const svg=$("relationship-graph"), ns="http://www.w3.org/2000/svg", nodes=new Map(), edges=[];
  function addNode(id,kind,label,info="") {if(!nodes.has(id)) nodes.set(id,{id,kind,label,info});}
  function entityNode(id) {
    const kind=id.split(":")[0], raw=id.slice(kind.length+1), known=data.entities[raw];
    const resolved=known ? (known.vendor_id?"vendor":"employee") : kind==="bank_account"?"bank":kind==="phone"?"phone":"representative";
    addNode(id,resolved, known?(known.name||known.full_name):resolved==="bank"?"TK · "+raw.slice(-8):resolved==="phone"?"SĐT · "+raw.slice(-8):raw,
            known?`${known.vendor_id||known.employee_id} · ${known.name||known.full_name}`:raw);
  }
  const uniqueEdges=new Set();
  for(const edge of data.graph_edges) {
    const key=[edge.source,edge.target].sort().join("|"); if(uniqueEdges.has(key))continue;uniqueEdges.add(key);
    entityNode(edge.source);entityNode(edge.target);edges.push({source:edge.source,target:edge.target,label:edge.link_type==="representative"?"Đại diện":edge.link_type==="phone"?"Cùng SĐT":"Cùng tài khoản",info:"Đã quan sát "+datetime(edge.observed_at)});
  }
  if(!edges.length) for(const tx of data.transactions.slice(0,6)) {
    const tid="transaction:"+tx.transaction_id;addNode(tid,"transaction",tx.transaction_id,`${date(tx.posted_at)} · ${money(tx.amount_vnd)} · ${types[tx.txn_type]||tx.txn_type}`);
    const recipient=tx.vendor_id||tx.employee_id;
    if(recipient){const recipientNode="entity:"+recipient;entityNode(recipientNode);edges.push({source:tid,target:recipientNode,label:Number(tx.is_financial_entry)&&tx.recipient_account?"Chi cho":"Đối tượng"});
      if(tx.recipient_account){const bank="bank_account:"+tx.recipient_account;addNode(bank,"bank","TK · "+tx.recipient_account.slice(-8),tx.recipient_account);edges.push({source:recipientNode,target:bank,label:"Thụ hưởng"});
        if(tx.employee_id)for(const entity of Object.values(data.entities))if(entity.employee_id&&entity.employee_id!==tx.employee_id&&entity.bank_account===tx.recipient_account&&entity.recorded_at<=tx.posted_at){const shared="entity:"+entity.employee_id;entityNode(shared);edges.push({source:shared,target:bank,label:"Cùng tài khoản"});}
      }
    }else{const maker="entity:"+tx.creator_id;entityNode(maker);edges.push({source:maker,target:tid,label:"Người lập"});}
  }
  const visible=[...nodes.values()].slice(0,18), columns={transaction:0,vendor:1,representative:1,bank:2,phone:2,employee:3}, grouped=[[],[],[],[]];
  for(const node of visible)grouped[columns[node.kind]??1].push(node);
  const used=grouped.map((group,index)=>group.length?index:null).filter(x=>x!==null);
  const maxRows=Math.max(...grouped.map(group=>group.length),1), height=Math.max(280,maxRows*67+50);
  svg.setAttribute("viewBox",`0 0 640 ${height}`);
  if(maxRows>3)svg.classList.add("graph-tall");
  used.forEach((column,index)=>grouped[column].forEach((node,row)=>{node.x=used.length===1?320:80+index*480/(used.length-1);node.y=height/2+(row-(grouped[column].length-1)/2)*67;}));
  const viewport=document.createElementNS(ns,"g");svg.appendChild(viewport);
  const colors={vendor:["#eef2ff","#647ccb"],employee:["#edf6f2","#76a98e"],bank:["#fff5e5","#c9a46a"],phone:["#fff5e5","#c9a46a"],representative:["#f4effa","#a18dbb"],transaction:["#f1f5fc","#8399ba"]};
  for(const edge of edges){const left=visible.find(n=>n.id===edge.source),right=visible.find(n=>n.id===edge.target);if(!left||!right)continue;
    const line=document.createElementNS(ns,"path"), middle=(left.x+right.x)/2;
    line.setAttribute("d",`M${left.x} ${left.y} C${middle} ${left.y} ${middle} ${right.y} ${right.x} ${right.y}`);line.setAttribute("stroke","#d6deed");line.setAttribute("stroke-width","1.5");line.setAttribute("fill","none");viewport.appendChild(line);
    const title=document.createElementNS(ns,"title");title.textContent=edge.label+(edge.info?" · "+edge.info:"");line.appendChild(title);
  }
  for(const node of visible){const group=document.createElementNS(ns,"g");group.setAttribute("transform",`translate(${node.x},${node.y})`);group.setAttribute("tabindex","0");group.setAttribute("role","button");group.setAttribute("aria-label",node.label);
    const rect=document.createElementNS(ns,"rect");rect.setAttribute("x","-65");rect.setAttribute("y","-21");rect.setAttribute("width","130");rect.setAttribute("height","42");rect.setAttribute("rx","7");rect.setAttribute("fill",colors[node.kind][0]);rect.setAttribute("stroke",colors[node.kind][1]);rect.setAttribute("stroke-opacity",".45");group.appendChild(rect);
    const text=document.createElementNS(ns,"text");text.setAttribute("text-anchor","middle");text.setAttribute("font-size","14");text.setAttribute("fill","#526987");text.setAttribute("dy","4");text.textContent=node.label.length>16?node.label.slice(0,15)+"…":node.label;group.appendChild(text);
    const title=document.createElementNS(ns,"title");title.textContent=node.info||node.label;group.appendChild(title);
    function select(){ $("node-detail").textContent=node.info||node.label;$("node-detail").classList.remove("hidden"); }
    group.addEventListener("click",select);group.addEventListener("keydown",event=>{if(event.key==="Enter"||event.key===" "){event.preventDefault();select();}});viewport.appendChild(group);
  }
  if(nodes.size>visible.length)$("graph-caption").textContent=`Sơ đồ hiển thị ${visible.length}/${nodes.size} nút. Các giao dịch đầy đủ nằm ở phần Giao dịch và Bằng chứng.`;
  let zoom=1, pan={x:0,y:0}, drag=null;
  const transform=()=>viewport.setAttribute("transform",`translate(${pan.x},${pan.y}) scale(${zoom})`);
  function changeZoom(factor){zoom=Math.max(.6,Math.min(2.5,zoom*factor));transform();}
  $("zoom-in").addEventListener("click",()=>changeZoom(1.15));$("zoom-out").addEventListener("click",()=>changeZoom(1/1.15));$("zoom-reset").addEventListener("click",()=>{zoom=1;pan={x:0,y:0};transform();});
  svg.addEventListener("wheel",event=>{event.preventDefault();changeZoom(event.deltaY<0?1.07:1/1.07);},{passive:false});
  svg.addEventListener("pointerdown",event=>{if(event.target.closest('[role="button"]'))return;drag={x:event.clientX,y:event.clientY,start:{...pan}};svg.setPointerCapture(event.pointerId);});
  svg.addEventListener("pointermove",event=>{if(drag){const scale=640/svg.getBoundingClientRect().width;pan={x:drag.start.x+(event.clientX-drag.x)*scale,y:drag.start.y+(event.clientY-drag.y)*scale};transform();}});svg.addEventListener("pointerup",()=>{drag=null;});
}
async function coverageModal(){try{const coverage=await api("/api/coverage?scenario="+state.scenario);showModal("Phạm vi các quy tắc",`<p>Một số quy tắc chưa đủ nguồn để đánh giá. Không có dữ liệu không đồng nghĩa với không có vi phạm.</p>${coverage.map(row=>`<div class="coverage-item"><span class="coverage-status">${{implemented:"Đã triển khai",partial:"Có giới hạn",not_evaluable:"Thiếu dữ liệu"}[row.status]}</span><strong>${esc(row.rule_id)} · ${esc(row.name)}</strong><small>${esc(row.note|| (row.scope==="aggregate_diagnostic"?"Chẩn đoán theo tập giao dịch, không cộng điểm từng giao dịch.":"Đánh giá từ thông tin đã biết tại thời điểm nghiệp vụ."))}</small></div>`).join("")}`);}catch(error){notice(error.message);}}
async function boot(){try{state.meta=await api("/api/meta");state.scenario=state.meta.default_scenario;$("scenario").innerHTML=state.meta.scenarios.map(tag=>`<option value="${tag}">Mô phỏng ${(Number(tag)/10).toLocaleString("vi-VN")}%</option>`).join("");$("scenario").value=state.scenario;$("budget").value=state.meta.daily_budget;$("company").innerHTML='<option value="">Tất cả công ty</option>'+state.meta.companies.map(row=>`<option value="${esc(row.company_id)}">${esc(row.company_id)} · ${esc(row.name)}</option>`).join("");$("environment-label").textContent=state.meta.qa?"KIỂM THỬ GIAO DIỆN":"Dữ liệu mô phỏng · 2024–2025";state.coverage=await api("/api/coverage?scenario="+state.scenario);$("rule").innerHTML='<option value="">Mọi quy tắc</option>'+state.coverage.filter(row=>row.scope==="transaction"&&row.status!=="not_evaluable").map(row=>`<option value="${esc(row.rule_id)}">${esc(row.rule_id)} · ${esc(row.name)}</option>`).join("");await loadQueue();}catch(error){notice(error.message);$("case-list").innerHTML='<div class="empty-state">Chưa nạp được hàng đợi. Kiểm tra thông báo phía trên và thử Làm mới.</div>';}}
$("scenario").addEventListener("change",()=>{state.scenario=$("scenario").value;state.selected=null;state.detail=null;state.offset=0;$("detail-panel").innerHTML='<div class="detail-placeholder"><h2>Chọn hồ sơ trong bộ dữ liệu mới</h2><p>Danh sách đã được cập nhật theo snapshot đang chọn.</p></div>';hideNotice();loadQueue();});
for(const id of ["company","status","priority","rule"])$(id).addEventListener("change",()=>{state.offset=0;loadQueue();});
let searchTimer;$("search").addEventListener("input",()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>{state.offset=0;loadQueue();},200);});
$("previous").addEventListener("click",()=>{state.offset=Math.max(0,state.offset-state.limit);loadQueue();});$("next").addEventListener("click",()=>{state.offset+=state.limit;loadQueue();});$("refresh").addEventListener("click",async()=>{hideNotice();await loadQueue();if(state.selected)try{const scenario=state.scenario,identifier=state.selected;const detail=await api("/api/case?"+new URLSearchParams({scenario,id:identifier}));if(scenario===state.scenario&&identifier===state.selected){state.detail=detail;renderDetail();}}catch(error){notice(error.message);}});
$("budget").addEventListener("change",async()=>{try{await api("/api/budget",{daily_budget:Number($("budget").value)});await loadQueue();notice("Đã cập nhật ngân sách rà soát. Số hồ sơ đã mở hôm nay được giữ lại.",true);}catch(error){notice(error.message);}});
$("export").addEventListener("click",()=>{const query=params();query.delete("offset");query.delete("limit");window.location.href="/api/export?"+query;});
$("coverage-nav").addEventListener("click",coverageModal);$("help-nav").addEventListener("click",()=>showModal("Cách rà soát một hồ sơ","<p><strong>1. Chọn hồ sơ ưu tiên.</strong> Mở tối đa 5 hoặc 10 hồ sơ mới cho mỗi công ty, mỗi bộ dữ liệu và mỗi ngày. Hồ sơ đã mở có thể tiếp tục xem.</p><p><strong>2. Đối chiếu bằng chứng.</strong> Kiểm tra số tiền, hóa đơn, hạn mức, người nhận và các ngoại lệ. Sơ đồ thể hiện quan hệ quan sát được; chưa xác nhận gian lận.</p><p><strong>3. Ghi nhận kết luận.</strong> Chọn kết luận, nhập tên người rà soát và lý do. Chọn Cần bổ sung nếu còn thiếu chứng từ. Lịch sử được giữ lại khi cập nhật kết luận.</p><p>Đây là bản thử nội bộ trên dữ liệu tổng hợp 2024–2025. Ngân sách hiện áp dụng cho việc mở hồ sơ rà soát; chưa có thông báo ERP, email hoặc Zalo.</p>"));
$("queue-nav").addEventListener("click",()=>{state.offset=0;loadQueue();});$("modal-close").addEventListener("click",()=>$("modal").close());
boot();
