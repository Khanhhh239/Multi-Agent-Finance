'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const mount = location.pathname.startsWith('/agent2/') ? '/agent2' : '';
  let portalMode = !!mount, portalContext = '', portalSyncing = false;
  let encryptedMode=false,bundleMode=false;
  const state = {token:'', actor:'', company:'', epoch:0, busy:false, draft:null, preview:null,
    uploadKey:null, commitKey:null, fileHash:null, saved:null, result:null, controller:null};
  let sourceIntake;
  const labels = {needs_review:'Cần đối chiếu', unavailable:'Chưa đủ nguồn', no_signal:'Chưa thấy tín hiệu', not_applicable:'Không áp dụng', context_only:'Cần thêm bối cảnh'};
  const tables = {transactions:'Giao dịch',companies:'Doanh nghiệp',vendors:'Nhà cung cấp',invoices:'Hóa đơn',payment_allocations:'Phân bổ thanh toán',employees:'Nhân viên',approvals:'Phê duyệt',supporting_documents:'Chứng từ',payment_history_coverage:'Phạm vi lịch sử',vendor_bank_history:'Lịch sử tài khoản'};
  const fields = {record_id:'mã bản ghi',amount_vnd:'số tiền',effective_at:'thời điểm hiệu lực',observed_at:'thời điểm nguồn được biết',company_id:'mã doanh nghiệp',tenant_id:'đơn vị quản lý',payment_channel:'kênh thanh toán',vendor_ref:'liên kết nhà cung cấp',transaction_ref:'liên kết giao dịch',invoice_ref:'liên kết hóa đơn',revision:'phiên bản',kind:'loại giao dịch'};
  const sourceLimits = {
    P1_INPUT_UNAVAILABLE:['Thanh toán hóa đơn','Chưa đủ kênh thanh toán, liên kết hóa đơn hoặc phạm vi lịch sử để đối chiếu.','Bổ sung kênh thanh toán, phân bổ–hóa đơn và bản khai phạm vi lịch sử có nguồn. Không điền số 0 thay lịch sử còn thiếu.'],
    DOCUMENT_BASIS_MISSING:['Chứng từ gốc','Chưa có đủ chứng từ gốc đã xác minh để kết luận nghiệp vụ.','Bổ sung và đối chiếu chứng từ của đúng giao dịch hoặc hóa đơn. Bản mô phỏng và bản xuất nguồn chưa thay cho chứng từ gốc đã xác minh.'],
    BANK_HISTORY_MISSING:['Lịch sử tài khoản nhà cung cấp','Chưa đủ nguồn để kiểm tra thay đổi tài khoản nhà cung cấp.','Bổ sung lịch sử tài khoản, ngày hiệu lực và ngày nguồn được biết.'],
    INVOICE_LINK_MISSING:['Liên kết hóa đơn','Có khoản thanh toán chưa liên kết được với hóa đơn.','Bổ sung bản ghi phân bổ thanh toán và hóa đơn được tham chiếu.'],
    APPROVAL_BASIS_MISSING:['Phê duyệt khoản chi','Chưa đủ nguồn để xác nhận dấu vết phê duyệt.','Bổ sung bản ghi phê duyệt của đúng khoản chi. Thiếu bản ghi chưa chứng minh khoản chi chưa được duyệt.']
  };
  const key = () => crypto.randomUUID();
  function vietnamInput(value) {const d=new Date(value);if(Number.isNaN(d.getTime()))throw Error('Mốc nguồn đã lưu không hợp lệ.');return new Date(d.getTime()+7*3600*1000).toISOString().slice(0,19);}
  const node = (tag,text,cls) => {const n=document.createElement(tag);if(text!==undefined)n.textContent=String(text);if(cls)n.className=cls;return n;};
  const put = (id,...children) => $(id).replaceChildren(...children);
  const show = (id,visible=true) => {$(id).hidden=!visible;};
  function notify(message) {put('notice',node('span',message));show('notice',!!message);}
  function progress(step) {for(let i=1;i<=4;i++){if(i===step)$('step'+i).setAttribute('aria-current','step');else $('step'+i).removeAttribute('aria-current');}}
  function money(value) {if(value===null||value===undefined)return "Chưa đủ dữ liệu";try{return BigInt(value).toLocaleString('vi-VN')+' đ';}catch{return 'Số tiền không hợp lệ';}}
  function date(value) {const d=new Date(value);return Number.isNaN(d.getTime())?String(value):d.toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',hour12:false})+' (UTC+07)';}
  function metadata(id,entries) {put(id,...entries.flatMap(([k,v])=>[node('dt',k),node('dd',v)]));}
  // Preserve signed VND integers beyond Number.MAX_SAFE_INTEGER. Never transform source uploads.
  function parseResponse(text) {
    let out='',i=0;
    while(i<text.length){const c=text[i];if(c==='"'){let start=i++;while(i<text.length){if(text[i]==='\\'){i+=2;continue;}if(text[i++]==='"')break;}out+=text.slice(start,i);}
      else if(c==='-'||/[0-9]/.test(c)){const m=text.slice(i).match(/^-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?/);if(!m)throw Error('Phản hồi JSON không hợp lệ.');const raw=m[0];out+=!/[.eE]/.test(raw)&&!Number.isSafeInteger(Number(raw))?JSON.stringify(raw):raw;i+=raw.length;}
      else{out+=c;i++;}}
    return JSON.parse(out);
  }
  async function api(path,body,headers={},method) {
    const authHeaders = portalMode ? {'X-Session':state.token,'X-Platform':'1'} : {Authorization:'Bearer '+state.token};
    const opts={method:method||(body===undefined?'GET':'POST'),headers:{...authHeaders,...headers},signal:state.controller?.signal,cache:'no-store'};
    if(body!==undefined){opts.body=typeof body==='string'||body instanceof ArrayBuffer?body:JSON.stringify(body);if(!opts.headers['Content-Type'])opts.headers['Content-Type']='application/json';}
    let response;try{response=await fetch(mount+path,opts);}catch(e){if(e.name==='AbortError')throw e;throw Error("Mất kết nối hệ thống xử lý. Thử lại thao tác này; yêu cầu lưu sẽ giữ mã chống trùng.");}let result;
    try{result=parseResponse(await response.text());}catch{throw Error("Hệ thống xử lý trả kết quả không đọc được. Kiểm tra kết nối rồi thử lại.");}
    if(!response.ok){const e=Error((result.errors||[]).map(x=>x.message+' '+(x.action||'')).join('\n')||result.error||'Không thực hiện được yêu cầu.');e.status=response.status;e.report=result;throw e;}
    return result;
  }
  function base(){return '/api/v1/companies/'+encodeURIComponent(state.company)+'/';}
  function remember() {if(!state.saved)return;try{sessionStorage.setItem('agent2.workbench',JSON.stringify({actor:state.actor,context:portalContext,company:state.company,snapshot:state.saved.snapshot_id,asOf:$('as-of').value}));}catch{/* private mode */}}
  function buttons(){const file=$('file').files[0];$('validate').disabled=!state.token||!state.company||!file||state.busy;
    $('save').disabled=state.busy||!state.preview||state.preview.status==='rejected'||!$('ack').checked||!!state.saved;
    $('ack').disabled=state.busy||!!state.saved;$('analyze').disabled=state.busy||!state.saved||!$('as-of').value;
    $('company').disabled=!state.token||state.busy;$('file').disabled=!state.token||!state.company||state.busy;
    $('connect').disabled=state.busy;$('as-of').disabled=state.busy;$('edit-source').disabled=state.busy;$('new-import').disabled=state.busy;
    sourceIntake?.buttons(state.busy,!!state.token&&!!state.company,!!file);if(sourceIntake?.enabled)$('validate').disabled=state.busy||!state.token||!state.company||!file||!sourceIntake.info;}
  function invalidate(){state.epoch++;state.controller?.abort();state.controller=null;state.busy=false;state.draft=null;state.preview=null;state.uploadKey=null;state.commitKey=null;state.fileHash=null;state.saved=null;state.result=null;$('ack').checked=false;
    for(const id of ['preview-panel','save-panel','analysis-panel','results'])show(id,false);for(const id of ['rows','groups','run-meta','snapshot-meta','snapshot-summary','branch-summary','results-source-limits','rule-readiness'])put(id);show('input-panel');sourceIntake?.editing();notify('');progress(1);buttons();}
  function invalidateMapping(){const retained={draft:state.draft,uploadKey:state.uploadKey,fileHash:state.fileHash};invalidate();Object.assign(state,retained);state.commitKey=key();buttons();}
  async function run(task){if(state.busy)return;state.busy=true;const epoch=state.epoch;state.controller=new AbortController();buttons();notify('');try{await task(epoch);}catch(error){if(epoch===state.epoch&&error.name!=='AbortError'){if(portalMode&&error.status===401)clearPortal(error.message);else{notify(error.message);if(portalMode&&error.status===403){show('results',false);setTimeout(syncPortal,0);}}}}finally{if(epoch===state.epoch){state.busy=false;state.controller=null;buttons();}}}
  const current = epoch => {if(epoch!==state.epoch)throw new DOMException('Nguồn đã thay đổi','AbortError');};
  async function bytesAndHash(){const file=$('file').files[0];if(!file)throw Error('Chọn lại tệp dữ liệu.');if(!/\.(json|csv|xlsx)$/i.test(file.name))throw Error("Chọn tệp CSV, Excel.xlsx hoặc JSON.");if(!file.size||file.size>10*1024*1024)throw Error('Tệp phải có dữ liệu và không vượt 10 MB.');
    let bytes,actualFile=file;try{if(sourceIntake?.enabled){const packed=await sourceIntake.pack($('file').files);bytes=packed.bytes;actualFile=packed.file;}else bytes=await file.arrayBuffer();}catch(error){throw Error(error.name==='Error'?error.message:'Không đọc được tệp hoặc tệp đã đổi trên máy. Chọn lại tệp rồi kiểm tra lại.');}const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),x=>x.toString(16).padStart(2,'0')).join('');return {bytes,hash,file:actualFile};}
  async function ensureUpload(epoch,requireInspected=false){const {bytes,hash,file}=await bytesAndHash();current(epoch);if(requireInspected&&sourceIntake.info?.source_hash!==hash){sourceIntake.reset();throw Error('Tệp đã đổi sau khi đọc bảng. Bấm Đọc bảng và cột rồi kiểm tra lại.');}if(hash!==state.fileHash){state.draft=null;state.uploadKey=key();state.commitKey=key();}state.fileHash=hash;if(!state.draft)state.draft=await api(base()+'imports/upload',bytes,{'Content-Type':'application/octet-stream','X-File-Name':encodeURIComponent(file.name),'Idempotency-Key':state.uploadKey});current(epoch);}
  function issueLocation(issue){const parts=(issue.path||'').split('/').filter(Boolean);const table=issue.table||parts[0];const row=issue.row||(/^\d+$/.test(parts[1]||'')?Number(parts[1])+1:null);const field=parts.slice(2).map(x=>fields[x]||x).join(' / ');
    return [issue.file?'Tệp '+issue.file:issue.sheet?'Sheet '+issue.sheet:tables[table]||table,issue.csv_row?'Dòng CSV '+issue.csv_row:row?'Dòng '+row:null,field?'Trường '+field:issue.field?'Trường '+issue.field:null,issue.json_line?'Dòng JSON '+issue.json_line+(issue.json_column?', cột '+issue.json_column:''):null].filter(Boolean).join(' · ');}
  function issueCard(issue,error=false){const n=node('div',undefined,'issue'+(error?' error':''));n.append(node('strong',issueLocation(issue)||'Kiểm tra dữ liệu'),node('p',issue.message||'Chưa đủ thông tin.'),node('p',issue.action||'Bổ sung nguồn và kiểm tra lại tệp.'));
    if(issue.affected_count!==undefined)n.append(node('small','Ảnh hưởng '+issue.affected_count+' giao dịch.'));
    if(issue.affected_rows?.length){const d=node('details');d.append(node('summary','Giao dịch liên quan'),node('p',issue.affected_rows.map(r=>(r.record_id||'')+(r.row?' (dòng '+r.row+')':'')).join(', ')+(issue.affected_rows_truncated?' · Danh sách chỉ hiển thị một phần; xem đầy đủ sau khi phân tích.':'')));n.append(d);}return n;}
  function renderPreview(report){show('preview-panel');show('input-panel',report.status==='rejected');progress(2);put('preview-source',node('span','Doanh nghiệp '+state.company+' · '+($('file').files[0]?.name||'Tệp đã chọn')));put('errors',...((report.errors||[]).map(x=>issueCard(x,true))));const limitCodes=new Set(Object.values(report.analysis_limits||{}).flat().map(x=>x.code));put('warnings',...((report.warnings||[]).filter(x=>!(report.rule_readiness&&x.code==='RULE_PROFILE_LIMITS')&&!limitCodes.has(x.code)&&!(limitCodes.size&&x.code==='CAPABILITY_UNAVAILABLE'&&x.path!=='/transactions')).map(x=>issueCard(x))));
    const limits=Object.values(report.analysis_limits||{}).flat();put('limits',...(limits.length?[node('h3',"Phần chưa đủ dữ liệu"),...limits.map(x=>{const [title,message,action]=sourceLimits[x.code]||['Nguồn liên quan',x.message,x.action];const card=node('div',undefined,'issue');card.append(node('strong',title+' · '+x.affected_count+' giao dịch'),node('p',message));const detail=node('details');detail.append(node('summary','Cần bổ sung gì?'),node('p',action));if(x.affected_rows?.length)detail.append(node('p','Giao dịch: '+x.affected_rows.map(r=>r.record_id+(r.row?' (dòng '+r.row+')':'')).join(', ')+(x.affected_rows_truncated?' · Danh sách rút gọn. Xem kết quả từng giao dịch sau khi lưu.':'')));card.append(detail);return card;})]:[]));
    const counts=report.counts||{};const count=counts.transactions;
    put('preview-summary',node('p',report.status==='rejected'?'Tệp chưa thể lưu. Sửa các lỗi bên dưới rồi chọn lại tệp.':'Tệp đạt kiểm tra cấu trúc. Bạn có thể lưu sau khi xem các giới hạn nguồn.',report.status==='rejected'?'':'good'),...(count!==undefined?[node('p',String(count)+' bản ghi giao dịch trong tệp.')]:[]));
    if(report.contract_version!=='agent2-rule-snapshot/1.0.0'&&(count>200||Object.values(counts).reduce((a,b)=>a+Number(b),0)>1000))$('preview-summary').append(node('p','Có thể lưu tệp, nhưng màn hình xem kết quả hiện chỉ nhận tối đa 200 bản ghi giao dịch và 1.000 bản ghi nguồn. Không cắt bỏ lịch sử để vượt giới hạn này.','issue'));
    metadata('preview-meta',[['Doanh nghiệp',state.company],['Hợp đồng',report.contract_version||'—'],['Phiên bản tệp',report.revision||'—'],['Có hiệu lực đến',report.expires_at?date(report.expires_at):'—'],['Checksum tệp',report.source_hash||'—']]);
    show('save-panel',report.status!=='rejected');$('ack').checked=false;put('save-status','');sourceIntake?.readiness(report);if(report.rule_readiness){const technical=(report.warnings||[]).filter(x=>x.code==='RULE_PROFILE_LIMITS');if(technical.length){const d=node('details');d.append(node('summary','Chi tiết kỹ thuật nhập nguồn'));for(const item of technical)d.append(node('p',item.message));$('warnings').append(d);}}sourceIntake?.editing(report.status==='rejected');buttons();}
  sourceIntake=new window.RuleSourceIntake({change:invalidateMapping,modeChange:invalidate});
  $('inspect-source').addEventListener('click',()=>run(async epoch=>{await ensureUpload(epoch);let info;try{info=await api(base()+'imports/'+state.draft.import_id+'/inspect',{expected_revision:state.draft.revision});}catch(error){if(error.report)renderPreview(error.report);throw error;}current(epoch);sourceIntake.render(info);buttons();}));
  function analysisLink(){
    if(state.actor&&state.company){try{sessionStorage.setItem('agent2.company.selection',JSON.stringify({version:1,actor:state.actor,context:portalContext,company:state.company,page:'data-import'}));}catch{/* optional selection */}}
    for(const link of document.querySelectorAll('header a[href]')){const page=new URL(link.href).pathname.split('/').pop();if(['workspace','encrypted-analysis','pipeline-workspace'].includes(page))link.href=mount+'/'+page+(state.company?'#company='+encodeURIComponent(state.company):'');}
  }
  async function acceptContext(context,epoch){current(epoch);state.actor=context.actor_id;portalContext=context.context_id||'';$('credential').value='';
    put('company',...context.companies.map(c=>{const o=node('option',c);o.value=c;return o;}));state.company=$('company').value;put('actor',node('span','Đã kết nối · '+state.actor));show('identity');show('connection',false);
    if(!context.companies.length)notify('Tài khoản chưa có doanh nghiệp được cấp quyền nhập. Yêu cầu quản lý cấp quyền.');
    let last,shared;try{last=JSON.parse(sessionStorage.getItem('agent2.workbench'));shared=JSON.parse(sessionStorage.getItem('agent2.company.selection'));}catch{/* absent */}
    const desired=new URLSearchParams(location.hash.slice(1)).get('company');
    const remembered=shared?.version===1&&shared.actor===state.actor&&shared.context===portalContext&&context.companies.includes(shared.company)?shared.company:null;
    const legacy=!shared&&last?.actor===state.actor&&context.companies.includes(last.company)?last.company:null;
    state.company=context.companies.includes(desired)?desired:remembered||legacy||context.companies[0]||'';$('company').value=state.company;
    if(last?.company!==state.company||last?.context!==undefined&&last.context!==portalContext||shared&&!remembered||desired&&!context.companies.includes(desired))last=null;
    history.replaceState(null,'',location.pathname+location.search+(state.company?'#company='+encodeURIComponent(state.company):''));
    if(last?.actor===state.actor&&context.companies.includes(last.company)){state.company=last.company;$('company').value=last.company;let snapshot;try{snapshot=await api(base()+'snapshots/'+encodeURIComponent(last.snapshot));}catch(e){if(e.status===403||e.status===404){sessionStorage.removeItem('agent2.workbench');if(portalMode)return acceptContext(await api('/api/v1/ui/context'),epoch);notify('Bản dữ liệu trước không còn khả dụng theo quyền hiện tại. Chọn tệp để bắt đầu lần nhập mới.');return;}throw e;}
      let restoredAsOf=last.asOf;
      if(snapshot.contract_version==='agent2-rule-snapshot/1.0.0'){
        let sourceAsOf;
        try{
          const report=await api(base()+'imports/'+encodeURIComponent(snapshot.origin_import_id)+'/report');
          if(report.report_hash!==snapshot.origin_report_hash||!report.required_as_of)throw Error('Chưa xác nhận được mốc nguồn của bản dữ liệu đã lưu.');
          sourceAsOf=report.required_as_of;
        }catch(error){
          if(![403,404].includes(error.status))throw error;
          // Snapshots are shared within the authorized company; draft reports
          // belong to their importing actor. Read the checksum-verified source
          // through the existing snapshot permission, never broaden draft access.
          const source=await api(base()+'snapshots/'+encodeURIComponent(snapshot.snapshot_id)+'/data');
          if(source.contract_version!==snapshot.contract_version||source.tenant_id!==snapshot.tenant_id||source.company_id!==snapshot.company_id||!source.source?.as_of)throw Error('Nguồn bản dữ liệu đã lưu không khớp doanh nghiệp.');
          sourceAsOf=source.source.as_of;
        }
        restoredAsOf=vietnamInput(sourceAsOf);
      }
      current(epoch);setSaved(snapshot,restoredAsOf);notify('Đã khôi phục bản dữ liệu đã lưu. Bấm xem kết quả để chạy lại đúng thời điểm đã chọn.');}
    show('portal-access',false);
    analysisLink();
  }
  $('connect').addEventListener('click',()=>run(async epoch=>{const token=$('credential').value.trim();if(!token)throw Error('Nhập mã truy cập do quản lý cấp.');state.token=token;let context;try{context=await api('/api/v1/ui/context');}catch(e){state.token='';throw e;}await acceptContext(context,epoch);}));
  function clearPortal(message){sourceIntake.reset();invalidate();state.token='';state.actor='';state.company='';portalContext='';$('credential').value='';$('file').value='';put('company',node('option',"Đăng nhập trang chung để chọn doanh nghiệp"));sessionStorage.removeItem('agent2.workbench');show('connection',false);show('identity',false);show('portal-access');put('portal-message',node('span',message||"Mở khóa trang chung một lần để làm việc với Agent2."));show('input-panel',false);buttons();}
  async function syncPortal(){if(!mount||state.busy||portalSyncing)return;portalSyncing=true;const epoch=state.epoch;try{const token=sessionStorage.getItem('kt-session')||'';if(!token){if(state.token||!$('portal-access').hidden)clearPortal("Mở khóa trang chung để xem dữ liệu Agent2.");return;}state.token=token;const context=await api('/api/v1/ui/context');current(epoch);if(state.actor&&portalContext!==context.context_id){$('file').value='';sourceIntake.reset();invalidate();sessionStorage.removeItem('agent2.workbench');}if(!state.actor||portalContext!==context.context_id){show('input-panel');await acceptContext(context,state.epoch);}buttons();}catch(e){if(e.name!=='AbortError')clearPortal(e.message);}finally{portalSyncing=false;}}
  $('disconnect').addEventListener('click',()=>{sourceIntake.reset();if(portalMode){window.top.location.assign('/#data');return;}invalidate();state.token='';state.actor='';state.company='';$('credential').value='';$('file').value='';put('company',node('option','Kết nối để chọn doanh nghiệp'));sessionStorage.removeItem('agent2.workbench');show('connection');show('identity',false);buttons();});
  $('company').addEventListener('change',()=>{state.company=$('company').value;history.replaceState(null,'',location.pathname+'#company='+encodeURIComponent(state.company));analysisLink();$('file').value='';sourceIntake.reset();invalidate();put('file-info',node('span','Chọn tệp của doanh nghiệp '+state.company+'. Cần kiểm tra lại trước khi lưu.'));});
  $('file').addEventListener('change',()=>{sourceIntake.reset();invalidate();const file=$('file').files[0];put('file-info',node('span',file?($('file').files.length>1?$('file').files.length+' tệp CSV':file.name)+' · Cần kiểm tra trước khi lưu.':'Chưa chọn tệp.'));});
  $('date-format').addEventListener('change',()=>invalidate());
  $('validate').addEventListener('click',()=>run(async epoch=>{state.preview=null;state.saved=null;state.result=null;$('ack').checked=false;show('save-panel',false);show('analysis-panel',false);show('preview-panel',false);
    const settings=sourceIntake.enabled?sourceIntake.settings():null;await ensureUpload(epoch,!!settings);
    if(settings){state.draft=await api(base()+'imports/'+state.draft.import_id+'/mapping',{expected_revision:state.draft.revision,mapping:settings},{'Idempotency-Key':key()},'PUT');current(epoch);}
    else if($('date-format').value!=='iso'&&!state.draft.dateMapping){state.draft=await api(base()+'imports/'+state.draft.import_id+'/mapping',{expected_revision:state.draft.revision,mapping:{date_format:$('date-format').value}},{'Idempotency-Key':state.uploadKey+'-date'},'PUT');state.draft.dateMapping=true;current(epoch);}
    try{state.preview=await api(base()+'imports/'+state.draft.import_id+'/preview',{expected_revision:state.draft.revision});}catch(e){if(e.report){renderPreview(e.report);}throw e;}current(epoch);renderPreview(state.preview);
    $('preview-panel').scrollIntoView({behavior:'smooth',block:'start'});
  }));
  $('ack').addEventListener('change',()=>{progress($('ack').checked?3:2);buttons();});
  $('edit-source').addEventListener('click',()=>{invalidate();$('company').focus();});
  $('new-import').addEventListener('click',()=>{$('file').value='';invalidate();$('file').focus();});
  function setSaved(snapshot,restoredAsOf){state.saved=snapshot;$('analyze').textContent=bundleMode?'Ti\u1ebfp t\u1ee5c \u0111\u1ebfn v\u1ee5 c\u1ea7n r\u00e0':snapshot.contract_version==='agent2-rule-snapshot/1.0.0'?'Xem 35 luật tại node doanh nghiệp':'Xem kết quả kiểm tra';if(state.preview?.required_as_of)$('as-of').value=vietnamInput(state.preview.required_as_of);else if(restoredAsOf)$('as-of').value=restoredAsOf;show('analysis-panel');show('input-panel',false);show('preview-panel',false);show('save-panel',false);progress(4);put('snapshot-summary',node('span','Doanh nghiệp '+state.company+' · Bản dữ liệu '+snapshot.snapshot_id));metadata('snapshot-meta',[["Mã bản dữ liệu",snapshot.snapshot_id],['Checksum',snapshot.checksum],['Checksum dữ liệu',snapshot.data_checksum],['Hợp đồng',snapshot.contract_version]]);remember();}
  $('save').addEventListener('click',()=>run(async epoch=>{if(!state.preview||!$('ack').checked)throw Error('Xem kết quả kiểm tra và xác nhận trước khi lưu.');
    const {hash}=await bytesAndHash();current(epoch);if(hash!==state.fileHash){invalidate();notify('Tệp đã thay đổi. Kiểm tra lại tệp trước khi lưu.');return;}
    if(Date.parse(state.preview.expires_at)<=Date.now()){state.preview=null;show('save-panel',false);show('preview-panel',false);show('input-panel');progress(1);throw Error('Kết quả kiểm tra đã hết hạn. Bấm Kiểm tra tệp để kiểm tra lại.');}
    const request={expected_revision:state.preview.revision,acknowledge:true};for(const name of ['preview_id','source_hash','mapping_hash','report_hash','context_hash'])request[name]=state.preview[name];
    put('save-status',node('span','Đang lưu…'));
    let receipt;try{receipt=await api(base()+'imports/'+state.draft.import_id+'/commit',request,{'Idempotency-Key':state.commitKey});}catch(e){if(e.status===409){invalidate();notify(e.message+' Kiểm tra lại tệp trước khi lưu.');return;}put('save-status',node('span','Chưa nhận được xác nhận lưu. Thử lại giữ nguyên yêu cầu.'));throw e;}current(epoch);setSaved(receipt.snapshot);notify('');$('analysis-panel').scrollIntoView({behavior:'smooth'});
  }));
  function refText(ref){return (ref.source||ref.record_type)+' · '+(ref.document_number?'Số '+ref.document_number+' · ':'')+(ref.display_name?ref.display_name+' · ':'')+ref.record_id+' · phiên bản '+ref.revision+' · '+(ref.source_kind==='simulated'?'Dữ liệu mô phỏng':'Bản xuất nguồn, chưa tự xác minh')+' · Được biết: '+date(ref.observed_at);}
  function renderCheck(check,kind){const box=node('div',undefined,'check-result');box.append(node('h4',check.name),node('span',labels[check.status]||check.status,'badge '+check.status));
    const why=check.reason||(check.status==='needs_review'?(kind==='vendor_names'?'Có tên nhà cung cấp tương tự trong danh mục. Cần đối chiếu định danh và hồ sơ gốc để phân biệt.':check.group_refs?.length?'Khoản chi thuộc nhóm thanh toán cùng thời điểm cần đối chiếu. Xem tổng của cả nhóm ở trên.':'Số phân bổ lũy kế có dấu hiệu vượt giá trị hóa đơn; cần đối chiếu nghĩa vụ và chứng từ.'):check.status==='no_signal'?'Chưa phát hiện dấu hiệu theo kiểm tra này trong nguồn hiện có.':check.status==='not_applicable'?'Kiểm tra này không áp dụng cho loại giao dịch này.':'Chưa có đủ nguồn để thực hiện kiểm tra.');
    box.append(node('p','Vì sao? '+why));
    for(const fact of check.facts||[]){const lines=[['Giá trị hóa đơn',fact.invoice_gross_vnd],['Đã trả trước',fact.prior_paid_vnd],['Phân bổ hiện tại',fact.current_allocated_vnd],['Lũy kế',fact.cumulative_paid_vnd],['Phần vượt',fact.excess_vnd]].filter(([,v])=>v!==undefined);
      if(lines.length)box.append(node('p',lines.map(([k,v])=>k+': '+money(v)).join(' · '),'fact'));}
    const gaps=check.missing_sources||[];if(gaps.length){box.append(node('p','Nguồn cần bổ sung:'));const ul=node('ul');for(const gap of gaps)ul.append(node('li',(gap.source||'Nguồn')+(gap.record_id?' · '+gap.record_id:'')+'. '+(gap.action||'Bổ sung bản ghi nguồn có thời điểm.')));box.append(ul);}
    const refs=check.evidence_refs||[];if(refs.length){const d=node('details');d.append(node('summary','Căn cứ cần đối chiếu ('+refs.length+')'));const ul=node('ul',undefined,'evidence');for(const ref of refs)ul.append(node('li',refText(ref)));d.append(ul);box.append(d);}
    const next=check.next_action||(check.status==='unavailable'?'Bổ sung đúng nguồn còn thiếu, tạo bản dữ liệu mới rồi kiểm tra lại.':check.status==='needs_review'?'Đối chiếu hóa đơn, phân bổ và chứng từ liên quan; với tên nhà cung cấp, kiểm tra danh mục và định danh gốc. Chưa kết luận sai phạm.':check.status==='no_signal'?'Giữ căn cứ đối chiếu. Kết quả này không xác nhận giao dịch hợp lệ hoặc không có sai phạm.':'Tiếp tục các kiểm tra áp dụng khác.');
    box.append(node('p','Bước tiếp theo: '+next));
    for(const id of check.group_refs||[]){const a=node('a','Xem kiểm tra nhóm thanh toán');a.href='#'+id;a.className='text-link';box.append(a);}return box;}
  const branchLabels={available:'Đã chạy',partial:'Chạy một phần',unavailable:'Chưa khả dụng'};
  const branchOrder=['rules','statistics','graph','ml'];
  function drawGraph(branch){const figure=node('div',undefined,'graph-figure');const graphNodes=branch.nodes,byId=new Map(graphNodes.map(n=>[n.id,n]));
    if(graphNodes.length&&graphNodes.length<=10){const ns='http://www.w3.org/2000/svg';const svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 800 430');svg.setAttribute('role','img');svg.setAttribute('aria-label','Sơ đồ quan hệ từ các bản ghi đã biết');svg.classList.add('graph-canvas');const positions=new Map(graphNodes.map((n,i)=>[n.id,{x:400+270*Math.cos(2*Math.PI*i/graphNodes.length),y:215+140*Math.sin(2*Math.PI*i/graphNodes.length)}]));
      for(const link of branch.links){const a=positions.get(link.source),b=positions.get(link.target);if(!a||!b)continue;const edge=document.createElementNS(ns,'line');for(const [k,v] of Object.entries({x1:a.x,y1:a.y,x2:b.x,y2:b.y}))edge.setAttribute(k,v);edge.classList.add(link.context_only?'context-link':'source-link');svg.append(edge);}
      const description=node('p','Chọn một đối tượng để xem tên và mã nguồn.','hint');
      for(const n of graphNodes){const pos=positions.get(n.id);const labelX=Math.min(610,Math.max(150,pos.x));const g=document.createElementNS(ns,'g');g.setAttribute('tabindex','0');g.setAttribute('role','button');g.setAttribute('aria-label',n.kind+': '+n.label);const hit=document.createElementNS(ns,'rect');const left=Math.min(pos.x-18,labelX-145);hit.setAttribute('x',left);hit.setAttribute('y',pos.y-20);hit.setAttribute('width',Math.max(pos.x+18,labelX+145)-left);hit.setAttribute('height','65');hit.setAttribute('fill','transparent');g.append(hit);const dot=document.createElementNS(ns,'circle');dot.setAttribute('cx',pos.x);dot.setAttribute('cy',pos.y);dot.setAttribute('r','13');g.append(dot);const t=document.createElementNS(ns,'text');t.setAttribute('x',labelX);t.setAttribute('y',pos.y+30);t.setAttribute('text-anchor','middle');t.textContent=n.label.length>34?n.label.slice(0,31)+'…':n.label;g.append(t);const explain=()=>{description.textContent=n.kind+': '+n.label+(n.record_id?' · Mã nguồn '+n.record_id:'');};g.addEventListener('click',explain);g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();explain();}});svg.append(g);}figure.append(svg,description);}
    const listing=node('ul',undefined,'evidence');for(const link of branch.links){const a=byId.get(link.source),b=byId.get(link.target);const item=node('li',(a?.label||'Đối tượng')+' ↔ '+(b?.label||'Đối tượng')+' · '+link.relation+(link.context_only?' · Cần thêm bối cảnh':''));item.append(node('div',refText(link.evidence)));listing.append(item);}figure.append(listing);return figure;
  }
  function renderBranch(kind,branch){const detail=node('details',undefined,'analysis-branch');detail.dataset.branch=kind;const heading=node('summary');heading.append(node('span',branch.name),node('span',branchLabels[branch.status],'badge '+branch.status));detail.append(heading,node('p',branch.message));
    if(kind==='rules')detail.append(node('p',branch.evaluated_count+'/'+branch.total_count+' kiểm tra đã đánh giá · '+branch.not_applicable_count+' không áp dụng · '+branch.unavailable_count+' chưa khả dụng. Không có điểm tổng đầy đủ.'));
    if(kind==='statistics'||kind==='ml')for(const result of branch.results){const block=node('div',undefined,'method-result');block.append(node('h4',result.label),node('span',branchLabels[result.status],'badge '+result.status));if(result.available){block.append(node('p','Vị trí tương đối: '+result.relative_position.toLocaleString('vi-VN')+'/100 so với tập đối chiếu. Đây không phải xác suất sai phạm.','relative-position'));if(result.retrospective)block.append(node('span','Phân tích hồi cứu','tag'));if(result.inputs_adjusted)block.append(node('p','Một số đầu vào thiếu đã được xử lý theo thiết lập lưu cùng phiên bản.','hint'));}else block.append(node('p',result.reason));if(result.missing_sources.length)block.append(node('p','Nguồn còn thiếu: '+result.missing_sources.join(', ')));detail.append(block);}
    if(kind==='graph'){for(const finding of branch.findings)detail.append(node('p',finding.description,'callout'));if(branch.nodes.length)detail.append(drawGraph(branch));for(const gap of branch.missing_sources)detail.append(node('p',gap.source+' · '+gap.record_id+'. '+gap.action,'issue'));}
    return detail;
  }
  function renderRows(){const result=state.result;if(!result)return;const filter=$('filter').value;const rows=result.rows.filter(r=>{const statuses=Object.values(r.checks).map(c=>c.status);if(filter==='all')return true;if(filter==='analysis_unavailable')return Object.values(r.branches).some(b=>b.status!=='available');if(filter==='no_signal')return statuses.includes('no_signal')&&!statuses.some(s=>s==='needs_review'||s==='unavailable');if(filter==='not_applicable')return statuses.every(s=>s==='not_applicable');return statuses.includes(filter);});
    put('rows',...rows.map(row=>{const card=node('article',undefined,'transaction');const head=node('div',undefined,'tx-heading');const info=node('div');info.append(node('h3','Giao dịch '+row.transaction_id),node('div',row.description||''),node('small',date(row.event_at)));head.append(info,node('span',money(row.amount_vnd),'amount'));card.append(head,node('span',row.source_kind==='simulated'?'Dữ liệu mô phỏng':'Bản xuất nguồn · chưa tự xác minh','tag'));if(row.availability?.available===false)card.append(node('p',row.availability.reason.message,'issue'));const remaining=[];for(const [kind,check] of Object.entries(row.checks)){if(state.result.version==='snapshot-rule-analysis/1.0.0'&&!['needs_review','context_only'].includes(check.status))remaining.push([kind,check]);else card.append(renderCheck(check,kind));}if(remaining.length){const details=node('details');details.append(node('summary','Các kiểm tra khác ('+remaining.length+')'));for(const [kind,check] of remaining)details.append(renderCheck(check,kind));card.append(details);}const branches=node('div',undefined,'row-branches');for(const kind of branchOrder)branches.append(renderBranch(kind,row.branches[kind]));card.append(branches);return card;}));
    if(!rows.length)put('rows',node('p','Không có giao dịch thuộc bộ lọc này.'));
  }
  function renderResult(result){if(!['snapshot-analysis/1.1.0','snapshot-rule-analysis/1.0.0'].includes(result.version)||!result.branch_summary)throw Error("Hệ thống xử lý chưa hỗ trợ phân tích bốn nhánh. Người vận hành cần khởi động lại Agent2; bản dữ liệu đã lưu được giữ nguyên.");state.result=result;show('results');put('coverage',node('span',result.coverage_message+" Chưa đủ căn cứ đánh giá độ chính xác Hệ thống học từ dữ liệu."));
    const visibleRows=result.rows.filter(row=>row.availability?.available!==false);
    metadata('run-meta',[['Lần kiểm tra',result.analysis_id],['Dùng nguồn đã biết đến',date(result.as_of)],['Kỳ giao dịch trong kết quả',visibleRows.length?date(visibleRows.map(r=>r.event_at).sort((a,b)=>Date.parse(a)-Date.parse(b))[0])+' — '+date(visibleRows.map(r=>r.event_at).sort((a,b)=>Date.parse(b)-Date.parse(a))[0]):'Không có giao dịch khả dụng tại thời điểm này.']]);
    const metrics=[['Giao dịch',result.row_count],['Cần đối chiếu theo luật',result.summary.transactions_to_review],["Đối chiếu luật thiếu dữ liệu",result.summary.unavailable_checks],['Nhóm cần đối chiếu',result.summary.groups_to_review]];
    put('metrics',...metrics.map(([k,v])=>{const n=node('div',undefined,'metric');n.append(node('strong',v),node('span',k));return n;}));
    put('branch-summary',...branchOrder.map(k=>result.branch_summary[k]).map(branch=>{const n=node('div',undefined,'metric branch-metric');n.append(node('h4',branch.name),node('p','Đã chạy: '+branch.available+' · Một phần: '+branch.partial+' · Chưa khả dụng: '+branch.unavailable));return n;}));
    put('results-source-limits',...(result.source_limits.length?[node('h3','Nguồn còn thiếu tại thời điểm đã chọn'),...result.source_limits.map(limit=>{const d=node('details',undefined,'source-limit');d.append(node('summary',limit.name+' · '+limit.affected_count+' giao dịch'),node('p',limit.message),node('p',limit.action));return d;})]:[]));
    put('groups',...(result.groups||[]).map(group=>{const n=node('article',undefined,'group');n.id=group.group_id;n.append(node('h3','Kiểm tra nhóm thanh toán'),node('span',labels[group.status]||group.status,'badge '+group.status),node('p','Giao dịch: '+group.transaction_refs.map(r=>r.record_id).join(', ')),node('p','Đã trả trước: '+money(group.prior_paid_vnd)+' · Tổng phân bổ nhóm: '+money(group.group_allocated_vnd)+' · Lũy kế: '+money(group.cumulative_paid_vnd)+' · Hóa đơn: '+money(group.invoice_gross_vnd)+' · Phần vượt: '+money(group.excess_vnd)),node('p','Đối chiếu cả nhóm cùng thời điểm. Đây là một kết quả nhóm, không cộng lặp vào từng giao dịch.'));return n;}));if(result.scope_checks?.length){const detail=node('details');detail.append(node('summary','Kiểm tra theo tập và nguồn ('+result.scope_checks.length+')'));for(const check of result.scope_checks)detail.append(renderCheck(check,'scope'));$('groups').append(detail);}renderRows();
  }
  $('filter').addEventListener('change',renderRows);
  $('as-of').addEventListener('change',()=>{state.epoch++;state.controller?.abort();state.controller=null;state.busy=false;state.result=null;show('results',false);remember();buttons();});
  $('analyze').addEventListener('click',()=>run(async epoch=>{if(bundleMode){if(!state.saved)throw Error('Lưu dữ liệu trước khi phân tích.');location.href=mount+'/pipeline-workspace#'+new URLSearchParams({company:state.company,snapshot:state.saved.snapshot_id});return;}if(encryptedMode&&state.saved?.contract_version!=='agent2-rule-snapshot/1.0.0'){if(!state.saved)throw Error('Lưu dữ liệu trước khi phân tích.');localStorage.setItem('agent2.he.selection',JSON.stringify({company:state.company,snapshot:state.saved.snapshot_id}));location.href=mount+'/encrypted-analysis';return;}show('results',false);state.result=null;const value=$('as-of').value;if(!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?$/.test(value))throw Error('Chọn ngày giờ phân tích hợp lệ.');
    const result=await api(base()+'snapshots/'+state.saved.snapshot_id+'/analyze',{as_of:value+(value.length===16?':00':'')+'+07:00',view:'review'});current(epoch);renderResult(result);remember();
  }));
  // Explicit Vietnam time, independent of the computer/browser timezone.
  const now=new Date(Date.now()+7*3600*1000);$('as-of').value=now.toISOString().slice(0,19);buttons();
  async function initialize(){
    if(mount){show('connection',false);show('input-panel',false);show('portal-access');}
    try{
      const response=await fetch(mount+'/api/v1/ui/settings',{cache:'no-store'});
      if(!response.ok)throw Error("Chưa đọc được cấu hình kết nối. Bật Agent2 từ trang chung rồi tải lại trang.");
      const settings=await response.json();encryptedMode=settings.analysis_mode==='four_encrypted_branches';
      bundleMode=settings.workspace_mode==='bundle_shadow';
      if(encryptedMode){$('analyze').textContent='Tiếp tục phân tích mã hóa';$('as-of').closest('label').hidden=true;const hint=$('analysis-panel').querySelector('p.hint');if(hint)hint.textContent='Tiếp tục với đúng bản dữ liệu vừa lưu. Các nhánh sẽ tính trên bản mã và giải mã tại doanh nghiệp.';}
      if(bundleMode){$('analyze').textContent='Tiếp tục đến vụ cần rà';$('as-of').closest('label').hidden=true;const hint=$('analysis-panel').querySelector('p.hint');if(hint)hint.textContent="Chuyển đúng bản dữ liệu vừa lưu vào luồng chung. Chọn bản dữ liệu và chạy cấu hình đã được duyệt cho doanh nghiệp; phần thiếu dữ liệu được báo riêng.";}
      if(settings.auth_mode!=='portal'){if(mount)throw Error("Agent2 chưa chạy ở chế độ trang chung. Người vận hành cần khởi động Agent2 từ trang chung.");return;}
      portalMode=true;show('connection',false);$('disconnect').textContent="Về trang chung";$('portal-login').href=(settings.portal_url||'')+'/#data';
      if(mount){await syncPortal();setInterval(syncPortal,15000);window.addEventListener('storage',e=>{if(e.key==='kt-session'){if(!e.newValue)clearPortal("trang chung đã khóa. Đăng nhập lại để tiếp tục.");else syncPortal();}});window.addEventListener('focus',syncPortal);}
      else clearPortal("Mở Agent2 từ trang chung để sử dụng phiên đăng nhập chung.");
    }catch(e){if(mount)clearPortal(e.message);else notify("Chưa đọc được cấu hình kết nối. Tải lại trang sau khi hệ thống xử lý hoạt động.");}
  }
  initialize();
})();
