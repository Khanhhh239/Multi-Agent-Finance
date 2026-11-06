"use strict";
(function(global){
  const escape=value=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const percent=value=>value==null?"Chưa đủ nhãn":(value*100).toFixed(2)+"%";
  const local=value=>value?new Date(value).toLocaleString("sv-SE",{timeZone:"Asia/Ho_Chi_Minh"}).replace(" ","T").slice(0,16):"";
  const date=value=>value?new Date(value).toLocaleString("vi-VN",{timeZone:"Asia/Ho_Chi_Minh"}):"—";
  const labels={data_updated:"Cập nhật dữ liệu",evaluated:"Đánh giá ứng viên",activated:"Kích hoạt phiên bản",rolled_back:"Quay lại phiên bản",kept:"Giữ phiên bản",scored:"Chạy ML"};
  function versionTable(data,algorithms,canManage){
    const names=Object.fromEntries(algorithms.map(a=>[a.id,a.label]));
    const used=new Set(data.history.filter(e=>["activated","rolled_back"].includes(e.action)).map(e=>e.details.version_id));
    if(!data.versions.length)return '<p>Chưa có ứng viên. Cập nhật dữ liệu rồi đánh giá một thuật toán.</p>';
    return `<div class="table-wrap"><table><thead><tr><th>Phiên bản</th><th>Evaluation</th><th>Cảnh báo</th><th>Precision / Recall</th><th>Thời gian</th><th>Thao tác</th></tr></thead><tbody>${data.versions.map(v=>{
      const active=v.version_id===data.active_version,stale=v.data_revision!==data.data?.revision;
      const rollback=used.has(v.version_id)&&!active;
      const eligible=!active&&(!stale||rollback)&&canManage;
      return `<tr class="${active?"active":""}"><td class="description"><strong>${escape(names[v.algorithm]||v.algorithm)} · v${v.number}</strong><br>${active?"Đang dùng":stale?"Đánh giá trên dữ liệu cũ":"Ứng viên chưa kích hoạt"}${v.converged===false?"<br>Chưa hội tụ · cần xem lại trước khi dùng":""}</td><td>${v.evaluation_rows} dòng<br><small>Từ ${escape(date(v.calibration_end))}</small></td><td>${v.evaluation_alerts} · ${percent(v.evaluation_alert_rate)}</td><td>${percent(v.precision)} / ${percent(v.recall)}<br><small>${v.labelled_evaluation_rows} dòng có nhãn</small></td><td>${escape(v.seconds)} giây</td><td>${active?"Đã cố định":`<button type="button" data-ml-version="${escape(v.version_id)}" data-rollback="${rollback}" ${eligible?"":"disabled"}>${rollback?"Quay lại":"Xác nhận dùng"} v${v.number}</button>`}</td></tr>`;
    }).join("")}</tbody></table></div>`;
  }
  function scoreTable(result){
    return `<p><strong>${result.run.rows} giao dịch đã chấm · ${result.run.flagged} vượt ngưỡng</strong> · v${result.run.number}</p><p class="hint">Hiển thị ${result.items.length}/${result.total} dòng. Kết quả đầy đủ được lưu cùng lượt chạy.</p><div class="table-wrap"><table><thead><tr><th>Giao dịch</th><th>Thời điểm</th><th>Điểm bất thường</th><th>Kết quả</th></tr></thead><tbody>${result.items.map(r=>`<tr><td>${escape(r.transaction_id)}</td><td>${escape(date(r.posted_at))}</td><td>${Number(r.anomaly_score).toFixed(6)}</td><td>${r.flagged?"Cần đối chiếu":"Trong ngưỡng model"}</td></tr>`).join("")}</tbody></table></div>`;
  }
  global.CompanyMLUI={escape,local,versionTable,scoreTable};
  labels.data_imported="Nhập CSV / Excel";labels.labels_updated="Cập nhật nhãn đã rà";
  if(!global.document?.getElementById("ml-company"))return;
  const $=id=>document.getElementById(id);
  let meta=null,overview=null,current=null,busy=false,generation=0,formRevision=null;
  let labelPreview=null,labelDraft="";
  let readiness=null,readinessFor=null,readinessSequence=0,readinessTimer=null,readinessError="";
  function notice(message,error=false){const node=$("ml-notice");node.textContent=message;node.className=error?"error":"";node.hidden=false;if(error)node.focus();}
  async function api(path,body){
    let response;
    try{response=await fetch(path,body===undefined?{}:{method:"POST",headers:{"Content-Type":"application/json","X-CSRF-Token":meta.csrf_token},body:JSON.stringify(body)});}
    catch{throw new Error("Mất kết nối. Không tự gửi lại thao tác. Tải lại cấu hình và kiểm tra lịch sử trước khi thử lại.");}
    let value;try{value=await response.json();}catch{throw new Error("Chưa đọc được phản hồi. Tải lại cấu hình để kiểm tra kết quả.");}
    if(!response.ok){
      if(response.status===403&&value.error==="Phiên làm việc đã thay đổi. Tải lại trang để tiếp tục.")meta=await api("/api/meta");
      throw new Error(value.error||"Chưa thực hiện được thao tác.");
    }
    return value;
  }
  const context=()=>({scenario:$("ml-scenario").value,company_id:$("ml-company").value});
  const iso=value=>value?value+(value.length===16?":00":"")+"+07:00":"";
  const windows=()=>({train_end:iso($("ml-train-end").value),calibration_end:iso($("ml-calibration-end").value)});
  const readinessKey=()=>JSON.stringify([context(),current?.data?.revision,current?.active_version,windows()]);
  const checked=()=>!!readiness&&readinessFor===readinessKey();
  function algorithms(){
    if(!overview)return;
    const selected=$("ml-algorithm").value||"isolation_forest";
    $("ml-algorithm").innerHTML=overview.algorithms.map(a=>{
      const blocked=a.requires_labels&&(!checked()||!readiness.catboost.eligible);
      return `<option value="${escape(a.id)}" ${!a.installed||blocked?"disabled":""}>${escape(a.label)}${!a.installed?" · chưa cài":blocked?" · chưa đủ điều kiện train":""}</option>`;
    }).join("");
    // Keep the user's choice visible when a period change makes it ineligible.
    // Training stays locked instead of silently switching the chosen algorithm.
    $("ml-algorithm").value=overview.algorithms.some(a=>a.id===selected)?selected:"isolation_forest";
  }
  function readinessNotes(){
    const ready=!!current?.data&&current.data.scenario===context().scenario;
    const pending=ready&&!checked()&&!readinessError;
    for(const id of ["ml-catboost-readiness","ml-score-readiness"])$(id).setAttribute("aria-busy",String(pending));
    $("ml-catboost-readiness").textContent=!ready?"Cập nhật dữ liệu cho bộ đang chọn để kiểm tra điều kiện CatBoost.":
      !checked()?readinessError||"Đang kiểm tra nhãn theo kỳ train đã chọn…":
      readiness.catboost.eligible?`CatBoost: ${readiness.catboost.verified_train_rows}/${readiness.catboost.train_rows} dòng train có nhãn hợp lệ trước cuối kỳ train · lớp 0: ${readiness.catboost.class_counts['0']} · lớp 1: ${readiness.catboost.class_counts['1']}. Đủ điều kiện.`:readiness.catboost.reason;
    $("ml-score-readiness").textContent=!ready?"Cập nhật dữ liệu cho bộ đang chọn để kiểm tra model.":
      !checked()?readinessError||"Đang kiểm tra tương thích của model đang dùng…":
      readiness.model.can_score?`Model tương thích · ${readiness.model.inference_rows} giao dịch ngoài kỳ train/calibration có thể chấm.`:readiness.model.reason;
    $("ml-score-readiness").className=checked()&&current.active_version&&!readiness.model.compatible?"note error":"note";
  }
  function invalidateReadiness(){
    ++readinessSequence;clearTimeout(readinessTimer);readinessTimer=null;
    readiness=null;readinessFor=null;readinessError="";algorithms();readinessNotes();controls();
  }
  async function checkReadiness(){
    if(!current?.data||current.data.scenario!==context().scenario)return;
    const own=++readinessSequence,key=readinessKey(),selected=context();
    const params={scenario:selected.scenario,company:selected.company_id,...windows(),
      expected_revision:current.data.revision,expected_active:current.active_version||""};
    try{
      const result=await api("/api/company-ml/readiness?"+new URLSearchParams(params));
      if(own!==readinessSequence||key!==readinessKey())return;
      if(result.company_id!==selected.company_id||result.scenario!==selected.scenario||result.data_revision!==current.data.revision||result.active_version!==current.active_version)
        throw new Error("Dữ liệu hoặc model đã đổi. Tải lại cấu hình trước khi tiếp tục.");
      readiness=result;readinessFor=key;readinessError="";
    }catch(error){
      if(own!==readinessSequence||key!==readinessKey())return;
      readiness=null;readinessFor=null;readinessError=error.message;
    }
    algorithms();readinessNotes();controls();
  }
  function scheduleReadiness(delay=0){
    invalidateReadiness();
    if(delay)readinessTimer=setTimeout(()=>{readinessTimer=null;checkReadiness();},delay);
    else checkReadiness();
  }
  function actionAllowed(action){
    if(!overview?.can_manage||!current?.data||current.data.scenario!==context().scenario||!checked())return false;
    if(action==="keep")return readiness.model.can_keep;
    if(action==="score")return readiness.model.can_score;
    const algorithm=overview.algorithms.find(a=>a.id===$("ml-algorithm").value);
    return !!algorithm?.installed&&readiness.evaluation.eligible&&(!algorithm.requires_labels||readiness.catboost.eligible);
  }
  function controls(){
    const manage=overview?.can_manage&&!busy,ready=!!current?.data&&current.data.scenario===context().scenario;
    for(const id of ["ml-company","ml-scenario","ml-reload","ml-labels","ml-algorithm","ml-train-end","ml-calibration-end","ml-budget"])$(id).disabled=busy;
    $("ml-update").disabled=!manage||!$("ml-company").value||!current;
    if(labelPreview)$("ml-update").disabled=true;
    if(current?.data?.source==="csv_excel_upload"&&!$("ml-labels").files.length)$("ml-update").disabled=true;
    const conflicts=!!labelPreview?.counts.conflicts,policy=$("ml-label-policy").value;
    const correcting=conflicts&&policy==="replace_conflicts";
    $("ml-label-policy-fields").hidden=!conflicts;
    $("ml-label-correction-fields").hidden=!correcting;
    for(const id of ["ml-label-policy","ml-label-reason","ml-label-acknowledge","ml-label-cancel"])$(id).disabled=busy;
    $("ml-label-save").disabled=!manage||!labelPreview||labelPreview.expected_revision!==current?.data?.revision||
      (conflicts&&!["keep_existing","replace_conflicts"].includes(policy))||
      (correcting&&(!$("ml-label-acknowledge").checked||!$("ml-label-reason").value.trim()));
    $("ml-evaluate").disabled=busy||!actionAllowed("evaluate");
    $("ml-keep").disabled=busy||!actionAllowed("keep");
    $("ml-score").disabled=busy||!actionAllowed("score");
    $("ml-versions").querySelectorAll("button[data-ml-version]").forEach(button=>{if(!manage||!ready)button.disabled=true;});
  }
  function render(data){
    current=data;
    const importLink=$("ml-import-link");
    if(importLink)importLink.href="/data-import?"+new URLSearchParams({company:data.company_id,scenario:context().scenario});
    const active=data.versions.find(v=>v.version_id===data.active_version);
    const imported=data.data?.source==="csv_excel_upload",sourceNote=$("ml-source-note");
    $("ml-update").textContent=imported?"Cập nhật nhãn cho dữ liệu đã nhập":"Cập nhật & kiểm tra dữ liệu";
    if(sourceNote)sourceNote.textContent=imported?"Đang dùng dữ liệu CSV/Excel đã kiểm tra. Chọn nhãn đã rà để bổ sung mà vẫn giữ nguyên giao dịch và feature. Để thay dữ liệu, mở màn hình nhập CSV/Excel.":"Đọc bộ nguồn đã kết nối với máy chủ và kiểm tra feature, thời gian, mã giao dịch trước khi lưu vào không gian ML của doanh nghiệp. Model đang dùng được giữ nguyên.";
    $("ml-data-summary").innerHTML=data.data?`<p><strong>${data.data.rows} giao dịch · ${data.data.columns.length} feature</strong> · ${data.data.labels_count} nhãn đã rà · Bộ ${escape(data.data.scenario)}<br>${escape(date(data.data.first_at))} → ${escape(date(data.data.last_at))}${data.data.scenario!==context().scenario?"<br>Cập nhật bộ đang chọn trước khi tiếp tục cấu hình/chạy ML.":""}</p>`:"<p>Chưa cập nhật dữ liệu ML cho doanh nghiệp này.</p>";
    $("ml-current").innerHTML=active?`<p class="note"><strong>Đang dùng: ${escape(overview.algorithms.find(a=>a.id===active.algorithm)?.label)} · v${active.number}</strong><br>Kích hoạt riêng cho ${escape(data.company_id)}. Cập nhật dữ liệu không tự đổi phiên bản.</p>`:'<p class="note">Doanh nghiệp chưa có model đang dùng. Cần đánh giá và xác nhận trước lần chạy đầu tiên.</p>';
    const formKey=JSON.stringify([data.company_id,data.data?.revision]);
    if(formKey!==formRevision){
      const defaults=data.data?.suggested_windows;
      $("ml-train-end").value=local(defaults?.train_end);$("ml-calibration-end").value=local(defaults?.calibration_end);
      formRevision=formKey;
    }
    $("ml-versions").innerHTML=versionTable(data,overview.algorithms,overview.can_manage);
    $("ml-history").innerHTML=data.history.slice().reverse().slice(0,40).map(e=>`<div class="history"><strong>${escape(labels[e.action]||e.action)}</strong> · ${escape(date(e.at))} · ${escape(e.actor)}</div>`).join("")||"<p>Chưa có thay đổi cấu hình.</p>";
    $("ml-runs").innerHTML=data.runs.length?`<h3>Lượt chạy gần đây</h3>${data.runs.map(r=>`<p class="hint">${escape(date(r.scored_at))} · v${r.number} · ${r.rows} dòng · ${r.flagged} vượt ngưỡng</p>`).join("")}`:"";
    scheduleReadiness();algorithmNote();controls();
  }
  function algorithmNote(){
    const notes={catboost:"CatBoost học từ nhãn xác nhận. Mọi dòng train phải có nhãn 0/1 và thời điểm biết nhãn trước cuối kỳ train.",
      autoencoder:"Autoencoder học tái tạo dữ liệu qua lớp nén. Cần xem cảnh báo hội tụ trong kết quả đánh giá.",
      ecod:"ECOD dùng phân phối tham chiếu cố định từ train; batch mới không làm thay phân phối đã lưu.",
      lof:"LOF chạy ở chế độ novelty, dùng model đã học để chấm dữ liệu mới.",
      isolation_forest:"Isolation Forest học trên kỳ train. Ngưỡng được chọn riêng bằng calibration của doanh nghiệp."};
    $("ml-algorithm-note").textContent=notes[$("ml-algorithm").value]||"";
  }
  async function reload(){
    const own=++generation;current=null;$("ml-scores").innerHTML="";
    clearLabelPreview();$("ml-labels").value="";
    invalidateReadiness();
    for(const id of ["ml-current","ml-versions","ml-history","ml-runs","ml-data-summary"])$(id).innerHTML="";
    controls();
    const previousCompany=$("ml-company").value;
    const nextOverview=await api("/api/company-ml?"+new URLSearchParams({scenario:context().scenario}));
    if(own!==generation)return;
    overview=nextOverview;
    $("ml-company").innerHTML=overview.companies.map(c=>`<option value="${escape(c.company_id)}">${escape(c.company_id)} · ${escape(c.name)}</option>`).join("");
    if(overview.companies.some(c=>c.company_id===previousCompany))$("ml-company").value=previousCompany;
    if(!$("ml-company").value)return;
    const data=await api("/api/company-ml/status?"+new URLSearchParams({scenario:context().scenario,company:context().company_id}));
    if(own===generation)render(data);
  }
  async function write(action,values={}){
    if(busy)return;
    if(["evaluate","keep","score"].includes(action)&&!actionAllowed(action)){
      notice(readinessError||"Thao tác chưa đủ điều kiện. Xem thông tin kiểm tra nhãn/model và tải lại cấu hình nếu dữ liệu đã đổi.",true);return;
    }
    busy=true;const own=generation;controls();
    notice(action==="evaluate"?"Đang huấn luyện và đánh giá trên các kỳ riêng… Model đang dùng được giữ nguyên.":"Đang xử lý…");
    try{
      const result=await api("/api/company-ml/"+action,{...context(),...values});
      if(own!==generation)return;
      if(action==="score"){$("ml-scores").innerHTML=scoreTable(result);await reloadStatus();}
      else render(result);
      if(action==="data-update"||action==="labels-update"){$("ml-labels").value="";clearLabelPreview();}
      if(action==="labels-update"){
        const counts=result.label_update;
        notice(`Đã xử lý nhãn: ${counts.existing} → ${counts.total}. Thêm ${counts.added}, trùng ${counts.unchanged}, sửa ${counts.updated}, giữ nhãn cũ do xung đột ${counts.skipped}. Giao dịch, feature và model đang dùng được giữ nguyên.`);return;
      }
      notice({evaluate:"Đã lưu ứng viên. Đối chiếu kết quả rồi chọn Xác nhận dùng phiên bản.","data-update":"Dữ liệu đã được kiểm tra và cập nhật. Tiếp theo chọn hoặc giữ model của doanh nghiệp.",activate:"Đã cố định phiên bản ML cho doanh nghiệp.",keep:"Đã giữ nguyên phiên bản hiện tại.",score:"Đã chấm bằng phiên bản đang dùng; kết quả lưu trong lịch sử."}[action]);
    }catch(error){scheduleReadiness();notice(error.message,true);}
    finally{
      busy=false;
      if(current)$("ml-versions").innerHTML=versionTable(current,overview.algorithms,overview.can_manage);
      controls();
    }
  }
  async function reloadStatus(){const data=await api("/api/company-ml/status?"+new URLSearchParams({scenario:context().scenario,company:context().company_id}));render(data);}
  function clearLabelPreview(){
    labelPreview=null;labelDraft="";$("ml-label-preview").hidden=true;
    $("ml-label-policy").value="";$("ml-label-reason").value="";$("ml-label-acknowledge").checked=false;
  }
  async function previewLabels(text){
    if(busy||!current?.data||!overview?.can_manage)return;
    busy=true;const own=generation;controls();notice("Đang kiểm tra nhãn và đối chiếu xung đột…");
    try{
      const result=await api("/api/company-ml/labels-preview",{...context(),expected_revision:current.data.revision,labels_text:text});
      if(own!==generation)return;
      clearLabelPreview();labelPreview=result;labelDraft=text;
      const c=result.counts;
      $("ml-label-counts").textContent=`Đang có ${c.existing} nhãn · tệp có ${c.incoming}: thêm ${c.added}, trùng ${c.unchanged}, xung đột ${c.conflicts}. Sau khi lưu: ${c.total} nhãn. Các nhãn không có trong tệp được giữ nguyên.`;
      const detail=value=>`Nhãn ${escape(value.label)}<br>Người rà: ${escape(value.reviewer_id)}<br>${escape(date(value.reviewed_at))}<br>Căn cứ: ${escape(value.evidence_ref)}`;
      $("ml-label-conflicts").innerHTML=result.conflicts.length?`<p>Chưa lưu thay đổi nào. Chọn cách xử lý toàn bộ nhãn xung đột dưới đây.</p><div class="table-wrap"><table><thead><tr><th>Giao dịch</th><th>Nhãn hiện có</th><th>Nhãn trong tệp</th></tr></thead><tbody>${result.conflicts.map(row=>`<tr><td>${escape(row.transaction_id)}</td><td>${detail(row.existing)}</td><td>${detail(row.incoming)}</td></tr>`).join("")}</tbody></table></div>`:"";
      $("ml-label-preview").hidden=false;notice("Đã kiểm tra nhãn. Xem trước và bấm Lưu nhãn để xác nhận.");
    }catch(error){notice(error.message,true);}
    finally{busy=false;controls();}
  }
  $("ml-reload").addEventListener("click",()=>reload().catch(error=>notice(error.message,true)));
  for(const id of ["ml-company","ml-scenario"])$(id).addEventListener("change",()=>reload().catch(error=>notice(error.message,true)));
  $("ml-algorithm").addEventListener("change",()=>{algorithmNote();controls();});
  $("ml-labels").addEventListener("change",()=>{clearLabelPreview();controls();});
  for(const id of ["ml-label-policy","ml-label-reason","ml-label-acknowledge"])$(id).addEventListener("input",controls);
  $("ml-label-policy").addEventListener("change",controls);
  $("ml-label-cancel").addEventListener("click",()=>{clearLabelPreview();controls();notice("Đã hủy xem trước; nhãn hiện có được giữ nguyên.");});
  $("ml-label-save").addEventListener("click",()=>{
    if($("ml-label-save").disabled||!labelPreview)return;
    write("labels-update",{expected_revision:labelPreview.expected_revision,labels_text:labelDraft,
      preview_hash:labelPreview.preview_hash,conflict_policy:labelPreview.counts.conflicts?$("ml-label-policy").value:"reject",
      acknowledge:$("ml-label-acknowledge").checked,reason:$("ml-label-reason").value});
  });
  for(const id of ["ml-train-end","ml-calibration-end"]){
    $(id).addEventListener("input",()=>scheduleReadiness(300));
    $(id).addEventListener("change",()=>scheduleReadiness());
  }
  $("ml-data-form").addEventListener("submit",async event=>{
    event.preventDefault();const file=$("ml-labels").files[0],own=generation;
    try{if(file?.size>1_500_000)throw new Error("CSV nhãn vượt giới hạn 1,5 MB.");
      const labelsText=file?await file.text():"";if(own!==generation)return;
      if(file&&current?.data)await previewLabels(labelsText);
      else await write(current?.data?.source==="csv_excel_upload"?"labels-update":"data-update",{expected_revision:current?.data?.revision||null,labels_text:labelsText});
    }catch(error){notice(error.message,true);}
  });
  $("ml-evaluate-form").addEventListener("submit",event=>{
    event.preventDefault();if(!current?.data)return;
    write("evaluate",{expected_revision:current.data.revision,algorithm:$("ml-algorithm").value,
      ...windows(),alert_budget:Number($("ml-budget").value)/100});
  });
  $("ml-versions").addEventListener("click",event=>{
    const button=event.target.closest("button[data-ml-version]");if(!button||button.disabled)return;
    write("activate",{version_id:button.dataset.mlVersion,rollback:button.dataset.rollback==="true",expected_active:current.active_version,expected_revision:current.data.revision});
  });
  for(const action of ["keep","score"])$("ml-"+action).addEventListener("click",()=>write(action,{expected_active:current.active_version,expected_revision:current.data.revision}));
  (async()=>{
    try{
      [meta,overview]=await Promise.all([api("/api/meta"),api("/api/company-ml")]);
      $("ml-scenario").innerHTML=meta.scenarios.filter(s=>s!=="005").map(s=>`<option value="${escape(s)}">${escape(s)}</option>`).join("");
      if(meta.default_scenario!=="005")$("ml-scenario").value=meta.default_scenario;
      const requested=new URLSearchParams(global.location?.search||"");
      if(meta.scenarios.includes(requested.get("scenario"))&&requested.get("scenario")!=="005")$("ml-scenario").value=requested.get("scenario");
      if($("ml-scenario").value!==meta.default_scenario)overview=await api("/api/company-ml?"+new URLSearchParams({scenario:$("ml-scenario").value}));
      $("ml-company").innerHTML=overview.companies.map(c=>`<option value="${escape(c.company_id)}">${escape(c.company_id)} · ${escape(c.name)}</option>`).join("");
      if(overview.companies.some(c=>c.company_id===requested.get("company")))$("ml-company").value=requested.get("company");
      $("ml-access").textContent=overview.can_manage?"Kế toán trưởng hoặc giám đốc có thể cập nhật, đánh giá và xác nhận ML trong phạm vi công ty được cấp.":"Cấu hình chỉ xem. Cần danh tính do máy chủ xác thực và quyền kế toán trưởng/giám đốc để thay đổi ML.";
      if(meta.qa)$("ml-access").textContent="MÔ PHỎNG / QA · Danh tính và dữ liệu test, không có người rà độc lập. "+$("ml-access").textContent;
      if(!overview.companies.length)notice("Chưa có doanh nghiệp trong phạm vi đăng nhập. Kết nối danh tính để cấu hình ML.");
      await reload();controls();
    }catch(error){notice(error.message,true);controls();}
  })();
})(globalThis);
