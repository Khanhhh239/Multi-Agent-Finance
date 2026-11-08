"use strict";
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const nodes={};
const context=vm.createContext({document:{getElementById:id=>nodes[id]??={classList:{remove(){}},innerHTML:'',disabled:false}}});
new vm.Script(fs.readFileSync('review_ui/review_workflow.js','utf8')).runInContext(context);
const api=context.ReviewWorkflowUI;
const policy={enabled:true,role_labels:{accountant:'Kế toán viên',chief_accountant:'Kế toán trưởng',director:'Giám đốc'},principal:null};
api.policy(policy);assert.match(nodes['review-workflow-status'].innerHTML,/Kế toán viên/);assert.match(nodes['review-workflow-status'].innerHTML,/luồng đăng nhập/);assert.equal(nodes.budget.disabled,true);
const locked=api.content({stage:'pending_review',policy});
assert.match(locked,/sẵn sàng khi có tài khoản/);assert.doesNotMatch(locked,/<button|name="workflow_minutes"/);
const accountant=api.content({stage:'pending_review',policy:{...policy,principal:{role:'accountant',display_name:'A<script>'}}});
assert.match(accountant,/Gửi kết quả để kiểm tra cuối/);assert.doesNotMatch(accountant,/Chốt kết luận<\/button>/);assert.doesNotMatch(accountant,/<script>/);
for(const role of ['chief_accountant','director']){
 const html=api.content({stage:'pending_final',primary:{actor:{display_name:'A'},data:{decision:'false_positive',reason:'Đã đối chiếu',active_minutes:5}},policy:{...policy,principal:{role,display_name:'B'}}});
 assert.match(html,/Chốt kết luận/);assert.match(html,/Trả lại để rà bổ sung/);assert.match(html,/Phút xử lý thực tế/);
 assert.doesNotMatch(html,/name="reviewer"|value="5"/);
}
async function navigation(){
 const {environment}=require('./review_evidence_ui.test.js');
 const path=require('node:path');
 for(const role of [null,'chief_accountant','accountant']){
  const e=environment(path.resolve('review_ui/app.js'));e.context.calls=[];e.context.testRole=role;
  e.eval(`state.meta={review_workflow:{enabled:true,principal:testRole?{role:testRole}:null}};
   renderDetail=()=>{};loadQueue=async()=>{};
   api=async(path,body)=>{calls.push({path,body});return body?{}:{case:{case_id:'RC_1',archived:false}};};`);
  await e.eval('openCase("RC_1")');assert.equal(e.eval('state.selected'),'RC_1');
  assert.equal(e.context.calls.filter(c=>c.path==='/api/admit').length,role==='accountant'?1:0);
 }
 console.log(JSON.stringify({tests:8,failures:0}));
}
navigation().catch(error=>{console.error(error);process.exitCode=1;});
