/* Evidence, P2 timing and refund regressions; frozen payloads, no scoring. */
"use strict";
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const ROOT = path.resolve(__dirname, "..");
const read = file => JSON.parse(fs.readFileSync(path.join(ROOT, file), "utf8").replace(/^\uFEFF/, ""));
const packet = id => read(`reports/representative_review_20261018/evidence/${id}.json`);
function environment(file) {
  const nodes = {},listeners={},historyWrites=[];
  const node = () => ({innerHTML:"",textContent:"",value:"",className:"",handlers:{},addEventListener(name,fn){this.handlers[name]=fn;},setAttribute(){},
    classList:{toggle(){}},querySelectorAll(){return[];},insertAdjacentHTML(where,html){this.innerHTML=html+this.innerHTML;}});
  const location={hash:"",pathname:file.endsWith("p2_controls.js")?"/p2-controls":"/",search:""};
  const writeHistory=(method,url)=>{historyWrites.push({method,url:String(url)});const hash=String(url).split("#")[1];location.hash=hash?"#"+hash:"";};
  const context = vm.createContext({document:{getElementById:id=>nodes[id]??=node(),querySelectorAll:()=>[]},
    window:{location,innerWidth:1200,history:{pushState:(a,b,url)=>writeHistory("push",url),replaceState:(a,b,url)=>writeHistory("replace",url)},
      addEventListener:(name,fn)=>(listeners[name]??=[]).push(fn)},localStorage:{getItem:()=>"",setItem(){}},Intl,Date,URLSearchParams,
    setTimeout(){},clearTimeout(){},CaseGraph:{dispose(){}}});
  new vm.Script(fs.readFileSync(path.join(ROOT,"review_ui/review_explanations.js"),"utf8")).runInContext(context);
  new vm.Script(fs.readFileSync(file,"utf8").replace(/\bboot\(\);\s*$/, ""),{filename:file}).runInContext(context);
  return {context,nodes,historyWrites,emit:async name=>{await Promise.all((listeners[name]||[]).map(fn=>fn()));},eval:code=>vm.runInContext(code,context)};
}
function controlDetails() {
  const frozen=path.join(__dirname,"fixtures/p2_controls_renderer.json");
  if(fs.existsSync(frozen)){
    const fixture=JSON.parse(fs.readFileSync(frozen,"utf8"));
    assert.equal(fixture.format,"sme-review-renderer-fixture-v1");
    return fixture.controls;
  }
  const source="data/p2_controls_20261018_v2",report="reports/p2_controls_20261018";
  const expected=read(`${source}/expected_outcomes.json`);
  return read(`${source}/control_index.json`).map(item=>{
    const t=read(`${source}/${item.control_id}/tables.json`);
    return {...item,group_label:item.group,transactions:t.transactions,hits:read(`${report}/${item.control_id}/rule_hits.json`),
      cases:read(`${report}/${item.control_id}/case_queue.json`),config:read(`${report}/${item.control_id}/rule_config.json`),documents:t.journal_documents,lines:t.journal_lines,
      invoices:t.invoices||[],invoice_versions:t.invoice_versions||[],document_links:t.document_links||[],recurring_payments:t.recurring_payments||[],
      supplier_payment_agreements:t.supplier_payment_agreements||[],transaction_documents:t.transaction_documents||[],payment_requests:t.payment_requests||[],
      comparisons:read(`${report}/${item.control_id}/predictions.json`).map(actual=>({actual,transaction_id:actual.transaction_id,
        expected:expected.find(e=>e.control_id===item.control_id&&e.transaction_id===actual.transaction_id),differences:{}})),
      matched:true,snapshot_id:"renderer-regression-only",history:[],review:null};
  });
}
function run() {
  const main=environment(path.join(ROOT,"review_ui/app.js")),p2=environment(path.join(ROOT,"review_ui/p2_controls.js"));
  const checks=[];
  const check=(name,fn)=>{fn();checks.push(name);};
  function card(id,rule){const p=packet(id);main.context.input=p;main.context.hit=p.hits.find(h=>h.rule_id===rule);main.eval("state.detail=input");return main.eval("evidenceCard(hit,true)");}
  check("A4 real null window renders calendar month and count",()=>{
    const html=card("A5_003_cold_operational","A4");
    assert.match(html,/2024-01/);assert.match(html,/Số lần<\/span>3/);assert.doesNotMatch(html,/null|undefined|Cửa sổ \(ngày\)/);
  });
  check("Null numeric facts are missing, zero is still a value",()=>{
    assert.equal(main.eval('factValue("amount_vnd",null)'),"Chưa có thông tin");
    assert.equal(main.eval('factValue("window_days",null)'),"Chưa có thông tin");
    assert.match(main.eval('factValue("amount_vnd",0)'),/^0/);
  });
  check("C4 exposes both real actions, leave windows and source references",()=>{
    for(const id of ["A5_001_TX_3103d5f23fde8b1a6f","A5_001_cold_operational"]){
      const p=packet(id),v=p.hits.find(h=>h.rule_id==="C4").evidence.violations[0],html=card(id,"C4");
      for(const value of [v.action.employee_id,v.action.action_id,v.leave.leave_id,v.leave.evidence_id])assert.ok(html.includes(value),value);
      main.context.leave=v.leave;
      assert.ok(html.includes(main.eval("datetime(leave.starts_at)")));assert.ok(html.includes(main.eval("datetime(leave.ends_at)")));
      assert.match(html,/Chưa thấy quyền làm việc/);assert.match(html,/Nguồn được biết lúc/);
    }
  });
  check("Authorized leave action displays the permission, without false missing warning",()=>{
    const p=packet("A5_001_TX_3103d5f23fde8b1a6f"),v=p.hits.find(h=>h.rule_id==="C4").evidence.violations[0];
    v.authorizations=[{authorization_id:"AUTH_TEST",action:"maker",status:"approved",starts_at:v.leave.starts_at,ends_at:v.leave.ends_at}];
    main.context.proof={violations:[],authorized_actions:[v]};const html=main.eval("leaveEvidence(proof)");
    assert.match(html,/AUTH_TEST/);assert.doesNotMatch(html,/Chưa thấy quyền làm việc/);
  });
  check("E2 exposes termination, regular salary, service period and both sources",()=>{
    const html=card("A5_003_TX_60bac87c93f578f6c3","E2");
    for(const value of ["E0000388","6/9/2025","7/9/2025","26/10/2025","Lương thường kỳ","EMP_592a14be853d88d550","PAY_4e5488e51fba4e35b6"])assert.ok(html.includes(value),value);
  });
  check("E2 missing settlement stays explicitly unevaluable",()=>{
    main.context.proof={employment_event:null,settlement:null,evidence_status:"information_gap"};
    const html=main.eval("employmentEvidence(proof)");assert.match(html,/Chưa đủ bằng chứng/);assert.doesNotMatch(html,/undefined|null|Nguồn ghi nhận lương thường kỳ/);
  });
  check("F1 exposes audit, closing, policy references, observations and rounded days",()=>{
    const html=card("A5_001_TX_ac2d5e5d289dc9227b","F1");
    for(const value of ["AUD_37c5b8d37a9d83b4a3","CLOSE_4e3e579f42934ef64e","MAT_79219e8e57f93abe93","3,64 ngày","Nhập thủ công","Nguồn được biết lúc"])assert.ok(html.includes(value),value);
    assert.doesNotMatch(html,/3,6382|undefined|null/);
  });
  check("Legacy evidence and missing F1 source keep their uncertainty",()=>{
    main.context.input={hits:[]};main.eval("state.detail=input");
    main.context.hit={rule_id:"C4",rule_name:"Legacy",points:0,related_transaction_ids:[],evidence:{employee_id:"OLD_EMP"}};
    assert.match(main.eval("evidenceCard(hit,true)"),/OLD_EMP/);
    main.context.proof={days_before_close:2,amount_vnd:1000,source_records:[]};
    assert.match(main.eval("closingEvidence(proof)"),/Chưa thấy bộ nguồn xác nhận/);
  });
  check("Stored source values are HTML escaped",()=>{
    main.context.proof={employment_event:{employee_id:'<img src=x onerror=bad()>',event_type:'<script>bad()</script>'},settlement:null,evidence_status:"information_gap"};
    const html=main.eval("employmentEvidence(proof)");assert.doesNotMatch(html,/<img|<script/);assert.match(html,/&lt;img/);
  });
  check("Foreign ledger and transaction consistently avoid claiming verified VND or original USD amount",()=>{
    const d=packet("P2_LIMIT_FOREIGN");p2.context.input=d;p2.eval('state.detail=input;state.transaction=input.transactions[0].transaction_id;state.tab="documents";renderTab()');
    const html=p2.nodes["uat-content"].innerHTML;
    assert.match(html,/Chưa xác minh quy đổi VND/);assert.match(html,/Nợ \(số nguồn, chưa xác minh VND\)/);
    assert.doesNotMatch(html,/Nợ \(VND\)|₫/);assert.match(html,/5\.000\.000/);
    p2.eval('state.tab="transactions";renderTab()');
    const tx=p2.nodes["uat-content"].innerHTML;assert.match(tx,/Nguồn ghi USD; chưa xác minh giá trị VND/);assert.doesNotMatch(tx,/5\.000\.000 USD/);
    main.context.proof=d.hits.find(h=>h.rule_id==="P2").evidence;assert.match(main.eval("cashEvidence(proof)"),/Nguồn ghi USD; chưa xác minh giá trị VND/);
  });
  check("Currency annotations stay bound to company, document and invoice",()=>{
    const d=packet("P2_LIMIT_FOREIGN");d.transactions.push({company_id:"OTHER",currency:"VND",transaction_id:"OTHER",journal_document_id:"OTHER_DOC"});
    p2.context.input=d;p2.context.record={company_id:"OTHER",document_id:"JD000000001"};assert.equal(p2.eval("foreignRows(input,record).length"),0);
    p2.context.record={company_id:"C001",invoice_id:"UNRELATED_INVOICE"};assert.equal(p2.eval("foreignRows(input,record).length"),0);
    d.transactions[0].invoice_id="FX_INVOICE";d.invoices=[{company_id:"C001",invoice_id:"FX_INVOICE",gross_amount_vnd:1234}];
    assert.match(p2.eval("documentsTab(input)"),/Giá trị hóa đơn theo nguồn · chưa xác minh VND/);
    d.transactions[0].currency='<img src=x>';assert.doesNotMatch(p2.eval("documentsTab(input)"),/<img/);
  });
  function p2Packet(id){const d=packet(id);p2.context.input=d;p2.context.row=d.transactions[0];p2.context.hit=d.hits.find(h=>h.rule_id==="P2");return d;}
  function controlPacket(id){
    const d=controlDetails().find(item=>item.control_id===id);
    assert.ok(d,`Missing committed control ${id}`);
    p2.context.input=d;p2.context.row=d.transactions[0];p2.context.hit=d.hits.find(h=>h.rule_id==="P2");return d;
  }
  check("NO_GROSS missing invoice total agrees between transaction and document tabs",()=>{
    const d=controlPacket("NO_GROSS"),before=JSON.stringify(d);
    assert.match(p2.eval("cashEvidence(hit)"),/Giá trị hóa đơn<\/span>Chưa có thông tin/);
    assert.match(p2.eval("documentsTab(input)"),/Giá trị hóa đơn<\/span>Chưa có thông tin/);
    assert.equal(JSON.stringify(d),before,"Presentation must not change frozen evidence");
    assert.equal(d.hits.find(h=>h.rule_id==="P2").points,0);
  });
  check("Absent invoice totals stay missing, while ledger and refund zero remain values",()=>{
    for(const value of [null,undefined,"",0,"0"]){
      const d=controlPacket("NO_GROSS");d.invoices[0].gross_amount_vnd=value;
      delete d.invoices[0].gross_vnd;delete d.invoices[0].invoice_gross_vnd;
      p2.context.hit.evidence.invoice_gross_vnd=value;
      assert.match(p2.eval("cashEvidence(hit)"),/Giá trị hóa đơn<\/span>Chưa có thông tin/);
      assert.match(p2.eval("documentsTab(input)"),/Giá trị hóa đơn<\/span>Chưa có thông tin/);
      d.transactions[0].currency="USD";
      assert.match(p2.eval("documentsTab(input)"),/Giá trị hóa đơn theo nguồn · chưa xác minh VND<\/span>Chưa có thông tin/);
    }
    assert.equal(p2.eval("money(0)"),"0 ₫");
    controlPacket("REFUND_FULL");assert.match(p2.eval("refundSummary(input)"),/Chênh lệch chi trừ hoàn theo nguồn<\/span>0 ₫/);
    controlPacket("FULL_EQUAL");assert.match(p2.eval("documentsTab(input)"),/Giá trị hóa đơn<\/span>5\.000\.000 ₫/);
  });
  check("No-P2 explanation does not compare an unknown invoice total to the threshold",()=>{
    const d=controlPacket("RECUR_A5"),before=JSON.stringify(d);
    p2.context.policy={threshold_vnd:5000000};
    for(const value of [null,undefined,"",0,"0"]){
      p2.context.row={...d.transactions[0],invoice_gross_vnd:value};
      const html=p2.eval("ReviewExplanations.noP2(row,policy)");
      assert.match(html,/Chưa có thông tin/);
      assert.doesNotMatch(html,/tổng hóa đơn đang có 0 ₫|và tổng hóa đơn.*dưới mốc/);
      assert.match(html,/Không có P2 chưa phải chứng nhận nghiệp vụ hợp lệ/);
    }
    assert.equal(JSON.stringify(d),before,"Presentation must not change baseline transactions");
  });
  check("Future invoice is explicitly excluded at payment time in both tabs",()=>{
    const d=p2Packet("P2_FUTURE_INVOICE"),html=p2.eval("temporalEvidence(input,row,hit)");
    assert.match(html,/11:00/);assert.match(html,/12:00/);assert.match(html,/Hóa đơn phát hành sau lúc chi/);
    assert.match(p2.eval("documentsTab(input)"),/chưa coi là chứng từ đã có khi chi/);assert.equal(d.hits.find(h=>h.rule_id==="P2").points,0);
  });
  check("Late verification and expired limit display effective dates without changing points",()=>{
    p2Packet("P2_LIMIT_FUTURE");const future=p2.eval("temporalEvidence(input,row,hit)");
    assert.match(future,/Xác minh hạn mức có sau lúc chi/);assert.match(future,/13\/8\/2025/);assert.match(future,/chưa được dùng làm bằng chứng/);
    p2Packet("P2_LIMIT_EXPIRED");const expired=p2.eval("temporalEvidence(input,row,hit)");
    assert.match(expired,/không gồm mốc cuối/);assert.match(expired,/đúng mốc kết thúc/);assert.match(expired,/12\/8\/2025/);
  });
  check("Installments expose source-version ambiguity without asserting lookahead",()=>{
    for(const id of ["P2_INSTALL_CASH","P2_INSTALL_MIXED"]){p2Packet(id);const html=p2.eval("documentsTab(input)");assert.match(html,/Cần lịch sử phiên bản hóa đơn/);assert.match(html,/chưa chứng minh dữ liệu tương lai/);}
  });
  check("Refund summary keeps original case and distinguishes full and partial returns",()=>{
    p2Packet("P2_REFUND_FULL");const full=p2.eval("refundSummary(input)");
    assert.match(full,/RC_a65bd18d556b9cfd/);assert.match(full,/8 điểm/);assert.match(full,/Chênh lệch chi trừ hoàn theo nguồn<\/span>0 ₫/);
    p2Packet("P2_REFUND_PART");const part=p2.eval("refundSummary(input)");
    assert.match(part,/6\.000\.000/);assert.match(part,/1\.000\.000/);assert.match(part,/Chênh lệch chi trừ hoàn theo nguồn<\/span>5\.000\.000 ₫/);
    assert.match(part,/không tự đóng hồ sơ gốc hoặc bù trừ/);
  });
  check("Journal reversal is never presented as proof of physical cash recovery",()=>{
    p2Packet("P2_REVERSAL_JOURNAL");const html=p2.eval("refundSummary(input)+documentsTab(input)");
    assert.match(html,/Đảo sổ \/ điều chỉnh kế toán/);assert.match(html,/chưa chứng minh đã nhận lại tiền thực/);
    assert.doesNotMatch(html,/Hoàn tiền cho khoản chi gốc theo nguồn/);
  });
  check("Original-transaction navigation works from the last refund row",()=>{
    const d=p2Packet("P2_REFUND_FULL");let handler;
    const button={dataset:{jumpTransaction:d.transactions[0].transaction_id},addEventListener:(event,fn)=>handler=fn};
    p2.nodes["uat-content"].querySelectorAll=()=>[button];
    p2.eval('state.detail=input;state.selected=input.control_id;state.transaction=input.transactions[1].transaction_id;state.tab="transactions";renderTab()');
    assert.equal(typeof handler,"function");handler();assert.equal(p2.eval("state.transaction"),d.transactions[0].transaction_id);
    assert.equal(p2.eval("state.tab"),"transactions");p2.nodes["uat-content"].querySelectorAll=()=>[];
  });
  check("Independent accounting acceptance is not inferred from UAT counts",()=>{
    const html=fs.readFileSync(path.join(ROOT,"review_ui/p2_controls.html"),"utf8");
    assert.match(html,/Nghiệm thu kế toán độc lập: chưa có biên bản được xác minh/);
    assert.match(html,/Đã có ghi chú UAT/);assert.match(html,/kể cả ghi chú của trợ lý/);
  });
  let renderedTransactions=0,renderedDocuments=0;
  check("All 32 frozen controls and all 73 transactions render; VND columns retain currency",()=>{
    const details=controlDetails();assert.equal(details.length,32);
    for(const d of details){
      const frozen=JSON.stringify(d);p2.context.input=d;p2.eval('state.detail=input;state.selected=input.control_id;state.transaction=input.transactions.at(-1).transaction_id;state.tab="transactions";renderDetail()');
      for(const tx of d.transactions){p2.context.tid=tx.transaction_id;p2.eval('state.transaction=tid;state.tab="transactions";renderTab()');assert.ok(p2.nodes["uat-content"].innerHTML);renderedTransactions++;}
      for(const tab of ["documents","queue","history"]){p2.context.tab=tab;p2.eval('state.tab=tab;renderTab()');assert.ok(p2.nodes["uat-content"].innerHTML);}
      if(d.control_id==="FULL_EQUAL"){const html=p2.eval("documentsTab(input)");assert.match(html,/Nợ \(VND\)/);assert.match(html,/₫/);assert.doesNotMatch(html,/Chưa xác minh quy đổi/);}
      renderedDocuments+=d.documents.length;assert.equal(JSON.stringify(d),frozen,"Renderer mutated payload");
    }
    assert.equal(renderedTransactions,73);
  });
  return {successful:true,check_count:checks.length,checks,rendered_controls:32,rendered_transactions:renderedTransactions,
    rendered_documents:renderedDocuments,browser_visual_qa:false};
}
module.exports={run,environment,controlDetails};
if(require.main===module)console.log(JSON.stringify(run(),null,2));
