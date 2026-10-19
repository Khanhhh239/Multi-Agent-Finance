'use strict';
// A reread is a proposal. Only the existing reviewed-save flow can confirm it.
const regionView={path:null,generation:0,busy:false};
const regionPanel=element('div',undefined,'region-panel');regionPanel.hidden=true;
const regionRead=button('Đọc lại vùng chữ',()=>perform(readSelectedRegion));regionRead.id='reread-region';
const regionStatus=element('p','Chỉ đọc tên, địa chỉ và mô tả hàng có vùng nguồn. Kết quả cần đối chiếu.','muted');regionStatus.id='region-status';regionStatus.setAttribute('role','status');
const regionOutput=element('div');regionOutput.id='region-output';regionPanel.append(regionRead,regionStatus,regionOutput);$('candidates').after(regionPanel);
function regionSupported(path){return /^(parties\.(seller|buyer)\.(name|address)|items\.[A-Za-z0-9_:-]+\.description)$/.test(path||'');}
function clearRegion(){regionView.generation++;regionView.path=null;regionPanel.hidden=true;regionOutput.replaceChildren();}
document.addEventListener('agent3:record-loading',clearRegion);
document.addEventListener('agent3:field-selected',event=>{regionView.generation++;regionView.path=event.detail.path;regionPanel.hidden=!regionSupported(regionView.path);regionOutput.replaceChildren();regionRead.disabled=regionView.busy;regionStatus.textContent='Đọc lại từng dòng từ vùng nguồn; không tự sửa hoặc xác nhận dữ liệu.';});
async function readSelectedRegion(){
 if(regionView.busy||!state.view||!regionSupported(regionView.path))return;
 if(state.loadingRecord||state.saving||hasDraft())throw new Error('Lưu hoặc bỏ bản nháp trước khi đọc lại vùng chữ.');
 const generation=regionView.generation,record=state.view.record,path=regionView.path,payer=state.payer;
 const current=()=>generation===regionView.generation&&state.payer===payer&&state.view?.record.record_id===record.record_id&&state.view.record.revision===record.revision;
 regionView.busy=true;regionRead.disabled=true;regionOutput.replaceChildren();regionStatus.textContent='Đang đọc lại vùng chữ trên máy; dữ liệu đã lưu được giữ nguyên…';
 try{
  const result=await api('/v1/records/'+record.record_id+'/reread-region',{method:'POST',body:{expected_record_revision:record.revision,field_path:path}});
  if(!current())return;
  regionStatus.textContent=result.status==='CANDIDATE'?'Đã đọc lại. So sánh với ảnh gốc trước khi dùng; chưa xác nhận dữ liệu.':'Chưa đọc đủ vùng chữ. Đối chiếu ảnh hoặc yêu cầu nguồn rõ hơn.';
  regionOutput.append(element('p','Giá trị đã lưu: '+(result.original_value??'Chưa có')),element('p','Đọc lại: '+(result.suggested_value??'Chưa có')));
  const details=element('details');details.append(element('summary','Xem từng dòng và vùng nguồn'));
  for(const observation of result.observations){const row=element('div');row.append(element('p',observation.original_text+' → '+observation.text));row.append(button('Xem vùng',()=>{if(current())return showPage(observation.evidence.page_index,[observation.evidence]);}));details.append(row);}regionOutput.append(details);
  if(result.status==='CANDIDATE')regionOutput.append(button('Đưa vào bản nháp',()=>{
   if(!current()||state.loadingRecord||state.saving)return;
   const edit=state.edits.get(path);if(!edit)return;
   if(hasDraft()){message('Đang có bản nháp. Lưu hoặc bỏ thay đổi trước khi dùng kết quả đọc lại.',true);return;}
   edit.input.value=result.suggested_value;edit.checked.checked=true;delete edit.candidate;edit.error.textContent='';updateDirty();
   $('reason').value='Đối chiếu ảnh gốc và kết quả đọc lại vùng '+result.recovery_id;
   message('Đã đưa vào bản nháp. Đối chiếu ảnh, rồi lưu dữ liệu hóa đơn để xác nhận.');
  }));
 }catch(error){
  const reasons={REGION_NO_EVIDENCE:'Chưa có vùng nguồn. Cần đối chiếu toàn trang hoặc xử lý riêng.',REGION_CONFLICT:'Các vùng nguồn rời nhau. Chọn đúng ứng viên trước để tránh ghép nhầm người bán/người mua.',REGION_BUDGET:'Trường có quá nhiều vùng hoặc ảnh quá lớn; cần xử lý riêng.',REGION_NOT_LINE:'Vùng nguồn gồm nhiều dòng hoặc quá lớn; cần tách vùng trước.',REGION_BUSY:'Đang đọc một vùng khác. Thử lại sau khi hoàn tất.',WORKER_TIMEOUT:'Bộ đọc đang bận hoặc hết thời gian. Dữ liệu cũ được giữ nguyên; có thể thử lại.',MODEL_UNAVAILABLE:'Bộ đọc vùng chưa sẵn sàng trên máy. Kiểm tra runtime/model rồi thử lại.'};
  if(reasons[error.code])error.message=reasons[error.code];if(current())regionStatus.textContent=error.message;throw error;
 }
 finally{regionView.busy=false;regionRead.disabled=false;}
}

// Revision-bound review queue. Recommendations are selected by policy, never
// silently written to a saved field or marked HUMAN_CONFIRMED.
const recoveryQueue={generation:0,report:null,busy:false};
const queuePanel=element('details',undefined,'task-section');queuePanel.id='recovery-queue';queuePanel.open=false;
const queueTitle=element('summary','Tự kiểm tra lỗi OCR');const queueStatus=element('p','Đang tải chẩn đoán…','muted');queueStatus.id='recovery-queue-status';queueStatus.setAttribute('role','status');
const queueItems=element('div');queueItems.id='recovery-queue-items';
const queueRun=button('Kiểm tra và đọc lại vùng lỗi',()=>perform(()=>runAutomaticRecovery(()=>true)));queueRun.id='run-region-recovery';
const queueRetry=button('Thử lại lượt bị lỗi',()=>perform(()=>runAutomaticRecovery(()=>true,true)));queueRetry.id='retry-region-recovery';queueRetry.hidden=true;
const queueApply=button('Đưa các gợi ý được chọn vào bản nháp',applyRecoveryRecommendations);queueApply.id='apply-recovery-recommendations';queueApply.hidden=true;
queuePanel.append(queueTitle,queueStatus,queueItems,queueRun,queueRetry,queueApply);$('fields').before(queuePanel);
function queueKey(){return state.view?state.payer+':'+state.view.record.record_id+':'+state.view.record.revision:null;}
function queueMatch(key,generation){return key===queueKey()&&generation===recoveryQueue.generation;}
function renderRecoveryQueue(report){
 recoveryQueue.report=report;queueItems.replaceChildren();queueRetry.hidden=!report.errors?.length||report.attempt>=2;queueApply.hidden=!report.recommended;
 const entries=report.entries||[];
 queueTitle.textContent=`Tự kiểm tra lỗi OCR · ${report.recommended||0} gợi ý · ${entries.length} trường cần chú ý`;
 queuePanel.open=Boolean(report.recommended||report.errors?.length);
 queueStatus.textContent=report.stale?'Bản này đã đổi. Tải lại trước khi dùng gợi ý.':`${report.recommended||0} gợi ý được chọn để đối chiếu · ${entries.length} trường cần chú ý. Dữ liệu đã lưu chưa thay đổi.`;
 if(report.errors?.length&&report.attempt>=2)queueStatus.textContent+=' Đã hết hai lượt thử; cần nguồn rõ hơn hoặc xử lý riêng.';
 for(const entry of entries){const row=element('div',undefined,'recovery-entry');row.append(element('strong',fieldLabel(entry.field_path)));
  const reason={REPEATED_SUFFIX:'Lặp chữ ở cuối',FIELD_MISSING:'Chưa đọc được',FIELD_AMBIGUOUS:'Có nhiều ứng viên',UNREADABLE_CHARACTER:'Có ký tự lỗi',SOURCE_CONFLICT:'Nguồn có xung đột'};
  row.append(element('p',entry.issue_codes.map(c=>reason[c]||'Cần đối chiếu').join(' · ')));
  if(entry.recovery)row.append(element('p','Đã lưu: '+(entry.recovery.original_value??'Chưa có')),element('p','Đọc lại: '+(entry.recovery.suggested_value??'Chưa có')));
  const decision=entry.selection?.decision;
  row.append(element('p',decision==='RECOMMENDED'?'Gợi ý sửa phần lặp đã được hai cách đọc đối chiếu; vẫn cần bạn xác nhận.':decision==='UNCHANGED'?'Đọc lại giống kết quả cũ; không chứng minh đã đúng.':entry.state==='ERROR'?'Chưa đọc lại được; dữ liệu cũ được giữ nguyên.':entry.state==='DEFERRED'?'Đã hết ngân sách lượt này; cần xử lý tiếp.':'Cần đối chiếu thủ công; chưa có gợi ý đủ căn cứ.','muted'));
  const key=queueKey(),generation=recoveryQueue.generation;
  row.append(button('Xem trường và nguồn',()=>{if(queueMatch(key,generation))return showField(entry.field_path);}));queueItems.append(row);
 }
}
async function loadRecoveryQueue(){
 if(!state.view||state.loadingRecord)return;const key=queueKey(),generation=++recoveryQueue.generation;
 const result=await api('/v1/records/'+state.view.record.record_id+'/automation-review');if(!queueMatch(key,generation))return;
 renderRecoveryQueue(result.latest||{entries:result.plan.entries,recommended:0,errors:[]});
}
async function runAutomaticRecovery(stillCurrent=()=>true,retryFailed=false){
 if(!state.view||state.loadingRecord||recoveryQueue.busy)return;
 if(state.saving||hasDraft())throw new Error('Lưu hoặc bỏ bản nháp trước khi tự phục hồi OCR.');
 const key=queueKey(),generation=++recoveryQueue.generation,record=state.view.record;
 recoveryQueue.busy=true;queueRun.disabled=true;queueRetry.disabled=true;queuePanel.open=true;queueStatus.textContent='Đang kiểm tra và đọc lại tối đa hai trường; bản đã lưu được giữ nguyên…';
 try{const result=await api('/v1/records/'+record.record_id+'/automation-review',{method:'POST',body:{expected_record_revision:record.revision,retry_failed:retryFailed}});
  if(queueMatch(key,generation)&&stillCurrent()&&!hasDraft())renderRecoveryQueue(result);
 }catch(error){
  const reasons={AUTOMATION_BUDGET:'Đã hết hai lượt phục hồi cho bản này. Cần nguồn rõ hơn hoặc xử lý riêng.',AUTOMATION_BUSY:'Bản này đang có lượt phục hồi khác; chờ hoàn tất rồi tải lại.'};
  if(reasons[error.code])error.message=reasons[error.code];if(queueMatch(key,generation))queueStatus.textContent='Chưa phục hồi được: '+error.message;throw error;
 }
 finally{recoveryQueue.busy=false;queueRun.disabled=false;queueRetry.disabled=false;}
}
function applyRecoveryRecommendations(){
 const report=recoveryQueue.report;if(!report||report.stale||report.record_id!==state.view?.record.record_id||report.record_revision!==state.view.record.revision)return;
 if(state.loadingRecord||state.saving||hasDraft())throw new Error('Lưu hoặc bỏ bản nháp trước khi đưa gợi ý vào.');
 const entries=report.entries.filter(e=>e.selection?.decision==='RECOMMENDED');
 for(const entry of entries){const edit=state.edits.get(entry.field_path);if(!edit||edit.current?.confidence_basis==='HUMAN_CONFIRMED')throw new Error('Trường đã thay đổi; tải lại để đối chiếu.');}
 for(const entry of entries){const edit=state.edits.get(entry.field_path);edit.input.value=entry.selection.selected_value;edit.checked.checked=true;delete edit.candidate;edit.error.textContent='';}
 $('reason').value='Đối chiếu nguồn và gợi ý phục hồi OCR '+report.run_id;updateDirty();message('Đã đưa gợi ý vào bản nháp. Đối chiếu rồi lưu để xác nhận.');
}
document.addEventListener('agent3:record-loading',()=>{recoveryQueue.generation++;recoveryQueue.report=null;queueItems.replaceChildren();queueApply.hidden=true;queueRetry.hidden=true;});
document.addEventListener('agent3:record-ready',()=>{if(!autoInput.checked)perform(loadRecoveryQueue);});
