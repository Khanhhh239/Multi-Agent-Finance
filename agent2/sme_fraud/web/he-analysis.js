'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const mount = location.pathname.startsWith('/agent2/') ? '/agent2' : '';
  let portal = !!mount, token = '', actorID = '', contextID = '', identity = '', epoch = 0, controller = null;
  let owner = '', company = '', datasets = [], available = false, busy = false, receipt = null;
  let history=[],terminal=false;
  const reviewTimers=new Set();
  const node = (tag, text) => {const n = document.createElement(tag); if(text !== undefined)n.textContent=String(text); return n;};
  const show = (id, value=true) => {$(id).hidden=!value;};
  const put = (id, ...items) => $(id).replaceChildren(...items);
  const notify = text => {put('notice', node('span', text)); show('notice', !!text);};
  const date = value => value ? new Date(value).toLocaleString('vi-VN', {timeZone:'Asia/Ho_Chi_Minh',hour12:false})+' (UTC+07)' : '—';
  const money=value=>{try{return BigInt(value).toLocaleString('vi-VN')+' đ';}catch{return String(value);}};
  function sourceView(ev){
    const record=ev.record,box=node('div'),tableNames={transactions:'Giao dịch',companies:'Doanh nghiệp',vendors:'Nhà cung cấp',employees:'Nhân viên',invoices:'Hóa đơn',payment_allocations:'Phân bổ thanh toán',approvals:'Phê duyệt',supporting_documents:'Tài liệu đối chiếu',vendor_bank_history:'Lịch sử tài khoản',payment_history_coverage:'Phạm vi lịch sử'};
    const facts=[['Loại bản ghi',tableNames[ev.table]||ev.table],['Mã',record.record_id],['Có hiệu lực',date(record.effective_at)],['Nguồn được biết lúc',date(record.observed_at)]];
    for(const [field,title] of [['amount_vnd','Số tiền'],['total_vnd','Tổng tiền'],['gross_amount_vnd','Tổng nghĩa vụ']])if(record[field]!==undefined&&record[field]!==null)facts.push([title,money(record[field])]);
    if(record.description)facts.push(['Nội dung',record.description]);
    if(record.number)facts.push(['Số hóa đơn',record.number]);
    if(record.transaction_ref)facts.push(['Giao dịch được phân bổ',record.transaction_ref.record_id+' · phiên bản '+record.transaction_ref.revision]);
    if(record.invoice_ref)facts.push(['Hóa đơn liên quan',record.invoice_ref.record_id+' · phiên bản '+record.invoice_ref.revision]);
    if(record.adjusts_ref)facts.push(['Điều chỉnh bản ghi',record.adjusts_ref.record_id+' · phiên bản '+record.adjusts_ref.revision]);
    if(ev.table==='payment_history_coverage'){
      facts.push(['Lịch sử từ',date(record.covered_from)],['Lịch sử đến',date(record.covered_through)],
        ['Hóa đơn trong phạm vi',record.invoice_refs.map(r=>r.record_id+' · phiên bản '+r.revision).join(', ')],
        ['Phạm vi do nguồn khai báo',({complete:'Đầy đủ trong phạm vi khai báo',partial:'Chưa đầy đủ',unknown:'Chưa xác định'})[record.coverage_status]||record.coverage_status]);
    }
    if(record.source)facts.push(['Nguồn',record.source.system+' · '+record.source.record_id]);
    const dl=node('dl');for(const [title,value] of facts)dl.append(node('dt',title),node('dd',value));box.append(dl);
    if(record.accounting_lines?.length){const table=node('table'),head=node('tr');for(const label of ['Tài khoản','Nợ','Có'])head.append(node('th',label));table.append(head);for(const line of record.accounting_lines){const row=node('tr');row.append(node('td',line.account),node('td',money(line.debit_vnd)),node('td',money(line.credit_vnd)));table.append(row);}box.append(table);}
    const details=node('details');details.append(node('summary','Chi tiết bản ghi nguồn'),node('pre',JSON.stringify(record,null,2)));box.append(details);return box;
  }
  const metadata = (id, fields) => put(id, ...fields.flatMap(([k,v])=>[node('dt',k),node('dd',v)]));
  const base = () => '/api/v1/companies/'+encodeURIComponent(company)+'/he/';
  const selected = () => datasets.find(d=>d.snapshot_id===$('dataset').value);
  function buttons(){ $('run').disabled=busy||!token||!selected()||(!available&&!receipt);$('new-run').disabled=busy||!token||!selected()||!available;show('new-run',terminal);$('dataset').disabled=!token||!datasets.length; $('company').disabled=!token; }
  async function refreshReadiness(e){const current=await api(base()+'datasets');if(e!==epoch)return;if(current.owner_id!==owner){lock('Quyền đã thay đổi. Mở lại từ Portal.');return;}available=current.available;show('reconnect',current.worker_ready===false);put('availability',node('span',current.message||''));show('availability',!!current.message);buttons();}
  function clearPrivateView(){terminal=false;show('new-run',false);for(const timer of reviewTimers)clearInterval(timer);reviewTimers.clear();show('results',false);show('progress-panel',false);for(const id of ['job-meta','result-meta','rows','result-summary','review-cases'])put(id);}
  function clear(){epoch++;controller?.abort();controller=new AbortController();busy=false;receipt=null;owner='';datasets=[];history=[];available=false;clearPrivateView();notify('');put('dataset',node('option','Đang đọc dữ liệu…'));put('previous-runs',node('option','Đang đọc lịch sử…'));put('dataset-info');show('analysis-settings',false);show('availability',false);show('reconnect',false);buttons();}
  function lock(message){clear();token='';identity='';show('selection',false);show('connection',false);put('portal-message',node('span',message));show('portal-access');buttons();}
  async function api(path, body, extra={}){
    const headers=portal?{'X-Session':token,'X-Platform':'1'}:{Authorization:'Bearer '+token};
    if(body!==undefined)headers['Content-Type']='application/json';
    let response;
    try{response=await fetch(mount+path,{method:body===undefined?'GET':'POST',headers:{...headers,...extra},body:body===undefined?undefined:JSON.stringify(body),cache:'no-store',signal:controller?.signal});}
    catch(e){if(e.name==='AbortError')throw e;throw Error('Mất kết nối. Bấm tiếp tục để dùng lại yêu cầu đã lưu.');}
    const value=await response.json();
    if(!response.ok){const error=Error(value.errors?.map(x=>x.message+' '+(x.action||'')).join('\n')||'Chưa thực hiện được yêu cầu.');error.status=response.status;throw error;}
    return value;
  }
  function storageKey(){return 'agent2.he.'+owner+'.'+company+'.'+(receipt?.snapshot||$('dataset').value);}
  function restore(){
    receipt=null;
    try{const r=JSON.parse(localStorage.getItem(storageKey()));if(r&&r.owner===owner&&r.company===company&&r.snapshot===$('dataset').value&&/^[a-f0-9-]{36}$/.test(r.key)&&(!r.job||/^herun_[a-f0-9]{32}$/.test(r.job)))receipt=r;}catch{/* unreadable receipt */}
  }
  function persist(){try{localStorage.setItem(storageKey(),JSON.stringify(receipt));}catch{throw Error('Trình duyệt chưa cho phép lưu phiếu theo dõi. Bật lưu trữ cho trang này trước khi chạy để tránh tạo yêu cầu trùng khi tải lại.');}}
  function remember(persistSelection=true){
    try{if(company&&actorID){sessionStorage.setItem('agent2.company.selection',JSON.stringify({version:1,actor:actorID,context:contextID,company,page:'encrypted-analysis'}));if(persistSelection)localStorage.setItem('agent2.he.selection',JSON.stringify({company,snapshot:$('dataset').value}));}}catch{/* submit requires durable receipt separately */}
    for(const a of document.querySelectorAll('header a[href],a#analysis-settings,a[href$="/data-import"]')){const page=new URL(a.href).pathname.split('/').pop();if(['workspace','data-import','analysis-settings'].includes(page))a.href=mount+'/'+page+(company?'#company='+encodeURIComponent(company):'');}
  }
  function datasetChanged(){
    epoch++;controller?.abort();controller=new AbortController();busy=false;clearPrivateView();notify('');
    const d=selected();put('dataset-info',...(d?[node('span',(d.simulated_records?'Có dữ liệu mô phỏng · ':'')+d.record_count+' bản ghi · '+date(d.period_start)+' — '+date(d.period_end)+' · Đã lưu '+date(d.created_at))]:[]));
    restore();remember();$('run').textContent=receipt?'Tiếp tục phân tích':'Chạy phân tích';buttons();if(receipt)analyze();else if(!available){const e=epoch;refreshReadiness(e).catch(error=>{if(e===epoch)failure(error);});}
  }
  async function loadDatasets(){
    clear();const e=epoch;
    try{
      const data=await api(base()+'datasets');if(e!==epoch)return;
      owner=data.owner_id;datasets=data.datasets;available=data.available;
      show('analysis-settings',data.can_manage===true);
      put('analysis-mode',node('span',data.analysis_mode==='four_encrypted_branches'?'Đối chiếu riêng bốn nhánh trên bản mã. Phần thiếu nguồn sẽ được giải thích trong từng giao dịch; chưa tự tính điểm tổng hoặc đưa vào hàng đợi.':'Đang thử nghiệm phân tích bất thường trên bản mã. Kết quả chưa ghép vào hàng đợi nghiệp vụ.'));
      show('reconnect',data.worker_ready===false);
      try{const saved=await api(base()+'runs');if(e!==epoch)return;history=saved.runs;put('previous-runs',node('option','Chọn lần phân tích đã lưu'),...history.map(r=>{const option=node('option',new Date(r.created_at*1000).toLocaleString('vi-VN')+' · '+r.phase+' · '+r.job_id.slice(-8));option.value=r.job_id;return option;}));}catch(error){if(error.name==='AbortError')throw error;history=[];put('previous-runs',node('option','Chưa tải được lịch sử'));}
      put('dataset',...(datasets.length?datasets.map(d=>{const option=node('option',d.record_count+' bản ghi · '+date(d.created_at)+' · '+d.snapshot_id.slice(-8));option.value=d.snapshot_id;return option;}):[node('option','Chưa có dữ liệu đã lưu')]));
      let previous;try{previous=JSON.parse(localStorage.getItem('agent2.he.selection'));}catch{/* empty */}
      if(previous?.company===company&&datasets.some(d=>d.snapshot_id===previous.snapshot))$('dataset').value=previous.snapshot;
      const messages=[data.message,!datasets.length?'Nhập và lưu dữ liệu trước khi phân tích.':'',data.limited?'Đang hiển thị 100 bản dữ liệu được lưu gần nhất.':''].filter(Boolean);
      put('availability',node('span',messages.join(' ')));show('availability',!!messages.length);datasetChanged();
    }catch(error){if(e===epoch)failure(error);}
  }
  function failure(error){if(error.name==='AbortError')return;if(portal&&(error.status===401||error.status===403)){lock('Phiên đăng nhập hoặc quyền đã thay đổi. Mở lại từ Portal để tiếp tục.');return;}show('results',false);notify(error.message);$('run').textContent=receipt?'Tiếp tục phân tích':'Chạy phân tích';buttons();}
  function workLink(run){const link=node('a','Mở hồ sơ rà và báo cáo');link.href=mount+'/workspace#'+new URLSearchParams({company,run});link.className='text-link';return link;}
  function render(result){
    loadReviews(result);
    show('results');metadata('result-meta',[['Doanh nghiệp',company],['Bản dữ liệu',result.snapshot_id],['Dùng nguồn đã biết đến',date(result.as_of)],['Lần chạy',result.run_id]]);
    const four=result.version==='he-four-branch-result/1.0.0',ready=result.rows.filter(r=>four?Object.values(r.branches).some(b=>b.available):r.available).length;put('result-summary',node('span',four?result.row_count+' giao dịch · '+ready+' có kết quả từ ít nhất một nhánh. Xem phần chưa đủ nguồn trong từng giao dịch.':result.row_count+' giao dịch · '+ready+' có điểm · '+(result.row_count-ready)+' chưa khả dụng.'));
    $('result-summary').append(document.createElement('br'),workLink(result.run_id));
    const explanations={features_missing:'Chưa đủ dữ liệu để tạo biến phân tích. Bổ sung nguồn rồi nhập thành bản dữ liệu mới.',features_all_missing:'Chưa đủ dữ liệu để tạo biến phân tích.',artifact_missing:'Chưa có phiên bản model đã cấu hình.',he_adapter_unsupported:'Phiên bản model chưa hỗ trợ phân tích bảo mật.',artifact_incompatible:'Model không tương thích với dữ liệu hiện tại.',artifact_from_future:'Model dùng lịch sử sau thời điểm giao dịch này. Chọn dữ liệu thuộc kỳ đánh giá phù hợp.',artifact_training_overlap:'Giao dịch này đã dùng để chuẩn bị model. Cần dữ liệu đánh giá riêng.',before_evaluation_period:'Giao dịch nằm trước kỳ đánh giá của model. Chọn dữ liệu thuộc kỳ đánh giá phù hợp.',artifact_not_yet_created:'Model chưa tồn tại tại thời điểm giao dịch này. Người quản lý cần kiểm tra kỳ đánh giá.',input_out_of_domain:'Giá trị nằm ngoài miền hỗ trợ của bản thử. Người quản lý cần kiểm tra dữ liệu và model.',he_batch_limit:'Bản thử hỗ trợ tối đa 8 giao dịch hợp lệ mỗi lượt. Cần chuẩn bị gói dữ liệu đúng phạm vi và giữ đủ lịch sử liên quan.'};
      put('rows',...result.rows.map(row=>{const article=node('article');article.className='transaction';const count=row.branches?Object.values(row.branches).filter(b=>b.available).length:0;article.append(node('h3','Giao dịch '+row.record_id),node('p',four?'Có kết quả từ '+count+'/4 nhánh. Đối chiếu căn cứ và phần chưa đủ nguồn trước khi ghi kết luận.':row.available?'Đã phân tích. Đối chiếu chứng từ khi chọn giao dịch này để rà soát.':(explanations[row.reason]||'Chưa đủ điều kiện phân tích giao dịch này. Người quản lý cần kiểm tra nguồn và phiên bản model.')));if(row.available&&!four){const detail=node('details');detail.append(node('summary','Xem điểm bất thường'),node('p',String(row.score)+' · Điểm không phải xác suất sai phạm.'));article.append(detail);}if(row.branches)renderBranches(article,row.branches);return article;}));
    $('run').textContent='Xem kết quả đã có';
  }
  function renderBranches(article,branches){
    const names={rules:'Đối chiếu thanh toán',statistics:'So sánh với lịch sử doanh nghiệp',graph:'Quan hệ giữa các đối tượng',ml:'Phân tích bất thường'};
    const reasons={rule_sources_unavailable:'Thiếu hóa đơn, liên kết thanh toán hoặc phạm vi lịch sử đầy đủ.',artifact_not_pinned:'Chưa chọn phiên bản thống kê đã fit cho doanh nghiệp.',artifact_missing:'Chưa có phiên bản đã fit phù hợp.',artifact_incompatible:'Phiên bản model không tương thích với dữ liệu.',artifact_from_future:'Model dùng lịch sử sau kỳ giao dịch.',artifact_training_overlap:'Giao dịch từng thuộc tập chuẩn bị model.',before_evaluation_period:'Giao dịch nằm trước kỳ đánh giá của model.',he_graph_node_limit:'Số đối tượng vượt phạm vi đồ thị mã hóa đang hỗ trợ; không tự cắt nguồn.',he_graph_sources_missing:'Chưa có đủ thuộc tính liên kết để phân tích.',he_p1_source_limit:'Lịch sử liên quan vượt phạm vi phép tính mã hóa đang hỗ trợ; không tự cắt lịch sử.',he4_key_not_provisioned:'Chưa chuẩn bị khóa phân tích cho doanh nghiệp.',he_statistics_out_of_domain:'Giá trị nằm ngoài miền thống kê mã hóa đã kiểm chứng.',features_missing:'Thiếu đầu vào cần thiết cho model.'};
    for(const [kind,branch] of Object.entries(branches)){
      const block=node('div');block.className='check-result';block.append(node('h4',names[kind]||kind));
      if(!branch.available)block.append(node('p',branch.status==='not_applicable'?'Loại giao dịch này không thuộc phạm vi đối chiếu.':(reasons[branch.reason]||'Chưa đủ nguồn hoặc phiên bản tương thích. Người quản lý cần kiểm tra trước khi sử dụng kết quả.')));
      else if(kind==='rules'){block.append(node('p',branch.matched?'Cần đối chiếu khoản trả với nghĩa vụ hóa đơn và lịch sử thanh toán.':'Đối chiếu P1 chưa thấy dấu hiệu vượt nghĩa vụ theo nguồn được cung cấp.'));block.append(node('small','Mới có đối chiếu P1, chưa phải toàn bộ quy tắc nghiệp vụ.'));if(branch.simultaneous_checks?.some(x=>x.matched))block.append(node('p','Có nhóm thanh toán đồng thời cần kiểm tra chung.'));}
      else if(kind==='graph')block.append(node('p','Đã đối chiếu các thuộc tính và quan hệ. Liên kết địa chỉ/mã số thuế chỉ cung cấp bối cảnh.'));
      else block.append(node('p','Đã chấm bằng phiên bản được ghim cho doanh nghiệp. Điểm không phải xác suất sai phạm.'));
      const detail=node('details');detail.append(node('summary','Xem căn cứ phân tích'),node('pre',JSON.stringify(branch,null,2)));block.append(detail);article.append(block);
    }
  }
  async function loadReviews(result){
    const e=epoch,run=receipt?.job,path=base()+'jobs/'+run+'/reviews';
    for(const timer of reviewTimers)clearInterval(timer);reviewTimers.clear();put('review-cases');
    try{
      const packet=await api(path);if(e!==epoch||receipt?.job!==run)return;
      const heading=node('h2','Phiếu rà và kết quả đã lưu');
      const report=node('button','Tải báo cáo rà');report.className='quiet';
      report.addEventListener('click',async()=>{try{const latest=await api(path);if(e!==epoch)return;const blob=new Blob([JSON.stringify(latest,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=node('a');a.href=url;a.download='agent2-review-'+run+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(error){failure(error);}});
      const summary=node('p'),filterLabel=node('label','Hiển thị phiếu'),filter=node('select'),reviewRows=[];filter.setAttribute('aria-label','Hiển thị phiếu');
      for(const [value,text] of [['all','Tất cả'],['pending','Chưa ghi kết quả'],['reviewed','Đã ghi kết quả'],['confirmed_risk','Có vấn đề cần xử lý'],['legitimate','Không phát hiện vấn đề'],['inconclusive','Chưa đủ căn cứ']]){const option=node('option',text);option.value=value;filter.append(option);}
      filterLabel.append(filter);
      function refreshReviews(){const reviewed=reviewRows.filter(r=>r.state.revision>0).length;summary.textContent=reviewed+'/'+packet.summary.total_cases+' phiếu đã ghi kết quả. Phiếu chưa rà không được tính là cảnh báo sai.';for(const row of reviewRows){const selected=filter.value;row.article.hidden=!(selected==='all'||selected==='pending'&&row.state.revision===0||selected==='reviewed'&&row.state.revision>0||row.state.revision>0&&row.state.feedback?.outcome===selected);}}
      filter.addEventListener('change',refreshReviews);
      put('review-cases',heading,summary,filterLabel,report);
      for(const item of packet.cases){
        const article=node('article');article.className='transaction';let lease=null,timer=null,pending=null,state=item.review;
        const title=node('h3','Giao dịch '+item.record_id+' · '+item.amount_vnd+' '+item.currency);
        const message=node('p',state.revision?'Đã lưu phiên bản '+state.revision:'Chưa ghi kết quả');
        const question=node('p',item.question),why=node('p',item.why),next=node('p',item.next_step);
        const evidence=node('details');evidence.append(node('summary','Chứng từ và nguồn đối chiếu'));const refs=[];
        for(const ev of item.evidence){const block=node('div'),check=document.createElement('input');check.type='checkbox';check.value=ev.evidence_id;refs.push(check);const label=node('label');label.className='check';label.append(check,node('span',ev.record.record_id+' · '+(ev.simulated?'Dữ liệu mô phỏng':ev.original_verified?'Chứng từ gốc có trạng thái xác minh tại nguồn':'Bản ghi nguồn, chưa xác minh chứng từ gốc')));block.append(label,sourceView(ev));evidence.append(block);}
        function select(label,options){const box=node('label',label),input=node('select');for(const [value,text] of options){const o=node('option',text);o.value=value;input.append(o);}box.append(input);article.append(box);return input;}
        article.append(title,question,why,next,evidence);
        const outcome=select('Kết quả nghiệp vụ',[['inconclusive','Chưa đủ căn cứ'],['confirmed_risk','Có vấn đề cần xử lý'],['legitimate','Không phát hiện vấn đề']]);
        const usefulness=select('Cảnh báo có giúp ích cho việc rà không?',[['not_assessed','Chưa đánh giá'],['yes','Có'],['no','Không']]);
        function text(label){const box=node('label',label),input=document.createElement('textarea');input.maxLength=4000;input.rows=3;box.append(input);article.append(box);return input;}
        const explanation=text('Đã kiểm tra gì và căn cứ nào?'),action=text('Cần ai làm gì tiếp theo?'),missing=text('Tài liệu còn thiếu');
        const completed=document.createElement('input');completed.type='checkbox';const ack=node('label');ack.className='check';ack.append(completed,node('span','Đã đối chiếu đủ tài liệu cho kết luận đang ghi'));article.append(ack);
        const old=state.feedback;if(old){outcome.value=old.outcome;usefulness.value=old.usefulness;explanation.value=old.explanation;action.value=old.action;missing.value=old.missing_materials;completed.checked=old.checks_completed;for(const check of refs)check.checked=old.evidence_ids.includes(check.value);}
        const start=node('button','Bắt đầu rà'),save=node('button','Lưu kết quả rà');save.disabled=true;const elapsed=node('span','Đã lưu '+Math.round(state.active_seconds)+' giây');const actions=node('div');actions.className='actions';actions.append(start,save,elapsed);article.append(actions,message);
        const history=node('details');history.append(node('summary','Lịch sử sửa kết quả'),node('pre',JSON.stringify(state.history,null,2)));article.append(history);
        const casePath=path+'/'+item.case_id;
        const attachments=node('div');
        function showAttachment(meta){const line=node('label');line.className='check';const check=document.createElement('input');check.type='checkbox';check.value=meta.id;check.checked=state.feedback?.evidence_ids.includes(meta.id)||false;refs.push(check);check.addEventListener('input',()=>{pending=null;});const download=node('button',meta.name+' · bổ sung, chưa xác minh');download.className='quiet';download.addEventListener('click',async()=>{try{const file=await api(casePath+'/attachments/'+meta.id);if(e!==epoch)return;const bytes=Uint8Array.from(atob(file.content),x=>x.charCodeAt(0)),url=URL.createObjectURL(new Blob([bytes],{type:'application/octet-stream'})),a=node('a');a.href=url;a.download=file.name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(error){message.textContent=error.message;}});line.append(check,download);attachments.append(line);}
        for(const meta of state.attachments)showAttachment(meta);
        const upload=document.createElement('input');upload.type='file';upload.accept='.pdf,.png,.jpg,.jpeg';const uploadLabel=node('label','Bổ sung tài liệu (PDF/ảnh, tối đa 2 MB)');uploadLabel.append(upload);attachments.append(uploadLabel);article.insertBefore(attachments,actions);
        upload.addEventListener('change',async()=>{const file=upload.files[0];if(!file)return;if(file.size>2*1024*1024){message.textContent='Tài liệu vượt 2 MB.';return;}upload.disabled=true;try{const content=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=reject;reader.readAsDataURL(file);});const saved=await api(casePath+'/attachments',{name:file.name,content});if(e!==epoch)return;if(!refs.some(x=>x.value===saved.attachment_id))showAttachment({id:saved.attachment_id,name:file.name});message.textContent='Đã lưu tài liệu bổ sung, chưa xác minh chứng từ gốc.';}catch(error){if(e===epoch)message.textContent=error.message;}finally{upload.disabled=false;upload.value='';}});
        start.addEventListener('click',async()=>{start.disabled=true;try{const value=await api(casePath+'/start',{});if(e!==epoch)return;lease=value.lease;save.disabled=false;message.textContent='Đang rà. Khi mất kết nối, khoảng gián đoạn không được tính.';timer=setInterval(async()=>{if(document.hidden||!lease)return;try{const beat=await api(casePath+'/heartbeat',{lease});if(e===epoch)elapsed.textContent=Math.round(state.active_seconds+beat.active_seconds)+' giây';}catch(error){if(e===epoch)message.textContent=error.message;}},5000);reviewTimers.add(timer);}catch(error){if(e===epoch){message.textContent=error.message;start.disabled=false;}}});
        for(const input of [outcome,usefulness,explanation,action,missing,completed,...refs])input.addEventListener('input',()=>{pending=null;});
        const reviewRow={article,state};reviewRows.push(reviewRow);
        save.addEventListener('click',async()=>{save.disabled=true;try{if(!pending)pending={lease,expected_revision:state.revision,request_id:crypto.randomUUID(),feedback:{outcome:outcome.value,usefulness:usefulness.value,explanation:explanation.value,action:action.value,missing_materials:missing.value,evidence_ids:refs.filter(x=>x.checked).map(x=>x.value),checks_completed:completed.checked}};state=await api(casePath+'/save',pending);if(e!==epoch)return;reviewRow.state=state;refreshReviews();pending=null;lease=null;clearInterval(timer);reviewTimers.delete(timer);start.disabled=false;elapsed.textContent='Đã lưu '+Math.round(state.active_seconds)+' giây';message.textContent='Đã lưu phiên bản '+state.revision+' tại doanh nghiệp.';history.replaceChildren(node('summary','Lịch sử sửa kết quả'),node('pre',JSON.stringify(state.history,null,2)));}catch(error){if(e===epoch){message.textContent=error.message;save.disabled=false;}}});
        $('review-cases').append(article);
      }
      refreshReviews();
    }catch(error){if(e===epoch)put('review-cases',node('p','Chưa tải được phiếu rà. '+error.message));}
  }
  async function analyze(){
    if(busy||!selected()||(!available&&!receipt))return;
    busy=true;const e=epoch;$('run').textContent='Đang phân tích';buttons();notify('');show('results',false);show('progress-panel');put('progress-message',node('span','Đang gửi yêu cầu'));put('progress-help',node('span','Có thể tải lại trang. Yêu cầu đã lưu sẽ được tiếp tục.'));
    try{
      if(!receipt)receipt={owner,company,snapshot:$('dataset').value,key:crypto.randomUUID(),job:null};
      persist();
      let state,resumeIssued=false;
      if(receipt.job)state=await api(base()+'jobs/'+receipt.job);
      else{state=await api(base()+'jobs',{snapshot_id:receipt.snapshot},{'Idempotency-Key':receipt.key});if(e!==epoch)return;receipt.job=state.job_id;persist();}
      const deadline=Date.now()+30*60*1000;
      while(e===epoch){
        terminal=['completed','failed','expired'].includes(state.phase);$('new-run').textContent=state.phase==='completed'?'Tạo lượt phân tích mới':'Chạy lại bằng lượt mới';show('new-run',terminal);
        put('progress-message',node('span',state.message));metadata('job-meta',[['Mã yêu cầu',receipt.job],['Doanh nghiệp',company],['Bản dữ liệu',receipt.snapshot]]);
        if(state.phase==='retryable'){
          $('run').textContent='Tiếp tục phân tích';
          put('progress-help',node('span','Bộ xử lý mất kết nối. Yêu cầu đã lưu; kết nối lại để tiếp tục.'));
          show('reconnect');
        }
        if(state.phase==='completed'){
          const result=await api(base()+'jobs/'+receipt.job+'/result');if(e!==epoch)return;render(result);
          // A recovered receipt can complete after catalog preflight saw an
          // offline worker. Refresh readiness before enabling another dataset.
          try{await refreshReadiness(e);}catch(error){if(error.name!=='AbortError'&&e===epoch)notify('Đã có kết quả. Chưa kiểm tra lại được kết nối cho lần phân tích mới.');}
          return;
        }
        if(['failed','expired'].includes(state.phase)){put('progress-help',node('span','Lượt gặp lỗi được giữ trong lịch sử. Sau khi khắc phục nguyên nhân, có thể chọn Chạy lại bằng lượt mới.'));$('run').textContent='Xem trạng thái';return;}
        if(Date.now()>deadline)throw Error('Phân tích vẫn đang được theo dõi. Bấm tiếp tục sau để lấy kết quả của cùng yêu cầu.');
        if(state.phase==='waiting_authorization'&&!resumeIssued){resumeIssued=true;state=await api(base()+'jobs/'+receipt.job+'/resume',{});}
        else{await new Promise(resolve=>setTimeout(resolve,700));if(e!==epoch)return;state=await api(base()+'jobs/'+receipt.job);}
        if(state.phase!=='waiting_authorization')resumeIssued=false;
      }
    }catch(error){if(e===epoch)failure(error);}finally{if(e===epoch){busy=false;buttons();}}
  }
  $('new-run').addEventListener('click',()=>{if(busy||!terminal||!selected()||!available)return;const previous=receipt;receipt={owner,company,snapshot:$('dataset').value,key:crypto.randomUUID(),job:null};try{persist();clearPrivateView();buttons();analyze();}catch(error){receipt=previous;failure(error);}});
  async function connect(){
    const context=await api('/api/v1/ui/context');const next=context.actor_id+'|'+(context.context_id||'')+'|'+JSON.stringify(context.companies);
    if(next===identity)return;
    clear();identity=next;actorID=context.actor_id;contextID=context.context_id||'';show('portal-access',false);show('connection',false);show('selection');
    put('company',...context.companies.map(c=>{const option=node('option',c);option.value=c;return option;}));
    let shared;try{shared=JSON.parse(sessionStorage.getItem('agent2.company.selection'));}catch{/* empty */}
    const desired=new URLSearchParams(location.hash.slice(1)).get('company');
    const remembered=shared?.version===1&&shared.actor===actorID&&shared.context===contextID&&context.companies.includes(shared.company)?shared.company:null;
    company=context.companies.includes(desired)?desired:remembered||context.companies[0]||'';$('company').value=company;
    window.history.replaceState(null,'',location.pathname+location.search+(company?'#company='+encodeURIComponent(company):''));remember(false);
    if(company)await loadDatasets();else{notify('Bạn chưa có doanh nghiệp được cấp quyền.');buttons();}
  }
  $('company').addEventListener('change',()=>{company=$('company').value;window.history.replaceState(null,'',location.pathname+'#company='+encodeURIComponent(company));remember(false);loadDatasets();});$('dataset').addEventListener('change',datasetChanged);$('run').addEventListener('click',analyze);
  $('previous-runs').addEventListener('change',()=>{const saved=history.find(r=>r.job_id===$('previous-runs').value);if(!saved)return;epoch++;controller?.abort();controller=new AbortController();busy=false;clearPrivateView();if(!datasets.some(d=>d.snapshot_id===saved.snapshot_id)){datasets.push({snapshot_id:saved.snapshot_id,record_count:saved.row_count||0,created_at:new Date(saved.created_at*1000).toISOString(),period_start:saved.as_of,period_end:saved.as_of});const option=node('option','Bản dữ liệu của lần chạy đã lưu');option.value=saved.snapshot_id;$('dataset').append(option);}$('dataset').value=saved.snapshot_id;receipt={owner,company,snapshot:saved.snapshot_id,key:crypto.randomUUID(),job:saved.job_id};remember();persist();analyze();});
  $('reconnect').addEventListener('click',async()=>{
    epoch++;controller?.abort();controller=new AbortController();busy=true;buttons();const e=epoch;
    $('reconnect').disabled=true;notify('');
    try{
      if(portal&&mount){
        const response=await fetch('/api/agents/agent2/recover',{method:'POST',headers:{'X-Session':token,'X-Platform':'1','Content-Type':'application/json'},body:'{}',signal:controller.signal});
        const value=await response.json();if(!response.ok){const error=Error(value.error||'Chưa kết nối lại được bộ xử lý.');error.status=response.status;throw error;}
      }
      const data=await api(base()+'datasets');if(e!==epoch)return;
      if(data.owner_id!==owner)throw Error('Quyền đã thay đổi. Tải lại trang để tiếp tục.');
      available=data.available;show('reconnect',data.worker_ready===false);
      put('availability',node('span',data.message||''));show('availability',!!data.message);
      if(!data.worker_ready)throw Error(data.message||'Bộ xử lý chưa kết nối. Yêu cầu đã lưu vẫn được giữ.');
      busy=false;buttons();
      if(receipt)await analyze();else notify('Đã kết nối. Bấm Chạy phân tích để bắt đầu.');
    }catch(error){if(e===epoch)failure(error);}finally{if(e===epoch){busy=false;buttons();}$('reconnect').disabled=false;}
  });
  $('connect').addEventListener('click',async()=>{clear();token=$('credential').value.trim();$('credential').value='';try{await connect();}catch(error){token='';failure(error);show('connection');}});
  let syncing=false;
  async function sync(){if(syncing)return;syncing=true;try{const fresh=sessionStorage.getItem('kt-session')||'';if(!fresh){lock('Portal đang khóa. Đăng nhập lại để tiếp tục.');return;}if(fresh!==token){clear();identity='';token=fresh;}await connect();}catch(error){lock(error.message);}finally{syncing=false;}}
  async function initialize(){try{const response=await fetch(mount+'/api/v1/ui/settings',{cache:'no-store'});if(!response.ok)throw Error('Chưa đọc được cấu hình kết nối.');const settings=await response.json();portal=settings.auth_mode==='portal';if(mount&&!portal)throw Error('Agent2 chưa chạy ở chế độ Portal.');if(portal){$('portal-login').href=(settings.portal_url||'')+'/#data';if(!mount){lock('Mở màn hình từ Portal để dùng phiên đăng nhập hiện tại.');return;}await sync();setInterval(sync,10000);window.addEventListener('focus',sync);window.addEventListener('storage',e=>{if(e.key==='kt-session')sync();});}else show('connection');}catch(error){lock(error.message);}}
  initialize();
})();
