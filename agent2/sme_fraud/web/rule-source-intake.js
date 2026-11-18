'use strict';
window.RuleSourceIntake=class {
  constructor({change,modeChange}) {
    this.$=id=>document.getElementById(id);this.info=null;this.change=change;
    this.validateHome=this.$('validate').parentElement;this.validateNext=this.$('validate').nextSibling;
    this.$('source-mode').addEventListener('change',()=>{this.reset();this.$('file').value='';this.$('file').multiple=this.enabled;this.$('file').accept=this.enabled?'.csv,.xlsx':'.json,.csv,.xlsx';this.$('native-input').hidden=!this.enabled;this.validateHome.hidden=this.enabled;this.validateHome.nextElementSibling.hidden=this.enabled;if(this.enabled)this.$('native-mapping').append(this.$('validate'));else this.validateHome.insertBefore(this.$('validate'),this.validateNext);modeChange();});
    for(const id of ['native-as-of','native-source-id','native-simulated','native-candidate-mode','native-ids','native-attest'])this.$(id).addEventListener('input',()=>{this.$('native-ids-label').hidden=this.$('native-candidate-mode').value!=='explicit';if(id!=='native-attest')this.$('native-attest').checked=false;change();});
    this.$('native-apply-coverage').addEventListener('click',()=>{for(const card of this.cards().filter(c=>Number(c.dataset.rowCount)>0))for(const [field,id] of [['covered_from','bulk-from'],['observed_at','bulk-known'],['status','bulk-status'],['history_basis','bulk-basis']])card.querySelector('[data-coverage="'+field+'"]').value=this.$(id).value;this.$('native-attest').checked=false;change();});
  }
  get enabled(){return this.$('source-mode').value==='rules';}
  title(table){return ({companies:'Doanh nghiệp',transactions:'Giao dịch',vendors:'Nhà cung cấp',employees:'Nhân viên',customers:'Khách hàng',calendar:'Lịch vận hành',entity_links:'Liên kết đối tượng',attendance:'Chấm công',vendor_status_history:'Lịch sử trạng thái NCC',bank_account_changes:'Thay đổi tài khoản NCC',advances:'Tạm ứng',advance_events:'Lịch sử tạm ứng',payroll_entitlements:'Quyền hưởng lương',supplier_payment_agreements:'Thỏa thuận thanh toán',procurement_links:'Liên kết đơn mua',transaction_documents:'Chứng từ giao dịch',payment_requests:'Yêu cầu chi',operating_schedules:'Lịch làm việc',recurring_payments:'Khoản chi định kỳ',vendor_payment_schedules:'Lịch thanh toán NCC',approval_authorities:'Thẩm quyền phê duyệt',approval_authority_coverage:'Phạm vi thẩm quyền',journal_audit_log:'Nhật ký bút toán',closing_periods:'Lịch khóa sổ',materiality_policies:'Chính sách trọng yếu',leave_periods:'Kỳ nghỉ phép',system_actions:'Nhật ký thao tác',leave_activity_authorizations:'Cho phép thao tác khi nghỉ',employment_events:'Lịch sử nhân sự',payroll_settlements:'Quyết toán lương',workflow_policies:'Chính sách quy trình',override_events:'Thao tác ghi đè',document_series:'Dải số chứng từ',document_register:'Sổ chứng từ',document_cancellations:'Hủy chứng từ',receivable_invoices:'Hóa đơn phải thu',receipt_allocations:'Phân bổ tiền thu',receipt_coverage:'Phạm vi tiền thu',receivable_explanations:'Giải trình công nợ',tax_risk_history:'Lịch sử rủi ro hóa đơn',journal_documents:'Chứng từ kế toán',journal_lines:'Dòng sổ cái',metadata:'Thông tin gói',coverage:'Phạm vi nguồn',candidates:'Giao dịch cần phân tích'})[table]||table;}
  cards(){return [...this.$('native-tables').querySelectorAll('[data-source-key]')];}
  reset(){this.info=null;this.$('native-tables').replaceChildren();this.$('native-mapping').hidden=true;this.$('native-attest').checked=false;for(const id of ['native-as-of','native-source-id','native-simulated','native-ids'])this.$(id).value='';}
  editing(on=true){this.$('native-input').hidden=!on||!this.enabled;}
  buttons(busy,connected,hasFile){this.$('inspect-source').disabled=busy||!connected||!hasFile||!!this.info;this.$('source-mode').disabled=busy;for(const item of this.$('native-mapping').querySelectorAll('input,select,textarea,button'))item.disabled=busy||!connected;}
  async pack(files){
    if(!files.length)throw Error('Chọn các tệp nguồn.');
    if(files.length===1){const f=files[0];if(!/\.(csv|xlsx)$/i.test(f.name))throw Error('Nguồn 35 luật nhận CSV hoặc Excel. JSON snapshot có sẵn dùng chế độ tệp chuẩn.');return {bytes:await f.arrayBuffer(),file:f};}
    if([...files].some(f=>!/\.csv$/i.test(f.name)))throw Error('Chọn một Excel nhiều sheet hoặc một nhóm CSV.');
    const names=new Set(),parts=[];let total=0;
    for(const f of files){if(names.has(f.name))throw Error('Tên CSV bị trùng. Đổi tên từng bảng nguồn.');names.add(f.name);total+=f.size;if(total>10*1024*1024)throw Error('Tổng nguồn vượt 10 MB.');const arr=new Uint8Array(await f.arrayBuffer());let binary='';for(let i=0;i<arr.length;i+=8192)binary+=String.fromCharCode(...arr.subarray(i,i+8192));parts.push({name:f.name,content_b64:btoa(binary)});}
    const bytes=new TextEncoder().encode(JSON.stringify({format:'agent2-source-files/1.0.0',files:parts})).buffer;
    if(bytes.byteLength>10*1024*1024)throw Error('Gói CSV sau đóng gói vượt 10 MB. Dùng Excel nhiều sheet hoặc xuất gói nhỏ hơn mà vẫn đủ lịch sử.');
    return {bytes,file:{name:'agent2-sources.json',size:bytes.byteLength}};
  }
  node(tag,text){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;}
  select(values,current){const n=this.node('select');for(const [value,text] of values){const o=this.node('option',text);o.value=value;n.append(o);}n.value=current;return n;}
  local(value){if(!value)return '';const d=new Date(value);return Number.isNaN(d.getTime())?'':new Date(d.getTime()+7*3600*1000).toISOString().slice(0,19);}
  time(value){return value?value+(value.length===16?':00':'')+'+07:00':'';}
  label(text,element){const n=this.node('label',text);n.append(element);return n;}
  render(info){
    this.info=info;this.$('native-mapping').hidden=false;this.$('native-tables').replaceChildren();
    this.$('native-as-of').value=this.local(info.metadata.as_of);this.$('native-source-id').value=info.metadata.source_id||'';
    this.$('native-simulated').value=info.metadata.is_simulated===true||info.metadata.is_simulated==='true'?'true':info.metadata.is_simulated===false||info.metadata.is_simulated==='false'?'false':'';
    this.$('native-candidate-mode').value=info.candidate_transaction_ids.length?'file':'explicit';this.$('native-ids-label').hidden=!!info.candidate_transaction_ids.length;
    const empty=this.node('details');empty.append(this.node('summary','Bảng chưa có dữ liệu'));const metadata=this.node('details');metadata.append(this.node('summary','Thông tin gói và danh sách ứng viên'));
    for(const source of info.sources){
      const card=this.node('details');card.className='source-card';card.dataset.sourceKey=source.key;card.dataset.rowCount=source.row_count;card.open=!source.suggested_table;card.append(this.node('summary',source.key+' · '+source.row_count+' dòng'+(source.suggested_table?' · '+this.title(source.suggested_table):' · Cần chọn bảng')));
      const table=this.select([['','Chọn bảng nguồn'],...Object.keys(info.fields).map(k=>[k,this.title(k)+' ('+k+')'])],source.suggested_table);table.dataset.table='';card.append(this.label('Bảng đích',table));
      const mapping=this.node('details');mapping.append(this.node('summary','Ánh xạ '+source.headers.length+' cột'));const columns=this.node('div');columns.className='column-mapping';
      for(const header of source.headers){const field=this.node('input');field.value=header;field.dataset.sourceColumn=header;field.setAttribute('list','native-fields-'+info.sources.indexOf(source));columns.append(this.label(header,field));}
      const list=this.node('datalist');list.id='native-fields-'+info.sources.indexOf(source);card.append(list);mapping.append(columns);card.append(mapping);
      const required=this.node('p');required.className='hint';const coverage=this.node('details');coverage.append(this.node('summary','Phạm vi lịch sử của bảng này'));const grid=this.node('div');grid.className='grid';
      const claim=info.coverage[source.suggested_table]||{};
      for(const [field,title] of [['status','Mức đầy đủ'],['history_basis','Loại lịch sử'],['covered_from','Từ thời điểm'],['observed_at','Khai báo phạm vi được biết lúc']]){
        let input;if(field==='status')input=this.select([['unknown','Chưa rõ'],['partial','Một phần'],['complete','Đủ trong phạm vi đã khai báo']],claim[field]||'unknown');else if(field==='history_basis')input=this.select([['unknown','Chưa rõ'],['bounded_period','Một kỳ có giới hạn'],['since_inception','Từ khi bắt đầu phát sinh']],claim[field]||'unknown');else{input=this.node('input');input.type='datetime-local';input.step='1';input.value=this.local(claim[field]);}input.dataset.coverage=field;grid.append(this.label(title,input));
      }
      coverage.append(grid,this.node('p','Phạm vi kết thúc tại mốc phân tích đã chọn. Không khai báo “đủ” nếu chỉ xuất một phần nguồn.'));mapping.append(required);card.append(coverage);
      const refresh=()=>{list.replaceChildren(...(info.fields[table.value]||[]).map(f=>{const o=this.node('option');o.value=f;return o;}));required.textContent=(info.required_fields[table.value]||[]).length?'Cột bắt buộc: '+info.required_fields[table.value].join(', '):'';coverage.hidden=['metadata','coverage','candidates'].includes(table.value);};
      table.addEventListener('change',()=>{refresh();this.$('native-attest').checked=false;this.change();});card.addEventListener('input',()=>{this.$('native-attest').checked=false;this.change();});refresh();if(['metadata','coverage','candidates'].includes(source.suggested_table))metadata.append(card);else if(!source.row_count&&source.suggested_table)empty.append(card);else this.$('native-tables').append(card);
    }
    if(empty.children.length>1)this.$('native-tables').append(empty);if(metadata.children.length>1)this.$('native-tables').append(metadata);
  }
  settings(){
    if(!this.info)throw Error('Bấm Đọc bảng và cột trước khi kiểm tra.');
    const metadata={as_of:this.time(this.$('native-as-of').value),source_id:this.$('native-source-id').value.trim(),is_simulated:this.$('native-simulated').value==='true'};
    if(!metadata.as_of||!metadata.source_id||!this.$('native-simulated').value)throw Error('Điền mốc phân tích, tên nguồn và loại dữ liệu.');
    const settings={profile:'rule_sources',sources:{},tables:{},metadata,coverage:{},date_format:this.$('date-format').value};const used=new Set();
    for(const card of this.cards()){
      const table=card.querySelector('[data-table]').value;if(!table)throw Error('Chọn bảng cho '+card.dataset.sourceKey+'.');if(used.has(table))throw Error('Hai nguồn cùng trỏ bảng '+table+'. Gộp đúng bảng tại nguồn hoặc chọn lại bảng đích.');used.add(table);settings.sources[card.dataset.sourceKey]=table;
      const map=Object.create(null);for(const field of card.querySelectorAll('[data-source-column]')){const target=field.value.trim();if(!target)throw Error('Chọn cột đích cho '+field.dataset.sourceColumn+'.');if(target!==field.dataset.sourceColumn)map[field.dataset.sourceColumn]=target;}if(Object.keys(map).length)settings.tables[table]=map;
      if(['metadata','coverage','candidates'].includes(table))continue;
      const claim={};for(const field of card.querySelectorAll('[data-coverage]'))claim[field.dataset.coverage]=field.type==='datetime-local'?this.time(field.value):field.value;
      if(claim.status==='unknown'&&!claim.covered_from&&!claim.observed_at){settings.coverage[table]=null;continue;}
      if(!claim.covered_from||!claim.observed_at)throw Error('Bảng '+table+': khai báo đủ hai mốc phạm vi hoặc để Chưa rõ.');claim.covered_through=metadata.as_of;settings.coverage[table]=claim;
    }
    if(Object.values(settings.coverage).some(c=>c!==null)&&!this.$('native-attest').checked)throw Error('Xác nhận các phạm vi nguồn đã khai báo trước khi kiểm tra.');
    const mode=this.$('native-candidate-mode').value;
    if(mode==='all')settings.candidate_selection='all';else if(mode==='explicit'){settings.candidate_transaction_ids=this.$('native-ids').value.split(/\r?\n/).map(s=>s.trim()).filter(Boolean);if(!settings.candidate_transaction_ids.length)throw Error('Nhập mã giao dịch cần phân tích, mỗi dòng một mã.');}
    return settings;
  }
  readiness(report){
    const root=this.$('rule-readiness');root.replaceChildren();const r=report.rule_readiness;if(!r)return;
    root.append(this.node('h3','Mức sẵn sàng của 35 kiểm tra'),this.node('p',r.meaning));
    root.append(this.node('p',`${r.summary.ready} đủ để chạy · ${r.summary.partial} chạy một phần · ${r.summary.needs_data} cần bổ sung · ${r.summary.not_applicable} không áp dụng`));
    const titles={ready:'Đủ để chạy',partial:'Chạy một phần',needs_data:'Cần bổ sung',not_applicable:'Không áp dụng'};
    for(const check of r.checks){const box=this.node('details');box.dataset.checkId=check.check_id;box.className='readiness-check '+check.status;box.append(this.node('summary',check.name+' — '+titles[check.status]));box.append(this.node('p',`${check.ready_count} khả dụng · ${check.missing_count} chưa đủ nguồn · ${check.not_applicable_count} không áp dụng`));const ul=this.node('ul');for(const gap of check.gaps)ul.append(this.node('li',(this.title(gap.table)||'Nguồn liên quan')+(gap.field?' · cột '+gap.field:'')+': '+this.reason(gap.reason)));box.append(ul);root.append(box);}
  }
  reason(code){return ({source_not_supplied:'Chưa tải bảng này.',source_coverage_missing:'Chưa khai báo phạm vi nguồn.',source_coverage_incomplete:'Nguồn được khai báo một phần hoặc chưa rõ.',history_before_window_unknown:'Chưa có lịch sử từ khi bắt đầu phát sinh.',statistical_sample_not_evaluable:'Chưa đủ mẫu phù hợp để đánh giá thống kê.',bound_evidence_not_known_at_event:'Chưa có chứng từ ràng buộc đã biết tại thời điểm cần kiểm tra.',signed_amount_policy_not_supported:'Kiểm tra chưa có chính sách áp dụng cho số âm.',signed_history_policy_not_supported:'Chưa có chính sách cho lịch sử thanh toán âm liên quan.',invoice_value_unavailable:'Thiếu giá trị hóa đơn.',recipient_bank_identity_incomplete:'Thiếu mã ngân hàng hoặc định danh tài khoản nhận.',approved_authority_source_missing:'Thiếu nguồn thẩm quyền đã được duyệt.',no_evaluable_receivable_scope:'Chưa có phạm vi công nợ đủ căn cứ để đánh giá.',transaction_not_visible_at_as_of:'Giao dịch chưa được biết hoặc chưa phát sinh tại mốc phân tích.'})[code]||'Cần bổ sung nguồn hoặc xác nhận phạm vi trước khi dùng kiểm tra này.';}
};
