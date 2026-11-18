'use strict';
(() => {
  const $=id=>document.getElementById(id),mount=location.pathname.startsWith('/agent2/')?'/agent2':'';
  const node=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=String(text);return n;};
  const labels={confirmed_risk:'Có vấn đề cần xử lý',legitimate:'Không phát hiện vấn đề',inconclusive:'Chưa đủ căn cứ'};
  const taskLabels={open:'Mở mới',in_progress:'Đang xử lý',waiting_external:'Chờ bổ sung',completed:'Đã hoàn tất',cancelled:'Đã hủy'};
  const roles={candidate:'Giao dịch ứng viên',prior_payment_evidence:'Thanh toán lịch sử',master_context:'Hồ sơ đối tượng',supporting_document:'Chứng từ liên quan',invoice:'Hóa đơn',payment_allocation:'Phân bổ thanh toán'};
  let token='',actor='',context='',listing=null,backlogState=null,company='',run='',desiredSnapshot='',epoch=0,controller=null,state=null,selected='',lease=null,beat=null,pending=null,dirty=false;
  const dirtyParts={};function setDirty(part,value){dirtyParts[part]=value;dirty=Object.values(dirtyParts).some(Boolean);}function resetDirty(){for(const key of Object.keys(dirtyParts))delete dirtyParts[key];dirty=false;}
  const base=()=>'/api/v1/companies/'+encodeURIComponent(company)+'/pipeline-workspace';
  const path=()=>base()+'/runs/'+encodeURIComponent(run);
  const bklMode=()=>$('bw-backlog-mode')?.value||'shadow';
  const bklKey=()=>'agent2.bundle.backlog.'+actor+'.'+context+'.'+company+'.'+bklMode();
  function savedBacklogReq(){try{return JSON.parse(sessionStorage.getItem(bklKey()));}catch{return null;}}
  function clearBacklog(){backlogState=null;$('bw-backlog-panel').hidden=true;$('bw-backlog-summary').replaceChildren();$('bw-backlog-list').replaceChildren();$('bw-backlog-periods').textContent='';$('bw-backlog-status').textContent='';$('bw-backlog-empty').hidden=true;$('bw-backlog-reeval').disabled=true;}
  function executionLabel(v){if(v.execution_location==='cloud_ciphertext_only')$('bw-mode').textContent=(v.queue_mode==='active'?'Hàng đợi chính thức (Pilot Active) · ':'')+'HE trên cloud cho phần khả dụng · Chỉ gửi bản mã; giải mã, gộp vụ và xét ngân sách tại doanh nghiệp. Luật/model chưa hỗ trợ vẫn chưa khả dụng.';}
  function syncExecutionMode(mode){if([...$('bw-execution-mode').options].some(o=>o.value===mode))$('bw-execution-mode').value=mode;runControls();}
  const notice=text=>{$('bw-notice').textContent=text;$('bw-notice').hidden=!text;};
  function stop(){clearInterval(beat);beat=null;lease=null;pending=null;}
  function clear(){epoch++;controller?.abort();controller=new AbortController();stop();state=null;selected='';resetDirty();$('bw-report').hidden=true;$('bw-pilot-warning').hidden=true;$('bw-pilot-warning').textContent='';$('bw-detail').hidden=true;$('bw-detail').replaceChildren();$('bw-meta').replaceChildren();$('bw-summary').replaceChildren();$('bw-cases').replaceChildren();$('bw-resume').hidden=true;$('bw-resume').disabled=false;$('bw-limits').replaceChildren();$('bw-manage').hidden=!(listing?.company_id===company&&listing.can_manage);notice('');}
  function remember(){const snapshot=$('bw-snapshot').value||desiredSnapshot;history.replaceState(null,'',location.pathname+'#'+new URLSearchParams({company,...(run?{run}:{}),...(snapshot?{snapshot}:{})}));for(const a of document.querySelectorAll('header a[href]')){const page=new URL(a.href).pathname.split('/').pop();if(['workspace','data-import','pipeline-workspace','pipeline-releases','label-verification','batch-training'].includes(page))a.href=mount+'/'+page+'#company='+encodeURIComponent(company);}try{sessionStorage.setItem('agent2.company.selection',JSON.stringify({version:1,actor,context,company,page:'pipeline-workspace',...(run?{run}:{})}));}catch{/* optional preference, never permission */}}
  async function api(url,body){const headers={'X-Platform':'1','X-Session':token};if(body!==undefined)headers['Content-Type']='application/json';let r;try{r=await fetch(mount+url,{method:body===undefined?'GET':'POST',headers,body:body===undefined?undefined:JSON.stringify(body),cache:'no-store',signal:controller?.signal});}catch(err){if(err.name==='AbortError')throw err;throw Error('M\u1ea5t k\u1ebft n\u1ed1i. Th\u1eed l\u1ea1i \u0111\u1ec3 ti\u1ebfp t\u1ee5c \u0111\u00fang y\u00eau c\u1ea7u \u0111\u00e3 g\u1eedi.');}const v=await r.json();if(!r.ok){const e=Error(v.errors?.map(x=>x.message+' '+x.action).join('\n')||'Chưa thực hiện được.');e.status=r.status;e.code=v.errors?.[0]?.code;throw e;}return v;}
  function summary(){const s=state.summary;const t=state.task_counts||{},d=state.document_counts||{};$('bw-workflow-summary').textContent='Công việc: '+((t.open||0)+(t.in_progress||0)+(t.waiting_external||0))+' đang mở · '+(t.completed||0)+' đã hoàn tất. Chứng từ: '+(d.pending_verification||0)+' chờ xác minh · '+(d.present||0)+' đã xác minh.';$('bw-summary').replaceChildren(...[['Vụ trong lần rà',s.total_cases],['Chưa ghi kết quả',s.pending_cases],['Đã ghi kết quả',s.reviewed_cases],['Chưa đủ căn cứ',s.outcomes.inconclusive]].map(([label,value])=>{const d=node('div');d.className='metric';d.append(node('strong',value),node('span',label));return d;}));}
  function renderCases(){summary();$('bw-empty').hidden=!!state.cases.length;$('bw-cases').replaceChildren(...state.cases.map(c=>{const b=node('button',c.question+' · '+(labels[c.review.feedback?.outcome]||'Chưa ghi kết quả'));b.className='quiet';b.dataset.review=c.review_id;b.onclick=()=>{if(dirty&&!confirm('Bỏ nội dung chưa lưu để mở vụ khác?'))return;stop();epoch++;resetDirty();selected=c.review_id;detail(c);};return b;}));}
  function field(label,tag='textarea'){const wrap=node('label',label),input=node(tag);input.id='bw-'+label.length+'-'+Math.random().toString(36).slice(2);if(tag==='textarea'){input.rows=3;input.maxLength=4000;}wrap.append(input);return {wrap,input};}
  function download(content,name,mime){const u=URL.createObjectURL(new Blob([content],{type:mime})),a=node('a');a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);}
  function detail(item){const e=epoch,box=$('bw-detail'),reviewPath=path()+'/reviews/'+item.review_id;box.hidden=false;box.replaceChildren(node('h2',item.question),node('p','Vì sao cần kiểm tra? '+item.why),node('p','Bước tiếp theo: '+item.next_step),node('p',item.source_kind==='simulated'?'Dữ liệu mô phỏng':'Bản ghi xuất từ nguồn; cần đối chiếu chứng từ gốc'));
    box.append(node('p','Giao dịch ứng viên: '+item.candidate_ids.join(', ')),node('p','Giao dịch lịch sử làm bằng chứng: '+(item.evidence_transaction_ids.join(', ')||'Chưa có trong nguồn đã khóa')));
    const evidence=node('div');box.append(node('h3','Cần đối chiếu căn cứ nào?'),evidence);const refs=[];
    function addRef(id,label,record){const existing=refs.find(r=>r.value===id);if(existing){existing.closest('details').querySelector('summary').textContent=label;return;}const d=node('details'),summary=node('summary',label),labelEl=node('label'),check=node('input');check.type='checkbox';check.value=id;check.checked=!!item.review.feedback?.evidence_ids.includes(id);check.onchange=()=>setDirty('review',true);refs.push(check);labelEl.className='check';labelEl.append(check,node('span','Tôi đã xem căn cứ này'));d.append(summary);if(record)d.append(node('pre',JSON.stringify(record,null,2)));d.append(labelEl);evidence.append(d);}
    for(const ev of item.evidence)addRef(ev.evidence_id,(roles[ev.role]||'Căn cứ liên quan')+' · '+(ev.source_kind==='simulated'?'mô phỏng':'bản ghi nguồn')+' · chưa xác minh chứng từ gốc',ev.record);
    for(const gap of item.source_limits)box.append(node('p',gap));
    const fields=node('fieldset'),out=field('Kết quả rà','select'),ex=field('Đã kiểm tra và giải thích được điều gì?'),act=field('Hành động tiếp theo'),missing=field('Tài liệu còn thiếu'),use=field('Cảnh báo có giúp ích không?','select');
    out.input.id='bw-outcome';ex.input.id='bw-explanation';act.input.id='bw-action';missing.input.id='bw-missing';use.input.id='bw-usefulness';
    const choose=node('option','Chọn kết quả');choose.value='';out.input.append(choose);for(const [v,label] of Object.entries(labels)){const o=node('option',label);o.value=v;out.input.append(o);}
    for(const [v,label] of [['not_assessed','Chưa đánh giá'],['yes','Có'],['no','Không']]){const o=node('option',label);o.value=v;use.input.append(o);}
    const checked=node('input');checked.type='checkbox';checked.id='bw-checks';const checkedLabel=node('label');checkedLabel.className='check';checkedLabel.append(checked,node('span','Đã đối chiếu đủ căn cứ cho kết luận này'));
    for(const f of [out,ex,act,missing,use]){fields.append(f.wrap);f.input.oninput=()=>setDirty('review',true);}checked.onchange=()=>setDirty('review',true);fields.append(checkedLabel);box.append(fields);
    let current=item.review;const old=current.feedback;if(old){out.input.value=old.outcome;ex.input.value=old.explanation;act.input.value=old.action;missing.input.value=old.missing_materials;use.input.value=old.usefulness;checked.checked=old.checks_completed;}
    const attachments=node('details');attachments.append(node('summary','Tài liệu đã bổ sung trước đây'));attachments.hidden=!current.attachments.length;box.append(attachments);
    for(const a of current.attachments){const b=node('button',a.name+' · tệp đính kèm cũ, chưa xác minh');b.className='quiet';b.onclick=async()=>{try{const file=await api(reviewPath+'/attachments/'+a.id);if(e!==epoch||selected!==item.review_id)return;download(Uint8Array.from(atob(file.content),c=>c.charCodeAt(0)),file.name,'application/octet-stream');}catch(err){notice(err.message);}};attachments.append(b);addRef(a.id,a.name+' · tài liệu bổ sung, chưa xác minh');}
    const start=node('button','Bắt đầu rà'),save=node('button','Lưu kết quả rà'),time=node('span',Math.round(current.active_seconds)+' giây đã lưu'),msg=node('p');start.id='bw-start';save.id='bw-save';save.disabled=true;const buttons=node('div');buttons.className='actions';buttons.append(start,save,time);box.append(buttons,msg);
    start.onclick=async()=>{start.disabled=true;try{const v=await api(reviewPath+'/start',{});if(e!==epoch||selected!==item.review_id)return;lease=v.lease;save.disabled=false;msg.textContent='Đang rà. Đối chiếu nguồn rồi ghi kết quả.';beat=setInterval(async()=>{if(document.hidden||!lease)return;try{const v=await api(reviewPath+'/heartbeat',{lease});if(e===epoch)time.textContent=Math.round(current.active_seconds+v.active_seconds)+' giây kết nối';}catch(err){stop();start.disabled=false;save.disabled=true;msg.textContent='Kết nối bị gián đoạn. Bấm Bắt đầu rà để tiếp tục.';}},5000);}catch(err){start.disabled=false;notice(err.message);}};
    function frozen(on){fields.disabled=on;for(const r of refs)r.disabled=on;}
    taskForm(box,item,reviewPath,e,ref=>addRef(ref.evidence_id,ref.name+' · v'+ref.version+' · '+({present:'đã xác minh',rejected:'bị từ chối',pending_verification:'chờ xác minh'}[ref.verification_status]||'chưa xác minh')));
    save.onclick=async()=>{if(!lease&&!pending)return;if(!pending)pending={expected_revision:current.revision,lease,request_id:crypto.randomUUID(),feedback:{outcome:out.input.value,usefulness:use.input.value,explanation:ex.input.value,action:act.input.value,missing_materials:missing.input.value,evidence_ids:refs.filter(r=>r.checked).map(r=>r.value),checks_completed:checked.checked}};save.disabled=true;frozen(true);
      try{const v=await api(reviewPath+'/save',pending);if(e!==epoch)return;current=v;item.review=v;pending=null;lease=null;setDirty('review',false);clearInterval(beat);save.disabled=true;start.disabled=false;frozen(false);time.textContent=Math.round(v.active_seconds)+' giây đã lưu';msg.textContent='Đã lưu kết quả phiên bản '+v.revision+' trên server.';const next=await api(path()+'/report');if(e===epoch&&state){Object.assign(state,{summary:next.summary,task_counts:next.task_counts,document_counts:next.document_counts});renderCases();}}
      catch(err){if(e!==epoch)return;notice(err.message);if(err.status){pending=null;frozen(false);}save.disabled=false;if(err.status===409){stop();start.disabled=false;save.disabled=true;}msg.textContent=err.status?'Kiểm tra nội dung hoặc tải lại phiếu.':'Mất phản hồi. Bấm lưu lại để gửi đúng yêu cầu cũ.';}};
  }
  function taskForm(box,item,reviewPath,e,addEvidence){
    const section=node('section');section.append(node('h3','Xử lý vụ này'));box.append(section);
    if(!state.tasks_available){section.append(node('p','Chưa kết nối kho công việc.'));return;}
    const list=node('div'),form=node('fieldset'),type=field('Loại công việc','select'),title=field('Nội dung công việc','input'),todo=field('Cần người phụ trách làm gì?'),reason=field('Lý do giao việc'),who=field('Bộ phận phụ trách','select'),due=field('Hạn xử lý (giờ Việt Nam)','input');
    type.input.id='bw-task-type';title.input.id='bw-task-title';todo.input.id='bw-task-todo';reason.input.id='bw-task-reason';who.input.id='bw-task-assignee';due.input.id='bw-task-due';due.input.type='datetime-local';title.input.maxLength=1000;
    for(const [v,label] of [['request_documents','Bổ sung chứng từ'],['reconcile_payment','Đối chiếu thanh toán'],['verify_control','Kiểm tra quy trình'],['remediate_issue','Xử lý vấn đề đã ghi nhận']]){const o=node('option',label);o.value=v;type.input.append(o);}
    title.input.value='Đối chiếu và bổ sung căn cứ cho vụ';todo.input.value=item.next_step;reason.input.value=item.why;
    const button=node('button','Giao việc'),status=node('p');button.id='bw-task-create';button.disabled=true;list.id='bw-task-list';
    for(const f of [type,title,todo,reason,who,due]){form.append(f.wrap);f.input.oninput=()=>setDirty('create',true);}form.prepend(node('legend','Giao việc mới'));
    section.append(list,form,button,status,node('p','Công việc giữ đúng nguồn của vụ. Giao việc không tự đóng vụ hoặc xác nhận gian lận.'));
    const key='agent2.bundle.task.'+actor+'.'+context+'.'+company+'.'+item.review_id;let request=null;
    try{request=JSON.parse(sessionStorage.getItem(key));}catch{/* optional local recovery */}
    const current=()=>e===epoch&&selected===item.review_id&&section.isConnected;
    async function refreshReport(){const next=await api(path()+'/report');if(!current()||!state)return;Object.assign(state,{summary:next.summary,task_counts:next.task_counts,document_counts:next.document_counts});for(const c of next.cases){const old=state.cases.find(x=>x.review_id===c.review_id);if(old){old.tasks=c.tasks;old.documents=c.documents;}}summary();}
    const lifecycle=new BundleRemediation({host:list,api,url:reviewPath+'/remediation',current,storageKey:key+'.lifecycle',legacyAttachments:item.review.attachments,addEvidence,changed:refreshReport,dirty:value=>setDirty('remediation',value),download});
    function display(tasks){item.tasks=tasks;lifecycle.load();}
    display(item.tasks||[]);
    api(reviewPath+'/tasks').then(v=>{if(!current())return;who.input.replaceChildren(...v.assignees.map(a=>{const o=node('option',a.label);o.value=a.key;return o;}));display(v.tasks);if(request){type.input.value=request.task_type;title.input.value=request.title;todo.input.value=request.what_to_do;reason.input.value=request.reason;who.input.value=request.assignee_key;due.input.value=request.due_at.replace(/\+07:00$/,'');form.disabled=true;button.textContent='Tiếp tục giao việc đã gửi';}button.disabled=false;}).catch(err=>{if(current())status.textContent=err.message;});
    button.onclick=async()=>{if(!request){if(!due.input.value){status.textContent='Chọn hạn xử lý và bộ phận phụ trách trước khi giao việc.';return;}request={task_type:type.input.value,title:title.input.value,what_to_do:todo.input.value,reason:reason.input.value,assignee_key:who.input.value,due_at:due.input.value+':00+07:00',request_id:crypto.randomUUID()};try{sessionStorage.setItem(key,JSON.stringify(request));}catch{/* server dedup still applies */}}button.disabled=true;form.disabled=true;
      try{const v=await api(reviewPath+'/tasks',request);if(!current())return;request=null;setDirty('create',false);try{sessionStorage.removeItem(key);}catch{/* optional recovery */}status.textContent=v.created?'Đã giao việc và lưu trên server.':'Công việc đã có; không tạo trùng.';button.textContent='Giao việc';const next=await api(reviewPath+'/tasks');if(current()){display(next.tasks);await refreshReport();}}
      catch(err){if(!current())return;if(err.status){request=null;try{sessionStorage.removeItem(key);}catch{}}status.textContent=err.message;}
      finally{if(current()){button.disabled=false;form.disabled=!!request;}}
    };
  }
  function syncBacklogControls(){
    const b=backlogState;if(!b?.available){$('bw-backlog-reeval').disabled=true;return;}
    const req=savedBacklogReq();
    if(req?.target_period_key){
      $('bw-backlog-period').value=req.target_period_key;
      $('bw-backlog-period').disabled=true;
      $('bw-backlog-reeval').textContent='Tiếp tục xét lại kỳ '+req.target_period_key;
      $('bw-backlog-reeval').disabled=!b.can_reevaluate;
      return;
    }
    $('bw-backlog-period').disabled=!b.can_reevaluate;
    $('bw-backlog-reeval').textContent='Xét lại vụ chờ sang kỳ mới';
    $('bw-backlog-reeval').disabled=!b.can_reevaluate||!b.summary.waiting_count||!$('bw-backlog-period').value.trim();
  }
  function renderBacklogItems(){
    if(!backlogState?.available)return;
    const mode=$('bw-backlog-filter').value;
    const items=backlogState.items.filter(x=>{
      const isDef=x.decision==='budget_deferred'||x.backlog_reason_code==='budget_exhausted';
      const isBelow=x.decision==='below_threshold'||x.backlog_reason_code==='below_admission_threshold';
      if(mode==='budget_deferred')return isDef;
      if(mode==='below_threshold')return isBelow;
      if(mode==='other')return !isDef&&!isBelow;
      return true;
    });
    $('bw-backlog-list').replaceChildren(...items.map(it=>{
      const card=node('article');card.className='bw-backlog-item';card.dataset.backlogCase=it.case_id;card.dataset.decision=it.decision;
      card.append(node('h3',it.question+' · '+it.reason_label_vi));
      card.append(node('p','Mã vụ: '+it.case_id+' · Kỳ phát sinh: '+it.origin_period_key+(it.period_key!==it.origin_period_key?' (kỳ xét gần nhất: '+it.period_key+')':'')+' · Đã chờ: '+it.age_hours+' giờ'));
      card.append(node('p','Giao dịch ứng viên: '+it.candidate_ids.join(', ')+' · Bằng chứng lịch sử: '+(it.evidence_transaction_ids.join(', ')||'Chưa có')+(it.snapshot_id?' · Snapshot: '+it.snapshot_id:'')));
      const fin=it.financial_summary||{};
      if(fin.discrepancy_amount_vnd!=null)card.append(node('p','Chênh lệch ghi nhận trong nguồn: '+fin.discrepancy_amount_vnd+' VND (chưa phải tổn thất đã xác nhận)'));
      else if(fin.candidate_amount_vnd!=null)card.append(node('p','Giá trị giao dịch ứng viên: '+fin.candidate_amount_vnd+' VND'));
      return card;
    }));
    $('bw-backlog-empty').hidden=items.length>0;
    const isAct=backlogState.queue_mode==='active';
    $('bw-backlog-empty').textContent=backlogState.items.length?'Không có vụ chờ nào thuộc nhóm lọc đang chọn.':('Hiện không có vụ nào đang chờ trong backlog '+(isAct?'chính thức (Pilot Active)':'shadow')+' của doanh nghiệp này.');
  }
  function renderBacklog(b){
    backlogState=b;$('bw-backlog-panel').hidden=!b?.available;
    if(!b?.available)return;
    const isAct=b.queue_mode==='active';
    $('bw-backlog-heading').textContent=isAct?'Hàng đợi chờ xét (Backlog Pilot Active)':'Hàng đợi chờ xét (Backlog shadow)';
    $('bw-backlog-hint').textContent=isAct?'Các vụ chờ trong hàng đợi chính thức (Pilot Active) do hết ngân sách kỳ hiện tại hoặc chưa đạt mức tiếp nhận. Vụ chờ không tự hết hạn.':'Các vụ tạm hoãn do hết ngân sách kỳ hiện tại hoặc chưa đạt mức ưu tiên tiếp nhận. Vụ chờ không tự hết hạn và chưa đẩy sang hàng đợi chính thức.';
    const s=b.summary,maxAge=s.age_hours?.max_hours!=null?s.age_hours.max_hours+' giờ':'0 giờ';
    $('bw-backlog-summary').replaceChildren(...[['Đang chờ xét',s.waiting_count],['Chờ ngân sách kỳ sau',s.budget_deferred_count],['Dưới mức tiếp nhận',s.below_threshold_count],['Tuổi chờ lớn nhất',maxAge]].map(([label,value])=>{const d=node('div');d.className='metric';d.append(node('strong',value),node('span',label));return d;}));
    $('bw-backlog-periods').textContent=b.budget_periods?.length?('Ngân sách '+(isAct?'Pilot Active':'shadow')+' theo kỳ: '+b.budget_periods.map(p=>p.period_key+' ('+p.reserved_count+'/'+p.budget_limit+' vụ, còn '+p.remaining+')').join(' · ')):'Chưa phát sinh kỳ ngân sách '+(isAct?'Pilot Active':'shadow')+' nào.';
    $('bw-backlog-period').placeholder=b.period_kind==='calendar_month_vn'?'Ví dụ: 2026-12':'Ví dụ: 2026-W48';
    const pat=b.period_kind==='calendar_month_vn'?/^\d{4}-\d{2}$/:/^\d{4}-W\d{2}$/;
    const curVal=$('bw-backlog-period').value.trim();
    const latest=b.budget_periods?.length?b.budget_periods[b.budget_periods.length-1].period_key:'';
    if(!savedBacklogReq()&&(!curVal||!pat.test(curVal)||(latest&&curVal<=latest)))$('bw-backlog-period').value=b.suggested_next_period_key||'';
    syncBacklogControls();renderBacklogItems();
  }
  $('bw-backlog-filter').onchange=renderBacklogItems;
  $('bw-backlog-mode').onchange=async()=>{const e=epoch;$('bw-backlog-status').textContent='';try{const bkl=await api(base()+'/backlog'+(bklMode()==='active'?'/active':''));if(e===epoch)renderBacklog(bkl);}catch(err){if(e===epoch&&err.name!=='AbortError')$('bw-backlog-status').textContent=err.message;}};
  $('bw-backlog-period').oninput=syncBacklogControls;
  $('bw-backlog-reeval').onclick=async()=>{
    if(!backlogState?.can_reevaluate)return;
    if(dirty&&!confirm('Bỏ nội dung chưa lưu để xét lại backlog sang kỳ mới?'))return;
    const e=epoch,qMode=bklMode();let req=savedBacklogReq();
    if(!req){
      const target=$('bw-backlog-period').value.trim();
      if(!target){$('bw-backlog-status').textContent='Nhập kỳ ngân sách mới trước khi xét lại.';return;}
      req={target_period_key:target,request_id:crypto.randomUUID(),...(qMode==='active'?{mode:'active'}:{})};
      try{sessionStorage.setItem(bklKey(),JSON.stringify(req));}catch{/* server dedup applies */}
    }
    $('bw-backlog-reeval').disabled=true;$('bw-backlog-period').disabled=true;
    $('bw-backlog-status').textContent='Đang xét lại vụ chờ sang kỳ '+req.target_period_key+'...';
    try{
      const res=await api(base()+'/backlog/reevaluate',req);
      if(e!==epoch)return;
      try{sessionStorage.removeItem(bklKey());}catch{}
      const qLabel=res.queue_mode==='active'?'hàng đợi chính thức (Pilot Active)':'hàng đợi shadow';
      const msg='Đã xét lại kỳ '+res.target_period_key+': tiếp nhận '+res.promoted_count+' vụ vào '+qLabel+', còn '+res.still_waiting_count+' vụ tiếp tục chờ (ngân sách '+res.budget_status.period_key+': '+res.budget_status.reserved_count+'/'+res.budget_status.budget_limit+' vụ).';
      if(res.created_runs?.length){
        run=res.created_runs[0];remember();await loadList(run);
        if(company===res.company_id)$('bw-backlog-status').textContent=msg+' Đã mở lượt rà cho các vụ vừa tiếp nhận: '+res.created_runs.join(', ')+'.';
      }else{
        renderBacklog(res.backlog);
        $('bw-backlog-status').textContent=msg;
      }
    }catch(err){
      if(e!==epoch||err.name==='AbortError')return;
      if(err.status){try{sessionStorage.removeItem(bklKey());}catch{}}
      $('bw-backlog-status').textContent=err.message;
      syncBacklogControls();
    }
  };
  async function loadRun(){clear();const e=epoch;if(!run)return;syncExecutionMode(listing?.runs.find(p=>p.run_id===run)?.execution_mode);try{const v=await api(path());if(e!==epoch)return;state=v;$('bw-report').hidden=false;const isAct=v.queue_mode==='active';$('bw-pilot-warning').hidden=!v.simulated_source_warning;$('bw-pilot-warning').textContent=v.simulated_source_warning||'';$('bw-cases-heading').textContent=isAct?'Vụ đã được tiếp nhận vào hàng đợi chính thức (Pilot Active)':'Vụ đã được tiếp nhận vào hàng đợi shadow';$('bw-mode').textContent=(isAct?'Hàng đợi chính thức (Pilot Active)':'Hàng đợi shadow')+' · Phân tích tại doanh nghiệp · '+v.queue_summary.total_cases+' vụ được xét trong lần chạy.';const b=v.baseline;$('bw-baseline').textContent=b?.catalogue_size?'Phạm vi đối chiếu: '+b.catalogue_size+' luật, kết hợp các nhánh khả dụng theo phiên bản đã duyệt. '+b.limitation:'Lượt cũ chưa lưu phạm vi luật; không suy thành baseline 35 luật.';$('bw-meta').replaceChildren(...['snapshot_id','run_id','bundle_id','as_of'].flatMap(k=>[node('dt',k),node('dd',v[k])]));$('bw-limits').replaceChildren(...v.source_status.map(x=>node('li',x.name+' - '+Object.entries(x.statuses).map(([k,n])=>( {available:'Kh\u1ea3 d\u1ee5ng',partial:'M\u1edbi ph\u00e2n t\u00edch m\u1ed9t ph\u1ea7n',unavailable:'Ch\u01b0a kh\u1ea3 d\u1ee5ng',not_applicable:'Kh\u00f4ng \u00e1p d\u1ee5ng'}[k]||'C\u00f3 gi\u1edbi h\u1ea1n')+': '+n).join(', '))));renderCases();executionLabel(v);syncExecutionMode(v.execution_location);}catch(err){if(e===epoch&&err.name!=='AbortError'){notice(err.message);if(err.code==='PIPELINE_RUN_PENDING')$('bw-resume').hidden=false;}}}
  async function loadList(wanted){clear();if(listing?.company_id!==company){listing=null;clearBacklog();$('bw-snapshot').replaceChildren();$('bw-run').replaceChildren();$('bw-lane').value='staging';$('bw-backlog-mode').value='shadow';}const e=epoch;$('bw-run').disabled=true;$('bw-snapshot').disabled=true;$('bw-analyze').disabled=true;$('bw-backlog-status').textContent='';try{const [v,bkl]=await Promise.all([api(base()),api(base()+'/backlog'+(bklMode()==='active'?'/active':''))]);if(e!==epoch)return;catalog(v);renderBacklog(bkl);const o=node('option','Chọn lần phân tích');o.value='';$('bw-run').replaceChildren(o,...v.runs.map(r=>{const x=node('option',new Date(r.created_at).toLocaleString('vi-VN')+' · '+(r.queue_mode==='active'?'[Pilot Active] · ':'')+(r.origin==='backlog_reevaluation'?'Tiếp nhận backlog ('+r.period_key+') · ':'')+r.run_id);x.value=r.run_id;return x;}));$('bw-run').disabled=false;run=v.runs.some(r=>r.run_id===wanted)?wanted:'';$('bw-run').value=run;remember();if(run)await loadRun();}catch(err){if(e===epoch&&err.name!=='AbortError')notice(err.message);}}
  function syncLaneExecutionModes(){if(!listing)return;const curLane=$('bw-lane').value,modes=listing.lane_execution_modes?.[curLane]||listing.execution_modes||['enterprise_local_only'],previousMode=$('bw-execution-mode').value;$('bw-execution-mode').replaceChildren(...modes.map(mode=>{const o=node('option',mode==='cloud_ciphertext_only'?'HE tr\u00ean cloud \u2014 ch\u1ec9 g\u1eedi b\u1ea3n m\u00e3':'T\u1ea1i doanh nghi\u1ec7p');o.value=mode;return o;}));if(modes.includes(previousMode))$('bw-execution-mode').value=previousMode;$('bw-lane-hint').textContent=curLane==='production'?'Kết quả đưa vào hàng đợi chính thức (Pilot Active); nếu dữ liệu nguồn là bản mô phỏng, hệ thống gắn cảnh báo rõ trên báo cáo.':'Kết quả vào hàng đợi rà thử (shadow); chưa phát hành vào hàng đợi chính thức.';runControls();}
  function catalog(v){listing=v;const lanes=v.available_lanes?.length?v.available_lanes:['staging'];$('bw-lane-wrap').hidden=!v.can_run_active;$('bw-backlog-mode-wrap').hidden=!v.can_run_active;if(!lanes.includes($('bw-lane').value))$('bw-lane').value=lanes[0];if(!v.can_run_active)$('bw-backlog-mode').value='shadow';syncLaneExecutionModes();$('bw-manage').hidden=!v.can_manage;const previous=$('bw-snapshot').value||desiredSnapshot||new URLSearchParams(location.hash.slice(1)).get('snapshot'),o=node('option','Chọn dữ liệu đã lưu');desiredSnapshot='';o.value='';$('bw-snapshot').replaceChildren(o,...v.datasets.map(d=>{const x=node('option',d.candidate_count+' giao dịch · '+(d.source_kind==='simulated'?'Dữ liệu mô phỏng':'Dữ liệu nguồn')+' · '+d.snapshot_id);x.value=d.snapshot_id;return x;}));if(v.datasets.some(d=>d.snapshot_id===previous))$('bw-snapshot').value=previous;$('bw-ready').textContent=v.message;$('bw-snapshot').disabled=!v.can_run;runControls();}
  function runControls(){const curLane=$('bw-lane').value,laneOk=curLane==='production'?!!listing?.can_run_active:!!listing?.can_run_staging||(!listing?.available_lanes&&!!listing?.can_run),data=listing?.datasets.find(d=>d.snapshot_id===$('bw-snapshot').value);$('bw-analyze').disabled=!laneOk||!data||data.can_analyze===false;if(listing)$('bw-ready').textContent=data?.can_analyze===false?data.reason:$('bw-execution-mode').value==='cloud_ciphertext_only'?'S\u1eb5n s\u00e0ng g\u1eedi y\u00eau c\u1ea7u HE; ch\u1ec9 c\u00e1c nh\u00e1nh h\u1ed7 tr\u1ee3 v\u00e0 \u0111\u1ee7 ngu\u1ed3n m\u1edbi kh\u1ea3 d\u1ee5ng.':listing.message;}
  $('bw-lane').onchange=syncLaneExecutionModes;
  $('bw-execution-mode').onchange=runControls;
  $('bw-snapshot').onchange=()=>{runControls();remember();};
  async function submit(body,key){if(dirty&&!confirm('B\u1ecf n\u1ed9i dung ch\u01b0a l\u01b0u \u0111\u1ec3 ch\u1ea1y ph\u00e2n t\u00edch?'))return;clear();const e=epoch;$('bw-analyze').disabled=true;$('bw-resume').disabled=true;notice(body.execution_mode==='cloud_ciphertext_only'?'\u0110ang g\u1eedi y\u00eau c\u1ea7u HE. Ch\u1ec9 g\u1eedi b\u1ea3n m\u00e3; gi\u1eef nguy\u00ean m\u00e3 y\u00eau c\u1ea7u khi m\u1ea5t k\u1ebft n\u1ed1i.':(body.lane==='production'?'\u0110ang ph\u00e2n t\u00edch Pilot Active t\u1ea1i doanh nghi\u1ec7p. Gi\u1eef nguy\u00ean y\u00eau c\u1ea7u n\u1ebfu m\u1ea5t k\u1ebft n\u1ed1i.':'\u0110ang ph\u00e2n t\u00edch shadow t\u1ea1i doanh nghi\u1ec7p. Gi\u1eef nguy\u00ean y\u00eau c\u1ea7u n\u1ebfu m\u1ea5t k\u1ebft n\u1ed1i.'));try{const v=await api(base()+'/runs',body);if(e!==epoch)return;if(key)sessionStorage.removeItem(key);run=v.run_id;remember();await loadList(run);}catch(err){if(e===epoch&&err.name!=='AbortError'){notice(err.message);if(err.code==='PIPELINE_RUN_PENDING'){run=body.run_id;remember();await loadList(run);notice(err.message);}}}finally{if(e===epoch){runControls();$('bw-resume').disabled=false;}}}
  $('bw-analyze').onclick=()=>{const sid=$('bw-snapshot').value,mode=$('bw-execution-mode').value,curLane=$('bw-lane').value,bid=listing?.lane_bundles?.[curLane]||listing?.active_bundle_id;if(!sid||!bid)return;const key='agent2.bundle.run.'+actor+'.'+context+'.'+company+'.'+curLane+'.'+sid+'.'+bid+'.'+mode;let rid=sessionStorage.getItem(key);if(!rid){rid=crypto.randomUUID();sessionStorage.setItem(key,rid);}submit({run_id:rid,snapshot_id:sid,execution_mode:mode,...(curLane==='production'?{lane:'production'}:{})},key);};
  $('bw-resume').onclick=()=>{const p=listing?.runs.find(x=>x.run_id===run);if(p)submit({run_id:p.run_id,snapshot_id:p.snapshot_id,execution_mode:p.execution_mode||'enterprise_local_only',...(p.lane==='production'?{lane:'production'}:{})});};
  $('bw-company').onchange=()=>{if(dirty&&!confirm('Bỏ nội dung chưa lưu để đổi doanh nghiệp?')){$('bw-company').value=company;return;}company=$('bw-company').value;run='';desiredSnapshot='';remember();loadList('');};
  $('bw-run').onchange=()=>{if(dirty&&!confirm('Bỏ nội dung chưa lưu để đổi lần phân tích?')){$('bw-run').value=run;return;}run=$('bw-run').value;remember();loadRun();};
  $('bw-refresh').onclick=()=>{if(!dirty||confirm('Bỏ nội dung chưa lưu và tải lại?'))loadList(run);};
  async function exportReport(format){const e=epoch,rid=run;try{const r=await fetch(mount+path()+'/report'+(format==='csv'?'.csv':''),{headers:{'X-Session':token,'X-Platform':'1'},cache:'no-store',signal:controller?.signal});if(!r.ok)throw Error('Chưa tải được báo cáo.');const bytes=await r.arrayBuffer();if(e!==epoch)return;download(bytes,'agent2-'+rid+'.'+format,format==='csv'?'text/csv':'application/json');}catch(err){if(e===epoch&&err.name!=='AbortError')notice(err.message);}}
  $('bw-json').onclick=()=>exportReport('json');
  $('bw-csv').onclick=()=>exportReport('csv');
  async function init(){clear();clearBacklog();listing=null;$('bw-run').replaceChildren();$('bw-run').disabled=true;$('bw-snapshot').replaceChildren();$('bw-snapshot').disabled=true;$('bw-analyze').disabled=true;$('bw-company').disabled=true;try{token=sessionStorage.getItem('kt-session')||'';if(!token||!mount){notice('Mở từ Portal và đăng nhập để rà hồ sơ.');return;}const c=await api('/api/v1/ui/context');actor=c.actor_id;context=c.context_id||'';$('bw-company').replaceChildren(...c.companies.map(id=>{const o=node('option',id);o.value=id;return o;}));$('bw-company').disabled=!c.companies.length;let shared;try{shared=JSON.parse(sessionStorage.getItem('agent2.company.selection'));}catch{}const remembered=shared?.version===1&&shared.actor===actor&&shared.context===context&&c.companies.includes(shared.company)?shared.company:'';const hash=new URLSearchParams(location.hash.slice(1));company=c.companies.includes(hash.get('company'))?hash.get('company'):remembered||c.companies[0]||'';$('bw-company').value=company;run=hash.get('run')||'';desiredSnapshot=hash.get('snapshot')||'';if(company){remember();await loadList(run);}else notice('Chưa có doanh nghiệp được cấp quyền.');}catch(err){notice(err.message);}}
  window.addEventListener('hashchange',()=>{const h=new URLSearchParams(location.hash.slice(1));if(h.get('company')!==company||h.get('run')!==(run||null)){if(dirty&&!confirm('Bỏ nội dung chưa lưu để mở liên kết khác?')){remember();return;}init();}});
  window.addEventListener('focus',()=>{if((sessionStorage.getItem('kt-session')||'')!==token)init();});init();
})();
