/* URL/history and async-navigation regressions. Browser acceptance is separate. */
"use strict";
const path=require("node:path"),assert=require("node:assert/strict");
const {environment,controlDetails}=require("./review_evidence_ui.test.js");
const ROOT=path.resolve(__dirname,"..");
function mainEnvironment(){
  const env=environment(path.join(ROOT,"review_ui/app.js"));
  env.context.calls=[];
  env.eval(`state.meta={default_scenario:"003",scenarios:["001","003"]};caseRouteReady=true;
    loadQueue=async()=>{calls.push({queue:state.scenario});};
    renderDetail=()=>{$("detail-panel").innerHTML=state.scenario+":"+state.selected;};
    api=async(path,body)=>{calls.push({path,body});if(body)return {};
      const q=new URLSearchParams(path.split("?")[1]);return {case:{case_id:q.get("id"),archived:false}};};`);
  return env;
}
function p2Environment(){
  const env=environment(path.join(ROOT,"review_ui/p2_controls.js"));
  env.context.controls=controlDetails();env.context.calls=[];
  env.eval(`p2RouteReady=true;loadControls=async()=>{};
    api=async(path)=>{calls.push(path);const id=new URLSearchParams(path.split("?")[1]).get("id");
      const d=controls.find(row=>row.control_id===id);if(!d)throw new Error("Unknown control");return d;};`);
  return env;
}
const deferred=()=>{let resolve;const promise=new Promise(done=>resolve=done);return {promise,resolve};};
async function run(){
  const checks=[],check=async(name,fn)=>{await fn();checks.push(name);};
  await check("Case selection writes scenario/id and reload route opens that case",async()=>{
    const e=mainEnvironment();e.eval('state.scenario="003"');await e.eval('openCase("A4_CASE")');
    assert.equal(e.context.window.location.hash,"#scenario=003&case=A4_CASE");
    assert.equal(e.nodes["detail-panel"].innerHTML,"003:A4_CASE");
    const restored=mainEnvironment();restored.context.window.location.hash=e.context.window.location.hash;
    await restored.eval("applyCaseLocation(true)");assert.equal(restored.eval("state.selected"),"A4_CASE");
  });
  await check("Same-tab case hash switches dataset/detail; duplicate history events admit once",async()=>{
    const e=mainEnvironment();await e.eval('openCase("OLD")');e.context.calls.length=0;
    e.context.window.location.hash="#scenario=001&case=NEW";
    await Promise.all([e.emit("popstate"),e.emit("hashchange")]);
    assert.equal(e.eval("state.scenario"),"001");assert.equal(e.nodes.scenario.value,"001");
    assert.equal(e.nodes["detail-panel"].innerHTML,"001:NEW");
    assert.equal(e.context.calls.filter(c=>c.path==="/api/admit").length,1);
    assert.ok(e.context.calls.find(c=>c.path?.includes("scenario=001&id=NEW")));
  });
  await check("Scenario dropdown clears old case URL; back/forward restore matching selection",async()=>{
    const e=mainEnvironment();await e.eval('openCase("A4_CASE")');
    e.nodes.scenario.value="001";await e.nodes.scenario.handlers.change();
    assert.equal(e.context.window.location.hash,"#scenario=001");assert.equal(e.eval("state.selected"),null);
    e.context.window.location.hash="#scenario=003&case=A4_CASE";await e.emit("popstate");
    assert.equal(e.nodes["detail-panel"].innerHTML,"003:A4_CASE");
    e.context.window.location.hash="#scenario=001";await e.emit("popstate");
    assert.equal(e.eval("state.detail"),null);assert.equal(e.eval("state.scenario"),"001");
  });
  await check("Late case response never displays or admits a superseded route",async()=>{
    const e=mainEnvironment(),old=deferred();e.context.old=old.promise;
    e.eval('api=async(path,body)=>{calls.push({path,body});if(body)return {};const id=new URLSearchParams(path.split("?")[1]).get("id");return id==="OLD"?old:{case:{case_id:id,archived:false}};};');
    const pending=e.eval('openCase("OLD")');assert.equal(e.eval("state.detail"),null);
    await e.eval('openCase("NEW")');old.resolve({case:{case_id:"OLD",archived:false}});await pending;
    assert.equal(e.nodes["detail-panel"].innerHTML,"003:NEW");
    assert.deepEqual(e.context.calls.filter(c=>c.path==="/api/admit").map(c=>c.body.case_id),["NEW"]);
  });
  await check("Invalid case or dataset clears previous evidence and feedback form",async()=>{
    const e=mainEnvironment();await e.eval('openCase("OLD")');
    e.eval('api=async()=>{throw new Error("Không tìm thấy hồ sơ trong bộ dữ liệu này.");}');
    e.context.window.location.hash="#scenario=003&case=MISSING";await e.emit("hashchange");
    assert.equal(e.eval("state.selected"),null);assert.equal(e.eval("state.detail"),null);
    assert.doesNotMatch(e.nodes["detail-panel"].innerHTML,/003:OLD/);
    assert.doesNotMatch(e.nodes["detail-panel"].innerHTML,/Đang nạp/);
    assert.match(e.nodes["detail-panel"].innerHTML,/chọn hồ sơ khác trong hàng đợi/);
    assert.match(e.nodes.notice.textContent,/Không tìm thấy hồ sơ/);
    e.context.window.location.hash="#scenario=999&case=OLD";await e.emit("hashchange");
    assert.match(e.nodes.notice.textContent,/Không tìm thấy bộ dữ liệu/);
  });
  await check("Failed case clears loading state and selecting a known case recovers",async()=>{
    const e=mainEnvironment();
    e.eval('const knownApi=api;api=async(path,body)=>{if(path.includes("id=MISSING"))throw new Error("Không tìm thấy hồ sơ trong bộ dữ liệu này.");return knownApi(path,body);};');
    await e.eval('openCase("MISSING")');
    assert.equal(e.eval("state.selected"),null);
    assert.doesNotMatch(e.nodes["detail-panel"].innerHTML,/Đang nạp/);
    assert.equal(e.context.calls.filter(c=>c.path==="/api/admit").length,0);
    await e.eval('openCase("C4_CASE")');
    assert.equal(e.nodes["detail-panel"].innerHTML,"003:C4_CASE");
    assert.equal(e.context.window.location.hash,"#scenario=003&case=C4_CASE");
    assert.equal(e.nodes.notice.className,"notice hidden");
  });
  await check("P2 cards and transaction picker update URL without losing review draft",async()=>{
    const e=p2Environment();await e.eval('openControl("REFUND_FULL")');
    assert.equal(e.context.window.location.hash,"#control=REFUND_FULL&transaction=AUDIT_0001");
    e.eval('$("uat-reason").value="Draft remains"');
    e.nodes["uat-transaction"].handlers.change({target:{value:"AUDIT_0000"}});
    assert.equal(e.context.window.location.hash,"#control=REFUND_FULL&transaction=AUDIT_0000");
    assert.equal(e.eval("state.transaction"),"AUDIT_0000");assert.equal(e.nodes["uat-reason"].value,"Draft remains");
  });
  await check("P2 same-control Back/Forward selects transaction without refetching",async()=>{
    const e=p2Environment();await e.eval('openControl("REFUND_FULL","AUDIT_0000")');
    e.context.window.location.hash="#control=REFUND_FULL&transaction=AUDIT_0001";
    await Promise.all([e.emit("popstate"),e.emit("hashchange")]);
    assert.equal(e.eval("state.transaction"),"AUDIT_0001");assert.equal(e.context.calls.length,1);
    e.context.window.location.hash="#control=REFUND_FULL&transaction=AUDIT_0000";await e.emit("popstate");
    assert.equal(e.eval("state.transaction"),"AUDIT_0000");assert.equal(e.context.calls.length,1);
  });
  await check("P2 cross-control hashes clear stale filters and load only the new route",async()=>{
    const e=p2Environment();await e.eval('openControl("FULL_EQUAL")');e.nodes["uat-group"].value="full_invoice";
    e.context.calls.length=0;e.context.window.location.hash="#control=RECUR_A5&transaction=AUDIT_0000";
    await Promise.all([e.emit("popstate"),e.emit("hashchange")]);
    assert.equal(e.eval("state.selected"),"RECUR_A5");assert.equal(e.eval("state.transaction"),"AUDIT_0000");
    assert.equal(e.nodes["uat-group"].value,"");assert.equal(e.context.calls.length,1);
    assert.match(e.nodes["uat-content"].innerHTML,/<option value="AUDIT_0000" selected>/);
  });
  await check("P2 late response cannot repopulate a cleared route",async()=>{
    const e=p2Environment(),slow=deferred();e.context.slow=slow.promise;
    e.eval('api=async()=>slow');const pending=e.eval('openControl("FULL_EQUAL")');
    assert.equal(e.eval("state.detail"),null);e.context.window.location.hash="";await e.emit("hashchange");
    slow.resolve(e.context.controls.find(c=>c.control_id==="FULL_EQUAL"));await pending;
    assert.equal(e.eval("state.detail"),null);assert.equal(e.eval("state.selected"),null);
  });
  await check("Invalid P2 transaction does not silently fall back to another transaction",async()=>{
    const e=p2Environment();await e.eval('openControl("FULL_EQUAL")');
    e.context.window.location.hash="#control=REFUND_FULL&transaction=MISSING";await e.emit("hashchange");
    assert.equal(e.eval("state.detail"),null);assert.match(e.nodes["uat-notice"].textContent,/Không tìm thấy giao dịch/);
    await e.eval('openControl("FULL_BELOW")');assert.equal(e.eval("state.selected"),"FULL_BELOW");
    assert.equal(e.nodes["uat-notice"].textContent,"");
  });
  await check("A default P2 link canonicalizes in place and never manufactures an engine case",async()=>{
    const e=p2Environment();e.context.window.location.hash="#control=FULL_BELOW";await e.emit("hashchange");
    assert.equal(e.context.window.location.hash,"#control=FULL_BELOW&transaction=AUDIT_0000");
    assert.equal(e.historyWrites.at(-1).method,"replace");
    assert.equal(e.eval("state.detail.cases.length"),0);assert.equal(e.eval("state.detail.hits.some(h=>h.rule_id==='P2')"),false);
  });
  return {successful:true,check_count:checks.length,checks,browser_visual_qa:false};
}
module.exports={run};
if(require.main===module)run().then(result=>console.log(JSON.stringify(result,null,2)));
