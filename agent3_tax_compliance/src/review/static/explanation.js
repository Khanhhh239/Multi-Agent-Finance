'use strict';
const explanationView = {generation:0, evaluation:null, busy:false, key:null};
function clearExplanation(view=null){
 explanationView.generation++;explanationView.evaluation=view;explanationView.busy=false;explanationView.key=null;
 $('explanation-detail').hidden=!view?.report;$('generate-explanation').disabled=!view?.report;
 $('explanation-status').textContent='Có thể xem diễn giải và nguồn của bản kết quả đã lưu.';
 $('explanation-claims').replaceChildren();$('explanation-sources').replaceChildren();
}
function renderExplanation(item){
 const reasons={LLM_DISABLED:'Model chưa được bật',MODEL_REVISION_UNPINNED:'Model chưa được khóa phiên bản',
 LEGAL_BASIS_NOT_REVIEWED:'Căn cứ pháp lý còn chờ đối chiếu',LEGAL_EXCERPT_UNAVAILABLE:'Chưa có trích đoạn pháp lý đã duyệt',
 CORPUS_VERSION_MISMATCH:'Kho pháp lý chưa khớp phiên bản đánh giá',NO_SELECTED_LEGAL_BASIS:'Chưa chọn được căn cứ pháp lý',
 MISSING_LEGAL_DATE:'Chưa xác nhận ngày áp dụng',CONTEXT_BUDGET:'Nội dung vượt giới hạn xử lý',
 PROVIDER_UNAVAILABLE:'Không kết nối được model; kiểm tra Ollama và thử lại',CLAIM_VALIDATION_FAILED:'Nội dung model không qua kiểm tra',
 PROVIDER_TIMEOUT:'Model phản hồi quá thời gian chờ; thử lại khi model đã tải xong',
 MODEL_REVISION_MISMATCH:'Model đã cài khác phiên bản được cấu hình',MODEL_MANIFEST_UNAVAILABLE:'Không đọc được phiên bản model từ Ollama',
 PROVIDER_HTTP_ERROR:'Ollama trả lỗi khi tạo diễn giải',PROVIDER_INVALID_RESPONSE:'Model trả dữ liệu không đúng định dạng',
 OUTPUT_TRUNCATED:'Phản hồi model vượt giới hạn độ dài',RESPONSE_BUDGET:'Phản hồi model vượt giới hạn dữ liệu',
 MODEL_OR_COMPLETION_MISMATCH:'Model chưa hoàn tất phản hồi hoặc không khớp cấu hình',
 LOCAL_ENDPOINT_REQUIRED:'Cấu hình model cần dùng địa chỉ local được hỗ trợ',PROVIDER_FAILURE:'Model gặp lỗi xử lý; có thể thử lại'};
 $('explanation-status').textContent=(item.mode==='LLM_VALIDATED'?'Diễn giải có model hỗ trợ, đã kiểm tra từng phát biểu.':'Diễn giải bằng mẫu: '+(reasons[item.fallback_reason]||'Model chưa đáp ứng điều kiện xử lý')+'.')+' Thuộc bản dữ liệu '+item.record_revision+'.';
 $('explanation-claims').replaceChildren(...item.claims.map(claim=>{const li=element('li');li.append(element('p',claim.text));const details=element('details');details.append(element('summary','Tham chiếu nguồn'),element('small',claim.refs.join(' · ')));li.append(details);return li;}));
 $('explanation-sources').replaceChildren(...item.excerpts.map(c=>element('p',c.document_id+' · '+c.locator+' · '+c.chunk_id)));
}
async function loadExplanation(view){
 clearExplanation(view);if(!view?.report)return;
 const generation=explanationView.generation;
 const data=await api('/v1/evaluations/'+view.evaluation_id+'/explanations');
 if(generation!==explanationView.generation||compliance.current?.evaluation_id!==view.evaluation_id)return;
 if(data.explanation)renderExplanation(data.explanation);
}
async function generateExplanation(){
 const view=explanationView.evaluation;
 if(!view?.report||explanationView.busy)return;
 if(state.saving||snapshotDraft().length||$('items-complete').checked)throw new Error('Lưu hoặc bỏ bản nháp trước khi xem giải thích cho bản đã lưu.');
 const generation=explanationView.generation;explanationView.busy=true;$('generate-explanation').disabled=true;
 $('explanation-status').textContent='Đang chuẩn bị diễn giải và kiểm tra nguồn…';
 explanationView.key=explanationView.key||crypto.randomUUID();
 try{const item=await api('/v1/evaluations/'+view.evaluation_id+'/explanations',{method:'POST',headers:{'Idempotency-Key':explanationView.key},body:{expected_record_revision:view.record_revision}});
  if(generation!==explanationView.generation||compliance.current?.evaluation_id!==view.evaluation_id)return;
  renderExplanation(item);explanationView.key=null;
 }catch(error){if(generation===explanationView.generation)$('explanation-status').textContent='Chưa tải được diễn giải bổ sung. Kết quả và giải thích gốc phía trên vẫn dùng được.';throw error;
 }finally{if(generation===explanationView.generation){explanationView.busy=false;$('generate-explanation').disabled=false;}}
}
document.addEventListener('agent3:record-opened',()=>clearExplanation());
document.addEventListener('agent3:evaluation-opened',event=>perform(()=>loadExplanation(event.detail)));
$('generate-explanation').addEventListener('click',()=>perform(generateExplanation));
