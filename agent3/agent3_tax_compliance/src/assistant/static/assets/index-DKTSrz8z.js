(function(){let e=document.createElement(`link`).relList;if(e&&e.supports&&e.supports(`modulepreload`))return;for(let e of document.querySelectorAll(`link[rel="modulepreload"]`))n(e);new MutationObserver(e=>{for(let t of e)if(t.type===`childList`)for(let e of t.addedNodes)e.tagName===`LINK`&&e.rel===`modulepreload`&&n(e)}).observe(document,{childList:!0,subtree:!0});function t(e){let t={};return e.integrity&&(t.integrity=e.integrity),e.referrerPolicy&&(t.referrerPolicy=e.referrerPolicy),t.credentials=e.crossOrigin===`use-credentials`?`include`:e.crossOrigin===`anonymous`?`omit`:`same-origin`,t}function n(e){if(e.ep)return;e.ep=!0;let n=t(e);fetch(e.href,n)}})();var e=(e,t=document)=>t.querySelector(e),t=e=>String(e??``).replace(/[&<>"']/g,e=>({"&":`&amp;`,"<":`&lt;`,">":`&gt;`,'"':`&quot;`,"'":`&#39;`})[e]),n=e=>{if(e==null||e===``)return`—`;let t=String(e);if(!/^-?\d+(\.\d+)?$/.test(t))return`Không xác định`;let[n,r=``]=t.split(`.`),i=r.replace(/0+$/,``);return n.replace(/\B(?=(\d{3})+(?!\d))/g,`.`)+(i?`,`+i:``)+` đ`};function r(e){if(e==null||e===``)return`<span class="kpi-amount-empty">—</span>`;let t=String(e);if(!/^-?\d+(\.\d+)?$/.test(t))return`<span class="kpi-amount-empty">Không xác định</span>`;let[n,r=``]=t.split(`.`),i=r.replace(/0+$/,``),a=n.startsWith(`-`),o=n.replace(/^-/,``).replace(/\B(?=(\d{3})+(?!\d))/g,`.`);return`<span class="kpi-money-wrap">
    ${a?`<span class="kpi-sign">-</span>`:``}
    <span class="kpi-digits">${o}</span>
    ${i?`<span class="kpi-tail">,${i}</span>`:``}
    <span class="kpi-currency-symbol">₫</span>
  </span>`}function i(e,t){let n=e=>String(e??`0`).split(`.`),[r,i=``]=n(e),[a,o=``]=n(t),s=Math.max(i.length,o.length),c=(e,t)=>BigInt((e.startsWith(`-`)?`-`:``)+e.replace(/^-/,``)+t.padEnd(s,`0`)),l=c(r,i),u=c(a,o);return l>u?1:l<u?-1:0}var a=e=>e?e.slice(0,10).split(`-`).reverse().join(`/`):``,o={get(e){try{return localStorage.getItem(e)}catch{return null}},set(e,t){try{localStorage.setItem(e,t)}catch{}}},s=new Map,c=new AbortController,l=[];function u(e){l.push(e)}function d(){return c.abort(),l.splice(0).forEach(e=>e()),c=new AbortController,c.signal}var f=()=>c.signal;async function p(e,t={}){let n=t.signal||c.signal,r=new Headers(t.headers),i=e.split(`?`)[0];e.startsWith(`/api/workspaces/`)&&(r.set(`X-Agent3-Profile-Revision`,k.platform?.profile_revision||``),t.method===`PUT`&&i.endsWith(`/pack`)&&s.has(i)&&r.set(`If-Match`,s.get(i)));let a=k.platform?.profile_revision,o=await fetch(e,{...t,headers:r,signal:n}),l=(o.headers.get(`content-type`)||``).includes(`json`)?await o.json():await o.text();if(n.throwIfAborted(),e.startsWith(`/api/workspaces/`)&&a!==k.platform?.profile_revision)throw new DOMException(`Context changed`,`AbortError`);if(o.headers.get(`etag`)&&s.set(i,o.headers.get(`etag`)),!o.ok&&l?.detail?.context_stale&&window.dispatchEvent(new Event(`agent3-context-stale`)),!o.ok){let e=Error(typeof l==`object`?l.detail?.message||l.detail||JSON.stringify(l):l);throw e.status=o.status,e}return l}var m=(e,t,n={})=>p(e,{...n,method:`POST`,headers:{"Content-Type":`application/json`,...n.headers},body:JSON.stringify(t??{})}),h=(e,t)=>p(e,{method:`PUT`,headers:{"Content-Type":`application/json`},body:JSON.stringify(t)});async function g(){let e=`/api/workspaces/${k.ws}/decisions`,t=await p(e);return{etag:s.get(e),events:t.events||[],report_revision:k.report?.meta.report_revision,workspace:k.ws,revision:k.platform?.profile_revision}}async function _(e,t,n){if(!n?.etag||!n.report_revision)throw Error(`Cần chạy phân tích và tải lại quyết định trước khi lưu.`);if(n.workspace!==k.ws||n.revision!==k.platform?.profile_revision)throw Error(`Hồ sơ đã thay đổi; không gửi quyết định cũ.`);let r=JSON.stringify(t);return r!==n.body&&(n.request_id=crypto.randomUUID(),n.body=r),m(e,{...t,request_id:n.request_id,report_revision:n.report_revision},{headers:{"If-Match":n.etag}})}async function v(e){let t=`/api/workspaces/${k.ws}/pack`,n=`/api/workspaces/${k.ws}/bank/formats`,r=await m(n,e,{headers:{"If-Match":s.get(t)||``}});return s.has(n)&&s.set(t,s.get(n)),r}var y=e=>e==null?`Chưa đủ dữ liệu / không áp dụng`:`${String(e).startsWith(`-`)?`Đầu vào vượt đầu ra`:`Đầu ra vượt đầu vào`}: ${n(String(e).replace(/^-/,``))}`,b=e=>{let t=Number(e);if(!Number.isFinite(t)||Math.abs(t)<1e6)return``;let n=e=>e.toLocaleString(`vi-VN`,{maximumFractionDigits:1});return Math.abs(t)>=0xe8d4a51000?`${n(t/0xe8d4a51000)} nghìn tỷ đồng`:Math.abs(t)>=1e9?`${n(t/1e9)} tỷ đồng`:`${n(t/1e6)} triệu đồng`},x={AT_RISK:[`Có nguy cơ bị loại`,`red`],REVIEW:[`Cần xem xét`,`magenta`],OPPORTUNITY:[`Có thể đang bỏ sót`,`blue`],INFO:[`Thông tin`,`gray`],LLM_VERIFIED:[`Đã kiểm tra căn cứ`,`green`],EXTRACTIVE:[`Trích nguyên văn`,`teal`],ABSTAIN:[`Không đủ căn cứ`,`gray`],DATA:[`Dữ liệu doanh nghiệp`,`cool-gray`],POLICY:[`Quy định`,`purple`],JUDGMENT:[`Cần chuyên gia`,`warm-gray`]},S=(e,n)=>{let[r,i]=x[e]||[n||e,`gray`];return`<div class="cds--tag cds--tag--${i}"><span class="cds--tag__label">${t(n||r)}</span></div>`},C=(e,n,r=``)=>`<div class="cds--inline-notification cds--inline-notification--${e} cds--inline-notification--low-contrast notice" role="${e===`error`?`alert`:`status`}">
  <div class="cds--inline-notification__details"><div class="cds--inline-notification__text-wrapper">
  <div class="cds--inline-notification__title">${t(n)}</div><div class="cds--inline-notification__subtitle">${t(r)}</div></div></div></div>`,w=(e=`Đang xử lý`)=>`<div class="bar kt-loading-wrap" style="display:inline-flex;align-items:center;gap:10px;padding:6px 0" aria-live="polite"><span class="kt-spinner teal" aria-hidden="true"></span><span class="muted" style="font-size:13px;font-weight:500">${t(e)}...</span></div>`,T=(e,n=`primary`,r=``)=>`<button ${/\btype=/.test(r)?``:`type="button" `}class="cds--btn cds--btn--${n} cds--btn--md" ${r}>${t(e)}</button>`,E=(e,n=``)=>{let r=`f-${e.key}`,i=e.help?`<div class="cds--form__helper-text">${t(e.help)}</div>`:``,a=e.required?``:` (không bắt buộc)`;if(e.type===`choice`)return`<div class="cds--form-item"><div class="cds--select"><label class="cds--label" for="${r}">${t(e.label)}${a}</label>
      <div class="cds--select-input__wrapper"><select class="cds--select-input" id="${r}" name="${e.key}" ${e.required?`required`:``}>
      ${e.choices.map(([e,r])=>`<option value="${t(e)}" ${e===n?`selected`:``}>${t(r)}</option>`).join(``)}</select></div>${i}</div></div>`;let o=Array.isArray(n)?n.join(`; `):n;return`<div class="cds--form-item cds--text-input-wrapper"><label class="cds--label" for="${r}">${t(e.label)}${a}</label>
    <div class="cds--text-input__field-wrapper"><input class="cds--text-input" id="${r}" name="${e.key}" value="${t(o)}" placeholder="${t(e.example||``)}" ${e.required?`required`:``}></div>${i}</div>`},D=(e,n,r=`Không có dữ liệu.`)=>n.length?`<div class="table-wrap"><table class="cds--data-table cds--data-table--md">
  <thead><tr>${e.map(e=>`<th${e.num?` class="num"`:``}><div class="cds--table-header-label">${t(e.label||e)}</div></th>`).join(``)}</tr></thead>
  <tbody>${n.join(``)}</tbody></table></div>`:`<div class="empty">${t(r)}</div>`;function O(e,n,r=`KHÔNG GIAN DOANH NGHIỆP`,i=``){let o=k.workspaces.find(e=>e.id===k.ws),s=k.report,c=s?.meta?.period?`Kỳ: ${a(s.meta.period[0])} - ${a(s.meta.period[1])}`:``;return`
    <div class="workspace-heading">
      <span class="top-label">TRỢ LÝ THUẾ GTGT</span>
      <span class="divider">/</span>
      <span id="breadcrumb">${t(e)}</span>
    </div>
    <div class="page-heading son-illustrated">
      <div>
        <div class="eyebrow">${t(r)}</div>
        <h1 class="page">${t(n)}</h1>
      </div>
    </div>
    ${o?`
    <div class="context-chips-bar">
      <span class="ctx-chip chip-company"><strong>${t(o.name)}</strong></span>
      <span class="ctx-chip chip-taxcode">MST: <code>${t(o.tax_code)}</code></span>
      ${c?`<span class="ctx-chip chip-period">${t(c)}</span>`:``}
      ${i}
    </div>`:``}
  `}var k={platform:null,ws:null,workspaces:[],report:null,schema:null},A=()=>e(`#app`),j=()=>new URLSearchParams(location.hash.split(`?`)[1]||``);async function M(){k.platform=await p(`/api/platform/context`),k.ws=k.platform.state===`ready`?k.platform.workspace_id:null,k.workspaces=k.ws?await p(`/api/workspaces`):[];let t=e(`#active-company`);t&&(t.textContent=k.platform.profile?`${k.platform.profile.legal_name} · MST ${k.platform.profile.tax_code}`:`Chưa kết nối doanh nghiệp`,t.title=t.textContent);let n=e(`#company-profile-link`);n&&(n.innerHTML=ee(`config`,`Hồ sơ chung`))}function ee(e=`config`,n=`Mở hồ sơ chung tại portal`){try{let r=new URL(k.platform?.portal_url);if(r.protocol===`http:`&&[`127.0.0.1`,`localhost`,`[::1]`].includes(r.hostname)&&!r.username&&!r.password)return`<a class="cds--btn cds--btn--tertiary" href="${t(r.origin)}/#${t(e)}" target="_top">${t(n)}</a>`}catch{}return`<p class="muted">Khởi động Agent 3 từ portal để kết nối hồ sơ doanh nghiệp chung.</p>`}var N=null;async function P(e=!1){if(!k.ws)return k.report=null,N=null,null;if(!e&&k.report&&N===k.ws)return k.report;try{k.report=await p(`/api/workspaces/${k.ws}/report`),N=k.ws}catch(e){if(e.status!==404)throw e;k.report=null,N=null}return k.report}var F=e=>k.report?.invoices.find(t=>t.key===e)||null,I=e=>e?`${e.template||``}${e.symbol||``}/${e.number||``}`:``;function L(){if(k.ws)return!1;let e={sync_required:`Hồ sơ đang chờ đồng bộ. Lưu lại hồ sơ tại portal hoặc khởi động lại Agent 3 từ portal.`,conflict:`Có nhiều dữ liệu trùng MST hoặc trùng dữ liệu mô phỏng. Cần kiểm tra trước khi liên kết.`,invalid_profile:`Hồ sơ chung chưa hợp lệ. Kiểm tra lại thông tin tại portal.`,missing_profile:`Chưa có hồ sơ doanh nghiệp chung. Hoàn tất hồ sơ tại portal.`};return A().innerHTML=`<h1 class="page">Kết nối hồ sơ doanh nghiệp</h1><p class="lead">${t(e[k.platform?.state]||`Agent 3 sử dụng doanh nghiệp do portal quản lý.`)}</p>${ee()}`,!0}function R(){try{let e=k.platform?.portal_url,t=new URL(e);if(t.protocol===`http:`&&[`127.0.0.1`,`localhost`].includes(t.hostname)&&!t.username&&!t.password&&t.origin!==location.origin)return t.origin}catch{}return null}function z(e){e.querySelectorAll(`a[href^="/api/workspaces/"]`).forEach(e=>{let t=new URL(e.href);t.searchParams.set(`profile_revision`,k.platform?.profile_revision||``),e.href!==t.href&&(e.href=t.href)});let t=R();t&&e.querySelectorAll(`a[href^="#/nap"], [data-go^="#/nap"]`).forEach(e=>{if((e.getAttribute(`href`)||e.dataset.go).includes(`b=chay`)){e.setAttribute(`href`,`#/`),e.dataset.go=`#/`,e.textContent=`Chạy phân tích ở Tổng quan`;return}let n=document.createElement(`a`);n.className=e.className,n.href=t+`/#data`,n.target=`_top`,e.closest(`#nav`)?n.innerHTML=`<span class="cds--side-nav__link-text">Nạp dữ liệu</span>`:n.textContent=`Nạp dữ liệu chung`,e.replaceWith(n)})}function te(){e(`#modal-root`).replaceChildren()}function B(){let t=e(`.drawer`);if(!t)return;let n=document.activeElement;t.setAttribute(`aria-modal`,`true`),t.tabIndex=-1;let r=document.createElement(`div`);r.className=`drawer-backdrop`,t.before(r);let i=[e(`#app`),e(`.side`),e(`header`)].filter(Boolean);i.forEach(e=>{e.inert=!0});let a=new AbortController,o=new MutationObserver(()=>{t.isConnected||s()}),s=()=>{o.disconnect(),a.abort(),r.remove(),i.forEach(e=>{e.inert=!1}),n?.isConnected&&n.focus({preventScroll:!0})};o.observe(e(`#modal-root`),{childList:!0});let c=()=>te();e(`#close`,t)?.addEventListener(`click`,c,{signal:a.signal}),r.addEventListener(`click`,c,{signal:a.signal}),document.addEventListener(`keydown`,e=>{if(e.key===`Escape`&&(e.preventDefault(),c()),e.key!==`Tab`)return;let n=[...t.querySelectorAll(`a[href],button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),[tabindex="0"]`)].filter(e=>e.getClientRects().length);n.length?e.shiftKey&&(document.activeElement===n[0]||document.activeElement===t)?(e.preventDefault(),n.at(-1).focus()):e.shiftKey||document.activeElement!==n.at(-1)&&document.activeElement!==t||(e.preventDefault(),n[0].focus()):(e.preventDefault(),t.focus())},{signal:a.signal}),t.focus({preventScroll:!0}),u(()=>{c(),s()})}function V(e){z(e),e.querySelectorAll(`.table-wrap`).forEach(e=>{e.tabIndex=0,e.setAttribute(`role`,`region`),e.setAttribute(`aria-label`,`Bảng dữ liệu, cuộn ngang để xem thêm cột`)}),e.querySelectorAll(`[data-go]`).forEach(e=>{e.tagName===`TR`&&(e.tabIndex=0,e.onkeydown=t=>{t.target===e&&[`Enter`,` `].includes(t.key)&&(t.preventDefault(),e.click())})}),e.querySelectorAll(`.bar:has(.filter-input)`).forEach(e=>{e.dataset.decorated||(e.dataset.decorated=`1`,e.classList.add(`toolbar`),e.querySelectorAll(`input[aria-label],select[aria-label]`).forEach(e=>{if(e.closest(`label`))return;let t=document.createElement(`label`);t.className=`filter-field`;let n=document.createElement(`span`);n.textContent=e.getAttribute(`aria-label`),e.before(t),t.append(n,e)}))})}function H(){document.addEventListener(`invalid`,e=>{e.preventDefault();let n=e.target.form;n&&queueMicrotask(()=>{let e=[...n.elements].filter(e=>e.validity&&!e.validity.valid);if(n.querySelectorAll(`.form-error,.error-summary`).forEach(e=>e.remove()),e.forEach((e,t)=>{e.id||=`invalid-`+t,e.setAttribute(`aria-invalid`,`true`);let n=document.createElement(`div`);n.className=`form-error`,n.id=e.id+`-error`,n.textContent=e.validationMessage,e.setAttribute(`aria-errormessage`,n.id),e.after(n)}),!e.length)return;let r=document.createElement(`div`);r.className=`error-summary`,r.tabIndex=-1,r.setAttribute(`role`,`alert`),r.innerHTML=`<strong>Kiểm tra lại thông tin</strong>`+e.map(e=>`<a href="#${t(e.id)}" data-error-field="${t(e.id)}">${t(e.labels?.[0]?.textContent||e.name||`Trường bắt buộc`)}: ${t(e.validationMessage)}</a>`).join(``),r.onclick=e=>{let t=e.target.closest(`[data-error-field]`);t&&(e.preventDefault(),document.getElementById(t.dataset.errorField)?.focus())},n.prepend(r),r.focus()})},!0),document.addEventListener(`input`,e=>{e.target.validity?.valid&&(e.target.removeAttribute(`aria-invalid`),document.getElementById(e.target.id+`-error`)?.remove(),e.target.removeAttribute(`aria-errormessage`))})}var U={date:`Ngày giao dịch`,debit:`Ghi nợ (tiền ra)`,credit:`Ghi có (tiền vào)`,description:`Nội dung`,counterparty_account:`Tài khoản đối ứng`,counterparty_name:`Tên đối ứng`};function W(e,n){return`<div class="drop" id="drop"><input type="file" id="file" multiple ${e?`accept="${t(e)}"`:``} class="cds--visually-hidden">
    ${T(`Chọn tệp`,`primary`,`id="pick"`)}<span class="muted">${t(n)}</span></div><div id="up"></div>`}function ne(t){let n=e(`#file`);e(`#pick`).onclick=()=>n.click(),n.onchange=()=>t([...n.files]);let r=e(`#drop`);r.ondragover=e=>{e.preventDefault(),r.classList.add(`over`)},r.ondragleave=()=>r.classList.remove(`over`),r.ondrop=e=>{e.preventDefault(),r.classList.remove(`over`),t([...e.dataTransfer.files])}}function re(e){let n=e.filter(e=>e.kind),r=Object.entries(n.reduce((e,t)=>({...e,[t.label]:(e[t.label]||0)+1}),{})).map(([e,t])=>`${t} ${e.toLowerCase()}`).join(`, `),i=e.filter(e=>!e.kind),a=n.filter(e=>/vẫn nạp để kiểm tra/.test(e.reason)),o=n.filter(e=>e.auto_format);return`${n.length?C(`success`,`Đã nhận ${n.length} tệp`,r):``}
    ${o.map(e=>C(`info`,`Sao kê ${e.file}: đã tự nhận dạng cột`,`Ngày: ${e.auto_format.columns.date}; ghi nợ: ${e.auto_format.columns.debit}; ghi có: ${e.auto_format.columns.credit}; nội dung: ${e.auto_format.columns.description}${e.auto_format.columns.counterparty_name?`; tên đối ứng: ${e.auto_format.columns.counterparty_name}`:`; chưa thấy cột tên đối ứng`}. Kiểm tra lại ở bước Sao kê ngân hàng nếu cần.`)).join(``)}
    ${a.length?C(`warning`,`${a.length} hóa đơn ghi sai mã số thuế doanh nghiệp`,a.map(e=>`${e.file}: ${e.reason}`).join(`; `)):``}
    ${i.length?`<div class="panel"><h3>${i.length} tệp không dùng</h3>${D([`Tệp`,`Lý do`],i.map(e=>`<tr><td class="mono">${t(e.file)}</td><td>${t(e.reason)}</td></tr>`))}</div>`:``}`}async function ie(t,n){let r=[];for(let[i,a]of t.entries()){e(`#up`).innerHTML=w(`Đang nạp ${i+1}/${t.length}: ${a.name}`);try{let e=await p(`${n}?name=${encodeURIComponent(a.name)}`,{method:`PUT`,body:a});r.push(...e.files||e.saved.map(e=>({file:e,kind:`ok`,label:`Tệp`,reason:``})))}catch(e){r.push({file:a.name,kind:null,label:`Không dùng`,reason:e.message})}}return await M(),r}function ae(e,r){if(!r.length)return`<div class="empty">Chưa có tệp.</div>`;let i=r.filter(e=>!e.ok).length,o=i?C(`warning`,`${i} trên ${r.length} tệp có lỗi`,`Xem cột Tình trạng; tệp lỗi vẫn được giữ, hệ thống báo trong Việc cần xử lý.`):C(`success`,`${r.length} tệp đọc tốt`);return e===`purchase_xml`||e===`sales_xml`?o+D([`Tệp`,`Hóa đơn`,`Ngày`,e===`purchase_xml`?`Người bán`:`Người mua`,{label:`Tổng thanh toán`,num:!0},`Tình trạng`],r.map(e=>`<tr><td class="mono small">${t(e.file)}</td><td>${t(e.number||``)}</td><td>${a(e.date)}</td><td>${t(e.party||``)}</td>
        <td class="num">${n(e.gross)}</td><td>${e.ok?S(`LLM_VERIFIED`,`Đọc tốt`):S(`AT_RISK`,`Có lỗi`)}<div class="muted small">${t((e.errors||[]).join(`, `))}</div></td></tr>`)):e===`bank`?o+D([`Tệp`,{label:`Giao dịch`,num:!0},`Từ ngày`,`Đến ngày`,`Tình trạng`,``],r.map(e=>`<tr><td class="mono small">${t(e.file)}</td>
      <td class="num">${e.rows??``}</td><td>${a(e.first)}</td><td>${a(e.last)}</td><td>${e.ok?S(`LLM_VERIFIED`,`Đọc tốt`):S(`AT_RISK`,`Chưa đọc được`)}<div class="muted small">${t((e.errors||[]).join(`, `))}</div></td>
      <td>${/\.(csv|xlsx)$/i.test(e.file)?T(e.ok?`Xem cột`:`Nhận dạng cột`,e.ok?`ghost`:`primary`,`data-suggest="${t(e.file)}"`):``}</td></tr>`)):o+D([`Tệp`,{label:`Số dòng`,num:!0},`Tình trạng`],r.map(e=>`<tr><td class="mono small">${t(e.file)}</td><td class="num">${e.rows??``}</td>
    <td>${e.ok?S(`LLM_VERIFIED`,`Đọc tốt`):S(`AT_RISK`,`Chưa đọc được`)}<div class="muted small">${t((e.errors||[]).join(`, `))}</div></td></tr>`))}async function oe(r){let i=e(`#suggest`);i.innerHTML=w(`Đang nhận dạng cột`);let o;try{o=await m(`/api/workspaces/${k.ws}/bank/suggest?name=${encodeURIComponent(r)}`)}catch(e){i.innerHTML=C(`error`,`Không nhận dạng được`,e.message);return}let s=structuredClone(o.format),c=e=>`<option value="">(không có)</option>${o.headers.map(n=>`<option ${n===e?`selected`:``}>${t(n)}</option>`).join(``)}`;i.innerHTML=`<div class="panel"><h3>Cột của ${t(r)}</h3><p class="muted">Hệ thống đã đoán cột ở dòng tiêu đề số ${o.header_row}. Nếu đoán sai, chọn lại; bản xem trước cập nhật ngay. Lưu mẫu một lần, lần sau tệp cùng ngân hàng được đọc tự động.</p>
    <div class="form-grid">${Object.keys(U).map(e=>`<div class="cds--form-item"><div class="cds--select"><label class="cds--label" for="m-${e}">${U[e]}${e===`date`||e===`debit`?``:` (không bắt buộc)`}</label>
      <div class="cds--select-input__wrapper"><select class="cds--select-input" id="m-${e}" data-col="${e}">${c(s.columns[e])}</select></div></div></div>`).join(``)}
      <div class="cds--form-item"><div class="cds--select"><label class="cds--label" for="m-num">Cách viết số tiền</label><div class="cds--select-input__wrapper"><select class="cds--select-input" id="m-num">
        <option value=".," ${s.thousands===`.`?`selected`:``}>1.234.567,00 (dấu chấm ngăn nghìn)</option><option value=",." ${s.thousands===`,`?`selected`:``}>1,234,567.00 (dấu phẩy ngăn nghìn)</option></select></div></div></div>
      <div class="cds--form-item"><div class="cds--select"><label class="cds--label" for="m-date">Cách viết ngày</label><div class="cds--select-input__wrapper"><select class="cds--select-input" id="m-date">
        ${[[`%d/%m/%Y`,`31/12/2026`],[`%Y-%m-%d`,`2026-12-31`],[`%d-%m-%Y`,`31-12-2026`],[`%d.%m.%Y`,`31.12.2026`]].map(([e,t])=>`<option value="${e}" ${s.date_format===e?`selected`:``}>${t}</option>`).join(``)}</select></div></div></div></div>
    <div id="pv"></div>
    <div class="bar" style="align-items:flex-end"><div class="cds--form-item cds--text-input-wrapper"><label class="cds--label" for="fmt-name">Tên mẫu (thường là tên ngân hàng)</label><input class="cds--text-input" id="fmt-name" value="${t(s.name)}"></div>
      ${T(`Lưu mẫu sao kê`,`primary`,`id="save-fmt"`)}<span id="fmt-msg"></span></div></div>`;let l=()=>(i.querySelectorAll(`[data-col]`).forEach(e=>{e.value?s.columns[e.dataset.col]=e.value:delete s.columns[e.dataset.col]}),[s.thousands,s.decimal]=e(`#m-num`).value.split(``),s.date_format=e(`#m-date`).value,s.name=e(`#fmt-name`).value||s.name,s),u=async()=>{e(`#pv`).innerHTML=w(`Đang đọc thử`);try{let i=await m(`/api/workspaces/${k.ws}/bank/preview?name=${encodeURIComponent(r)}`,l());e(`#pv`).innerHTML=`<h3 style="margin-top:1rem">Đọc thử ${i.preview.length} dòng đầu</h3>${i.errors?C(`warning`,`${i.errors} dòng không đọc được`,`Kiểm tra cách viết ngày và số tiền.`):``}
        ${D([`Ngày`,{label:`Tiền ra`,num:!0},{label:`Tiền vào`,num:!0},`Đối ứng`,`Nội dung`],i.preview.map(e=>e.error?`<tr><td colspan="5">${t(e.error)}</td></tr>`:`<tr><td>${a(e.date)}</td><td class="num">${n(e.debit)}</td><td class="num">${n(e.credit)}</td><td>${t(e.counterparty)}</td><td>${t(e.description)}</td></tr>`))}`}catch(t){e(`#pv`).innerHTML=C(`error`,`Chưa đọc được với cách chọn này`,t.message)}};i.querySelectorAll(`select`).forEach(e=>{e.onchange=u}),u(),e(`#save-fmt`).onclick=async()=>{let t=e(`#save-fmt`);t.disabled=!0;try{await v(l()),e(`#fmt-msg`).innerHTML=C(`success`,`Đã lưu mẫu; chạy lại phân tích để kiểm tra toàn bộ tệp`)}catch(t){e(`#fmt-msg`).innerHTML=C(`error`,`Không lưu được`,t.message)}finally{t.isConnected&&(t.disabled=!1)}},i.scrollIntoView({behavior:`smooth`,block:`start`})}async function se(){await p(`/api/workspaces/${k.ws}/pack`);let e=await p(`/api/workspaces/${k.ws}/details/bank`);A().innerHTML=`<h1 class="page">Nhận dạng cột sao kê</h1><p class="lead">Chỉnh cách đọc các tệp đã nạp. Lưu mẫu cần quyền quản trị; thao tác này không nạp thêm tệp.</p>${ae(`bank`,e)}<div id="suggest"></div>`,A().querySelectorAll(`[data-suggest]`).forEach(e=>{e.onclick=()=>oe(e.dataset.suggest)})}async function ce(){let n=await p(`/api/workspaces/${k.ws}/portal/lists`);A().innerHTML=`
    ${O(`Bảng kê`,`Bảng kê cổng thuế đang sử dụng`,`NGUỒN DỮ LIỆU ĐỐI SOÁT`)}
    <p class="lead" style="margin-top:10px">Các bản nguồn được giữ riêng. Chỉ bản được chọn mới được phân tích; chọn lại không xóa bản cũ.</p>
    ${n.error?C(`warning`,`Cần chọn bản bảng kê`,n.error):``}
    <form id="active-list"><label for="list-version">Bản nguồn</label><select id="list-version" class="cds--select-input" required><option value="">Chọn bảng kê</option>${n.files.map(e=>`<option value="${t(e)}" ${e===n.active?`selected`:``}>${t(e)}</option>`).join(``)}</select>
    <div class="bar">${T(`Sử dụng bản này`,`primary`,`type="submit"`)}<span id="list-result"></span></div></form>
    <a class="cds--btn cds--btn--ghost" href="#/quan-tri/mau-sao-ke">Nhận dạng cột sao kê (quản trị)</a>`,e(`#active-list`).onsubmit=async t=>{t.preventDefault();let n=t.target.querySelector(`button`);n.disabled=!0;try{await h(`/api/workspaces/${k.ws}/portal/active-list`,{name:e(`#list-version`).value}),e(`#list-result`).innerHTML=C(`success`,`Đã chọn bảng kê; chạy lại phân tích để áp dụng.`)}catch(t){e(`#list-result`).innerHTML=C(`error`,`Không đổi được bảng kê`,t.message)}finally{n.isConnected&&(n.disabled=!1)}}}async function le(){if(L())return;k.schema||=await p(`/api/schema`),await p(`/api/workspaces/${k.ws}/pack`);let r=k.workspaces.find(e=>e.id===k.ws),i=k.schema.files.filter(e=>e.folder),a=Object.values(r?.files||{}).reduce((e,t)=>e+(Number(t)||0),0),o=j().get(`b`),s=o===`chay`?`chay`:o===`nhanh`?`nhanh`:o?`da-nap`:a?`chay`:`nhanh`,c=`<h1 class="page">Nạp dữ liệu</h1><p class="lead">Doanh nghiệp tự xuất tệp từ cổng hóa đơn điện tử, ngân hàng điện tử và phần mềm đang dùng. Hệ thống không đăng nhập thay doanh nghiệp và không gửi dữ liệu ra ngoài máy này.</p>
    <nav class="steps">${[[`nhanh`,`Nạp tệp`],[`da-nap`,`Tệp đã nạp (${a})`],[`chay`,`Kiểm tra và chạy`]].map(([e,n],r)=>`<a href="#/nap?b=${e}" class="${e===s?`on`:``}"><span class="n">${r+1}</span>${t(n)}</a>`).join(``)}</nav>`;if(s===`nhanh`)A().innerHTML=`${c}<p>Thả cùng lúc mọi thứ đang có: tệp XML hóa đơn (mua vào và bán ra), tệp nén .zip, sao kê Excel, CSV hoặc MT940, bảng kê từ cổng thuế. Hệ thống tự nhận ra từng loại theo nội dung tệp, không cần đặt tên hay chia thư mục.</p>
      ${W(`.xml,.zip,.csv,.xlsx,.sta,.mt940,.txt`,`hoặc kéo thả tất cả vào đây`)}
      <details class="guide"><summary>Lấy các tệp này ở đâu</summary><div class="guide-body">${i.map(e=>`<p class="cell-title">${t(e.label)}</p><ol>${e.how.map(e=>`<li>${t(e)}</li>`).join(``)}</ol>`).join(``)}</div></details>`,ne(async t=>{let r=await ie(t,`/api/workspaces/${k.ws}/inbox`),i=Object.values(k.workspaces.find(e=>e.id===k.ws)?.files||{}).reduce((e,t)=>e+(Number(t)||0),0),a=A().querySelector(`.steps a[href="#/nap?b=da-nap"]`);if(a&&(a.lastChild.textContent=`Tệp đã nạp (${i})`),e(`#up`).innerHTML=`${re(r)}<div id="autorun">${w(`Đang tự chạy phân tích với dữ liệu mới`)}</div>`,r.some(e=>e.kind))try{let t=await m(`/api/workspaces/${k.ws}/run`),r=await p(`/api/workspaces/${k.ws}/coverage`);e(`#autorun`).innerHTML=C(`success`,`Đã phân tích xong`,`${t.items.length} việc; thuế có nguy cơ ${n(t.totals.at_risk_vat)}`)+r.filter(e=>e.level===`warning`).map(e=>C(`warning`,e.title,e.detail)).join(``)+`<div class="bar">${T(`Xem việc cần xử lý`,`primary`,`data-go="#/viec"`)}${T(`Về tổng quan`,`ghost`,`data-go="#/"`)}</div>`}catch(t){e(`#autorun`).innerHTML=C(`error`,`Phân tích chưa chạy được`,t.message)}else e(`#autorun`).innerHTML=``});else if(s===`chay`){A().innerHTML=`${c}<h2 class="section" style="margin-top:0">Kiểm tra trước khi phân tích</h2><div id="cov">${w(`Đang kiểm tra dữ liệu đã nạp`)}</div>
      <div class="bar">${T(`Chạy phân tích`,`primary`,`id="run2"`)}<span id="r2"></span></div>`,e(`#run2`).onclick=async()=>{e(`#r2`).innerHTML=w(`Đang phân tích`);try{await m(`/api/workspaces/${k.ws}/run`),location.hash=`#/`}catch(t){e(`#r2`).innerHTML=C(`error`,`Phân tích không chạy được`,t.message)}};try{let t=await p(`/api/workspaces/${k.ws}/coverage`);e(`#cov`).innerHTML=t.length?t.map(e=>C(e.level===`warning`?`warning`:`info`,e.title,e.detail)).join(``):C(`success`,`Dữ liệu đủ để phân tích`,`Có hóa đơn, sao kê phủ các tháng có hóa đơn và bảng kê cổng thuế.`)}catch(t){e(`#cov`).innerHTML=C(`error`,`Không kiểm tra được`,t.message)}}else A().innerHTML=`${c}${i.map(e=>`<h2 class="section">${t(e.label)} (${r?.files?.[e.key]??0})</h2><div id="det-${e.key}">${w(`Đang đọc từng tệp`)}</div>`).join(``)}<div id="suggest"></div>`,await Promise.all(i.map(async t=>{try{let n=await p(`/api/workspaces/${k.ws}/details/${t.key}`);e(`#det-${t.key}`).innerHTML=ae(t.key,n)}catch(n){e(`#det-${t.key}`).innerHTML=C(`error`,`Không đọc được danh sách tệp`,n.message)}})),A().querySelectorAll(`[data-suggest]`).forEach(e=>{e.onclick=()=>oe(e.dataset.suggest)})}function G(n,r=``,i=`success`){let a=e(`#toasts`);a||(a=document.createElement(`div`),a.id=`toasts`,document.body.appendChild(a));let o=document.createElement(`div`);o.className=`toast toast-${i}`,o.setAttribute(`role`,`status`),o.innerHTML=`<strong>${t(n)}</strong>${r?`<div>${t(r)}</div>`:``}`,a.appendChild(o),setTimeout(()=>{o.classList.add(`out`),setTimeout(()=>o.remove(),300)},4200)}async function ue(e){let t=[...e?.querySelectorAll(`button`)||[]];t.forEach(e=>{e.disabled=!0,e.setAttribute(`aria-busy`,`true`)});try{let e=await m(`/api/workspaces/${k.ws}/run`);return await M(),G(`Đã phân tích xong`,`${e.items.length} việc, thuế có nguy cơ ${Number(e.totals.at_risk_vat).toLocaleString(`vi-VN`)} đ`),window.dispatchEvent(new Event(`hashchange`)),e}catch(e){return e.name!==`AbortError`&&G(`Không chạy được phân tích`,e.message,`error`),null}finally{t.forEach(e=>{e.disabled=!1,e.removeAttribute(`aria-busy`)})}}async function de(n){if(n&&k.ws)try{let r=await p(`/api/workspaces/${k.ws}/freshness`);if(!r.stale){n.innerHTML=``;return}n.innerHTML=`<div class="banner banner-warn"><div><strong>${r.analysed?`Dữ liệu đã thay đổi sau lần phân tích gần nhất`:`Chưa có kết quả phân tích`}</strong>
      <div class="small">${r.analysed?`Số liệu đang hiển thị có thể đã cũ.`:`Nạp dữ liệu rồi chạy phân tích để xem kết quả.`}${r.reason?` `+t(r.reason):``}</div></div>
      <button type="button" class="cds--btn cds--btn--primary cds--btn--sm" id="fresh-run">Chạy phân tích ngay</button></div>`,e(`#fresh-run`).onclick=()=>ue(e(`#fresh-run`).parentElement)}catch{n.innerHTML=``}}function fe(e,n=new Date){let r=(e?.calendar||[]).filter(e=>{let t=(new Date(e.due)-n)/864e5;return t>=-3&&t<=7});return r.length?`<div class="banner banner-danger"><div><strong>Hạn sắp tới</strong><div class="small">${r.map(e=>`${t(e.period)}: ${a(e.due)} (${t(e.status)})`).join(`; `)}</div></div>
    <a class="cds--btn cds--btn--ghost cds--btn--sm" href="#/lich">Xem lịch thuế</a></div>`:``}async function pe(e,n){let r=e.files||{},i=null;try{i=await p(`/api/workspaces/${k.ws}/ai`)}catch{}let o=(n?.items||[]).filter(e=>e.status===`AT_RISK`||e.status===`REVIEW`).length,s=[[`Hồ sơ doanh nghiệp`,!0,`#/quan-tri/doanh-nghiep`,`Đã có`],[`Hóa đơn mua vào (XML)`,r.purchase_xml>0,`#/nap?b=nhanh`,r.purchase_xml?`${r.purchase_xml} tệp`:`Bắt buộc`],[`Sao kê ngân hàng`,r.bank>0,`#/nap?b=nhanh`,r.bank?`${r.bank} tệp`:`Nên có: thiếu thì mọi hóa đơn từ ngưỡng bị báo chưa có chứng từ`],[`Bảng kê từ cổng thuế`,r.portal_list>0,`#/nap?b=nhanh`,r.portal_list?`Đã có`:`Nên có: để phát hiện hóa đơn bỏ sót`],[`Chạy phân tích`,!!n,`#/nap?b=chay`,n?`ngày ${a(n.meta.as_of)}`:`Chưa chạy`],[`AI phân loại dòng hàng`,!!(i&&i.labelled_invoices),`#/viec`,i&&i.labelled_invoices?`${i.labelled_invoices} hóa đơn`:`Tùy chọn, chạy trên máy`],[`Xử lý việc cần làm`,n&&o===0,`#/viec`,n?o?`còn ${o} việc`:`Đã xử lý hết`:``]],c=s.find(e=>!e[1]);return`<details class="steps-card"><summary>Tiến độ kỳ này <span class="muted small">${c?` · Tiếp theo: ${t(c[0])}`:` · Đã xong các bước`}</span></summary><div class="steps-head">${c?`<a class="cds--btn cds--btn--primary cds--btn--sm" href="${c[2]}">Làm tiếp: ${t(c[0])}</a>`:`<span class="muted small">Đã xong các bước</span>`}</div>
    <ol class="checklist">${s.map(([e,n,r,i])=>`<li class="${n?`done`:``}"><a href="${r}"><span class="dot">${n?`✓`:``}</span><span>${t(e)}</span></a><span class="muted small">${t(i)}</span></li>`).join(``)}</ol></details>`}function me(n,r){if(!n||!r)return;let i=`agent3.seenRisky.${k.ws}`,a=[...new Set(r.items.filter(e=>e.code===`R08_RISKY_SELLER`).map(e=>e.invoice_keys[0].split(`|`)[0]))],o=null;try{o=JSON.parse(localStorage.getItem(i)||`null`)}catch{o=null}let s=o?a.filter(e=>!o.includes(e)):a;if(s.length){let c=s.map(e=>r.invoices.find(t=>t.seller_tax_id===e)?.seller_name||e),l=r.items.filter(e=>e.code===`R08_RISKY_SELLER`&&s.includes(e.invoice_keys[0].split(`|`)[0])).length;n.innerHTML=`<div class="banner banner-danger"><div><strong>${o?`Người bán mới xuất hiện trong danh sách rủi ro`:`Người bán đang nằm trong danh sách rủi ro`}</strong>
      <div class="small">${c.map(t).join(`, `)}: ${l} hóa đơn cần kiểm tra hợp đồng, giao nhận và thanh toán trước khi kê khai.</div></div>
      <div class="chips"><a class="cds--btn cds--btn--primary cds--btn--sm" href="#/viec?loc=REVIEW">Xem các hóa đơn</a><button type="button" class="cds--btn cds--btn--ghost cds--btn--sm" id="seen-ok">Đã biết</button></div></div>`,e(`#seen-ok`).onclick=()=>{try{localStorage.setItem(i,JSON.stringify(a))}catch{}n.innerHTML=``}}else n.innerHTML=``}var he=()=>window.dispatchEvent(new Event(`hashchange`)),ge=e=>e===`AI_VERIFIED`?S(`LLM_VERIFIED`,`AI, đã kiểm tra`):S(`INFO`,`Câu mẫu`);async function _e(e,n){e.innerHTML=`<div class="plain">${w(`Mô hình trên máy đang viết lời giải thích dễ hiểu`)}</div>`;try{let r=await m(`/api/workspaces/${k.ws}/ai/explain`,{index:n});e.innerHTML=`<div class="plain"><div class="bar" style="margin:0 0 .5rem">${ge(r.mode)}<span class="muted small">Nói đơn giản${r.note?` (${t(r.note)})`:``}</span></div>${t(r.text)}</div>`}catch{e.innerHTML=``}}async function ve(n){let r=f(),i=await p(`/api/workspaces/${k.ws}/ai`);if(r.aborted||!n.isConnected)return;let a=i.job,o=a&&a.running;n.innerHTML=`<div class="panel ai-panel"><h3>Trợ lý AI chạy trên máy (${t(i.model)})</h3>
    <p class="muted small">AI chỉ đề xuất; mọi đề xuất đã qua kiểm tra tự động và chỉ thành "cần xem xét", người duyệt quyết định. Dữ liệu không rời khỏi máy này.</p>
    <div class="bar">${T(o&&a.task===`phân loại dòng hàng`?`Đang phân loại ${a.done}/${a.total}`:`Phân loại dòng hàng (${i.labelled_invoices} hóa đơn đã phân loại, ${i.flagged_invoices} cần xem)`,`tertiary`,`id="ai-cls" ${o?`disabled`:``}`)}
    ${T(o&&a.task===`đọc nội dung chuyển khoản`?`Đang đọc nội dung chuyển khoản`:`Đọc nội dung chuyển khoản (${i.proposals.length} đề xuất chờ xác nhận)`,`tertiary`,`id="ai-bank" ${o?`disabled`:``}`)}
    ${i.proposals.length?T(`Xem đề xuất ghép`,`ghost`,`data-go="#/ngan-hang"`):``}</div>
    ${a&&a.error?C(`error`,`Việc AI bị lỗi`,a.error):``}${a&&!a.running&&a.result?C(`success`,`Xong: ${a.task}`,JSON.stringify(a.result).replace(/[{}"]/g,``).replace(`flagged:`,`hóa đơn cần xem: `).replace(`proposals:`,`đề xuất: `)):``}</div>`;let s=async e=>{try{await m(`/api/workspaces/${k.ws}/ai/${e}`),ve(n)}catch(e){n.insertAdjacentHTML(`beforeend`,C(`error`,`Không chạy được`,e.message))}};e(`#ai-cls`).onclick=()=>s(`classify`),e(`#ai-bank`).onclick=()=>s(`bank`);let c=n.dataset.wasRunning===`1`&&!o;if(n.dataset.wasRunning=o?`1`:`0`,c&&!document.querySelector(`.drawer`))he();else if(o){let e=setTimeout(()=>{document.body.contains(n)&&ve(n).catch(()=>{})},3e3);u(()=>clearTimeout(e))}}async function ye(r){let i=await p(`/api/workspaces/${k.ws}/ai`);if(!i.proposals.length){r.innerHTML=``;return}let s=await g(),c=o.get(`agent3.reviewer`)||``;r.innerHTML=`<h2 class="section">Đề xuất ghép từ nội dung chuyển khoản (${i.proposals.length})</h2>
    <p class="muted">Số tiền khớp chính xác; AI đọc nội dung chuyển khoản và tìm thấy cụm chữ nhắc tới người bán. Xác nhận thì hệ thống ghi quyết định có tên người duyệt và chạy lại.</p>
    <div class="bar" style="align-items:flex-end"><div class="cds--form-item cds--text-input-wrapper"><label class="cds--label" for="reviewer">Người duyệt</label><input class="cds--text-input" id="reviewer" value="${t(c)}" placeholder="Kế toán trưởng"></div></div>
    ${D([`Giao dịch`,{label:`Số tiền`,num:!0},`Nội dung chuyển khoản`,`Hóa đơn đề xuất`,`Căn cứ của AI`,``],i.proposals.map((e,r)=>`<tr>
      <td>${a(e.booked)}<div class="muted small">${t(e.source||``)}</div></td><td class="num">${n(e.amount)}</td><td>${t(e.description||``)}<div class="muted small">${t(e.counterparty_name||``)}</div></td>
      <td>${t(e.seller_name)}<div class="muted small">số ${t(e.invoice_number||``)}</div></td><td>cụm "<strong>${t(e.name_in_text)}</strong>", độ giống ${e.similarity}<div class="muted small">${t(e.reason)}</div></td>
      <td><div class="chips">${T(`Xác nhận`,`primary`,`data-acc="${r}"`)}${T(`Bác bỏ`,`ghost`,`data-rej="${r}"`)}</div></td></tr>`))}<div id="pmsg"></div>`;let l=async(t,n)=>{let a=e(`#reviewer`).value.trim();if(!a){e(`#pmsg`).innerHTML=C(`warning`,`Cần tên người duyệt`);return}o.set(`agent3.reviewer`,a);let c=[...r.querySelectorAll(`button`)];c.forEach(e=>{e.disabled=!0});try{let e=await _(`/api/workspaces/${k.ws}/ai/bank/decide`,{txn_id:i.proposals[t].txn_id,invoice_key:i.proposals[t].invoice_key,accept:n,by:a},s);e.report_pending&&G(`Quyết định đã lưu; cần chạy lại báo cáo`,e.message,`warning`),n&&window.sonStamp?.(a),he()}catch(t){e(`#pmsg`).innerHTML=C(`error`,`Không ghi được`,t.message)}finally{c.forEach(e=>{e.disabled=!1})}};r.querySelectorAll(`[data-acc]`).forEach(e=>{e.onclick=()=>l(Number(e.dataset.acc),!0)}),r.querySelectorAll(`[data-rej]`).forEach(e=>{e.onclick=()=>l(Number(e.dataset.rej),!1)})}async function be(){if(L())return;let r=await P();if(!r){A().innerHTML=`<h1 class="page">Giải trình</h1>${C(`info`,`Chưa phân tích`)}`;return}let i=[...new Set(r.items.filter(e=>e.status!==`INFO`).flatMap(e=>e.invoice_keys))].filter(e=>F(e));A().innerHTML=`
    ${O(`Giải trình`,`Giải trình với cơ quan thuế`,`HỒ SƠ GIẢI TRÌNH & BẢO VỆ SỐ LIỆU`)}
    <p class="lead" style="margin-top:10px">Khi nhận công văn yêu cầu giải trình hoặc bổ sung hồ sơ: chọn hóa đơn liên quan, dán nội dung công văn. Hệ thống gom hóa đơn XML, chứng từ thanh toán đã ghép, quyết định của người duyệt và điều khoản luật thành một tệp nén, kèm bản nháp thư. Mỗi đoạn thư ghi rõ dựa vào dữ kiện nào; đoạn có số liệu không khớp dữ kiện bị loại.</p>
    <div class="cds--form-item"><label class="cds--label" for="req">Nội dung công văn của cơ quan thuế (không bắt buộc)</label>
    <textarea class="cds--text-area" id="req" rows="4" placeholder="Ví dụ: Đề nghị doanh nghiệp giải trình việc kê khai khấu trừ thuế GTGT đầu vào của các hóa đơn mua hàng của Công ty TNHH Điện máy Thành Công trong quý 3/2026..."></textarea></div>
    <h2 class="section">Hóa đơn đưa vào hồ sơ</h2>
    <div class="bar"><input class="cds--text-input filter-input" id="dq" placeholder="Tìm số hóa đơn hoặc người bán" aria-label="Tìm hóa đơn"><span class="muted small" id="dcount"></span>
      ${T(`Chọn các hóa đơn đang hiện`,`ghost`,`id="dpick"`)}${T(`Bỏ chọn tất cả`,`ghost`,`id="dnone"`)}</div>
    <div id="dlist"></div>
    <div class="bar">${T(`Soạn thư và lập hồ sơ`,`primary`,`id="make"`)}<span id="mk"></span></div><div id="letter"></div>`;let o=50,s=new Set,c=i.map(e=>({k:e,i:F(e),its:r.items.filter(t=>t.invoice_keys.includes(e))})),l=()=>{let t=e(`#dq`).value.trim().toLowerCase();return t?c.filter(e=>`${I(e.i)} ${e.i.seller_name}`.toLowerCase().includes(t)):c},u=()=>{let r=l();e(`#dcount`).textContent=`${r.length} hóa đơn, đã chọn ${s.size}`,e(`#dlist`).innerHTML=D([``,`Hóa đơn`,`Người bán`,`Vấn đề`,{label:`Tổng thanh toán`,num:!0}],r.slice(0,o).map(({k:e,i:r,its:i})=>`<tr><td><input type="checkbox" class="pick" value="${t(e)}" ${s.has(e)?`checked`:``} aria-label="Chọn hóa đơn"></td>
      <td>${t(I(r))}<div class="muted small">${a(r.issue_date)}</div></td><td>${t(r.seller_name)}</td>
      <td><div class="chips" title="${t(i.map(e=>e.title).join(`; `))}">${i[0]?S(i[0].status,i[0].title):``}${i.length>1?`<span class="muted small">và ${i.length-1} vấn đề khác</span>`:``}</div></td><td class="num">${n(r.gross)}</td></tr>`),`Không có hóa đơn nào khớp.`)+(r.length>o?`<div class="bar"><span class="muted small">Đang hiện ${o} trên ${r.length}</span>${T(`Hiện thêm ${Math.min(50,r.length-o)}`,`ghost`,`id="dmore"`)}</div>`:``),A().querySelectorAll(`.pick`).forEach(t=>{t.onchange=()=>{t.checked?s.add(t.value):s.delete(t.value),e(`#dcount`).textContent=`${l().length} hóa đơn, đã chọn ${s.size}`}}),e(`#dmore`)&&(e(`#dmore`).onclick=()=>{o+=50,u()})};e(`#dq`).oninput=()=>{o=50,u()},e(`#dpick`).onclick=()=>{l().slice(0,o).forEach(e=>s.add(e.k)),u()},e(`#dnone`).onclick=()=>{s.clear(),u()},u(),e(`#make`).onclick=async()=>{let n=[...s];if(!n.length){e(`#mk`).innerHTML=C(`warning`,`Chọn ít nhất một hóa đơn`);return}let r=e(`#make`);r.disabled=!0,e(`#mk`).innerHTML=w(`Đang gom chứng từ và soạn thư bằng mô hình trên máy (khoảng 1 đến 2 phút)`);try{let r=await m(`/api/workspaces/${k.ws}/dossier`,{invoice_keys:n,request_text:e(`#req`).value});e(`#mk`).innerHTML=``;let i=r.letter;e(`#letter`).innerHTML=`<div class="panel"><div class="bar" style="margin-top:0">${ge(i.mode)}<span class="muted small">${t(i.note||``)}</span>
        <a class="cds--btn cds--btn--primary cds--btn--sm" href="/api/workspaces/${t(k.ws)}/dossier/${t(r.file)}">Tải hồ sơ (.zip)</a></div>
        <h3>Bản nháp thư</h3>${i.paragraphs.map(e=>`<p>${t(e.text)} <span class="muted small">${[...e.fact_ids,...e.passage_ids].map(t).join(`, `)}</span></p>`).join(``)}
        ${i.dropped&&i.dropped.length?C(`info`,`${i.dropped.length} đoạn của mô hình bị loại vì không qua kiểm tra`,i.dropped.map(e=>e.reason).join(`; `)):``}
        <h3>Dữ kiện</h3><ul>${r.facts.map(e=>`<li><strong>${t(e.id)}</strong> ${t(e.text)}</li>`).join(``)}</ul>
        ${r.passages.length?`<h3>Điều khoản</h3><ul>${r.passages.map(e=>`<li><strong>${t(e.pid)}</strong> <a href="${t(e.url)}" target="_blank" rel="noopener">${t(e.path)}</a></li>`).join(``)}</ul>`:``}
        <p class="muted small">Bản nháp; người có thẩm quyền phải đọc, sửa và ký trước khi gửi.</p></div>`}catch(t){e(`#mk`).innerHTML=C(`error`,`Không lập được hồ sơ`,t.message)}finally{r.isConnected&&(r.disabled=!1)}}}async function xe(){if(L())return;let r;try{r=await p(`/api/workspaces/${k.ws}/vat-summary`)}catch(e){if(e.name===`AbortError`)throw e;let t=[404,409].includes(e.status);A().innerHTML=`<h1 class="page">Số liệu thuế GTGT</h1>${C(t?`info`:`error`,t?`Cần chạy phân tích`:`Không tải được số liệu`,e.message)}`;return}let i=e=>e==null?``:Number(e)===0?S(`LLM_VERIFIED`,`Khớp`):`<span class="risk-text">${Number(e)>0?`+`:``}${n(e)}</span>`;A().innerHTML=`
    ${O(`Số liệu thuế GTGT`,`Số liệu thuế giá trị gia tăng`,`TỔNG HỢP & ĐỐI CHIẾU NGHĨA VỤ`)}
    <p class="lead" style="margin-top:10px">${t(r.note)}</p>
    ${D([`Kỳ`,`Thuế đầu ra`,`Thuế đầu vào`,`Không kê khai`,`Có nguy cơ`,`Chờ xem xét`,`Chưa phát hiện cảnh báo`,`Chênh lệch: chưa tính chờ duyệt`,`Chênh lệch: nếu chờ duyệt được chấp nhận`],r.rows.map(e=>`<tr><td>${t(e.period)}</td><td class="num">${n(e.output_vat)}</td><td class="num">${n(e.input_vat)}</td><td class="num">${n(e.not_claimed_vat)}</td><td class="num">${n(e.at_risk)}</td><td class="num">${n(e.review_vat)}</td><td class="num">${n(e.no_alert_vat)}</td><td>${y(e.scenario_without_review)}</td><td>${y(e.scenario_with_review)}</td></tr>`))}
    ${r.calculation_status===`UNSUPPORTED_DIRECT`?C(`warning`,`Chưa hỗ trợ tính thuế theo phương pháp trực tiếp`,`Chỉ hiển thị số liệu hóa đơn; không tính thuế phải nộp bằng công thức khấu trừ.`):``}
    <h2 class="section">Đối chiếu với số đã khai</h2>
    <p class="muted">Nhập số liệu lấy từ tờ khai để đối chiếu với hóa đơn đã nạp. Chênh lệch cần kiểm tra chứng từ, không tự chứng minh khai sai hay xác nhận đã nộp tờ khai.</p>
    <form id="decl">${D([`Kỳ`,`Đầu ra đã khai`,`Chênh lệch đầu ra`,`Đầu vào đã khai`,`Chênh lệch với phần chưa có cảnh báo`],r.rows.map(e=>`<tr><td>${t(e.period)}</td>
      <td><input class="cds--text-input decl" aria-label="Đầu ra đã khai ${t(e.period)}" data-p="${t(e.period_key)}" data-k="output_vat" value="${e.declared?.output_vat??``}" placeholder="vd 20.000.000" inputmode="numeric"></td><td>${i(e.diff_output)}</td>
      <td><input class="cds--text-input decl" aria-label="Đầu vào đã khai ${t(e.period)}" data-p="${t(e.period_key)}" data-k="input_vat" value="${e.declared?.input_vat??``}" placeholder="vd 15.084.000" inputmode="numeric"></td><td>${i(e.diff_input)}</td></tr>`))}
      <div class="bar">${T(`Lưu và đối chiếu`,`primary`,`type="submit"`)}</div></form>
    ${r.rows.some(e=>!e.sales)?C(`info`,`Chưa có hóa đơn bán ra ở một số kỳ`,`Chênh lệch chỉ phản ánh các tệp đã nạp; kiểm tra mức đầy đủ dữ liệu trước khi dùng số liệu.`):``}`,e(`#decl`).onsubmit=async e=>{e.preventDefault();let t=e.target.querySelector(`button[type=submit]`);t.disabled=!0;let n={};A().querySelectorAll(`.decl`).forEach(e=>{e.value.trim()&&(n[e.dataset.p]||={},n[e.dataset.p][e.dataset.k]=e.value.trim())});try{await p(`/api/workspaces/${k.ws}/declared`,{method:`PUT`,headers:{"Content-Type":`application/json`},body:JSON.stringify(n)}),G(`Đã lưu số đã khai`),he()}catch(e){G(`Không lưu được`,e.message,`error`)}finally{t.isConnected&&(t.disabled=!1)}}}async function Se(n){let r=await p(`/api/law/alerts`);r.length?(n.innerHTML=`<h2 class="section">Thay đổi luật cần chú ý (150 ngày qua và 180 ngày tới)</h2>
    ${D([`Ngày`,`Loại`,`Văn bản`,``],r.slice(0,40).map((e,n)=>`<tr><td>${a(e.day)}</td><td>${e.kind===`ENDED`?S(`AT_RISK`,`Hết hiệu lực`):S(`OPPORTUNITY`,`Có hiệu lực`)}</td>
      <td><a href="#/luat?doc=${t(e.doc_id)}">${t(e.doc_type)} ${t(e.doc_num)}</a><div class="muted small">${t((e.title||``).slice(0,150))}${e.by_doc_num?`; thay bằng ${t(e.by_doc_num)}`:``}</div><div id="sum-${n}"></div></td>
      <td>${e.kind===`EFFECTIVE`?T(`Tóm tắt điểm chính`,`ghost`,`data-sum="${n}"`):``}</td></tr>`))}`,n.querySelectorAll(`[data-sum]`).forEach(n=>{n.onclick=async()=>{let i=Number(n.dataset.sum),a=e(`#sum-${i}`);a.innerHTML=w(`Mô hình trên máy đang đọc văn bản (30 đến 90 giây)`);try{let e=await m(`/api/law/alerts/${encodeURIComponent(r[i].doc_id)}/summary`);a.innerHTML=`<div class="answer"><div class="chips">${S(e.mode)}</div>${e.sentences.map(e=>`<p style="margin:.4rem 0">${t(e.text)} <span class="muted small">[${e.citations.map(e=>t(e.path.split(` > `).slice(1).join(` > `))).join(`; `)}]</span></p>`).join(``)}
        ${e.dropped?.length?`<div class="cite">${e.dropped.length} câu bị loại vì không có căn cứ.</div>`:``}${e.note?`<div class="cite">${t(e.note)}</div>`:``}</div>`}catch(e){a.innerHTML=C(`error`,`Không tóm tắt được`,e.message)}}})):n.innerHTML=``}function Ce(t){t.innerHTML=`<h3 style="margin-top:1.5rem">Nhập danh sách từ tệp</h3><p class="muted small">Tệp CSV hoặc văn bản bất kỳ có mã số thuế (ví dụ danh sách doanh nghiệp bỏ địa chỉ kinh doanh do cơ quan thuế công bố). Hệ thống lấy mọi mã số thuế hợp lệ trong tệp.</p>
    <div class="form-grid"><div class="cds--form-item cds--text-input-wrapper"><label class="cds--label" for="rl-name">Tên danh sách</label><input class="cds--text-input" id="rl-name" placeholder="Danh sách bỏ địa chỉ kinh doanh tháng 10/2026"></div>
    <div class="cds--form-item cds--text-input-wrapper"><label class="cds--label" for="rl-date">Ngày của danh sách</label><input class="cds--text-input" id="rl-date" type="date"></div>
    <div class="cds--form-item cds--text-input-wrapper"><label class="cds--label" for="rl-src">Nguồn</label><input class="cds--text-input" id="rl-src" placeholder="Thông báo của Thuế tỉnh ..."></div></div>
    <div class="bar"><input type="file" id="rl-file" accept=".csv,.txt" class="cds--visually-hidden">${T(`Chọn tệp và nhập`,`secondary`,`id="rl-pick"`)}<span id="rl-msg"></span></div>`,e(`#rl-pick`).onclick=()=>{!e(`#rl-name`).value||!e(`#rl-date`).value?e(`#rl-msg`).innerHTML=C(`warning`,`Cần tên và ngày của danh sách`):e(`#rl-file`).click()},e(`#rl-file`).onchange=async()=>{let t=e(`#rl-file`).files[0];try{let n=await p(`/api/workspaces/${k.ws}/risk-list?name=${encodeURIComponent(e(`#rl-name`).value)}&as_of=${e(`#rl-date`).value}&source=${encodeURIComponent(e(`#rl-src`).value)}`,{method:`PUT`,body:t});e(`#rl-msg`).innerHTML=C(`success`,`Đã nhập ${n.tax_ids} mã số thuế`,n.rejected.length?`Bỏ qua mã sai: ${n.rejected.join(`, `)}`:`Chạy lại phân tích để áp dụng.`)}catch(t){e(`#rl-msg`).innerHTML=C(`error`,`Không nhập được`,t.message)}}}var we=()=>window.dispatchEvent(new Event(`hashchange`)),Te=[`id`,`flag`,`min_gross`,`description_contains`],Ee=e=>Object.fromEntries(Te.filter(t=>e[t]!==void 0&&e[t]!==``&&!(Array.isArray(e[t])&&!e[t].length)).map(t=>[t,e[t]]));function De(e,n,r,i=`pol`){return`<div class="preset ${r?`on`:``}" data-card="${n}"><input type="checkbox" data-${i}="${n}" ${r?`checked`:``} aria-label="Áp dụng">
    <div class="preset-body"><div class="preset-head"><strong>${t(e.flag)}</strong>${e.industry_fit?`<span class="badge-fit">Gợi ý cho ngành của bạn</span>`:e.recommended?`<span class="badge-rec">Nên dùng</span>`:``}${e.group?`<span class="muted small">${t(e.group)}</span>`:``}</div>
    <div class="preset-edit">
      <label>Nội dung nhắc<input class="cds--text-input" data-f="flag" value="${t(e.flag)}"></label>
      <label>Áp dụng từ số tiền (đồng)<input class="cds--text-input" data-f="min_gross" inputmode="numeric" value="${e.min_gross??``}" placeholder="mọi số tiền"></label>
      <label>Khi tên hàng có (cách nhau dấu phẩy)<input class="cds--text-input" data-f="description_contains" value="${t((e.description_contains||[]).join(`, `))}" placeholder="mọi hàng hóa"></label></div></div></div>`}function Oe(e){let t=t=>e.querySelector(`[data-f="${t}"]`).value.trim(),n=Number(t(`min_gross`).replace(/\D/g,``))||void 0;return{flag:t(`flag`),min_gross:n,description_contains:t(`description_contains`).split(`,`).map(e=>e.trim()).filter(Boolean)}}Array.from({length:12},(e,t)=>[String(t+1),`Tháng ${t+1}`]);async function ke(){L()}var Ae=e=>`<div class="panel shared-profile"><h2 class="section">Hồ sơ chung từ portal</h2><dl class="kv"><dt>Doanh nghiệp</dt><dd>${t(e.legal_name)}</dd><dt>Mã số thuế</dt><dd>${t(e.tax_code)}</dd><dt>Địa chỉ</dt><dd>${t(e.registered_address||`Chưa khai báo`)}</dd><dt>Ngành nghề</dt><dd>${t((e.industry||[]).join(`; `))}</dd><dt>Thuế GTGT / Kỳ khai</dt><dd>${e.vat_method===`DIRECT`?`Trực tiếp`:`Khấu trừ`} / ${e.filing_period===`MONTH`?`Tháng`:`Quý`}</dd><dt>Kết thúc năm tài chính</dt><dd>Tháng ${t(e.fiscal_year_end_month||12)}</dd></dl><p class="muted">Thông tin được quản lý tại portal. Agent 3 chỉ lưu thiết lập nghiệp vụ thuế riêng.</p>${ee()}</div>`;async function je(){if(L())return;k.schema||=await p(`/api/schema`);let n=await p(`/api/workspaces/${k.ws}/pack`),r=null,i=null,s={...structuredClone(n),custom:[],picked:null,edits:{}},c=`agent3.tax-draft.${k.platform.profile_revision}`,l=!1;u(()=>{if(!l){g();try{sessionStorage.setItem(c,JSON.stringify({...s,picked:s.picked?[...s.picked]:null}))}catch{}}});let d=Math.max(1,Math.min(5,Number(new URLSearchParams(location.hash.split(`?`)[1]||``).get(`buoc`)||1))),f=[`Quy định chi tiêu`,`Ngưỡng nội bộ`,`Nhóm hàng đặc thù`,`Ngày nghỉ`,`Xác nhận`],m=()=>{let u=`<nav class="steps">${f.map((e,n)=>`<a class="${n+1===d?`on`:n+1<d?`done`:``}" ${n+1<d?`data-step="${n+1}" href="javascript:void 0"`:``}><span class="n">${n+1<d?`✓`:n+1}</span>${t(e)}</a>`).join(``)}</nav>`,_=``;if(d===1){let e=(s.profile.industry||[]).join(`;`);if(!r||i!==e){p(`/api/presets?industry=${encodeURIComponent(e)}`).then(t=>{r=t.policies,i=e,s.picked===null&&(s.picked=new Set(s.policies.filter(e=>r.some(t=>t.id===e.id)).map(e=>e.id)),s.edits=Object.fromEntries(s.policies.map(e=>[e.id,e])),s.custom=s.policies.filter(e=>!r.some(t=>t.id===e.id))),m()}).catch(e=>{e.name!==`AbortError`&&(A().innerHTML=C(`error`,`Chưa tải được gợi ý`,e.message))}),A().innerHTML=`<h1 class="page">Thiết lập nghiệp vụ thuế</h1>${w(`Đang chọn gợi ý theo ngành nghề`)}`;return}}if(d===1){let e=(s.profile.industry||[]).map(e=>(String(e).match(/^\s*(\d{2,5})/)||[])[1]).filter(Boolean);_=`<p class="muted">Quy định chi tiêu nội bộ: mỗi quy định chỉ thêm nhắc nhở cho kế toán khi gặp hóa đơn phù hợp, không làm thay đổi kết quả theo luật.
        ${e.length?`Gợi ý theo ngành ${e.map(t).join(`, `)}.`:`Chưa có ngành nghề trong hồ sơ chung; chỉ hiển thị gợi ý chung.`} Sửa nội dung, số tiền, từ khóa theo quy chế của doanh nghiệp.</p>
        <div class="bar" style="margin-bottom:12px">
          ${T(`Chọn gợi ý theo ngành`,`tertiary`,`id="setup-sync-policies" type="button"`)}
          ${T(`Chọn tất cả gợi ý`,`ghost`,`id="setup-all-policies" type="button"`)}
        </div>
        <div class="preset-list">${r.map((e,t)=>De({...e,...s.edits[e.id]||{}},t,s.picked.has(e.id))).join(``)}</div>
        <h3 class="sub-h">Quy định riêng của doanh nghiệp</h3>
        <div id="custom-list">${s.custom.map((e,t)=>De({...e,recommended:!1},t,!0,`cus`)).join(``)||`<p class="muted small">Chưa có. Ví dụ: "Mua văn phòng phẩm từ 1 triệu cần phiếu đề xuất" khi tên hàng có "giấy, bút, mực in".</p>`}</div>
        <div class="bar">${T(`Thêm quy định riêng`,`ghost`,`id="add-pol"`)}</div>`}else _=d===2?`<p class="muted">Ngưỡng của doanh nghiệp chỉ được chặt hơn luật. Để trống để dùng mức theo luật.</p><div class="form-grid">
        ${E({key:`match_days_after_invoice`,label:`Số ngày tối đa từ ngày hóa đơn đến ngày thanh toán`,example:`90 (không quá 90)`,help:`Khoản chi trả quá số ngày này sau hóa đơn sẽ không được tự ghép.`},s.thresholds.match_days_after_invoice??``)}
        ${E({key:`non_cash_threshold_override`,label:`Ngưỡng nội bộ yêu cầu chuyển khoản (đồng)`,example:`ví dụ 2000000; để trống dùng 5.000.000 theo luật`,help:`Nếu công ty quy định mọi khoản từ 2 triệu phải chuyển khoản, nhập 2000000.`},s.thresholds.non_cash_threshold_override??``)}</div>`:d===3?`<p class="muted">Nhóm hàng đặc thù của ngành mà AI có thể hiểu nhầm là chi tiêu cá nhân. Ví dụ nhà hàng mua thực phẩm, spa mua mỹ phẩm, công ty du lịch mua vé máy bay. AI sẽ coi các nhóm này là phục vụ kinh doanh.</p>
        <div id="cats">${(s.ai_categories.length?s.ai_categories:[{name:``,description:``}]).map((e,n)=>`<div class="form-grid cat-row">
          <div class="cds--form-item cds--text-input-wrapper"><label class="cds--label">Tên nhóm</label><input class="cds--text-input" data-cat="${n}" data-k="name" value="${t(e.name)}" placeholder="Nguyên liệu thực phẩm"></div>
          <div class="cds--form-item cds--text-input-wrapper"><label class="cds--label">Mô tả</label><input class="cds--text-input" data-cat="${n}" data-k="description" value="${t(e.description)}" placeholder="thịt, cá, rau, gia vị dùng chế biến món ăn bán cho khách"></div></div>`).join(``)}</div>
        <div class="bar">${T(`Thêm nhóm`,`ghost`,`id="add-cat"`)}<span class="muted small">Không bắt buộc. Tối đa 10 nhóm.</span></div>`:d===4?`<p class="muted">Ngày nghỉ Tết và nghỉ bù do Chính phủ công bố hằng năm. Hạn nộp trùng ngày nghỉ sẽ được dời sang ngày làm việc kế tiếp (khoản 7 Điều 3 Nghị định 252/2026). Thứ Bảy, Chủ nhật và lễ cố định (1/1, 30/4, 1/5, 2/9) đã có sẵn.</p>
        <div class="bar" style="margin-bottom:12px">
          ${T(`Đồng bộ từ lịch nghỉ lễ hệ thống`,`tertiary`,`id="setup-sync-holidays" type="button"`)}
        </div>
        <div class="cds--form-item"><label class="cds--label" for="days">Mỗi dòng một ngày, dạng năm-tháng-ngày</label><textarea class="cds--text-area" id="days" rows="6" placeholder="2027-02-05&#10;2027-02-08">${t(s.days_off.join(`
`))}</textarea></div>`:`<p class="muted">Kiểm tra lại rồi lưu thiết lập nghiệp vụ thuế. Mọi mục đều sửa được sau trong trang Cấu hình doanh nghiệp.</p>
        <dl class="kv"><dt>Doanh nghiệp</dt><dd>${t(s.profile.legal_name||``)} (MST ${t(s.profile.tax_code||``)})</dd>
        <dt>Phương pháp, kỳ khai</dt><dd>${s.profile.vat_method===`DIRECT`?`Trực tiếp`:`Khấu trừ`}, ${s.profile.filing_period===`QUARTER`?`theo quý`:`theo tháng`}</dd>
        <dt>Năm tài chính kết thúc</dt><dd>tháng ${t(s.profile.fiscal_year_end_month||12)}</dd>
        <dt>Quy định chi tiêu</dt><dd>${s.policies.length?s.policies.map(e=>t(e.flag)).join(`<br>`):`không có`}</dd>
        <dt>Ngưỡng nội bộ</dt><dd>${Object.keys(s.thresholds).length?Object.entries(s.thresholds).map(([e,n])=>`${e===`match_days_after_invoice`?`Số ngày tối đa`:`Ngưỡng chuyển khoản`}: ${t(n)}`).join(`<br>`):`theo luật`}</dd>
        <dt>Nhóm hàng đặc thù</dt><dd>${s.ai_categories.length?s.ai_categories.map(e=>t(e.name)).join(`, `):`không có`}</dd>
        <dt>Ngày nghỉ thêm</dt><dd>${s.days_off.length?s.days_off.map(a).join(`, `):`không có`}</dd>
</dl><div id="setup-msg"></div>`;A().innerHTML=`<span class="eyebrow">Cấu hình nghiệp vụ thuế</span>
      <h1 class="page">Thiết lập nghiệp vụ thuế</h1>
      <p class="lead">Biến khung kiểm tra thuế dùng chung thành trợ lý thuế riêng của doanh nghiệp. Bước ${d}/${f.length}: <strong>${t(f[d-1])}</strong>.</p>
      ${Ae(s.profile)}${u}
      <form id="setup">
        <div class="panel" style="padding:26px 28px;border-radius:12px;box-shadow:var(--a3-shadow-sm);margin-bottom:20px;border:1px solid var(--cds-border-subtle)">${_}</div>
        <div class="bar">${d>1?T(`Quay lại`,`ghost`,`id="back"`):T(`Trở về cấu hình doanh nghiệp`,`ghost`,`data-go="#/quan-tri/doanh-nghiep"`)}${T(d===f.length?`Lưu thiết lập`:`Tiếp tục`,`primary`,`type="submit"`)}</div>
      </form>`,A().querySelectorAll(`[data-step]`).forEach(e=>{e.onclick=()=>{g(),d=Number(e.dataset.step),m()}}),e(`#back`)&&(e(`#back`).onclick=()=>{g(),--d,m()}),A().querySelectorAll(`[data-pol],[data-cus]`).forEach(e=>{e.onchange=()=>e.closest(`[data-card]`).classList.toggle(`on`,e.checked)}),e(`#add-pol`)&&(e(`#add-pol`).onclick=()=>{g(),s.custom.push({flag:`Quy định mới: sửa nội dung nhắc`,description_contains:[]}),m()}),e(`#add-cat`)&&(e(`#add-cat`).onclick=()=>{g(),s.ai_categories.length<10&&s.ai_categories.push({name:``,description:``}),m()}),e(`#setup-sync-policies`)&&(e(`#setup-sync-policies`).onclick=()=>{g();let e=0;r.forEach(t=>{(t.industry_fit||t.recommended)&&(s.picked.add(t.id),e++)}),m(),G(`Đã chọn ${e} quy định gợi ý theo ngành`)}),e(`#setup-all-policies`)&&(e(`#setup-all-policies`).onclick=()=>{g(),r.forEach(e=>s.picked.add(e.id)),m(),G(`Đã chọn tất cả gợi ý`)}),e(`#setup-sync-holidays`)&&(e(`#setup-sync-holidays`).onclick=async()=>{try{let t=(await p(`/api/admin/catalog/holidays`)).data?.years||{},n=[];for(let e in t)for(let r of t[e]||[])r.date&&/^\d{4}-\d{2}-\d{2}$/.test(r.date)&&n.push(r.date);let r=e(`#days`).value.split(/\s+/).map(e=>e.trim()).filter(e=>/^\d{4}-\d{2}-\d{2}$/.test(e)),i=Array.from(new Set([...r,...n])).sort();e(`#days`).value=i.join(`
`),s.days_off=i,G(`Đã đồng bộ ngày nghỉ từ hệ thống`,`Tổng cộng ${i.length} ngày`)}catch(e){G(`Chưa đồng bộ được lịch nghỉ`,e.message,`error`)}}),e(`#setup`).onsubmit=async t=>{if(t.preventDefault(),!g())return;if(d<f.length){d+=1,m();return}let r=e(`#setup button[type="submit"]`);r.disabled=!0,e(`#setup-msg`).innerHTML=w(`Đang lưu thiết lập`);try{let e={...n,policies:s.policies,thresholds:s.thresholds,ai_categories:s.ai_categories,days_off:s.days_off};await h(`/api/workspaces/${k.ws}/pack?by=${encodeURIComponent(o.get(`agent3.reviewer`)||``)}`,e),l=!0,sessionStorage.removeItem(c),G(`Đã lưu thiết lập nghiệp vụ thuế`,`Chạy lại phân tích để áp dụng`),location.hash=`#/quan-tri/doanh-nghiep`}catch(t){e(`#setup-msg`)&&(e(`#setup-msg`).innerHTML=C(`error`,`Chưa lưu được`,t.message))}finally{r.isConnected&&(r.disabled=!1)}}},g=()=>{let t=e(`#setup`);if(!t)return!0;if(d===1)s.picked=new Set,t.querySelectorAll(`[data-pol]`).forEach(e=>{let t=r[Number(e.dataset.pol)];s.edits[t.id]=Oe(e.closest(`[data-card]`)),e.checked&&s.picked.add(t.id)}),s.custom=[...t.querySelectorAll(`[data-cus]`)].filter(e=>e.checked).map(e=>({...s.custom[Number(e.dataset.cus)],...Oe(e.closest(`[data-card]`))})).filter(e=>e.flag),s.policies=[...r.filter(e=>s.picked.has(e.id)).map(e=>Ee({id:e.id,...s.edits[e.id]})),...s.custom.map((e,t)=>Ee({id:e.id||`RIENG_${t+1}`,...e}))];else if(d===2){let e=Object.fromEntries(new FormData(t).entries());if(s.thresholds={},e.match_days_after_invoice&&(s.thresholds.match_days_after_invoice=Number(e.match_days_after_invoice)),e.non_cash_threshold_override&&(s.thresholds.non_cash_threshold_override=Number(String(e.non_cash_threshold_override).replace(/\D/g,``))),(s.thresholds.match_days_after_invoice||0)>90)return G(`Số ngày không được quá 90 (chỉ được chặt hơn luật)`,``,`error`),!1;if((s.thresholds.non_cash_threshold_override||0)>5e6)return G(`Ngưỡng nội bộ không được cao hơn 5.000.000 đồng theo luật`,``,`error`),!1}else if(d===3){let e={};if(t.querySelectorAll(`[data-cat]`).forEach(t=>{e[t.dataset.cat]||={},e[t.dataset.cat][t.dataset.k]=t.value.trim()}),s.ai_categories=Object.values(e).filter(e=>e.name||e.description),s.ai_categories.some(e=>!e.name||!e.description))return G(`Mỗi nhóm cần cả tên và mô tả`,``,`error`),!1}else if(d===4&&(s.days_off=e(`#days`).value.split(/\s+/).map(e=>e.trim()).filter(Boolean),s.days_off.some(e=>!/^\d{4}-\d{2}-\d{2}$/.test(e))))return G(`Ngày phải có dạng năm-tháng-ngày, ví dụ 2027-02-05`,``,`error`),!1;return!0};try{let e=JSON.parse(sessionStorage.getItem(c)||`null`);e&&(Object.assign(s,e,{profile:n.profile}),s.picked=e.picked?new Set(e.picked):null)}catch{}m()}async function Me(){if(!k.ws){location.hash=`#/`;return}k.schema||=await p(`/api/schema`);let[r,i]=await Promise.all([p(`/api/workspaces/${k.ws}/pack`),p(`/api/workspaces/${k.ws}/pack/history`)]),s={policies:(await p(`/api/presets?industry=${encodeURIComponent((r.profile.industry||[]).join(`;`))}`)).policies},c=async(e,t)=>{try{await h(`/api/workspaces/${k.ws}/pack?by=${encodeURIComponent(o.get(`agent3.reviewer`)||``)}`,e),G(t||`Đã lưu cấu hình`,`Chạy lại phân tích để áp dụng`),await M(),we()}catch(e){G(`Không lưu được`,e.message,`error`)}},l={"ho-so":`<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>`,"ngan-hang":`<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2" y="5" width="20" height="14" rx="2"/><line x1="2" y1="10" x2="22" y2="10"/></svg>`,"bang-ke":`<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M9 21V9"/></svg>`,"quy-dinh":`<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>`,nguong:`<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 20v-6M6 20V10M18 20V4"/></svg>`,"nhom-hang":`<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m7.5 4.27 9 5.15"/><path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/></svg>`,"ngay-nghi":`<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>`,"rui-ro":`<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="7.86 2 16.14 2 22 7.86 22 16.14 16.14 22 7.86 22 2 16.14 2 7.86 7.86 2"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`,"lich-su":`<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`},u=(e,n,r,i)=>`<section class="cfg" id="cfg-${e}"><h2 class="section">${l[e]||``} <span>${t(n)}</span></h2><p class="section-desc">${t(r)}</p>${i}</section>`,d=r.ai_categories||[],f=(r.profile.industry||[]).map(e=>(String(e).match(/^\s*(\d{2,5})/)||[])[1]).filter(Boolean),g=f.length?`ngành VSIC ${f.join(`, `)}`:`ngành`,_=`
    <div class="panel" style="border-radius:12px;padding:18px 22px;background:var(--a3-surface);border:1px solid var(--cds-border-subtle);margin-bottom:24px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:16px;box-shadow:var(--a3-shadow-sm)">
      <div style="max-width:650px">
        <h4 style="margin:0 0 6px 0;font-size:15px;font-weight:600;display:flex;align-items:center;gap:8px">
          <span>🧭</span> Hướng dẫn thiết lập nghiệp vụ thuế (Wizard 5 bước)
        </h4>
        <p class="muted small" style="margin:0;line-height:1.55">Trình hỗ trợ thiết lập tuần tự: chọn quy định chi tiêu, ngưỡng kiểm soát, nhóm hàng AI và ngày nghỉ theo từng bước có giải thích chi tiết.</p>
      </div>
      <div class="bar" style="margin:0">
        ${T(`Chạy wizard thiết lập 5 bước`,`secondary`,`data-go="#/thiet-lap"`)}
      </div>
    </div>`;A().innerHTML=`<span class="eyebrow">Cấu hình riêng của doanh nghiệp</span>
    <h1 class="page">${t(r.profile.legal_name)}</h1>
    <p class="lead">Thiết lập các tham số, quy định chi tiêu, ngưỡng kiểm soát và danh mục đặc thù khớp với doanh nghiệp của bạn. Khung kiểm tra luật thuế dùng chung luôn được bảo toàn.</p>
    ${_}
    <nav class="cfg-nav">${[[`ho-so`,`Hồ sơ`],[`ngan-hang`,`Mẫu sao kê`],[`bang-ke`,`Cột bảng kê`],[`quy-dinh`,`Quy định chi tiêu`],[`nguong`,`Ngưỡng`],[`nhom-hang`,`Nhóm hàng đặc thù`],[`ngay-nghi`,`Ngày nghỉ`],[`rui-ro`,`Danh sách rủi ro`],[`lich-su`,`Lịch sử thay đổi`]].map(([e,n])=>`<a href="javascript:void 0" data-jump="cfg-${e}">${t(n)}</a>`).join(``)}</nav>
    <section id="cfg-ho-so">${Ae(r.profile)}</section>
    ${u(`ngan-hang`,`Mẫu sao kê ngân hàng`,`Mỗi ngân hàng một mẫu; chỉnh cột từ sao kê đã nạp.`,D([`Tên mẫu`,`Cột ngày`,`Cột tiền ra`,`Cột tiền vào`,`Cách viết số`,``],(r.bank_formats||[]).map((e,n)=>`<tr><td>${t(e.name)}</td><td class="mono">${t(e.columns.date)}</td>
      <td class="mono">${t(e.columns.debit)}</td><td class="mono">${t(e.columns.credit||``)}</td><td>${e.thousands===`.`?`1.234.567`:`1,234,567`}</td><td>${T(`Xóa`,`ghost`,`data-delfmt="${n}"`)}</td></tr>`),`Chưa có mẫu. Nạp sao kê tại portal rồi mở Nhận dạng cột.`)+`<div class="bar">${T(`Nhận dạng cột từ sao kê đã nạp`,`ghost`,`data-go="#/quan-tri/mau-sao-ke"`)}</div>`)}
    ${u(`bang-ke`,`Cột của bảng kê cổng thuế`,`Khi cổng hóa đơn điện tử đổi mẫu tệp xuất, chọn lại cột ở đây; không cần sửa tệp.`,`<div id="portal-map"><div class="bar">`+T(`Đọc tiêu đề bảng kê đã nạp`,`ghost`,`id="portal-load"`)+`</div></div>`)}
    ${u(`quy-dinh`,`Quy định chi tiêu nội bộ`,`Chỉ thêm nhắc nhở cho kế toán, không thay đổi kết quả theo luật.`,`
      <div class="bar" style="margin-bottom:14px">
        ${T(`Chọn gợi ý theo ${g}`,`tertiary`,`id="sync-industry-policies" type="button"`)}
        ${T(`Chọn tất cả gợi ý`,`ghost`,`id="select-all-presets" type="button"`)}
        ${T(`Bỏ chọn tất cả`,`ghost`,`id="deselect-all-presets" type="button"`)}
      </div>
      <div class="preset-list">${s.policies.map((e,i)=>`<label class="preset"><input type="checkbox" data-preset="${i}" ${(r.policies||[]).some(t=>t.id===e.id)?`checked`:``}>
      <span><strong>${t(e.flag)}</strong>${e.industry_fit?`<span class="badge-fit">Gợi ý cho ngành của bạn</span>`:``}<span class="muted small">${e.min_gross?`từ ${n(e.min_gross)}`:``}${e.description_contains?` khi tên hàng có: ${e.description_contains.map(t).join(`, `)}`:``}</span></span></label>`).join(``)}
      ${(r.policies||[]).filter(e=>!s.policies.some(t=>t.id===e.id)).map(e=>`<label class="preset"><input type="checkbox" checked data-custom="${t(e.id)}"><span><strong>${t(e.flag)}</strong><span class="muted small">quy định riêng</span></span></label>`).join(``)}</div>
      <form id="f-pol" style="margin-top:.75rem"><div class="form-grid">${E({key:`flag`,label:`Thêm quy định riêng: nội dung nhắc`,example:`Mua văn phòng phẩm từ 1 triệu cần phiếu đề xuất`})}${E({key:`min_gross`,label:`Áp dụng từ số tiền (đồng)`,example:`1000000`})}${E({key:`description_contains`,label:`Tên hàng có chứa (cách nhau dấu chấm phẩy)`,example:`giấy; bút; mực in`})}</div>
      <div class="bar">${T(`Lưu quy định`,`primary`,`type="submit"`)}</div></form>`)}
    ${u(`nguong`,`Ngưỡng nội bộ`,`Chỉ được chặt hơn luật; để trống để dùng mức theo luật.`,`<form id="f-th"><div class="form-grid">
      ${E({key:`match_days_after_invoice`,label:`Số ngày tối đa từ ngày hóa đơn đến ngày thanh toán`,example:`90 (không quá 90)`},r.thresholds?.match_days_after_invoice??``)}
      ${E({key:`non_cash_threshold_override`,label:`Ngưỡng nội bộ yêu cầu chuyển khoản (đồng)`,example:`để trống dùng 5.000.000 theo luật`},r.thresholds?.non_cash_threshold_override??``)}</div>
      <div class="bar">${T(`Lưu ngưỡng`,`primary`,`type="submit"`)}</div></form>`)}
    ${u(`nhom-hang`,`Nhóm hàng đặc thù cho AI`,`AI coi các nhóm này là phục vụ kinh doanh khi phân loại dòng hàng (ví dụ nhà hàng mua thực phẩm). Chạy lại Phân loại dòng hàng sau khi đổi.`,`<form id="f-cat">
      <div class="bar" style="margin-bottom:12px">
        ${T(`Nạp gợi ý nhóm hàng từ hệ thống`,`tertiary`,`id="sync-cats-sys" type="button"`)}
      </div>
      <div id="cat-rows-container">
      ${(d.length?d:[{name:``,description:``}]).concat([{name:``,description:``}]).map((e,n)=>`<div class="form-grid cat-row">
        <div class="cds--form-item cds--text-input-wrapper"><label class="cds--label">Tên nhóm</label><input class="cds--text-input" data-cat="${n}" data-k="name" value="${t(e.name)}" placeholder="Nguyên liệu thực phẩm"></div>
        <div class="cds--form-item cds--text-input-wrapper"><label class="cds--label">Mô tả</label><input class="cds--text-input" data-cat="${n}" data-k="description" value="${t(e.description)}" placeholder="thịt, cá, rau dùng chế biến món ăn"></div></div>`).join(``)}
      </div>
      <div class="bar">${T(`Lưu nhóm hàng`,`primary`,`type="submit"`)}</div></form>`)}
    ${u(`ngay-nghi`,`Ngày nghỉ trong năm`,`Tết và nghỉ bù do Chính phủ công bố hằng năm; thứ Bảy, Chủ nhật và lễ cố định đã có sẵn.`,`<form id="f-days">
      <div class="bar" style="margin-bottom:12px">
        ${T(`Đồng bộ từ lịch nghỉ lễ hệ thống`,`tertiary`,`id="sync-holidays-sys" type="button"`)}
      </div>
      <div class="cds--form-item"><textarea class="cds--text-area" id="days" rows="5" placeholder="2026-02-16&#10;2026-02-17&#10;2027-02-05">${t((r.days_off||[]).join(`
`))}</textarea></div>
      <div class="bar">${T(`Lưu ngày nghỉ`,`primary`,`type="submit"`)}<span id="days-msg" class="muted small"></span></div></form>`)}
    ${u(`rui-ro`,`Danh sách doanh nghiệp rủi ro`,`Người bán trong danh sách sẽ được gắn cờ cần xem; luôn ghi ngày và nguồn.`,D([`Tên danh sách`,`Ngày`,{label:`Số mã số thuế`,num:!0},`Nguồn`],(r.reference_lists||[]).map(e=>`<tr><td>${t(e.name)}</td><td>${a(e.as_of)}</td><td class="num">${e.tax_ids.length}</td><td>${t(e.source||``)}</td></tr>`),`Chưa có.`)+`<div id="riskimp"></div>`)}
    ${u(`lich-su`,`Lịch sử thay đổi cấu hình`,`Ai đổi phần nào, lúc nào.`,D([`Thời điểm`,`Người`,`Phần thay đổi`],i.slice(0,30).map(e=>`<tr><td>${t(e.at.replace(`T`,` `))}</td><td>${t(e.by)}</td><td>${e.created?`Tạo doanh nghiệp`:t(e.changed.join(`, `))}</td></tr>`),`Chưa có thay đổi nào được ghi.`))}`,A().querySelectorAll(`[data-jump]`).forEach(e=>{e.onclick=()=>document.getElementById(e.dataset.jump).scrollIntoView({block:`start`})}),A().querySelectorAll(`[data-delfmt]`).forEach(e=>{e.onclick=()=>c({...r,bank_formats:r.bank_formats.filter((t,n)=>n!==Number(e.dataset.delfmt))},`Đã xóa mẫu sao kê`)});let v=e(`#sync-industry-policies`);v&&(v.onclick=()=>{let e=0;s.policies.forEach((t,n)=>{let r=A().querySelector(`[data-preset="${n}"]`);r&&(t.industry_fit||t.recommended)&&(r.checked=!0,e++)}),G(`Đã chọn ${e} quy định gợi ý`,`Bấm "Lưu quy định" để lưu thay đổi`)});let y=e(`#select-all-presets`);y&&(y.onclick=()=>{s.policies.forEach((e,t)=>{let n=A().querySelector(`[data-preset="${t}"]`);n&&(n.checked=!0)}),G(`Đã chọn tất cả gợi ý`,`Bấm "Lưu quy định" để lưu`)});let b=e(`#deselect-all-presets`);b&&(b.onclick=()=>{s.policies.forEach((e,t)=>{let n=A().querySelector(`[data-preset="${t}"]`);n&&(n.checked=!1)}),G(`Đã bỏ chọn gợi ý`,`Bấm "Lưu quy định" để lưu`)});let x=e(`#sync-holidays-sys`);x&&(x.onclick=async()=>{try{x.disabled=!0;let t=(await p(`/api/admin/catalog/holidays`)).data?.years||{},n=[];for(let e in t)for(let r of t[e]||[])r.date&&/^\d{4}-\d{2}-\d{2}$/.test(r.date)&&n.push(r.date);let r=e(`#days`).value.split(/\s+/).map(e=>e.trim()).filter(e=>/^\d{4}-\d{2}-\d{2}$/.test(e)),i=Array.from(new Set([...r,...n])).sort();e(`#days`).value=i.join(`
`),G(`Đã đồng bộ ngày nghỉ từ hệ thống`,`Tổng cộng ${i.length} ngày (đã hợp nhất). Bấm "Lưu ngày nghỉ" để áp dụng.`)}catch(e){G(`Chưa đồng bộ được lịch nghỉ`,e.message,`error`)}finally{x.isConnected&&(x.disabled=!1)}});let S=e(`#sync-cats-sys`);S&&(S.onclick=async()=>{try{S.disabled=!0;let n=((await p(`/api/admin/catalog/ai_categories`)).data?.categories||[]).filter(e=>![`CA_NHAN`,`KHONG_RO`].includes(e.id));if(!n.length){G(`Không có nhóm hàng mẫu nào`,``,`warning`);return}let r=[...A().querySelectorAll(`.cat-row`)].map(e=>({name:e.querySelector(`[data-k="name"]`)?.value.trim()||``,description:e.querySelector(`[data-k="description"]`)?.value.trim()||``})).filter(e=>e.name||e.description),i=n.map(e=>({name:e.id.replace(/_/g,` `),description:e.description})).filter(e=>!r.some(t=>t.name.toLowerCase()===e.name.toLowerCase())),a=[...r,...i].slice(0,10),o=e(`#cat-rows-container`);o&&(o.innerHTML=a.concat([{name:``,description:``}]).map((e,n)=>`<div class="form-grid cat-row">
          <div class="cds--form-item cds--text-input-wrapper"><label class="cds--label">Tên nhóm</label><input class="cds--text-input" data-cat="${n}" data-k="name" value="${t(e.name)}" placeholder="Nguyên liệu thực phẩm"></div>
          <div class="cds--form-item cds--text-input-wrapper"><label class="cds--label">Mô tả</label><input class="cds--text-input" data-cat="${n}" data-k="description" value="${t(e.description)}" placeholder="thịt, cá, rau dùng chế biến món ăn"></div></div>`).join(``)),G(`Đã nạp nhóm hàng gợi ý`,`Thêm ${i.length} nhóm. Bấm "Lưu nhóm hàng" để áp dụng.`)}catch(e){G(`Chưa nạp được nhóm hàng`,e.message,`error`)}finally{S.isConnected&&(S.disabled=!1)}});let w=()=>[...s.policies.filter((e,t)=>A().querySelector(`[data-preset="${t}"]`).checked).map(e=>Ee({...e,...(r.policies||[]).find(t=>t.id===e.id)||{}})),...(r.policies||[]).filter(e=>!s.policies.some(t=>t.id===e.id)&&A().querySelector(`[data-custom="${e.id}"]`)?.checked)];e(`#f-pol`).onsubmit=e=>{e.preventDefault();let t=Object.fromEntries(new FormData(e.target).entries()),n=w();if(t.flag){let e={id:`RIENG_${Date.now().toString(36).toUpperCase()}`,flag:t.flag};t.min_gross&&(e.min_gross=Number(String(t.min_gross).replace(/\D/g,``))),t.description_contains&&(e.description_contains=t.description_contains.split(`;`).map(e=>e.trim()).filter(Boolean)),n.push(e)}c({...r,policies:n},`Đã lưu quy định chi tiêu`)},e(`#f-th`).onsubmit=e=>{e.preventDefault();let t=Object.fromEntries(new FormData(e.target).entries()),n={};t.match_days_after_invoice&&(n.match_days_after_invoice=Number(t.match_days_after_invoice)),t.non_cash_threshold_override&&(n.non_cash_threshold_override=Number(String(t.non_cash_threshold_override).replace(/\D/g,``))),c({...r,thresholds:n},`Đã lưu ngưỡng`)},e(`#f-cat`).onsubmit=e=>{e.preventDefault();let t={};e.target.querySelectorAll(`[data-cat]`).forEach(e=>{t[e.dataset.cat]||={},t[e.dataset.cat][e.dataset.k]=e.value.trim()}),c({...r,ai_categories:Object.values(t).filter(e=>e.name&&e.description)},`Đã lưu nhóm hàng đặc thù`)},e(`#f-days`).onsubmit=t=>{t.preventDefault(),c({...r,days_off:e(`#days`).value.split(/\s+/).map(e=>e.trim()).filter(Boolean)},`Đã lưu ngày nghỉ`)},e(`#portal-load`).onclick=async()=>{try{let n=await m(`/api/workspaces/${k.ws}/portal/suggest`);e(`#portal-map`).innerHTML=`<form id="f-portal"><div class="form-grid">${Object.entries(n.fields).map(([e,r])=>`<div class="cds--form-item"><div class="cds--select"><label class="cds--label">${t(r)}</label>
        <div class="cds--select-input__wrapper"><select class="cds--select-input" name="${e}"><option value="">(không có)</option>${n.headers.map(r=>`<option ${r===n.current[e]?`selected`:``}>${t(r)}</option>`).join(``)}</select></div></div></div>`).join(``)}</div>
        <div class="bar">${T(`Lưu cột bảng kê`,`primary`,`type="submit"`)}</div></form>`,e(`#f-portal`).onsubmit=e=>{e.preventDefault();let t=Object.fromEntries([...new FormData(e.target).entries()].filter(([,e])=>e));c({...r,portal_columns:t},`Đã lưu cột bảng kê`)}}catch(t){e(`#portal-map`).insertAdjacentHTML(`beforeend`,C(`warning`,`Chưa đọc được bảng kê`,t.message))}},Ce(e(`#riskimp`))}var K={risk:`<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`,penalty:`<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 16l3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1zM2 16l3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1z"/><path d="M7 21h10"/><path d="M12 3v18"/><path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2"/></svg>`,review:`<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><path d="M11 8v6M8 11h6"/></svg>`,opportunity:`<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>`,chart:`<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>`,calendar:`<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>`,bank:`<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="21" x2="21" y2="21"/><line x1="3" y1="10" x2="21" y2="10"/><polyline points="5 6 12 3 19 6"/><line x1="4" y1="10" x2="4" y2="21"/><line x1="20" y1="10" x2="20" y2="21"/><line x1="8" y1="14" x2="8" y2="17"/><line x1="12" y1="14" x2="12" y2="17"/><line x1="16" y1="14" x2="16" y2="17"/></svg>`,dossier:`<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>`,law:`<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>`},q=e=>e.finding_id||`${e.code}|${e.invoice_keys.join(`,`)}`,Ne=[],Pe=null,Fe=null,Ie=()=>window.dispatchEvent(new Event(`hashchange`));async function Le(){if(!k.ws){await ke();return}let i=k.workspaces.find(e=>e.id===k.ws),o=await P(),s=o?.totals,c=i.files;o?.meta.period&&`${a(o.meta.period[0])}${a(o.meta.period[1])}`;let l=e=>e===`undated`?`Chưa rõ ngày`:`Tháng ${e.slice(5)}/${e.slice(0,4)}`,u=o?.totals.series||[],d=e=>{if(s?.missing_vat_invoices)return``;let t=u.map(t=>Math.abs(Number(t[e]||0)));if(t.length<2||!t.some(Boolean))return``;let n=Math.max(...t),r=t.map((e,r)=>[2+r/(t.length-1)*88,26-e/n*20]),i=r[r.length-1],a=r.map(e=>e.map(e=>e.toFixed(1)).join(`,`)).join(` `),o=`2,30 ${a} ${i[0].toFixed(1)},30`,c=`spark-g-${e.toLowerCase()}`,l={at_risk:[`#ff8389`,`rgba(255, 131, 137, 0.28)`,`rgba(255, 131, 137, 0)`],review:[`#fcd34d`,`rgba(252, 211, 77, 0.28)`,`rgba(252, 211, 77, 0)`],opportunity:[`#2dd4bf`,`rgba(45, 212, 191, 0.28)`,`rgba(45, 212, 191, 0)`]}[e.toLowerCase()]||[`#60a5fa`,`rgba(96, 165, 250, 0.28)`,`rgba(96, 165, 250, 0)`];return`<svg class="spark spark-${e.toLowerCase()}" viewBox="0 0 96 30" width="96" height="30" role="img" aria-label="Diễn biến theo tháng, ${t.length} tháng">
      <defs>
        <linearGradient id="${c}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="${l[1]}"/>
          <stop offset="100%" stop-color="${l[2]}"/>
        </linearGradient>
      </defs>
      <polygon points="${o}" fill="url(#${c})"/>
      <polyline points="${a}" stroke="${l[0]}"/>
      <circle cx="${i[0].toFixed(1)}" cy="${i[1].toFixed(1)}" r="2.8" fill="${l[0]}"/>
    </svg>`},f=()=>{if(s?.missing_vat_invoices)return C(`info`,`Chưa đủ số thuế để vẽ biểu đồ`,`Một số hóa đơn thiếu số thuế; không thay giá trị thiếu bằng 0.`);if(u.length<2)return``;let e=Math.max(...u.map(e=>Number(e.total||0)),1),r=u.map((r,i)=>{let a=10+i*34,o=Math.abs(Number(r.AT_RISK))/e*300,s=Math.abs(Number(r.REVIEW))/e*300,c=[Number(r.AT_RISK)?`${b(r.AT_RISK)||n(r.AT_RISK)} có nguy cơ`:``,Number(r.REVIEW)?`${b(r.REVIEW)||n(r.REVIEW)} cần xem xét`:``].filter(Boolean);return`<text class="t-month" x="0" y="${a+15}">${t(l(r.k))}</text>
        ${o?`<rect class="bar-risk" x="118" y="${a}" width="${o.toFixed(1)}" height="20"/>`:``}${s?`<rect class="bar-review" x="${(118+o).toFixed(1)}" y="${a}" width="${s.toFixed(1)}" height="20"/>`:``}
        <text class="t-val" x="${(118+o+s+10).toFixed(1)}" y="${a+15}">${t(c.join(` · `)||`không có việc`)}</text>`}).join(``);return`<section class="tufte" aria-labelledby="tufte-h"><h2 class="section" id="tufte-h">Thuế cần chú ý theo tháng lập hóa đơn</h2>
      <svg class="tufte-svg" viewBox="0 0 700 ${u.length*34+14}" role="img" aria-label="Thuế có nguy cơ và cần xem xét theo tháng">${r}</svg></section>`};A().innerHTML=`
    ${O(`Tổng quan`,`Tổng quan`,`KHÔNG GIAN DOANH NGHIỆP`,o?`<span class="ctx-chip chip-date">Phân tích: ${a(o.meta.as_of)}</span>`:``)}
    ${i.simulated?`<p class="lead" style="margin-top: 8px;">Dữ liệu mô phỏng đối soát nội bộ, không phải doanh nghiệp thật.</p>`:``}
    <details class="compliance-disclaimer-strip">
      <summary class="disclaimer-summary">
        <span class="disclaimer-badge">🛡️ Lưu ý nghiệp vụ</span>
        <span class="disclaimer-title">Kết quả rà soát tự động theo quy tắc dự thảo (Chưa thay thế kết luận chính thức của chuyên gia thuế)</span>
        <span class="disclaimer-toggle">Chi tiết căn cứ ▾</span>
      </summary>
      <div class="disclaimer-body">
        <p>Cảnh báo và ước tính tiền thuế không phải kết luận vi phạm chính thức hoặc số thuế phải nộp. Vui lòng đối chiếu với hóa đơn gốc, chứng từ thanh toán ngân hàng và xác nhận của kế toán trưởng trước khi kê khai chính thức.</p>
        ${(o?.meta.data_warnings||[]).map(e=>`<p class="data-warning-item">⚠️ ${t(e)}</p>`).join(``)}
      </div>
    </details>
    <div id="fresh"></div>
    <div id="watch"></div>
    ${fe(o)}

    <div class="kpis-v2">
      <!-- 1. Thuế đầu vào có nguy cơ bị loại -->
      <a href="#/viec?loc=AT_RISK" class="kpi-card-v2 kpi-card-risk" title="Bấm để xem danh sách việc có nguy cơ bị loại">
        <div class="kpi-head-v2">
          <div class="kpi-title-wrap-v2">
            <span class="kpi-icon-box badge-risk">${K.risk}</span>
            <span class="kpi-title-label">Thuế đầu vào có nguy cơ bị loại</span>
          </div>
          ${d(`AT_RISK`)}
        </div>
        <div class="kpi-money-block">
          <div class="kpi-main-money val-risk">${r(s?.at_risk_vat)}</div>
          ${s&&b(s.at_risk_vat)?`<span class="kpi-human-read tag-risk">~ ${b(s.at_risk_vat)}</span>`:``}
        </div>
        <div class="kpi-footer-v2">
          <span class="kpi-sub-text">${s?`<strong>${s.at_risk_invoices}</strong> hóa đơn có cảnh báo vi phạm`:`Chưa có phân tích`}</span>
          <span class="kpi-arrow-action" aria-hidden="true">→</span>
        </div>
      </a>

      <!-- 2. Kịch bản phạt nếu khai sai -->
      <a href="#/so-lieu" class="kpi-card-v2 kpi-card-penalty" title="Bấm để xem đối chiếu số liệu và kịch bản">
        <div class="kpi-head-v2">
          <div class="kpi-title-wrap-v2">
            <span class="kpi-icon-box badge-penalty">${K.penalty}</span>
            <span class="kpi-title-label">Kịch bản phạt nếu khai sai</span>
          </div>
          ${d(`AT_RISK`)}
        </div>
        <div class="kpi-money-block">
          <div class="kpi-main-money val-penalty">${r(s?.penalty_estimate)}</div>
          ${s&&b(s.penalty_estimate)?`<span class="kpi-human-read tag-penalty">~ ${b(s.penalty_estimate)}</span>`:``}
        </div>
        <div class="kpi-footer-v2">
          <span class="kpi-sub-text">${s?`Ước tính chậm nộp & xử phạt vi phạm`:`Chưa có số liệu`}</span>
          <span class="kpi-arrow-action" aria-hidden="true">→</span>
        </div>
      </a>

      <!-- 3. Hóa đơn cần xem xét -->
      <a href="#/viec?loc=REVIEW" class="kpi-card-v2 kpi-card-warn" title="Bấm để xem danh sách hóa đơn cần duyệt">
        <div class="kpi-head-v2">
          <div class="kpi-title-wrap-v2">
            <span class="kpi-icon-box badge-warn">${K.review}</span>
            <span class="kpi-title-label">Hóa đơn cần người xem xét</span>
          </div>
          ${d(`REVIEW`)}
        </div>
        <div class="kpi-money-block">
          <div class="kpi-main-money val-warn">${r(s?.review_vat)}</div>
          ${s&&b(s.review_vat)?`<span class="kpi-human-read tag-warn">~ ${b(s.review_vat)}</span>`:``}
        </div>
        <div class="kpi-footer-v2">
          <span class="kpi-sub-text">${s?`<strong>${s.review_invoices}</strong> hóa đơn cần đối chiếu chứng từ`:`Không có hóa đơn chờ`}</span>
          <span class="kpi-arrow-action" aria-hidden="true">→</span>
        </div>
      </a>

      <!-- 4. Có thể đang bỏ sót khấu trừ -->
      <a href="#/viec?loc=OPPORTUNITY" class="kpi-card-v2 kpi-card-opportunity" title="Bấm để xem hóa đơn bỏ sót khấu trừ">
        <div class="kpi-head-v2">
          <div class="kpi-title-wrap-v2">
            <span class="kpi-icon-box badge-opportunity">${K.opportunity}</span>
            <span class="kpi-title-label">Có thể đang bỏ sót khấu trừ</span>
          </div>
          ${d(`OPPORTUNITY`)}
        </div>
        <div class="kpi-money-block">
          <div class="kpi-main-money val-opportunity">${r(s?.opportunity_vat)}</div>
          ${s&&b(s.opportunity_vat)?`<span class="kpi-human-read tag-opportunity">~ ${b(s.opportunity_vat)}</span>`:``}
        </div>
        <div class="kpi-footer-v2">
          <span class="kpi-sub-text">Hóa đơn trên cổng thuế chưa lưu trữ XML</span>
          <span class="kpi-arrow-action" aria-hidden="true">→</span>
        </div>
      </a>
    </div>

    <div class="bar">
      ${T(`Chạy phân tích ngay`,`primary`,`id="run"`)}
      ${o?`<details class="quick-export"><summary>Xuất và in báo cáo</summary>
        <a class="cds--btn cds--btn--tertiary cds--btn--md" href="/api/workspaces/${t(k.ws)}/report.html" target="_blank" rel="noopener">Mở báo cáo để in</a>
        <a class="cds--btn cds--btn--ghost cds--btn--md" href="/api/workspaces/${t(k.ws)}/export/hoa-don.xlsx">Xuất danh sách hóa đơn (Excel)</a>
        <a class="cds--btn cds--btn--ghost cds--btn--md" href="/api/workspaces/${t(k.ws)}/export/quyet-dinh.xlsx">Xuất nhật ký quyết định (Excel)</a>
      </details>`:``}
      <span id="run-msg"></span>
    </div>

    ${f()}

    <div class="quick-links">
      <a href="#/so-lieu"><span class="icon-wrap">${K.chart}</span> <span>Số liệu thuế GTGT theo kỳ</span></a>
      <a href="#/lich"><span class="icon-wrap">${K.calendar}</span> <span>Lịch thuế và Hạn nộp</span></a>
      <a href="#/ngan-hang"><span class="icon-wrap">${K.bank}</span> <span>Giao dịch ngân hàng</span></a>
      <a href="#/giai-trinh"><span class="icon-wrap">${K.dossier}</span> <span>Soạn hồ sơ giải trình</span></a>
      <a href="#/luat"><span class="icon-wrap">${K.law}</span> <span>Kho luật và Điểm mới</span></a>
    </div>

    <div class="grid2">
      <div>
        <h2 class="section">Việc lớn nhất cần xử lý</h2>
        ${D([`Trạng thái`,`Hóa đơn`,`Lý do`,{label:`Số tiền`,num:!0}],(o?.items||[]).slice(0,6).map(e=>{let r=F(e.invoice_keys[0]);return`<tr class="clickable" data-go="#/viec">
            <td>${S(e.status)}</td>
            <td><strong>${t(I(r)||e.invoice_keys[0])}</strong><div class="muted small">${t(r?.seller_name||``)}</div></td>
            <td>${t(e.title)}</td>
            <td class="num"><strong>${n(e.amount)}</strong></td>
          </tr>`}),o?`Không có khoản nào có rủi ro.`:`Chưa phân tích.`)}
      </div>

      <div>
        <h2 class="section">Dữ liệu đã nạp</h2>
        <div class="panel">
          <div class="coverage-grid">
            <div class="coverage-card">
              <span class="cov-title">Hóa đơn mua vào</span>
              <span class="cov-status ${c.purchase_xml?`ok`:`empty`}">${c.purchase_xml?`✓ ${c.purchase_xml} tệp`:`Chưa có`}</span>
            </div>
            <div class="coverage-card">
              <span class="cov-title">Hóa đơn bán ra</span>
              <span class="cov-status ${c.sales_xml?`ok`:`empty`}">${c.sales_xml?`✓ ${c.sales_xml} tệp`:`0 tệp`}</span>
            </div>
            <div class="coverage-card">
              <span class="cov-title">Sao kê ngân hàng</span>
              <span class="cov-status ${c.bank?`ok`:`empty`}">${c.bank?`✓ ${c.bank} tệp`:`Chưa có`}</span>
            </div>
            <div class="coverage-card">
              <span class="cov-title">Bảng kê cổng thuế</span>
              <span class="cov-status ${c.portal_list?`ok`:`empty`}">${c.portal_list?`✓ Đã có`:`Chưa có`}</span>
            </div>
          </div>
          ${T(`Nạp thêm dữ liệu`,`ghost`,`data-go="#/nap"`)}
        </div>

        <h2 class="section">Hạn nộp gần nhất</h2>
        ${D([`Kỳ`,`Hạn`,`Tình trạng`],(o?.calendar||[]).filter(e=>e.due>=new Date().toLocaleDateString(`sv-SE`)).slice(0,3).map(e=>`<tr>
          <td><strong>${t(e.period)}</strong></td>
          <td>${a(e.due)}</td>
          <td>${t(e.status)}</td>
        </tr>`),`Chưa có hạn sắp tới trong dữ liệu đã nạp.`)}
        <details><summary>Hạn đã qua — cần kiểm tra tình trạng kê khai</summary>
        ${D([`Kỳ`,`Hạn`],(o?.calendar||[]).filter(e=>e.due<new Date().toLocaleDateString(`sv-SE`)).map(e=>`<tr><td>${t(e.period)}</td><td>${a(e.due)}</td></tr>`),`Không có hạn đã qua.`)}</details>
      </div>
    </div>
    <div id="next"></div>`,de(e(`#fresh`)),me(e(`#watch`),o),pe(i,o).then(t=>{let n=e(`#next`);n&&(n.innerHTML=t)}),e(`#run`).onclick=async()=>{let t=e(`#run`),n=e(`#run-msg`);t.disabled=!0,n.innerHTML=w(`Đang phân tích dữ liệu hóa đơn và sao kê`);try{await m(`/api/workspaces/${k.ws}/run`),await M(),Ie()}catch(e){n.isConnected&&e.name!==`AbortError`&&(n.innerHTML=C(`error`,`Phân tích không chạy được`,e.message))}finally{t.isConnected&&(t.disabled=!1)}}}function Re(e){return e?t(e).replace(/Lỗi:\s*([A-Z0-9_,\s]+)/g,(e,t)=>`<div class="tech-err-row"><span class="tech-err-label">Lỗi kỹ thuật:</span> ${t.split(`,`).map(e=>e.trim()).filter(Boolean).map(e=>`<span class="tech-err-pill" title="Mã lỗi kỹ thuật: ${e}">${e}</span>`).join(` `)}</div>`):``}function ze(e){return e===`AT_RISK`?`<span class="rev-badge rev-badge-risk" title="Có nguy cơ bị cơ quan thuế loại trừ"><span class="badge-dot dot-risk"></span>Có nguy cơ</span>`:e===`REVIEW`?`<span class="rev-badge rev-badge-warn" title="Cần rà soát và đối chiếu bổ sung chứng từ"><span class="badge-dot dot-warn"></span>Cần xem xét</span>`:e===`OPPORTUNITY`?`<span class="rev-badge rev-badge-opp" title="Cơ hội khấu trừ hợp lệ"><span class="badge-dot dot-opp"></span>Bỏ sót</span>`:S(e)}function Be(e,t){return`<div class="rev-money-cell ${t===`AT_RISK`?`val-risk`:t===`REVIEW`?`val-warn`:`val-opp`}">
    ${r(e)}
  </div>`}function Ve(e,t){return e.length?`<div class="table-wrap review-table-wrap">
    <table class="cds--data-table cds--data-table--md review-data-table">
      <thead>
        <tr>
          <th class="pickcell" style="width:40px">
            <input type="checkbox" id="pick-all" aria-label="Chọn tất cả trên trang" title="Chọn tất cả các việc trên trang hiện tại">
          </th>
          <th style="width:130px"><div class="cds--table-header-label">Trạng thái</div></th>
          <th style="width:165px"><div class="cds--table-header-label">Hóa đơn / Ký hiệu</div></th>
          <th style="min-width:180px"><div class="cds--table-header-label">Nhà cung cấp / Đối tác</div></th>
          <th><div class="cds--table-header-label">Vấn đề & Căn cứ kỹ thuật</div></th>
          <th class="num" style="width:145px"><div class="cds--table-header-label">Số tiền thuế</div></th>
          <th style="width:36px"></th>
        </tr>
      </thead>
      <tbody>
        ${e.map(t).join(``)}
      </tbody>
    </table>
  </div>`:`<div class="review-empty-state">
      <div class="empty-icon-wrap">⚖️</div>
      <h3 class="empty-title">Không tìm thấy việc nào khớp bộ lọc</h3>
      <p class="empty-desc">Thử điều chỉnh lại từ khóa tìm kiếm, nhóm lỗi, kỳ phát sinh hoặc chọn tab "Tất cả" để xem danh sách đầy đủ.</p>
      <button type="button" class="cds--btn cds--btn--secondary cds--btn--sm" id="empty-reset-btn">✕ Đặt lại tất cả bộ lọc</button>
    </div>`}async function He(){let i=await P();if(!i){A().innerHTML=`<h1 class="page">Việc cần xử lý</h1>${C(`info`,`Chưa phân tích`,`Chạy phân tích ở trang Tổng quan để kiểm tra rủi ro.`)}`;return}if(i.meta.schema_version!==2){A().innerHTML=`<h1 class="page">Việc cần xử lý</h1>${C(`warning`,`Báo cáo phiên bản cũ`,`Về Tổng quan và chạy lại phân tích trước khi lưu quyết định.`)}<a href="#/">Về Tổng quan</a>`;return}let s=j().get(`loc`)||`all`,c=`agent3.review.${k.ws}.${k.platform?.profile_revision}`,l={};try{l=JSON.parse(sessionStorage.getItem(c)||`{}`)}catch{}let d=await g(),f=[...new Set(i.invoices.filter(e=>e.issue_date).map(e=>e.issue_date.slice(0,7)))].sort(),p=i.items.filter(e=>s===`all`||e.status===s),m=e=>i.items.filter(t=>t.status===e).length,h=i.totals?.at_risk_vat||i.items.filter(e=>e.status===`AT_RISK`).reduce((e,t)=>e+Number(t.amount||0),0),v=i.items.filter(e=>e.status===`REVIEW`).reduce((e,t)=>e+Number(t.amount||0),0),y=i.items.filter(e=>e.status===`OPPORTUNITY`).reduce((e,t)=>e+Number(t.amount||0),0),b=i.items.length,x=d?.events?.length||0,S=b>0?Math.min(100,Math.round(x/(x+b)*100)):0;A().innerHTML=`
    ${O(`Việc cần xử lý`,`Việc cần xử lý`,`RÀ SOÁT & ĐỐI CHIẾU THUẾ`,`<span class="ctx-chip chip-count">${i.items.length} việc cần xử lý</span>`)}
    
    <div class="review-summary-strip">
      <div class="rev-summary-card card-risk">
        <div class="rev-card-top">
          <span class="rev-card-icon">🚨</span>
          <span class="rev-card-label">Nguy cơ bị loại</span>
          <span class="rev-card-count pill-risk">${m(`AT_RISK`)} việc</span>
        </div>
        <div class="rev-card-val">${r(h)}</div>
        <div class="rev-card-sub">Tổng tiền thuế GTGT có nguy cơ cao</div>
      </div>

      <div class="rev-summary-card card-warn">
        <div class="rev-card-top">
          <span class="rev-card-icon">⚠️</span>
          <span class="rev-card-label">Cần xem xét</span>
          <span class="rev-card-count pill-warn">${m(`REVIEW`)} việc</span>
        </div>
        <div class="rev-card-val">${r(v)}</div>
        <div class="rev-card-sub">Cần rà soát và bổ sung chứng từ</div>
      </div>

      <div class="rev-summary-card card-opp">
        <div class="rev-card-top">
          <span class="rev-card-icon">💡</span>
          <span class="rev-card-label">Cơ hội khấu trừ</span>
          <span class="rev-card-count pill-opp">${m(`OPPORTUNITY`)} việc</span>
        </div>
        <div class="rev-card-val">${r(y)}</div>
        <div class="rev-card-sub">Hóa đơn hợp lệ chưa kê khai</div>
      </div>

      <div class="rev-summary-card card-progress">
        <div class="rev-card-top">
          <span class="rev-card-icon">📊</span>
          <span class="rev-card-label">Tiến độ phê duyệt</span>
          <span class="rev-card-count pill-progress">${x} đã duyệt</span>
        </div>
        <div class="rev-progress-val">
          <div class="progress-pct">${S}%</div>
          <div class="progress-text-sub">${b} việc đang chờ xử lý</div>
        </div>
        <div class="rev-progress-bar-wrap">
          <div class="rev-progress-bar-fill" style="width: ${Math.max(S,2)}%"></div>
        </div>
      </div>
    </div>

    <div id="fresh"></div>
    <div id="ai-tools"></div>

    <div class="toolbar smart-toolbar">
      <div class="status-filter-pills segmented-pills">
        ${[[`all`,`Tất cả`,i.items.length,`pill-all`,`📋`],[`AT_RISK`,`Có nguy cơ`,m(`AT_RISK`),`pill-risk`,`🚨`],[`REVIEW`,`Cần xem xét`,m(`REVIEW`),`pill-warn`,`⚠️`],[`OPPORTUNITY`,`Bỏ sót`,m(`OPPORTUNITY`),`pill-opp`,`💡`]].map(([e,n,r,i,a])=>`<a class="${e===s?`active `+i:``}" href="#/viec?loc=${e}">
          <span class="tab-icon">${a}</span>
          <span class="tab-label">${t(n)}</span>
          <span class="pill-count">${r}</span>
        </a>`).join(``)}
      </div>

      <div class="filter-field filter-field-search" style="flex: 2 1 260px">
        <span class="filter-label">Tìm kiếm</span>
        <div class="search-input-wrap">
          <span class="search-icon" aria-hidden="true">🔍</span>
          <input class="cds--text-input filter-input search-input" id="q" placeholder="Số hóa đơn, người bán, lý do..." aria-label="Tìm việc">
          <button type="button" class="search-clear-btn" id="q-clear" title="Xóa tìm kiếm" hidden aria-label="Xóa tìm kiếm">✕</button>
        </div>
      </div>

      <div class="filter-field filter-field-group">
        <span class="filter-label">Vấn đề</span>
        <select class="cds--select-input filter-select" id="group" aria-label="Lọc theo vấn đề"></select>
      </div>

      <div class="filter-field filter-field-month">
        <span class="filter-label">Kỳ phát sinh</span>
        <select class="cds--select-input filter-select" id="month" aria-label="Lọc theo tháng">
          <option value="">Mọi tháng</option>
          ${f.map(e=>`<option value="${e}">Tháng ${e.slice(5)}/${e.slice(0,4)}</option>`).join(``)}
        </select>
      </div>

      <div class="toolbar-actions">
        <span class="muted small count-tag" id="shown" role="status"></span>
        ${T(`Xóa lọc`,`ghost`,`id="reset-filters" class="cds--btn--sm btn-reset"`)}
        <a class="cds--btn cds--btn--ghost cds--btn--sm btn-export" href="/api/workspaces/${t(k.ws)}/export/viec-can-xu-ly.xlsx">
          <span class="btn-icon">📥</span> Xuất Excel
        </a>
      </div>
    </div>

    <div class="bulk floating-bulk-dock" id="bulk" hidden>
      <div class="bulk-dock-inner">
        <div class="bulk-badge-group">
          <span class="bulk-sparkle-icon">⚡</span>
          <span class="bulk-count-pill" id="bulk-n">Đã chọn 0 việc</span>
        </div>
        <div class="bulk-controls">
          <select class="cds--select-input bulk-select" id="bulk-action" aria-label="Quyết định hàng loạt"></select>
          <input class="cds--text-input bulk-input" id="bulk-ev" aria-label="Chứng từ hoặc lý do chung" placeholder="Chứng từ hoặc lý do chung...">
          <input class="cds--text-input bulk-input bulk-by" id="bulk-by" aria-label="Người duyệt" placeholder="Người duyệt" value="${t(o.get(`agent3.reviewer`)||``)}">
          <button type="button" class="cds--btn cds--btn--primary bulk-confirm-btn" id="bulk-go">
            <span class="btn-icon">✍️</span> Ghi cho các việc đã chọn
          </button>
        </div>
      </div>
    </div>

    <div id="list"></div>`;let w=l.shown||50,E=j().get(`nhom`)||l.code||``,D=new Map(i.items.map((e,t)=>[e,t])),M=e=>i.transactions.find(t=>e.txn_ids?.includes(t.txn_id)),ee=e=>{let t=F(e.invoice_keys[0]),n=M(e);return`${I(t)} ${t?.seller_name||n?.counterparty_name||``} ${e.title} ${e.detail}`.toLowerCase()},N=e=>(F(e.invoice_keys[0])?.issue_date||M(e)?.booked||``).slice(0,7),L={};p.forEach(e=>{let t=L[e.code]||={title:e.title,status:e.status,n:0,amount:0};t.n+=1,t.amount+=Number(e.amount||0)});let R=()=>{let n=Object.entries(L).sort((e,t)=>t[1].amount-e[1].amount||t[1].n-e[1].n);e(`#group`).innerHTML=`<option value="">Mọi vấn đề</option>${n.map(([e,n])=>`<option value="${t(e)}" ${e===E?`selected`:``}>${t(n.title)} (${n.n})</option>`).join(``)}`},z=new Set,te=e=>{let n=F(e.invoice_keys[0]),r=M(e),i=D.get(e),o=(e.status===`AT_RISK`||e.status===`REVIEW`)&&e.invoice_keys.length,s=z.has(e.finding_id);return`<tr class="clickable review-row ${e.status===`AT_RISK`?`row-risk`:e.status===`REVIEW`?`row-warn`:`row-opp`} ${s?`row-checked`:``}" tabindex="0" data-item="${i}">
      <td class="pickcell">
        ${o?`<input type="checkbox" class="bulk-pick" data-idx="${i}" aria-label="Chọn" ${s?`checked`:``}>`:``}
      </td>
      <td class="status-cell">${ze(e.status)}</td>
      <td class="invoice-cell">
        <div class="inv-code-pill" title="${t(e.invoice_keys[0]||``)}">
          <span class="inv-badge-icon">${r?`💳`:`📄`}</span>
          <span class="inv-badge-text">${t(I(n)||e.invoice_keys[0]||(r?`Khoản thu`:`Chưa gắn mã`))}</span>
        </div>
        <div class="inv-date-sub">${a(n?.issue_date||r?.booked)||`—`}</div>
      </td>
      <td class="seller-cell">
        <div class="seller-name" title="${t(n?.seller_name||r?.counterparty_name||``)}">
          ${t(n?.seller_name||r?.counterparty_name||`Đối tác chưa xác định`)}
        </div>
        <div class="seller-tax-sub mono">
          ${n?`<span class="mst-tag">MST</span> <code>${t(n.seller_tax_id||`—`)}</code>`:`<span class="bank-tag">${t(r?.source||`Ngân hàng`)}</span>`}
        </div>
      </td>
      <td class="issue-cell">
        <div class="issue-title">${t(e.title)}</div>
        <div class="issue-detail-wrap">${Re(e.detail)}</div>
      </td>
      <td class="amount-cell num">
        ${Be(e.amount,e.status)}
      </td>
      <td class="action-cell">
        <span class="row-arrow" aria-hidden="true" title="Xem chi tiết">→</span>
      </td>
    </tr>`},B=[],V=()=>{let n=B.filter(e=>e.checked).map(e=>i.items[Number(e.dataset.idx)]);if(e(`#bulk`).hidden=!n.length,!n.length)return;e(`#bulk-n`).textContent=`Đã chọn ${n.length} việc`;let r=n.map(J).reduce((e,t)=>e.filter(([e])=>t.some(([t])=>t===e)));e(`#bulk-action`).innerHTML=r.map(([e,n])=>`<option value="${e}">${t(n)}</option>`).join(``)},H=()=>{let t=e(`#q`).value.trim().toLowerCase(),n=e(`#month`).value,r=p.filter(e=>(!E||e.code===E)&&(!t||ee(e).includes(t))&&(!n||N(e)===n));Ne=r,Pe=()=>{try{sessionStorage.setItem(c,JSON.stringify({q:e(`#q`).value,month:e(`#month`).value,code:E,shown:w,scroll:window.scrollY,focus:Fe}))}catch{}},e(`#shown`).textContent=t||n||E?`${r.length} việc khớp`:`${r.length} việc`;let a=r.length>w?`
      <div class="pagination-bar">
        <div class="pagination-info">
          <span class="muted small">Đang hiển thị <strong>${Math.min(w,r.length)}</strong> trên tổng số <strong>${r.length}</strong> việc (${Math.round(Math.min(w,r.length)/r.length*100)}%)</span>
        </div>
        <div class="pagination-buttons">
          ${T(`Hiện thêm ${Math.min(50,r.length-w)} việc`,`ghost`,`id="more" class="btn-load-more"`)}
          ${T(`Hiện tất cả`,`ghost`,`id="all" class="btn-load-all"`)}
        </div>
      </div>
    `:``;e(`#list`).innerHTML=Ve(r.slice(0,w),te)+a;let o=e(`#pick-all`);B=[...A().querySelectorAll(`.bulk-pick`)],o&&(o.checked=B.length>0&&B.every(e=>e.checked),o.indeterminate=B.some(e=>e.checked)&&!o.checked,o.onchange=()=>{B.forEach(e=>{e.checked=o.checked;let t=i.items[Number(e.dataset.idx)].finding_id;o.checked?z.add(t):z.delete(t);let n=e.closest(`tr`);n&&n.classList.toggle(`row-checked`,o.checked)}),V()}),B.forEach(e=>{e.onclick=e=>e.stopPropagation(),e.onchange=()=>{let t=i.items[Number(e.dataset.idx)].finding_id;e.checked?z.add(t):z.delete(t);let n=e.closest(`tr`);if(n&&n.classList.toggle(`row-checked`,e.checked),o){let e=B.length>0&&B.every(e=>e.checked);o.checked=e,o.indeterminate=B.some(e=>e.checked)&&!e}V()}}),A().querySelectorAll(`[data-item]`).forEach(e=>{e.onclick=()=>Ge(i.items[Number(e.dataset.item)],Number(e.dataset.item)),e.onkeydown=t=>{t.target===e&&[`Enter`,` `].includes(t.key)&&(t.preventDefault(),e.click())}}),e(`#more`)&&(e(`#more`).onclick=()=>{w+=50,H()}),e(`#all`)&&(e(`#all`).onclick=()=>{w=r.length,H()});let l=e(`#empty-reset-btn`);l&&(l.onclick=()=>{s===`all`?(e(`#q`).value=``,e(`#month`).value=``,E=``,e(`#group`).value=``,w=50,H()):location.hash=`#/viec`});let u=e(`#q`),d=e(`#q-clear`);u&&d&&(d.hidden=!u.value,u.oninput=()=>{d.hidden=!u.value,w=50,H()},d.onclick=()=>{u.value=``,d.hidden=!0,w=50,H()}),V()};e(`#group`).onchange=()=>{E=e(`#group`).value,w=50,H()},e(`#month`).onchange=()=>{w=50,H()},e(`#bulk-go`).onclick=async()=>{let t=B.filter(e=>e.checked).map(e=>i.items[Number(e.dataset.idx)]),r={invoice_keys:[...new Set(t.map(e=>e.invoice_keys[0]))],finding_ids:t.map(e=>e.finding_id),action:e(`#bulk-action`).value,evidence:e(`#bulk-ev`).value.trim(),by:e(`#bulk-by`).value.trim()};if(!r.action||!r.evidence||!r.by){G(`Cần quyết định, chứng từ hoặc lý do và người duyệt`,``,`error`);return}o.set(`agent3.reviewer`,r.by);let a=e(`#bulk-go`);a.disabled=!0;try{Pe?.();let e=await _(`/api/workspaces/${k.ws}/decisions/bulk`,r,d);if(e.report_pending){G(`Quyết định đã lưu; cần chạy lại báo cáo`,e.message,`warning`),a.disabled=!1;return}G(`Đã ghi ${e.decisions} quyết định`,`Thuế có nguy cơ còn ${n(e.totals.at_risk_vat)}`),window.sonStamp?.(r.by),Ie()}catch(e){a.isConnected&&(G(`Không ghi được`,e.message,`error`),a.disabled=!1)}},e(`#reset-filters`).onclick=()=>{s===`all`?(e(`#q`).value=``,e(`#month`).value=``,E=``,e(`#group`).value=``,w=50,H()):location.hash=`#/viec`},e(`#q`).value=l.q||``,e(`#month`).value=l.month||``,R(),H(),u(()=>{A().querySelector(`#shown`)&&Pe?.()}),requestAnimationFrame(()=>{if(A().querySelector(`#shown`)&&!document.querySelector(`.drawer`)){window.scrollTo(0,l.scroll||0);let e=i.items.findIndex(e=>q(e)===l.focus);A().querySelector(`[data-item="${e}"]`)?.focus({preventScroll:!0})}}),ve(e(`#ai-tools`)).catch(t=>{let n=e(`#ai-tools`);n&&t.name!==`AbortError`&&(n.innerHTML=C(`info`,`Trợ lý AI chưa sẵn sàng`,`Bạn vẫn có thể xem chứng từ và xử lý công việc bình thường.`))}),de(e(`#fresh`));let U=null;try{U=sessionStorage.getItem(`agent3.openNext`),sessionStorage.removeItem(`agent3.openNext`)}catch{}if(U){let e=i.items.findIndex(e=>q(e)===U);e>=0&&Ge(i.items[e],e)}let W=j().get(`open`);if(W&&!U){let e=i.items.findIndex(e=>e.code===W||q(e)===W||e.invoice_keys.includes(W));e>=0&&Ge(i.items[e],e)}}function J(e){if(e.code.startsWith(`R14`))return[[`CONFIRMED_NON_REVENUE`,`Đã kiểm tra: không phải khoản thu bán hàng`],[`SALES_EVIDENCE_ATTACHED`,`Đã bổ sung hóa đơn bán ra liên quan`]];let t=/^R0[123]_/.test(e.code),n=[];return t&&n.push([`PAYMENT_EVIDENCE_ATTACHED`,`Đã có chứng từ thanh toán không dùng tiền mặt`]),e.status===`REVIEW`&&n.push([`CONFIRMED_OK`,`Đã kiểm tra, không có vấn đề (ghi rõ căn cứ kiểm tra)`]),n.push([`NOT_CLAIMED`,`Không kê khai khấu trừ hóa đơn này`]),n}var Ue=e=>/^R0[123]_/.test(e.code)||e.status===`REVIEW`?``:`Với loại rủi ro này, chứng từ thanh toán không khắc phục được; cần hóa đơn thay thế hoặc điều chỉnh từ người bán, hoặc không kê khai.`;async function We(e,r){try{let i=(await p(`/api/workspaces/${k.ws}/exposure`))[r];if(!i)return;e.innerHTML=`<div class="panel exposure-panel">
      <h3 class="exposure-title" style="margin-top:0"><span class="sec-icon">⚠️</span> Đánh giá thiệt hại và Phương án xử lý tối ưu</h3>
      <p class="exposure-note">${t(i.note)}</p>
      ${i.overdue===!0?`<div class="exposure-table-wrap"><table class="mini exposure-table" style="width:100%;font-size:13px">
            <tr><td>Thuế theo giả định</td><td class="num"><strong>${n(i.amount)}</strong></td><td class="muted small">Chưa xác nhận đã khấu trừ hoặc thực tế thiếu thuế</td></tr>
            <tr><td>Chậm nộp theo giả định</td><td class="num">${n(i.interest)||`Chưa đủ dữ liệu`}</td><td class="muted small">${i.days_late} ngày sau hạn lịch</td></tr>
            <tr><td>Phạt theo giả định</td><td class="num">${n(i.penalty)||`Chưa đủ dữ liệu`}</td><td class="muted small">Không phải kết luận xử phạt</td></tr>
          </table></div>`:`<p class="exposure-due-note">${i.due?`Hạn theo lịch: ${a(i.due)}; chưa quá hạn lịch.`:`Chưa xác định được hạn; không tính số ngày chậm.`} Chưa có bằng chứng xác nhận tình trạng kê khai hoặc nộp.</p>`}
      <div class="cite exposure-cite" style="margin-top:8px">${i.basis.filter(Boolean).map(t).join(`<br>`)}</div>
    </div>`}catch{e.innerHTML=``}}function Ge(r,i){Fe=q(r);let s=F(r.invoice_keys[0]),c=k.report.matches.find(e=>e.invoice_keys.includes(r.invoice_keys[0])),l=(r.status===`AT_RISK`||r.status===`REVIEW`)&&(r.invoice_keys.length>0||r.txn_ids?.length>0),u=r.code.startsWith(`R14`),d=new Set,f=k.report.transactions.find(e=>r.txn_ids?.includes(e.txn_id)),m=g();m.catch(()=>{}),e(`#modal-root`).innerHTML=`<aside class="drawer" role="dialog" aria-labelledby="drawer-title">
    <div class="drawer-top-bar">
      <div class="drawer-header-content">
        <div class="drawer-subhead">
          ${ze(r.status)}
          <span class="rule-code-badge">${t(r.code)}</span>
          ${r.amount?`<span class="amount-badge">Số tiền thuế: <strong>${n(r.amount)}</strong></span>`:``}
        </div>
        <h2 id="drawer-title">${t(r.title)}</h2>
      </div>
      <button class="cds--btn cds--btn--ghost cds--btn--sm close drawer-close-btn" id="close" type="button" aria-label="Đóng ngăn chi tiết">✕ Đóng</button>
    </div>

    <div id="plain" style="margin-top:1rem"></div>

    <div class="dossier-grid">
      <div class="dossier-card">
        <h3 class="dossier-card-title"><span class="dossier-icon">${K.dossier}</span> ${u?`Thông tin giao dịch`:`Hóa đơn đầu vào XML`}</h3>
        ${u&&f?`<dl class="kv"><dt>Ngày</dt><dd>${a(f.booked)}</dd><dt>Số tiền</dt><dd><strong>${n(f.amount)}</strong></dd><dt>Đối tác</dt><dd>${t(f.counterparty_name)}</dd><dt>Nội dung</dt><dd>${t(f.description)}</dd><dt>Nguồn</dt><dd class="mono small">${t(f.source)}</dd></dl>`:``}
        <dl class="kv" ${u?`hidden`:``}>
          <dt>Số hóa đơn</dt><dd><strong>${t(I(s)||r.invoice_keys[0])}</strong></dd>
          <dt>Người bán</dt><dd><strong>${t(s?.seller_name||``)}</strong> <div class="muted small">MST: ${t(s?.seller_tax_id||``)}</div></dd>
          <dt>Ngày lập</dt><dd>${a(s?.issue_date)}</dd>
          <dt>Tổng thanh toán</dt><dd><strong>${n(s?.gross)}</strong></dd>
          <dt>Tiền thuế GTGT</dt><dd><strong style="color:var(--a3-primary);font-size:15px">${n(s?.vat)}</strong></dd>
          <dt>Tệp XML gốc</dt><dd class="mono small" style="word-break:break-all">${t(s?.file||``)}</dd>
        </dl>
      </div>

      <div class="dossier-card">
        <h3 class="dossier-card-title"><span class="dossier-icon">${K.bank}</span> Chứng từ Ngân hàng đối chiếu</h3>
        ${c?`
          <div class="match-badge ${c.status===`MATCHED`?`match-ok`:`match-warn`}">
            ${c.status===`MATCHED`?`✓ Đã ghép chứng từ thanh toán`:`⚠ Khớp mơ hồ / Cần xem lại`}
          </div>
          <p class="small" style="margin:8px 0 12px">${t(c.note)}</p>
          ${f?`<dl class="kv"><dt>Ngày hạch toán</dt><dd>${a(f.booked)}</dd><dt>Số tiền TT</dt><dd><strong>${n(f.amount)}</strong></dd><dt>Nội dung CK</dt><dd>${t(f.description)}</dd></dl>`:``}
        `:`
          <div class="match-badge match-empty">⚠ Chưa ghép được chứng từ thanh toán không dùng tiền mặt</div>
          <p class="muted small" style="margin-top:8px">Hóa đơn có giá trị từ 20 triệu đồng trở lên cần chứng từ thanh toán không dùng tiền mặt để đủ điều kiện khấu trừ thuế GTGT.</p>
        `}
      </div>
    </div>

    <div id="exposure"></div>
    <details><summary>Lịch sử quyết định và bằng chứng</summary><div id="decision-history"></div></details>

    <h3 class="section">Chi tiết vấn đề và Khuyến nghị</h3>
    <div style="background:var(--cds-layer);padding:14px 16px;border-radius:8px;border:1px solid var(--cds-border-subtle);margin-bottom:14px">
      <p style="margin:0 0 8px;font-size:13.5px"><strong>Hiện tượng:</strong> ${t(r.detail)}</p>
      <p style="margin:0;font-size:13.5px;color:var(--a3-primary)"><strong>Hành động cần làm:</strong> ${t(r.action)}</p>
    </div>

    <h3 class="section">Căn cứ pháp lý</h3>
    <ul style="font-size:13px;line-height:1.6;margin:0 0 16px 20px;padding:0">
      ${r.basis.map(e=>`<li>${t(e)}</li>`).join(``)}
    </ul>

    ${l?`<h3 class="section">Phê duyệt và Quyết định xử lý</h3>
      <div id="suggest"></div>
      <form id="decide">
        <div class="form-grid">
          ${E({key:`action`,label:`Quyết định xử lý`,type:`choice`,required:!0,choices:J(r),help:Ue(r)},J(r)[0][0])}
          ${E({key:`evidence`,label:`Chứng từ hoặc lý do giải trình`,required:!0,example:`Ủy nhiệm chi số 5521 ngày 05/09/2026`})}
          ${E({key:`by`,label:`Người duyệt`,required:!0,example:`Kế toán trưởng`},o.get(`agent3.reviewer`)||``)}
          ${u?E({key:`category`,label:`Loại khoản thu nếu không phải bán hàng`,type:`choice`,choices:[[`LOAN`,`Khoản vay`],[`INTERNAL_TRANSFER`,`Chuyển nội bộ`],[`CAPITAL`,`Góp vốn`],[`REFUND`,`Hoàn tiền`],[`OTHER`,`Khác, ghi rõ bằng chứng`]]}):``}
        </div>
        ${u?`<details><summary>Hóa đơn bán ra liên quan (khi xác nhận đã bổ sung hóa đơn)</summary><label for="sales-query">Tìm số hóa đơn hoặc người mua</label><input id="sales-query" class="cds--text-input"><div id="sales-picks" class="sales-evidence-list"></div><div id="sales-selected" role="status"></div></details>`:``}
        <div class="bar drawer-action-bar" style="margin-top:16px">
          ${T(`Lưu và mở việc tiếp theo →`,`primary`,`type="submit" data-next="1" class="btn-save-next"`)}
          ${T(`Lưu quyết định này`,`secondary`,`type="submit" class="btn-save-current"`)}
          <span id="dmsg"></span>
        </div>
      </form>`:``}
  </aside>`,B();let h=e(`#decision-history`);if(m.then(e=>{if(!h.isConnected)return;let n=e.events.filter(e=>e.finding_id===r.finding_id||r.invoice_keys.includes(e.invoice_key)||e.txn_ids?.some(e=>r.txn_ids?.includes(e)));h.innerHTML=D([`Thời điểm`,`Người duyệt`,`Quyết định`,`Bằng chứng`],n.map(e=>`<tr><td>${t(e.at)}${e.legacy?` (dữ liệu cũ)`:``}</td><td>${t(e.by)}</td><td>${t(e.action)}${e.supersedes?`<div class="muted small">Thay thế một quyết định trước; bản trước vẫn được giữ</div>`:``}</td><td>${t(e.evidence)}</td></tr>`),`Chưa có quyết định cho đối tượng này.`)}).catch(e=>{h.isConnected&&(h.innerHTML=C(`error`,`Không tải được lịch sử`,e.message))}),u){let r=k.report.invoices.filter(e=>e.role===`SALE`&&!e.duplicate_of),i=()=>{let a=e(`#sales-query`).value.trim().toLowerCase(),o=r.filter(e=>`${I(e)} ${e.buyer_name}`.toLowerCase().includes(a));e(`#sales-picks`).innerHTML=o.slice(0,50).map(e=>`<label><input type="checkbox" value="${t(e.key)}" ${d.has(e.key)?`checked`:``}> ${t(I(e))} — ${t(e.buyer_name)} — ${n(e.gross)}</label>`).join(``),e(`#sales-selected`).textContent=`Hiện tối đa 50/${o.length} hóa đơn; đã chọn ${d.size}. Tìm để thu hẹp kết quả.`,e(`#sales-picks`).onchange=e=>{e.target.matches(`input`)&&(e.target.checked?d.add(e.target.value):d.delete(e.target.value),i())}};e(`#sales-query`).oninput=i,i()}Number.isInteger(i)&&_e(e(`#plain`),i),r.status===`AT_RISK`&&Number.isInteger(i)&&We(e(`#exposure`),i);let v=e(`#decide`);if(v){let n=e(`.drawer`);p(`/api/workspaces/${k.ws}/decisions/suggest?key=${encodeURIComponent(r.invoice_keys[0])}&code=${encodeURIComponent(r.code)}`).then(i=>{let a=i.suggestion;a&&n.isConnected&&J(r).some(([e])=>e===a.action)&&(e(`#suggest`).innerHTML=`<div class="banner banner-info">
        <div><strong>Gợi ý từ quyết định trước</strong><div class="small">${t(a.because)}</div></div>
        <button type="button" class="cds--btn cds--btn--ghost cds--btn--sm" id="use-sugg">Điền theo gợi ý</button>
      </div>`,e(`#use-sugg`).onclick=()=>{v.querySelector(`[name=action]`).value=a.action,v.querySelector(`[name=evidence]`).value=``,v.querySelector(`[name=evidence]`).placeholder=`Lần trước: ${a.evidence}`,v.querySelector(`[name=by]`).value||(v.querySelector(`[name=by]`).value=a.by),v.querySelector(`[name=evidence]`).focus()})}).catch(()=>{}),v.onsubmit=async t=>{t.preventDefault();let n=Object.fromEntries(new FormData(v).entries());o.set(`agent3.reviewer`,n.by);let a=t.submitter&&t.submitter.dataset.next,s=Ne.filter(e=>(e.status===`AT_RISK`||e.status===`REVIEW`)&&q(e)!==q(r)&&!e.invoice_keys.includes(r.invoice_keys[0])),c=s[s.indexOf(s.find(e=>k.report.items.indexOf(e)>i))]||s[0];e(`#dmsg`).innerHTML=`<span class="muted">Đang lưu quyết định...</span>`;let l=e(`#dmsg`),f=[...v.querySelectorAll(`button[type="submit"]`)];f.forEach(e=>{e.disabled=!0});try{Pe?.();let e=await _(`/api/workspaces/${k.ws}/decisions`,{...n,invoice_key:r.invoice_keys[0],finding_id:r.finding_id,invoice_keys:u?[...d]:void 0},await m);if(e.report_pending){l.innerHTML=C(`warning`,`Quyết định đã lưu; cần chạy lại báo cáo`,e.message),f.forEach(e=>{e.disabled=!1});return}if(G(`Đã lưu quyết định`,`Thuế có nguy cơ còn ${Number(e.totals.at_risk_vat).toLocaleString(`vi-VN`)} đ`),window.sonStamp?.(n.by),a&&c)try{sessionStorage.setItem(`agent3.openNext`,q(c))}catch{}te(),Ie()}catch(e){v.isConnected&&(l.innerHTML=C(`error`,`Không lưu được`,e.message),f.forEach(e=>{e.disabled=!1}))}}}}var Ke=()=>window.dispatchEvent(new Event(`hashchange`));async function qe(){if(L())return;let r=await P();if(!r){A().innerHTML=`<h1 class="page">Hóa đơn</h1>${C(`info`,`Chưa phân tích`)}`;return}let o=new Map(r.matches.flatMap(e=>e.invoice_keys.map(t=>[t,e]))),s=new Map;r.items.forEach(e=>e.invoice_keys.forEach(t=>s.set(t,[...s.get(t)||[],e])));let c=[...new Set(r.invoices.filter(e=>e.issue_date).map(e=>e.issue_date.slice(0,7)))].sort(),l=e=>{let t=(s.get(e.key)||[]).filter(e=>e.status!==`INFO`);return t.some(e=>e.status===`AT_RISK`)?`AT_RISK`:t.some(e=>e.status===`REVIEW`)?`REVIEW`:t.length?`OTHER`:`OK`},d=`agent3.invoices.${k.ws}.${k.platform?.profile_revision}`,f={};try{f=JSON.parse(sessionStorage.getItem(d)||`{}`)}catch{}let p=f.page||0;A().innerHTML=`
    ${O(`Hóa đơn`,`Hóa đơn GTGT`,`QUẢN LÝ CHỨNG TỪ`,`<span class="ctx-chip chip-count">${r.invoices.length} hóa đơn</span>`)}
    <p class="lead" style="margin-top:10px">${r.invoices.length} hóa đơn đọc từ tệp XML. Lọc, tìm và xem theo trang 50 dòng; bấm tiêu đề cột để sắp xếp; bấm dòng có cảnh báo để xử lý.</p>
    <div class="bar"><select class="cds--select-input filter-select" id="role" aria-label="Loại hóa đơn"><option value="">Mua vào và bán ra</option><option value="PURCHASE">Mua vào</option><option value="SALE">Bán ra</option></select>
      <select class="cds--select-input filter-select" id="st" aria-label="Tình trạng"><option value="">Mọi tình trạng</option><option value="AT_RISK">Có nguy cơ</option><option value="REVIEW">Cần xem xét</option><option value="OK">Không cảnh báo</option><option value="UNPAID">Chưa ghép thanh toán</option></select>
      <select class="cds--select-input filter-select" id="mon" aria-label="Tháng"><option value="">Mọi tháng</option>${c.map(e=>`<option value="${e}">Tháng ${e.slice(5)}/${e.slice(0,4)}</option>`).join(``)}</select>
      <input class="cds--text-input filter-input" id="iq" placeholder="Tìm số hóa đơn, người bán, mã số thuế, tên hàng" aria-label="Tìm hóa đơn">
      <span class="muted small" id="icount" role="status"></span>${T(`Xóa bộ lọc`,`ghost`,`id="reset-invoices"`)}
      <a class="cds--btn cds--btn--ghost cds--btn--sm" href="/api/workspaces/${t(k.ws)}/export/hoa-don.xlsx">Xuất Excel</a></div>
    <div id="ilist"></div>`;let m=f.sort||[`issue_date`,-1],h={issue_date:e=>e.issue_date||``,gross:e=>e.gross||`0`,vat:e=>e.vat||`0`,seller:e=>(e.role===`SALE`?e.buyer_name:e.seller_name)||``},g=()=>{let c=e(`#role`).value,u=e(`#st`).value,d=e(`#mon`).value,f=e(`#iq`).value.trim().toLowerCase(),_=r.invoices.filter(e=>(!c||e.role===c)&&(!d||(e.issue_date||``).startsWith(d))&&(!u||(u===`UNPAID`?e.role===`PURCHASE`&&!o.get(e.key):l(e)===u))&&(!f||`${I(e)} ${e.number} ${e.seller_name} ${e.seller_tax_id} ${e.buyer_name||``} ${(e.descriptions||[]).join(` `)}`.toLowerCase().includes(f))).sort((e,t)=>{let n=h[m[0]](e),r=h[m[0]](t);return([`gross`,`vat`].includes(m[0])?i(n,r):n>r?1:n<r?-1:0)*m[1]}),v=Math.max(1,Math.ceil(_.length/50));p=Math.min(p,v-1);let y=(e,n,r)=>`<th class="${r?`num `:``}sortable" aria-sort="${m[0]===e?m[1]>0?`ascending`:`descending`:`none`}"><button type="button" class="sort-button" data-sort="${e}">${t(n)}${m[0]===e?m[1]>0?` ↑`:` ↓`:``}</button></th>`;e(`#icount`).textContent=`${_.length} hóa đơn`,e(`#ilist`).innerHTML=_.length?`<div class="table-wrap"><table class="cds--data-table cds--data-table--md"><thead><tr><th>Hóa đơn</th>${y(`issue_date`,`Ngày`)}${y(`seller`,`Người bán hoặc người mua`)}${y(`gross`,`Tổng thanh toán`,!0)}${y(`vat`,`Thuế`,!0)}<th>Toàn vẹn</th><th>Thanh toán</th><th>Cảnh báo</th></tr></thead><tbody>
      ${_.slice(p*50,p*50+50).map(e=>{let r=o.get(e.key),i=(s.get(e.key)||[]).filter(e=>e.status!==`INFO`),c=e.guard_errors.length?S(`AT_RISK`,`Lỗi ${e.guard_errors.length}`):e.signed?S(`LLM_VERIFIED`,`Chữ ký hợp lệ`):S(`INFO`,`Không ký`);return`<tr class="${i.length?`clickable`:``}" ${i.length?`data-go="#/viec?open=${encodeURIComponent(e.key)}"`:``}><td>${t(I(e))}${e.duplicate_of?` <span class="muted small">(bản trùng)</span>`:``}<div class="muted small">${e.role===`SALE`?`Bán ra`:`Mua vào`}</div></td><td>${a(e.issue_date)}</td>
          <td>${t(e.role===`SALE`?e.buyer_name:e.seller_name)}</td><td class="num">${n(e.gross)}</td><td class="num">${n(e.vat)}</td><td>${c}</td>
          <td>${e.role===`SALE`?``:r?r.status===`MATCHED`?`Đã ghép`:`Cần xác nhận`:`<span class="muted">Chưa ghép</span>`}</td><td><div class="chips">${i.map(e=>S(e.status,e.title.length>40?`${e.title.slice(0,38)}…`:e.title)).join(``)}</div></td></tr>`}).join(``)}</tbody></table></div>
      <div class="bar pager">${T(`Trang trước`,`ghost`,`id="prev" ${p===0?`disabled`:``}`)}<span class="small">Trang ${p+1} / ${v}</span>${T(`Trang sau`,`ghost`,`id="next" ${p>=v-1?`disabled`:``}`)}</div>`:`<div class="empty">Không có hóa đơn nào khớp.</div>`,e(`#prev`)&&(e(`#prev`).onclick=()=>{--p,g()}),e(`#next`)&&(e(`#next`).onclick=()=>{p+=1,g()}),A().querySelectorAll(`[data-sort]`).forEach(e=>{e.onclick=()=>{let t=e.dataset.sort;m=[t,m[0]===t?-m[1]:-1],g(),A().querySelector(`[data-sort="${t}"]`)?.focus({preventScroll:!0})}})};[`role`,`st`,`mon`].forEach(t=>{e(`#${t}`).onchange=()=>{p=0,g()}}),e(`#iq`).oninput=()=>{p=0,g()},e(`#reset-invoices`).onclick=()=>{[`role`,`st`,`mon`,`iq`].forEach(t=>{e(`#${t}`).value=``}),p=0,g()},[`role`,`st`,`mon`,`iq`].forEach(t=>{e(`#${t}`).value=f[t]||``}),g(),u(()=>{if(A().querySelector(`#ilist`))try{sessionStorage.setItem(d,JSON.stringify({sort:m,page:p,scroll:window.scrollY,...Object.fromEntries([`role`,`st`,`mon`,`iq`].map(t=>[t,e(`#${t}`).value]))}))}catch{}}),requestAnimationFrame(()=>{A().querySelector(`#ilist`)&&window.scrollTo(0,f.scroll||0)})}async function Je(){if(L())return;let r=await P();if(!r){A().innerHTML=`<h1 class="page">Ngân hàng</h1>${C(`info`,`Chưa phân tích`)}`;return}let i=new Map(r.matches.flatMap(e=>e.txn_ids.map(t=>[t,e])));A().innerHTML=`
    ${O(`Ngân hàng`,`Giao dịch ngân hàng`,`ĐỐI SOÁT THANH TOÁN`,`<span class="ctx-chip chip-count">${r.transactions.length} giao dịch</span>`)}
    <p class="lead" style="margin-top:10px">${r.transactions.length} giao dịch từ các tệp sao kê. Một khoản chi chỉ được ghép khi đúng số tiền và có dấu hiệu nhận ra người bán. <a href="#/du-lieu">Chọn bảng kê cổng thuế đang dùng ↗</a></p><div id="props"></div>
    ${D([`Ngày`,`Chiều`,{label:`Số tiền`,num:!0},`Đối ứng`,`Nội dung`,`Ghép với hóa đơn`,`Nguồn`],r.transactions.map(e=>{let r=i.get(e.txn_id);return`<tr><td>${a(e.booked)}</td><td>${e.direction===`OUT`?`Chi`:`Thu`}</td><td class="num">${n(e.amount)}</td>
        <td>${t(e.counterparty_name||``)}<div class="muted small mono">${t(e.counterparty_account||``)}</div></td><td>${t(e.description)}</td>
        <td>${r?`${r.invoice_keys.map(e=>t(I(F(e)))).join(`, `)}<div class="muted small">${r.status===`MATCHED`?`Đã ghép`:`Mơ hồ`}</div>`:``}</td><td class="muted small">${t(e.source)}</td></tr>`}))}`,ye(e(`#props`))}async function Ye(){if(L())return;let e=await P();A().innerHTML=`
    ${O(`Lịch thuế`,`Lịch thuế`,`THEO DÕI NGHĨA VỤ`)}
    <p class="lead" style="margin-top:10px">Hạn lịch theo bộ quy tắc nháp, đã tính dời ngày nghỉ theo cấu hình. Tình trạng được tính tại ngày phân tích ${a(e?.meta.as_of)}; chưa xác nhận đã kê khai hoặc nộp tiền.</p>
    ${D([`Kỳ`,`Hạn nộp`,`Tình trạng`,`Căn cứ`],(e?.calendar||[]).map(e=>`<tr><td>${t(e.period)}</td><td>${a(e.due)}${e.moved_from?`<div class="muted small">Dời từ ${a(e.moved_from)} do ngày nghỉ</div>`:``}</td><td>${t(e.status)}${e.open_items?`<div><a href="#/viec" class="risk-text">còn ${e.open_items} việc chưa xử lý của kỳ này</a></div>`:``}${e.extension?`<div class="muted small">${t(e.extension)}</div>`:``}</td><td class="muted small">${t(e.basis)}</td></tr>`),`Chưa có dữ liệu.`)}`}async function Xe(){let n=await p(`/api/law/status`),r=n.stats,i=j().get(`doc`);if(i){let e=await p(`/api/law/docs/${encodeURIComponent(i)}`);A().innerHTML=`<div class="bar">${T(`Quay lại kho luật`,`ghost`,`data-go="#/luat"`)}</div><h1 class="page">${t(e.doc.doc_type)} ${t(e.doc.doc_num)}</h1>
      <p class="lead">${t(e.doc.title)}</p><dl class="kv"><dt>Ban hành</dt><dd>${a(e.doc.issue_date)}</dd><dt>Hiệu lực</dt><dd>${a(e.doc.eff_from)||`không ghi`}${e.doc.eff_to?` đến `+a(e.doc.eff_to):``}</dd>
      <dt>Tình trạng</dt><dd>${t(e.doc.status_name||`không ghi`)}</dd><dt>Nguồn</dt><dd><a href="${t(e.doc.url)}" target="_blank" rel="noopener">Cơ sở dữ liệu quốc gia về pháp luật</a></dd>
      <dt>Chuyên gia duyệt</dt><dd>${t(e.doc.review_status)}</dd><dt>Dùng để trả lời</dt><dd>${e.doc.indexed?`Có`:`Không (chỉ lưu để đối chiếu)`}</dd></dl>
      ${e.ended?C(`warning`,`Hết hiệu lực từ ${a(e.ended.eff_to)} theo ${e.ended.by_path||e.ended.by_doc_num}`,`${e.ended.path?e.ended.path+`. `:``}Căn cứ nguyên văn: "${e.ended.quote}"${e.ended.exception?` Ngoại lệ: ${e.ended.exception}`:``}`):``}
      ${e.validity_notes.length?`<div class="panel"><h3>Ghi chú hiệu lực cần chuyên gia xem</h3><ul>${e.validity_notes.map(e=>`<li>${t(e.kind===`PARTIAL`?`Hết hiệu lực một phần`:`Được nhắc là văn bản sửa đổi, vẫn giữ hiệu lực`)} theo ${t(e.by_doc_num)}: <span class="muted">${t(e.quote.slice(0,300))}</span></li>`).join(``)}</ul></div>`:``}
      ${e.provisions.length?e.provisions.map(e=>`<div class="law-prov l${e.level}">${t(e.text)}</div>`).join(``):C(`warning`,`Văn bản chưa có toàn văn trong kho`,`Trang nguồn chỉ có tệp đính kèm.`)}`;return}A().innerHTML=`
    ${O(`Kho luật`,`Kho luật thuế`,`CĂN CỨ PHÁP LÝ`)}
    <p class="lead" style="margin-top:10px">Văn bản thuế lấy tự động từ Cơ sở dữ liệu quốc gia về pháp luật (vbpl.vn) của Bộ Tư pháp, theo từng điều, khoản, điểm, có ngày hiệu lực. Chỉ đọc trang được phép theo robots.txt, tối đa 1 yêu cầu mỗi 2 giây.</p>
    <div class="kpis"><div class="kpi"><span class="label">Văn bản</span><span class="value">${r?r.documents:0}</span><span class="sub">${r?`${r.in_force} còn hiệu lực`:``}</span></div>
    <div class="kpi"><span class="label">Điều khoản</span><span class="value">${r?r.provisions.toLocaleString(`vi-VN`):0}</span><span class="sub">${r?`${r.chunks.toLocaleString(`vi-VN`)} đoạn tìm kiếm`:``}</span></div>
    <div class="kpi"><span class="label">Lần đồng bộ gần nhất</span><span class="value" style="font-size:1.25rem">${r?.last_snapshot?.created_at?a(r.last_snapshot.created_at):`chưa có`}</span>
    <span class="sub">${n.job.running?`đang chạy${n.job.external?` từ dòng lệnh`:``}: ${n.job.done} văn bản, ${t(n.job.last)}`:``}</span></div>
    <div class="kpi"><span class="label">Hết hiệu lực theo văn bản thay thế</span><span class="value">${r?r.ended_by_later_act??0:0}</span><span class="sub">đọc từ điều khoản hiệu lực thi hành của văn bản mới</span></div></div>
    <h2 class="section">Tìm trong kho</h2><form id="lsearch" class="bar" style="align-items:flex-end"><div class="cds--form-item cds--text-input-wrapper" style="flex:1;min-width:16rem">
    <label class="cds--label" for="lq">Nội dung</label><input class="cds--text-input" id="lq" placeholder="Ví dụ: thời hạn nộp hồ sơ khai thuế theo quý"></div>
    <div class="cds--form-item cds--text-input-wrapper"><label class="cds--label" for="lasof">Ngày áp dụng</label><input class="cds--text-input" id="lasof" type="date" value="${new Date().toISOString().slice(0,10)}"></div>
    ${T(`Tìm`,`primary`,`type="submit"`)}</form><div id="lres"></div>
    <h2 class="section">Văn bản</h2><div id="ldocs">${w(`Đang tải danh sách`)}</div><details class="law-management"><summary>Đồng bộ và lịch sử kho luật</summary>    <div class="bar">${T(n.job.running?`Đang đồng bộ`:`Đồng bộ kho luật`,`primary`,`id="sync" ${n.job.running?`disabled`:``}`)}${T(`Chỉ văn bản lõi`,`tertiary`,`id="sync-core" ${n.job.running?`disabled`:``}`)}
    <span>${n.job.error?C(`error`,`Lỗi đồng bộ`,n.job.error):``}</span></div>
    <div id="alerts"></div>
    <h2 class="section">Thay đổi gần đây</h2>${D([`Lần`,`Loại`,`Văn bản`,`Chi tiết`],(n.changes||[]).slice(0,15).map(e=>`<tr><td>${e.snapshot_id}</td><td>${t(e.kind)}</td><td>${t(e.doc_num||``)}</td><td>${t(e.detail)}</td></tr>`),`Chưa có thay đổi.`)}
</details>`;let o=async t=>{try{await m(`/api/law/sync${t}`),Ke()}catch(t){e(`#lres`).innerHTML=C(`error`,`Chưa đồng bộ được`,t.message)}};if(e(`#sync`).onclick=()=>o(``),e(`#sync-core`).onclick=()=>o(`?core_only=true`),Se(e(`#alerts`)).catch(()=>{}),n.job.running){let e=setTimeout(()=>{j().get(`doc`)||Ke()},5e3);u(()=>clearTimeout(e))}e(`#lsearch`).onsubmit=async n=>{n.preventDefault();let r=e(`#lq`).value.trim();if(r){e(`#lres`).innerHTML=w(`Đang tìm`);try{let n=await p(`/api/law/search?q=${encodeURIComponent(r)}&as_of=${e(`#lasof`).value}`);e(`#lres`).innerHTML=n.length?n.map(e=>`<div class="panel"><h3><a href="#/luat?doc=${t(e.doc_id)}">${t(e.path)}</a></h3>
        <div class="muted small">${t(e.status||`không ghi tình trạng`)}, hiệu lực từ ${a(e.eff_from)||`không ghi`}</div><p>${t(e.text.slice(0,900))}${e.text.length>900?`...`:``}</p></div>`).join(``):`<div class="empty">Không tìm thấy điều khoản phù hợp tại ngày này.</div>`}catch(t){e(`#lres`).innerHTML=C(`error`,`Không tìm được`,t.message)}}};try{let n=await p(`/api/law/docs`);e(`#ldocs`).innerHTML=D([`Văn bản`,`Ban hành`,`Hiệu lực`,`Tình trạng`,{label:`Điều khoản`,num:!0}],n.map(e=>`<tr class="clickable" data-go="#/luat?doc=${t(e.doc_id)}">
      <td><span class="cell-title">${t(e.doc_type)} ${t(e.doc_num)}</span><div class="muted small">${t((e.title||``).slice(0,140))}</div></td><td>${a(e.issue_date)}</td><td>${a(e.eff_from)}</td>
      <td>${e.ended_on?`Hết hiệu lực từ ${a(e.ended_on)} theo ${t(e.ended_by)}`:t(e.status_name||``)}${e.structure===`none`?`<div class="muted small">chưa có toàn văn</div>`:``}${e.indexed?``:`<div class="muted small">không dùng để trả lời</div>`}</td><td class="num">${e.n_provisions}</td></tr>`),`Kho trống. Bấm Đồng bộ kho luật.`)}catch{e(`#ldocs`).innerHTML=`<div class="empty">Kho trống. Bấm Đồng bộ kho luật.</div>`}}var Ze=null;function Qe(e){return`<details class="guide" id="guide" style="border-radius:12px;overflow:hidden;margin-top:20px;border:1px solid var(--cds-border-subtle);background:var(--cds-layer)">
    <summary style="font-size:13.5px;font-weight:600;padding:12px 16px;cursor:pointer">Danh mục câu hỏi trợ lý hỗ trợ (${e.groups.reduce((e,t)=>e+t.domains.length,0)} nhóm)</summary>
    <p class="muted small" style="margin:4px 16px 12px">Bấm vào bất kỳ câu hỏi mẫu nào để gửi ngay vào cuộc hội thoại.</p>
    ${e.groups.map(e=>`<details class="guide-group" style="margin:6px 16px 10px">
      <summary style="font-size:13px;font-weight:600;cursor:pointer">${t(e.title)} <span class="muted small">(${e.domains.length} câu)</span></summary>
      ${e.domains.map(e=>`<div class="guide-domain" style="border-bottom:1px solid var(--cds-border-subtle);padding:10px 0">
        <strong style="font-size:13px;color:var(--a3-primary, #0f766e)">${t(e.title)}</strong>
        <div class="small" style="margin:2px 0 6px">${t(e.what)}</div>
        ${e.limits?`<div class="muted small" style="margin-bottom:6px"><em>Giới hạn:</em> ${t(e.limits)}</div>`:``}
        <div class="chips">${e.examples.map(e=>e.includes(`<`)?`<span class="chip-tpl small">${t(e)}</span>`:`<button type="button" class="cds--btn cds--btn--ghost cds--btn--sm chip-q" data-q="${t(e)}" style="border-radius:9999px;font-size:12px">${t(e)}</button>`).join(``)}</div>
      </div>`).join(``)}
    </details>`).join(``)}
  </details>`}function $e(e){let n=e.understood||{};if(!n.title)return``;let r=[n.period&&`kỳ ${n.period}`,n.invoice_numbers&&`hóa đơn ${n.invoice_numbers.join(`, `)}`,n.seller&&`người bán ${n.seller}`,n.issue&&`loại vấn đề: ${n.issue}`,n.top_n&&`${n.top_n} dòng`].filter(Boolean);return`<div class="understood small" style="background:var(--cds-layer-hover, #f4f4f4);padding:5px 12px;border-radius:6px;margin:6px 0 10px;display:inline-block">
    Phân tích câu hỏi: <strong>${t(n.title)}</strong>${r.length?` (${t(r.join(`; `))})`:``}
  </div>`}function et(e,n,r){let i=(n.facts||[]).find(e=>e&&e.passages),a=i?i.sentences.flatMap(e=>e.citations).filter((e,t,n)=>n.findIndex(t=>t.path===e.path)===t).map(e=>`<a href="${t(e.url)}" target="_blank" rel="noopener" style="color:#0f766e;font-weight:600">${t(e.doc_num)}</a>: ${t(e.path.split(` > `).slice(1).join(` > `))}`):(n.citations||[]).map(t),o=n.rows||[],s=n.columns||[],c=o.slice(0,50),l=o.length&&s.length?`<div class="table-wrap" style="margin:12px 0"><table class="cds--data-table cds--data-table--sm"><thead><tr>${s.map(([,e])=>`<th>${t(e)}</th>`).join(``)}</tr></thead>
    <tbody>${c.map(e=>`<tr>${s.map(([n])=>`<td>${t(e[n])}</td>`).join(``)}</tr>`).join(``)}</tbody></table></div>
    ${o.length>c.length?`<div class="muted small">Hiện 50 trên ${o.length} dòng; xem đủ ở trang liên quan.</div>`:``}`:``,u=n.alternatives?.length?`<div class="alts small" style="margin-top:12px;border-top:1px dashed var(--cds-border-subtle);padding-top:8px">${n.domain?`Không đúng ý? Thử hỏi theo loại khác:`:`Có phải bạn muốn hỏi:`} ${n.alternatives.map(n=>`<button type="button" class="cds--btn cds--btn--ghost cds--btn--sm alt-q" data-q="${t(e)}" data-domain="${t(n.domain)}" style="border-radius:9999px;margin:2px">${t(n.title)}</button>`).join(``)}</div>`:``,d={SEMANTIC:`nhận dạng ngữ nghĩa`,STRUCTURE:`nhận dạng theo số hóa đơn/MST đối tác`,MODEL:`mô hình AI phân loại`,CHOSEN_BY_USER:`loại do bạn chọn`,REFUSED:`ngoài phạm vi`,KEYWORD_FALLBACK:`nhận dạng từ khóa`}[n.route?.method]||``;return`<div class="msg-bot-row">
    <div class="bot-avatar-box" aria-hidden="true">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M12 2a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2 2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z"/><rect x="3" y="8" width="18" height="12" rx="4"/><circle cx="9" cy="13" r="1.5" fill="currentColor"/><circle cx="15" cy="13" r="1.5" fill="currentColor"/><path d="M9 17h6"/></svg>
    </div>
    <div class="bot-bubble">
      <div class="bot-bubble-head">
        <span class="bot-author">Trợ lý Thuế GTGT</span>
        ${S(n.branch===`REFUSED`?`ABSTAIN`:n.branch,n.branch===`REFUSED`?`Không trả lời`:n.branch===`HELP`?`Hướng dẫn`:void 0)}
        ${i?S(i.mode):``}
        <span class="bot-time">${r}s${d?` · ${t(d)}`:``}</span>
      </div>
      ${$e(n)}
      <div class="bot-text">${t(n.text)}</div>
      ${l}
      ${a.length?`<div class="cite-box">
        <div class="cite-head"><span aria-hidden="true">📜</span> Căn cứ pháp lý trích dẫn:</div>
        <div class="cite-links">${a.join(`; `)}</div>
      </div>`:``}
      ${i?.dropped?.length?`<div class="cite-warning">⚠️ ${i.dropped.length} câu của mô hình đã bị loại bỏ do không có trích dẫn điều luật bảo đảm.</div>`:``}
      ${(n.links||[]).length?`<div class="chips" style="margin-top:10px">${n.links.map(([e,n])=>`<a class="cds--btn cds--btn--ghost cds--btn--sm" href="${t(n)}" style="border-radius:6px">${t(e)} →</a>`).join(``)}</div>`:``}
      ${u}
      <div class="bot-actions-row">
        <button type="button" class="copy-msg-btn" title="Sao chép nội dung">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
          <span>Sao chép</span>
        </button>
      </div>
    </div>
  </div>`}function tt(e,n){let r=new Date,i=`${String(r.getHours()).padStart(2,`0`)}:${String(r.getMinutes()).padStart(2,`0`)}`;return`<div class="msg-user-row">
    <div class="user-bubble-box">
      <div class="user-bubble">${t(e)}${n?` <span class="small">(đã chọn lại loại câu hỏi)</span>`:``}</div>
      <div class="user-meta"><span>Bạn</span> · <span class="msg-time">${i}</span></div>
    </div>
    <div class="user-avatar-circle" aria-hidden="true">B</div>
  </div>`}function nt(){return`<div class="chat-hero" id="chat-hero">
    <div class="hero-badge">
      <span aria-hidden="true">✨</span>
      <span>TRỢ LÝ AI ĐỐI SOÁT THUẾ GTGT</span>
    </div>
    <h2 class="hero-title">Xin chào! Trợ lý có thể hỗ trợ gì cho doanh nghiệp hôm nay?</h2>
    <p class="hero-desc">Hỏi bằng ngôn ngữ tự nhiên về số liệu thuế, rà soát hóa đơn rủi ro hoặc tra cứu căn cứ pháp lý từ Cơ sở dữ liệu Quốc gia. Dữ liệu xử lý an toàn 100% nội bộ trên máy này.</p>
    <div class="prompt-cards-grid">
      <div class="prompt-card chip-q" data-q="Quý này có bao nhiêu tiền thuế có nguy cơ bị loại?">
        <div class="card-icon">⚡</div>
        <div class="card-title">Rủi ro thuế kỳ hiện tại</div>
        <div class="card-sub">Tổng số thuế GTGT có nguy cơ và cần xem xét</div>
      </div>
      <div class="prompt-card chip-q" data-q="Hóa đơn số 340 có vấn đề gì và căn cứ xử lý?">
        <div class="card-icon">🔍</div>
        <div class="card-title">Đối chiếu hóa đơn</div>
        <div class="card-sub">Kiểm tra tính hợp lệ và cảnh báo nhà cung cấp</div>
      </div>
      <div class="prompt-card chip-q" data-q="Hạn nộp tờ khai thuế giá trị gia tăng quý 1 năm 2026 khi nào?">
        <div class="card-icon">📅</div>
        <div class="card-title">Lịch nộp tờ khai</div>
        <div class="card-sub">Theo dõi hạn nộp tờ khai và dời ngày nghỉ</div>
      </div>
      <div class="prompt-card chip-q" data-q="Điều kiện khấu trừ thuế giá trị gia tăng đầu vào gồm những gì?">
        <div class="card-icon">⚖️</div>
        <div class="card-title">Điều kiện khấu trừ</div>
        <div class="card-sub">Trích dẫn luật thuế GTGT và chứng từ thanh toán</div>
      </div>
    </div>
  </div>`}async function rt(){if(L())return;let t=f(),n=k.ws,r;u(()=>clearInterval(r));let i=`agent3.chat2.${k.ws}`,a=[];try{a=JSON.parse(sessionStorage.getItem(i)||`[]`)}catch{a=[]}let o=()=>{try{sessionStorage.setItem(i,JSON.stringify(a.slice(-30)))}catch{}};A().innerHTML=`<div class="ask-wrap">
    ${O(`Hỏi đáp`,`Hỏi đáp thuế & dữ liệu`,`TRỢ LÝ AI ĐỐI CHIẾU`)}
    
    <div id="hero-container">${a.length?``:nt()}</div>
    <div id="chat" class="chat" role="log" aria-label="Hội thoại" aria-live="polite"></div>
    <div id="pending" role="status"></div>

    <form id="ask" class="ask-bar-floating">
      <div class="ask-input-pill">
        <input class="ask-text-input" id="q" name="q" autocomplete="off" maxlength="500" placeholder="Nhập câu hỏi về hóa đơn, kỳ thuế hoặc quy định pháp luật... (Enter để gửi)">
        <button type="submit" class="send-btn" id="send-btn" title="Gửi câu hỏi" aria-label="Gửi câu hỏi">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
        </button>
      </div>
      <div class="ask-bar-footer">
        <span class="privacy-badge">🔒 Dữ liệu được xử lý an toàn nội bộ trên máy này</span>
        <div style="display:flex;align-items:center;gap:12px">
          ${a.length?`<button type="button" class="btn-clear-chat" id="clear">🗑️ Xóa hội thoại</button>`:``}
        </div>
      </div>
    </form>

    <div id="guide-box">${w(`Đang tải danh mục câu hỏi trợ lý`)}</div>
  </div>`;let s=e(`#chat`),c=e(`#pending`),l=e(`#ask`),d=l.querySelector(`[type="submit"]`),h=e(`#q`),g=e(`#hero-container`),_=()=>{s.innerHTML=a.join(``),g&&(g.innerHTML=a.length?``:nt())};_();let v=!1,y=async(e,i)=>{if(v||!e||t.aborted)return;v=!0,d.disabled=!0,h.disabled=!0,l.setAttribute(`aria-busy`,`true`),a.push(tt(e,i)),_(),s.lastElementChild?.scrollIntoView({behavior:`smooth`,block:`nearest`});let u=Date.now(),f=()=>{let e=Math.round((Date.now()-u)/1e3);t.aborted||(c.innerHTML=`
          <div class="typing-row">
            <div class="bot-avatar-box" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M12 2a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2 2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z"/><rect x="3" y="8" width="18" height="12" rx="4"/><circle cx="9" cy="13" r="1.5" fill="currentColor"/><circle cx="15" cy="13" r="1.5" fill="currentColor"/><path d="M9 17h6"/></svg>
            </div>
            <div class="typing-bubble">
              <span class="kt-typing-dots"><span class="kt-typing-dot"></span><span class="kt-typing-dot"></span><span class="kt-typing-dot"></span></span>
              <span class="typing-text">${e>3?`Đang tìm điều khoản và trích xuất căn cứ (${e}s)...`:`Trợ lý đang phân tích câu hỏi...`}</span>
            </div>
          </div>
        `)};f(),r=setInterval(f,1e3);try{let r=await m(`/api/workspaces/${n}/ask`,i?{question:e,domain:i}:{question:e},{signal:t});if(t.aborted)return;a.push(et(e,r,Math.round((Date.now()-u)/1e3)))}catch(n){if(t.aborted)return;a.push(C(`error`,`Không trả lời được`,n.message)),h.value=e}clearInterval(r),c.innerHTML=``,v=!1,d.disabled=!1,h.disabled=!1,l.removeAttribute(`aria-busy`),h.focus(),o(),_(),s.lastElementChild?.scrollIntoView({behavior:`smooth`,block:`nearest`})};e(`#ask`).onsubmit=t=>{t.preventDefault();let n=e(`#q`).value.trim();e(`#q`).value=``,y(n)},A().addEventListener(`click`,e=>{let t=e.target.closest(`.chip-q`);if(t){y(t.dataset.q);return}let n=e.target.closest(`.alt-q`);if(n){y(n.dataset.q,n.dataset.domain);return}let r=e.target.closest(`.copy-msg-btn`);if(r){let e=r.closest(`.bot-bubble`),t=e&&e.querySelector(`.bot-text`)?.innerText||``;t&&navigator.clipboard.writeText(t).then(()=>{r.classList.add(`copied`);let e=r.querySelector(`span`);e&&(e.textContent=`Đã chép!`),setTimeout(()=>{r.classList.remove(`copied`),e&&(e.textContent=`Sao chép`)},2e3)}).catch(()=>{})}else e.target.closest(`#clear`)&&(a=[],o(),_())},{signal:t});try{if(Ze||=await p(`/api/chat/guide`),t.aborted)return;e(`#guide-box`).innerHTML=Qe(Ze)}catch(n){if(t.aborted)return;e(`#guide-box`).innerHTML=C(`error`,`Không tải được hướng dẫn`,n.message)}}var it=[[`#/quan-tri`,`Tổng quan quản trị`],[`#/quan-tri/doanh-nghiep`,`Cấu hình doanh nghiệp`],[`#/quan-tri/danh-muc?ten=policy_presets`,`Quy định chi tiêu gợi ý`],[`#/quan-tri/danh-muc?ten=ai_categories`,`Nhóm hàng cho AI`],[`#/quan-tri/danh-muc?ten=holidays`,`Lịch nghỉ lễ`],[`#/quan-tri/danh-muc?ten=law_topics`,`Chủ đề tin luật`],[`#/quan-tri/danh-muc?ten=chat_domains`,`Câu hỏi của trợ lý`],[`#/quan-tri/kho-luat`,`Kho luật`],[`#/quan-tri/lich-su`,`Lịch sử thay đổi`]],Y=Object.fromEntries(it.filter(([e])=>e.includes(`ten=`)).map(([e,t])=>[e.split(`ten=`)[1],t]));async function at(){return p(`/api/admin/status`)}function ot(){let e=location.hash,n=t=>e===t||t===`#/quan-tri/doanh-nghiep`&&e.startsWith(`#/thiet-lap`)||t!==`#/quan-tri`&&e.startsWith(t);return`<nav class="admin-nav" aria-label="Quản trị">${it.map(([e,r])=>`<a href="${e}" class="${n(e)?`on`:``}">${t(r)}</a>`).join(``)}
    <button type="button" class="cds--btn cds--btn--ghost cds--btn--sm" id="admin-logout">Đăng xuất quản trị</button></nav>`}function st(){let t=e(`#admin-logout`);t&&(t.onclick=async()=>{await m(`/api/admin/logout`),G(`Đã đăng xuất quản trị`),location.hash=`#/`})}function ct(t){let n=!t.configured;A().innerHTML=`<span class="eyebrow">Hệ thống bảo vệ</span>
    <h1 class="page">Quản trị hệ thống</h1>
    <p class="lead">${n?`Lần đầu sử dụng: đặt mật khẩu quản trị. Mật khẩu này dùng để thay đổi cấu hình doanh nghiệp, danh mục dùng chung và kho luật; công việc hằng ngày (nạp dữ liệu, xử lý việc, hỏi đáp) không cần mật khẩu.`:`Khu vực quản trị cấu hình và danh mục hệ thống. Vui lòng nhập mật khẩu quản trị để tiếp tục.`}</p>
    <div style="display:flex;justify-content:center;margin:32px 0">
      <form id="admin-form" class="panel narrow" style="width:100%;max-width:440px">
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:20px;padding-bottom:14px;border-bottom:1px solid var(--cds-border-subtle)">
          <div style="background:var(--a3-primary-soft);color:var(--a3-primary);width:40px;height:40px;border-radius:10px;display:grid;place-items:center;flex:none">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
          </div>
          <div>
            <h3 style="margin:0;font-size:16px;font-weight:600">${n?`Thiết lập mật khẩu quản trị`:`Xác thực quản trị viên`}</h3>
            <span class="muted small">${t.ttl_minutes} phút không thao tác sẽ tự khóa</span>
          </div>
        </div>
        <div class="cds--form-item cds--text-input-wrapper"><label class="cds--label" for="pw">Mật khẩu${n?` mới (ít nhất 8 ký tự)`:``}</label>
        <input class="cds--text-input son-box" id="pw" type="password" autocomplete="${n?`new-password`:`current-password`}" required></div>
        ${n?`<div class="cds--form-item cds--text-input-wrapper"><label class="cds--label" for="pw2">Nhập lại mật khẩu</label><input class="cds--text-input son-box" id="pw2" type="password" autocomplete="new-password" required></div>`:``}
        <div class="bar" style="margin-top:20px">${T(n?`Đặt mật khẩu`:`Đăng nhập`,`primary`,`type="submit"`)}</div><div id="admin-msg"></div>
        <p class="muted small" style="margin-top:14px">Mật khẩu được mã hóa băm an toàn trên máy cục bộ.</p>
      </form>
    </div>`,e(`#admin-form`).onsubmit=async t=>{t.preventDefault();let r=e(`#pw`).value;if(n&&r!==e(`#pw2`).value)e(`#admin-msg`).innerHTML=C(`error`,`Hai lần nhập không khớp`);else try{await m(n?`/api/admin/setup`:`/api/admin/login`,{password:r}),G(n?`Đã đặt mật khẩu quản trị`:`Đã đăng nhập quản trị`),window.dispatchEvent(new Event(`hashchange`))}catch(t){e(`#admin-msg`).innerHTML=C(`error`,n?`Không đặt được mật khẩu`:`Không đăng nhập được`,t.message)}}}function X(e){return async()=>{let t=await at();t.logged_in?(await e(),A().insertAdjacentHTML(`afterbegin`,ot()),st()):ct(t)}}async function lt(){let n=await p(`/api/admin/catalog`);A().innerHTML=`<span class="eyebrow">Bảng điều khiển quản trị</span>
    <h1 class="page">Quản trị và Danh mục dùng chung</h1>
    <p class="lead">Mọi thay đổi ở đây được kiểm tra hợp lệ, ghi phiên bản và lưu vào nhật ký lịch sử. Danh mục dùng chung áp dụng cho mọi doanh nghiệp; cấu hình doanh nghiệp áp dụng riêng cho từng không gian.</p>
    <div class="grid2">
      <div class="panel" style="border-radius:12px;padding:24px 26px;box-shadow:var(--a3-shadow-sm)">
        <h3 style="margin-top:0;font-size:17px;font-weight:600;display:flex;align-items:center;gap:8px">
          <span>🏢</span> Doanh nghiệp từ portal
        </h3>
        <p class="muted" style="font-size:13.5px;line-height:1.65">Doanh nghiệp từ hồ sơ chung tại portal: <strong>${t(k.workspaces.find(e=>e.id===k.ws)?.name||`chưa chọn`)}</strong>.</p>
        <div class="bar" style="margin-top:20px">
          ${T(`Cấu hình doanh nghiệp này`,`primary`,`data-go="#/quan-tri/doanh-nghiep"`)}
          ${T(`Chạy wizard thiết lập (5 bước)`,`ghost`,`data-go="#/thiet-lap"`)}
        </div>
      </div>
      <div class="panel" style="border-radius:12px;padding:24px 26px;box-shadow:var(--a3-shadow-sm)">
        <h3 style="margin-top:0;font-size:17px;font-weight:600;display:flex;align-items:center;gap:8px">
          <span>📚</span> Danh mục dùng chung toàn hệ thống
        </h3>
        <ul class="list-plain" style="margin-top:14px">
          ${n.map(e=>`<li style="padding:10px 0;border-bottom:1px solid var(--cds-border-subtle);display:flex;justify-content:space-between;align-items:center">
            <a href="#/quan-tri/danh-muc?ten=${e.name}" style="font-weight:500;text-decoration:none">${t(Y[e.name]||e.name)}</a>
            <span class="cds--tag cds--tag--teal" style="font-size:11.5px">v${t(e.version)}</span>
          </li>`).join(``)}
        </ul>
      </div>
    </div>
    <div class="panel narrow" style="border-radius:12px;padding:24px 26px;box-shadow:var(--a3-shadow-sm);margin-top:24px;max-width:560px">
      <h3 style="margin-top:0;font-size:17px;font-weight:600;display:flex;align-items:center;gap:8px">
        <span>🔑</span> Đổi mật khẩu quản trị
      </h3>
      <form id="pwchg" style="margin-top:16px">
        <div class="form-grid">
          <div class="cds--form-item cds--text-input-wrapper"><label class="cds--label" for="old">Mật khẩu hiện tại</label><input class="cds--text-input" id="old" type="password" autocomplete="current-password"></div>
          <div class="cds--form-item cds--text-input-wrapper"><label class="cds--label" for="new">Mật khẩu mới</label><input class="cds--text-input" id="new" type="password" autocomplete="new-password"></div>
        </div>
        <div class="bar" style="margin-top:18px">${T(`Đổi mật khẩu`,`secondary`,`type="submit"`)}</div>
      </form>
    </div>`,e(`#pwchg`).onsubmit=async t=>{t.preventDefault();try{G(`Đã đổi mật khẩu`,(await m(`/api/admin/password`,{old:e(`#old`).value,new:e(`#new`).value})).note),window.dispatchEvent(new Event(`hashchange`))}catch(e){G(`Không đổi được mật khẩu`,e.message,`error`)}}}var Z=e=>e.split(`
`).map(e=>e.trim()).filter(Boolean),ut=e=>e.split(`,`).map(e=>e.trim()).filter(Boolean),Q=(e,n,r=``)=>`<input class="cds--text-input ${e}" value="${t(n??``)}" ${r}>`,$={policy_presets:{help:`Mỗi dòng là một quy định gợi ý khi thiết lập doanh nghiệp. "Ngành" là hai chữ số đầu mã VSIC (cách nhau dấu phẩy) để gợi ý theo ngành; để trống là gợi ý cho mọi doanh nghiệp. Quy định chỉ thêm nhắc nhở, không đổi kết quả theo luật.`,render:e=>`<div class="table-wrap"><table class="cds--data-table cds--data-table--sm edit-table"><thead><tr><th>Mã</th><th>Nội dung nhắc</th><th>Nhóm</th><th>Ngành</th><th>Từ số tiền</th><th>Khi tên hàng có</th><th>Đánh dấu sẵn</th><th></th></tr></thead>
      <tbody id="rows">${e.presets.map(e=>$.policy_presets.row(e)).join(``)}</tbody></table></div>${T(`Thêm quy định`,`ghost`,`id="add-row"`)}`,row:(e={})=>`<tr><td>${Q(`f-id`,e.id,`placeholder="VD: VAN_PHONG_PHAM"`)}</td><td>${Q(`f-flag`,e.flag)}</td><td>${Q(`f-group`,e.group||`Chung`)}</td>
      <td>${Q(`f-for`,(e.for||[]).join(`, `),`placeholder="62, 63"`)}</td><td>${Q(`f-min`,e.min_gross??``,`inputmode="numeric"`)}</td>
      <td>${Q(`f-words`,(e.description_contains||[]).join(`, `))}</td><td><input type="checkbox" class="f-rec" ${e.recommended?`checked`:``}></td>
      <td><button type="button" class="cds--btn cds--btn--ghost cds--btn--sm del-row">Xóa</button></td></tr>`,read:e=>({...e,presets:[...A().querySelectorAll(`#rows tr`)].map(e=>{let t=t=>e.querySelector(t).value.trim(),n={id:t(`.f-id`).toUpperCase(),flag:t(`.f-flag`),group:t(`.f-group`),for:ut(t(`.f-for`)),recommended:e.querySelector(`.f-rec`).checked};return t(`.f-min`)&&(n.min_gross=Number(t(`.f-min`).replace(/\D/g,``))),t(`.f-words`)&&(n.description_contains=ut(t(`.f-words`))),n}).filter(e=>e.id||e.flag)})},ai_categories:{help:`Nhóm hàng mà AI chọn khi phân loại từng dòng hàng trên hóa đơn mua vào. Mô tả càng cụ thể AI càng chọn đúng. Nhóm CA_NHAN (đồ cá nhân) và KHONG_RO (không rõ) là nhóm hệ thống, không xóa được. Đổi danh mục thì nên chạy lại "Phân loại dòng hàng".`,render:e=>`<div class="table-wrap"><table class="cds--data-table cds--data-table--sm edit-table"><thead><tr><th>Mã nhóm</th><th>Mô tả cho AI</th><th></th></tr></thead>
      <tbody id="rows">${e.categories.map(t=>$.ai_categories.row(t,e.system)).join(``)}</tbody></table></div>${T(`Thêm nhóm`,`ghost`,`id="add-row"`)}`,row:(e={},t=[])=>`<tr><td>${Q(`f-id`,e.id,t.includes(e.id)?`readonly`:`placeholder="VD: THIET_BI_Y_TE"`)}</td><td>${Q(`f-desc`,e.description)}</td>
      <td>${t.includes(e.id)?`<span class="muted small">hệ thống</span>`:`<button type="button" class="cds--btn cds--btn--ghost cds--btn--sm del-row">Xóa</button>`}</td></tr>`,read:e=>({...e,categories:[...A().querySelectorAll(`#rows tr`)].map(e=>({id:e.querySelector(`.f-id`).value.trim().toUpperCase(),description:e.querySelector(`.f-desc`).value.trim()})).filter(e=>e.id)})},holidays:{help:`Ngày nghỉ dùng để dời hạn nộp hồ sơ thuế khi hạn trùng ngày nghỉ (thứ Bảy, Chủ nhật luôn được tính). Ngày lễ cố định lặp lại mỗi năm; nghỉ Tết, nghỉ bù thay đổi theo năm, nhập theo thông báo của Bộ Nội vụ. Bỏ đánh dấu "Đã đối chiếu" với ngày chỉ là phương án dự kiến.`,render:e=>{let n=Object.keys(e.years||{}).sort();return`<h3>Ngày lễ cố định hằng năm</h3><div class="table-wrap"><table class="cds--data-table cds--data-table--sm edit-table"><thead><tr><th>Ngày</th><th>Tháng</th><th>Tên</th><th></th></tr></thead>
        <tbody id="fixed">${e.fixed.map(e=>`<tr><td>${Q(`f-day`,e.day,`inputmode="numeric"`)}</td><td>${Q(`f-month`,e.month,`inputmode="numeric"`)}</td><td>${Q(`f-name`,e.name)}</td><td><button type="button" class="cds--btn cds--btn--ghost cds--btn--sm del-row">Xóa</button></td></tr>`).join(``)}</tbody></table></div>
        ${n.map(t=>`<h3>Năm ${t}</h3><div class="table-wrap"><table class="cds--data-table cds--data-table--sm edit-table"><thead><tr><th>Ngày</th><th>Tên</th><th>Đã đối chiếu</th><th></th></tr></thead>
          <tbody class="year" data-year="${t}">${e.years[t].map(e=>$.holidays.row(e)).join(``)}</tbody></table></div>
          <button type="button" class="cds--btn cds--btn--ghost cds--btn--sm add-day" data-year="${t}">Thêm ngày nghỉ năm ${t}</button>`).join(``)}
        <div class="bar"><input class="cds--text-input filter-input" id="new-year" placeholder="Năm mới, VD 2028" inputmode="numeric">${T(`Thêm năm`,`ghost`,`id="add-year"`)}</div>
        ${(e.sources||[]).length?`<p class="muted small">Nguồn đã dùng: ${e.sources.map(e=>`<a href="${t(e)}" target="_blank" rel="noopener">${t(new URL(e).hostname)}</a>`).join(`, `)}</p>`:``}`},row:(e={})=>`<tr><td>${Q(`f-date`,e.date,`type="date"`)}</td><td>${Q(`f-name`,e.name)}</td><td><input type="checkbox" class="f-ver" ${e.verified===!1?``:`checked`}></td><td><button type="button" class="cds--btn cds--btn--ghost cds--btn--sm del-row">Xóa</button></td></tr>`,read:e=>({...e,fixed:[...A().querySelectorAll(`#fixed tr`)].map(e=>({day:Number(e.querySelector(`.f-day`).value),month:Number(e.querySelector(`.f-month`).value),name:e.querySelector(`.f-name`).value.trim()})),years:Object.fromEntries([...A().querySelectorAll(`tbody.year`)].map(e=>[e.dataset.year,[...e.querySelectorAll(`tr`)].map(e=>({date:e.querySelector(`.f-date`).value,name:e.querySelector(`.f-name`).value.trim(),verified:e.querySelector(`.f-ver`).checked})).filter(e=>e.date)]))})},law_topics:{help:`Tin luật mới được lọc theo độ gần nghĩa giữa trích yếu văn bản và các chủ đề dưới đây (mô hình bge-m3 chạy trên máy). Viết mỗi chủ đề một dòng, càng cụ thể càng tốt. "Chủ đề loại trừ" là từ khóa của văn bản khu vực công cần bỏ qua.`,render:e=>`<div class="cds--form-item"><label class="cds--label" for="topics">Chủ đề liên quan (mỗi dòng một chủ đề)</label><textarea class="cds--text-area" id="topics" rows="12">${t(e.topics.join(`
`))}</textarea></div>
      <div class="cds--form-item"><label class="cds--label" for="noise">Chủ đề loại trừ (mỗi dòng một cụm từ, viết không dấu)</label><textarea class="cds--text-area" id="noise" rows="6">${t((e.noise||[]).join(`
`))}</textarea></div>`,read:t=>({...t,topics:Z(e(`#topics`).value),noise:Z(e(`#noise`).value)})},chat_domains:{help:`Mỗi loại câu hỏi có mô tả (hiện ở trang Hỏi đáp), câu ví dụ để trợ lý học cách nhận ra loại câu đó, và câu gợi ý hiện cho người dùng. Thêm câu ví dụ đúng cách người dùng hay hỏi giúp trợ lý nhận dạng tốt hơn. Thêm loại câu hỏi mới cần lập trình hàm trả lời nên không làm được ở đây.`,render:e=>e.domains.map(e=>`<details class="guide-group domain-edit" data-id="${t(e.id)}"><summary>${t(e.title)} <span class="muted small">${t(e.id)}, ${e.examples.length} câu ví dụ${e.examples_generated?.length?`, ${e.examples_generated.length} câu do mô hình viết đã lọc`:``}</span></summary>
      <div class="form-grid"><div class="cds--form-item"><label class="cds--label">Tên loại câu hỏi</label>${Q(`f-title`,e.title)}</div>
      <div class="cds--form-item"><label class="cds--label">Giới hạn</label>${Q(`f-limits`,e.limits)}</div></div>
      <div class="cds--form-item"><label class="cds--label">Trả lời được</label><textarea class="cds--text-area f-what" rows="2">${t(e.what)}</textarea></div>
      <div class="form-grid"><div class="cds--form-item"><label class="cds--label">Câu ví dụ để nhận dạng (mỗi dòng một câu, ít nhất 3)</label><textarea class="cds--text-area f-ex" rows="8">${t(e.examples.join(`
`))}</textarea></div>
      <div class="cds--form-item"><label class="cds--label">Câu gợi ý hiện cho người dùng (dùng &lt;...&gt; cho chỗ cần điền)</label><textarea class="cds--text-area f-guide" rows="8">${t((e.guide||[]).join(`
`))}</textarea></div></div></details>`).join(``),read:e=>({...e,domains:e.domains.map(e=>{let t=A().querySelector(`.domain-edit[data-id="${e.id}"]`);return{...e,title:t.querySelector(`.f-title`).value.trim(),limits:t.querySelector(`.f-limits`).value.trim(),what:t.querySelector(`.f-what`).value.trim(),examples:Z(t.querySelector(`.f-ex`).value),guide:Z(t.querySelector(`.f-guide`).value)}})})}};async function dt(){let n=new URLSearchParams(location.hash.split(`?`)[1]||``).get(`ten`)||`policy_presets`,r=$[n];if(!r){A().innerHTML=C(`error`,`Không có danh mục này`);return}let{data:i,history:a}=await p(`/api/admin/catalog/${n}`);A().innerHTML=`<span class="eyebrow">Danh mục dùng chung hệ thống</span>
    <h1 class="page">${t(Y[n])}</h1>
    <p class="lead">${t(r.help)}</p>
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:20px">
      <span class="cds--tag cds--tag--teal">Phiên bản ${t(i.version)}</span>
      <span class="muted small">Áp dụng chung cho mọi doanh nghiệp trên máy này</span>
    </div>
    <form id="cat-form"><div id="cat-body" class="panel" style="border-radius:12px;padding:24px 26px;box-shadow:var(--a3-shadow-sm);margin-bottom:24px">${r.render(i)}</div>
    <div class="bar sticky-save"><input class="cds--text-input filter-input" id="by" placeholder="Người sửa" value="${t(o.get(`agent3.reviewer`)||``)}" required>
    ${T(`Lưu danh mục`,`primary`,`type="submit"`)}<span id="cat-msg"></span></div></form>
    ${a.length?`<h2 class="section">Nhật ký phiên bản danh mục</h2><ul class="list-plain small" style="background:var(--a3-surface);border:1px solid var(--cds-border-subtle);border-radius:10px;padding:16px 20px">${a.map(e=>`<li style="padding:6px 0;border-bottom:1px solid var(--cds-border-subtle)">${t(e.at.replace(`T`,` `))}: <strong>${t(e.by)}</strong> ${t(JSON.stringify(e.summary))}</li>`).join(``)}</ul>`:``}`;let s=e(`#cat-body`);s.addEventListener(`click`,e=>{e.target.closest(`.del-row`)&&e.target.closest(`tr`).remove();let t=e.target.closest(`.add-day`);t&&A().querySelector(`tbody.year[data-year="${t.dataset.year}"]`).insertAdjacentHTML(`beforeend`,$.holidays.row({date:`${t.dataset.year}-01-01`,name:``}))}),e(`#add-row`)&&(e(`#add-row`).onclick=()=>e(`#rows`).insertAdjacentHTML(`beforeend`,r.row({},i.system||[]))),e(`#add-year`)&&(e(`#add-year`).onclick=()=>{let t=e(`#new-year`).value.trim();/^20\d{2}$/.test(t)?(i.years={...r.read(i).years,[t]:[]},s.innerHTML=r.render({...r.read(i),years:i.years})):G(`Năm không hợp lệ`,``,`error`)}),e(`#cat-form`).onsubmit=async t=>{t.preventDefault();let a=e(`#by`).value.trim();if(!a)G(`Cần ghi tên người sửa`,``,`error`);else{o.set(`agent3.reviewer`,a);try{G(`Đã lưu danh mục`,`phiên bản ${(await h(`/api/admin/catalog/${n}?by=${encodeURIComponent(a)}`,r.read(i))).version}`),window.dispatchEvent(new Event(`hashchange`))}catch(t){e(`#cat-msg`).innerHTML=C(`error`,`Chưa lưu được`,t.message)}}}}async function ft(){let e=(await Promise.all(Object.keys(Y).map(e=>p(`/api/admin/catalog/${e}`).then(t=>t.history.map(t=>({...t,label:Y[e]})))))).flat().sort((e,t)=>e.at<t.at?1:-1),n=[];if(k.ws)try{n=await p(`/api/workspaces/${k.ws}/pack/history`)}catch{n=[]}A().innerHTML=`<h1 class="page">Lịch sử thay đổi</h1><h2 class="section">Danh mục dùng chung</h2>
    ${e.length?`<ul class="list-plain small">${e.map(e=>`<li>${t(e.at.replace(`T`,` `))}: <strong>${t(e.label)}</strong>, ${t(e.by)}, ${t(JSON.stringify(e.summary))}</li>`).join(``)}</ul>`:`<p class="muted">Chưa có thay đổi.</p>`}
    <h2 class="section">Cấu hình doanh nghiệp đang chọn</h2>
    ${n.length?`<ul class="list-plain small">${n.slice().reverse().map(e=>`<li>${t((e.at||``).replace(`T`,` `))}: ${t(e.by||``)} ${t(JSON.stringify(e.changes||e.diff||e))}</li>`).join(``)}</ul>`:`<p class="muted">Chưa có thay đổi.</p>`}`}var pt=[[`#/`,`Tổng quan`,Le],[`#/nap`,`Nạp dữ liệu`,le],[`#/viec`,`Việc cần xử lý`,He],[`#/hoa-don`,`Hóa đơn`,qe],[`#/hoi`,`Hỏi đáp`,rt]],mt=[[`#/du-lieu`,`Bảng kê đang sử dụng`,ce],[`#/quan-tri/mau-sao-ke`,`Nhận dạng cột sao kê`,X(se)],[`#/ngan-hang`,`Ngân hàng`,Je],[`#/so-lieu`,`Số liệu thuế GTGT`,xe],[`#/giai-trinh`,`Giải trình`,be],[`#/lich`,`Lịch thuế`,Ye],[`#/luat`,`Kho luật`,Xe],[`#/tin-luat`,`Kho luật`,Xe],[`#/quan-tri`,`Quản trị`,X(lt)],[`#/quan-tri/doanh-nghiep`,`Cấu hình doanh nghiệp`,X(Me)],[`#/quan-tri/danh-muc`,`Danh mục dùng chung`,X(dt)],[`#/quan-tri/kho-luat`,`Kho luật`,X(Xe)],[`#/quan-tri/lich-su`,`Lịch sử thay đổi`,X(ft)],[`#/thiet-lap`,`Thiết lập nghiệp vụ thuế`,X(je)],[`#/cai-dat`,`Cấu hình doanh nghiệp`,X(Me)]],ht=[`#/ngan-hang`,`#/so-lieu`,`#/giai-trinh`,`#/lich`,`#/luat`,`#/tin-luat`,`#/du-lieu`];function gt(n){let r=n.startsWith(`#/quan-tri`)||[`#/thiet-lap`,`#/cai-dat`].includes(n)?`#/quan-tri`:n;e(`#nav`).innerHTML=pt.map(([e,n])=>`<li class="cds--side-nav__item"><a class="cds--side-nav__link" href="${e}" ${e===r?`aria-current="page"`:``}>
    <span class="cds--side-nav__link-text">${t(n)}</span></a></li>`).join(``),e(`.admin-link`).setAttribute(`aria-current`,r===`#/quan-tri`?`page`:`false`),V(e(`#nav`))}async function _t(){let n=d(),r=location.hash.split(`?`)[0]||`#/`;if(n.aborted)return;if(r===`#/nap`&&k.ws&&R()){window.top.location.href=R()+`/#data`;return}gt(r);let i=e(`#active-company`);i&&(i.title=i.textContent),document.body.classList.remove(`nav-open`),e(`.menu-toggle`).setAttribute(`aria-expanded`,`false`),e(`#modal-root`).innerHTML=``;let a=pt.find(([e])=>e===r)||mt.find(([e])=>e===r)||pt[0],o=a[2];document.title=`${a[1]} · Agent 3 Trợ lý thuế`;try{if(L())return;await o()}catch(e){if(n.aborted)return;A().innerHTML=`<h1 class="page">${t(a[1])}</h1>`+C(`error`,`Có lỗi khi tải trang`,e.message)}!n.aborted&&ht.includes(r)&&!A().querySelector(`.back-crumb`)&&A().insertAdjacentHTML(`afterbegin`,`<a class="back-crumb" href="#/">← Quay về Tổng quan</a>`),!n.aborted&&[`#/viec`,`#/so-lieu`,`#/giai-trinh`,`#/lich`].includes(r)&&A().querySelector(`h1`)?.insertAdjacentHTML(`afterend`,C(`warning`,`Kết quả tham khảo theo quy tắc nháp`,`Chưa có chuyên gia thuế duyệt; chưa xác nhận nghĩa vụ kê khai, nộp thuế hoặc xử phạt.`)),n.aborted||(V(A()),document.querySelector(`.drawer`)||A().focus({preventScroll:!0}))}document.addEventListener(`click`,e=>{let t=e.target.closest(`[data-go]`);t&&(location.hash=t.dataset.go)}),e(`.menu-toggle`).setAttribute(`aria-expanded`,`false`),e(`.menu-toggle`).onclick=()=>{let t=document.body.classList.toggle(`nav-open`);e(`.menu-toggle`).setAttribute(`aria-expanded`,String(t))};var vt=window.self!==window.top,yt=vt?o.get(`agent3.theme.embedded`)||`g10`:o.get(`agent3.theme`)||(window.matchMedia?.(`(prefers-color-scheme: dark)`).matches?`g100`:`g10`);document.body.className=`cds--${yt}`,e(`.theme-toggle`).onclick=()=>{let e=document.body.classList.contains(`cds--g100`)?`g10`:`g100`;document.body.className=`cds--${e}`,o.set(vt?`agent3.theme.embedded`:`agent3.theme`,e)},window.addEventListener(`hashchange`,_t),H(),e(`.skip-link`).onclick=e=>{e.preventDefault(),A().focus()};var bt=null;new MutationObserver(()=>{bt||=setTimeout(()=>{bt=null,V(A())},100)}).observe(A(),{childList:!0,subtree:!0}),document.addEventListener(`keydown`,t=>{t.key===`Escape`&&(e(`#modal-root`).innerHTML?e(`#modal-root`).innerHTML=``:document.body.classList.contains(`nav-open`)&&(document.body.classList.remove(`nav-open`),e(`.menu-toggle`).setAttribute(`aria-expanded`,`false`),e(`.menu-toggle`).focus()))}),M().then(_t).catch(e=>{A().innerHTML=C(`error`,`Không kết nối được máy chủ Agent 3`,e.message)});var xt=!1;async function St(){if(!(xt||document.hidden)){xt=!0;try{let t=await fetch(`/api/platform/context`,{cache:`no-store`});if(!t.ok)return;let n=await t.json();if(!k.platform||n.profile_revision!==k.platform.profile_revision||n.workspace_id!==k.platform.workspace_id||n.state!==k.platform.state){let t=[...A().querySelectorAll(`input,select,textarea`)].filter(e=>![`password`,`file`,`hidden`].includes(e.type)).map(e=>({name:e.name||e.id||e.dataset.f,value:e.value,checked:e.checked}));if(t.length)try{sessionStorage.setItem(`agent3.previous-context-draft`,JSON.stringify({revision:k.platform?.profile_revision,path:location.hash,fields:t}))}catch{}k.platform=n,d(),k.report=null,e(`#modal-root`).replaceChildren(),await M(),await _t(),t.length&&A().insertAdjacentHTML(`afterbegin`,C(`warning`,`Hồ sơ portal đã thay đổi`,`Bản nháp cũ được giữ riêng trong phiên trình duyệt; không áp dụng sang doanh nghiệp mới.`))}}catch{}finally{xt=!1}}}setInterval(St,4e3),document.addEventListener(`visibilitychange`,St),window.addEventListener(`agent3-context-stale`,St);