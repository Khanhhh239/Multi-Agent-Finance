'use strict';
(() => {
  const $=id=>document.getElementById(id),mount=location.pathname.startsWith('/agent2/')?'/agent2':'';
  const node=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=String(text);return n;};
  const put=(id,...items)=>$(id).replaceChildren(...items),show=(id,on=true)=>$(id).hidden=!on;
  const date=v=>v?new Date(typeof v==='number'?v*1000:v).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',hour12:false}):'—';
  const money=v=>{try{return BigInt(v).toLocaleString('vi-VN')+' đ';}catch{return String(v);}};
  const phase={queued:'Đã nhận',preparing:'Đang chuẩn bị',ready:'Đang chuẩn bị tính',sending:'Đang tính mã hóa',received:'Đang kiểm tra kết quả',decrypting:'Đang giải mã',waiting_authorization:'Cần đăng nhập lại',retryable:'Chờ kết nối lại',waiting_worker:'Chờ bộ xử lý',completed:'Đã phân tích xong',failed:'Gặp lỗi',expired:'Đã hết hạn'};
  const outcome={confirmed_risk:'Có vấn đề cần xử lý',legitimate:'Không phát hiện vấn đề',inconclusive:'Chưa đủ căn cứ'};
  const remDocStatus={unknown:'Chưa có nguồn kiểm tra',missing:'Đã xác nhận thiếu',pending_verification:'Đã nhận, chưa xác minh',present:'Đã xác minh',not_applicable:'Không áp dụng',rejected:'Từ chối xác minh'};
  const remTaskStatus={open:'Mở mới',in_progress:'Đang xử lý',waiting_external:'Chờ bổ sung bên ngoài',completed:'Đã hoàn tất',cancelled:'Đã hủy'};
  const tables={transactions:'Giao dịch',invoices:'Hóa đơn',payment_allocations:'Phân bổ thanh toán',payment_history_coverage:'Phạm vi lịch sử',companies:'Doanh nghiệp',vendors:'Nhà cung cấp',employees:'Nhân viên',approvals:'Phê duyệt',supporting_documents:'Chứng từ đối chiếu',vendor_bank_history:'Lịch sử ngân hàng'};
  let token='',portal=!!mount,identity='',actorID='',contextID='',company='',catalog=null,report=null,comparison=null,selected='',epoch=0,controller=null,poll=null,beat=null,dirty=false;
  const base=()=>'/api/v1/companies/'+encodeURIComponent(company),runPath=()=>base()+'/workspace/runs/'+report.run_id;
  function notice(text){put('ws-notice',node('span',text));show('ws-notice',!!text);}
  function stopTimers(){clearTimeout(poll);clearInterval(beat);poll=null;beat=null;}
  function clear(){epoch++;controller?.abort();controller=new AbortController();stopTimers();catalog=null;report=null;comparison=null;selected='';dirty=false;for(const id of ['ws-runs','ws-datasets','ws-cases','ws-detail','ws-run-meta','ws-comparison','ws-rem-tasks','ws-rem-report-metrics','ws-rem-report-finance','ws-rem-home-detail'])if($(id))put(id);if($('ws-rem-home-detail'))show('ws-rem-home-detail',false);show('ws-comparison-panel',false);show('ws-comparison-refresh',false);show('ws-comparison-export',false);show('ws-compare');$('ws-compare').disabled=false;show('ws-home',false);show('ws-run',false);show('manage-link',false);}
  function lock(text){clear();token='';identity='';actorID='';contextID='';company='';show('ws-selection',false);show('ws-login');notice(text);}
  async function api(path,body){
    const headers=portal?{'X-Platform':'1','X-Session':token}:{Authorization:'Bearer '+token};
    if(body!==undefined)headers['Content-Type']='application/json';
    let response;try{response=await fetch(mount+path,{method:body===undefined?'GET':'POST',headers,body:body===undefined?undefined:JSON.stringify(body),cache:'no-store',signal:controller?.signal});}
    catch(e){if(e.name==='AbortError')throw e;throw Error('Mất kết nối. Nội dung đang nhập được giữ trên màn hình; thử lại khi kết nối trở lại.');}
    const value=await response.json();if(!response.ok){const e=Error(value.errors?.map(x=>x.message+' '+(x.action||'')).join('\n')||value.error||'Chưa thực hiện được yêu cầu.');e.status=response.status;throw e;}return value;
  }
  function failure(e){if(e.name==='AbortError')return;if(portal&&(e.status===401||e.status===403)){lock('Phiên đăng nhập hoặc quyền đã thay đổi. Đăng nhập lại từ Portal để tiếp tục.');return;}notice(e.message);}
  function remember(){
    try{if(company&&actorID){const saved={version:1,actor:actorID,context:contextID,company,page:'workspace'};if(report?.run_id)saved.run=report.run_id;sessionStorage.setItem('agent2.company.selection',JSON.stringify(saved));localStorage.setItem('agent2.workspace.company',company);}}catch{/* optional selection */}
    for(const a of document.querySelectorAll('header a[href],#ws-selection a[href],#ws-comparison-panel a[href]')){const page=new URL(a.href).pathname.split('/').pop();if(['workspace','data-import','encrypted-analysis','analysis-settings','pipeline-workspace'].includes(page))a.href=mount+'/'+page+(company?'#company='+encodeURIComponent(company):'');}
  }
  function route(run){const fields=new URLSearchParams({company});if(run)fields.set('run',run);if(location.hash.slice(1)===fields.toString()){run?loadRun(run):loadHome();return;}location.hash=fields.toString();}
  function selection(){const h=new URLSearchParams(location.hash.slice(1));return {company:h.get('company'),run:h.get('run')};}
  function metadata(id,items){put(id,...items.flatMap(([k,v])=>[node('dt',k),node('dd',v)]));}
  function metrics(id,items){put(id,...items.map(([label,count])=>{const n=node('div');n.className='metric';n.append(node('strong',count),node('span',label));return n;}));}
  function chooseDataset(snapshot){try{localStorage.setItem('agent2.he.selection',JSON.stringify({company,snapshot}));}catch{notice('Trình duyệt chưa cho phép lưu lựa chọn. Bật lưu trữ cho trang rồi thử lại.');return;}location.href=mount+'/encrypted-analysis';}
  async function loadRemediationOverview(){
    if(!company||!$('ws-rem-filter'))return;const e=epoch,filt=$('ws-rem-filter').value||'all';
    try{
      const [tasksRes,repRes]=await Promise.all([api(base()+'/remediation/tasks/filter/'+filt),api(base()+'/remediation/report')]);
      if(e!==epoch)return;
      const r=repRes,t=r.task_counts,c=r.case_counts,d=r.document_counts,am=r.amounts_vnd;
      metrics('ws-rem-report-metrics',[['Vụ việc riêng',c.total_distinct_cases],['Công việc mở/đang xử lý',t.open+t.in_progress+t.waiting_external],['Quá hạn',t.overdue],['Sắp đến hạn',t.due_soon],['Chờ xác nhận',t.awaiting_confirmation],['Hồ sơ chưa đủ',d.incomplete_checklists]]);
      const moneyText=(label,v)=>{const sp=node('span',label+': ');sp.append(node('strong',v==null?'Chưa xác định':money(v)));return sp;};
      put('ws-rem-report-finance',moneyText('Tiền liên quan (khử trùng)',am.related_amount_vnd),moneyText('Chênh lệch đối chiếu',am.discrepancy_amount_vnd),moneyText('Thất thoát xác nhận',am.confirmed_loss_vnd),moneyText('Đã thu hồi',am.recovered_vnd));
      put('ws-rem-tasks',...tasksRes.tasks.map(task=>{
        const tr=node('tr'),caseTd=node('td',task.case_id);caseTd.append(node('small',task.obligation_id));
        const ttl=node('td',task.title);ttl.append(node('small',task.what_to_do));
        const who=node('td',(task.assignee.display_label||task.assignee.assignee_key)+' ('+task.assignee.assignee_kind+')');who.append(node('small','Hạn: '+date(task.due_at)));
        const st=node('td',remTaskStatus[task.status]||task.status);st.append(node('small','rev '+task.revision));
        const btn=node('button','Mở xử lý hồ sơ');btn.className='quiet';btn.addEventListener('click',()=>{show('ws-rem-home-detail',true);loadCaseRemediation($('ws-rem-home-detail'),task.case_id,{obligation_id:task.obligation_id});$('ws-rem-home-detail').scrollIntoView({block:'start',behavior:'smooth'});});
        const actTd=node('td');actTd.append(btn);
        if(task.source_binding){const a=node('a','Mở vụ nguồn');a.href=mount+'/pipeline-workspace#'+new URLSearchParams({company,run:task.source_binding.run_id});actTd.append(a);}
        tr.append(caseTd,ttl,who,st,actTd);return tr;
      }));
      show('ws-rem-tasks-empty',!tasksRes.tasks.length);show('ws-remediation-overview',true);
    }catch(err){if(e===epoch&&![404,503].includes(err.status))failure(err);}
  }
  async function loadCaseRemediation(container,caseKey,defaults={}){
    const e=epoch;container.className='rem-box';container.replaceChildren(node('h3','Hồ sơ chứng từ & Công việc khắc phục'),node('p','Đang tải trạng thái hồ sơ...'));
    try{
      const rem=await api(base()+'/remediation/cases/'+encodeURIComponent(caseKey));
      if(e!==epoch)return;
      container.replaceChildren();
      container.append(node('h3','Hồ sơ chứng từ & Công việc khắc phục · '+caseKey));
      container.append(node('p','Ba phần độc lập: Kết luận vụ việc · Tình trạng chứng từ · Công việc khắc phục (không tự sinh nhãn ML).'));
      if(rem.linked_case){container.append(node('p','Trạng thái vụ việc độc lập: '+rem.linked_case.case_workflow_status+(rem.linked_case.case_resolution?' ('+rem.linked_case.case_resolution+')':'')));}
      const nextP=node('p');nextP.append(node('strong','Bước tiếp theo là gì? '),document.createTextNode(rem.next_step_vi));container.append(nextP);
      const statusMsg=node('p','');statusMsg.className='review-message';statusMsg.hidden=true;container.append(statusMsg);
      const setMsg=msg=>{statusMsg.textContent=msg;statusMsg.hidden=!msg;};

      // 1. Checklist: Con thieu gi?
      const chkTitle=node('h4','1. Còn thiếu gì? (Checklist chứng từ theo chính sách)');container.append(chkTitle);
      if(rem.checklist){
        const tbl=node('table'),hr=node('tr');for(const h of ['Chứng từ','Trạng thái','Nguồn','Chi tiết'])hr.append(node('th',h));tbl.append(hr);
        for(const it of rem.checklist.items){
          const tr=node('tr'),pill=node('span',remDocStatus[it.item_status]||it.item_status);
          pill.className='rem-pill'+(it.item_status==='missing'||it.item_status==='unknown'?' bad':it.item_status==='pending_verification'?' warn':'');
          const stTd=node('td');stTd.append(pill);
          tr.append(node('td',it.title_vi+' ('+it.document_type+')'),stTd,node('td',it.decision_source),node('td',it.note));tbl.append(tr);
        }
        const sc=node('div');sc.className='table-scroll';sc.append(tbl);container.append(sc);
      }else{
        const evalBtn=node('button','Đánh giá checklist theo nhóm vấn đề');evalBtn.className='quiet';
        evalBtn.addEventListener('click',async()=>{try{await api(base()+'/remediation/cases/'+encodeURIComponent(caseKey)+'/checklist',{obligation_id:defaults.obligation_id||caseKey,problem_family:defaults.problem_family||'payment_invoice',rule_ids:defaults.rule_ids||[],available_sources:defaults.available_sources||[]});await loadCaseRemediation(container,caseKey,defaults);}catch(err){setMsg(err.message);}});
        container.append(node('p','Chưa đánh giá checklist cho vụ này.'),evalBtn);
      }

      // 2. Documents + versions + verify
      container.append(node('h4','2. Chứng từ đã nộp & Xác minh độc lập'));
      if(!rem.documents.length)container.append(node('p','Chưa có chứng từ đính kèm.'));
      for(const doc of rem.documents){
        const card=node('div');card.className='rem-task-card';
        const pill=node('span',remDocStatus[doc.verification_status]||doc.verification_status);pill.className='rem-pill'+(doc.verification_status==='present'?'':doc.verification_status==='rejected'?' bad':' warn');
        const head=node('div');head.append(node('strong',doc.document_type+' · v'+doc.current_version+' '),pill);card.append(head);
        const latest=doc.versions[doc.versions.length-1];
        card.append(node('p',latest.filename+' · SHA256 '+latest.sha256.slice(0,12)+' · nhận '+date(latest.received_at)+(doc.late_arrival_after_as_of?' · Nộp sau mốc as_of (không sửa snapshot cũ)':'')));
        const acts=node('div');acts.className='actions';
        const noteIn=node('input');noteIn.placeholder='Ghi chú đối chiếu chứng từ';noteIn.value='Đã đối chiếu chứng từ gốc khớp kỳ';
        const btnOk=node('button','Xác minh đạt');btnOk.className='quiet';btnOk.addEventListener('click',async()=>{try{await api(base()+'/remediation/documents/'+doc.document_id+'/verify',{decision:'present',verification_note:noteIn.value});await loadCaseRemediation(container,caseKey,defaults);await loadRemediationOverview();}catch(err){setMsg(err.message);}});
        const btnRej=node('button','Từ chối');btnRej.className='quiet';btnRej.addEventListener('click',async()=>{try{await api(base()+'/remediation/documents/'+doc.document_id+'/verify',{decision:'rejected',verification_note:noteIn.value||'Chứng từ không khớp'});await loadCaseRemediation(container,caseKey,defaults);await loadRemediationOverview();}catch(err){setMsg(err.message);}});
        acts.append(noteIn,btnOk,btnRej);card.append(acts);container.append(card);
      }
      const upForm=node('div');upForm.className='rem-form';
      const dtSel=node('select');for(const [k,v] of [['invoice','Hóa đơn VAT'],['payment_allocation','Phân bổ thanh toán'],['bank_transfer_receipt','Ủy nhiệm chi ngân hàng'],['credit_or_adjustment_note','Biên bản hoàn/điều chỉnh'],['supporting_transaction_voucher','Chứng từ giải trình']]){const o=node('option',v);o.value=k;dtSel.append(o);}
      const upFile=node('input');upFile.type='file';upFile.accept='.pdf,.png,.jpg,.jpeg';
      const upBtn=node('button','Tải chứng từ bổ sung (chưa xác minh)');upBtn.className='quiet';
      upBtn.addEventListener('click',async()=>{const f=upFile.files[0];if(!f){setMsg('Chọn tệp PDF/PNG/JPEG trước khi tải lên.');return;}if(f.size>2*1024*1024){setMsg('Tệp vượt 2 MB.');return;}try{const b64=await new Promise((res,rej)=>{const rd=new FileReader();rd.onload=()=>res(String(rd.result).split(',')[1]);rd.onerror=rej;rd.readAsDataURL(f);});await api(base()+'/remediation/cases/'+encodeURIComponent(caseKey)+'/documents',{obligation_id:defaults.obligation_id||caseKey,document_type:dtSel.value,filename:f.name,mime:f.type||'application/pdf',content_base64:b64,idempotency_key:crypto.randomUUID()});await loadCaseRemediation(container,caseKey,defaults);await loadRemediationOverview();}catch(err){setMsg(err.message);}});
      upForm.append(node('strong','Tải lên hoặc cập nhật phiên bản chứng từ'),dtSel,upFile,upBtn);container.append(upForm);

      // 3. ActionTasks: Ai dang xu ly, han nao?
      container.append(node('h4','3. Ai đang xử lý, hạn nào? (ActionTask)'));
      if(!rem.tasks.length)container.append(node('p','Chưa có công việc khắc phục nào.'));
      for(const t of rem.tasks){
        const tc=node('div');tc.className='rem-task-card';
        const stPill=node('span',(remTaskStatus[t.status]||t.status)+' (rev '+t.revision+')');stPill.className='rem-pill'+(t.status==='completed'?'':t.status==='cancelled'?' bad':' warn');
        tc.append(node('strong',t.title+' '),stPill,node('p','Việc phải làm: '+t.what_to_do),node('p','Phụ trách: '+(t.assignee.display_label||t.assignee.assignee_key)+' ['+t.assignee.assignee_kind+'] · Hạn: '+date(t.due_at)));
        if(t.submission)tc.append(node('p','Kết quả đã gửi: '+t.submission.result_summary+' ('+t.submission.submitted_by+')'));
        const resIn=node('input');resIn.placeholder='Tóm tắt kết quả thực hiện / ghi chú xác nhận';
        const acts=node('div');acts.className='actions';
        if(['open','in_progress','waiting_external'].includes(t.status)){
          const bSub=node('button','Gửi kết quả');bSub.className='quiet';bSub.addEventListener('click',async()=>{try{await api(base()+'/remediation/tasks/'+t.task_id+'/submit',{expected_revision:t.revision,result_summary:resIn.value||'Đã đối chiếu và bổ sung chứng từ',document_ids:rem.documents.map(d=>d.document_id)});await loadCaseRemediation(container,caseKey,defaults);await loadRemediationOverview();}catch(err){setMsg(err.message);}});
          const bConf=node('button','Xác nhận hoàn tất');bConf.addEventListener('click',async()=>{try{await api(base()+'/remediation/tasks/'+t.task_id+'/decision',{expected_revision:t.revision,decision:'confirm_complete',note:resIn.value||'Đã kiểm tra đủ chứng từ xác minh'});await loadCaseRemediation(container,caseKey,defaults);await loadRemediationOverview();}catch(err){setMsg(err.message);}});
          const bRw=node('button','Yêu cầu làm lại');bRw.className='quiet';bRw.addEventListener('click',async()=>{try{await api(base()+'/remediation/tasks/'+t.task_id+'/decision',{expected_revision:t.revision,decision:'request_rework',note:resIn.value||'Cần bổ sung thêm chứng từ hợp lệ'});await loadCaseRemediation(container,caseKey,defaults);await loadRemediationOverview();}catch(err){setMsg(err.message);}});
          acts.append(resIn,bSub,bConf,bRw);
        }else{
          const bRe=node('button','Mở lại');bRe.className='quiet';bRe.addEventListener('click',async()=>{try{await api(base()+'/remediation/tasks/'+t.task_id+'/decision',{expected_revision:t.revision,decision:'reopen',note:resIn.value||'Mở lại để kiểm tra bổ sung'});await loadCaseRemediation(container,caseKey,defaults);await loadRemediationOverview();}catch(err){setMsg(err.message);}});
          acts.append(resIn,bRe);
        }
        tc.append(acts);container.append(tc);
      }

      const taskForm=node('div');taskForm.className='rem-form';
      const tTitle=node('input');tTitle.placeholder='Tiêu đề việc cần làm';tTitle.value='Kiểm tra hồ sơ & đối chiếu công nợ';
      const tDue=node('input');tDue.placeholder='Hạn xử lý ISO kèm múi giờ (hoặc để trống), vd: 2026-11-25T17:00:00+07:00';
      const tRole=node('select');for(const [k,v] of [['ke_toan_cong_no','Bộ phận Kế toán công nợ'],['nhan_su_tien_luong','Bộ phận Nhân sự & Lương'],['kiem_soat_noi_bo','Bộ phận Kiểm soát nội bộ'],['phe_duyet_tai_chinh','Phê duyệt tài chính']]){const o=node('option',v);o.value=k;tRole.append(o);}
      const btnReq=node('button','Yêu cầu bổ sung');btnReq.className='quiet';
      const btnAss=node('button','Giao việc xử lý');btnAss.className='quiet';
      const createT=async(tType)=>{try{await api(base()+'/remediation/tasks',{case_id:caseKey,obligation_id:defaults.obligation_id||caseKey,task_type:tType,issue_type:tType==='request_documents'?'missing_document':'payment_discrepancy',title:tTitle.value,what_to_do:tTitle.value,reason:'Tạo từ không gian xử lý vụ việc',assignee_kind:'department_role',assignee_key:tRole.value,due_at:tDue.value.trim()||null,require_evidence:true,required_document_types:defaults.required_document_types||[],idempotency_key:crypto.randomUUID()});await loadCaseRemediation(container,caseKey,defaults);await loadRemediationOverview();}catch(err){setMsg(err.message);}};
      btnReq.addEventListener('click',()=>createT('request_documents'));
      btnAss.addEventListener('click',()=>createT('reconcile_payment'));
      const btnBar=node('div');btnBar.className='actions';btnBar.append(btnReq,btnAss);
      taskForm.append(node('strong','Tạo yêu cầu bổ sung hoặc giao việc xử lý'),tTitle,tRole,tDue,btnBar);container.append(taskForm);
    }catch(err){if(e===epoch)container.replaceChildren(node('h3','Hồ sơ chứng từ & Công việc khắc phục'),node('p',err.message));}
  }
  async function loadHome(){
    clear();remember();const e=epoch;notice('');show('ws-selection');
    try{const value=await api(base()+'/workspace');if(e!==epoch)return;catalog=value;show('ws-home');show('ws-login',false);show('manage-link',value.can_manage);show('ws-availability',!value.available);put('ws-availability',node('span',value.message||'Chưa sẵn sàng phân tích mới. Có thể nhập dữ liệu và xem kết quả đã lưu.'));
      metrics('ws-metrics',[['Bản dữ liệu đã lưu',value.summary.datasets],['Lượt đang xử lý',value.summary.active],['Lượt đã phân tích',value.summary.completed],['Lượt cần kiểm tra lỗi',value.summary.failed]]);
      put('ws-runs',...value.runs.map(r=>{const tr=node('tr'),data=node('td',r.row_count==null?'Đã lưu dữ liệu':r.row_count+' giao dịch');data.append(node('small',r.snapshot_id));const action=node('button',r.phase==='completed'?'Mở kết quả và phiếu rà':'Xem trạng thái');action.className='quiet';action.addEventListener('click',()=>route(r.job_id));const cell=node('td');cell.append(action);tr.append(node('td',date(r.created_at)),data,node('td',phase[r.phase]||'Đang xử lý'),cell);['Thời gian','Bản dữ liệu','Trạng thái','Thao tác'].forEach((label,i)=>tr.children[i].dataset.label=label);return tr;}));
      put('ws-datasets',...value.datasets.map(d=>{const tr=node('tr'),period=node('td',date(d.period_start)+' – '+date(d.period_end));if(d.simulated_records){const badge=node('span','Dữ liệu mô phỏng');badge.className='tag';period.append(badge);}const button=node('button','Phân tích bản này');button.className='quiet';button.disabled=!value.available||d.is_training_source;if(d.is_training_source)button.textContent='Lịch sử chuẩn bị phiên bản';button.addEventListener('click',()=>chooseDataset(d.snapshot_id));const action=node('td');action.append(button);tr.append(period,node('td',d.record_count),node('td',date(d.created_at)),action);['Kỳ giao dịch','Số giao dịch','Ngày lưu','Thao tác'].forEach((label,i)=>tr.children[i].dataset.label=label);return tr;}));show('ws-runs-empty',!value.runs.length);show('ws-data-empty',!value.datasets.length);
      loadRemediationOverview();
    }catch(err){if(e===epoch)failure(err);}
  }
  async function loadRun(id,refresh=false){
    if(!/^herun_[a-f0-9]{32}$/.test(id)){notice('Mã lượt phân tích không hợp lệ.');return;}
    if(!refresh){clear();show('ws-selection');show('ws-run');notice('');}
    const e=epoch;
    try{const value=await api(base()+'/workspace/runs/'+id);if(e!==epoch)return;report=value;remember();show('ws-run');show('ws-home',false);put('ws-run-title',node('span',phase[value.status]||'Lượt phân tích'));put('ws-run-message',node('span',value.message||value.progress.message));
      metadata('ws-run-meta',[['Doanh nghiệp',company],['Lần phân tích',id],...(value.snapshot_id?[['Bản dữ liệu',value.snapshot_id],['Nguồn được biết đến',date(value.as_of)]]:[]),['Tạo lúc',date(value.created_at)]]);
      const completed=value.status==='completed',known=value.progress.total_tasks!=null;show('ws-progress',known&&!completed);if(known){$('ws-progress').max=Math.max(1,value.progress.total_tasks);$('ws-progress').value=value.progress.completed_tasks;}
      put('ws-progress-count',node('span',known?value.progress.completed_tasks+'/'+value.progress.total_tasks+' phép tính đã hoàn tất. Số phép tính có thể khác số giao dịch.':''));
      show('ws-resume',['waiting_authorization','retryable','waiting_worker'].includes(value.status));show('ws-csv',completed);show('ws-json',completed);show('ws-review-area',completed);
      if(completed){const s=value.summary;metrics('ws-review-metrics',[['Giao dịch',value.row_count],['Chưa ghi kết quả',s.pending_cases],['Đã ghi kết quả',s.reviewed_cases],['Chưa đủ căn cứ',s.outcomes.inconclusive]]);renderCases();show('ws-comparison-panel',value.comparison_available===true);if(value.comparison_available)await loadComparison(false);}
      else{put('ws-review-metrics');if(!['failed','expired'].includes(value.status))poll=setTimeout(()=>loadRun(id,true),5000);}
    }catch(err){if(e===epoch)failure(err);}
  }
  async function loadComparison(create=false){
    const e=epoch;if(!report?.comparison_available)return;$('ws-compare').disabled=true;
    try{const value=await api(runPath()+'/comparison',create?{policy:'rules_first_fill/1.0.0',budget:5}:undefined);if(e!==epoch)return;comparison=value;show('ws-compare',false);show('ws-comparison-refresh');show('ws-comparison-export');renderComparison(value);}
    catch(error){if(e===epoch&&!(error.status===404&&!create))failure(error);}
    finally{if(e===epoch)$('ws-compare').disabled=false;}
  }
  function renderComparison(value){
    const box=$('ws-comparison');box.replaceChildren();
    box.append(node('p','Đã khóa lựa chọn. Đây là thử nghiệm trên lượt đã biết kết quả'+(value.plan.simulated_data?' và dữ liệu mô phỏng':'')+'. Chưa chứng minh độ chính xác phát hiện gian lận.'));
    const number=v=>v==null?'Chưa đánh giá':String(v),percent=v=>v==null?'Chưa đánh giá':(v*100).toLocaleString('vi-VN',{maximumFractionDigits:1})+'%';
    const table=node('table'),head=node('tr');for(const name of ['Chỉ số','Chỉ luật P1','Luật P1 + ML'])head.append(node('th',name));table.append(head);
    const a=value.baseline.metrics,b=value.combined.metrics;
    for(const [label,x,y] of [['Đã chọn / tối đa',a.selected+'/5',b.selected+'/5'],['Đã ghi kết quả',a.reviewed,b.reviewed],['Chưa rà',a.pending,b.pending],['Chưa đủ căn cứ',a.inconclusive,b.inconclusive],['Khoản cần xử lý do người rà ghi',number(a.declared_problem_transactions),number(b.declared_problem_transactions)],['Tỷ lệ cần xử lý / đã kết luận',percent(a.declared_precision_resolved),percent(b.declared_precision_resolved)],['Đã kết luận / đã chọn',a.resolved+'/'+a.selected,b.resolved+'/'+b.selected],['Cảnh báo được ghi hữu ích',number(a.declared_useful_transactions),number(b.declared_useful_transactions)],['Giây kết nối đã lưu',number(a.saved_connected_seconds),number(b.saved_connected_seconds)]]){const row=node('tr');row.append(node('td',label),node('td',x),node('td',y));table.append(row);}
    const scroll=node('div');scroll.className='table-scroll';scroll.append(table);box.append(scroll);
    box.append(node('p','ML thêm '+value.overlap.added+' giao dịch; thay '+value.overlap.removed+' giao dịch của luật. Luật chỉ chọn cảnh báo hiện có, không tự thêm giao dịch cho đủ 5.'));
    box.append(node('p','Nguồn khả dụng: P1 '+value.coverage.p1_available+'/'+value.coverage.total_transactions+'; ML '+value.coverage.ml_available+'/'+value.coverage.total_transactions+'. P1 chưa bao phủ toàn bộ quy tắc.'));
    if(value.deferred_rule_alerts.length)box.append(node('p',value.deferred_rule_alerts.length+' giao dịch cảnh báo luật chưa được chọn vì ngân sách hoặc cần giữ nguyên nhóm đồng thời.'));
    const labels={alert:'Cảnh báo P1',no_p1_hit:'P1 chưa trúng, chưa đại diện toàn bộ luật',unavailable:'P1 chưa đủ nguồn',not_applicable:'P1 không áp dụng cho loại giao dịch này'};
    for(const [title,items,open] of [['ML bổ sung',value.added,true],['Chỉ luật P1',value.baseline.transactions,false],['Luật P1 + ML',value.combined.transactions,false]]){const details=node('details');details.open=open;details.append(node('summary',title+' · '+items.length+(open?' giao dịch':'/5 giao dịch')));if(!items.length)details.append(node('p','Không có giao dịch được chọn.'));for(const entry of items){const line=node('div');line.className='comparison-entry';const button=node('button',entry.record_id+' · '+money(entry.amount_vnd));button.className='quiet';button.addEventListener('click',()=>{if(dirty&&!confirm('Bỏ nội dung phiếu chưa lưu để mở giao dịch này?'))return;const item=report.cases.find(c=>c.case_id===entry.case_id);if(item){$('ws-filter').value='all';$('ws-search').value='';renderCase(item);$('ws-detail').scrollIntoView({block:'start',behavior:'smooth'});}});line.append(button,node('p',(entry.reason==='ml_addition'?'ML bổ sung · ':'')+(labels[entry.rule_state]||'Chưa đủ thông tin')),node('small',entry.outcome?outcome[entry.outcome]:'Chưa ghi kết quả rà'));details.append(line);}box.append(details);}
    box.append(node('p','Lợi ích thêm do người rà ghi: '+number(value.delta.declared_useful_transactions)+'.'));
    const method=node('details');method.append(node('summary','Cách tính và mã đối chiếu'),node('p',value.plan_id),node('p','Các giao dịch chung dùng cùng phiếu; thời gian là phần kết nối quy cho từng phương án, chưa phải thử nghiệm thời gian độc lập. Nhóm thanh toán đồng thời giữ nguyên; số giao dịch không phải số vụ gian lận.'));box.append(method);
  }
  function renderCases(){
    if(!selected&&!$('ws-detail').children.length)put('ws-detail',node('h2','Chọn một giao dịch để rà'),node('p','Mở khoản ML bổ sung ở trên hoặc chọn giao dịch trong danh sách để xem căn cứ và ghi kết quả.'));
    const query=$('ws-search').value.toLocaleLowerCase('vi-VN'),filter=$('ws-filter').value;
    const cases=report.cases.filter(c=>(c.record_id+' '+c.why).toLocaleLowerCase('vi-VN').includes(query)&&(filter==='all'||filter==='pending'&&!c.review.revision||filter==='reviewed'&&c.review.revision>0||filter==='signal'&&c.payment_signal||filter==='missing'&&c.payment_unavailable));
    put('ws-cases',...cases.map(c=>{const b=node('button');b.className='case-choice';b.setAttribute('aria-pressed',String(selected===c.case_id));b.append(node('strong',c.record_id+' · '+money(c.amount_vnd)),node('small',c.review.revision?outcome[c.review.feedback.outcome]:'Chưa ghi kết quả'),node('small',c.payment_signal?'Cần đối chiếu thanh toán':c.payment_unavailable?'Thanh toán chưa đủ nguồn':date(c.event_at)));b.addEventListener('click',()=>{if(dirty&&!confirm('Phiếu đang có nội dung chưa lưu. Bỏ nội dung này để mở phiếu khác?'))return;renderCase(c);});return b;}));if(!cases.length)put('ws-cases',node('p','Không có giao dịch thuộc bộ lọc này.'));
  }
  function sourceCard(ev){
    const record=ev.record,box=node('div');box.className='source-card';const details=node('details');const rid=record.record_id||record.transaction_id||record.vendor_id||record.employee_id||record.document_id||record.authority_id||record.coverage_id||'';details.append(node('summary',(tables[ev.table]||'Bản ghi nguồn')+' · '+rid));
    const facts=[['Loại nguồn',ev.simulated?'Dữ liệu mô phỏng':ev.original_verified?'Chứng từ gốc có trạng thái xác minh tại nguồn':'Bản ghi nguồn, chưa xác minh chứng từ gốc'],['Có hiệu lực',date(record.effective_at||record.posted_at||record.recorded_at||record.observed_at)],['Được biết lúc',date(record.observed_at)]];
    for(const k of ['amount_vnd','total_vnd','gross_amount_vnd','invoice_gross_vnd'])if(record[k]!=null)facts.push(['Số tiền',money(record[k])]);
    if(record.number||record.invoice_number)facts.push(['Số hóa đơn',record.number||record.invoice_number]);if(record.description)facts.push(['Nội dung',record.description]);
    for(const [k,label] of [['transaction_ref','Giao dịch'],['invoice_ref','Hóa đơn'],['adjusts_ref','Điều chỉnh khoản']])if(record[k])facts.push([label,record[k].record_id]);
    if(record.covered_from)facts.push(['Lịch sử từ',date(record.covered_from)],['Lịch sử đến',date(record.covered_through)],['Hóa đơn trong phạm vi',(record.invoice_refs||[]).map(x=>x.record_id).join(', ')]);
    if(record.source)facts.push(['Nguồn',record.source.system+' · '+record.source.record_id]);
    const dl=node('dl');for(const [k,v] of facts)dl.append(node('dt',k),node('dd',v));details.append(dl);
    if(record.accounting_lines?.length){const table=node('table'),head=node('tr');for(const name of ['Tài khoản','Nợ','Có'])head.append(node('th',name));table.append(head);for(const l of record.accounting_lines){const tr=node('tr');tr.append(node('td',l.account),node('td',money(l.debit_vnd)),node('td',money(l.credit_vnd)));table.append(tr);}details.append(table);}
    box.append(details);return box;
  }
  function renderCase(item){
    clearInterval(beat);beat=null;dirty=false;selected=item.case_id;renderCases();const e=epoch,box=$('ws-detail');box.replaceChildren();let state=item.review,lease=null,pending=null;
    box.append(node('h2','Giao dịch '+item.record_id+' · '+money(item.amount_vnd)),node('p',date(item.event_at)));
    if(item.evidence.some(x=>x.simulated)){const tag=node('span','Dữ liệu mô phỏng');tag.className='tag';box.append(tag);}
    box.append(node('h3','Điều cần làm rõ'),node('p',item.question),node('h3','Vì sao cần kiểm tra?'),node('p',item.why),node('h3','Bước tiếp theo'),node('p',item.next_step));
    for(const [heading,rows] of [['Đối chiếu thanh toán',item.invoice_checks],['Nhóm thanh toán cùng thời điểm',item.simultaneous_checks]])if(rows.length){const detail=node('details');detail.append(node('summary',heading));const table=node('table'),head=node('tr');for(const title of ['Đã trả trước','Khoản / nhóm này','Lũy kế','Hóa đơn','Phần vượt'])head.append(node('th',title));table.append(head);for(const c of rows){const tr=node('tr');for(const key of ['prior_paid_vnd','current_allocated_vnd','cumulative_paid_vnd','invoice_gross_vnd','excess_vnd'])tr.append(node('td',money(c[key])));table.append(tr);}detail.append(table);box.append(detail);}
    if(item.graph_links.length){const detail=node('details');detail.append(node('summary','Liên kết giữa các đối tượng'));for(const link of item.graph_links)detail.append(node('p',link.source+' ↔ '+link.target+' · '+link.relation+(link.context_only?' · Liên kết bối cảnh, cần căn cứ bổ sung':'')));detail.append(node('p','Liên kết cần được đối chiếu với hồ sơ; chưa xác nhận sai phạm.'));box.append(detail);}
    const checks=node('details');checks.append(node('summary','Tình trạng các phần phân tích'));for(const c of item.checks){const p=node('p',c.title+': '+c.message);p.className='branch-state '+c.status;checks.append(p);}box.append(checks);
    for(const limit of item.missing_sources||[]){const p=node('p',(limit.message||'')+' '+(limit.action||''));p.className='issue';box.append(p);}
    const remPanel=node('div');box.append(remPanel);loadCaseRemediation(remPanel,item.case_id,{obligation_id:item.record_id||item.case_id,problem_family:item.payment_signal||item.payment_unavailable?'payment_invoice':'ml_anomaly'});
    const evidence=node('details');evidence.append(node('summary','Chứng từ và nguồn đối chiếu'));const refs=[];
    const addRef=(id,label,content)=>{const wrapper=node('div'),line=node('label'),check=node('input');line.className='check';check.type='checkbox';check.value=id;check.checked=state.feedback?.evidence_ids.includes(id)||false;refs.push(check);line.append(check,node('span',label));wrapper.append(line);if(content)wrapper.append(content);evidence.append(wrapper);check.addEventListener('input',()=>dirty=true);};
    for(const ev of item.evidence)addRef(ev.evidence_id,ev.record.record_id+' · Đã xem nguồn này',sourceCard(ev));box.append(evidence);
    const message=node('p',state.revision?'Đã lưu kết quả phiên bản '+state.revision:'Chưa ghi kết quả rà');message.className='review-message';message.setAttribute('role','status');
    const fields=node('fieldset');fields.id='ws-feedback';const input=(label,kind='textarea')=>{const l=node('label',label),n=node(kind);if(kind==='textarea'){n.maxLength=4000;n.rows=3;}l.append(n);fields.append(l);n.addEventListener('input',()=>dirty=true);return n;};
    const result=input('Kết quả nghiệp vụ','select');result.id='ws-outcome';for(const [v,label] of [['','Chọn kết quả sau khi đối chiếu'],...Object.entries(outcome)]){const o=node('option',label);o.value=v;result.append(o);}
    const explanation=input('Đã kiểm tra gì, căn cứ nào?');explanation.id='ws-explanation';const action=input('Cần ai làm gì tiếp theo?');action.id='ws-action';const missing=input('Tài liệu còn thiếu');missing.id='ws-missing';
    const completed=node('input');completed.type='checkbox';completed.id='ws-checks-completed';const ack=node('label');ack.className='check';ack.append(completed,node('span','Đã đối chiếu đủ tài liệu cho kết luận đang ghi'));fields.append(ack);completed.addEventListener('input',()=>dirty=true);
    const usefulness=input('Cảnh báo có giúp ích cho việc rà không?','select');usefulness.id='ws-usefulness';for(const [v,label] of [['not_assessed','Chưa đánh giá'],['yes','Có'],['no','Không']]){const o=node('option',label);o.value=v;usefulness.append(o);}const extra=node('details');extra.append(node('summary','Đánh giá hỗ trợ (tùy chọn)'),usefulness.closest('label'));fields.append(extra);
    const old=state.feedback;if(old){result.value=old.outcome;explanation.value=old.explanation;action.value=old.action;missing.value=old.missing_materials;usefulness.value=old.usefulness;completed.checked=old.checks_completed;}
    box.append(fields);const attachments=node('details');attachments.append(node('summary','Tài liệu bổ sung'));
    const casePath=base()+'/he/jobs/'+report.run_id+'/reviews/'+item.case_id;
    function attachment(meta){const b=node('button',meta.name+' · bổ sung, chưa xác minh');b.className='quiet';b.addEventListener('click',async()=>{try{const file=await api(casePath+'/attachments/'+meta.id);if(e!==epoch)return;const bytes=Uint8Array.from(atob(file.content),c=>c.charCodeAt(0));download(new Blob([bytes],{type:'application/octet-stream'}),file.name);}catch(error){failure(error);}});attachments.append(b);addRef(meta.id,meta.name+' · Đã xem tài liệu bổ sung');}
    for(const meta of state.attachments)attachment(meta);const upload=node('input');upload.type='file';upload.accept='.pdf,.png,.jpg,.jpeg';upload.setAttribute('aria-label','Bổ sung chứng từ');attachments.append(node('p','PDF/ảnh, tối đa 2 MB. Tài liệu bổ sung chưa tự trở thành chứng từ gốc đã xác minh.'),upload);box.append(attachments);
    upload.addEventListener('change',async()=>{const file=upload.files[0];if(!file)return;if(file.size>2*1024*1024){message.textContent='Tệp vượt 2 MB.';return;}upload.disabled=true;try{const content=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=reject;reader.readAsDataURL(file);});const value=await api(casePath+'/attachments',{name:file.name,content});if(e!==epoch)return;if(!refs.some(r=>r.value===value.attachment_id))attachment({id:value.attachment_id,name:file.name});message.textContent='Đã lưu tài liệu bổ sung, chưa xác minh chứng từ gốc.';}catch(error){failure(error);}finally{upload.disabled=false;upload.value='';}});
    function frozen(on){fields.disabled=on;upload.disabled=on;for(const ref of refs)ref.disabled=on;}
    const start=node('button','Bắt đầu rà'),save=node('button','Lưu kết quả rà'),elapsed=node('span',Math.round(state.active_seconds)+' giây đã lưu');start.id='ws-start';save.id='ws-save';save.disabled=true;const actions=node('div');actions.className='actions';actions.append(start,save,elapsed);box.append(actions,message);
    const history=node('details');history.append(node('summary','Lịch sử chỉnh sửa'));const historyText=node('pre',JSON.stringify(state.history,null,2));history.append(historyText);box.append(history);
    start.addEventListener('click',async()=>{start.disabled=true;try{const value=await api(casePath+'/start',{});if(e!==epoch||selected!==item.case_id)return;lease=value.lease;save.disabled=false;message.textContent='Đang rà. Đối chiếu nguồn rồi ghi kết quả.';beat=setInterval(async()=>{if(document.hidden||!lease)return;try{const b=await api(casePath+'/heartbeat',{lease});if(e===epoch&&selected===item.case_id)elapsed.textContent=Math.round(state.active_seconds+b.active_seconds)+' giây kết nối';}catch(error){clearInterval(beat);lease=null;save.disabled=true;start.disabled=false;message.textContent='Kết nối rà bị gián đoạn. Bấm Bắt đầu rà để tiếp tục; nội dung đang nhập vẫn được giữ.';failure(error);}},5000);}catch(error){start.disabled=false;failure(error);}});
    save.addEventListener('click',async()=>{if(!lease)return;if(!pending){if(!result.value||!explanation.value.trim()){message.textContent='Chọn kết quả và ghi rõ đã kiểm tra gì trước khi lưu.';return;}pending={lease,expected_revision:state.revision,request_id:crypto.randomUUID(),feedback:{outcome:result.value,usefulness:usefulness.value,explanation:explanation.value,action:action.value,missing_materials:missing.value,evidence_ids:refs.filter(x=>x.checked).map(x=>x.value),checks_completed:completed.checked}};}
      save.disabled=true;frozen(true);try{const value=await api(casePath+'/save',pending);if(e!==epoch||selected!==item.case_id)return;state=value;item.review=value;pending=null;lease=null;dirty=false;clearInterval(beat);frozen(false);start.disabled=false;save.disabled=true;message.textContent='Đã lưu kết quả phiên bản '+state.revision+' trên server.';historyText.textContent=JSON.stringify(state.history,null,2);elapsed.textContent=Math.round(state.active_seconds)+' giây đã lưu';renderCases();const reviewed=report.cases.filter(c=>c.review.revision>0).length;metrics('ws-review-metrics',[['Giao dịch',report.row_count],['Chưa ghi kết quả',report.row_count-reviewed],['Đã ghi kết quả',reviewed],['Chưa đủ căn cứ',report.cases.filter(c=>c.review.feedback?.outcome==='inconclusive').length]]);
      }catch(error){if(e===epoch){save.disabled=false;if(error.status){pending=null;frozen(false);}if(error.status===409){clearInterval(beat);lease=null;save.disabled=true;start.disabled=false;}message.textContent=error.message+(error.status===409?' Làm mới phiếu để xem bản lưu gần nhất.':error.status?'':' Bấm Lưu kết quả rà để gửi lại cùng yêu cầu.');if(!error.status||[401,403].includes(error.status))failure(error);}}});
  }
  function download(blob,name){const url=URL.createObjectURL(blob),a=node('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  async function exportReport(kind){try{if(kind==='json'){const data=await api(runPath()+'/report');download(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}),'agent2-'+company+'-'+report.run_id+'.json');return;}const headers=portal?{'X-Platform':'1','X-Session':token}:{Authorization:'Bearer '+token};const response=await fetch(mount+runPath()+'/report.csv',{headers,cache:'no-store'});if(!response.ok){const e=Error('Chưa tải được báo cáo. Kiểm tra phiên và thử lại.');e.status=response.status;throw e;}download(await response.blob(),'agent2-'+company+'-'+report.run_id+'.csv');}catch(error){failure(error);}}
  async function sync(){
    if(portal){const current=sessionStorage.getItem('kt-session')||'';if(!current){lock('Đăng nhập từ Portal để mở đúng doanh nghiệp được cấp quyền.');return;}if(current!==token){clear();token=current;identity='';}}
    if(!token)return;const e=epoch;
    try{const value=await api('/api/v1/ui/context');if(e!==epoch)return;const id=value.actor_id+'|'+value.context_id;if(identity===id)return;clear();identity=id;actorID=value.actor_id;contextID=value.context_id||'';show('ws-login',false);show('ws-selection');put('ws-company',...value.companies.map(c=>{const o=node('option',c);o.value=c;return o;}));if(!value.companies.length){company='';history.replaceState(null,'',location.pathname+location.search);remember();notice('Chưa được cấp doanh nghiệp để làm việc.');return;}
      const desired=selection();let last='',shared,imported;try{shared=JSON.parse(sessionStorage.getItem('agent2.company.selection'));imported=JSON.parse(sessionStorage.getItem('agent2.workbench'));last=localStorage.getItem('agent2.workspace.company')||'';}catch{/* optional */}
      const remembered=shared?.version===1&&shared.actor===actorID&&shared.context===contextID&&value.companies.includes(shared.company)?shared.company:null;
      const legacy=!shared?(imported?.actor===actorID&&value.companies.includes(imported.company)?imported.company:value.companies.includes(last)?last:null):null;
      company=value.companies.includes(desired.company)?desired.company:remembered||legacy||value.companies[0];$('ws-company').value=company;remember();
      const run=desired.company===company&&/^herun_[a-f0-9]{32}$/.test(desired.run||'')?desired.run:null;
      history.replaceState(null,'',location.pathname+location.search+'#'+new URLSearchParams({company,...(run?{run}:{})}));
      if(run)await loadRun(run);else await loadHome();if(desired.company&&desired.company!==company)notice('Doanh nghiệp trong liên kết không còn khả dụng theo quyền hiện tại. Đang mở '+company+'.');
    }catch(error){failure(error);}
  }
  $('ws-company').addEventListener('change',()=>{if(dirty&&!confirm('Bỏ nội dung phiếu chưa lưu để chuyển doanh nghiệp?')){$('ws-company').value=company;return;}clear();company=$('ws-company').value;remember();route();});$('ws-refresh').addEventListener('click',()=>{if(dirty&&!confirm('Bỏ nội dung chưa lưu và tải bản mới nhất?'))return;report?loadRun(report.run_id):loadHome();});$('ws-back').addEventListener('click',()=>{if(dirty&&!confirm('Bỏ nội dung phiếu chưa lưu để về danh sách?'))return;route();});
  for(const id of ['ws-search','ws-filter'])$(id).addEventListener('input',renderCases);$('ws-rem-filter')?.addEventListener('change',loadRemediationOverview);$('ws-csv').addEventListener('click',()=>exportReport('csv'));$('ws-json').addEventListener('click',()=>exportReport('json'));
  $('ws-compare').addEventListener('click',()=>loadComparison(true));$('ws-comparison-refresh').addEventListener('click',()=>loadComparison(false));$('ws-comparison-export').addEventListener('click',async()=>{try{const value=await api(runPath()+'/comparison');download(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}),'agent2-comparison-'+company+'-'+value.plan_id+'.json');}catch(error){failure(error);}});
  $('ws-resume').addEventListener('click',async()=>{const id=report.run_id;$('ws-resume').disabled=true;try{await api(base()+'/he/jobs/'+id+'/resume',{});await loadRun(id);}catch(error){failure(error);}finally{$('ws-resume').disabled=false;}});
  window.addEventListener('hashchange',()=>{if(!token||!identity)return;const s=selection();if(s.company&&s.company!==company){if([...$('ws-company').options].some(o=>o.value===s.company)){company=s.company;$('ws-company').value=company;remember();}else{history.replaceState(null,'',location.pathname+location.search+'#'+new URLSearchParams({company}));loadHome().then(()=>notice('Doanh nghiệp trong liên kết chưa được cấp quyền.'));return;}}if(s.run)loadRun(s.run);else loadHome();});
  window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue='';}});window.addEventListener('focus',()=>portal&&sync());
  $('ws-connect').addEventListener('click',async()=>{token=$('ws-credential').value.trim();$('ws-credential').value='';identity='';await sync();});
  (async()=>{try{const response=await fetch(mount+'/api/v1/ui/settings',{cache:'no-store'});const settings=await response.json();portal=settings.auth_mode==='portal';show('local-access',!portal);if(!portal){show('ws-login');return;}await sync();setInterval(sync,15000);}catch(error){lock('Chưa kết nối được Agent2. Bật Agent2 từ Portal rồi tải lại trang.');}})();
})();
