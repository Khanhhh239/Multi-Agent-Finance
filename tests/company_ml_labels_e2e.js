"use strict";
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'C:/Users/Technical Support/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const ROOT=path.resolve(__dirname,'..'),DEMO=path.resolve(process.env.LABELS_DEMO_ROOT||path.join(ROOT,'.runtime/company_ml_labels_demo_20261106'));
const BASE=process.env.LABELS_DEMO_URL||'http://127.0.0.1:8859',OUT=path.join(ROOT,'.runtime/company_ml_labels_e2e_'+Date.now());
fs.mkdirSync(OUT,{recursive:true});const checks=[],errors=[],writes=[];let browser,page;
function check(name,value){checks.push({name,passed:!!value});assert.ok(value,name);}
async function state(company='C001'){return (await page.request.get(BASE+'/api/company-ml/status?scenario=003&company='+company)).json();}
async function ready(){await page.waitForFunction(()=>!document.getElementById('ml-reload').disabled&&document.getElementById('ml-data-summary').textContent.trim()&&document.getElementById('ml-score-readiness').getAttribute('aria-busy')==='false');}
async function upload(name){
  await page.locator('#ml-labels').setInputFiles(path.join(DEMO,'SIM_'+name+'.csv'));
  const response=page.waitForResponse(r=>r.url().endsWith('/labels-preview'));
  await page.locator('#ml-update').click();return await response;
}
async function save(){
  const response=page.waitForResponse(r=>r.url().endsWith('/labels-update'));
  await page.locator('#ml-label-save').click();const result=await response;await result.finished();
  await page.waitForFunction(()=>!document.getElementById('ml-reload').disabled);return result;
}
(async()=>{
  const marker=JSON.parse(fs.readFileSync(path.join(DEMO,'demo.json'),'utf8'));
  check('fresh_synthetic_workspace',marker.kind==='company-ml-labels-demo-v1'&&marker.is_synthetic);
  browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
  const context=await browser.newContext({viewport:{width:1365,height:1000},locale:'vi-VN',timezoneId:'Asia/Ho_Chi_Minh'});
  page=await context.newPage();page.setDefaultTimeout(20000);
  page.on('pageerror',error=>errors.push(error.message));
  page.on('request',request=>{if(request.method()==='POST')writes.push(request.url());});
  check('qa_server',(await (await page.request.get(BASE+'/api/health')).json()).qa===true);
  await page.goto(BASE+'/company-ml?company=C001&scenario=003',{waitUntil:'networkidle'});await ready();
  const original=await state(),other=await state('C002');check('starts_with_fifteen_labels',original.data.labels_count===15);
  let response=await upload('identical');check('identical_preview_succeeds',response.ok());
  check('preview_does_not_save',(await state()).data.revision===original.data.revision);
  check('preview_explains_preservation',(await page.locator('#ml-label-counts').innerText()).includes('Các nhãn không có trong tệp được giữ nguyên'));
  response=await save();const same=await response.json();
  check('one_identical_label_keeps_fifteen_and_revision',same.data.labels_count===15&&same.data.revision===original.data.revision&&same.label_update.unchanged===1);
  check('success_reports_fifteen_to_fifteen',(await page.locator('#ml-notice').innerText()).includes('15 → 15'));
  await ready();await upload('new');response=await save();const added=await response.json();
  check('new_label_adds_to_sixteen',added.data.labels_count===16&&added.label_update.added===1);
  check('active_model_is_preserved',added.active_version===original.active_version);
  await ready();await page.reload({waitUntil:'networkidle'});await ready();
  check('reload_keeps_sixteen',(await page.locator('#ml-data-summary').innerText()).includes('16 nhãn'));
  const beforeConflict=await state();await upload('conflicts');
  check('conflicts_do_not_save_automatically',(await state()).data.revision===beforeConflict.data.revision);
  check('conflict_details_are_visible',(await page.locator('#ml-label-conflicts').innerText()).includes('SIM_NEW_EVIDENCE'));
  check('conflicts_require_an_explicit_choice',await page.locator('#ml-label-save').isDisabled());
  await page.locator('#ml-label-policy').selectOption('keep_existing');
  check('keeping_old_labels_requires_no_correction_confirmation',!(await page.locator('#ml-label-save').isDisabled()));
  response=await save();const kept=await response.json();
  check('keep_old_adds_new_and_counts_conflicts',kept.data.labels_count===17&&kept.label_update.added===1&&kept.label_update.skipped===1);
  await ready();await upload('conflicts');await page.locator('#ml-label-policy').selectOption('replace_conflicts');
  check('correction_locked_without_reason_and_confirmation',await page.locator('#ml-label-save').isDisabled());
  await page.locator('#ml-label-reason').fill('SIM: đối chiếu chứng từ mới, sửa nhãn kiểm thử');
  check('correction_still_locked_without_confirmation',await page.locator('#ml-label-save').isDisabled());
  await page.locator('#ml-label-acknowledge').check();
  check('explicit_correction_enabled',!(await page.locator('#ml-label-save').isDisabled()));
  await page.screenshot({path:path.join(OUT,'conflicts_desktop.png'),fullPage:true});
  response=await save();const corrected=await response.json();
  check('correction_keeps_seventeen_and_changes_only_one',corrected.data.labels_count===17&&corrected.label_update.updated===1&&corrected.label_update.added===0);
  check('correction_audit_reference_exists',!!corrected.history.at(-1).details.operation_id);
  await ready();await upload('invalid');
  check('invalid_company_explained',(await page.locator('#ml-notice').innerText()).includes('đúng công ty/giao dịch'));
  check('invalid_upload_keeps_labels',(await state()).data.revision===corrected.data.revision);
  // A failed save must preserve the authored decision, and send no automatic retry.
  await upload('identical');await page.locator('#ml-label-policy').selectOption('replace_conflicts');
  await page.locator('#ml-label-reason').fill('SIM: retained draft after network failure');await page.locator('#ml-label-acknowledge').check();
  const beforeNetwork=writes.filter(url=>url.endsWith('/labels-update')).length;
  await page.route('**/api/company-ml/labels-update',route=>route.abort('failed'));
  await page.locator('#ml-label-save').click();await page.waitForFunction(()=>document.getElementById('ml-notice').textContent.includes('Mất kết nối'));
  check('network_failure_keeps_draft',await page.locator('#ml-label-reason').inputValue()==='SIM: retained draft after network failure'&&await page.locator('#ml-label-acknowledge').isChecked());
  check('network_failure_does_not_replay',writes.filter(url=>url.endsWith('/labels-update')).length===beforeNetwork+1);
  check('network_failure_keeps_database',(await state()).data.revision===corrected.data.revision);
  await page.unroute('**/api/company-ml/labels-update');await page.locator('#ml-label-cancel').click();
  check('cancel_clears_preview_without_saving',await page.locator('#ml-label-preview').isHidden());
  // Commit another verified addition after preview, simulating a second session.
  await upload('all_labels');const csrf=(await (await page.request.get(BASE+'/api/meta')).json()).csrf_token;
  const lines=fs.readFileSync(path.join(DEMO,'SIM_all_labels.csv'),'utf8').replace(/^\uFEFF/,'').trim().split(/\r?\n/);
  const concurrent=await page.request.post(BASE+'/api/company-ml/labels-update',{headers:{'X-CSRF-Token':csrf},
    data:{scenario:'003',company_id:'C001',expected_revision:corrected.data.revision,labels_text:lines[0]+'\n'+lines[19]+'\n'}});
  check('second_session_addition_succeeds',concurrent.ok());const concurrentState=await concurrent.json();
  await page.locator('#ml-label-policy').selectOption('keep_existing');response=await save();
  check('stale_preview_is_blocked',response.status()===409&&(await page.locator('#ml-notice').innerText()).includes('Dữ liệu đã đổi'));
  check('stale_save_keeps_second_session_labels',(await state()).data.revision===concurrentState.data.revision);
  await page.locator('#ml-reload').click();await ready();await upload('identical');
  await page.setViewportSize({width:390,height:844});
  check('mobile_page_fits_viewport',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  check('mobile_conflict_controls_visible',await page.locator('#ml-label-policy').isVisible());
  await page.screenshot({path:path.join(OUT,'conflicts_mobile.png'),fullPage:true});
  check('other_company_data_and_model_untouched',JSON.stringify(await state('C002'))===JSON.stringify(other));
  const readContext=await browser.newContext({viewport:{width:390,height:844},locale:'vi-VN'}),readPage=await readContext.newPage();
  const readBase=BASE.replace(':8859',':8860');await readPage.goto(readBase+'/company-ml',{waitUntil:'networkidle'});
  check('readonly_update_locked',await readPage.locator('#ml-update').isDisabled());
  const readToken=(await (await readContext.request.get(readBase+'/api/meta')).json()).csrf_token;
  const forbidden=await readContext.request.post(readBase+'/api/company-ml/labels-preview',{headers:{'X-CSRF-Token':readToken},
    data:{company_id:'C001',expected_revision:concurrentState.data.revision,labels_text:lines[0]+'\n'+lines[1]+'\n'}});
  check('readonly_preview_blocked_on_server',forbidden.status()===403);
  check('no_browser_javascript_errors',errors.length===0);
  await readContext.close();
})().catch(error=>{errors.push(error.stack);process.exitCode=1;}).finally(async()=>{
  if(page&&process.exitCode)await page.screenshot({path:path.join(OUT,'failure.png'),fullPage:true}).catch(()=>{});
  fs.writeFileSync(path.join(OUT,'results.json'),JSON.stringify({checks,errors,writes},null,2));
  console.log(JSON.stringify({out:OUT,passed:checks.filter(check=>check.passed).length,total:checks.length,errors},null,2));
  if(browser)await browser.close();
});
