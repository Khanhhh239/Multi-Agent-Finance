'use strict';
// Structural edits are saved separately; existing field drafts must be resolved first.
const itemEditor={generation:0,box:null,page:null,picking:false,busy:false,itemId:null,pending:null};
const itemDialog=element('dialog');itemDialog.id='item-dialog';
const itemForm=element('form');const itemTitle=element('h2','Bổ sung dòng hàng bị bỏ sót');
itemForm.append(itemTitle,element('p','Nhập đúng nội dung được in. Chọn vùng dòng hàng trên hóa đơn gốc để lưu nguồn đối chiếu.','muted'));
const itemInputs={};
for(const name of ['description','quantity','unit_price','net','vat_treatment','vat_rate']){
 const label=element('label',labels[name]);let input;
 if(name==='vat_treatment'){input=element('select');for(const [value,text] of [['','Chưa xác định'],['TAXABLE_RATE','Theo thuế suất'],['KCT','Không chịu thuế'],['KKKNT','Không kê khai, nộp thuế']]){const opt=element('option',text);opt.value=value;input.append(opt);}}
 else input=element(name==='description'?'textarea':'input');
 input.id='new-item-'+name;input.setAttribute('aria-label','Dòng mới · '+labels[name]);input.required=name==='description';
 if(['quantity','unit_price','net','vat_rate'].includes(name))input.inputMode='decimal';
 label.append(input);itemForm.append(label);itemInputs[name]=input;
}
const itemRegion=element('p','Chưa chọn vùng nguồn.');itemRegion.id='item-region';
const chooseItemRegion=button('Chọn vùng trên hóa đơn',()=>{itemDialog.close();itemEditor.picking=true;$('page-frame').classList.add('picking-row');mobileTab('source');message('Kéo chuột bao quanh đúng một dòng hàng trên hóa đơn.');});
const itemReasonLabel=element('label','Căn cứ đối chiếu');const itemReason=element('textarea');itemReason.id='item-reason';itemReason.required=true;itemReason.maxLength=2000;itemReasonLabel.append(itemReason);
const itemError=element('p','','field-error');itemError.id='item-error';itemError.setAttribute('role','alert');
const itemSave=element('button','Lưu dòng bổ sung','primary');itemSave.type='submit';itemSave.id='save-new-item';
itemForm.append(itemRegion,chooseItemRegion,itemReasonLabel,itemError,button('Hủy',()=>itemDialog.close()),itemSave);itemDialog.append(itemForm);document.body.append(itemDialog);
function itemHasDraft(){return itemEditor.picking||itemDialog.open&&Object.values(itemInputs).some(i=>i.value.trim());}
function itemCanStart(){if(!state.view||state.loadingRecord||state.saving||itemEditor.busy)throw new Error('Chờ xử lý hiện tại hoàn tất.');if(snapshotDraft().length||state.conflictDraft.length||$('items-complete').checked||(typeof businessHasDraft==='function'&&businessHasDraft()))throw new Error('Lưu hoặc bỏ bản nháp trước khi thay đổi dòng hàng.');if(!state.task)throw new Error('Chọn việc cần kiểm tra trước khi sửa dòng hàng.');}
function addItem(){itemCanStart();itemEditor.generation++;itemEditor.box=null;itemEditor.page=null;itemEditor.itemId='manual-'+crypto.randomUUID();itemEditor.pending=null;for(const input of Object.values(itemInputs))input.value='';itemInputs.vat_rate.disabled=false;itemReason.value='Đối chiếu dòng bị bỏ sót trên hóa đơn gốc';itemRegion.textContent='Chưa chọn vùng nguồn.';itemError.textContent='';itemDialog.showModal();}
itemInputs.vat_treatment.addEventListener('change',()=>{const exempt=['KCT','KKKNT'].includes(itemInputs.vat_treatment.value);itemInputs.vat_rate.disabled=exempt;if(exempt)itemInputs.vat_rate.value='';});
async function saveItemOperations(ops,reason){
 itemCanStart();const rid=state.view.record.record_id,revision=state.view.record.revision,generation=itemEditor.generation;
 const command={record_id:rid,expected_revision:revision,task_id:state.task.task_id,reason,item_operations:ops};
 const signature=JSON.stringify(command);
 if(itemEditor.pending?.signature!==signature)itemEditor.pending={signature,key:crypto.randomUUID()};
 const key=itemEditor.pending.key;
 state.saving=true;itemEditor.busy=true;itemSave.disabled=true;
 try{await api('/v1/corrections',{method:'POST',body:command,headers:{'Idempotency-Key':key}});itemEditor.pending=null;itemDialog.close();await openRecord(rid,{force:true});message('Đã lưu thay đổi dòng hàng và tính lại dữ liệu. Cần đối chiếu lại đủ dòng/trang.');}
 catch(error){if(generation===itemEditor.generation)itemError.textContent=error.status===409?'Bản dữ liệu đã đổi. Nội dung nhập vẫn được giữ; đóng cửa sổ và tải lại hóa đơn trước khi thử lại.':error.message;throw error;}
 finally{state.saving=false;itemEditor.busy=false;itemSave.disabled=false;}
}
itemForm.addEventListener('submit',event=>{event.preventDefault();perform(async()=>{
 if(!itemEditor.box||itemEditor.page===null)throw new Error('Chọn vùng dòng hàng trên hóa đơn trước khi lưu.');
 const values={};for(const [name,input] of Object.entries(itemInputs))if(!input.disabled&&input.value.trim())values[name]=canonicalValue('items.manual.'+name,input.value);
 await saveItemOperations([{operation:'ADD',item_id:itemEditor.itemId,page_index:itemEditor.page,bbox:itemEditor.box,values}],itemReason.value.trim());
});});
function deleteItem(item){itemCanStart();askReason('Xóa dòng '+item.line_number+' khỏi bản dữ liệu (bản gốc và lịch sử vẫn được giữ)',reason=>saveItemOperations([{operation:'DELETE',item_id:item.item_id}],reason));}
let rowStart=null;
function rowPoint(event){const rect=$('page-image').getBoundingClientRect();return [Math.max(0,Math.min(1,(event.clientX-rect.left)/rect.width)),Math.max(0,Math.min(1,(event.clientY-rect.top)/rect.height))];}
$('page-frame').addEventListener('pointerdown',event=>{if(!itemEditor.picking||event.button!==0)return;event.preventDefault();rowStart=rowPoint(event);$('page-frame').setPointerCapture(event.pointerId);});
$('page-frame').addEventListener('pointerup',event=>{if(!itemEditor.picking||!rowStart)return;const end=rowPoint(event);const box=[Math.min(rowStart[0],end[0]),Math.min(rowStart[1],end[1]),Math.max(rowStart[0],end[0]),Math.max(rowStart[1],end[1])];rowStart=null;if(box[2]-box[0]<.01||box[3]-box[1]<.003){message('Vùng quá nhỏ. Kéo lại bao quanh một dòng hàng.',true);return;}itemEditor.box=box;itemEditor.page=Number($('page').value);itemEditor.picking=false;$('page-frame').classList.remove('picking-row');itemRegion.textContent='Đã chọn vùng dòng hàng · Trang '+(itemEditor.page+1);itemDialog.showModal();});
$('page-frame').addEventListener('pointercancel',()=>{rowStart=null;});
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&itemEditor.picking){itemEditor.picking=false;rowStart=null;$('page-frame').classList.remove('picking-row');itemDialog.showModal();}});
document.addEventListener('agent3:record-loading',()=>{itemEditor.generation++;itemEditor.picking=false;rowStart=null;itemDialog.close();$('page-frame').classList.remove('picking-row');});
// Add controls without replacing fields or their draft listeners.
function attachItemControls(){if(!state.view)return;const group=[...$('fields').querySelectorAll('.field-group')].at(-1);if(!group||group.querySelector('#add-item'))return;const add=button('Bổ sung dòng hàng',addItem);add.id='add-item';group.append(add);const rows=group.querySelectorAll('tbody tr');state.view.record.items.forEach((item,i)=>{const cell=rows[i]?.firstElementChild;if(cell){const del=button('Xóa dòng',()=>deleteItem(item));del.setAttribute('aria-label','Xóa dòng '+item.line_number);cell.append(del);}});}
document.addEventListener('agent3:record-ready',attachItemControls);
