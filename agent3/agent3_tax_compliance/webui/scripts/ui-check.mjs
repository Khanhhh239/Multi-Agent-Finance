// Isolated synthetic API + Chrome CDP checks. Never calls the user's running backend.
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
const root = fileURLToPath(new URL('../../src/assistant/static/', import.meta.url));
const output = fileURLToPath(new URL('../.qa/', import.meta.url));
fs.mkdirSync(output, { recursive: true });
const invoices = Array.from({ length: 65 }, (_, n) => ({ key: 'invoice-' + n, number: String(n + 1).padStart(6, '0'), template: '1', symbol: 'C26TAA', role: n % 3 ? 'PURCHASE' : 'SALE', issue_date: '2026-09-15', seller_name: 'Nhà cung cấp mô phỏng ' + n, seller_tax_id: '0109999982', buyer_name: 'Doanh nghiệp mô phỏng', gross: '11000000', vat: '1000000', guard_errors: [], signed: true, descriptions: ['Hàng hóa thử nghiệm'], file: n + '.xml' }));
const items = invoices.map((inv, n) => ({ code: 'R02_PAYMENT', invoice_keys: [inv.key], title: 'Cần bổ sung chứng từ thanh toán', status: n % 2 ? 'REVIEW' : 'AT_RISK', amount: '1000000', detail: 'Chưa có chứng từ thanh toán phù hợp.', action: 'Kiểm tra và bổ sung chứng từ.', basis: ['Căn cứ mô phỏng, không dùng để tư vấn thuế'] }));
const report = { meta: { as_of: '2026-10-15', period: ['2026-09-01', '2026-09-30'] }, invoices, items, matches: [], transactions: [], calendar: [], totals: { at_risk_vat: '33000000', at_risk_invoices: 33, penalty_estimate: '6600000', penalty_rate: .2, review_vat: '32000000', review_invoices: 32, opportunity_vat: '0' } };
const workspaces = ['demo-a','demo-b'].map((id) => ({ id, name: 'Công ty mô phỏng ' + id.toUpperCase(), tax_code: '0109999982', simulated: true, files: { purchase_xml: 65, sales_xml: 0, bank: 0, portal_list: 0 } }));
let asks = 0, decisions = 0, reportMode = 'normal';
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://local');
  if (url.pathname === '/frame') { res.setHeader('Content-Type', 'text/html'); res.end('<iframe title="Agent 3" style="width:100%;height:95vh;border:0" src="/?portal=http://127.0.0.1:8800#/?dn=demo-a"></iframe>'); return; }
  if (url.pathname.startsWith('/api/')) {
    let data = {};
    if (url.pathname === '/api/workspaces') data = workspaces;
    else if (url.pathname.endsWith('/report')) { res.statusCode = reportMode === 'missing' ? 404 : reportMode === 'error' ? 503 : 200; data = reportMode === 'normal' ? report : { detail:'Lỗi máy chủ mô phỏng' }; }
    else if (url.pathname.endsWith('/freshness')) data = { stale: false, analysed: true };
    else if (url.pathname.endsWith('/ai')) data = { model:'qwen3:8b', labelled_invoices:0, flagged_invoices:0, proposals:[], job:null };
    else if (url.pathname.endsWith('/ai/explain')) { res.statusCode = 503; data = { detail:'Mô hình chưa sẵn sàng' }; }
    else if (url.pathname.endsWith('/exposure')) data = {};
    else if (url.pathname.endsWith('/decisions/suggest')) data = { suggestion: null };
    else if (url.pathname.endsWith('/decisions') || url.pathname.endsWith('/decisions/bulk')) { decisions++; res.statusCode = 422; data = { detail: 'Lỗi lưu mô phỏng; dữ liệu biểu mẫu được giữ' }; }
    else if (url.pathname.endsWith('/ask')) { asks++; await new Promise((r) => setTimeout(r, 600)); data = { text: 'Câu trả lời mô phỏng ' + asks, branch: 'DATA', citations: [], facts: [], links: [] }; }
    else if (url.pathname.endsWith('/chat/suggestions')) data = ['Có bao nhiêu hóa đơn?', 'Hóa đơn nào cần xem?'];
    else if (url.pathname === '/api/chat/guide') data = { groups: [] };
    else if (url.pathname === '/api/admin/status') data = { configured:true, logged_in:false, ttl_minutes:20 };
    else if (url.pathname === '/api/law/status') data = { stats:null, job:{running:false}, changes:[] };
    else if (url.pathname === '/api/law/docs' || url.pathname.endsWith('/law-alerts') || url.pathname.endsWith('/coverage')) data = [];
    else if (url.pathname.endsWith('/vat-summary')) data = { rows:[], note:'Số liệu mô phỏng' };
    else if (url.pathname === '/api/schema') data = { profile:[], files:[], thresholds:[] };
    res.setHeader('Content-Type','application/json; charset=utf-8'); res.end(JSON.stringify(data)); return;
  }
  const pathname = url.pathname === '/' ? '/index.html' : url.pathname;
  const file = path.resolve(root, '.' + pathname);
  if (!file.startsWith(root) || !fs.existsSync(file) || !fs.statSync(file).isFile()) { res.statusCode=404; res.end(); return; }
  res.setHeader('Content-Type', ({'.html':'text/html; charset=utf-8','.js':'text/javascript','.css':'text/css','.woff2':'font/woff2','.woff':'font/woff'})[path.extname(file)] || 'application/octet-stream');
  res.end(fs.readFileSync(file));
});
await new Promise((r) => server.listen(0,'127.0.0.1',r));
const origin = 'http://127.0.0.1:' + server.address().port;
if (process.argv.includes('--serve')) { console.log(origin); } else {
  const chromePath = process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
  const profile = path.join(output, 'chrome-test-' + Date.now());
  const chrome = spawn(chromePath, ['--headless=new','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'], { stdio:'ignore', windowsHide:true });
  let ws;
  const sleep = (n) => new Promise((r) => setTimeout(r,n));
  const errors = [], results = [];
  try {
    const active = path.join(profile,'DevToolsActivePort');
    let port = '';
    for (let n=0; n<100; n++) {
      try {
        if (fs.existsSync(active)) {
          const content = fs.readFileSync(active, 'utf8');
          port = content.split('\n')[0].trim();
          if (port) break;
        }
      } catch (e) {}
      await sleep(100);
    }
    const target = await (await fetch('http://127.0.0.1:'+port+'/json/new?about:blank',{method:'PUT'})).json();
    ws = new WebSocket(target.webSocketDebuggerUrl);
    await new Promise((r,j) => { ws.onopen=r; ws.onerror=j; });
    let id=0; const pending = new Map();
    ws.onmessage = (e) => { const m=JSON.parse(e.data); if(m.id) { pending.get(m.id)?.(m); pending.delete(m.id); } else if (m.method==='Runtime.exceptionThrown') errors.push(m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text); };
    const send = (method,params={}) => new Promise((r,j) => { const i=++id; const t=setTimeout(()=>j(new Error('CDP timeout '+method)),15000); pending.set(i,(m)=>{clearTimeout(t);m.error?j(new Error(JSON.stringify(m.error))):r(m.result);}); ws.send(JSON.stringify({id:i,method,params})); });
    const evaluate = async (expression) => { const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true}); if(r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text); return r.result.value; };
    const wait = async (expression) => { for(let n=0;n<100;n++){if(await evaluate(expression))return;await sleep(50);}throw new Error('Wait: '+expression); };
    const go = async (hash) => { await evaluate(`location.hash=${JSON.stringify(hash)}`); await sleep(150); await wait('!!document.querySelector("h1.page")'); };
    const check = (name,value) => { assert.ok(value,name); results.push(name); console.log('PASS',name); };
    for (const asset of ['platform-theme.css','platform-theme.js','agent3-product.css','platform-fonts/bvp-vietnamese-400.woff2','platform-fonts/bvp-vietnamese-500.woff2','platform-fonts/bvp-vietnamese-600.woff2']) check('build asset '+asset,(await fetch(origin+'/assets/'+asset)).ok);
    await send('Page.enable'); await send('Runtime.enable');
    await send('Emulation.setEmulatedMedia',{features:[{name:'prefers-color-scheme',value:'light'}]});
    await send('Page.navigate',{url:origin+'/#/?dn=demo-a'});
    await wait('document.querySelector("#run")');
    check('overview workspace', await evaluate('document.querySelector("h1").textContent.includes("DEMO-A")'));
    check('product stylesheet order',await evaluate('[...document.querySelectorAll("link[rel=stylesheet]")].at(-1).href.includes("agent3-product")'));
    const widths=[1440,1024,768,390,320];
    for(const width of widths){
      await send('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:false});
      await sleep(80);
      check('overview no page overflow '+width,await evaluate('document.documentElement.scrollWidth<=innerWidth'));
      const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false}); fs.writeFileSync(path.join(output,'overview-'+width+'.png'),Buffer.from(shot.data,'base64'));
    }
    await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
    await go('#/hoa-don'); await wait('document.querySelector("#ilist tbody")');
    check('invoice page size 50',await evaluate('document.querySelectorAll("#ilist tbody tr").length===50'));
    await evaluate('document.querySelector("[data-sort=gross]").click()');
    check('sort aria state',await evaluate('document.querySelector("[data-sort=gross]").closest("th").getAttribute("aria-sort")==="descending"'));
    await evaluate('let q=document.querySelector("#iq");q.value="NOT-FOUND";q.dispatchEvent(new Event("input"))');
    check('empty filter result',await evaluate('!document.querySelector("#ilist tbody")'));
    await evaluate('document.querySelector("#reset-invoices").click()');
    check('reset invoice filter',await evaluate('document.querySelectorAll("#ilist tbody tr").length===50'));
    await evaluate('document.querySelector("#next").click()');
    check('invoice second page 15 rows',await evaluate('document.querySelectorAll("#ilist tbody tr").length===15'));
    await go('#/viec'); await wait('document.querySelector("[data-item]")');
    await evaluate('document.querySelector("[data-item]").focus();document.querySelector("[data-item]").click()');
    check('dialog focus and inert',await evaluate('document.activeElement.classList.contains("drawer") && document.querySelector("#app").inert'));
    await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape'});
    await wait('!document.querySelector(".drawer")');
    check('dialog restores focus',await evaluate('document.activeElement.matches("[data-item]") && !document.querySelector("#app").inert'));
    await evaluate('document.querySelector("[data-item]").click()');
    await evaluate('document.querySelector("[name=evidence]").value="Chứng từ mô phỏng";document.querySelector("[name=by]").value="Người duyệt thử";document.querySelector("#decide").requestSubmit()');
    await wait('document.querySelector("#dmsg").textContent.includes("Lỗi lưu")');
    check('failed decision retains form',await evaluate('document.querySelector("[name=evidence]").value==="Chứng từ mô phỏng" && !document.querySelector("#decide button").disabled'));
    await evaluate('document.querySelector("#close").click()');
    await evaluate('document.querySelector(".bulk-pick").click()');
    check('select row does not open dialog',await evaluate('!document.querySelector(".drawer") && !document.querySelector("#bulk").hidden'));
    await evaluate('document.querySelector("#bulk-ev").value="Chứng từ thử"; document.querySelector("#bulk-by").value="Kế toán thử";document.querySelector("#bulk-go").click()');await sleep(150);
    check('bulk failure retains values and unlocks',await evaluate('document.querySelector("#bulk-ev").value==="Chứng từ thử" && !document.querySelector("#bulk-go").disabled'));
    await go('#/hoi'); await wait('document.querySelector(".chip-q")');
    await evaluate('document.querySelector(".chip-q").click()');
    await wait('document.querySelector("#ask button[type=submit]").disabled');
    await go('#/hoa-don'); await sleep(800);
    check('late answer does not replace next page',await evaluate('document.querySelector("h1").textContent==="Hóa đơn"'));
    for(let n=0;n<3;n++){await go('#/hoi');await go('#/hoa-don');}
    await go('#/hoi'); await wait('document.querySelector(".chip-q")'); const before=asks;
    await evaluate('document.querySelector(".chip-q").click()'); await wait('document.querySelector(".msg-bot")');
    check('one request after repeated navigation', asks===before+1);
    await go('#/hoi');await wait('document.querySelector(".chip-q")');await evaluate('document.querySelector(".chip-q").click();let s=document.querySelector("#ws-select");s.value="demo-b";s.dispatchEvent(new Event("change"))');await sleep(900);
    check('workspace change cancels stale reply',await evaluate('document.querySelector("h1").textContent.includes("DEMO-B") && !document.querySelector(".msg-bot")'));
    await go('#/luat');await wait('document.querySelector("#lsearch")');
    check('law maintenance collapsed',await evaluate('!document.querySelector(".law-management").open'));
    for (const route of ['#/ngan-hang','#/so-lieu','#/lich','#/nap','#/giai-trinh']) {
      await go(route);await sleep(100);
      check('secondary page '+route,await evaluate('!!document.querySelector("h1.page") && !document.querySelector("#app > .cds--inline-notification--error")'));
    }
    await go('#/quan-tri'); await wait('document.querySelector("#admin-form")');
    await evaluate('document.querySelector("#admin-form").requestSubmit()');await sleep(50);
    check('linked validation summary',await evaluate('!!document.querySelector(".error-summary a") && !!document.querySelector("[aria-invalid=true]")'));
    reportMode='missing';await go('#/hoa-don');await sleep(100);
    check('no report state',await evaluate('document.querySelector("#app").textContent.includes("Chưa phân tích")'));
    reportMode='error';await go('#/');await sleep(100);
    check('server failure distinct from missing report',await evaluate('document.querySelector("#app").textContent.includes("Lỗi máy chủ mô phỏng")'));
    reportMode='normal';await go('#/hoa-don');
    await go('#/');await wait('document.querySelector("#run")');
    await evaluate('document.querySelector(".theme-toggle").click()');
    check('dark mode',await evaluate('document.body.classList.contains("cds--g100")'));
    await send('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});
    check('reduced motion',await evaluate('getComputedStyle(document.querySelector("#run")).transitionDuration==="0s"'));
    const dark=await send('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(output,'dark.png'),Buffer.from(dark.data,'base64'));
    await evaluate('document.documentElement.style.zoom="2"');await sleep(100);
    check('200 percent reflow',await evaluate('document.documentElement.scrollWidth<=innerWidth'));
    await evaluate('document.documentElement.style.zoom="";var selectedWorkspace=document.querySelector("#ws-select");selectedWorkspace.value="";selectedWorkspace.dispatchEvent(new Event("change"))');await sleep(150);
    check('no workspace welcome',await evaluate('!document.querySelector("#run") && document.querySelector("h1").textContent.includes("Agent 3")'));
    await send('Page.navigate',{url:origin+'/frame'});
    await wait(`!!document.querySelector('iframe')?.contentDocument?.querySelector('a[href="http://127.0.0.1:8800/#data"]')`);
    check('embedded intake uses validated portal link',await evaluate(`Array.from(document.querySelector('iframe').contentDocument.querySelectorAll('a')).some(a => a.href === 'http://127.0.0.1:8800/#data')`));
    check('no uncaught browser errors',errors.length===0);
    fs.writeFileSync(path.join(output,'ui-results.json'),JSON.stringify({passed:results,errors,asks,decisions,origin},null,2));
  } finally { ws?.close(); chrome.kill(); server.close(); }
}
