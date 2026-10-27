"use strict";
globalThis.ReviewWorkflowUI=(()=>{
  const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const labels={pending_review:"Chưa rà lần đầu",pending_final:"Chờ kiểm tra cuối",returned:"Cần rà bổ sung",finalized:"Đã chốt qua hai cấp"};
  const decisions={confirmed_suspicion:"Cần kiểm tra nghi vấn",false_positive:"Hợp lệ / báo động giả",information_gap:"Cần bổ sung bằng chứng",non_compliance:"Vi phạm kiểm soát",confirmed_fraud:"Xác nhận gian lận"};
  const kinds={primary_submitted:"Gửi kết quả rà",returned:"Trả lại để rà bổ sung",finalization_requested:"Kiểm tra cuối",finalization_failed:"Chốt chưa thành công"};
  const when=value=>value?new Date(value).toLocaleString("vi-VN",{timeZone:"Asia/Ho_Chi_Minh"}):"";
  function policy(status){
    const element=document.getElementById("review-workflow-status");if(!element)return;
    element.classList.remove("hidden");
    const budget=document.getElementById("budget");if(budget)budget.disabled=!["chief_accountant","director"].includes(status.principal?.role);
    element.innerHTML="<strong>Luồng duyệt hai cấp</strong><p>Kế toán viên rà hồ sơ → kế toán trưởng hoặc giám đốc kiểm tra và chốt. Người chốt phải khác người rà.</p>"+
      (status.principal?`<p>${esc(status.role_labels[status.principal.role])} · ${esc(status.principal.display_name)}</p>`:"<p>Đã cấu hình quyền; đang chờ bổ sung luồng đăng nhập và cấp tài khoản thực tế.</p>");
  }
  function record(event,title,extraClass=""){
    if(!event)return "";
    const data=event.data||{};
    return `<section class="workflow-record ${extraClass}"><strong>${esc(title)} · ${esc(event.actor?.display_name)}</strong><small>${esc(when(event.event_at))} · giờ Việt Nam</small>${data.decision?`<p>${esc(decisions[data.decision]||data.decision)}</p>`:""}${data.reason?`<p class="workflow-text">${esc(data.reason)}</p>`:""}${data.missing_evidence?`<p class="workflow-text">Cần bổ sung: ${esc(data.missing_evidence)}</p>`:""}${data.active_minutes!=null?`<small>Phút xử lý đã ghi: ${esc(data.active_minutes)}</small>`:""}</section>`;
  }
  function content(data){
    const actor=data.policy?.principal,primary=data.primary,history=data.history||[];
    const last=kind=>[...history].reverse().find(event=>event.kind===kind);
    const final=last("finalized"),intent=history.find(event=>event.event_hash===final?.data.intent_hash)||last("finalization_requested");
    const awaitingMore=data.stage==="finalized"&&(intent||final)?.data.decision==="information_gap";
    const heading=`<h3>Rà soát và kiểm tra kết luận</h3><p class="workflow-status" tabindex="-1" role="status">${esc(awaitingMore?"Đã kiểm tra · chờ bổ sung bằng chứng":labels[data.stage]||data.stage)}</p>`;
    const preview=record(primary,"Kết quả rà lần đầu")+
      (data.stage==="returned"?record(last("returned"),"Yêu cầu rà bổ sung","workflow-returned"):"")+
      (data.stage==="finalized"?record(intent||final,awaitingMore?"Kết quả kiểm tra · cần bổ sung":"Kết luận đã chốt","workflow-finalized"):"");
    // Intent holds the final reason and measured minutes, including a failed attempt.
    const visibleHistory=history.filter(event=>!["finalized","finalization_failed"].includes(event.kind));
    const trail=visibleHistory.length?`<details class="workflow-history"><summary>Lịch sử duyệt · ${visibleHistory.length} bước</summary>${visibleHistory.map(event=>record(event,history.some(item=>item.kind==="finalization_failed"&&item.data.intent_hash===event.event_hash)?"Chốt chưa thành công":kinds[event.kind]||event.kind)).join("")}</details>`:"";
    const warning=data.active_request_count?`<p class="workflow-request-warning">Còn ${esc(data.active_request_count)} yêu cầu tài liệu chưa rà xong. Vào “Bổ sung tài liệu” để nhận và rà lại, hoặc hủy có lý do trước khi chốt kết luận cuối.</p>`:"";
    const summary=heading+warning+preview+trail;
    if(!actor)return summary+"<p>Kế toán viên được gửi kết quả rà. Kế toán trưởng hoặc giám đốc được chốt hoặc trả lại để bổ sung.</p><p>Chức năng ghi nhận sẽ sẵn sàng khi có tài khoản từ luồng đăng nhập. Hồ sơ hiện vẫn xem được.</p>";
    if(data.stage==="finalized"&&!awaitingMore)return summary+"<p>Kết luận và người chốt đã được lưu. Hồ sơ này đang ở chế độ xem.</p>";
    const isPrimary=actor.role==="accountant",canFinal=["chief_accountant","director"].includes(actor.role)&&data.stage==="pending_final";
    if(!isPrimary&&!canFinal)return summary+`<p>${data.stage==="returned"||awaitingMore?"Đang chờ kế toán viên bổ sung và gửi lại kết quả.":"Chưa có kết quả rà lần đầu đang chờ kiểm tra cuối."}</p>`;
    const mode=isPrimary?"primary":"finalize",selected=primary?.data.decision;
    const editingPending=isPrimary&&data.stage==="pending_final";
    const form=`<p>Người thực hiện: <strong>${esc(actor.display_name)}</strong> · ${esc(data.policy.role_labels[actor.role])}</p><input type="hidden" name="workflow_action" value="${mode}"><fieldset class="workflow-decisions"><legend>${isPrimary?"Kết quả đề xuất":"Kết luận sau kiểm tra"}</legend><div class="decision-options">${Object.entries(decisions).map(([value,label])=>`<label><input type="radio" name="workflow_decision" value="${value}" ${selected===value?"checked":""} required>${esc(label)}</label>`).join("")}</div></fieldset><label class="field">Lý do / bằng chứng đã đối chiếu<textarea name="workflow_reason" maxlength="2000" required rows="3"></textarea></label><label class="field">Chứng từ hoặc bằng chứng còn thiếu<textarea name="workflow_missing" maxlength="2000" rows="2"></textarea></label><label class="field">Phút xử lý thực tế · đo bằng đồng hồ<input name="workflow_minutes" type="number" min="0.01" max="1440" step="0.01" required></label><p>Ghi thời gian đã làm; trừ thời gian nghỉ. Đây là công rà ${isPrimary?"lần đầu":"kiểm tra cuối"}, được lưu riêng.</p>${!isPrimary?"<p>Để trả lại, ghi rõ lý do cần rà bổ sung và số phút kiểm tra. Không bắt buộc chọn kết luận.</p>":""}<div class="workflow-error hidden" role="alert" tabindex="-1"></div><div class="workflow-actions"><button type="submit" class="primary-button">${isPrimary?(editingPending?"Gửi bản rà cập nhật":"Gửi kết quả để kiểm tra cuối"):"Chốt kết luận"}</button>${!isPrimary?'<button type="button" class="icon-button" data-return-review>Trả lại để rà bổ sung</button>':""}<button type="button" class="text-button hidden" data-workflow-reload>Tải lại hồ sơ (bỏ nội dung chưa gửi)</button></div>`;
    return summary+(editingPending?`<p>Đã gửi kết quả. Đang chờ kế toán trưởng hoặc giám đốc kiểm tra.</p><details class="workflow-edit"><summary>Sửa kết quả đã gửi</summary><p>Bản cập nhật sẽ thay bản đang chờ kiểm tra; các lần gửi vẫn lưu trong lịch sử.</p>${form}</details>`:form);
  }
  function render(form,data,context){
    form.innerHTML=content(data);
    if(!form.querySelector('[name="workflow_action"]'))return;
    let saving=false;
    function error(message){
      const element=form.querySelector('.workflow-error');
      element.textContent=message;element.classList.remove('hidden');element.focus();context.notice(message);
    }
    async function send(action){
      if(saving)return;
      const value=name=>form.querySelector(`[name="${name}"]`)?.value||"";
      const decision=form.querySelector('[name="workflow_decision"]:checked')?.value;
      const minutes=Number(value("workflow_minutes"));
      const body={scenario:context.scenario,case_id:context.caseId,decision:action==="return"?null:decision,reason:value("workflow_reason").trim(),
        missing_evidence:value("workflow_missing").trim(),active_minutes:minutes,timing_method:"measured_stopwatch",
        expected_event_hash:data.latest_event_hash,expected_scope_hash:data.case_scope_hash};
      if(!body.reason||body.reason.length>2000){error("Ghi lý do đã đối chiếu, tối đa 2.000 ký tự.");return;}
      if(!Number.isFinite(minutes)||minutes<=0||minutes>1440){error("Ghi số phút thực tế lớn hơn 0 và không quá 1.440 phút.");return;}
      if(action!=="return"&&!decision){error("Chọn kết quả đã đối chiếu.");return;}
      if(action!=="return"&&decision==="information_gap"&&!body.missing_evidence){error("Ghi rõ chứng từ hoặc bằng chứng cần bổ sung.");return;}
      saving=true;form.querySelectorAll("button").forEach(b=>b.disabled=true);
      try{await context.api("/api/review-workflow/"+action,body);await context.saved(action);}
      catch(failure){error(failure.message);form.querySelector('[data-workflow-reload]').classList.remove('hidden');}
      finally{saving=false;form.querySelectorAll("button").forEach(b=>b.disabled=false);}
    }
    form.addEventListener("submit",event=>{event.preventDefault();return send(form.querySelector('[name="workflow_action"]').value);});
    form.querySelector('[data-return-review]')?.addEventListener("click",()=>send("return"));
    form.querySelector('[data-workflow-reload]')?.addEventListener("click",()=>context.reload());
  }
  return {policy,content,render};
})();
