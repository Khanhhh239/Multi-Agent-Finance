"use strict";
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'C:/Users/Technical Support/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const ROOT=path.resolve(__dirname,'..'),BASE='http://127.0.0.1:8765',WORK=path.join(ROOT,'.runtime/unified_8765_20261106');
const OUT=path.join(WORK,'browser_'+Date.now());fs.mkdirSync(OUT,{recursive:true});
const checks=[],errors=[],posts=[];let browser,page;
function check(name,value){checks.push({name,passed:!!value});assert.ok(value,name);}
async function status(company){const r=await page.request.get(BASE+'/api/company-ml/status?scenario=003&company='+company);assert.ok(r.ok());return r.json();}
async function mlReady(){await page.waitForFunction(()=>!document.getElementById('ml-reload').disabled&&document.getElementById('ml-score-readiness').getAttribute('aria-busy')==='false'&&document.getElementById('ml-current').textContent.trim());}
async function importReady(){await page.waitForFunction(()=>!document.getElementById('import-reload').disabled&&document.getElementById('import-schema').textContent.includes('transaction_id'));}
(async()=>{
  const profile=JSON.parse(fs.readFileSync(path.join(ROOT,'.runtime/review/server_8765.config.json'),'utf8'));
  check('explicit_local_qa_profile',profile.qa===true&&profile.demo_ml_manager===true);
  browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
  const context=await browser.newContext({viewport:{width:1365,height:1000},locale:'vi-VN',timezoneId:'Asia/Ho_Chi_Minh'});
  await context.route('**/api/**',route=>{
    const r=route.request();if(r.method()==='POST'){posts.push(r.url());if(!r.url().endsWith('/api/data-import/preview'))return route.abort('blockedbyclient');}
    return route.continue();
  });
  page=await context.newPage();page.setDefaultTimeout(30000);page.on('pageerror',error=>errors.push(error.message));
  const original={C001:await status('C001'),C002:await status('C002')};
  const overview=await (await page.request.get(BASE+'/api/company-ml')).json();
  check('manager_has_all_five_company_scopes',overview.can_manage&&overview.companies.length===5);
  await page.goto(BASE+'/',{waitUntil:'networkidle'});
  await page.waitForFunction(()=>document.querySelector('#scenario option'));
  check('main_queue_has_rows',(await (await page.request.get(BASE+'/api/cases?scenario=003&limit=1')).json()).total>1000);
  for(const href of ['/data-import','/company-ml','/ml-reviews'])check('navigation_'+href,await page.locator('.sidebar a[href="'+href+'"]').count()===1);
  check('all_navigation_stays_on_8765',await page.locator('.sidebar a[href^="/"]').evaluateAll(links=>links.every(link=>new URL(link.href).origin===location.origin)));
  await page.screenshot({path:path.join(OUT,'main_desktop.png'),fullPage:true});
  await page.locator('.sidebar a[href="/data-import"]').click();await importReady();
  check('upload_enabled_on_main_port',!(await page.locator('#import-file').isDisabled()));
  check('upload_uses_main_master_scope',await page.locator('#import-company option').count()===5);
  check('upload_ready_reason_visible',(await page.locator('#import-file-status').innerText()).includes('Đã sẵn sàng'));
  const downloadPromise=page.waitForEvent('download');await page.locator('#import-template').click();const download=await downloadPromise;
  await download.saveAs(path.join(OUT,'transactions_template.csv'));
  check('template_download_on_main_port',fs.readFileSync(path.join(OUT,'transactions_template.csv'),'utf8').includes('transaction_id'));
  await page.locator('#import-file').setInputFiles(path.join(WORK,'existing_source_sample.csv'));
  const previewReply=page.waitForResponse(r=>r.url().endsWith('/api/data-import/preview'));
  await page.locator('#import-check').click();const preview=await (await previewReply).json();
  check('main_source_csv_previews_with_194_features',preview.valid&&preview.feature_count===194&&preview.summary.rows===1);
  check('preview_keeps_commit_locked',await page.locator('#import-save').isDisabled());
  check('preview_preserves_transferred_dataset',(await status('C001')).data.revision===original.C001.data.revision);
  await page.screenshot({path:path.join(OUT,'import_preview_desktop.png'),fullPage:true});
  await page.goto(BASE+'/company-ml?company=C001&scenario=003',{waitUntil:'networkidle'});await mlReady();
  check('C001_active_model_preserved',(await status('C001')).active_version===original.C001.active_version);
  check('C001_active_model_can_score',!(await page.locator('#ml-score').isDisabled()));
  check('C001_keeps_thirty_rows',(await page.locator('#ml-data-summary').innerText()).includes('30 giao dịch'));
  check('CatBoost_stays_gated_for_missing_labels',await page.locator('option[value="catboost"]').evaluate(option=>option.disabled));
  await page.locator('#ml-company').selectOption('C002');await mlReady();
  check('C002_ECOD_active_preserved',(await status('C002')).active_version===original.C002.active_version&&(await page.locator('#ml-current').innerText()).includes('ECOD'));
  check('C002_active_model_can_score',!(await page.locator('#ml-score').isDisabled()));
  check('C002_keeps_verified_label',(await status('C002')).data.labels_count===original.C002.data.labels_count);
  await page.goto(BASE+'/ml-reviews',{waitUntil:'networkidle'});
  await page.waitForFunction(()=>!document.getElementById('review-reload').disabled&&document.getElementById('review-list').textContent.trim());
  const packets=await (await page.request.get(BASE+'/api/ml-reviews')).json();
  check('frozen_review_packet_visible',packets.packets.length===1);
  const units=await (await page.request.get(BASE+'/api/ml-reviews/units?packet='+packets.packets[0].packet_id)).json();
  check('twelve_review_units_preserved',units.total===12&&units.reviewed===0);
  const first=units.items[0],detail=await (await page.request.get(BASE+'/api/ml-reviews/detail?packet='+packets.packets[0].packet_id+'&review='+first.review_id)).json();
  check('review_evidence_is_blinded',!JSON.stringify(detail).includes('"algorithm"')&&!JSON.stringify(detail).includes('"rank"'));
  await page.screenshot({path:path.join(OUT,'reviews_desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  check('review_mobile_fits',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await page.goto(BASE+'/data-import',{waitUntil:'networkidle'});await importReady();
  check('upload_mobile_fits',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  check('upload_mobile_enabled',!(await page.locator('#import-file').isDisabled()));
  await page.screenshot({path:path.join(OUT,'import_mobile.png'),fullPage:true});
  check('both_company_states_unchanged',JSON.stringify(await status('C001'))===JSON.stringify(original.C001)&&JSON.stringify(await status('C002'))===JSON.stringify(original.C002));
  check('no_persistent_write_requests',posts.every(url=>url.endsWith('/api/data-import/preview')));
  check('no_browser_javascript_errors',errors.length===0);
})().catch(error=>{errors.push(error.stack);process.exitCode=1;}).finally(async()=>{
  if(page&&process.exitCode)await page.screenshot({path:path.join(OUT,'failure.png'),fullPage:true}).catch(()=>{});
  fs.writeFileSync(path.join(OUT,'results.json'),JSON.stringify({checks,errors,posts},null,2));
  console.log(JSON.stringify({out:OUT,passed:checks.filter(c=>c.passed).length,total:checks.length,errors},null,2));
  if(browser)await browser.close();
});
