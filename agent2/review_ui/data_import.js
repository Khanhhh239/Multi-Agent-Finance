"use strict";
(function(global){
  const escape=value=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  function errorsTable(data){
    if(!data.error_count)return "";
    return `<h3>${data.error_count} lỗi cần sửa · chưa lưu dữ liệu</h3><p>Hiển thị ${data.errors.length} lỗi đầu tiên. Sửa tệp nguồn rồi kiểm tra lại.</p><div class="table-wrap"><table><thead><tr><th>Dòng</th><th>Cột</th><th>Lý do</th><th>Cách sửa</th></tr></thead><tbody>${data.errors.map(e=>`<tr><td>${escape(e.row??"—")}</td><td>${escape(e.column)}</td><td>${escape(e.message)}</td><td>${escape(e.fix)}</td></tr>`).join("")}</tbody></table></div>`;
  }
  function rowsTable(rows){
    const fields=['transaction_id','company_id','posted_at','created_at','approved_at','amount_vnd','creator_id','vendor_id'];
    return `<table><thead><tr>${fields.map(f=>`<th>${f}</th>`).join("")}</tr></thead><tbody>${rows.map(r=>`<tr>${fields.map(f=>`<td>${escape(r[f])}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  }
  global.DataImportUI={escape,errorsTable,rowsTable};
  if(!global.document?.getElementById('import-company'))return;
  const $=id=>document.getElementById(id);
  let meta,overview,current,preview,busy=false,generation=0,loading=true,loadError='';
  const context=()=>({scenario:$('import-scenario').value,company_id:$('import-company').value});
  function notice(message,error=false){const node=$('import-notice');node.textContent=message;node.className=error?'error':'note';node.hidden=false;if(error)node.focus();}
  async function api(path,body){
    let response;
    try{response=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':meta.csrf_token},body:JSON.stringify(body)});}
    catch{throw new Error('Mất kết nối. Tải lại doanh nghiệp để kiểm tra dữ liệu trước khi thử lại; không tự gửi lại thao tác lưu.');}
    let value;try{value=await response.json();}catch{throw new Error('Chưa đọc được dữ liệu từ máy chủ. Bấm thử tải lại sau khi kiểm tra kết nối.');}
    if(!response.ok){
      if(response.status===403&&value.error==='Phiên làm việc đã thay đổi. Tải lại trang để tiếp tục.')meta=await api('/api/meta');
      if(response.status===404&&path.startsWith('/api/data-import/'))throw new Error('Phiên máy chủ này chưa hỗ trợ nhập CSV/Excel. Khởi động phiên bản máy chủ mới rồi thử tải lại.');
      throw new Error(value.error||'Chưa thực hiện được thao tác.');
    }
    return value;
  }
  function controls(){
    const manage=!!overview?.can_manage&&!!current;
    for(const id of ['import-scenario','import-company'])$(id).disabled=busy||!overview;
    $('import-reload').disabled=busy;
    for(const id of ['import-file','import-date-order','import-encoding','import-delimiter'])$(id).disabled=busy||!manage;
    $('import-check').disabled=busy||!manage||!$('import-file').files.length;
    $('import-ack').disabled=busy;
    $('import-save').disabled=busy||!manage||!preview?.valid||!preview?.token||!$('import-ack').checked;
    const status=$('import-file-status');
    status.textContent=loadError?loadError+' Bấm “Thử tải lại dữ liệu nhập” để kết nối lại.':
      loading?'Đang tải doanh nghiệp và kiểm tra quyền nhập dữ liệu…':
      !overview?.companies.length?'Chưa có doanh nghiệp trong phạm vi tài khoản. Cần đăng nhập bằng tài khoản được cấp quyền trên doanh nghiệp để nhập dữ liệu.':
      !overview.can_manage?'Phiên hiện tại chỉ có quyền xem nên nút chọn tệp bị khóa. Cần dùng tài khoản kế toán trưởng hoặc giám đốc có quyền trên doanh nghiệp để nhập CSV/Excel.':
      !current?'Chọn doanh nghiệp và tải danh mục trước khi chọn tệp.':
      busy?'Đang xử lý dữ liệu; chờ hoàn tất để chọn tệp khác.':
      `Đã sẵn sàng nhập dữ liệu cho ${context().company_id}. Chọn tệp CSV/Excel, sau đó bấm “Kiểm tra và tạo bản xem trước”.`;
    status.className=loadError?'note error':'note';status.setAttribute('aria-busy',String(loading));
    $('import-retry').hidden=!loadError;$('import-retry').disabled=busy;
  }
  function invalidate(){preview=null;$('import-ack').checked=false;$('import-save-section').hidden=true;$('import-preview-section').hidden=true;$('import-notice').hidden=true;controls();}
  async function load(){
    if(busy)return;
    const own=++generation;current=null;loading=true;loadError='';busy=true;invalidate();controls();
    $('import-existing').textContent='Đang đọc danh mục…';$('import-references').textContent='';$('import-schema').textContent='';
    try{
      overview=await api('/api/company-ml?'+new URLSearchParams({scenario:context().scenario}));
      $('import-access').textContent=(meta.qa?'MÔ PHỎNG / QA · Dữ liệu và danh tính thử nghiệm. ':'')+(overview.can_manage?'Kế toán trưởng/giám đốc có thể nhập trong phạm vi doanh nghiệp được cấp.':'Chỉ xem. Cần quyền kế toán trưởng/giám đốc để kiểm tra và lưu tệp.');
      const previous=context().company_id;
      $('import-company').innerHTML=overview.companies.map(c=>`<option value="${escape(c.company_id)}">${escape(c.company_id)} · ${escape(c.name)}</option>`).join('');
      if(overview.companies.some(c=>c.company_id===previous))$('import-company').value=previous;
      if(!context().company_id){$('import-existing').textContent='Không có doanh nghiệp trong phạm vi tài khoản.';return;}
      const value=await api('/api/data-import/context?'+new URLSearchParams({scenario:context().scenario,company:context().company_id}));
      if(own!==generation)return;
      current=value;
      $('import-existing').textContent=`Tập ML hiện tại: ${value.status.data?.rows||0} giao dịch. Lần nhập sẽ thay thế tập này. Model ${value.status.active_version?'đang dùng sẽ được giữ nguyên.':'chưa được kích hoạt.'}`;
      $('import-template').href='/api/data-import/template?'+new URLSearchParams({scenario:context().scenario,company:context().company_id});
      $('import-references').innerHTML=Object.entries(value.references).map(([name,ids])=>`<p><strong>${escape({employees:'Nhân viên',vendors:'Nhà cung cấp',customers:'Khách hàng'}[name])} (${ids.length} mã)</strong>: ${escape(ids.slice(0,100).join(', ')||'Chưa có mã')}${ids.length>100?' … (hiển thị 100 mã đầu)':''}</p>`).join('');
      $('import-schema').innerHTML=`<p><strong>Bắt buộc</strong><br><code>${escape(value.required.join(', '))}</code></p><p><strong>Tùy chọn</strong><br><code>${escape(value.optional.join(', '))}</code></p><p><strong>txn_type</strong><br><code>${escape(value.txn_types.join(', '))}</code></p><p>Cột company_id có thể bỏ trống để dùng doanh nghiệp đang chọn. Các cột tiền bắt buộc phải khai rõ, kể cả 0. Cột tùy chọn thiếu sẽ được nêu trong bản xem trước; không tự điền bằng chứng.</p>`;
    }catch(error){loadError=error.message;$('import-existing').textContent='Chưa đọc được danh mục.';notice(error.message,true);}
    finally{loading=false;busy=false;controls();}
  }
  function render(value){
    preview=value;$('import-preview-section').hidden=false;
    const s=value.summary;
    $('import-summary').innerHTML=`<p><strong>${escape(s.company_id)} · ${s.rows} dòng qua kiểm tra${value.valid?` · ${value.feature_count} đặc trưng`:''}</strong><br>Bỏ qua ${s.skipped_blank_rows} dòng rỗng · cắt khoảng trắng ở ${s.trimmed_cells} ô.${value.valid?`<br>Thay thế ${s.previous_rows} → ${s.rows} giao dịch. ${escape(s.first_at)} → ${escape(s.last_at)}`:''}</p>`;
    $('import-errors').innerHTML=errorsTable(value);
    $('import-warnings').innerHTML=value.warnings.length?`<h3>Đọc trước khi lưu</h3><ul>${value.warnings.map(w=>`<li>${escape(w)}</li>`).join('')}</ul>`:'';
    const missing=Object.entries(s.missing_optional||{});
    if(missing.length)$('import-warnings').innerHTML+=`<details><summary>Ô tùy chọn còn thiếu</summary><p>${missing.map(([k,v])=>`${escape(k)}: ${v} dòng`).join(' · ')}</p></details>`;
    $('import-rows').innerHTML=rowsTable(value.normalized_preview);$('import-normalized').open=!!value.valid;
    $('import-save-section').hidden=!value.valid;$('import-ack').checked=false;
    notice(value.valid?'Kiểm tra đạt. Xem dữ liệu chuẩn hóa và cảnh báo trước khi xác nhận lưu.':'Có lỗi cần sửa. Dữ liệu và mô hình hiện tại được giữ nguyên.',!value.valid);
    controls();
  }
  async function encode(file){
    const bytes=new Uint8Array(await file.arrayBuffer());let binary='';
    for(let i=0;i<bytes.length;i+=32768)binary+=String.fromCharCode(...bytes.subarray(i,i+32768));
    return btoa(binary);
  }
  $('import-form').addEventListener('submit',async event=>{
    event.preventDefault();if(busy||!current||!overview?.can_manage)return;
    invalidate();busy=true;controls();const own=generation,file=$('import-file').files[0];
    notice('Đang kiểm tra tệp, chuẩn hóa dữ liệu và tạo đặc trưng…');
    try{
      if(!file||file.size>current.max_bytes||!file.size)throw new Error('Chọn tệp không rỗng, tối đa 10 MB.');
      const value=await api('/api/data-import/preview',{...context(),filename:file.name,content_base64:await encode(file),
        expected_revision:current.status.data?.revision||null,date_order:$('import-date-order').value,
        encoding:$('import-encoding').value,delimiter:$('import-delimiter').value==='tab'?'\t':$('import-delimiter').value});
      if(own===generation)render(value);
    }catch(error){notice(error.message,true);}
    finally{busy=false;controls();}
  });
  $('import-save').addEventListener('click',async()=>{
    if(busy||!overview?.can_manage||!current||!preview?.token||!$('import-ack').checked)return;
    busy=true;controls();notice('Đang lưu dữ liệu đã kiểm tra…');
    try{
      const value=await api('/api/data-import/commit',{...context(),token:preview.token,acknowledge:true});
      preview=null;global.location.assign(value.next_url);
    }catch(error){preview=null;$('import-ack').checked=false;$('import-save-section').hidden=true;notice(error.message+' Tải lại và kiểm tra lại tệp trước khi lưu.',true);}
    finally{busy=false;controls();}
  });
  const reload=()=>meta&&$('import-scenario').value?load():initialize();
  for(const id of ['import-company','import-scenario','import-reload'])$(id).addEventListener(id==='import-reload'?'click':'change',()=>{if(id!=='import-reload')$('import-file').value='';reload();});
  $('import-retry').addEventListener('click',reload);
  for(const id of ['import-file','import-date-order','import-encoding','import-delimiter'])$(id).addEventListener('change',invalidate);
  $('import-ack').addEventListener('change',controls);
  async function initialize(){
    if(busy)return;
    busy=true;loading=true;loadError='';controls();
    try{
      meta=await api('/api/meta');overview=await api('/api/company-ml');
      const query=new URLSearchParams(global.location.search);
      $('import-scenario').innerHTML=meta.scenarios.filter(s=>s!=='005').map(s=>`<option value="${escape(s)}">${escape(s)}</option>`).join('');
      $('import-scenario').value=meta.scenarios.includes(query.get('scenario'))&&query.get('scenario')!=='005'?query.get('scenario'):meta.default_scenario;
      if($('import-scenario').value!==meta.default_scenario)overview=await api('/api/company-ml?'+new URLSearchParams({scenario:$('import-scenario').value}));
      $('import-company').innerHTML=overview.companies.map(c=>`<option value="${escape(c.company_id)}">${escape(c.company_id)} · ${escape(c.name)}</option>`).join('');
      if(overview.companies.some(c=>c.company_id===query.get('company')))$('import-company').value=query.get('company');
    }catch(error){loadError=error.message;notice(error.message,true);}
    finally{busy=false;loading=false;controls();}
    if(!loadError)await load();
  }
  initialize();
})(globalThis);
