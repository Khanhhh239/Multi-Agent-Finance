"use strict";
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'C:/Users/Technical Support/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const ROOT=path.resolve(__dirname,'..'),BASE='http://127.0.0.1:8857',OUT=path.join(ROOT,'.runtime/ml_reviews_e2e_'+Date.now());fs.mkdirSync(OUT,{recursive:true});
const checks=[],errors=[];let browser,page;
function check(name,value){checks.push({name,passed:!!value});assert.ok(value,name);}
async function ready(){await page.waitForFunction(()=>!document.getElementById('review-reload').disabled&&!document.getElementById('review-work').hidden);}
async function post(button,endpoint){
  const response=page.waitForResponse(r=>r.url().endsWith('/api/ml-reviews/'+endpoint)&&r.request().method()==='POST');
  await page.locator(button).click();const r=await response;const data=await r.json();assert.equal(r.status(),200,JSON.stringify(data));await ready();return data;
}
(async()=>{
  const marker=JSON.parse(fs.readFileSync(path.join(ROOT,'.runtime/ml_reviews_demo_20261105/demo.json'),'utf8'));check('isolated_qa_workspace',marker.kind==='ml-reviews-qa-v1');
  browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
  const context=await browser.newContext({viewport:{width:1365,height:1000},locale:'vi-VN',timezoneId:'Asia/Ho_Chi_Minh'});
  page=await context.newPage();page.setDefaultTimeout(30000);page.on('pageerror',error=>errors.push(error.message));
  await page.goto(BASE+'/ml-reviews',{waitUntil:'networkidle'});await ready();
  check('company_scope_and_queue_visible',await page.locator('#review-company').inputValue()==='C001'&&(await page.locator('#review-list button').count())>0);
  check('public_page_has_no_private_model_names',!/(Isolation Forest|Autoencoder|Local Outlier Factor|ECOD)/.test(await page.locator('main').innerText()));
  const firstTitle=await page.locator('#review-title').innerText();
  await post('#review-start','timer');await page.waitForTimeout(1200);
  await page.locator('#review-useful').selectOption('unknown');await page.locator('#review-rationale').fill('SIMULATED: chưa có chứng từ gốc để kết luận hành động.');
  await page.locator('#review-refs').fill('SIMULATED: '+(await page.locator('#review-reference').innerText()));
  const paused=await post('#review-pause','timer');check('real_time_measured',paused.work.timer.confirmed_ms>=1000);
  const clock=await page.locator('#review-clock').innerText();await page.waitForTimeout(1200);
  check('pause_excludes_waiting',await page.locator('#review-clock').innerText()===clock);
  await post('#review-start','timer');await page.waitForTimeout(1100);const resumed=await post('#review-pause','timer');
  check('resume_adds_active_segment',resumed.work.timer.confirmed_ms>=paused.work.timer.confirmed_ms+1000);
  const draft=await post('#review-draft','save');check('draft_saved',draft.work.status==='draft');
  await page.reload({waitUntil:'networkidle'});await ready();
  check('reload_restores_unit_and_draft',await page.locator('#review-title').innerText()===firstTitle&&(await page.locator('#review-rationale').inputValue()).startsWith('SIMULATED'));
  check('reload_preserves_time',await page.locator('#review-clock').innerText()===clock||await page.locator('#review-clock').innerText()!=='00:00:00');
  await page.locator('#review-ack').check();const saved=await post('#review-submit','save');
  check('unknown_saved_with_actor_time_and_evidence',saved.work.status==='reviewed'&&saved.work.form.useful==='unknown'&&saved.work.owner.user_id==='SIM_CHIEF'&&saved.work.timer.confirmed_ms>0);
  await page.locator('#review-summary').click();await page.waitForFunction(()=>document.getElementById('review-summary-body').textContent.includes('phiếu đã rà'));
  check('model_summary_hidden_until_review_complete',(await page.locator('#review-summary-body').innerText()).includes('Hoàn tất')&&!/ecod|isolation_forest/.test(await page.locator('#review-summary-body').innerText()));
  const downloadPromise=page.waitForEvent('download');await page.locator('#review-export').click();const download=await downloadPromise;await download.saveAs(path.join(OUT,'reviews.csv'));
  check('CSV_export_contains_result_and_measured_time',fs.readFileSync(path.join(OUT,'reviews.csv'),'utf8').includes('SIM_CHIEF'));
  await page.locator('#review-company').selectOption('C002');await ready();
  check('switch_company_updates_evidence',(await page.locator('#review-title').innerText()).startsWith('C002'));
  await post('#review-start','timer');await page.waitForTimeout(1100);
  await page.locator('#review-useful').selectOption('yes');await page.locator('#review-rationale').fill('SIMULATED: đối chiếu dữ kiện trong phiếu.');await page.locator('#review-refs').fill('SIMULATED_EVIDENCE');
  await page.locator('#review-action').fill('');
  await page.locator('#review-ack').check();check('useful_action_is_required',await page.locator('#review-action').getAttribute('required')!==null);
  const blocked=page.waitForResponse(r=>r.url().endsWith('/api/ml-reviews/save'));
  await page.locator('#review-form').evaluate(form=>form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
  check('backend_rejects_useful_without_action',(await blocked).status()===400);await ready();
  await page.locator('#review-action').fill('SIMULATED: yêu cầu đối chiếu lại chứng từ, chỉ điều chỉnh khi có căn cứ.');await page.locator('#review-ack').check();
  const useful=await post('#review-submit','save');check('useful_action_and_basis_persisted',useful.work.form.business_action.startsWith('SIMULATED')&&useful.work.form.evidence_refs==='SIMULATED_EVIDENCE');
  await page.reload({waitUntil:'networkidle'});await ready();check('reload_keeps_company_and_result',await page.locator('#review-company').inputValue()==='C002'&&await page.locator('#review-useful').inputValue()==='yes');
  await page.screenshot({path:path.join(OUT,'review_desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});check('mobile_no_horizontal_overflow',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.locator('#review-form').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(OUT,'review_mobile.png')});
  await page.goto('http://127.0.0.1:8858/ml-reviews',{waitUntil:'networkidle'});await ready();
  check('accountant_only_sees_own_company',(await page.locator('#review-company option').count())===1&&await page.locator('#review-company').inputValue()==='C001');
  check('other_review_owner_cannot_be_overwritten',await page.locator('#review-start').isDisabled()&&await page.locator('#review-submit').isDisabled());
  check('manager_controls_hidden_for_accountant',await page.locator('#review-manager').isHidden());
  const unstarted=page.locator('#review-list button').filter({hasText:'Chưa rà'}).first();
  await unstarted.click();await ready();await post('#review-start','timer');await page.waitForTimeout(1100);
  const autoPause=page.waitForResponse(r=>r.url().endsWith('/api/ml-reviews/timer')&&r.request().postDataJSON()?.action==='pause');
  // Headless Chrome can keep all tabs visible; drive its visibility event explicitly.
  await page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});document.dispatchEvent(new Event('visibilitychange'));});
  await autoPause;
  await page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,get:()=>false});document.dispatchEvent(new Event('visibilitychange'));});
  await ready();
  check('hidden_tab_event_pauses_timer',await page.locator('#review-pause').isDisabled()&&!(await page.locator('#review-start').isDisabled()));
  await post('#review-start','timer');await page.locator('#review-rationale').fill('SIMULATED: bản nháp giữ lại khi mất kết nối.');
  await page.route('**/api/ml-reviews/timer',route=>route.request().postDataJSON().action==='pause'?route.abort():route.continue());
  await page.locator('#review-pause').click();await page.waitForFunction(()=>document.getElementById('review-notice').textContent.includes('Mất kết nối'));
  check('network_failure_stops_further_mutations',await page.locator('#review-start').isDisabled()&&await page.locator('#review-draft').isDisabled());
  await page.unroute('**/api/ml-reviews/timer');await page.locator('#review-reload').click();await ready();
  check('reload_preserves_unsaved_text',(await page.locator('#review-rationale').inputValue()).includes('mất kết nối'));
  check('lost_timer_session_requires_recovery',await page.locator('#review-recover').isVisible());
  await post('#review-recover','timer');await post('#review-draft','save');
  check('recovered_session_is_paused',await page.locator('#review-pause').isDisabled());
  check('no_browser_errors',errors.length===0);
  fs.writeFileSync(path.join(OUT,'results.json'),JSON.stringify({checks,errors},null,2));console.log(JSON.stringify({out:OUT,passed:checks.filter(c=>c.passed).length,total:checks.length},null,2));
})().catch(error=>{fs.writeFileSync(path.join(OUT,'failure.json'),JSON.stringify({error:error.message,stack:error.stack,checks,errors},null,2));console.error(error);console.error(OUT);process.exitCode=1;})
.finally(async()=>{if(page)await page.screenshot({path:path.join(OUT,'last_screen.png'),fullPage:true}).catch(()=>{});if(browser)await browser.close();});
