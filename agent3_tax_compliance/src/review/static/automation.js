'use strict';
// Opt-in browser orchestration. Closing the page stops this chain, not capture workers.
const automation={generation:0,attempted:new Set(),recovered:new Set(),running:new Set(),recovering:false};
const autoBar=element('div',undefined,'automation-bar');
const autoLabel=element('label',undefined,'check');const autoInput=element('input');autoInput.type='checkbox';autoInput.id='auto-chain';
autoLabel.append(autoInput,element('span','Tự kiểm tra và diễn giải sau khi tải / lưu (khi web đang mở)'));
const recoverButton=button('Trích xuất lại dữ liệu',()=>perform(()=>recoverExtraction(false)));recoverButton.id='recover-extraction';
const autoRetry=button('Chạy tiếp',()=>perform(()=>runAutomation(true)));autoRetry.id='run-automation';
const autoStatus=element('p','Bật tự chạy để giảm thao tác. Dữ liệu vẫn cần đối chiếu; không tự xác nhận trường.','muted');autoStatus.id='automation-status';autoStatus.setAttribute('role','status');
autoBar.append(autoLabel,recoverButton,autoRetry,autoStatus);$('workflow-nav').after(autoBar);
function automationKey(){return state.view?state.payer+':'+state.view.record.record_id+':'+state.view.record.revision:null;}
function automationMatch(key,generation){return key===automationKey()&&generation===automation.generation;}
async function recoverExtraction(automatic){
 if(!state.view||automation.recovering)return false;
 if(state.loadingRecord)throw new Error('Đang mở hồ sơ. Chờ tải xong trước khi trích xuất lại.');
 if(state.saving||hasDraft())throw new Error('Lưu hoặc bỏ bản nháp trước khi trích xuất lại.');
 const key=automationKey(),generation=automation.generation,record=state.view.record;
 automation.recovering=true;recoverButton.disabled=true;
 autoStatus.textContent='Đang trích xuất lại từ OCR đã lưu; không ghi đè hồ sơ cũ…';
 try{
  const result=await api('/v1/records/'+record.record_id+'/reextract',{method:'POST',body:{expected_record_revision:record.revision,reason:automatic?'Automatic bounded recovery: no extracted rows':'Operator requested extraction recovery from retained OCR'}});
  if(!automationMatch(key,generation))return false;
  if(result.status==='NO_CHANGE'){autoStatus.textContent=result.message;return false;}
  if(!result.record_id){autoStatus.textContent='Cần tách tài liệu / xử lý riêng. Hồ sơ cũ được giữ nguyên.';return false;}
  if(hasDraft()||result.previous_current_revision!==record.revision){autoStatus.textContent='Đã tạo bản trích xuất mới nhưng bản đang xem có thay đổi. Mở từ danh sách để đối chiếu; chưa chuyển hồ sơ.';await loadRecords();return false;}
  await loadRecords();if(!automationMatch(key,generation)||hasDraft())return false;
  await openRecord(result.record_id);
  autoStatus.textContent='Đã mở bản trích xuất mới: '+result.item_count+' dòng. Hồ sơ cũ vẫn giữ nguyên trong danh sách; cần đối chiếu lại.';
  return true;
 }catch(error){if(automationMatch(key,generation))autoStatus.textContent='Chưa trích xuất lại được: '+error.message;throw error;}
 finally{automation.recovering=false;recoverButton.disabled=false;}
}
async function runAutomation(force=false){
 if(!state.view||state.loadingRecord||(!autoInput.checked&&!force))return;
 const key=automationKey(),generation=automation.generation;
 if(automation.running.has(key))return;
 if(automation.attempted.has(key)&&!force)return;
 if(state.saving||hasDraft()){autoStatus.textContent='Đang có bản nháp. Lưu trước để chạy tiếp.';return;}
 automation.attempted.add(key);automation.running.add(key);autoRetry.disabled=true;
 try{
  const source=state.payer+':'+state.view.record.source_id;
  if(!state.view.record.items.length&&!automation.recovered.has(source)){
   automation.recovered.add(source);
   if(await recoverExtraction(true))return;
  }
  if(!automationMatch(key,generation)||hasDraft())return;
  await runAutomaticRecovery(()=>automationMatch(key,generation)&&!hasDraft());
  if(!automationMatch(key,generation)||hasDraft())return;
  autoStatus.textContent='Đang tải kết quả hoặc kiểm tra bản đã lưu; không tự chấp nhận dữ liệu…';
  await loadCurrentEvaluation();if(!automationMatch(key,generation)||hasDraft())return;
  if(!compliance.current?.report)await evaluateRecord();
  if(!automationMatch(key,generation)||hasDraft())return;
  if(compliance.current?.report){
   await loadExplanation(compliance.current);
   if(!automationMatch(key,generation)||hasDraft())return;
   // Existing explanation belongs to this pinned evaluation; do not call the model again.
   if(!explanationView.cacheValid){autoStatus.textContent='Đã có kết quả. Đang chuẩn bị diễn giải; bạn vẫn có thể xem dữ liệu.';await generateExplanation();}
   if(automationMatch(key,generation))autoStatus.textContent='Đã xử lý bản đã lưu. Xem phạm vi thuế, phần cần review và diễn giải; chưa tự xác nhận hợp lệ.';
  }else autoStatus.textContent='Chưa hoàn tất kiểm tra. Xem trạng thái ở bước Kiểm tra thuế.';
 }catch(error){if(automationMatch(key,generation))autoStatus.textContent='Đã dừng tự chạy: '+error.message;throw error;}
 finally{automation.running.delete(key);autoRetry.disabled=automation.running.size>0;}
}
autoInput.addEventListener('change',()=>{if(autoInput.checked)perform(()=>runAutomation());else{automation.generation++;autoStatus.textContent='Đã tắt tự chạy. Tác vụ đã gửi lên server có thể vẫn hoàn tất, nhưng chuỗi không tiếp tục.';}});
document.addEventListener('agent3:record-opened',()=>{automation.generation++;});
document.addEventListener('agent3:record-loading',()=>{recoverButton.disabled=true;autoRetry.disabled=true;autoInput.disabled=true;document.querySelector('.data-pane').inert=true;});
document.addEventListener('agent3:record-load-finished',()=>{recoverButton.disabled=automation.recovering;autoRetry.disabled=automation.running.size>0;autoInput.disabled=false;document.querySelector('.data-pane').inert=false;});
document.addEventListener('agent3:record-ready',event=>{if(event.detail?.record_id===state.view?.record.record_id&&event.detail.revision===state.view.record.revision)perform(()=>runAutomation());});
