'use strict';
(() => {
  const packet=JSON.parse(document.getElementById('packet').textContent),$=id=>document.getElementById(id);
  const key='agent2.business-demo.'+packet.packet_id;
  const node=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=String(text);return n;};
  let state={reviews:[],drafts:{},reviewer:''},current=packet.cases[0],running=false,last=0;
  const tables={transactions:'Giao dịch',vendors:'Nhà cung cấp',employees:'Nhân viên',invoices:'Bản ghi hóa đơn',payment_allocations:'Phân bổ thanh toán',approvals:'Bản ghi phê duyệt',supporting_documents:'Bản ghi tài liệu'};
  const notify=text=>{$('notice').textContent=text;$('notice').hidden=!text;};
  const money=value=>BigInt(value).toLocaleString('vi-VN')+' đ';
  const latest=id=>state.reviews.filter(r=>r.case_id===id).sort((a,b)=>b.revision-a.revision)[0];
  function read(){const raw=localStorage.getItem(key);if(!raw)return {reviews:[],drafts:{},reviewer:''};const v=JSON.parse(raw);if(!Array.isArray(v.reviews)||!v.drafts||typeof v.drafts!=='object')throw Error('Bản lưu trình duyệt không hợp lệ. Giữ bản sao để kiểm tra; chưa ghi đè.');return v;}
  function mergeReviews(a,b){const map=new Map();for(const r of [...a,...b]){const k=r.case_id+'|'+r.revision;if(map.has(k)&&JSON.stringify(map.get(k))!==JSON.stringify(r))throw Error('Hai bản kết quả cùng phiên bản đang xung đột. Xuất bản sao để xử lý; không tự ghi đè.');map.set(k,r);}return [...map.values()];}
  function persist(){const old=read();state.reviews=mergeReviews(old.reviews,state.reviews);state.drafts={...old.drafts,[current.case_id]:state.drafts[current.case_id]};state.reviewer=$('reviewer').value;localStorage.setItem(key,JSON.stringify(state));}
  function fresh(base=0){return {base,active_ms:0,resolution:'',usefulness:'not_assessed',explanation:'',action:'',missing_materials:'',reviewed_evidence_ids:[],checks_completed:false};}
  function draft(){if(!state.drafts[current.case_id])state.drafts[current.case_id]=fresh(latest(current.case_id)?.revision||0);return state.drafts[current.case_id];}
  function active(){const d=draft();if(running){const now=performance.now();d.active_ms+=Math.max(0,now-last);last=now;}return d.active_ms;}
  function controls(){const saved=latest(current.case_id),editing=draft().base===(saved?.revision||0)&&draft().editing;const locked=!!saved&&!editing;
    $('decision').disabled=locked;$('save').disabled=locked;$('start').disabled=locked||running;$('pause').disabled=!running;
    $('revise').hidden=!locked;$('saved-info').hidden=!saved;$('saved-info').textContent=saved?'Đã lưu phiên bản '+saved.revision+'. Nếu cần sửa, tạo phiên bản mới để giữ lịch sử.':'';
    for(const c of document.querySelectorAll('#evidence input'))c.disabled=locked;
    const ms=active();$('elapsed').textContent=ms>0?(ms/1000).toFixed(1)+' giây đang rà'+(running?'':' · Tạm dừng'):'Chưa bắt đầu';}
  function pause(){active();running=false;try{persist();}catch(e){notify(e.message);}controls();}
  function capture(){const d=draft();for(const [field,id] of [['resolution','resolution'],['usefulness','usefulness'],['explanation','explanation'],['action','action'],['missing_materials','missing']])d[field]=$(id).value;d.checks_completed=$('checks').checked;d.reviewed_evidence_ids=[...document.querySelectorAll('#evidence input:checked')].map(x=>x.value);persist();}
  function overview(){const rows=packet.cases.filter(c=>c.company_id===$('company').value);$('cases').replaceChildren(...rows.map(c=>{const b=node('button',c.priority_rank+'. '+c.record_id);b.className=c.case_id===current.case_id?'selected':'';b.append(node('small',latest(c.case_id)?'Đã ghi kết quả':'Chưa rà'));b.onclick=()=>{pause();current=c;render();};return b;}));
    const count=new Set(state.reviews.map(r=>r.case_id)).size;$('overall').textContent=count+'/'+packet.cases.length+' phiếu đã ghi kết quả thử. Chưa có đánh giá hiệu quả nghiệp vụ đã xác minh.';
    const table=node('table'),head=node('tr');for(const name of ['DN','Đã rà','Khai báo hữu ích','Chưa đánh giá hữu ích','Phút thử từ trình duyệt'])head.append(node('th',name));table.append(head);
    for(const company of ['C001','C002']){const ids=packet.cases.filter(c=>c.company_id===company).map(c=>c.case_id),rows=ids.map(latest).filter(Boolean),yes=rows.filter(r=>r.usefulness==='yes').length,assessed=rows.filter(r=>r.usefulness!=='not_assessed').length,ms=state.reviews.filter(r=>ids.includes(r.case_id)).reduce((a,r)=>a+r.active_ms,0),tr=node('tr');for(const v of [company,rows.length+'/5',assessed?yes+'/'+assessed:'Chưa có',rows.filter(r=>r.usefulness==='not_assessed').length,rows.length?(ms/60000).toFixed(2):'—'])tr.append(node('td',v));table.append(tr);}$('summary').replaceChildren(table);}
  function render(){notify('');const saved=latest(current.case_id);if(saved&&!draft().editing)state.drafts[current.case_id]={...saved,base:saved.revision,editing:false};const d=draft();
    $('case-title').textContent=current.company_id+' · Giao dịch '+current.record_id+' · Ưu tiên '+current.priority_rank+'/5';
    $('transaction').textContent=money(current.amount_vnd)+' · '+new Date(current.event_at).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',hour12:false})+' (UTC+07)';
    for(const field of ['question','why'])$(field).textContent=current[field];$('limits').textContent=current.source_limits.join(' ');
    $('needed').replaceChildren(...current.documents_to_request.map(x=>node('li',x)));
    $('evidence').replaceChildren(...current.evidence.map(e=>{const box=node('div'),label=node('label');label.className='check';const input=node('input');input.type='checkbox';input.value=e.evidence_id;input.checked=d.reviewed_evidence_ids.includes(e.evidence_id);input.onchange=()=>{try{capture();}catch(error){notify(error.message);}};label.append(input,node('span',(tables[e.table]||e.table)+' '+e.record_id+' · phiên bản '+e.revision+(e.money_display.amount_vnd?' · '+money(e.money_display.amount_vnd):'')+' · Mô phỏng'));const details=node('details');details.append(node('summary','Xem bản ghi nguồn'),node('pre',JSON.stringify(e.source_record,null,2)));box.append(label,details);return box;}));
    const fields=[['Bản dữ liệu',current.snapshot_id],['Lần model',current.model_version],['Nguồn biết đến',current.knowledge_cutoff],['Gói phiếu',packet.packet_id]];
    $('source-meta').replaceChildren(...fields.flatMap(([k,v])=>[node('dt',k),node('dd',v)]));
    for(const [field,id] of [['resolution','resolution'],['usefulness','usefulness'],['explanation','explanation'],['action','action'],['missing_materials','missing']])$(id).value=d[field]||'';$('checks').checked=d.checks_completed;
    overview();controls();}
  $('company').onchange=()=>{pause();current=packet.cases.find(c=>c.company_id===$('company').value);render();};
  $('start').onclick=()=>{try{if(document.hidden)throw Error('Mở thẻ này trước khi bắt đầu.');if(!$('reviewer').value.trim())throw Error('Nhập tên người trực tiếp rà trước.');running=true;last=performance.now();persist();notify('');controls();}catch(e){running=false;notify(e.message);}};
  $('pause').onclick=pause;$('reviewer').oninput=()=>{try{persist();}catch(e){notify(e.message);}};
  for(const id of ['resolution','usefulness','explanation','action','missing','checks'])$(id).addEventListener('input',()=>{try{capture();}catch(e){notify(e.message);}});
  $('revise').onclick=()=>{const old=latest(current.case_id);state.drafts[current.case_id]={...old,base:old.revision,editing:true,active_ms:0};persist();render();};
  $('save').onclick=()=>{try{
    pause();capture();const d=draft(),remote=read();state.reviews=mergeReviews(remote.reviews,state.reviews);const old=latest(current.case_id);
    if((old?.revision||0)!==d.base)throw Error('Phiếu đã có phiên bản mới ở cửa sổ khác. Tải lại trước khi sửa; không ghi đè.');
    if(!$('reviewer').value.trim()||!d.explanation.trim()||!d.resolution)throw Error('Điền tên người rà, kết quả và phần giải thích.');
    if(!(d.active_ms>=1))throw Error('Bấm Bắt đầu rà và đối chiếu trước khi lưu.');
    if(d.usefulness==='yes'&&!d.action.trim())throw Error('Đánh giá hữu ích cần nêu rõ ai phải làm gì.');
    if(d.resolution==='inconclusive'&&(!d.missing_materials.trim()||!d.action.trim()))throw Error('Chưa đủ căn cứ: nêu tài liệu thiếu và bước bổ sung tiếp theo.');
    if(d.resolution!=='inconclusive'&&(!d.checks_completed||!d.reviewed_evidence_ids.length))throw Error('Kết luận cần dẫn bản ghi đã xem và xác nhận đã đối chiếu đủ trong bản thử.');
    const r={case_id:current.case_id,revision:(old?.revision||0)+1,reviewer_name_declared:$('reviewer').value.trim(),resolution:d.resolution,usefulness:d.usefulness,explanation:d.explanation,action:d.action,missing_materials:d.missing_materials,reviewed_evidence_ids:[...d.reviewed_evidence_ids],checks_completed:d.checks_completed,active_ms:d.active_ms,timer_basis:'unverified_browser_active_time',submitted_at:new Date().toISOString()};
    state.reviews.push(r);state.drafts[current.case_id]={...r,base:r.revision,editing:false};persist();render();notify('Đã lưu kết quả thử trong trình duyệt. Xuất JSON để lưu bản sao.');
  }catch(e){notify(e.message);}};
  $('export').onclick=()=>{try{pause();const old=read();state.reviews=mergeReviews(old.reviews,state.reviews);const value={version:'he-business-review-feedback/1.0.0',packet_id:packet.packet_id,reviews:state.reviews};const blob=new Blob([JSON.stringify(value,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=node('a');a.href=url;a.download='KET_QUA_RA_THU_'+packet.packet_id.slice(-12)+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(e){notify(e.message);}};
  document.addEventListener('visibilitychange',()=>{if(document.hidden)pause();});window.addEventListener('pagehide',pause);
  setInterval(()=>{if(running){active();try{persist();}catch(e){running=false;notify(e.message);}controls();}},1000);
  try{state=read();$('reviewer').value=state.reviewer||'';render();}catch(e){notify(e.message);for(const id of ['save','start','export'])$(id).disabled=true;}
})();
