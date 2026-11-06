"use strict";
(function(global){
  const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const duration=ms=>{const seconds=Math.floor(Math.max(0,ms)/1000);return [Math.floor(seconds/3600),Math.floor(seconds/60)%60,seconds%60].map(v=>String(v).padStart(2,'0')).join(':');};
  const names={transaction_id:'Mã giao dịch',company_id:'Doanh nghiệp',posted_at:'Ghi sổ',created_at:'Tạo giao dịch',approved_at:'Duyệt',txn_type:'Loại nghiệp vụ',amount_vnd:'Số tiền VND',approval_limit_vnd:'Hạn mức VND',vendor_id:'Nhà cung cấp',employee_id:'Nhân viên nhận',customer_id:'Khách hàng',creator_id:'Người lập',approver_id:'Người duyệt',recipient_account:'Tài khoản nhận',recipient_bank_code:'Mã ngân hàng nhận',debit_account:'Tài khoản Nợ',credit_account:'Tài khoản Có',journal_signature:'Cặp bút toán',accounting_purpose:'Mục đích hạch toán',business_purpose:'Diễn giải',payment_channel:'Kênh thanh toán'};
  function evidenceTable(record){return '<table><tbody>'+Object.entries(record).filter(([k])=>names[k]).map(([k,v])=>`<tr><th>${names[k]}</th><td>${escape(v===''?'Chưa có dữ liệu':v)}</td></tr>`).join('')+'</tbody></table>';}
  function summaryTable(data){
    const progress=`<p><strong>${data.reviewed}/${data.total} phiếu đã rà</strong> · ${Number(data.total_unique_review_minutes).toFixed(2)} phút cho các giao dịch duy nhất đã xác nhận.</p>`;
    if(!data.complete)return progress+`<p class="note">${escape(data.reason)}</p>`;
    return progress+'<div class="table-wrap"><table><thead><tr><th>Doanh nghiệp</th><th>Model</th><th>Đã rà</th><th>Hữu ích</th><th>Chưa đủ căn cứ</th><th>Phút theo danh sách model</th></tr></thead><tbody>'+data.metrics.map(m=>`<tr><td>${escape(m.company_id)}</td><td>${escape(m.algorithm)}</td><td>${m.reviewed}/${m.selected}</td><td>${m.useful}</td><td>${m.unknown}</td><td>${m.full_budget_review_minutes==null?'Chưa đủ phiếu':Number(m.full_budget_review_minutes).toFixed(2)}</td></tr>`).join('')+'</tbody></table></div>';
  }
  global.MLReviewUI={escape,duration,evidenceTable,summaryTable};
  if(!global.document?.getElementById('review-packet'))return;
  const $=id=>document.getElementById(id),formIds=['review-useful','review-action','review-rationale','review-refs'];
  let meta,overview,detail=null,items=[],token=null,busy=false,saving=false,dirty=false,uncertain=false,pauseWhenIdle=false,baseMs=0,syncedAt=0;
  const pid=()=>$('review-packet').value;
  function notice(text,error=false){$('review-notice').textContent=text;$('review-notice').className=error?'error':'note';$('review-notice').hidden=false;if(error)$('review-notice').focus();}
  async function api(path,body,keepalive=false){
    let response;
    try{response=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':meta.csrf_token},body:JSON.stringify(body),keepalive});}
    catch{throw new Error('Mất kết nối. Đồng hồ đã dừng trên màn hình. Tải lại phiếu để kiểm tra kết quả; không tự gửi lại thao tác lưu.');}
    let value;try{value=await response.json();}catch{throw new Error('Chưa đọc được kết quả. Tải lại phiếu trước khi tiếp tục.');}
    if(!response.ok){
      if(response.status===403&&value.error==='Phiên làm việc đã thay đổi. Tải lại trang để tiếp tục.')meta=await api('/api/meta');
      const error=new Error(value.error||'Chưa thực hiện được thao tác.');error.status=response.status;throw error;
    }
    return value;
  }
  const form=()=>({useful:$('review-useful').value,business_action:$('review-action').value,rationale:$('review-rationale').value,evidence_refs:$('review-refs').value});
  function fill(value){$('review-useful').value=value.useful||'';$('review-action').value=value.business_action||'';$('review-rationale').value=value.rationale||'';$('review-refs').value=value.evidence_refs||'';$('review-ack').checked=false;}
  function elapsed(){return baseMs+(detail?.work.timer.running&&token&&!uncertain?Math.min(30000,Math.max(0,performance.now()-syncedAt)):0);}
  function sync(work,nextToken){
    detail.work=work;if(nextToken)token=nextToken;if(!work.timer.running)token=null;
    baseMs=work.timer.elapsed_ms;syncedAt=performance.now();paint();controls();
  }
  function paint(){if(!detail)return;$('review-clock').textContent=duration(elapsed());}
  function controls(){
    const editable=!!detail?.work.can_edit&&!uncertain,live=!!detail?.work.timer.running;
    for(const id of ['review-packet','review-company','review-reload'])$(id).disabled=busy||!overview?.packets.length;
    $('review-list').querySelectorAll('button').forEach(button=>button.disabled=busy);
    for(const id of formIds)$(id).disabled=!editable||saving;
    $('review-ack').disabled=!editable||saving;$('review-action').required=$('review-useful').value==='yes';
    $('review-start').disabled=busy||!editable||live;
    $('review-pause').disabled=busy||!editable||!live||!token;
    $('review-recover').hidden=!detail||!editable||(!live&&!detail.work.timer.expired)||!!token;
    $('review-recover').disabled=busy;
    $('review-draft').disabled=busy||!editable||!detail.work.revision;
    $('review-submit').disabled=busy||!editable||!$('review-ack').checked||elapsed()<=0;
    if(detail){
      $('review-timer-state').textContent=uncertain?'Cần tải lại để kiểm tra phiên':!editable?'Phiếu thuộc người rà khác':live?(token?'Đang đo thời gian kiểm tra':'Đồng hồ đang chạy ở phiên khác'):detail.work.timer.expired?'Phiên cũ hết hạn · chỉ giữ thời gian đã xác nhận':'Đã tạm dừng';
      $('review-owner').textContent=detail.work.owner?`Người rà: ${detail.work.owner.display_name} · ${detail.work.status==='reviewed'?'Đã xác nhận':'Đang rà / bản nháp'}`:'Chưa có người nhận. Bấm bắt đầu để nhận phiếu và đo thời gian.';
    }
    $('review-save-state').textContent=dirty?'Có nội dung chưa lưu.':detail?.work.status==='reviewed'?'Kết quả đã được xác nhận và lưu cùng người rà, căn cứ và thời gian.':'Nội dung chỉ được lưu khi bấm lưu bản nháp hoặc xác nhận đã rà.';
  }
  async function perform(fn){
    if(busy)return;busy=true;controls();
    try{await fn();}
    catch(error){if(!error.status||error.status>=500||[403,409].includes(error.status))uncertain=true;notice(error.message,true);}
    finally{busy=false;saving=false;paint();controls();if(pauseWhenIdle){pauseWhenIdle=false;if(detail?.work.timer.running&&token&&!uncertain)perform(()=>timer('pause'));}}
  }
  async function timer(action){
    const value=await api('/api/ml-reviews/timer',{packet_id:pid(),review_id:detail.review_id,expected_revision:detail.work.revision,action,timer_token:token||''});
    sync(value.work,value.timer_token);if(action==='start')await refreshList();if(value.notice)notice(value.notice);
  }
  async function pauseForSave(){
    if(detail.work.timer.running||detail.work.timer.expired)await timer(token?'pause':'recover');
  }
  async function save(submit){
    saving=true;controls();await pauseForSave();
    const value=await api('/api/ml-reviews/save',{packet_id:pid(),review_id:detail.review_id,expected_revision:detail.work.revision,
      form:form(),submit,acknowledge:submit&&$('review-ack').checked});
    sync(value.work);dirty=false;$('review-ack').checked=false;
    notice(submit?'Đã lưu kết quả rà, căn cứ và thời gian.':'Đã lưu bản nháp.');await refreshList();
  }
  async function beforeSwitch(){
    if(!detail)return;
    if(uncertain){if(dirty)throw new Error('Tải lại phiếu hiện tại trước khi chuyển; nội dung chưa lưu vẫn được giữ trên màn hình.');return;}
    if(detail.work.timer.running&&token)await timer('pause');
    if(dirty&&detail.work.can_edit&&detail.work.revision)await save(false);
    else if(dirty)throw new Error('Bắt đầu nhận phiếu rồi lưu bản nháp trước khi chuyển.');
  }
  function listMarkup(){
    const labels={unstarted:'Chưa rà',draft:'Đang rà / bản nháp',reviewed:'Đã xác nhận'};
    $('review-list').innerHTML=items.map(unit=>`<button type="button" class="unit ${detail?.review_id===unit.review_id?'selected':''}" data-unit="${escape(unit.review_id)}"><strong>${escape(unit.transaction_id)}</strong><span>${escape(unit.company_id)} · ${labels[unit.status]}</span></button>`).join('')||'<p>Không có phiếu trong phạm vi đang chọn.</p>';
  }
  async function refreshList(){
    const value=await api('/api/ml-reviews/units?'+new URLSearchParams({packet:pid(),company:$('review-company').value}));items=value.items;
    $('review-progress').textContent=`${value.reviewed}/${value.total} phiếu đã xác nhận · giao dịch trùng giữa model chỉ rà một lần.`;listMarkup();
  }
  async function openUnit(rid,preserve=false){
    const draft=preserve&&dirty?form():null;
    const value=await api('/api/ml-reviews/detail?'+new URLSearchParams({packet:pid(),review:rid}));
    detail=value;token=null;uncertain=false;dirty=!!draft;
    $('review-detail').hidden=$('review-work').hidden=false;
    $('review-title').textContent=`${value.company_id} · Giao dịch ${value.transaction_id}`;
    $('review-evidence').innerHTML=evidenceTable(value.evidence.source_record);
    $('review-limits').innerHTML='<ul>'+(value.evidence.limitations||[]).map(text=>`<li>${escape(text)}</li>`).join('')+'</ul>';
    $('review-reference').textContent=`${value.review_id} · SHA256 ${value.evidence_sha256}`;
    fill(draft||value.work.form);sync(value.work);listMarkup();
    if(draft)notice('Đã tải lại trạng thái máy chủ; nội dung chưa lưu vẫn được giữ trên màn hình.');
    const route=new URLSearchParams({packet:pid(),company:value.company_id,review:rid});global.history.replaceState(null,'','/ml-reviews?'+route);
  }
  async function loadUnits(preferred){
    detail=null;token=null;dirty=false;uncertain=false;$('review-detail').hidden=$('review-work').hidden=true;
    $('review-summary-body').innerHTML='';$('review-export').href='/api/ml-reviews/export?'+new URLSearchParams({packet:pid()});
    await refreshList();const selected=items.find(u=>u.review_id===preferred)||items[0];if(selected)await openUnit(selected.review_id);
  }
  function companies(preferred){
    const packet=overview.packets.find(p=>p.packet_id===pid());
    $('review-company').innerHTML=(packet?.companies||[]).map(c=>`<option value="${escape(c)}">${escape(c)}</option>`).join('');
    if(packet?.companies.includes(preferred))$('review-company').value=preferred;
  }
  $('review-list').addEventListener('click',event=>{const button=event.target.closest('button[data-unit]');if(!button||button.disabled)return;perform(async()=>{await beforeSwitch();await openUnit(button.dataset.unit);});});
  $('review-start').addEventListener('click',()=>perform(()=>timer('start')));
  $('review-pause').addEventListener('click',()=>perform(()=>timer('pause')));
  $('review-recover').addEventListener('click',()=>perform(()=>timer('recover')));
  $('review-draft').addEventListener('click',()=>perform(()=>save(false)));
  $('review-form').addEventListener('submit',event=>{event.preventDefault();if(!$('review-submit').disabled)perform(()=>save(true));});
  for(const id of formIds)$(id).addEventListener('input',()=>{dirty=true;$('review-ack').checked=false;controls();});
  $('review-useful').addEventListener('change',()=>{dirty=true;$('review-ack').checked=false;controls();});
  $('review-ack').addEventListener('change',controls);
  $('review-reload').addEventListener('click',()=>perform(async()=>{
    if(!detail)return loadUnits();const rid=detail.review_id;
    if(!uncertain&&detail.work.timer.running&&token)await timer('pause');
    await openUnit(rid,true);await refreshList();
  }));
  $('review-packet').addEventListener('change',()=>perform(async()=>{
    // Timer requests must still target the old packet while settling the old unit.
    const next=pid(),old=detail?.packet_id;if(old)$('review-packet').value=old;
    try{await beforeSwitch();$('review-packet').value=next;companies();await loadUnits();}catch(error){if(old)$('review-packet').value=old;throw error;}
  }));
  $('review-company').addEventListener('change',()=>perform(async()=>{
    const next=$('review-company').value,old=detail?.company_id;
    try{await beforeSwitch();$('review-company').value=next;await loadUnits();}catch(error){if(old)$('review-company').value=old;throw error;}
  }));
  $('review-summary').addEventListener('click',()=>perform(async()=>{
    const result=await api('/api/ml-reviews/summary?'+new URLSearchParams({packet:pid()}));$('review-summary-body').innerHTML=summaryTable(result);
  }));
  document.addEventListener('visibilitychange',()=>{if(document.hidden&&detail?.work.timer.running&&token){if(busy)pauseWhenIdle=true;else perform(()=>timer('pause'));}});
  global.addEventListener('pagehide',()=>{
    if(detail?.work.timer.running&&token&&!busy&&!uncertain)api('/api/ml-reviews/timer',{
      packet_id:pid(),review_id:detail.review_id,expected_revision:detail.work.revision,action:'pause',timer_token:token},true).catch(()=>{});
  });
  global.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
  setInterval(()=>{paint();controls();},1000);
  setInterval(()=>{if(!document.hidden&&!busy&&!uncertain&&detail?.work.timer.running&&token)perform(()=>timer('heartbeat'));},10000);
  (async()=>{
    try{
      meta=await api('/api/meta');overview=await api('/api/ml-reviews');
      $('review-access').textContent=(overview.qa?'MÔ PHỎNG / QA · Dữ liệu và kết quả thử nghiệm. ':'')+overview.principal.display_name+' · Chỉ xem và ghi phiếu trong phạm vi doanh nghiệp được cấp.';
      $('review-manager').hidden=!overview.can_summarize;
      $('review-packet').innerHTML=overview.packets.map((p,i)=>`<option value="${escape(p.packet_id)}">Lượt ${i+1} · ${escape(p.created_at.slice(0,10))} · ${p.source_kind==='synthetic_demo'?'Mô phỏng':'Dữ liệu đã khóa'}</option>`).join('');
      if(!overview.packets.length){notice('Chưa có gói phiếu rà được nạp cho tài khoản. Quản trị viên cần kết nối gói so sánh đã khóa.');controls();return;}
      const query=new URLSearchParams(global.location.search),requested=query.get('packet');if(overview.packets.some(p=>p.packet_id===requested))$('review-packet').value=requested;
      companies(query.get('company'));await perform(()=>loadUnits(query.get('review')));
    }catch(error){notice(error.message,true);controls();}
  })();
})(globalThis);
