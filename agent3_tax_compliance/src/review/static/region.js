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
