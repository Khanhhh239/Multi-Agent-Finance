"use strict";
const {test}=require('node:test');
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const context=vm.createContext({});
new vm.Script(fs.readFileSync('review_ui/company_ml.js','utf8')).runInContext(context);
const ui=context.CompanyMLUI;
const algorithms=[{id:'ecod',label:'ECOD'}];
const version=(id,number=1,extra={})=>({version_id:id,number,algorithm:'ecod',data_revision:'current',evaluation_rows:10,
  evaluation_alerts:1,evaluation_alert_rate:.1,labelled_evaluation_rows:0,precision:null,recall:null,seconds:.1,
  calibration_end:'2025-01-01T00:00:00+07:00',...extra});
const data=(versions,extra={})=>({versions,active_version:null,data:{revision:'current'},history:[],...extra});
test('candidate requires an explicit activation action',()=>{
  const html=ui.versionTable(data([version('A')]),algorithms,true);
  assert.match(html,/Ứng viên chưa kích hoạt/);assert.match(html,/Xác nhận dùng v1/);
  assert.doesNotMatch(html,/data-rollback="true"/);
});
test('active model is marked and not offered for replacement by itself',()=>{
  const html=ui.versionTable(data([version('A')],{active_version:'A'}),algorithms,true);
  assert.match(html,/Đang dùng/);assert.doesNotMatch(html,/data-ml-version/);
});
test('unlabelled evaluations do not invent precision or recall',()=>{
  const html=ui.versionTable(data([version('A')]),algorithms,true);
  assert.match(html,/Chưa đủ nhãn/);assert.match(html,/0 dòng có nhãn/);
});
test('old-data candidates are disabled and historical active versions offer rollback',()=>{
  const old=version('A',1,{data_revision:'old'});
  assert.match(ui.versionTable(data([old]),algorithms,true),/disabled/);
  const html=ui.versionTable(data([old],{history:[{action:'activated',details:{version_id:'A'}}]}),algorithms,true);
  assert.match(html,/data-rollback="true"/);assert.match(html,/Quay lại v1/);assert.doesNotMatch(html,/disabled/);
});
test('read-only users cannot activate versions',()=>{
  assert.match(ui.versionTable(data([version('A')]),algorithms,false),/disabled/);
});
test('nonconvergence remains visible for manual review',()=>{
  assert.match(ui.versionTable(data([version('A',1,{converged:false})]),algorithms,true),/Chưa hội tụ/);
});
test('company, version and transaction values are escaped',()=>{
  const html=ui.versionTable(data([version('<img src=x onerror=evil()>')]),[{id:'ecod',label:'<script>bad</script>'}],true);
  assert.doesNotMatch(html,/<img|<script/);assert.match(html,/&lt;script&gt;/);
  const scores=ui.scoreTable({run:{rows:1,flagged:1,number:1},total:1,items:[{transaction_id:'<script>x</script>',posted_at:'2025-01-01',anomaly_score:3,flagged:true}]});
  assert.doesNotMatch(scores,/<script/);assert.match(scores,/Cần đối chiếu/);
});
test('Vietnam time input is independent of the browser timezone',()=>{
  assert.equal(ui.local('2024-01-19T17:00:00Z'),'2024-01-20T00:00');
});
