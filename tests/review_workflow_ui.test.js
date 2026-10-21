/* Case-review presentation and submission, using frozen evidence and fake DOM. */
"use strict";
const fs=require("node:fs"),path=require("node:path"),assert=require("node:assert/strict");
const {environment,controlDetails}=require("./review_evidence_ui.test.js");
const ROOT=path.resolve(__dirname,"..");
const packet=id=>JSON.parse(fs.readFileSync(path.join(ROOT,`reports/representative_review_20261018/evidence/${id}.json`),"utf8"));
async function run(){
  const main=environment(path.join(ROOT,"review_ui/app.js")),p2=environment(path.join(ROOT,"review_ui/p2_controls.js"));
  const checks=[],check=async(name,fn)=>{await fn();checks.push(name);};
  const controls=controlDetails(),control=id=>controls.find(r=>r.control_id===id);
  const evaluate=(env,expression,input)=>{env.context.input=input;return env.eval(expression);};
  await check("A1 installment explanation shows actual agreement and source, without exempting P2",()=>{
    const d=control("INSTALL_MIXED"),h=d.hits.find(h=>h.rule_id==="A1"&&h.evidence.installment_check);
    p2.context.hit=h;p2.context.support=d;
    const html=p2.eval("ReviewExplanations.exception(hit,support)");
    for(const text of ["AGR_CONTROL","CONTRACT_CONTROL","SYNTHETIC_AGREEMENT","20.000.000","không tự miễn P2","Nguồn được biết lúc"])assert.ok(html.includes(text),text);
  });
  await check("Recurring A5 explains approval, P99 and expense accrual without treating no P2 as valid",()=>{
    const d=control("RECUR_A5"),h=d.hits.find(h=>h.rule_id==="A5"&&h.evidence.recurring_pattern_id);
    p2.context.hit=h;p2.context.support=d;
    const html=p2.eval("ReviewExplanations.a5(hit.evidence)+ReviewExplanations.exception(hit,support)");
    for(const text of ["PAT_CONTROL","SYNTHETIC_APPROVED_RECURRING","Phân vị 99","Chi phí ghi Nợ","Hằng tháng","không tự miễn P2"])assert.ok(html.includes(text),text);
    const row=d.transactions.at(-1);p2.context.row=row;
    const no=p2.eval("ReviewExplanations.noP2(row,{threshold_vnd:5000000})");
    assert.match(no,/dưới mốc đối chiếu/);assert.match(no,/chưa phải chứng nhận/);assert.equal(h.points,0);
  });
  await check("Small cash installment explains invoice-total threshold",()=>{
    const h=control("INSTALL_CASH").hits.find(h=>h.rule_id==="P2");
    const html=evaluate(p2,"ReviewExplanations.cashSentence(input)",h);
    assert.match(html,/3\.000\.000/);assert.match(html,/12\.000\.000/);assert.match(html,/dù đợt chi hiện tại nhỏ hơn mốc/);
  });
  await check("Unlinked receipts request payer and original evidence; journal returns never clear original",()=>{
    const row=control("RECEIPT_UNLINKED").transactions[0];
    assert.match(evaluate(p2,"ReviewExplanations.noP2(input)",row),/xác định bên nộp/);
    const d=packet("P2_REVERSAL_JOURNAL");d.review_support={transactions:d.transactions,document_links:d.document_links};
    assert.match(evaluate(main,"caseSupportingEvidence(input)",d),/chưa xác nhận nhận tiền thực/);
    assert.match(main.eval("caseSupportingEvidence(input)"),/không được dùng để xóa hit lịch sử/);
  });
  await check("Invoice revisions distinguish first observation, current revision and later update",()=>{
    const invoice={company_id:"SIM_COMPANY",invoice_id:"SIM_INVOICE",currency:"VND"};
    const versions=JSON.parse(fs.readFileSync(path.join(ROOT,"examples/invoice_versions.review_only.json"),"utf8"));
    p2.context.invoice=invoice;p2.context.versions=versions;
    const frozen=JSON.stringify(versions),html=p2.eval('ReviewExplanations.invoiceVersions(invoice,versions,"2025-08-12T11:00:00+07:00")');
    assert.match(html,/Phiên bản đã biết tại lúc chi<\/span>SIM_REV_1/);assert.match(html,/SIM_REV_2 · Được biết sau lúc chi/);
    assert.match(html,/SIM_SOURCE_1/);assert.match(html,/chưa xác nhận hiệu lực/);assert.equal(JSON.stringify(versions),frozen);
    versions[0].company_id="OTHER";
    assert.match(p2.eval('ReviewExplanations.invoiceVersions(invoice,versions,"2025-08-12T11:00:00+07:00")'),/Chưa có phiên bản đã biết/);
    versions[1].observed_at="bad";
    assert.match(p2.eval('ReviewExplanations.invoiceVersions(invoice,versions,"2025-08-12T11:00:00+07:00")'),/thiếu mã hoặc thời điểm/);
    versions[0].company_id="SIM_COMPANY";versions[1].observed_at="2025-08-12T02:00:00Z";
    assert.match(p2.eval('ReviewExplanations.invoiceVersions(invoice,versions,"2025-08-12T11:00:00+07:00")'),/Nhiều phiên bản cùng mốc/);
  });
  await check("Late approval is historical context even if source was observed earlier",()=>{
    const d=control("INSTALL_MIXED"),h=d.hits.find(h=>h.rule_id==="A1"&&h.evidence.installment_check);
    const copy=JSON.parse(JSON.stringify(d));copy.supplier_payment_agreements[0].approved_at="2026-01-01T09:00:00+07:00";
    p2.context.hit=h;p2.context.support=copy;
    assert.match(p2.eval("ReviewExplanations.exception(hit,support)"),/được biết hoặc phê duyệt sau lúc phát hiện/);
  });
  await check("A4 admission and E2 hard trigger explain queue without changing score",()=>{
    const a=packet("A5_003_cold_operational");
    assert.match(evaluate(main,"ReviewExplanations.score(input.case,input.hits)",a),/rà mẫu chia nhỏ/);
    const b=packet("A5_003_TX_60bac87c93f578f6c3");
    assert.match(evaluate(main,"ReviewExplanations.score(input.case,input.hits)",b),/bắt buộc rà: E2/);
    assert.match(main.eval("ReviewExplanations.score(input.case,input.hits)"),/không phải xác suất gian lận/);
    assert.equal(Number(b.case.max_score),23);
  });
  await check("Score decomposition shows source base and recurrence without adding correlated hits",()=>{
    const d=packet("A5_001_TX_3103d5f23fde8b1a6f");
    main.context.input=d;main.context.scores=[{transaction_id:d.transactions[0].transaction_id,rule_score:11,base_score:11,recurrence_points:0}];
    const html=main.eval("ReviewExplanations.score(input.case,input.hits,scores)");
    assert.match(html,/C4: 8/);assert.match(html,/C1: 1/);assert.match(html,/C: 8/);assert.match(html,/Điểm lặp lại theo nguồn<\/span>0/);
  });
  await check("Future invoice warning has no literal template expression",()=>{
    const d=packet("P2_FUTURE_INVOICE");p2.context.input=d;p2.context.row=d.transactions[0];p2.context.hit=d.hits.find(h=>h.rule_id==="P2");
    const html=p2.eval("temporalEvidence(input,row,hit)");assert.doesNotMatch(html,/\$\{/);assert.match(html,/Hóa đơn phát hành sau/);
  });
  const d=packet("A5_003_cold_operational");
  d.feedback_history=[];d.related_feedback_history=[];d.case_lineage=[];
  d.case.review_scope_hash="SIM_SCOPE";d.case.status="awaiting_information";
  d.information_requests={active_count:1,requests:[{request_id:"SIM_REQUEST",event_hash:"SIM_HASH",status:"received",owner:"SIM_OWNER",due_at:"2026-10-21T09:00:00+07:00",created_at:"2026-10-19T09:00:00+07:00",age_hours:0,requested_documents:"Hóa đơn gốc",evidence_refs:["SIM_DOC"],applies_to_current_scope:true,active:true}],history:[{action:"receive",actor:"<img src=bad>",reason:"Đã nhận để rà lại",event_at:"2026-10-19T09:00:00+07:00",request_id:"SIM_REQUEST"}]};
  await check("Main requests tab exposes owner, operational deadline and received-awaiting-review",()=>{
    evaluate(main,'state.detail=input;state.tab="requests";renderDetail()',d);
    const html=main.nodes["detail-content"].innerHTML;
    for(const text of ["SIM_OWNER","SIM_DOC","Đã nhận · chờ rà lại","không lấy ngày giao dịch","chưa đồng nghĩa hợp lệ","Đã rà lại tài liệu"])assert.ok(html.includes(text),text);
    assert.match(main.nodes["detail-panel"].innerHTML,/Bổ sung tài liệu/);assert.match(main.nodes["feedback-form"].innerHTML,/Còn 1 yêu cầu/);
    assert.doesNotMatch(html,/<img/);assert.match(html,/&lt;img/);
  });
  await check("Changed scope and archived requests remain read-only",()=>{
    d.information_requests.requests[0].applies_to_current_scope=false;d.information_requests.requests[0].active=false;d.case.archived=true;
    evaluate(main,'state.detail=input;state.tab="requests";renderTab()',d);
    const html=main.nodes["detail-content"].innerHTML;
    assert.match(html,/Phạm vi đã đổi/);assert.match(html,/SIM_DOC/);assert.doesNotMatch(html,/<form/);
    d.case.archived=false;
  });
  await check("Request submission posts scope and due time separately from risk",async()=>{
    main.context.captured=[];main.context.input=d;
    main.eval('state.detail=input;state.scenario="003";state.selected=input.case.case_id;api=async(path,body)=>{captured.push({path,body});if(!body)return input;return {};};renderDetail=()=>{};loadQueue=async()=>{};notice=()=>{};');
    const values={owner:"SIM_OWNER",due:"2026-10-21T09:00",actor:"SIM_ACTOR",reason:"Yêu cầu đối chiếu",documents:"Hóa đơn gốc"};
    const button={disabled:false},form={dataset:{request:""},elements:{namedItem:n=>({value:values[n]||""})},querySelector:()=>button};
    main.context.form=form;
    await main.eval("saveInformationRequest({preventDefault(){}},form)");
    const body=main.context.captured[0].body;
    assert.equal(body.case_scope_hash,"SIM_SCOPE");assert.equal(body.due_at,"2026-10-21T09:00:00+07:00");assert.equal(body.owner,"SIM_OWNER");
    assert.equal(body.action,"create");assert.equal(body.expected_hash,"");assert.equal(body.rule_score,undefined);assert.equal(button.disabled,false);
  });
  await check("Late detail refresh cannot overwrite another selected case",async()=>{
    main.eval('state.selected=input.case.case_id;state.detail=input;api=async(path,body)=>{if(body)return {};state.selected="OTHER_CASE";return {case:{case_id:"STALE_CASE"}};};');
    await main.eval("saveInformationRequest({preventDefault(){}},form)");
    assert.equal(main.eval("state.detail.case.case_id"),d.case.case_id);assert.equal(main.eval("state.selected"),"OTHER_CASE");
  });
  await check("Notification preview links are clickable while original payload stays separate and escaped",()=>{
    const env=environment(path.join(ROOT,"review_ui/app.js"));
    env.context.job={company_id:'C001',channel:'email',kind:'weekly',status:'simulated',created_at:'2026-10-20T09:00:00+07:00',
      body:'Original http://127.0.0.1:8765/#scenario=001&case=RC_1 <script>bad()</script>',
      preview_body:'Preview http://127.0.0.1:8771/#scenario=001&case=RC_1 <img src=x onerror=bad()>',
      case_links:[{url:'http://127.0.0.1:8771/#scenario=001&case=RC_1'}]};
    const html=env.eval('notificationJob(job)');
    assert.match(html,/<a href="http:\/\/127.0.0.1:8771\/#scenario=001&amp;case=RC_1">/);
    assert.doesNotMatch(html,/<a href="http:\/\/127.0.0.1:8765/);
    assert.match(html,/<details><summary>Nội dung đã mô phỏng trước đây/);
    assert.match(html,/&lt;script&gt;/);assert.match(html,/&lt;img/);assert.doesNotMatch(html,/<script>|<img/);
    env.eval('job.channel="zalo"');assert.match(env.eval('notificationJob(job)'),/Zalo OA/);
  });
  return {successful:true,check_count:checks.length,checks,browser_visual_qa:false};
}
module.exports={run};
if(require.main===module)run().then(result=>console.log(JSON.stringify(result,null,2)));
