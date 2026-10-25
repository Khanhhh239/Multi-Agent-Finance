'use strict';
const captureInsights=element('details');captureInsights.id='capture-insights';
captureInsights.append(element('summary','Chất lượng dữ liệu và thời gian xử lý'));
const insightsBody=element('div');insightsBody.setAttribute('aria-live','polite');
const insightsRefresh=button('Cập nhật số liệu',()=>perform(loadCaptureInsights));
captureInsights.append(insightsBody,insightsRefresh);$('fields').before(captureInsights);
let insightsGeneration=0;
async function loadCaptureInsights(){
 if(!state.view||state.loadingRecord)return;const generation=++insightsGeneration,record=state.view.record;
 insightsRefresh.disabled=true;
 try{const data=await api('/v1/records/'+record.record_id+'/capture-insights');
  if(generation!==insightsGeneration||state.view?.record.record_id!==record.record_id||state.view.record.revision!==data.record_revision)return;
  insightsBody.replaceChildren(element('p','Bản '+data.record_revision+' · '+data.item_count+' dòng hàng · '+data.present+' trường có giá trị · '+data.missing+' thiếu · '+data.ambiguous+' cần đối chiếu.'),
   element('p',data.human_confirmed+' trường được người dùng xác nhận · '+data.review_saves+' lần lưu đối chiếu.'),element('p','Các số đếm này không phải độ chính xác OCR; chưa có nhãn kiểm thử độc lập.','muted'));
  const names={review_save:'Lưu đối chiếu',region_ocr:'Đọc lại vùng',automatic_recovery:'Phục hồi tự động',explanation:'Diễn giải',tax_check:'Kiểm tra thuế',upload:'Tải lên'};
  for(const row of data.timings)insightsBody.append(element('p',(names[row.stage]||'Xử lý')+' · '+row.count+' lượt · trung vị '+row.p50_seconds.toFixed(2)+' giây · p95 '+row.p95_seconds.toFixed(2)+' giây.'));
  insightsBody.append(element('small','Thời gian HTTP của đơn vị đang chọn, gồm tối đa 1.000 lượt thành công; không phải thời gian OCR toàn bộ hoặc SLA.'));
 }catch(error){if(generation===insightsGeneration)insightsBody.textContent='Chưa tải được số liệu. Dữ liệu hóa đơn vẫn được giữ.';throw error;}
 finally{insightsRefresh.disabled=false;}
}
document.addEventListener('agent3:record-loading',()=>{insightsGeneration++;insightsBody.replaceChildren();});
document.addEventListener('agent3:record-ready',()=>perform(loadCaptureInsights));
