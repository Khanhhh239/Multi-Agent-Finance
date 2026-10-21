"use strict";
const $=id=>document.getElementById(id);
const esc=value=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const num=value=>new Intl.NumberFormat("vi-VN",{maximumFractionDigits:2}).format(Number(value||0));
const money=value=>value==null||value===""?"Chưa có thông tin":num(value)+" ₫";
const time=value=>value?new Date(value).toLocaleString("vi-VN",{timeZone:"Asia/Ho_Chi_Minh"}):"Chưa có thông tin";
const categoryNames={no_p2:"Không phát sinh P2",information_request:"Thiếu bằng chứng",vat_document_review:"Đối chiếu chứng từ / VAT",verified_internal_breach:"Vượt hạn mức đã xác minh"};
const routeNames={transaction:"Rà soát nghiệp vụ",information_request:"Yêu cầu bổ sung bằng chứng",batch:"Hồ sơ theo lô",source:"Hồ sơ nguồn"};
const priorityNames={thap:"Thấp",trung_binh:"Trung bình",cao:"Cao",cao_nhat:"Cao nhất"};
const verdictNames={passed:"Đạt",needs_fix:"Cần sửa",needs_information:"Cần bổ sung"};
let state={meta:null,detail:null,selected:null,transaction:null,tab:"transactions",request:0,opening:0,saving:false};
let p2RouteReady=false,p2RouteKey=null;
const p2Key=(control,transaction)=>JSON.stringify([control||"",transaction||""]);
function writeP2Location(control,transaction,replace=false){
  const route=new URLSearchParams();if(control)route.set("control",control);if(transaction)route.set("transaction",transaction);
  const hash=route.toString()?"#"+route:"";
  if(window.location.hash!==hash)window.history[replace?"replaceState":"pushState"](null,"",hash||window.location.pathname+window.location.search);
}
function clearP2Detail(message="Chọn tình huống trong danh sách đang lọc."){
  state.selected=null;state.detail=null;state.transaction=null;state.tab="transactions";
  $("uat-detail").innerHTML=`<div class="empty-state">${esc(message)}</div>`;
  document.querySelectorAll("[data-control]").forEach(button=>{button.classList.toggle("selected",false);button.setAttribute("aria-pressed","false");});
}
function selectP2Transaction(id,{updateLocation=true}={}){
  if(!state.detail?.transactions.some(t=>t.transaction_id===id))return;
  state.transaction=id;state.tab="transactions";p2RouteKey=p2Key(state.selected,id);
  if(updateLocation)writeP2Location(state.selected,id);
  document.querySelectorAll("[data-tab]").forEach(tab=>tab.classList.toggle("active",tab.dataset.tab===state.tab));
  renderTab();
}
async function applyP2Location(force=false){
  if(!p2RouteReady)return;
  const route=new URLSearchParams(window.location.hash.slice(1)),id=route.get("control"),tx=route.get("transaction");
  const key=p2Key(id,tx);if(!force&&key===p2RouteKey)return;
  p2RouteKey=key;
  if(id&&state.selected===id&&state.detail&&(!tx||state.detail.transactions.some(t=>t.transaction_id===tx))){
    selectP2Transaction(tx||state.detail.transactions.at(-1).transaction_id,{updateLocation:false});writeP2Location(state.selected,state.transaction,true);return;
  }
  const generation=++state.opening;clearP2Detail(id?"Đang nạp tình huống…":undefined);
  if(!id)return;
  // A deep link identifies a sample independently of the previous list filters.
  for(const field of ["uat-search","uat-group","uat-category","uat-verdict"])$(field).value="";
  await loadControls();if(generation!==state.opening)return;
  await openControl(id,tx,{updateLocation:false});
}
async function api(path,body){const response=await fetch(path,body===undefined?{}:{method:"POST",headers:{"Content-Type":"application/json","X-CSRF-Token":state.meta.csrf_token},body:JSON.stringify(body)});const result=await response.json();if(!response.ok)throw new Error(result.error||"Chưa thực hiện được thao tác.");return result;}
function notice(message,success=false){$("uat-notice").textContent=message;$("uat-notice").className="notice"+(success?" success":"");}
function params(){return new URLSearchParams({group:$("uat-group").value,category:$("uat-category").value,verdict:$("uat-verdict").value,q:$("uat-search").value});}
function reviewBadge(review){const verdict=review?.verdict||"unreviewed";return `<span class="uat-badge ${esc(verdict)}">${esc(verdictNames[verdict]||"Chưa nghiệm thu")}</span>`;}
function amount(row){return row.currency&&row.currency!=="VND"?`${num(row.amount_vnd)} · Nguồn ghi ${row.currency}; chưa xác minh giá trị VND`:money(row.amount_vnd);}
async function loadControls(){const request=++state.request;try{const [meta,result]=await Promise.all([api("/api/p2-controls/meta"),api("/api/p2-controls?"+params())]);if(request!==state.request)return;state.meta=meta;$("uat-matched").textContent=`${meta.matched_controls}/${meta.controls}`;$("uat-transactions").textContent=num(meta.transactions);$("uat-reviewed").textContent=`${meta.reviewed_controls}/${meta.controls}`;$("uat-needs-fix").textContent=num(meta.verdict_counts.needs_fix||0);$("uat-count").textContent=num(result.total);$("uat-export").href="/api/p2-controls/export?"+params();$("uat-list").innerHTML=result.items.map(row=>`<button class="case-card ${state.selected===row.control_id?"selected":""}" data-control="${esc(row.control_id)}" aria-pressed="${state.selected===row.control_id}"><div class="case-top">${reviewBadge(row.review)}<span class="uat-caption">${row.matched?"✓ Khớp tự động":"Có sai lệch tự động"}</span></div><div class="case-title">${esc(row.title_vi)}</div><div class="case-sub">${esc(row.group_label)} · ${num(row.transactions)} giao dịch</div><p class="case-summary">${Object.entries(row.categories).map(([k,n])=>`${esc(categoryNames[k])}: ${num(n)}`).join(" · ")}</p><div class="case-code">${esc(row.control_id)}</div></button>`).join("")||'<div class="empty-state">Không có tình huống phù hợp bộ lọc.</div>';document.querySelectorAll("[data-control]").forEach(button=>button.addEventListener("click",()=>openControl(button.dataset.control)));if(state.selected&&!result.items.some(r=>r.control_id===state.selected)){state.opening++;clearP2Detail();p2RouteKey=p2Key(null,null);writeP2Location(null,null);}}catch(error){if(request===state.request){notice(error.message);$("uat-list").innerHTML='<div class="empty-state">Chưa đọc được bộ đối chứng. Thử Làm mới.</div>';}}}
async function openControl(id,transaction,{updateLocation=true}={}){
  const generation=++state.opening;p2RouteKey=p2Key(id,transaction);
  if(updateLocation)writeP2Location(id,transaction);notice("");clearP2Detail("Đang nạp tình huống…");
  try{
    const detail=await api("/api/p2-controls/detail?"+new URLSearchParams({id}));if(generation!==state.opening)return;
    if(transaction&&!detail.transactions.some(t=>t.transaction_id===transaction))throw new Error("Không tìm thấy giao dịch trong tình huống của liên kết.");
    state.detail=detail;state.selected=id;state.transaction=transaction||detail.transactions.at(-1).transaction_id;state.tab="transactions";
    p2RouteKey=p2Key(id,state.transaction);writeP2Location(id,state.transaction,true);
    document.querySelectorAll("[data-control]").forEach(button=>{const active=button.dataset.control===id;button.classList.toggle("selected",active);button.setAttribute("aria-pressed",String(active));});renderDetail();
  }catch(error){if(generation===state.opening){clearP2Detail("Chưa mở được tình huống. Chọn tình huống khác hoặc thử Làm mới.");notice(error.message);}}
}
function renderDetail(){const d=state.detail;$("uat-detail").innerHTML=`<div class="detail-header"><div class="detail-overline"><span class="detail-id">${esc(d.control_id)} · ${esc(d.group_label)}</span>${reviewBadge(d.review)}</div><h2>${esc(d.title_vi)}</h2><div class="detail-meta">${num(d.transactions.length)} giao dịch · ${d.matched?"Khớp kỳ vọng tự động":"Có sai lệch với kỳ vọng"}</div></div><nav class="detail-tabs" aria-label="Nội dung tình huống">${[["transactions","Giao dịch & P2"],["documents","Chứng từ & liên kết"],["queue","Hàng đợi"],["history","Lịch sử nghiệm thu"]].map(([key,label])=>`<button data-tab="${key}" class="${state.tab===key?"active":""}">${label}</button>`).join("")}</nav><div id="uat-content" class="detail-content"></div><form id="uat-form" class="uat-review"><h3>Ghi kết quả nghiệm thu tình huống</h3><p>Áp dụng cho toàn bộ ${num(d.transactions.length)} giao dịch của tình huống này. Đây là kết quả kiểm tra giao diện/nghiệp vụ, không phải kết luận gian lận hoặc phản hồi vận hành.</p><label class="field">Kết quả<select id="uat-result" required><option value="">Chọn kết quả</option>${Object.entries(verdictNames).map(([key,label])=>`<option value="${key}">${label}</option>`).join("")}</select></label><label class="field">Người nghiệm thu<input id="uat-reviewer" type="text" required maxlength="100" autocomplete="name"></label><label class="field">Lý do / lỗi có thể tái hiện<textarea id="uat-reason" rows="3" required maxlength="2000" placeholder="Đã kiểm tra điều gì? Nếu cần sửa, ghi bước thực hiện và kết quả mong muốn."></textarea></label><button id="uat-save" class="primary-button" type="submit">Lưu nghiệm thu</button><p id="uat-save-note" class="uat-caption">${d.review?`Kết quả gần nhất: ${esc(verdictNames[d.review.verdict])} · ${esc(d.review.reviewer)} · ${time(d.review.reviewed_at)}`:"Chưa có kết quả nghiệm thu được lưu cho tình huống này."}</p></form>`;try{$("uat-reviewer").value=localStorage.getItem("p2_uat_reviewer")||"";}catch{}$("uat-form").addEventListener("submit",saveReview);document.querySelectorAll("[data-tab]").forEach(button=>button.addEventListener("click",()=>{state.tab=button.dataset.tab;document.querySelectorAll("[data-tab]").forEach(b=>b.classList.toggle("active",b===button));renderTab();}));renderTab();}
function facts(items){return `<div class="evidence-facts">${items.map(([k,v])=>`<div><span>${esc(k)}</span>${esc(v)}</div>`).join("")}</div>`;}
function foreignRows(d, record) {
  return d.transactions.filter(t=>t.currency&&t.currency!=="VND"&&t.company_id===record.company_id&&
    ((record.transaction_id&&t.transaction_id===record.transaction_id)||(record.document_id&&
      (t.journal_document_id===record.document_id||t.linked_document_id===record.document_id))||
      (record.invoice_id&&t.invoice_id===record.invoice_id)));
}
function currencyWarning(rows) {
  if(!rows.length)return "";
  const currencies=[...new Set(rows.map(t=>t.currency))].join(", ");
  return `<div class="source-banner source-gap"><strong>Chưa xác minh quy đổi VND</strong>Nguồn giao dịch ghi đồng tiền ${esc(currencies)}. Các số sổ/hóa đơn dưới đây giữ nguyên theo nguồn, chưa có bằng chứng quy đổi được xác nhận; không dùng để so hạn mức VND.</div>`;
}
function invoiceTiming(d, invoice, cutoff) {
  const payments=d.transactions.filter(t=>t.company_id===invoice.company_id&&t.invoice_id===invoice.invoice_id);
  const earlier=payments.filter(t=>t.invoice_issued_at&&Date.parse(t.invoice_issued_at)<=Date.parse(t.posted_at)&&Date.parse(invoice.recorded_at)>Date.parse(t.posted_at));
  const versions=(d.invoice_versions||[]).filter(r=>r.company_id===invoice.company_id&&r.invoice_id===invoice.invoice_id);
  const displayInvoice={...invoice,currency:foreignRows(d,invoice)[0]?.currency||invoice.currency};
  return ReviewExplanations.invoiceVersions(displayInvoice,versions,cutoff||payments[0]?.posted_at)+facts([["Mốc ghi nhận hóa đơn trong nguồn",time(invoice.recorded_at)]])+(earlier.length&&!versions.length?`<div class="source-banner source-gap"><strong>Cần lịch sử phiên bản hóa đơn</strong>Giao dịch ${earlier.map(t=>esc(t.transaction_id)).join(", ")} đã có thông tin hóa đơn trước mốc ghi nhận trên bảng hóa đơn nguồn. Cần xác minh thời điểm hệ thống nhận hóa đơn lần đầu; mốc này chưa chứng minh dữ liệu tương lai đã được dùng để chấm.</div>`:"");
}
function temporalEvidence(d, row, hit) {
  const proof=hit?.evidence||{},invoice=d.invoices.find(i=>i.company_id===row.company_id&&i.invoice_id===row.invoice_id);
  const limit=proof.internal_limit_evidence||d.config?.cash_limit_evidence_by_company?.[row.company_id];
  const issued=proof.invoice_issued_at||row.invoice_issued_at;
  const futureInvoice=issued&&Date.parse(issued)>Date.parse(row.posted_at);
  const futureLimit=proof.internal_limit_status==="not_known_at_payment";
  return `<div class="source-block"><strong>Mốc chứng từ tại thời điểm chi</strong>${facts([["Thời điểm chi / ghi sổ",time(proof.payment_at||row.posted_at)],["Hóa đơn phát hành lúc",time(issued)]])}${futureInvoice?`<div class="source-banner source-gap"><strong>Hóa đơn phát hành sau lúc chi</strong>Chưa dùng hóa đơn này làm bằng chứng đã có tại thời điểm chi. ${proof.review_category==="information_request"?"Kết quả P2 đang giữ yêu cầu bổ sung.":"Xem kết quả P2 riêng theo phạm vi quy tắc."}</div>`:""}${invoice?invoiceTiming(d,invoice,row.posted_at):""}${limit?facts([["Nguồn xác minh hạn mức",limit.source_ref],["Người xác minh",limit.verified_by],["Xác minh lúc",time(limit.verified_at)],["Hiệu lực từ",time(limit.effective_from)],["Hiệu lực đến · không gồm mốc cuối",limit.effective_to?time(limit.effective_to):"Không khai báo mốc cuối"]]):""}${futureLimit?'<div class="source-banner source-gap"><strong>Xác minh hạn mức có sau lúc chi</strong>Nguồn cấu hình chỉ hiển thị để đối chiếu thời điểm; chưa được dùng làm bằng chứng vượt hạn mức đã xác minh lúc chi.</div>':""}${proof.internal_limit_status==="outside_effective_period"?'<p>Hạn mức không có hiệu lực tại lúc chi. Giao dịch đúng mốc kết thúc không được coi là còn trong kỳ hiệu lực.</p>':""}</div>`;
}
function returnRelations(d) {
  const found=new Map();
  for(const related of d.transactions){
    const link=d.document_links.find(l=>["cash_return_of","reversal_of"].includes(l.link_type)&&l.target_document_id===related.journal_document_id);
    const originals=d.transactions.filter(t=>t.company_id===related.company_id&&((related.original_transaction_id&&t.transaction_id===related.original_transaction_id)||(link&&t.journal_document_id===link.source_document_id)));
    if(originals.length!==1)continue;
    const original=originals[0],key=original.company_id+":"+original.transaction_id;
    if(!found.has(key))found.set(key,{original,returns:[]});
    found.get(key).returns.push({related,link,journal:related.payment_channel==="journal"||link?.link_type==="reversal_of"});
  }
  return [...found.values()];
}
function returnLinkLabel(d, link) {
  const target=link.target_document_id&&d.transactions.find(t=>t.journal_document_id===link.target_document_id);
  if(target?.payment_channel==="journal"||link.link_type==="reversal_of")return "Đảo sổ / điều chỉnh kế toán · chưa xác nhận hoàn tiền thực";
  return ({cash_return_of:"Hoàn tiền cho khoản chi gốc theo nguồn · cần đối chiếu",invoice_before_payment:"Hóa đơn được ghi nhận trước thanh toán"})[link.link_type]||link.link_type;
}
function refundSummary(d) {
  const groups=returnRelations(d);
  if(!groups.length)return "";
  return `<div class="section-label">Khoản chi gốc và hoàn / đảo · toàn bộ tình huống</div>${groups.map(({original,returns})=>{
    const cash=returns.filter(r=>!r.journal&&["cash","bank"].includes(r.related.payment_channel)&&/^(111|112)/.test(String(r.related.debit_account))&&!/^(111|112)/.test(String(r.related.credit_account)));
    const sameVnd=(original.currency||"VND")==="VND"&&cash.every(r=>(r.related.currency||"VND")==="VND");
    const returned=cash.reduce((sum,r)=>sum+Number(r.related.amount_vnd),0);
    const cases=d.cases.filter(c=>c.company_id===original.company_id&&JSON.parse(c.transaction_ids).includes(original.transaction_id));
    return `<div class="source-block"><strong>Khoản chi gốc ${esc(original.transaction_id)}</strong>${facts([["Chi theo nguồn",amount(original)],["Thời điểm chi gốc",time(original.posted_at)],["Tổng hoàn/thu tiền theo nguồn",sameVnd?money(returned):"Chưa xác minh cùng đơn vị VND"],["Chênh lệch chi trừ hoàn theo nguồn",sameVnd?money(Number(original.amount_vnd)-returned):"Chưa tính do khác/chưa rõ đơn vị"]])}<button class="link-button" data-jump-transaction="${esc(original.transaction_id)}">Xem khoản chi gốc →</button>${returns.map(({related,link,journal})=>`<div class="source-block"><strong>${journal?"Đảo sổ / điều chỉnh kế toán":"Hoàn/thu tiền theo nguồn · cần xác minh dòng tiền"}</strong>${facts([["Giao dịch liên quan",related.transaction_id],["Số theo nguồn",amount(related)],["Ghi sổ lúc",time(related.posted_at)],["Liên kết được biết lúc",time(link?.observed_at)]])}<button class="link-button" data-jump-transaction="${esc(related.transaction_id)}">Xem nghiệp vụ liên quan →</button>${journal?"<p>Đảo sổ chưa chứng minh đã nhận lại tiền thực; cần chứng từ dòng tiền riêng.</p>":""}</div>`).join("")}<p><strong>Hồ sơ gốc trong snapshot engine:</strong> ${cases.map(c=>`${esc(c.case_id)} · ${num(c.max_score)} điểm · ${esc(priorityNames[c.priority]||c.priority)}`).join("; ")||"Không mở hồ sơ"}.</p><p>Khoản hoàn/đảo không tự đóng hồ sơ gốc hoặc bù trừ điều kiện VAT. Chênh lệch trên chỉ là đối chiếu số theo nguồn; cần kiểm chứng trước khi kết luận. Bộ đối chứng không chứa kết luận vận hành.</p></div>`;
  }).join("")}`;
}
function documentsTab(d) {
  const documents=d.documents.map(doc=>{
    const lines=d.lines.filter(l=>l.document_id===doc.document_id&&(!l.company_id||l.company_id===doc.company_id));
    const foreign=foreignRows(d,doc),unverified=foreign.length>0;
    const value=v=>unverified?esc(num(v)):money(v);
    const unit=unverified?"số nguồn, chưa xác minh VND":"VND";
    return `<div class="document-title">${esc(doc.document_id)} · ${time(doc.posted_at)}</div>${currencyWarning(foreign)}<div class="data-table-wrap"><table class="data-table"><thead><tr><th>Tài khoản</th><th>Nợ (${unit})</th><th>Có (${unit})</th></tr></thead><tbody>${lines.map(l=>`<tr><td>${esc(l.account_code)}</td><td>${value(l.debit_vnd)}</td><td>${value(l.credit_vnd)}</td></tr>`).join("")}<tr><td><strong>${unverified?"Tổng số theo nguồn":"Tổng"}</strong></td><td>${value(lines.reduce((s,l)=>s+Number(l.debit_vnd),0))}</td><td>${value(lines.reduce((s,l)=>s+Number(l.credit_vnd),0))}</td></tr></tbody></table></div>`;
  }).join("");
  const invoices=d.invoices.map(i=>{
    const foreign=foreignRows(d,i),gross=i.gross_amount_vnd??i.gross_vnd??i.invoice_gross_vnd;
    const future=d.transactions.filter(t=>t.company_id===i.company_id&&t.invoice_id===i.invoice_id&&Date.parse(i.issued_at||i.invoice_issued_at)>Date.parse(t.posted_at));
    return currencyWarning(foreign)+(future.length?`<div class="source-banner source-gap"><strong>Hóa đơn phát hành sau giao dịch ${future.map(t=>esc(t.transaction_id)).join(", ")}</strong>Chỉ hiển thị để đối chiếu nguồn; chưa coi là chứng từ đã có khi chi.</div>`:"")+facts([["Mã hóa đơn",i.invoice_id],["Số hóa đơn",i.invoice_number],["Ngày phát hành",time(i.issued_at||i.invoice_issued_at)],[foreign.length?"Giá trị hóa đơn theo nguồn · chưa xác minh VND":"Giá trị hóa đơn",ReviewExplanations.invoiceAmount(gross,foreign.length>0)]])+invoiceTiming(d,i);
  }).join("");
  return `<div class="section-label">Chứng từ kế toán · toàn bộ tình huống</div>${documents}${d.invoices.length?`<div class="section-label">Hóa đơn nguồn</div>${invoices}`:""}<div class="section-label">Liên kết hoàn / đảo và chứng từ</div>${d.document_links.length?d.document_links.map(link=>`<div class="source-block">${facts([["Chứng từ gốc",link.source_document_id],["Chứng từ liên quan",link.target_document_id],["Quan hệ",returnLinkLabel(d,link)],["Được biết lúc",time(link.observed_at)]])}</div>`).join(""):"<p>Không có liên kết được khai báo trong tình huống này.</p>"}${d.recurring_payments.length?`<details class="uat-expectations"><summary>Thỏa thuận định kỳ được cung cấp</summary>${d.recurring_payments.map(r=>facts([["Mẫu định kỳ",r.pattern_id],["Giá trị theo thỏa thuận",money(r.expected_amount_vnd)],["Dung sai",money(r.tolerance_vnd)],["Chu kỳ",({monthly:"Hằng tháng",weekly:"Hằng tuần"})[r.frequency]||r.frequency],["Hiệu lực từ / đến",`${r.effective_from} / ${r.effective_to}`],["Trạng thái",r.status==="approved"?"Đã duyệt":r.status],["Người duyệt",r.approver_id],["Phê duyệt lúc",time(r.approved_at)],["Được biết lúc",time(r.observed_at)],["Mã bằng chứng",r.evidence_id]])).join("")}</details>`:""}`;
}
function cashEvidence(hit){const proof=hit.evidence;const internal={not_configured:"Chưa khai báo",not_exceeded:"Không ghi nhận vượt",not_evaluable:"Chưa đủ dữ kiện",unverified_limit:"Chưa xác minh",not_known_at_payment:"Chưa biết lúc chi",outside_effective_period:"Ngoài kỳ hiệu lực",verified_breach:"Đã xác minh vượt hạn mức"};const missing={invoice_identity:"Mã hoặc số hóa đơn",invoice_issued_at:"Ngày hóa đơn",invoice_gross_vnd:"Tổng tiền hóa đơn",invoice_issued_at_not_in_future:"Hóa đơn đã có lúc chi",verified_vnd_amount:"Số tiền VND đã xác minh",internal_limit_verification:"Bằng chứng xác minh hạn mức"};return `<div class="source-banner ${proof.review_category==="information_request"?"source-gap":"source-signal"}"><strong>${esc(proof.summary_vi)}</strong>${esc(proof.conclusion)}</div>${facts([["Điểm P2",hit.points],["Giá trị hóa đơn",ReviewExplanations.invoiceAmount(proof.invoice_gross_vnd)],["Mã / số hóa đơn",proof.invoice_id||proof.invoice_number||"Chưa có thông tin"],["Ngày hóa đơn",time(proof.invoice_issued_at)],["Ngưỡng đối chiếu tại thời điểm",money(proof.vat_non_cash_threshold_vnd)],["Hạn mức nội bộ",money(proof.internal_cash_limit_vnd)],["Trạng thái hạn mức",internal[proof.internal_limit_status]||proof.internal_limit_status]])}${proof.missing_fields?.length?`<p><strong>Cần bổ sung:</strong> ${proof.missing_fields.map(k=>esc(missing[k]||k)).join("; ")}.</p>`:""}${proof.internal_limit_evidence?facts([["Nguồn xác minh",proof.internal_limit_evidence.source_ref],["Người xác minh",proof.internal_limit_evidence.verified_by],["Thời điểm xác minh",time(proof.internal_limit_evidence.verified_at)]]):""}<p>${esc(proof.next_action_vi)}</p>`;}
function expectedPanel(d){return `<details class="uat-expectations"><summary>Xem kỳ vọng đã khai báo và đối chiếu tự động</summary><p>Kỳ vọng được khai báo trước khi chấm. “Khớp” là kiểm tra logic xác định, không phải precision gian lận.</p>${d.comparisons.map(row=>{const e=row.expected,a=row.actual;return `<div class="uat-check"><strong>${esc(row.transaction_id)} · ${Object.keys(row.differences).length?"Có sai lệch":"Khớp"}</strong><dl><dt>P2 mong đợi</dt><dd>${esc(categoryNames[e.category||"no_p2"])} · ${num(e.points)} điểm</dd><dt>P2 thực tế</dt><dd>${esc(categoryNames[a.category||"no_p2"])} · ${num(a.points)} điểm</dd><dt>Hàng đợi mong đợi</dt><dd>${esc(routeNames[e.case_type]||"Không mở hồ sơ")} · ${esc(priorityNames[e.priority]||"Không áp dụng")}</dd><dt>Hàng đợi thực tế</dt><dd>${esc(a.case_types.map(t=>routeNames[t]||t).join(", ")||"Không mở hồ sơ")} · ${esc(a.priorities.map(p=>priorityNames[p]||p).join(", ")||"Không áp dụng")}</dd>${e.a5_suppressed!==undefined?`<dt>Ngoại lệ A5</dt><dd>Mong đợi: ${e.a5_suppressed?"có":"không"} · Thực tế: ${a.a5_suppressed?"có":"không"}</dd>`:""}</dl>${Object.keys(row.differences).length?`<pre class="uat-error uat-line">${esc(JSON.stringify(row.differences,null,2))}</pre>`:""}</div>`;}).join("")}<p class="uat-caption">Mã bộ đối chứng: ${esc(d.snapshot_id.slice(0,16))}. Nguồn và kết quả đã đối chiếu checksum.</p></details>`;}
function renderTabContent(){const d=state.detail,container=$("uat-content");if(state.tab==="transactions"){const row=d.transactions.find(t=>t.transaction_id===state.transaction),hit=d.hits.find(h=>h.rule_id==="P2"&&h.transaction_id===row.transaction_id),actual=d.comparisons.find(r=>r.transaction_id===row.transaction_id).actual;container.innerHTML=`<label for="uat-transaction" class="section-label">Chọn giao dịch · gồm cả dòng không có P2</label><select id="uat-transaction" class="uat-transaction-picker">${d.transactions.map(t=>`<option value="${esc(t.transaction_id)}" ${t.transaction_id===row.transaction_id?"selected":""}>${esc(t.transaction_id)} · ${time(t.posted_at)} · ${esc(amount(t))}</option>`).join("")}</select><div class="summary-grid">${[["Thời điểm ghi sổ",time(row.posted_at)],["Giá trị theo nguồn",amount(row)],["Nợ / Có",`${row.debit_account} / ${row.credit_account}`],["Kênh thanh toán",{cash:"Tiền mặt",bank:"Ngân hàng",none:"Không chi tiền"}[row.payment_channel]||row.payment_channel],["Chứng từ",row.journal_document_id||"Chưa có"],["Nội dung",row.business_purpose||row.accounting_purpose||row.txn_type]].map(([k,v])=>`<div><span>${esc(k)}</span>${esc(v)}</div>`).join("")}</div>${refundSummary(d)}${temporalEvidence(d,row,hit)}${hit?cashEvidence(hit)+ReviewExplanations.cashSentence(hit):ReviewExplanations.noP2(row,d.policy_context?.[row.transaction_id])}<div class="source-block"><strong>Kết quả đưa vào hàng đợi</strong><p>${esc(actual.case_types.map(t=>routeNames[t]||t).join(", ")||"Không mở hồ sơ")} · ${esc(actual.priorities.map(p=>priorityNames[p]||p).join(", ")||"Không có mức ưu tiên")}</p><span>Quy tắc khác có điểm: ${esc(actual.other_positive_rules.join(", ")||"Không có")}</span></div>${d.hits.filter(h=>h.rule_id!=="P2"&&h.transaction_id===row.transaction_id).map(h=>`<div class="source-block"><strong>${esc(h.rule_id)} · ${esc(h.rule_name)}</strong><p>${h.suppressed_reason?esc(h.suppressed_reason):`${num(h.points)} điểm`}</p>${h.rule_id==="A5"&&h.evidence.selected_parameter?ReviewExplanations.a5(h.evidence):""}${ReviewExplanations.exception(h,d)}</div>`).join("")}${d.cases.filter(c=>JSON.parse(c.transaction_ids).includes(row.transaction_id)).map(c=>ReviewExplanations.score(c,d.hits,d.rule_scores||[])).join("")}${expectedPanel(d)}`;$("uat-transaction").addEventListener("change",event=>{selectP2Transaction(event.target.value);});}else if(state.tab==="documents"){container.innerHTML=refundSummary(d)+documentsTab(d);}else if(state.tab==="queue"){container.innerHTML=`<div class="section-label">Hồ sơ thực tế của engine</div>${d.cases.length?d.cases.map(c=>`<div class="source-block"><strong>${esc(c.case_id)}</strong>${facts([["Nhóm",routeNames[c.case_type]||c.case_type],["Ưu tiên",priorityNames[c.priority]||c.priority],["Điểm cao nhất",c.max_score],["Giao dịch",JSON.parse(c.transaction_ids).join(", ")],["Quy tắc",c.rule_ids],["Giải thích",c.explanation_vi]])}</div>`).join(""):"<p>Engine không mở hồ sơ cho tình huống này. Các giao dịch vẫn được giữ để nghiệm thu.</p>"}${expectedPanel(d)}`;}else{container.innerHTML=`<div class="section-label">Lịch sử nghiệm thu · chỉ bộ đối chứng này</div>${d.history.length?d.history.slice().reverse().map(r=>`<div class="timeline-entry">${reviewBadge(r)}<p class="uat-history">${esc(r.reason)}</p><small>${esc(r.reviewer)} · ${time(r.reviewed_at)}</small></div>`).join(""):"<p>Chưa có kết quả nghiệm thu được lưu.</p>"}<p class="uat-caption">Nhật ký được kiểm tra chuỗi hash khi đọc và lưu; không phải chữ ký số.</p>`;}}
function renderTab(){renderTabContent();$("uat-content").querySelectorAll("[data-jump-transaction]").forEach(button=>button.addEventListener("click",()=>selectP2Transaction(button.dataset.jumpTransaction)));}
async function saveReview(event){event.preventDefault();if(state.saving)return;const id=state.selected,snapshot=state.detail.snapshot_id,verdict=$("uat-result").value,reviewer=$("uat-reviewer").value.trim(),reason=$("uat-reason").value.trim();if(!verdict||!reviewer||!reason){notice("Chọn kết quả, nhập người nghiệm thu và lý do trước khi lưu.");return;}state.saving=true;$("uat-save").disabled=true;try{await api("/api/p2-controls/review",{snapshot_id:snapshot,control_id:id,verdict,reviewer,reason,expected_hash:state.detail.review?.event_hash||""});try{localStorage.setItem("p2_uat_reviewer",reviewer);}catch{}if(state.selected===id){state.detail=await api("/api/p2-controls/detail?"+new URLSearchParams({id}));state.tab="history";renderDetail();}await loadControls();notice(`Đã lưu nghiệm thu cho ${id}. Nguồn và kết quả P2 giữ nguyên.`,true);}catch(error){notice(error.message);}finally{state.saving=false;if($("uat-save"))$("uat-save").disabled=false;}}
async function boot(){try{state.meta=await api("/api/p2-controls/meta");for(const [id,map] of [["uat-group",state.meta.groups],["uat-category",state.meta.categories],["uat-verdict",state.meta.verdicts]]){$(id).insertAdjacentHTML("beforeend",Object.entries(map).map(([key,label])=>`<option value="${esc(key)}">${esc(label)}</option>`).join(""));}await loadControls();p2RouteReady=true;await applyP2Location();}catch(error){notice(error.message);$("uat-list").innerHTML='<div class="empty-state">Chưa nạp được bộ đối chứng đã xác minh.</div>';}}
window.addEventListener("hashchange",()=>applyP2Location());
window.addEventListener("popstate",()=>applyP2Location());
for(const id of ["uat-group","uat-category","uat-verdict"])$(id).addEventListener("change",loadControls);
let searchTimer;$("uat-search").addEventListener("input",()=>{clearTimeout(searchTimer);searchTimer=setTimeout(loadControls,250);});
$("refresh-controls").addEventListener("click",async()=>{const id=state.selected,tx=state.transaction;await loadControls();if(id&&state.selected===id)await openControl(id,tx);});
boot();
