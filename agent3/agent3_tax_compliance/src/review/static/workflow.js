'use strict';
// Presentation only: existing forms, handlers and revision guards keep ownership of data.
const workflow = {step:'data'};
const workflowSteps = [
 ['data','Dữ liệu hóa đơn','Đối chiếu và lưu các trường với hóa đơn gốc.'],
 ['business','Hồ sơ bổ sung','Bổ sung căn cứ bạn đã đối chiếu; để trống phần chưa xác nhận.'],
 ['tax','Kiểm tra thuế','Chạy kiểm tra trên bản đã lưu. Luật thực tế còn chờ duyệt.'],
 ['explanation','Diễn giải','Xem giải thích gắn với đúng bản kết quả và nguồn tham chiếu.']
];
function setupWorkflow(){
 const explanationDetail=$('explanation-detail');
 const nav=element('nav',undefined,'workflow-nav');nav.id='workflow-nav';nav.setAttribute('aria-label','Các bước xử lý hóa đơn');
 const heading=element('div',undefined,'workflow-heading');heading.append(element('h2','','workflow-title'),element('p','','muted'));heading.firstChild.id='workflow-title';heading.lastChild.id='workflow-help';
 const scroll=document.querySelector('.data-scroll');const data=element('section');data.id='workflow-data';
 for(const node of [...scroll.children])if(node.id!=='business-panel')data.append(node);
 const business=element('section');business.id='workflow-business';business.append($('business-panel'));
 const tax=element('section');tax.id='workflow-tax';tax.append($('compliance-panel'));
 const explanation=element('section');explanation.id='workflow-explanation';
 const empty=element('div',undefined,'workflow-empty');empty.id='explanation-empty';empty.append(element('h3','Chưa có kết quả để diễn giải'),element('p','Kiểm tra bản đã lưu trước, sau đó quay lại bước này.'),button('Đến kiểm tra thuế',()=>setWorkflowStep('tax')));
 explanation.append(empty,explanationDetail);scroll.replaceChildren(data,business,tax,explanation);
 $('business-panel').open=true;
 for(const [index,[key,title]] of workflowSteps.entries()){
  const b=button('',()=>setWorkflowStep(key),'workflow-step');b.id='step-'+key;b.setAttribute('aria-controls','workflow-'+key);
  b.append(element('span',String(index+1),'step-number'),element('span',title));nav.append(b);
 }
 $('field-summary').before(nav);scroll.before(heading);
 const next=button('Hồ sơ bổ sung →',()=>setWorkflowStep('business'));next.id='workflow-next';document.querySelector('.save-bar .inline').append(next);
 const summary=element('p','','workflow-overview');summary.id='workflow-overview';$('record-summary').after(summary);
 const label=element('label','Tìm chứng từ','sr-only');label.htmlFor='record-search';const search=element('input');search.id='record-search';search.type='search';search.placeholder='Tìm số hóa đơn, người bán…';
 const noResults=element('p','Không tìm thấy trong danh sách đã tải.','muted');noResults.id='record-search-empty';noResults.hidden=true;
 $('records').before(label,search);$('records').after(noResults);
 search.addEventListener('input',filterWorkflowRecords);
 new MutationObserver(filterWorkflowRecords).observe($('records'),{childList:true,subtree:true,characterData:true});
 const upload=$('upload-form');const drawer=element('details',undefined,'upload-drawer');drawer.id='upload-drawer';drawer.append(element('summary','＋ Tải hóa đơn'),upload);document.querySelector('.sidebar .section-title').after(drawer);
 new MutationObserver(updateWorkflowOverview).observe($('dirty-count'),{childList:true,subtree:true});
 new MutationObserver(updateWorkflowOverview).observe($('field-summary'),{childList:true,subtree:true});
 new MutationObserver(updateWorkflowOverview).observe($('compliance-status'),{childList:true,subtree:true});
 new MutationObserver(()=>{$('explanation-empty').hidden=!$('explanation-detail').hidden;}).observe($('explanation-detail'),{attributes:true,attributeFilter:['hidden']});
 // A one-time event delegation expands a row without creating extra data/edit state.
 $('fields').addEventListener('click',event=>{const control=event.target.closest('[data-item-toggle]');if(!control)return;const row=control.closest('tr');const expanded=row.classList.toggle('item-expanded');control.setAttribute('aria-expanded',String(expanded));control.textContent=expanded?'Thu gọn':'Chi tiết';});
 $('audit').addEventListener('click',()=>setWorkflowStep('data'));
 document.addEventListener('click',event=>{const b=event.target.closest('button');if(b&&(b.textContent.startsWith('Xem nguồn')||b.textContent==='Xem vị trí'))mobileTab('source');});
 setWorkflowStep('data');
}
function setWorkflowStep(step){
 if(!workflowSteps.some(s=>s[0]===step))return;
 workflow.step=step;
 for(const [key] of workflowSteps){$('workflow-'+key).hidden=key!==step;const b=$('step-'+key);b.setAttribute('aria-current',key===step?'step':'false');}
 const config=workflowSteps.find(s=>s[0]===step);$('workflow-title').textContent=config[1];$('workflow-help').textContent=config[2];
 document.querySelector('.save-bar').hidden=step!=='data';$('field-summary').hidden=step!=='data';$('field-filter').hidden=step!=='data';
 $('data-title').textContent=config[1];if(step==='business')$('business-panel').open=true;if(step==='explanation')$('explanation-detail').open=true;
 // On small screens a workflow selection always reveals its controls.
 mobileTab('data');document.querySelector('.data-scroll').scrollTop=0;
}
function filterWorkflowRecords(){
 const q=$('record-search').value.trim().normalize('NFC').toLocaleLowerCase('vi');let visible=0;
 for(const row of $('records').querySelectorAll('[data-record]')){row.hidden=!row.textContent.normalize('NFC').toLocaleLowerCase('vi').includes(q);if(!row.hidden)visible++;}
 $('record-search-empty').hidden=!q||visible>0;
}
function updateWorkflowOverview(){
 if(!state.view)return;
 const dirty=snapshotDraft().length||$('items-complete').checked;
 const unconfirmed=[...state.edits.values()].filter(edit=>edit.current?.confidence_basis!=='HUMAN_CONFIRMED').length;
 $('workflow-overview').textContent=dirty?'Có thay đổi chưa lưu · Kết quả kiểm tra chỉ dùng bản đã lưu.':(compliance.current?.report?'Đã có kết quả kiểm tra cho bản này · Xem phạm vi và phần cần review.':unconfirmed?unconfirmed+' trường chưa xác nhận · Đối chiếu dữ liệu trước khi kiểm tra.':'Dữ liệu đã xác nhận · Bước tiếp theo: kiểm tra thuế hoặc bổ sung hồ sơ.');
 $('workflow-overview').classList.toggle('has-draft',Boolean(dirty));
}
document.addEventListener('agent3:record-opened',()=>{setWorkflowStep('data');});
setupWorkflow();
