"use strict";
const {test}=require('node:test');
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const context=vm.createContext({document:{getElementById:()=>null}});
new vm.Script(fs.readFileSync('review_ui/review_workflow.js','utf8')).runInContext(context);
const ui=context.ReviewWorkflowUI;
const policy=role=>({role_labels:{accountant:'Kế toán viên',chief_accountant:'Kế toán trưởng',director:'Giám đốc'},principal:role?{role,display_name:role}:null});
const event=(kind,data={},event_hash=kind)=>({kind,data,event_hash,event_at:'2026-10-27T10:00:00+07:00',actor:{display_name:'Người mô phỏng'}});
const primary=event('primary_submitted',{decision:'false_positive',reason:'Đã rà mẫu',active_minutes:3});
const state=(role='accountant',extra={})=>({stage:'pending_review',policy:policy(role),history:[],latest_event_hash:'read-version',case_scope_hash:'evidence-version',...extra});
function harness(data=state(),values={}){
  const nodes={};
  const node=(value='')=>({value,disabled:false,textContent:'',focused:false,classes:new Set(['hidden']),listeners:{},classList:{remove(name){this.owner.classes.delete(name);}},focus(){this.focused=true;},addEventListener(name,fn){this.listeners[name]=fn;}});
  for(const [key,value] of Object.entries({workflow_action:'primary',workflow_reason:'MÔ PHỎNG: lý do',workflow_minutes:'2',workflow_missing:'',...values}))nodes[`[name="${key}"]`]=node(value);
  nodes['[name="workflow_decision"]:checked']=node(values.decision||'false_positive');
  for(const key of ['.workflow-error','[data-return-review]','[data-workflow-reload]'])nodes[key]=node();
  Object.values(nodes).forEach(n=>n.classList.owner=n);
  const buttons=[node(),node()],listeners={},calls=[],notices=[],saved=[];
  const form={innerHTML:'',querySelector:key=>nodes[key]||null,querySelectorAll:()=>buttons,addEventListener:(name,fn)=>listeners[name]=fn};
  const actions={scenario:'003',caseId:'RC_1',api:async(path,body)=>calls.push({path,body}),notice:message=>notices.push(message),saved:async action=>saved.push(action),reload:()=>calls.push({reload:true})};
  ui.render(form,data,actions);
  return {nodes,buttons,calls,notices,saved,actions,form,submit:()=>listeners.submit({preventDefault(){}}),return:()=>nodes['[data-return-review]'].listeners.click()};
}
test('returned review exposes checker, reason and missing documents safely',()=>{
 const returned=event('returned',{reason:'Cần sao kê <script>',missing_evidence:'Sao kê T1',active_minutes:1});
 const html=ui.content(state('accountant',{stage:'returned',primary,history:[primary,returned]}));
 assert.match(html,/Yêu cầu rà bổ sung/);assert.match(html,/Cần sao kê &lt;script&gt;/);assert.match(html,/Cần bổ sung: Sao kê T1/);assert.doesNotMatch(html,/<script>/);
});
test('pending result is explicit and corrections are collapsed',()=>{
 const html=ui.content(state('accountant',{stage:'pending_final',primary,history:[primary]}));
 assert.match(html,/Đã gửi kết quả/);assert.match(html,/<details class="workflow-edit">/);assert.match(html,/Gửi bản rà cập nhật/);assert.doesNotMatch(html,/<details class="workflow-edit" open/);
});
test('final summary follows committed intent rather than a different later intent',()=>{
 const intent=event('finalization_requested',{decision:'non_compliance',reason:'Kết luận đã lưu',active_minutes:4},'approved');
 const finalized=event('finalized',{intent_hash:'approved'},'done');
 const stray=event('finalization_requested',{reason:'Không dùng nhầm'},'stray');
 const html=ui.content(state('chief_accountant',{stage:'finalized',primary,history:[primary,intent,finalized,stray]}));
 assert.match(html,/Kết luận đã chốt/);assert.match(html,/Vi phạm kiểm soát/);assert.match(html,/Phút xử lý đã ghi: 4/);
 assert.match(html,/workflow-finalized[^]*?Kết luận đã lưu/);assert.doesNotMatch(html,/name="workflow_action"/);
});
for(const role of ['accountant','chief_accountant','director',null])test(`finalized result is read only for ${role}`,()=>{
 const html=ui.content(state(role,{stage:'finalized',primary}));assert.doesNotMatch(html,/<button|name="workflow_minutes"/);
});
test('checker waits for resubmission after return',()=>{
 const html=ui.content(state('director',{stage:'returned',primary}));assert.match(html,/Đang chờ kế toán viên bổ sung/);assert.doesNotMatch(html,/Chốt kết luận<\/button>/);
});
test('failed finalization retains its reason and handling minutes in history',()=>{
 const intent=event('finalization_requested',{reason:'Thiếu sao kê',active_minutes:2},'attempt');
 const failed=event('finalization_failed',{intent_hash:'attempt'});
 const html=ui.content(state('director',{stage:'pending_final',primary,history:[primary,intent,failed]}));
 assert.match(html,/Chốt chưa thành công/);assert.match(html,/Thiếu sao kê/);assert.match(html,/Phút xử lý đã ghi: 2/);assert.match(html,/Lịch sử duyệt · 2 bước/);
});
test('open document requests are visible before a final decision',()=>{
 const html=ui.content(state('director',{stage:'pending_final',primary,active_request_count:1}));
 assert.match(html,/Còn 1 yêu cầu tài liệu chưa rà xong/);assert.match(html,/Bổ sung tài liệu/);
});
test('approved information gap stays open for accountant rereview',()=>{
 const intent=event('finalization_requested',{decision:'information_gap',reason:'Chưa đủ',missing_evidence:'Sổ gốc'},'gap');
 const finalized=event('finalized',{intent_hash:'gap'});
 const data={stage:'finalized',primary,history:[primary,intent,finalized]};
 const html=ui.content(state('accountant',data));assert.match(html,/Đã kiểm tra · chờ bổ sung bằng chứng/);assert.match(html,/name="workflow_action"/);assert.match(html,/Gửi kết quả để kiểm tra cuối/);
 const checker=ui.content(state('director',data));assert.doesNotMatch(checker,/name="workflow_action"/);assert.match(checker,/Đang chờ kế toán viên bổ sung/);
});
test('anonymous view has no editing controls',()=>assert.doesNotMatch(ui.content(state(null)),/<button|<textarea|name="workflow_minutes"/));
test('missing evidence decision requires details before API call',async()=>{
 const h=harness(state(),{decision:'information_gap'});await h.submit();assert.equal(h.calls.length,0);assert.match(h.notices[0],/Ghi rõ chứng từ/);assert.equal(h.nodes['.workflow-error'].focused,true);
});
for(const minutes of ['0','-1','1441','NaN'])test(`reject invalid minutes ${minutes} inline`,async()=>{
 const h=harness(state(),{workflow_minutes:minutes});await h.submit();assert.equal(h.calls.length,0);assert.match(h.notices[0],/1.440/);
});
test('return does not accidentally validate a preselected information gap',async()=>{
 const h=harness(state('chief_accountant',{stage:'pending_final',primary}),{workflow_action:'finalize',decision:'information_gap'});await h.return();
 assert.equal(h.calls.length,1);assert.equal(h.calls[0].path,'/api/review-workflow/return');assert.equal(h.calls[0].body.decision,null);assert.deepEqual(h.saved,['return']);
});
test('request carries optimistic concurrency tokens and no client identity',async()=>{
 const h=harness();await h.submit();const body=h.calls[0].body;
 assert.equal(body.expected_event_hash,'read-version');assert.equal(body.expected_scope_hash,'evidence-version');assert.equal(body.timing_method,'measured_stopwatch');assert.equal('actor' in body,false);assert.deepEqual(h.saved,['primary']);
});
test('double click cannot send a duplicate while request is pending',async()=>{
 const h=harness();let release;h.actions.api=()=>new Promise(resolve=>{h.calls.push('request');release=resolve;});
 const first=h.submit();await h.submit();assert.equal(h.calls.length,1);assert.ok(h.buttons.every(b=>b.disabled));release();await first;assert.ok(h.buttons.every(b=>!b.disabled));
});
test('failed/stale request keeps draft and exposes a reload action',async()=>{
 const h=harness();h.actions.api=async()=>{throw Error('Bước rà đã được cập nhật.');};await h.submit();
 assert.equal(h.nodes['[name="workflow_reason"]'].value,'MÔ PHỎNG: lý do');assert.equal(h.nodes['.workflow-error'].focused,true);
 assert.equal(h.nodes['[data-workflow-reload]'].classes.has('hidden'),false);h.nodes['[data-workflow-reload]'].listeners.click();assert.equal(h.calls[0].reload,true);
});
