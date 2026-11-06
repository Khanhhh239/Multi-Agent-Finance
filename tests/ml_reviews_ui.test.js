"use strict";
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const context=vm.createContext({});new vm.Script(fs.readFileSync('review_ui/ml_reviews.js','utf8')).runInContext(context);
const ui=context.MLReviewUI;
test('timer formats active milliseconds as hours minutes seconds without negative display',()=>{
  assert.equal(ui.duration(3661000),'01:01:01');assert.equal(ui.duration(-100),'00:00:00');assert.equal(ui.duration(900),'00:00:00');
});
test('public evidence only renders supported facts and escapes source text',()=>{
  const html=ui.evidenceTable({transaction_id:'00001',business_purpose:'<img src=x onerror=bad>',algorithm:'SECRET_MODEL',anomaly_score:9});
  assert.match(html,/00001/);assert.match(html,/&lt;img/);assert.doesNotMatch(html,/<img|SECRET_MODEL|anomaly_score/);
});
test('incomplete summary shows progress without model names or completed-budget claims',()=>{
  const html=ui.summaryTable({reviewed:1,total:12,total_unique_review_minutes:2,complete:false,reason:'Hoàn tất phiếu <script>',metrics:[{algorithm:'SECRET'}]});
  assert.match(html,/1\/12/);assert.doesNotMatch(html,/SECRET|<script>/);assert.match(html,/&lt;script&gt;/);
});
test('complete summary separates unknown reviews and unique time from per-model time',()=>{
  const html=ui.summaryTable({reviewed:2,total:2,total_unique_review_minutes:3,complete:true,metrics:[{company_id:'C001',algorithm:'ECOD',reviewed:2,selected:2,useful:1,unknown:1,full_budget_review_minutes:3}]});
  assert.match(html,/ECOD/);assert.match(html,/3\.00/);assert.match(html,/Chưa đủ căn cứ/);
});
