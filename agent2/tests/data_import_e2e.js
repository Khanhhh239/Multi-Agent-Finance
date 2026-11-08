"use strict";
// Run against tests/data_import_demo.py only; the marker/QA checks guard the target.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'C:/Users/Technical Support/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const ROOT=path.resolve(__dirname,'..'),BASE=process.env.DATA_IMPORT_DEMO_URL||'http://127.0.0.1:8861';
const SAMPLES=path.resolve(process.env.DATA_IMPORT_DEMO_ROOT||path.join(ROOT,'.runtime/data_import_ui_demo_20261106'));
const readonlyURL=new URL(BASE);readonlyURL.port=String(Number(readonlyURL.port)+1);
const OUT=path.join(ROOT,'.runtime/data_import_e2e_'+Date.now());fs.mkdirSync(OUT,{recursive:true});
const checks=[],errors=[];let browser,page;
function check(name,condition){checks.push({name,passed:!!condition});assert.ok(condition,name);}
async function state(company){const r=await page.request.get(BASE+'/api/company-ml/status?scenario=003&company='+company);assert.equal(r.status(),200);return r.json();}
async function importReady(){await page.waitForFunction(()=>!document.getElementById('import-reload').disabled&&document.getElementById('import-schema').textContent.includes('transaction_id'));}
async function mlReady(){await page.waitForFunction(()=>!document.getElementById('ml-reload').disabled&&document.getElementById('ml-current').textContent.trim());}
async function preview(file){
  await page.locator('#import-file').setInputFiles(path.join(SAMPLES,file));
  const response=page.waitForResponse(r=>r.url().endsWith('/api/data-import/preview'));
  await page.locator('#import-check').click();const r=await response;assert.equal(r.status(),200);return r.json();
}
async function save(){
  check('save_requires_acknowledgement',await page.locator('#import-save').isDisabled());
  await page.locator('#import-ack').check();
  const response=page.waitForResponse(r=>r.url().endsWith('/api/data-import/commit'));
  await page.locator('#import-save').click();const r=await response;assert.equal(r.status(),200);
  await page.waitForURL('**/company-ml?**');await mlReady();return {status:await state(await page.locator('#ml-company').inputValue())};
}
async function mlPost(selector,action){
  const response=page.waitForResponse(r=>r.url().endsWith('/api/company-ml/'+action));
  await page.locator(selector).click();const r=await response;const value=await r.json();assert.equal(r.status(),200,JSON.stringify(value));await mlReady();return value;
}
(async()=>{
  const marker=JSON.parse(fs.readFileSync(path.join(SAMPLES,'demo.json'),'utf8'));
  assert.notEqual(SAMPLES,path.join(ROOT,'.runtime/data_import_demo_20261104'),'Use an isolated import QA workspace; the main demo is locked to a comparison packet.');
  check('isolated_demo_marker',marker.kind==='synthetic-data-import-demo-v1'&&marker.is_synthetic);
  browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
  const context=await browser.newContext({viewport:{width:1365,height:1000},locale:'vi-VN',timezoneId:'Asia/Ho_Chi_Minh'});
  page=await context.newPage();page.setDefaultTimeout(30000);page.on('pageerror',error=>errors.push(error.message));
  check('qa_server',(await (await page.request.get(BASE+'/api/health')).json()).qa===true);
  await page.goto(BASE+'/data-import?company=C001&scenario=003',{waitUntil:'networkidle'});await importReady();
  check('file_input_enabled_for_manager',!(await page.locator('#import-file').isDisabled()));
  check('file_input_explains_ready_state',(await page.locator('#import-file-status').innerText()).includes('Đã sẵn sàng nhập dữ liệu cho C001'));
  const before=await state('C001');
  const downloadPromise=page.waitForEvent('download');await page.locator('#import-template').click();
  const download=await downloadPromise;await download.saveAs(path.join(OUT,download.suggestedFilename()));
  check('template_download',fs.readFileSync(path.join(OUT,'transactions_template.csv'),'utf8').includes('transaction_id,posted_at'));
  const invalid=await preview('SIMULATED_errors.csv');
  check('invalid_csv_blocked',!invalid.valid&&invalid.error_count>=2&&await page.locator('#import-save-section').isHidden());
  check('errors_explain_row_column_fix',(await page.locator('#import-errors').innerText()).includes('Cách sửa')&&invalid.errors.every(e=>e.row&&e.column&&e.fix));
  check('invalid_upload_no_change',(await state('C001')).data?.revision===before.data?.revision);
  await page.screenshot({path:path.join(OUT,'errors_desktop.png'),fullPage:true});
  let good=await preview('SIMULATED_C001.csv');
  check('csv_preview_features',good.valid&&good.feature_count>100&&good.summary.rows===30);
  check('leading_zeros_preserved',good.normalized_preview[0].transaction_id==='000000'&&good.normalized_preview[0].recipient_account==='000999');
  check('preview_no_database_change',(await state('C001')).data?.revision===before.data?.revision);
  check('replacement_and_missing_sources_explained',good.warnings.some(w=>w.includes('THAY THẾ'))&&good.warnings.some(w=>w.includes('chưa cung cấp')));
  await page.screenshot({path:path.join(OUT,'preview_desktop.png'),fullPage:true});
  await page.locator('#import-date-order').selectOption('dmy');
  check('option_change_invalidates_preview',await page.locator('#import-save-section').isHidden());
  good=await preview('SIMULATED_C001.csv');await save();
  check('handoff_correct_company',await page.locator('#ml-company').inputValue()==='C001');
  check('import_labels_action_separate',await page.locator('#ml-update').isDisabled()&&(await page.locator('#ml-source-note').innerText()).includes('CSV/Excel'));
  const results={};
  for(const [company,algorithm] of [['C001','isolation_forest'],['C002','ecod']]){
    console.log(company+': import, evaluate, activate, score, reload');
    if(company==='C002'){
      await page.goto(BASE+'/data-import?company=C002&scenario=003',{waitUntil:'networkidle'});await importReady();
      check('C002_selected_from_query',await page.locator('#import-company').inputValue()==='C002');
      const value=await preview('SIMULATED_C002.xlsx');check('xlsx_preview_features',value.valid&&value.summary.rows===30);
      await save();check('xlsx_handoff_correct_company',await page.locator('#ml-company').inputValue()==='C002');
    }
    const uploaded=await state(company);
    await page.locator('#ml-algorithm').selectOption(algorithm);
    const evaluated=await mlPost('#ml-evaluate','evaluate'),version=evaluated.versions[0];
    check(company+'_no_auto_activation',evaluated.active_version===uploaded.active_version&&version.algorithm===algorithm);
    await mlPost(`[data-ml-version="${version.version_id}"]`,'activate');
    const scored=await mlPost('#ml-score','score');check(company+'_correct_frozen_scorer',scored.run.version_id===version.version_id&&scored.items.every(r=>r.company_id===company));
    await page.reload({waitUntil:'networkidle'});await mlReady();
    check(company+'_reload_selection_and_model',await page.locator('#ml-company').inputValue()===company&&(await state(company)).active_version===version.version_id);
    // Refresh from an actual upload; this must keep artifact and binding.
    await page.locator('#ml-import-link').click();await importReady();
    check(company+'_import_link_scope',await page.locator('#import-company').inputValue()===company);
    await preview('SIMULATED_'+company+(company==='C001'?'.csv':'.xlsx'));const saved=await save();
    check(company+'_upload_preserves_model',saved.status.active_version===version.version_id&&saved.status.versions[0].artifact_sha256===version.artifact_sha256);
    const again=await mlPost('#ml-score','score');check(company+'_predictions_stable',JSON.stringify(again.items)===JSON.stringify(scored.items));
    results[company]={algorithm,version:version.version_id,rows:saved.status.data.rows,feature_count:saved.status.data.columns.length,score_rows:again.total};
  }
  check('company_models_independent',(await state('C001')).active_version===results.C001.version&&(await state('C002')).active_version===results.C002.version);
  // Add reviewed labels without replacing the imported records or matrix.
  const beforeLabels=await state('C002');
  const labels='company_id,transaction_id,label,reviewer_id,reviewed_at,evidence_ref,verified\nC002,000000,0,SIM_REVIEWER,2024-01-01T14:00:00+07:00,SIM_DOC,1\n';
  await page.locator('#ml-labels').setInputFiles({name:'SIMULATED_labels.csv',mimeType:'text/csv',buffer:Buffer.from(labels)});
  await mlPost('#ml-update','labels-preview');
  const labelled=await mlPost('#ml-label-save','labels-update');
  check('label_update_keeps_uploaded_data',labelled.data.source==='csv_excel_upload'&&labelled.data.rows===30&&labelled.data.labels_count===1&&labelled.data.source_sha256===beforeLabels.data.source_sha256&&labelled.active_version===results.C002.version);
  await page.goto(BASE+'/data-import?company=C002&scenario=003',{waitUntil:'networkidle'});await importReady();
  await preview('SIMULATED_C002.xlsx');
  await page.setViewportSize({width:390,height:844});
  check('mobile_no_page_overflow',await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
  await page.locator('#import-preview-section').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(OUT,'preview_mobile.png')});
  await page.setViewportSize({width:1365,height:1000});
  await page.locator('#import-company').selectOption('C001');await importReady();
  check('company_change_invalidates_preview',await page.locator('#import-save-section').isHidden()&&(await page.locator('#import-file').inputValue())==='');
  await page.goto(readonlyURL.origin+'/data-import',{waitUntil:'networkidle'});await importReady();
  check('accountant_readonly',await page.locator('#import-file').isDisabled()&&await page.locator('#import-check').isDisabled());
  check('readonly_lock_explained_beside_file',(await page.locator('#import-file-status').innerText()).includes('chỉ có quyền xem nên nút chọn tệp bị khóa'));
  check('accountant_only_own_company',(await page.locator('#import-company option').count())===1);
  await page.screenshot({path:path.join(OUT,'readonly_explanation.png'),fullPage:true});
  await page.route('**/api/meta',route=>route.abort('failed'),{times:1});
  await page.goto(BASE+'/data-import',{waitUntil:'networkidle'});
  await page.locator('#import-retry').waitFor({state:'visible'});
  check('initial_network_failure_has_inline_reason',(await page.locator('#import-file-status').innerText()).includes('Mất kết nối')&&await page.locator('#import-file').isDisabled());
  check('initial_network_failure_keeps_retry_enabled',!(await page.locator('#import-retry').isDisabled())&&!(await page.locator('#import-reload').isDisabled()));
  await page.locator('#import-retry').click();await importReady();
  check('retry_recovers_file_input',!(await page.locator('#import-file').isDisabled())&&await page.locator('#import-retry').isHidden());
  await page.route('**/api/data-import/context?*',route=>route.fulfill({status:404,contentType:'application/json',body:JSON.stringify({error:'Unknown route'})}),{times:1});
  await page.reload({waitUntil:'networkidle'});await page.locator('#import-retry').waitFor({state:'visible'});
  check('old_server_explanation_visible',(await page.locator('#import-file-status').innerText()).includes('chưa hỗ trợ nhập CSV/Excel'));
  await page.locator('#import-retry').click();await importReady();
  check('old_server_retry_recovers',!(await page.locator('#import-file').isDisabled()));
  check('no_browser_errors',errors.length===0);
  fs.writeFileSync(path.join(OUT,'results.json'),JSON.stringify({checks,errors,results},null,2));
  console.log(JSON.stringify({out:OUT,passed:checks.filter(c=>c.passed).length,total:checks.length,results},null,2));
})().catch(error=>{fs.writeFileSync(path.join(OUT,'failure.json'),JSON.stringify({message:error.message,stack:error.stack,checks,errors},null,2));console.error(error);process.exitCode=1;}).finally(async()=>{if(page)await page.screenshot({path:path.join(OUT,'last_screen.png'),fullPage:true}).catch(()=>{});if(browser)await browser.close();});
