"use strict";
/* Presentation of stored evidence only. These helpers never change detector results. */
globalThis.ReviewExplanations=(()=>{
  const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const money=v=>v==null||v===""?"Chưa có thông tin":new Intl.NumberFormat("vi-VN").format(Number(v))+" ₫";
  // Stored snapshots use zero as the missing invoice-total sentinel. Ledger
  // entries and refund balances still use money(), where zero is a real value.
  const hasInvoiceTotal=v=>v!=null&&String(v).trim()!==""&&Number.isFinite(Number(v))&&Number(v)!==0;
  const invoiceAmount=(v,unverified=false)=>!hasInvoiceTotal(v)?"Chưa có thông tin":
    unverified?new Intl.NumberFormat("vi-VN",{maximumFractionDigits:2}).format(Number(v)):money(v);
  const time=v=>v?new Date(v).toLocaleString("vi-VN",{timeZone:"Asia/Ho_Chi_Minh"}):"Chưa có thông tin";
  const facts=rows=>`<div class="evidence-facts">${rows.map(([k,v])=>`<div><span>${esc(k)}</span>${esc(v??"Chưa có thông tin")}</div>`).join("")}</div>`;
  const ids=v=>Array.isArray(v)?v:typeof v==="string"?JSON.parse(v||"[]"):[];
  const measurement={cash_outflow:"Dòng tiền chi",expense_debit:"Chi phí ghi Nợ"};
  function a5(proof){
    const p=proof.selected_parameter||{};
    return facts([["Số tiền được so sánh",money(proof.comparison_amount_vnd)],["Ngưỡng lịch sử tại lúc ghi sổ",money(proof.threshold_vnd)],["Mẫu lịch sử",`${p.sample_count??"?"} / tối thiểu ${p.minimum_samples??"?"} mẫu trong ${p.window_days??"?"} ngày`],["Phép đo",measurement[p.measurement]||p.measurement||"Chưa có"],["Phạm vi",`${p.company_id||""} · TK ${p.account_code||""}`],["Cách tính",({p99:"Phân vị 99",p95:"Phân vị 95",mean_plus_k_std:"Trung bình cộng k lần độ lệch chuẩn"})[p.method]||p.method||"Theo nguồn"],["Chu kỳ",p.phase==="all_days"?"Toàn bộ ngày; chưa dùng ngưỡng chu kỳ riêng":p.phase||"Chưa có"]])+"<p>Ngưỡng chỉ dùng lịch sử đã biết trước giao dịch. Chi phí ghi Nợ có thể là trích trước, không đồng nghĩa đã chi tiền. A5 cần căn cứ độc lập; thiếu mẫu hoặc không có hit chưa chứng minh hợp lệ.</p>";
  }
  function source(record,cutoff){
    if(!record)return "<p>Chưa nạp bản ghi phê duyệt tương ứng; đối chiếu mã tham chiếu với tài liệu gốc.</p>";
    const late=[record.observed_at,record.approved_at].some(t=>t&&Date.parse(t)>Date.parse(cutoff));
    return facts([["Mã bằng chứng",record.evidence_id||"Chưa có"],["Trạng thái nguồn",record.status==="approved"?"Đã duyệt":record.status||"Chưa có"],["Người duyệt",record.approver_id||"Chưa có"],["Phê duyệt lúc",time(record.approved_at)],["Nguồn được biết lúc",time(record.observed_at)],["Hiệu lực từ / đến",`${record.effective_from||"Không khai báo"} / ${record.effective_to||"Không khai báo"}`]])+(late?"<p>Nguồn này được biết hoặc phê duyệt sau lúc phát hiện; chỉ để đối chiếu lịch sử, không dùng để hợp thức hóa giao dịch quá khứ.</p>":"");
  }
  function exception(hit,support={}){
    const p=hit.evidence||{};
    if(hit.rule_id==="A1"&&p.installment_check){
      const checks=[p.installment_check,...(p.excluded_independent_obligations||[])];
      return `<div class="source-block"><strong>Căn cứ nghĩa vụ chi của A1</strong>${checks.map(c=>{
        const records=(support.supplier_payment_agreements||[]).filter(r=>r.company_id===hit.company_id&&r.agreement_id===c.agreement_id);
        return facts([["Giao dịch gắn nghĩa vụ",c.transaction_id||hit.transaction_id],["Thỏa thuận / hợp đồng",`${c.agreement_id||"Chưa có"} / ${c.contract_id||"Chưa có"}`],["Tổng được phép",money(c.authorized_total_vnd)],["Tổng đã thanh toán",money(c.cumulative_paid_vnd)],["Hóa đơn",c.invoice_check?.invoice_number||"Chưa có"],["Giá trị hóa đơn",money(c.invoice_check?.invoice_gross_vnd)],["Mã bằng chứng liên kết",(c.evidence_ids||[]).join(", ")||"Chưa có"]])+(records.length?records.map(r=>source(r,hit.detected_at)).join(""):source(null));
      }).join("")}<p>Đây là giải trình cho A1 theo bằng chứng đã lưu; không tự miễn P2 hoặc các kiểm soát khác.</p></div>`;
    }
    if(hit.rule_id==="A5"&&p.recurring_pattern_id){
      const records=(support.recurring_payments||[]).filter(r=>r.company_id===hit.company_id&&r.pattern_id===p.recurring_pattern_id);
      return `<div class="source-block"><strong>Ngoại lệ khoản định kỳ của A5</strong>${facts([["Mã lịch định kỳ",p.recurring_pattern_id]])}${records.map(r=>facts([["Giá trị theo thỏa thuận",money(r.expected_amount_vnd)],["Dung sai",money(r.tolerance_vnd)],["Chu kỳ",r.frequency==="monthly"?"Hằng tháng":r.frequency]])+source(r,hit.detected_at)).join("")||source(null)}<p>Khoản có thể vượt ngưỡng lịch sử nhưng được A5 giải trình theo lịch đã duyệt. Hợp đồng định kỳ không tự miễn P2.</p></div>`;
    }
    return "";
  }
  function cashSentence(hit){
    const p=hit.evidence||{};
    if(p.limit_priority){
      const t=p.limit_priority,labels={thap:"Thấp",trung_binh:"Trung bình",cao:"Cao",cao_nhat:"Cao nhất"};
      return facts([["Hạn mức nội bộ",money(t.limit_vnd)],["Số tiền vượt",money(t.excess_vnd)],["Tỷ lệ vượt",t.excess_ratio==null?"Không áp dụng (hạn mức 0)":new Intl.NumberFormat("vi-VN",{style:"percent",maximumFractionDigits:6}).format(t.excess_ratio)],["Điểm P2",hit.points],["Ưu tiên xử lý P2",labels[p.review_priority]||p.review_priority],["Chính sách phân tầng",t.version]])+"<p>Điểm lưu bằng chứng vượt hạn mức. Ưu tiên xử lý theo mức vượt, nhu cầu rà chứng từ VAT và các tín hiệu độc lập; hồ sơ vẫn được giữ để rà.</p>";
    }
    if(p.review_category!=="vat_document_review")return "";
    return `<p>Khoản chi hiện tại ${esc(money(p.cash_amount_vnd))}; tổng hóa đơn ${esc(money(p.invoice_gross_vnd))}; mốc đối chiếu trong snapshot ${esc(money(p.vat_non_cash_threshold_vnd))}. ${Number(p.cash_amount_vnd)<Number(p.vat_non_cash_threshold_vnd)&&Number(p.invoice_gross_vnd)>=Number(p.vat_non_cash_threshold_vnd)?"P2 cần đối chiếu vì tổng hóa đơn đạt mốc, dù đợt chi hiện tại nhỏ hơn mốc.":"Cần đối chiếu hóa đơn gốc và chứng từ thanh toán."} Đây chưa phải kết luận quyền khấu trừ hoặc gian lận.</p>`;
  }
  function noP2(row,policy={}){
    let reason,action;
    const invoiceKnown=hasInvoiceTotal(row.invoice_gross_vnd);
    if(/^(111|112)/.test(String(row.debit_account))&&!/^(111|112)/.test(String(row.credit_account))){
      reason="Đây là dòng thu/hoàn hoặc đảo ghi Nợ tiền, không phải khoản chi mới thuộc P2.";
      action=row.original_transaction_id?"Đối chiếu chứng từ thu/đảo và khoản chi gốc; không tự xóa cảnh báo gốc.":"Chưa liên kết khoản chi gốc: xác định bên nộp, lý do thu và chứng từ gốc; đối chiếu sổ quỹ.";
    }else if(row.payment_channel!=="cash"){
      reason=row.payment_channel==="bank"?"Thanh toán qua ngân hàng, ngoài phạm vi kiểm tra chi tiền mặt P2.":"Nghiệp vụ không phải chi tiền mặt thuộc phạm vi P2.";
      action="Tiếp tục đối chiếu nghĩa vụ chi, thẩm quyền và các kiểm soát khác.";
    }else if(policy.threshold_vnd&&Number(row.amount_vnd)<policy.threshold_vnd&&(!invoiceKnown||Number(row.invoice_gross_vnd)<policy.threshold_vnd)){
      reason=invoiceKnown?
        `Khoản chi ${money(row.amount_vnd)} và tổng hóa đơn đang có ${invoiceAmount(row.invoice_gross_vnd)} dưới mốc đối chiếu ${money(policy.threshold_vnd)} trong chính sách của snapshot.`:
        `Khoản chi ${money(row.amount_vnd)} dưới mốc đối chiếu ${money(policy.threshold_vnd)} trong chính sách của snapshot. Tổng giá trị hóa đơn: Chưa có thông tin; chưa đủ dữ kiện để so sánh tổng hóa đơn với mốc này.`;
      action="Kiểm tra chứng từ và hạn mức nội bộ nếu có; không mở P2 giả cho tình huống ngoài điều kiện.";
    }else{
      reason="Dữ kiện hiện có không tạo hit P2; cần đối chiếu phạm vi và điều kiện của quy tắc.";
      action="Tiếp tục kiểm tra bằng chứng và các quy tắc khác nếu có.";
    }
    return `<div class="source-block"><strong>Không phát sinh P2 cho giao dịch này.</strong><p>${esc(reason)}</p><p>${esc(action)}</p><p>Không có P2 chưa phải chứng nhận nghiệp vụ hợp lệ.</p></div>`;
  }
  function score(caseRow,hits,scores=[]){
    const members=ids(caseRow.transaction_ids),rows=scores.filter(s=>members.includes(s.transaction_id));
    const hard=hits.filter(h=>Number(h.hard_trigger)&&Number(h.points)>0).map(h=>h.rule_id);
    const basis=caseRow.case_type==="information_request"?"Yêu cầu bổ sung dữ kiện, chưa phải kết luận rủi ro đã xác minh.":String(caseRow.admission_basis||"").includes("split_pattern")?"Nhận để rà mẫu chia nhỏ theo chính sách A2/A4, dù điểm có thể dưới ngưỡng thông thường.":hard.length?`Có căn cứ độc lập bắt buộc rà: ${[...new Set(hard)].join(", ")}; mức ưu tiên không chỉ do A5.`:"Theo chính sách tiếp nhận của snapshot; đối chiếu quy tắc và bằng chứng độc lập.";
    return `<div class="source-block"><strong>Căn cứ vào hàng đợi, điểm và ưu tiên xử lý</strong>${facts([["Điểm hồ sơ theo snapshot",caseRow.max_score],["Ưu tiên xử lý",({thap:"Thấp",trung_binh:"Trung bình",cao:"Cao",cao_nhat:"Cao nhất"})[caseRow.priority]||caseRow.priority],["Căn cứ tiếp nhận",basis]])}${rows.map(r=>{
      const positive=hits.filter(h=>h.transaction_id===r.transaction_id&&Number(h.points)>0&&!h.suppressed_reason),groups={};
      for(const h of positive){const family=["B5","E4","E3"].includes(h.rule_id)?"Chất lượng danh mục":h.rule_id[0];groups[family]=Math.max(groups[family]||0,Number(h.points));}
      return `<details><summary>${esc(r.transaction_id)} · ${esc(r.rule_score)} điểm</summary>${facts([["Điểm nền theo nguồn",r.base_score??"Chưa có"],["Điểm lặp lại theo nguồn",r.recurrence_points??"Chưa có"],["Điểm từng quy tắc",positive.map(h=>`${h.rule_id}: ${h.points}`).join("; ")||"Không có"],["Mỗi nhóm lấy điểm cao nhất",Object.entries(groups).map(([k,v])=>`${k}: ${v}`).join("; ")||"Không có"]])}</details>`;
    }).join("")||"<p>Snapshot này chưa có bảng điểm giao dịch để phân rã; không tự suy điểm còn thiếu.</p>"}<p>Không cộng cơ học mọi hit hoặc mọi giao dịch thành điểm hồ sơ. Hàng đợi dùng mức ưu tiên xử lý rồi mới đến điểm trong cùng mức. Điểm không phải xác suất gian lận.</p></div>`;
  }
  function invoiceVersions(invoice,versions,cutoff){
    const matching=(versions||[]).filter(r=>r.company_id===invoice.company_id&&r.invoice_id===invoice.invoice_id);
    if(!matching.length)return "";
    const all=matching.filter(r=>r.revision_id&&r.observed_at&&/([+-]\d\d:\d\d|Z)$/.test(r.observed_at)&&Number.isFinite(Date.parse(r.observed_at))).sort((a,b)=>Date.parse(a.observed_at)-Date.parse(b.observed_at)||a.revision_id.localeCompare(b.revision_id));
    const known=all.filter(r=>Date.parse(r.observed_at)<=Date.parse(cutoff)),current=known.at(-1);
    const ambiguous=current&&known.filter(r=>Date.parse(r.observed_at)===Date.parse(current.observed_at)).length>1;
    return `<div class="source-block"><strong>Lịch sử phiên bản hóa đơn</strong>${facts([["Lần đầu được biết theo lịch sử nguồn",time(all[0]?.observed_at)],["Phiên bản đã biết tại lúc chi",ambiguous?"Nhiều phiên bản cùng mốc; cần xác minh thứ tự nguồn":current?.revision_id||"Chưa có phiên bản đã biết"],["Phiên bản đó được biết lúc",time(current?.observed_at)],["Mốc cập nhật cuối trong nguồn",time(all.at(-1)?.observed_at)]])}${all.map(r=>`<details><summary>${esc(r.revision_id)} · ${Date.parse(r.observed_at)<=Date.parse(cutoff)?"Đã biết tại lúc chi":"Được biết sau lúc chi"}</summary>${facts([["Mã bằng chứng nguồn",r.evidence_id||"Chưa có"],["Nguồn được biết lúc",time(r.observed_at)],["Phát hành lúc theo phiên bản",time(r.issued_at)],["Cập nhật ở nguồn lúc",time(r.source_updated_at)],["Giá trị hóa đơn theo phiên bản",invoice.currency&&invoice.currency!=="VND"?"Chưa xác minh quy đổi VND":money(r.gross_amount_vnd)],["Trạng thái phiên bản",r.status||"Chưa có"]])}</details>`).join("")}${all.length<matching.length?"<p>Có phiên bản thiếu mã hoặc thời điểm biết có múi giờ; chưa dùng để xác định thứ tự.</p>":""}<p>Đây là lịch sử nguồn để đối chiếu; “đã biết” chưa xác nhận hiệu lực chứng từ. Các phiên bản được biết sau lúc chi không điền ngược vào bằng chứng quá khứ. Hit và điểm vẫn theo snapshot đã lưu.</p></div>`;
  }
  return {a5,exception,cashSentence,noP2,score,invoiceVersions,facts,invoiceAmount};
})();
