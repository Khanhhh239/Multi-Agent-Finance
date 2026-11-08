"use strict";
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'C:/Users/Technical Support/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const ROOT=path.resolve(__dirname,'..'),BASE='http://127.0.0.1:8855',OUT=path.join(ROOT,'.runtime/company_ml_readiness_e2e_'+Date.now());
fs.mkdirSync(OUT,{recursive:true});let browser,page;const checks=[],errors=[],writes=[];
function check(name,value){checks.push({name,passed:!!value});assert.ok(value,name);}
async function ready(){await page.waitForFunction(()=>{
  const note=document.getElementById('ml-score-readiness');
  return !document.getElementById('ml-reload').disabled&&document.getElementById('ml-current').textContent.trim()
    &&note.textContent&&note.getAttribute('aria-busy')==='false';
});}
async function period(value){
  const response=page.waitForResponse(r=>r.url().includes('/api/company-ml/readiness?')&&new URL(r.url()).searchParams.get('train_end')===value+':00+07:00');
  await page.locator('#ml-train-end').fill(value);await page.locator('#ml-train-end').blur();await response;await ready();
}
async function state(company){return (await page.request.get(BASE+'/api/company-ml/status?scenario=003&company='+company)).json();}
async function catBlocked(){return page.locator('option[value="catboost"]').evaluate(option=>option.disabled);}
(async()=>{
  const marker=JSON.parse(fs.readFileSync(path.join(ROOT,'.runtime/company_ml_readiness_demo_20261105/demo.json'),'utf8'));
  check('isolated_QA_workspace',marker.kind==='company-ml-readiness-demo-v1'&&marker.is_synthetic);
  browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
  const context=await browser.newContext({viewport:{width:1365,height:1000},locale:'vi-VN',timezoneId:'Asia/Ho_Chi_Minh'});
  page=await context.newPage();page.setDefaultTimeout(30000);
  page.on('pageerror',error=>errors.push(error.message));page.on('request',request=>{if(request.method()==='POST')writes.push(request.url());});
  check('QA_server',(await (await page.request.get(BASE+'/api/health')).json()).qa===true);
  await page.goto(BASE+'/company-ml?company=C001&scenario=003',{waitUntil:'networkidle'});await ready();
  const before=await state('C001');
  check('complete_training_labels_enable_CatBoost',!(await catBlocked()));
  check('coverage_and_both_classes_visible',(await page.locator('#ml-catboost-readiness').innerText()).includes('18/18'));
  check('compatible_active_model_can_score',!(await page.locator('#ml-score').isDisabled())&&!(await page.locator('#ml-keep').isDisabled()));
  await page.locator('#ml-algorithm').selectOption('catboost');
  const changedPeriod=page.waitForResponse(r=>r.url().includes('/api/company-ml/readiness?')&&new URL(r.url()).searchParams.get('train_end')==='2024-01-10T12:00:00+07:00');
  await page.locator('#ml-train-end').fill('2024-01-10T12:00');
  check('editing_train_period_locks_immediately',await page.locator('#ml-evaluate').isDisabled());
  await page.locator('#ml-train-end').blur();await changedPeriod;await ready();
  check('late_label_locks_CatBoost_for_new_period',await catBlocked()&&await page.locator('#ml-evaluate').isDisabled());
  check('chosen_algorithm_not_silently_changed',await page.locator('#ml-algorithm').inputValue()==='catboost');
  check('late_label_reason_visible',(await page.locator('#ml-catboost-readiness').innerText()).includes('biết nhãn muộn'));
  const beforeBlocked=writes.length;
  await page.locator('#ml-evaluate-form').evaluate(form=>form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
  check('blocked_training_sends_no_POST',writes.length===beforeBlocked);
  await period('2024-01-19T12:00');
  check('valid_period_reopens_CatBoost',!(await catBlocked())&&!(await page.locator('#ml-evaluate').isDisabled()));
  const evaluatedResponse=page.waitForResponse(r=>r.url().endsWith('/api/company-ml/evaluate'));
  await page.locator('#ml-evaluate').click();const response=await evaluatedResponse;check('eligible_CatBoost_POST_accepted',response.status()===200);
  const evaluated=await response.json();await ready();
  check('actual_candidate_is_CatBoost',evaluated.versions[0].algorithm==='catboost');
  check('evaluating_never_switches_active_model',evaluated.active_version===before.active_version);
  await period('2024-01-26T12:00');
  check('invalid_window_locks_training',await page.locator('#ml-evaluate').isDisabled());
  check('invalid_training_window_does_not_break_compatible_scoring',!(await page.locator('#ml-score').isDisabled()));
  await period('2024-01-19T12:00');
  await page.route('**/api/company-ml/readiness?**',route=>route.abort());
  await page.locator('#ml-reload').click();
  await page.waitForFunction(()=>document.getElementById('ml-score-readiness').textContent.includes('Mất kết nối'));
  check('readiness_network_failure_locks_actions',await page.locator('#ml-score').isDisabled()&&await page.locator('#ml-keep').isDisabled()&&await page.locator('#ml-evaluate').isDisabled());
  await page.unroute('**/api/company-ml/readiness?**');await page.locator('#ml-reload').click();await ready();
  check('explicit_reload_recovers',!(await page.locator('#ml-score').isDisabled())&&!(await page.locator('#ml-evaluate').isDisabled()));
  await page.locator('#ml-company').selectOption('C002');await ready();
  check('partial_labels_CatBoost_disabled',await catBlocked());
  check('partial_label_count_visible',(await page.locator('#ml-catboost-readiness').innerText()).includes('1/18'));
  check('incompatible_active_model_locks_score_and_keep',await page.locator('#ml-score').isDisabled()&&await page.locator('#ml-keep').isDisabled());
  check('incompatibility_reason_visible',(await page.locator('#ml-score-readiness').innerText()).includes('khác hợp đồng'));
  await page.locator('#ml-algorithm').selectOption('isolation_forest');
  check('compatible_new_candidate_can_still_be_evaluated',!(await page.locator('#ml-evaluate').isDisabled()));
  const blockedWrites=writes.length;
  await page.locator('#ml-score').evaluate(button=>button.dispatchEvent(new MouseEvent('click',{bubbles:true})));
  check('locked_score_sends_no_POST',writes.length===blockedWrites);
  const current=await state('C002'),meta=await (await page.request.get(BASE+'/api/meta')).json();
  const bypass=await page.request.post(BASE+'/api/company-ml/score',{headers:{'X-CSRF-Token':meta.csrf_token},
    data:{scenario:'003',company_id:'C002',expected_revision:current.data.revision,expected_active:current.active_version}});
  check('backend_still_rejects_incompatible_scoring',bypass.status()===400);
  await page.screenshot({path:path.join(OUT,'incompatible_desktop.png'),fullPage:true});
  await page.goto(BASE+'/company-ml?company=C002&scenario=003',{waitUntil:'networkidle'});await ready();
  await page.reload({waitUntil:'networkidle'});await ready();
  check('reload_preserves_gating',await catBlocked()&&await page.locator('#ml-score').isDisabled());
  await page.setViewportSize({width:390,height:844});
  check('mobile_no_page_overflow',await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
  await page.locator('#ml-catboost-readiness').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(OUT,'readiness_mobile.png')});
  await page.goto('http://127.0.0.1:8856/company-ml',{waitUntil:'networkidle'});await ready();
  check('read_only_role_cannot_train_score_or_keep',await page.locator('#ml-evaluate').isDisabled()&&await page.locator('#ml-score').isDisabled()&&await page.locator('#ml-keep').isDisabled());
  check('no_browser_errors',errors.length===0);
  fs.writeFileSync(path.join(OUT,'results.json'),JSON.stringify({checks,errors},null,2));
  console.log(JSON.stringify({out:OUT,passed:checks.filter(c=>c.passed).length,total:checks.length},null,2));
})().catch(error=>{fs.writeFileSync(path.join(OUT,'failure.json'),JSON.stringify({error:error.message,stack:error.stack,checks,errors},null,2));console.error(error);console.error('Evidence: '+OUT);process.exitCode=1;})
.finally(async()=>{if(page)await page.screenshot({path:path.join(OUT,'last_screen.png'),fullPage:true}).catch(()=>{});if(browser)await browser.close();});
