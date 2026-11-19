(function(){let e=document.createElement(`link`).relList;if(e&&e.supports&&e.supports(`modulepreload`))return;for(let e of document.querySelectorAll(`link[rel="modulepreload"]`))n(e);new MutationObserver(e=>{for(let t of e)if(t.type===`childList`)for(let e of t.addedNodes)e.tagName===`LINK`&&e.rel===`modulepreload`&&n(e)}).observe(document,{childList:!0,subtree:!0});function t(e){let t={};return e.integrity&&(t.integrity=e.integrity),e.referrerPolicy&&(t.referrerPolicy=e.referrerPolicy),t.credentials=e.crossOrigin===`use-credentials`?`include`:e.crossOrigin===`anonymous`?`omit`:`same-origin`,t}function n(e){if(e.ep)return;e.ep=!0;let n=t(e);fetch(e.href,n)}})();var e=(e,t=document)=>t.querySelector(e),t=e=>String(e??``).replace(/[&<>"']/g,e=>({"&":`&amp;`,"<":`&lt;`,">":`&gt;`,'"':`&quot;`,"'":`&#39;`})[e]),n=e=>{if(e==null||e===``)return`—`;let t=String(e);if(!/^-?\d+(\.\d+)?$/.test(t))return`Không xác định`;let[n,r=``]=t.split(`.`),i=r.replace(/0+$/,``);return n.replace(/\B(?=(\d{3})+(?!\d))/g,`.`)+(i?`,`+i:``)+` đ`};function r(e){if(e==null||e===``)return`<span class="kpi-amount-empty">—</span>`;let t=String(e);if(!/^-?\d+(\.\d+)?$/.test(t))return`<span class="kpi-amount-empty">Không xác định</span>`;let[n,r=``]=t.split(`.`),i=r.replace(/0+$/,``),a=n.startsWith(`-`),o=n.replace(/^-/,``).replace(/\B(?=(\d{3})+(?!\d))/g,`.`);return`<span class="kpi-money-wrap">
    ${a?`<span class="kpi-sign">-</span>`:``}
    <span class="kpi-digits">${o}</span>
    ${i?`<span class="kpi-tail">,${i}</span>`:``}
    <span class="kpi-currency-symbol">₫</span>
  </span>`}function i(e,t){let n=e=>String(e??`0`).split(`.`),[r,i=``]=n(e),[a,o=``]=n(t),s=Math.max(i.length,o.length),c=(e,t)=>BigInt((e.startsWith(`-`)?`-`:``)+e.replace(/^-/,``)+t.padEnd(s,`0`)),l=c(r,i),u=c(a,o);return l>u?1:l<u?-1:0}var a=e=>e?e.slice(0,10).split(`-`).reverse().join(`/`):``,o={get(e){try{return localStorage.getItem(e)}catch{return null}},set(e,t){try{localStorage.setItem(e,t)}catch{}}},s=new Map,c=new AbortController,l=[];function u(e){l.push(e)}function d(){return c.abort(),l.splice(0).forEach(e=>e()),c=new AbortController,c.signal}var f=()=>c.signal;async function p(e,t={}){let n=t.signal||c.signal,r=new Headers(t.headers),i=e.split(`?`)[0];e.startsWith(`/api/workspaces/`)&&(r.set(`X-Agent3-Profile-Revision`,N.platform?.profile_revision||``),t.method===`PUT`&&i.endsWith(`/pack`)&&s.has(i)&&r.set(`If-Match`,s.get(i)));let a=N.platform?.profile_revision,o=await fetch(e,{...t,headers:r,signal:n}),l=(o.headers.get(`content-type`)||``).includes(`json`)?await o.json():await o.text();if(n.throwIfAborted(),e.startsWith(`/api/workspaces/`)&&a!==N.platform?.profile_revision)throw new DOMException(`Context changed`,`AbortError`);if(o.headers.get(`etag`)&&s.set(i,o.headers.get(`etag`)),!o.ok&&l?.detail?.context_stale&&window.dispatchEvent(new Event(`agent3-context-stale`)),!o.ok){let e=Error(typeof l==`object`?l.detail?.message||l.detail||JSON.stringify(l):l);throw e.status=o.status,e}return l}var m=(e,t,n={})=>p(e,{...n,method:`POST`,headers:{"Content-Type":`application/json`,...n.headers},body:JSON.stringify(t??{})}),h=(e,t)=>p(e,{method:`PUT`,headers:{"Content-Type":`application/json`},body:JSON.stringify(t)});async function g(){let e=`/api/workspaces/${N.ws}/decisions`,t=await p(e);return{etag:s.get(e),events:t.events||[],report_revision:N.report?.meta.report_revision,workspace:N.ws,revision:N.platform?.profile_revision}}async function _(e,t,n){if(!n?.etag||!n.report_revision)throw Error(`Cần chạy phân tích và tải lại quyết định trước khi lưu.`);if(n.workspace!==N.ws||n.revision!==N.platform?.profile_revision)throw Error(`Hồ sơ đã thay đổi; không gửi quyết định cũ.`);let r=JSON.stringify(t);return r!==n.body&&(n.request_id=crypto.randomUUID(),n.body=r),m(e,{...t,request_id:n.request_id,report_revision:n.report_revision},{headers:{"If-Match":n.etag}})}async function v(e){let t=`/api/workspaces/${N.ws}/pack`,n=`/api/workspaces/${N.ws}/bank/formats`,r=await m(n,e,{headers:{"If-Match":s.get(t)||``}});return s.has(n)&&s.set(t,s.get(n)),r}var y=e=>e==null?`Chưa đủ dữ liệu / không áp dụng`:`${String(e).startsWith(`-`)?`Đầu vào vượt đầu ra`:`Đầu ra vượt đầu vào`}: ${n(String(e).replace(/^-/,``))}`,b=e=>{let t=Number(e);if(!Number.isFinite(t)||Math.abs(t)<1e6)return``;let n=e=>e.toLocaleString(`vi-VN`,{maximumFractionDigits:1});return Math.abs(t)>=0xe8d4a51000?`${n(t/0xe8d4a51000)} nghìn tỷ đồng`:Math.abs(t)>=1e9?`${n(t/1e9)} tỷ đồng`:`${n(t/1e6)} triệu đồng`},x={AT_RISK:[`Có nguy cơ bị loại`,`red`],REVIEW:[`Cần xem xét`,`magenta`],OPPORTUNITY:[`Có thể đang bỏ sót`,`blue`],INFO:[`Thông tin`,`gray`],LLM_VERIFIED:[`Đã kiểm tra căn cứ`,`green`],EXTRACTIVE:[`Trích nguyên văn`,`teal`],ABSTAIN:[`Không đủ căn cứ`,`gray`],DATA:[`Dữ liệu doanh nghiệp`,`cool-gray`],POLICY:[`Quy định`,`purple`],JUDGMENT:[`Cần chuyên gia`,`warm-gray`]},S=(e,n)=>{let[r,i]=x[e]||[n||e,`gray`];return`<div class="cds--tag cds--tag--${i}"><span class="cds--tag__label">${t(n||r)}</span></div>`},C=(e,n,r=``)=>`<div class="cds--inline-notification cds--inline-notification--${e} cds--inline-notification--low-contrast notice" role="${e===`error`?`alert`:`status`}">
  <div class="cds--inline-notification__details"><div class="cds--inline-notification__text-wrapper">
  <div class="cds--inline-notification__title">${t(n)}</div><div class="cds--inline-notification__subtitle">${t(r)}</div></div></div></div>`,w=(e=`Đang xử lý`)=>`<div class="bar kt-loading-wrap" style="display:inline-flex;align-items:center;gap:10px;padding:6px 0" aria-live="polite"><span class="kt-spinner teal" aria-hidden="true"></span><span class="muted" style="font-size:13px;font-weight:500">${t(e)}...</span></div>`,T=(e,n=`primary`,r=``)=>`<button ${/\btype=/.test(r)?``:`type="button" `}class="cds--btn cds--btn--${n} cds--btn--md" ${r}>${t(e)}</button>`,E=(e,n=``)=>{let r=`f-${e.key}`,i=e.help?`<div class="cds--form__helper-text">${t(e.help)}</div>`:``,a=e.required?``:` (không bắt buộc)`;if(e.type===`choice`)return`<div class="cds--form-item"><div class="cds--select"><label class="cds--label" for="${r}">${t(e.label)}${a}</label>
      <div class="cds--select-input__wrapper"><select class="cds--select-input" id="${r}" name="${e.key}" ${e.required?`required`:``}>
      ${e.choices.map(([e,r])=>`<option value="${t(e)}" ${e===n?`selected`:``}>${t(r)}</option>`).join(``)}</select></div>${i}</div></div>`;let o=Array.isArray(n)?n.join(`; `):n;return`<div class="cds--form-item cds--text-input-wrapper"><label class="cds--label" for="${r}">${t(e.label)}${a}</label>
    <div class="cds--text-input__field-wrapper"><input class="cds--text-input" id="${r}" name="${e.key}" value="${t(o)}" placeholder="${t(e.example||``)}" ${e.required?`required`:``}></div>${i}</div>`},D=(e,n,r=`Không có dữ liệu.`)=>n.length?`<div class="table-wrap"><table class="cds--data-table cds--data-table--md">
  <thead><tr>${e.map(e=>`<th${e.num?` class="num"`:``}><div class="cds--table-header-label">${t(e.label||e)}</div></th>`).join(``)}</tr></thead>
  <tbody>${n.join(``)}</tbody></table></div>`:`<div class="empty">${t(r)}</div>`,O={"chung-tu":[[`#/hoa-don`,`Hóa đơn GTGT`],[`#/ngan-hang`,`Sao kê ngân hàng`],[`#/du-lieu`,`Bảng kê cổng thuế`]],"bao-cao":[[`#/so-lieu`,`Số liệu thuế GTGT`],[`#/giai-trinh`,`Hồ sơ giải trình`],[`#/lich`,`Lịch thuế`]],"tu-van":[[`#/hoi`,`Hỏi đáp thuế & dữ liệu`],[`#/luat`,`Kho văn bản luật`]]};function k(e,n){let r=O[e];if(!r)return``;let i=(n||location.hash.split(`?`)[0]||`#/`).replace(`#/tin-luat`,`#/luat`);return`<nav class="a3-subnav" aria-label="Điều hướng nhóm trang">
    ${r.map(([e,n])=>`<a href="${e}" class="a3-subnav-link ${i===e?`active`:``}" ${i===e?`aria-current="page"`:``}>${t(n)}</a>`).join(``)}
  </nav>`}var A={"Tổng quan":`Tổng hợp rủi ro khấu trừ, đối chiếu số liệu tờ khai và tiến độ xử lý thuế GTGT trong kỳ.`,"Việc cần xử lý":`Rà soát từng cảnh báo hóa đơn, đối chiếu chứng từ thanh toán và ghi nhận quyết định phê duyệt.`,"Hóa đơn":`Tra cứu, kiểm tra tính toàn vẹn chữ ký số XML và trạng thái ghép sao kê của từng hóa đơn.`,"Ngân hàng":`Đối chiếu các khoản thu chi ngân hàng và xác nhận ghép ủy nhiệm chi với hóa đơn mua vào.`,"Bảng kê":`Quản lý và chọn bản bảng kê hóa đơn điện tử từ cổng thuế để đối chiếu chéo với tệp XML.`,"Số liệu thuế GTGT":`Tổng hợp thuế GTGT đầu ra, đầu vào theo kịch bản rà soát và đối chiếu số liệu tờ khai đã nộp.`,"Giải trình":`Tập hợp chứng từ, trích dẫn căn cứ pháp lý và soạn thảo công văn giải trình cơ quan thuế.`,"Lịch thuế":`Theo dõi thời hạn nộp hồ sơ khai thuế và quy tắc dời hạn khi trùng ngày nghỉ lễ, cuối tuần.`,"Hỏi đáp":`Hỏi đáp trực tiếp trên số liệu hóa đơn kỳ này hoặc tra cứu điều khoản luật thuế GTGT.`,"Kho luật":`Tra cứu văn bản quy phạm pháp luật thuế còn hiệu lực từ Cơ sở dữ liệu quốc gia.`,"Nạp dữ liệu":`Tải lên hóa đơn điện tử XML, sao kê ngân hàng và bảng kê cổng thuế để chạy phân tích.`,"Mẫu sao kê":`Chỉnh sửa ánh xạ cột ngày, số tiền và nội dung chuyển khoản cho từng định dạng sao kê ngân hàng.`,"Quản trị hệ thống":`Khu vực bảo vệ dùng để thiết lập cấu hình doanh nghiệp, danh mục dùng chung và kho văn bản luật.`,"Tổng quan quản trị":`Quản lý danh mục dùng chung toàn hệ thống, phiên bản quy tắc và cấu hình riêng của từng doanh nghiệp.`,"Cấu hình doanh nghiệp":`Thiết lập các tham số, quy định chi tiêu, ngưỡng kiểm soát và danh mục đặc thù khớp với doanh nghiệp.`,"Thiết lập nghiệp vụ":`Trình hướng dẫn tuần tự 5 bước giúp cá nhân hóa quy chế kiểm tra thuế cho doanh nghiệp.`,"Danh mục dùng chung":`Chỉnh sửa danh mục hệ thống áp dụng chung cho mọi doanh nghiệp với nhật ký phiên bản đầy đủ.`,"Lịch sử thay đổi":`Theo dõi toàn bộ nhật ký cập nhật danh mục hệ thống và cấu hình nghiệp vụ của doanh nghiệp.`};function j(e){return String(e||``).replace(/^["'“”‘’\s]+|["'“”‘’\s]+$/g,``).trim()}function M(e,n,r=`KHÔNG GIAN DOANH NGHIỆP`,i=``,o=``){let s=N.workspaces.find(e=>e.id===N.ws),c=j(s?.name||N.platform?.profile?.legal_name||``),l=N.platform?.profile?.tax_code||s?.tax_code||``,u=(e=>String(e||``).replace(/<[^>]*>/g,``).trim())(i)||A[e]||``,d=[];l&&d.push(`MST ${l}`),N.report?.meta?.as_of&&d.push(`Kỳ phân tích: ${a(N.report.meta.as_of)}`);let f=`<span class="a3-h1-main">${t(n)}</span>`;return`
    <div class="page-heading a3-compact-header son-illustrated">
      <div class="a3-header-main">
        <div class="eyebrow"><span class="a3-eyebrow-pill">${t(r)}</span><span class="a3-eyebrow-dot">·</span><span id="breadcrumb">${t(e)}</span></div>
        <h1 class="page">${f}</h1>${c?`<p class="a3-company-line">${t(c)}</p>`:``}
        ${u||d.length?`<p class="a3-header-sub">${u?`<span class="a3-sub-desc">${t(u)}</span>`:``}${d.length?`<span class="a3-sub-meta">${u?` · `:``}${t(d.join(` · `))}</span>`:``}</p>`:``}
      </div>
    </div>
    ${o?k(o):``}
  `}function ee(e){if(!e)return null;let t=e.totals||{},n=e.invoices||[],r=e.items||[],i=e.matches||[],a=new Set(e.decisions?.not_claimed_keys||[]),o=new Map(i.flatMap(e=>(e.invoice_keys||[]).map(t=>[t,e]))),s=new Map;r.forEach(e=>{(e.invoice_keys||[]).forEach(t=>{s.has(t)||s.set(t,[]),s.get(t).push(e)})});let c=e=>{if(!e||e.duplicate_of)return`DUPLICATE`;if(e.role===`PURCHASE`&&a.has(e.key))return`NOT_CLAIMED`;let t=(s.get(e.key)||[]).filter(e=>e.status!==`INFO`);return t.some(e=>e.status===`AT_RISK`)?`AT_RISK`:t.some(e=>e.status===`REVIEW`)?`REVIEW`:t.length?`OTHER`:`OK`},l=n.filter(e=>e.role===`PURCHASE`&&!e.duplicate_of),u=n.filter(e=>e.role===`SALE`&&!e.duplicate_of),d=n.filter(e=>!!e.duplicate_of),f=l.reduce((e,t)=>e+Number(t.gross||0),0),p=l.reduce((e,t)=>e+Number(t.vat||0),0),m=u.reduce((e,t)=>e+Number(t.gross||0),0),h=u.reduce((e,t)=>e+Number(t.vat||0),0),g=l.filter(e=>c(e)===`AT_RISK`),_=l.filter(e=>c(e)===`REVIEW`),v=l.filter(e=>c(e)===`NOT_CLAIMED`),y=l.filter(e=>c(e)===`OK`),b=t.at_risk_vat===void 0?String(g.reduce((e,t)=>e+Number(t.vat||0),0)):t.at_risk_vat,x=t.review_vat===void 0?String(_.reduce((e,t)=>e+Number(t.vat||0),0)):t.review_vat,S=t.opportunity_vat===void 0?String(r.filter(e=>e.status===`OPPORTUNITY`).reduce((e,t)=>e+Number(t.amount||0),0)):t.opportunity_vat,C=t.penalty_estimate===void 0?`0`:t.penalty_estimate,w=v.reduce((e,t)=>e+Number(t.vat||0),0),T=y.reduce((e,t)=>e+Number(t.vat||0),0),E=h-T,D=h-T-Number(x||0),O=l.filter(e=>{let t=o.get(e.key);return!t||t.status!==`MATCHED`}),k=r.filter(e=>e.status===`AT_RISK`).length,A=r.filter(e=>e.status===`REVIEW`).length,j=r.filter(e=>e.status===`OPPORTUNITY`).length,M=t.at_risk_invoices??g.length,ee=t.review_invoices??_.length;return{matchedMap:o,riskByInvoice:s,invoiceBucket:c,purchaseInvs:l,saleInvs:u,duplicateInvs:d,purchaseGross:f,purchaseVat:p,saleGross:m,saleVat:h,noAlertVat:T,notClaimedVat:w,atRiskVat:b,reviewVat:x,opportunityVat:S,penaltyEstimate:C,scenarioWithoutReview:E,scenarioWithReview:D,unpaidInvs:O,unpaidCount:O.length,atRiskItems:k,reviewItems:A,opportunityItems:j,atRiskInvoices:M,reviewInvoices:ee}}var N={platform:null,ws:null,workspaces:[],report:null,schema:null},P=()=>e(`#app`),F=()=>new URLSearchParams(location.hash.split(`?`)[1]||``);async function I(){N.platform=await p(`/api/platform/context`),N.ws=N.platform.state===`ready`?N.platform.workspace_id:null,N.workspaces=N.ws?await p(`/api/workspaces`):[];let t=e(`#active-company`);t&&(t.textContent=N.platform.profile?`${N.platform.profile.legal_name} · MST ${N.platform.profile.tax_code}`:`Chưa kết nối doanh nghiệp`,t.title=t.textContent);let n=e(`#company-profile-link`);n&&(n.innerHTML=L(`config`,`Hồ sơ chung`))}function L(e=`config`,n=`Mở hồ sơ chung tại portal`){try{let r=new URL(N.platform?.portal_url);if(r.protocol===`http:`&&[`127.0.0.1`,`localhost`,`[::1]`].includes(r.hostname)&&!r.username&&!r.password)return`<a class="cds--btn cds--btn--tertiary" href="${t(r.origin)}/#${t(e)}" target="_top">${t(n)}</a>`}catch{}return`<p class="muted">Khởi động Agent 3 từ portal để kết nối hồ sơ doanh nghiệp chung.</p>`}async function R(){if(!N.ws)return N.report=null,null;try{N.report=await p(`/api/workspaces/${N.ws}/report`)}catch(e){if(e.status!==404)throw e;N.report=null}return N.report}var z=e=>N.report?.invoices.find(t=>t.key===e)||null,B=e=>e?`${e.template||``}${e.symbol||``}/${e.number||``}`:``;function V(){if(N.ws)return!1;let e={sync_required:`Hồ sơ đang chờ đồng bộ. Lưu lại hồ sơ tại portal hoặc khởi động lại Agent 3 từ portal.`,conflict:`Có nhiều dữ liệu trùng MST hoặc trùng dữ liệu mô phỏng. Cần kiểm tra trước khi liên kết.`,invalid_profile:`Hồ sơ chung chưa hợp lệ. Kiểm tra lại thông tin tại portal.`,missing_profile:`Chưa có hồ sơ doanh nghiệp chung. Hoàn tất hồ sơ tại portal.`};return P().innerHTML=`<h1 class="page">Kết nối hồ sơ doanh nghiệp</h1><p class="lead">${t(e[N.platform?.state]||`Agent 3 sử dụng doanh nghiệp do portal quản lý.`)}</p>${L()}`,!0}function H(){try{let e=N.platform?.portal_url,t=new URL(e);if(t.protocol===`http:`&&[`127.0.0.1`,`localhost`].includes(t.hostname)&&!t.username&&!t.password&&t.origin!==location.origin)return t.origin}catch{}return null}function U(e){e.querySelectorAll(`a[href^="/api/workspaces/"]`).forEach(e=>{let t=new URL(e.href);t.searchParams.set(`profile_revision`,N.platform?.profile_revision||``),e.href!==t.href&&(e.href=t.href)});let t=H();t&&e.querySelectorAll(`a[href^="#/nap"], [data-go^="#/nap"]`).forEach(e=>{if((e.getAttribute(`href`)||e.dataset.go).includes(`b=chay`)){e.setAttribute(`href`,`#/`),e.dataset.go=`#/`,e.textContent=`Chạy phân tích ở Tổng quan`;return}let n=document.createElement(`a`);n.className=e.className,n.href=t+`/#data`,n.target=`_top`,e.closest(`#nav`)?n.innerHTML=`<span class="cds--side-nav__link-text">Nạp dữ liệu</span>`:n.textContent=`Nạp dữ liệu chung`,e.replaceWith(n)})}function W(){e(`#modal-root`).replaceChildren()}function te(){let t=e(`.drawer`);if(!t)return;let n=document.activeElement;t.setAttribute(`aria-modal`,`true`),t.tabIndex=-1;let r=document.createElement(`div`);r.className=`drawer-backdrop`,t.before(r);let i=[e(`#app`),e(`.side`),e(`header`)].filter(Boolean);i.forEach(e=>{e.inert=!0});let a=new AbortController,o=new MutationObserver(()=>{t.isConnected||s()}),s=()=>{o.disconnect(),a.abort(),r.remove(),i.forEach(e=>{e.inert=!1}),n?.isConnected&&n.focus({preventScroll:!0})};o.observe(e(`#modal-root`),{childList:!0});let c=()=>W();e(`#close`,t)?.addEventListener(`click`,c,{signal:a.signal}),r.addEventListener(`click`,c,{signal:a.signal}),document.addEventListener(`keydown`,e=>{if(e.key===`Escape`&&(e.preventDefault(),c()),e.key!==`Tab`)return;let n=[...t.querySelectorAll(`a[href],button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),[tabindex="0"]`)].filter(e=>e.getClientRects().length);n.length?e.shiftKey&&(document.activeElement===n[0]||document.activeElement===t)?(e.preventDefault(),n.at(-1).focus()):e.shiftKey||document.activeElement!==n.at(-1)&&document.activeElement!==t||(e.preventDefault(),n[0].focus()):(e.preventDefault(),t.focus())},{signal:a.signal}),t.focus({preventScroll:!0}),u(()=>{c(),s()})}function ne(e){U(e),e.querySelectorAll(`.table-wrap`).forEach(e=>{e.tabIndex=0,e.setAttribute(`role`,`region`),e.setAttribute(`aria-label`,`Bảng dữ liệu, cuộn ngang để xem thêm cột`)}),e.querySelectorAll(`[data-go]`).forEach(e=>{e.tagName===`TR`&&(e.tabIndex=0,e.onkeydown=t=>{t.target===e&&[`Enter`,` `].includes(t.key)&&(t.preventDefault(),e.click())})}),e.querySelectorAll(`.bar:has(.filter-input)`).forEach(e=>{e.dataset.decorated||(e.dataset.decorated=`1`,e.classList.add(`toolbar`),e.querySelectorAll(`input[aria-label],select[aria-label]`).forEach(e=>{if(e.closest(`label`))return;let t=document.createElement(`label`);t.className=`filter-field`;let n=document.createElement(`span`);n.textContent=e.getAttribute(`aria-label`),e.before(t),t.append(n,e)}))})}function re(){document.addEventListener(`invalid`,e=>{e.preventDefault();let n=e.target.form;n&&queueMicrotask(()=>{let e=[...n.elements].filter(e=>e.validity&&!e.validity.valid);if(n.querySelectorAll(`.form-error,.error-summary`).forEach(e=>e.remove()),e.forEach((e,t)=>{e.id||=`invalid-`+t,e.setAttribute(`aria-invalid`,`true`);let n=document.createElement(`div`);n.className=`form-error`,n.id=e.id+`-error`,n.textContent=e.validationMessage,e.setAttribute(`aria-errormessage`,n.id),e.after(n)}),!e.length)return;let r=document.createElement(`div`);r.className=`error-summary`,r.tabIndex=-1,r.setAttribute(`role`,`alert`),r.innerHTML=`<strong>Kiểm tra lại thông tin</strong>`+e.map(e=>`<a href="#${t(e.id)}" data-error-field="${t(e.id)}">${t(e.labels?.[0]?.textContent||e.name||`Trường bắt buộc`)}: ${t(e.validationMessage)}</a>`).join(``),r.onclick=e=>{let t=e.target.closest(`[data-error-field]`);t&&(e.preventDefault(),document.getElementById(t.dataset.errorField)?.focus())},n.prepend(r),r.focus()})},!0),document.addEventListener(`input`,e=>{e.target.validity?.valid&&(e.target.removeAttribute(`aria-invalid`),document.getElementById(e.target.id+`-error`)?.remove(),e.target.removeAttribute(`aria-errormessage`))})}function G(n,r=``,i=`success`){let a=e(`#toasts`);a||(a=document.createElement(`div`),a.id=`toasts`,document.body.appendChild(a));let o=document.createElement(`div`);o.className=`toast toast-${i}`,o.setAttribute(`role`,`status`),o.innerHTML=`<strong>${t(n)}</strong>${r?`<div>${t(r)}</div>`:``}`,a.appendChild(o),setTimeout(()=>{o.classList.add(`out`),setTimeout(()=>o.remove(),300)},4200)}function ie(){let e=document.querySelector(`.kt-top-progress`);return e||(e=document.createElement(`div`),e.className=`kt-top-progress`,e.setAttribute(`aria-hidden`,`true`),document.body.appendChild(e)),e}function ae(e=`Đang phân tích dữ liệu hóa đơn và sao kê kỳ thuế`){return`<div class="a3-analysis-progress-card" role="status" aria-live="polite">
    <div class="a3-analysis-head">
      <div class="a3-analysis-title-wrap">
        <span class="kt-spinner" aria-hidden="true"></span>
        <div>
          <strong class="a3-analysis-title">${t(e)}</strong>
          <div class="a3-analysis-sub">Hệ thống đang đối chiếu chứng từ gốc XML, bảng kê cổng thuế và sao kê ngân hàng</div>
        </div>
      </div>
      <span class="a3-analysis-timer" data-analysis-timer>0.0s</span>
    </div>
    <div class="a3-analysis-bar-track" aria-hidden="true">
      <div class="a3-analysis-bar-fill"></div>
    </div>
    <ol class="a3-analysis-steps">
      <li class="a3-step is-active" data-step-idx="0">
        <span class="a3-step-num">01</span>
        <span class="a3-step-text">Kiểm tra cấu trúc XML, chữ ký số và hóa đơn trùng lặp</span>
      </li>
      <li class="a3-step" data-step-idx="1">
        <span class="a3-step-num">02</span>
        <span class="a3-step-text">Đối chiếu bảng kê cổng thuế và danh sách mã số thuế rủi ro</span>
      </li>
      <li class="a3-step" data-step-idx="2">
        <span class="a3-step-num">03</span>
        <span class="a3-step-text">Khớp nối giao dịch sao kê ngân hàng và tổng hợp bảng tính thuế GTGT</span>
      </li>
    </ol>
  </div>`}async function K({triggerBtn:t,stageEl:n,title:r,onSuccess:i,onError:a}={}){let o=ie();o.classList.add(`active`);let s=t?t.innerHTML:``;t&&(t.disabled=!0,t.setAttribute(`aria-busy`,`true`),t.classList.add(`is-analyzing`),t.innerHTML=`<span class="kt-spinner" aria-hidden="true" style="width:14px;height:14px;border-width:2px;margin-right:8px"></span><span>Đang phân tích...</span>`);let c=n;c||=e(`#analysis-stage`)||e(`#run-msg`)||e(`#r2`)||e(`#autorun`),c&&(c.innerHTML=ae(r));let l=P();l&&l.classList.add(`a3-is-analyzing`);let u=performance.now(),d=setInterval(()=>{if(!c||!c.isConnected)return;let e=(performance.now()-u)/1e3,t=c.querySelector(`[data-analysis-timer]`);t&&(t.textContent=`${e.toFixed(1)}s`);let n=c.querySelectorAll(`.a3-step`);n.length===3&&(e>=.35&&(n[0].classList.remove(`is-active`),n[0].classList.add(`is-done`),n[1].classList.add(`is-active`)),e>=.75&&(n[1].classList.remove(`is-active`),n[1].classList.add(`is-done`),n[2].classList.add(`is-active`)))},100);try{let e=await m(`/api/workspaces/${N.ws}/run`);return await I(),c&&c.isConnected&&c.querySelectorAll(`.a3-step`).forEach(e=>{e.classList.remove(`is-active`),e.classList.add(`is-done`)}),i?await i(e):(G(`Đã phân tích xong`,`${e.items.length} việc, thuế có nguy cơ ${Number(e.totals.at_risk_vat).toLocaleString(`vi-VN`)} đ`),window.dispatchEvent(new Event(`hashchange`))),e}catch(e){return e.name!==`AbortError`&&(a?a(e,c):c&&c.isConnected?c.innerHTML=C(`error`,`Phân tích không chạy được`,e.message):G(`Không chạy được phân tích`,e.message,`error`)),null}finally{clearInterval(d),o.classList.remove(`active`),l&&l.classList.remove(`a3-is-analyzing`),t&&t.isConnected&&(t.disabled=!1,t.removeAttribute(`aria-busy`),t.classList.remove(`is-analyzing`),t.innerHTML=s)}}async function oe(t){let n=t?.querySelector(`#fresh-run`)||t?.querySelector(`button`)||null,r=e(`#analysis-stage`);return!r&&t&&(r=document.createElement(`div`),r.style.marginTop=`10px`,t.after(r)),K({triggerBtn:n,stageEl:r})}async function se(n){if(n&&N.ws)try{let r=await p(`/api/workspaces/${N.ws}/freshness`);if(!r.stale){n.innerHTML=``;return}n.innerHTML=`<div class="banner banner-warn"><div><strong>${r.analysed?`Dữ liệu đã thay đổi sau lần phân tích gần nhất`:`Chưa có kết quả phân tích`}</strong>
      <div class="small">${r.analysed?`Số liệu đang hiển thị có thể đã cũ.`:`Nạp dữ liệu rồi chạy phân tích để xem kết quả.`}${r.reason?` `+t(r.reason):``}</div></div>
      <button type="button" class="cds--btn cds--btn--primary cds--btn--sm" id="fresh-run">Chạy phân tích ngay</button></div>`,e(`#fresh-run`).onclick=()=>oe(e(`#fresh-run`).parentElement)}catch{n.innerHTML=``}}function ce(e,n=new Date){let r=(e?.calendar||[]).filter(e=>{let t=(new Date(e.due)-n)/864e5;return t>=-3&&t<=7});return r.length?`<div class="banner banner-danger"><div><strong>Hạn sắp tới</strong><div class="small">${r.map(e=>`${t(e.period)}: ${a(e.due)} (${t(e.status)})`).join(`; `)}</div></div>
    <a class="cds--btn cds--btn--ghost cds--btn--sm" href="#/lich">Xem lịch thuế</a></div>`:``}function le(n,r){if(!n||!r)return;let i=`agent3.seenRisky.${N.ws}`,a=[...new Set(r.items.filter(e=>e.code===`R08_RISKY_SELLER`).map(e=>e.invoice_keys[0].split(`|`)[0]))],o=null;try{o=JSON.parse(localStorage.getItem(i)||`null`)}catch{o=null}let s=o?a.filter(e=>!o.includes(e)):a;if(s.length){let c=s.map(e=>r.invoices.find(t=>t.seller_tax_id===e)?.seller_name||e),l=r.items.filter(e=>e.code===`R08_RISKY_SELLER`&&s.includes(e.invoice_keys[0].split(`|`)[0])).length;n.innerHTML=`<div class="banner banner-danger"><div><strong>${o?`Người bán mới xuất hiện trong danh sách rủi ro`:`Người bán đang nằm trong danh sách rủi ro`}</strong>
      <div class="small">${c.map(t).join(`, `)}: ${l} hóa đơn cần kiểm tra hợp đồng, giao nhận và thanh toán trước khi kê khai.</div></div>
      <div class="chips"><a class="cds--btn cds--btn--primary cds--btn--sm" href="#/viec?loc=REVIEW">Xem các hóa đơn</a><button type="button" class="cds--btn cds--btn--ghost cds--btn--sm" id="seen-ok">Đã biết</button></div></div>`,e(`#seen-ok`).onclick=()=>{try{localStorage.setItem(i,JSON.stringify(a))}catch{}n.innerHTML=``}}else n.innerHTML=``}var ue={date:`Ngày giao dịch`,debit:`Ghi nợ (tiền ra)`,credit:`Ghi có (tiền vào)`,description:`Nội dung`,counterparty_account:`Tài khoản đối ứng`,counterparty_name:`Tên đối ứng`};function de(e,n){return`<div class="drop" id="drop"><input type="file" id="file" multiple ${e?`accept="${t(e)}"`:``} class="cds--visually-hidden">
    ${T(`Chọn tệp`,`primary`,`id="pick"`)}<span class="muted">${t(n)}</span></div><div id="up"></div>`}function fe(t){let n=e(`#file`);e(`#pick`).onclick=()=>n.click(),n.onchange=()=>t([...n.files]);let r=e(`#drop`);r.ondragover=e=>{e.preventDefault(),r.classList.add(`over`)},r.ondragleave=()=>r.classList.remove(`over`),r.ondrop=e=>{e.preventDefault(),r.classList.remove(`over`),t([...e.dataTransfer.files])}}function pe(e){let n=e.filter(e=>e.kind),r=Object.entries(n.reduce((e,t)=>({...e,[t.label]:(e[t.label]||0)+1}),{})).map(([e,t])=>`${t} ${e.toLowerCase()}`).join(`, `),i=e.filter(e=>!e.kind),a=n.filter(e=>/vẫn nạp để kiểm tra/.test(e.reason)),o=n.filter(e=>e.auto_format);return`${n.length?C(`success`,`Đã nhận ${n.length} tệp`,r):``}
    ${o.map(e=>C(`info`,`Sao kê ${e.file}: đã tự nhận dạng cột`,`Ngày: ${e.auto_format.columns.date}; ghi nợ: ${e.auto_format.columns.debit}; ghi có: ${e.auto_format.columns.credit}; nội dung: ${e.auto_format.columns.description}`)).join(``)}
    ${a.length?C(`warning`,`${a.length} hóa đơn ghi sai mã số thuế doanh nghiệp`,a.map(e=>`${e.file}: ${e.reason}`).join(`; `)):``}
    ${i.length?`<div class="panel"><h3>${i.length} tệp không dùng</h3>${D([`Tệp`,`Lý do`],i.map(e=>`<tr><td class="mono">${t(e.file)}</td><td>${t(e.reason)}</td></tr>`))}</div>`:``}`}async function me(t,n){let r=[];for(let[i,a]of t.entries()){e(`#up`).innerHTML=w(`Đang nạp ${i+1}/${t.length}: ${a.name}`);try{let e=await p(`${n}?name=${encodeURIComponent(a.name)}`,{method:`PUT`,body:a});r.push(...e.files||e.saved.map(e=>({file:e,kind:`ok`,label:`Tệp`,reason:``})))}catch(e){r.push({file:a.name,kind:null,label:`Không dùng`,reason:e.message})}}return await I(),r}function he(e,r){if(!r.length)return`<div class="empty">Chưa có tệp.</div>`;let i=r.filter(e=>!e.ok).length,o=i?C(`warning`,`${i} trên ${r.length} tệp có lỗi`,`Xem cột Tình trạng; tệp lỗi vẫn được giữ, hệ thống báo trong Việc cần xử lý.`):C(`success`,`${r.length} tệp đọc tốt`);return e===`purchase_xml`||e===`sales_xml`?o+D([`Tệp`,`Hóa đơn`,`Ngày`,e===`purchase_xml`?`Người bán`:`Người mua`,{label:`Tổng thanh toán`,num:!0},`Tình trạng`],r.map(e=>`<tr><td class="mono small">${t(e.file)}</td><td>${t(e.number||``)}</td><td>${a(e.date)}</td><td>${t(e.party||``)}</td>
        <td class="num">${n(e.gross)}</td><td>${e.ok?S(`LLM_VERIFIED`,`Đọc tốt`):S(`AT_RISK`,`Có lỗi`)}<div class="muted small">${t((e.errors||[]).join(`, `))}</div></td></tr>`)):e===`bank`?o+D([`Tệp`,{label:`Giao dịch`,num:!0},`Từ ngày`,`Đến ngày`,`Tình trạng`,``],r.map(e=>`<tr><td class="mono small">${t(e.file)}</td>
      <td class="num">${e.rows??``}</td><td>${a(e.first)}</td><td>${a(e.last)}</td><td>${e.ok?S(`LLM_VERIFIED`,`Đọc tốt`):S(`AT_RISK`,`Chưa đọc được`)}<div class="muted small">${t((e.errors||[]).join(`, `))}</div></td>
      <td>${/\.(csv|xlsx)$/i.test(e.file)?T(e.ok?`Xem cột`:`Nhận dạng cột`,e.ok?`ghost`:`primary`,`data-suggest="${t(e.file)}"`):``}</td></tr>`)):o+D([`Tệp`,{label:`Số dòng`,num:!0},`Tình trạng`],r.map(e=>`<tr><td class="mono small">${t(e.file)}</td><td class="num">${e.rows??``}</td>
    <td>${e.ok?S(`LLM_VERIFIED`,`Đọc tốt`):S(`AT_RISK`,`Chưa đọc được`)}<div class="muted small">${t((e.errors||[]).join(`, `))}</div></td></tr>`))}async function ge(r){let i=e(`#suggest`);i.innerHTML=w(`Đang nhận dạng cột`);let o;try{o=await m(`/api/workspaces/${N.ws}/bank/suggest?name=${encodeURIComponent(r)}`)}catch(e){i.innerHTML=C(`error`,`Không nhận dạng được`,e.message);return}let s=structuredClone(o.format),c=e=>`<option value="">(không có)</option>${o.headers.map(n=>`<option ${n===e?`selected`:``}>${t(n)}</option>`).join(``)}`;i.innerHTML=`<div class="panel"><h3>Cột của ${t(r)}</h3><p class="muted">Dòng tiêu đề số ${o.header_row}. Chọn lại nếu cần; bản xem trước cập nhật ngay.</p>
    <div class="form-grid">${Object.keys(ue).map(e=>`<div class="cds--form-item"><div class="cds--select"><label class="cds--label" for="m-${e}">${ue[e]}${e===`date`||e===`debit`?``:` (không bắt buộc)`}</label>
      <div class="cds--select-input__wrapper"><select class="cds--select-input" id="m-${e}" data-col="${e}">${c(s.columns[e])}</select></div></div></div>`).join(``)}
      <div class="cds--form-item"><div class="cds--select"><label class="cds--label" for="m-num">Cách viết số tiền</label><div class="cds--select-input__wrapper"><select class="cds--select-input" id="m-num">
        <option value=".," ${s.thousands===`.`?`selected`:``}>1.234.567,00 (dấu chấm ngăn nghìn)</option><option value=",." ${s.thousands===`,`?`selected`:``}>1,234,567.00 (dấu phẩy ngăn nghìn)</option></select></div></div></div>
      <div class="cds--form-item"><div class="cds--select"><label class="cds--label" for="m-date">Cách viết ngày</label><div class="cds--select-input__wrapper"><select class="cds--select-input" id="m-date">
        ${[[`%d/%m/%Y`,`31/12/2026`],[`%Y-%m-%d`,`2026-12-31`],[`%d-%m-%Y`,`31-12-2026`],[`%d.%m.%Y`,`31.12.2026`]].map(([e,t])=>`<option value="${e}" ${s.date_format===e?`selected`:``}>${t}</option>`).join(``)}</select></div></div></div></div>
    <div id="pv"></div>
    <div class="bar" style="align-items:flex-end"><div class="cds--form-item cds--text-input-wrapper"><label class="cds--label" for="fmt-name">Tên mẫu</label><input class="cds--text-input" id="fmt-name" value="${t(s.name)}"></div>
      ${T(`Lưu mẫu sao kê`,`primary`,`id="save-fmt"`)}<span id="fmt-msg"></span></div></div>`;let l=()=>(i.querySelectorAll(`[data-col]`).forEach(e=>{e.value?s.columns[e.dataset.col]=e.value:delete s.columns[e.dataset.col]}),[s.thousands,s.decimal]=e(`#m-num`).value.split(``),s.date_format=e(`#m-date`).value,s.name=e(`#fmt-name`).value||s.name,s),u=async()=>{e(`#pv`).innerHTML=w(`Đang đọc thử`);try{let i=await m(`/api/workspaces/${N.ws}/bank/preview?name=${encodeURIComponent(r)}`,l());e(`#pv`).innerHTML=`<h3 style="margin-top:1rem">Đọc thử ${i.preview.length} dòng đầu</h3>${i.errors?C(`warning`,`${i.errors} dòng không đọc được`,`Kiểm tra cách viết ngày và số tiền.`):``}
        ${D([`Ngày`,{label:`Tiền ra`,num:!0},{label:`Tiền vào`,num:!0},`Đối ứng`,`Nội dung`],i.preview.map(e=>e.error?`<tr><td colspan="5">${t(e.error)}</td></tr>`:`<tr><td>${a(e.date)}</td><td class="num">${n(e.debit)}</td><td class="num">${n(e.credit)}</td><td>${t(e.counterparty)}</td><td>${t(e.description)}</td></tr>`))}`}catch(t){e(`#pv`).innerHTML=C(`error`,`Chưa đọc được với cách chọn này`,t.message)}};i.querySelectorAll(`select`).forEach(e=>{e.onchange=u}),u(),e(`#save-fmt`).onclick=async()=>{let t=e(`#save-fmt`);t.disabled=!0;try{await v(l()),e(`#fmt-msg`).innerHTML=C(`success`,`Đã lưu mẫu; chạy lại phân tích để kiểm tra toàn bộ tệp`)}catch(t){e(`#fmt-msg`).innerHTML=C(`error`,`Không lưu được`,t.message)}finally{t.isConnected&&(t.disabled=!1)}},i.scrollIntoView({behavior:`smooth`,block:`start`})}async function _e(){await p(`/api/workspaces/${N.ws}/pack`);let e=await p(`/api/workspaces/${N.ws}/details/bank`);P().innerHTML=`${M(`Mẫu sao kê`,`Nhận dạng cột sao kê`,`QUẢN TRỊ CHỨNG TỪ`)}${he(`bank`,e)}<div id="suggest"></div>`,P().querySelectorAll(`[data-suggest]`).forEach(e=>{e.onclick=()=>ge(e.dataset.suggest)})}async function ve(){let n=await p(`/api/workspaces/${N.ws}/portal/lists`);P().innerHTML=`
    ${M(`Bảng kê`,`Bảng kê cổng thuế đang sử dụng`,`QUẢN LÝ CHỨNG TỪ`,`<span class="ctx-chip chip-count">${n.files.length} bản lưu</span>`,`chung-tu`)}
    ${n.error?C(`warning`,`Cần chọn bản bảng kê`,n.error):``}
    <form id="active-list" style="margin-top:14px"><label for="list-version" class="cds--label">Chọn bản bảng kê cổng thuế để đối chiếu</label><select id="list-version" class="cds--select-input" required><option value="">Chọn bảng kê</option>${n.files.map(e=>`<option value="${t(e)}" ${e===n.active?`selected`:``}>${t(e)}</option>`).join(``)}</select>
    <div class="bar">${T(`Sử dụng bản này`,`primary`,`type="submit"`)}<span id="list-result"></span></div></form>
    <a class="cds--btn cds--btn--ghost cds--btn--sm" href="#/quan-tri/mau-sao-ke">Nhận dạng cột sao kê (quản trị)</a>`,e(`#active-list`).onsubmit=async t=>{t.preventDefault();let n=t.target.querySelector(`button`);n.disabled=!0;try{await h(`/api/workspaces/${N.ws}/portal/active-list`,{name:e(`#list-version`).value}),e(`#list-result`).innerHTML=C(`success`,`Đã chọn bảng kê; chạy lại phân tích để áp dụng.`)}catch(t){e(`#list-result`).innerHTML=C(`error`,`Không đổi được bảng kê`,t.message)}finally{n.isConnected&&(n.disabled=!1)}}}async function ye(){if(V())return;N.schema||=await p(`/api/schema`);let r=N.workspaces.find(e=>e.id===N.ws),i=N.schema.files.filter(e=>e.folder),a=Object.values(r?.files||{}).reduce((e,t)=>e+(Number(t)||0),0),o=F().get(`b`),s=o===`chay`?`chay`:o===`nhanh`?`nhanh`:o?`da-nap`:a?`chay`:`nhanh`,c=[[`nhanh`,`Nạp tệp`],[`da-nap`,`Tệp đã nạp (${a})`],[`chay`,`Kiểm tra và chạy`]],l=`${M(`Nạp dữ liệu`,`Nạp dữ liệu`,`NGUỒN CHỨNG TỪ`,`<span class="ctx-chip chip-count">${a} tệp đã nạp</span>`)}
    <nav class="steps" style="margin-top:14px">${c.map(([e,n],r)=>`<a href="#/nap?b=${e}" class="${e===s?`on`:``}"><span class="n">${r+1}</span>${t(n)}</a>`).join(``)}</nav>`;if(s===`nhanh`)P().innerHTML=`${l}<p class="muted" style="margin:0 0 12px">Thả tệp XML hóa đơn (mua vào, bán ra), tệp nén .zip, sao kê ngân hàng (.xlsx, .csv, .mt940) và bảng kê cổng thuế vào ô dưới đây.</p>
      ${de(`.xml,.zip,.csv,.xlsx,.sta,.mt940,.txt`,`hoặc kéo thả tất cả vào đây`)}
      <details class="guide" style="margin-top:14px"><summary>Hướng dẫn xuất tệp từ cổng thuế và ngân hàng</summary><div class="guide-body">${i.map(e=>`<p class="cell-title">${t(e.label)}</p><ol>${e.how.map(e=>`<li>${t(e)}</li>`).join(``)}</ol>`).join(``)}</div></details>`,fe(async t=>{let r=await me(t,`/api/workspaces/${N.ws}/inbox`),i=Object.values(N.workspaces.find(e=>e.id===N.ws)?.files||{}).reduce((e,t)=>e+(Number(t)||0),0),a=P().querySelector(`.steps a[href="#/nap?b=da-nap"]`);a&&(a.lastChild.textContent=`Tệp đã nạp (${i})`),e(`#up`).innerHTML=`${pe(r)}<div id="autorun"></div>`,r.some(e=>e.kind)?await K({stageEl:e(`#autorun`),title:`Đang tự chạy phân tích với dữ liệu mới vừa nạp`,onSuccess:async t=>{let r=await p(`/api/workspaces/${N.ws}/coverage`);e(`#autorun`)?.isConnected&&(e(`#autorun`).innerHTML=C(`success`,`Đã phân tích xong`,`${t.items.length} việc; thuế có nguy cơ ${n(t.totals.at_risk_vat)}`)+r.filter(e=>e.level===`warning`).map(e=>C(`warning`,e.title,e.detail)).join(``)+`<div class="bar">${T(`Xem việc cần xử lý`,`primary`,`data-go="#/viec"`)}${T(`Về tổng quan`,`ghost`,`data-go="#/"`)}</div>`)},onError:(e,t)=>{t?.isConnected&&(t.innerHTML=C(`error`,`Phân tích chưa chạy được`,e.message))}}):e(`#autorun`).innerHTML=``});else if(s===`chay`){P().innerHTML=`${l}<h2 class="section" style="margin-top:0">Kiểm tra mức độ đầy đủ dữ liệu</h2><div id="cov">${w(`Đang kiểm tra dữ liệu đã nạp`)}</div>
      <div class="bar">${T(`Chạy phân tích`,`primary`,`id="run2"`)}</div><div id="r2"></div>`,e(`#run2`).onclick=async()=>{await K({triggerBtn:e(`#run2`),stageEl:e(`#r2`),title:`Đang phân tích dữ liệu hóa đơn và sao kê kỳ thuế`,onSuccess:async()=>{location.hash=`#/`}})};try{let t=await p(`/api/workspaces/${N.ws}/coverage`);e(`#cov`).innerHTML=t.length?t.map(e=>C(e.level===`warning`?`warning`:`info`,e.title,e.detail)).join(``):C(`success`,`Dữ liệu đủ để phân tích`,`Có hóa đơn, sao kê phủ các tháng có hóa đơn và bảng kê cổng thuế.`)}catch(t){e(`#cov`).innerHTML=C(`error`,`Không kiểm tra được`,t.message)}}else P().innerHTML=`${l}${i.map(e=>`<h2 class="section">${t(e.label)} (${r?.files?.[e.key]??0})</h2><div id="det-${e.key}">${w(`Đang đọc từng tệp`)}</div>`).join(``)}<div id="suggest"></div>`,await Promise.all(i.map(async t=>{try{let n=await p(`/api/workspaces/${N.ws}/details/${t.key}`);e(`#det-${t.key}`).innerHTML=he(t.key,n)}catch(n){e(`#det-${t.key}`).innerHTML=C(`error`,`Không đọc được danh sách tệp`,n.message)}})),P().querySelectorAll(`[data-suggest]`).forEach(e=>{e.onclick=()=>ge(e.dataset.suggest)})}var be=()=>window.dispatchEvent(new Event(`hashchange`)),xe=e=>e===`AI_VERIFIED`?S(`LLM_VERIFIED`,`AI, đã kiểm tra`):S(`INFO`,`Câu mẫu`);async function Se(e,n){e.innerHTML=`<div class="plain">${w(`Đang tóm tắt vấn đề`)}</div>`;try{let r=await m(`/api/workspaces/${N.ws}/ai/explain`,{index:n});e.innerHTML=`<div class="plain"><div class="bar" style="margin:0 0 .5rem">${xe(r.mode)}<span class="muted small">Tóm tắt nhanh${r.note?` (${t(r.note)})`:``}</span></div>${t(r.text)}</div>`}catch{e.innerHTML=``}}async function Ce(e){e.replaceChildren()}async function we(r){let i=await p(`/api/workspaces/${N.ws}/ai`);if(!i.proposals.length){r.innerHTML=``;return}let s=await g(),c=o.get(`agent3.reviewer`)||``;r.innerHTML=`<h2 class="section">Đề xuất ghép từ nội dung chuyển khoản (${i.proposals.length})</h2>
    <div class="bar" style="align-items:flex-end"><div class="cds--form-item cds--text-input-wrapper"><label class="cds--label" for="reviewer">Người duyệt</label><input class="cds--text-input" id="reviewer" value="${t(c)}" placeholder="Kế toán trưởng"></div></div>
    ${D([`Giao dịch`,{label:`Số tiền`,num:!0},`Nội dung chuyển khoản`,`Hóa đơn đề xuất`,`Căn cứ nhận diện`,``],i.proposals.map((e,r)=>`<tr>
      <td>${a(e.booked)}<div class="muted small">${t(e.source||``)}</div></td><td class="num">${n(e.amount)}</td><td>${t(e.description||``)}<div class="muted small">${t(e.counterparty_name||``)}</div></td>
      <td>${t(e.seller_name)}<div class="muted small">số ${t(e.invoice_number||``)}</div></td><td>cụm "<strong>${t(e.name_in_text)}</strong>", độ giống ${e.similarity}<div class="muted small">${t(e.reason)}</div></td>
      <td><div class="chips">${T(`Xác nhận`,`primary`,`data-acc="${r}"`)}${T(`Bác bỏ`,`ghost`,`data-rej="${r}"`)}</div></td></tr>`))}<div id="pmsg"></div>`;let l=async(t,n)=>{let a=e(`#reviewer`).value.trim();if(!a){e(`#pmsg`).innerHTML=C(`warning`,`Cần tên người duyệt`);return}o.set(`agent3.reviewer`,a);let c=[...r.querySelectorAll(`button`)];c.forEach(e=>{e.disabled=!0});try{let e=await _(`/api/workspaces/${N.ws}/ai/bank/decide`,{txn_id:i.proposals[t].txn_id,invoice_key:i.proposals[t].invoice_key,accept:n,by:a},s);e.report_pending&&G(`Quyết định đã lưu; cần chạy lại báo cáo`,e.message,`warning`),n&&window.sonStamp?.(a),be()}catch(t){e(`#pmsg`).innerHTML=C(`error`,`Không ghi được`,t.message)}finally{c.forEach(e=>{e.disabled=!1})}};r.querySelectorAll(`[data-acc]`).forEach(e=>{e.onclick=()=>l(Number(e.dataset.acc),!0)}),r.querySelectorAll(`[data-rej]`).forEach(e=>{e.onclick=()=>l(Number(e.dataset.rej),!1)})}async function Te(){if(V())return;let r=await R();if(!r){P().innerHTML=`<h1 class="page">Giải trình</h1>${C(`info`,`Chưa phân tích`)}`;return}let i=[...new Set(r.items.filter(e=>e.status!==`INFO`).flatMap(e=>e.invoice_keys))].filter(e=>z(e));P().innerHTML=`
    ${M(`Giải trình`,`Hồ sơ giải trình cơ quan thuế`,`TỔNG HỢP & HỒ SƠ THUẾ`,`<span class="ctx-chip chip-count">${i.length} hóa đơn có cảnh báo</span>`,`bao-cao`)}
    <div class="cds--form-item" style="margin-top:14px"><label class="cds--label" for="req">Nội dung công văn yêu cầu giải trình (không bắt buộc)</label>
    <textarea class="cds--text-area" id="req" rows="3" placeholder="Ví dụ: Đề nghị giải trình việc kê khai khấu trừ thuế GTGT đầu vào của các hóa đơn trong kỳ..."></textarea></div>
    <h2 class="section" style="margin-top:20px">Chọn hóa đơn đưa vào hồ sơ (.zip)</h2>
    <div class="bar"><input class="cds--text-input filter-input" id="dq" placeholder="Tìm số hóa đơn hoặc người bán" aria-label="Tìm hóa đơn"><span class="muted small" id="dcount"></span>
      ${T(`Chọn trang hiện tại`,`ghost`,`id="dpick"`)}${T(`Bỏ chọn tất cả`,`ghost`,`id="dnone"`)}</div>
    <div id="dlist"></div>
    <div class="bar">${T(`Soạn thư giải trình & đóng gói hồ sơ`,`primary`,`id="make"`)}<span id="mk"></span></div><div id="letter"></div>`;let o=50,s=new Set,c=i.map(e=>({k:e,i:z(e),its:r.items.filter(t=>t.invoice_keys.includes(e))})),l=()=>{let t=e(`#dq`).value.trim().toLowerCase();return t?c.filter(e=>`${B(e.i)} ${e.i.seller_name}`.toLowerCase().includes(t)):c},u=()=>{let r=l();e(`#dcount`).textContent=`${r.length} hóa đơn, đã chọn ${s.size}`,e(`#dlist`).innerHTML=D([``,`Hóa đơn`,`Người bán`,`Vấn đề`,{label:`Tổng thanh toán`,num:!0}],r.slice(0,o).map(({k:e,i:r,its:i})=>`<tr><td><input type="checkbox" class="pick" value="${t(e)}" ${s.has(e)?`checked`:``} aria-label="Chọn hóa đơn"></td>
      <td><strong>${t(B(r))}</strong><div class="muted small">${a(r.issue_date)}</div></td><td>${t(r.seller_name)}</td>
      <td><div class="chips" title="${t(i.map(e=>e.title).join(`; `))}">${i[0]?S(i[0].status,i[0].title):``}${i.length>1?`<span class="muted small">+${i.length-1} vấn đề</span>`:``}</div></td><td class="num">${n(r.gross)}</td></tr>`),`Không có hóa đơn nào khớp.`)+(r.length>o?`<div class="bar"><span class="muted small">Đang hiện ${o} / ${r.length}</span>${T(`Hiện thêm ${Math.min(50,r.length-o)}`,`ghost`,`id="dmore"`)}</div>`:``),P().querySelectorAll(`.pick`).forEach(t=>{t.onchange=()=>{t.checked?s.add(t.value):s.delete(t.value),e(`#dcount`).textContent=`${l().length} hóa đơn, đã chọn ${s.size}`}}),e(`#dmore`)&&(e(`#dmore`).onclick=()=>{o+=50,u()})};e(`#dq`).oninput=()=>{o=50,u()},e(`#dpick`).onclick=()=>{l().slice(0,o).forEach(e=>s.add(e.k)),u()},e(`#dnone`).onclick=()=>{s.clear(),u()},u(),e(`#make`).onclick=async()=>{let n=[...s];if(!n.length){e(`#mk`).innerHTML=C(`warning`,`Chọn ít nhất một hóa đơn`);return}let r=e(`#make`);r.disabled=!0,e(`#mk`).innerHTML=w(`Đang gom chứng từ và soạn thư giải trình`);try{let r=await m(`/api/workspaces/${N.ws}/dossier`,{invoice_keys:n,request_text:e(`#req`).value});e(`#mk`).innerHTML=``;let i=r.letter;e(`#letter`).innerHTML=`<div class="panel"><div class="bar" style="margin-top:0">${xe(i.mode)}<span class="muted small">${t(i.note||``)}</span>
        <a class="cds--btn cds--btn--primary cds--btn--sm" href="/api/workspaces/${t(N.ws)}/dossier/${t(r.file)}">Tải hồ sơ (.zip)</a></div>
        <h3>Bản nháp thư giải trình</h3>${i.paragraphs.map(e=>`<p>${t(e.text)} <span class="muted small">${[...e.fact_ids,...e.passage_ids].map(t).join(`, `)}</span></p>`).join(``)}
        ${i.dropped&&i.dropped.length?C(`info`,`${i.dropped.length} đoạn bị loại vì không qua kiểm tra căn cứ`,i.dropped.map(e=>e.reason).join(`; `)):``}
        <h3>Dữ kiện đối chiếu</h3><ul>${r.facts.map(e=>`<li><strong>${t(e.id)}</strong> ${t(e.text)}</li>`).join(``)}</ul>
        ${r.passages.length?`<h3>Điều khoản trích dẫn</h3><ul>${r.passages.map(e=>`<li><strong>${t(e.pid)}</strong> <a href="${t(e.url)}" target="_blank" rel="noopener">${t(e.path)}</a></li>`).join(``)}</ul>`:``}</div>`}catch(t){e(`#mk`).innerHTML=C(`error`,`Không lập được hồ sơ`,t.message)}finally{r.isConnected&&(r.disabled=!1)}}}async function Ee(){if(V())return;let r;try{r=await p(`/api/workspaces/${N.ws}/vat-summary`)}catch(e){if(e.name===`AbortError`)throw e;let t=[404,409].includes(e.status);P().innerHTML=`<h1 class="page">Số liệu thuế GTGT</h1>${C(t?`info`:`error`,t?`Cần chạy phân tích`:`Không tải được số liệu`,e.message)}`;return}let i=e=>e==null?``:Number(e)===0?S(`LLM_VERIFIED`,`Khớp`):`<span class="risk-text">${Number(e)>0?`+`:``}${n(e)}</span>`;P().innerHTML=`
    ${M(`Số liệu thuế GTGT`,`Số liệu thuế giá trị gia tăng`,`TỔNG HỢP & HỒ SƠ THUẾ`,``,`bao-cao`)}
    <h2 class="section" style="margin-top:16px">Bảng tính thuế GTGT theo kỳ</h2>
    ${D([`Kỳ`,{label:`Thuế đầu ra`,num:!0},{label:`Tổng thuế đầu vào`,num:!0},{label:`Không kê khai`,num:!0},{label:`Có nguy cơ`,num:!0},{label:`Chờ xem xét`,num:!0},{label:`Chưa cảnh báo`,num:!0},`Cân đối: chưa tính chờ duyệt`,`Cân đối: kể cả chờ duyệt`],r.rows.map(e=>`<tr><td><strong>${t(e.period)}</strong></td><td class="num">${n(e.output_vat)}</td><td class="num">${n(e.input_vat)}</td><td class="num">${n(e.not_claimed_vat)}</td><td class="num"><strong style="color:var(--a3-danger)">${n(e.at_risk)}</strong></td><td class="num">${n(e.review_vat)}</td><td class="num"><strong>${n(e.no_alert_vat)}</strong></td><td>${y(e.scenario_without_review)}</td><td>${y(e.scenario_with_review)}</td></tr>`))}
    ${r.calculation_status===`UNSUPPORTED_DIRECT`?C(`warning`,`Chưa hỗ trợ tính thuế theo phương pháp trực tiếp`,`Chỉ hiển thị số liệu hóa đơn; không tính thuế phải nộp bằng công thức khấu trừ.`):``}
    <h2 class="section">Đối chiếu với tờ khai đã nộp</h2>
    <form id="decl">${D([`Kỳ`,`Đầu ra đã khai`,`Chênh lệch đầu ra`,`Đầu vào đã khai`,`Chênh lệch với phần chưa cảnh báo`],r.rows.map(e=>`<tr><td><strong>${t(e.period)}</strong></td>
      <td><input class="cds--text-input decl" aria-label="Đầu ra đã khai ${t(e.period)}" data-p="${t(e.period_key)}" data-k="output_vat" value="${e.declared?.output_vat??``}" placeholder="vd 20.000.000" inputmode="numeric"></td><td>${i(e.diff_output)}</td>
      <td><input class="cds--text-input decl" aria-label="Đầu vào đã khai ${t(e.period)}" data-p="${t(e.period_key)}" data-k="input_vat" value="${e.declared?.input_vat??``}" placeholder="vd 15.084.000" inputmode="numeric"></td><td>${i(e.diff_input)}</td></tr>`))}
      <div class="bar">${T(`Lưu và đối chiếu`,`primary`,`type="submit"`)}</div></form>
    ${r.rows.some(e=>!e.sales)?C(`info`,`Chưa có hóa đơn bán ra ở một số kỳ`,`Chênh lệch chỉ phản ánh các tệp đã nạp; kiểm tra mức đầy đủ dữ liệu trước khi dùng số liệu.`):``}`,e(`#decl`).onsubmit=async e=>{e.preventDefault();let t=e.target.querySelector(`button[type=submit]`);t.disabled=!0;let n={};P().querySelectorAll(`.decl`).forEach(e=>{e.value.trim()&&(n[e.dataset.p]||={},n[e.dataset.p][e.dataset.k]=e.value.trim())});try{await p(`/api/workspaces/${N.ws}/declared`,{method:`PUT`,headers:{"Content-Type":`application/json`},body:JSON.stringify(n)}),G(`Đã lưu số đã khai`),be()}catch(e){G(`Không lưu được`,e.message,`error`)}finally{t.isConnected&&(t.disabled=!1)}}}async function De(n){let r=await p(`/api/law/alerts`);r.length?(n.innerHTML=`<h2 class="section">Thay đổi luật cần chú ý (150 ngày qua và 180 ngày tới)</h2>
    ${D([`Ngày`,`Loại`,`Văn bản`,``],r.slice(0,40).map((e,n)=>`<tr><td>${a(e.day)}</td><td>${e.kind===`ENDED`?S(`AT_RISK`,`Hết hiệu lực`):S(`OPPORTUNITY`,`Có hiệu lực`)}</td>
      <td><a href="#/luat?doc=${t(e.doc_id)}">${t(e.doc_type)} ${t(e.doc_num)}</a><div class="muted small">${t((e.title||``).slice(0,150))}${e.by_doc_num?`; thay bằng ${t(e.by_doc_num)}`:``}</div><div id="sum-${n}"></div></td>
      <td>${e.kind===`EFFECTIVE`?T(`Tóm tắt điểm chính`,`ghost`,`data-sum="${n}"`):``}</td></tr>`))}`,n.querySelectorAll(`[data-sum]`).forEach(n=>{n.onclick=async()=>{let i=Number(n.dataset.sum),a=e(`#sum-${i}`);a.innerHTML=w(`Đang đọc văn bản luật`);try{let e=await m(`/api/law/alerts/${encodeURIComponent(r[i].doc_id)}/summary`);a.innerHTML=`<div class="answer"><div class="chips">${S(e.mode)}</div>${e.sentences.map(e=>`<p style="margin:.4rem 0">${t(e.text)} <span class="muted small">[${e.citations.map(e=>t(e.path.split(` > `).slice(1).join(` > `))).join(`; `)}]</span></p>`).join(``)}
        ${e.dropped?.length?`<div class="cite">${e.dropped.length} câu bị loại vì không có căn cứ.</div>`:``}${e.note?`<div class="cite">${t(e.note)}</div>`:``}</div>`}catch(e){a.innerHTML=C(`error`,`Không tóm tắt được`,e.message)}}})):n.innerHTML=``}function Oe(t){t.innerHTML=`<h3 style="margin-top:1.5rem">Nhập danh sách từ tệp</h3><p class="muted small">Tệp CSV hoặc văn bản bất kỳ có mã số thuế.</p>
    <div class="form-grid"><div class="cds--form-item cds--text-input-wrapper"><label class="cds--label" for="rl-name">Tên danh sách</label><input class="cds--text-input" id="rl-name" placeholder="Danh sách bỏ địa chỉ kinh doanh tháng 10/2026"></div>
    <div class="cds--form-item cds--text-input-wrapper"><label class="cds--label" for="rl-date">Ngày của danh sách</label><input class="cds--text-input" id="rl-date" type="date"></div>
    <div class="cds--form-item cds--text-input-wrapper"><label class="cds--label" for="rl-src">Nguồn</label><input class="cds--text-input" id="rl-src" placeholder="Thông báo của Thuế tỉnh ..."></div></div>
    <div class="bar"><input type="file" id="rl-file" accept=".csv,.txt" class="cds--visually-hidden">${T(`Chọn tệp và nhập`,`secondary`,`id="rl-pick"`)}<span id="rl-msg"></span></div>`,e(`#rl-pick`).onclick=()=>{!e(`#rl-name`).value||!e(`#rl-date`).value?e(`#rl-msg`).innerHTML=C(`warning`,`Cần tên và ngày của danh sách`):e(`#rl-file`).click()},e(`#rl-file`).onchange=async()=>{let t=e(`#rl-file`).files[0];try{let n=await p(`/api/workspaces/${N.ws}/risk-list?name=${encodeURIComponent(e(`#rl-name`).value)}&as_of=${e(`#rl-date`).value}&source=${encodeURIComponent(e(`#rl-src`).value)}`,{method:`PUT`,body:t});e(`#rl-msg`).innerHTML=C(`success`,`Đã nhập ${n.tax_ids} mã số thuế`,n.rejected.length?`Bỏ qua mã sai: ${n.rejected.join(`, `)}`:`Chạy lại phân tích để áp dụng.`)}catch(t){e(`#rl-msg`).innerHTML=C(`error`,`Không nhập được`,t.message)}}}var ke=()=>window.dispatchEvent(new Event(`hashchange`)),Ae=[`id`,`flag`,`min_gross`,`description_contains`],je=e=>Object.fromEntries(Ae.filter(t=>e[t]!==void 0&&e[t]!==``&&!(Array.isArray(e[t])&&!e[t].length)).map(t=>[t,e[t]]));function Me(e,n,r,i=`pol`){return`<div class="preset ${r?`on`:``}" data-card="${n}"><input type="checkbox" data-${i}="${n}" ${r?`checked`:``} aria-label="Áp dụng">
    <div class="preset-body"><div class="preset-head"><strong>${t(e.flag)}</strong>${e.industry_fit?`<span class="badge-fit">Gợi ý cho ngành của bạn</span>`:e.recommended?`<span class="badge-rec">Nên dùng</span>`:``}${e.group?`<span class="muted small">${t(e.group)}</span>`:``}</div>
    <div class="preset-edit">
      <label>Nội dung nhắc<input class="cds--text-input" data-f="flag" value="${t(e.flag)}"></label>
      <label>Áp dụng từ số tiền (đồng)<input class="cds--text-input" data-f="min_gross" inputmode="numeric" value="${e.min_gross??``}" placeholder="mọi số tiền"></label>
      <label>Khi tên hàng có (cách nhau dấu phẩy)<input class="cds--text-input" data-f="description_contains" value="${t((e.description_contains||[]).join(`, `))}" placeholder="mọi hàng hóa"></label></div></div></div>`}function Ne(e){let t=t=>e.querySelector(`[data-f="${t}"]`).value.trim(),n=Number(t(`min_gross`).replace(/\D/g,``))||void 0;return{flag:t(`flag`),min_gross:n,description_contains:t(`description_contains`).split(`,`).map(e=>e.trim()).filter(Boolean)}}Array.from({length:12},(e,t)=>[String(t+1),`Tháng ${t+1}`]);async function Pe(){V()}var Fe=e=>`<div class="panel shared-profile"><h2 class="section">Hồ sơ chung từ portal</h2><dl class="kv"><dt>Doanh nghiệp</dt><dd>${t(e.legal_name)}</dd><dt>Mã số thuế</dt><dd>${t(e.tax_code)}</dd><dt>Địa chỉ</dt><dd>${t(e.registered_address||`Chưa khai báo`)}</dd><dt>Ngành nghề</dt><dd>${t((e.industry||[]).join(`; `))}</dd><dt>Thuế GTGT / Kỳ khai</dt><dd>${e.vat_method===`DIRECT`?`Trực tiếp`:`Khấu trừ`} / ${e.filing_period===`MONTH`?`Tháng`:`Quý`}</dd><dt>Kết thúc năm tài chính</dt><dd>Tháng ${t(e.fiscal_year_end_month||12)}</dd></dl><p class="muted">Thông tin được quản lý tại portal. Agent 3 chỉ lưu thiết lập nghiệp vụ thuế riêng.</p>${L()}</div>`;async function Ie(){if(V())return;N.schema||=await p(`/api/schema`);let n=await p(`/api/workspaces/${N.ws}/pack`),r=null,i=null,s={...structuredClone(n),custom:[],picked:null,edits:{}},c=`agent3.tax-draft.${N.platform.profile_revision}`,l=!1;u(()=>{if(!l){g();try{sessionStorage.setItem(c,JSON.stringify({...s,picked:s.picked?[...s.picked]:null}))}catch{}}});let d=Math.max(1,Math.min(5,Number(new URLSearchParams(location.hash.split(`?`)[1]||``).get(`buoc`)||1))),f=[`Quy định chi tiêu`,`Ngưỡng nội bộ`,`Nhóm hàng đặc thù`,`Ngày nghỉ`,`Xác nhận`],m=()=>{let u=`<nav class="steps">${f.map((e,n)=>`<a class="${n+1===d?`on`:n+1<d?`done`:``}" ${n+1<d?`data-step="${n+1}" href="javascript:void 0"`:``}><span class="n">${n+1<d?`✓`:n+1}</span>${t(e)}</a>`).join(``)}</nav>`,_=``;if(d===1){let e=(s.profile.industry||[]).join(`;`);if(!r||i!==e){p(`/api/presets?industry=${encodeURIComponent(e)}`).then(t=>{r=t.policies,i=e,s.picked===null&&(s.picked=new Set(s.policies.filter(e=>r.some(t=>t.id===e.id)).map(e=>e.id)),s.edits=Object.fromEntries(s.policies.map(e=>[e.id,e])),s.custom=s.policies.filter(e=>!r.some(t=>t.id===e.id))),m()}).catch(e=>{e.name!==`AbortError`&&(P().innerHTML=C(`error`,`Chưa tải được gợi ý`,e.message))}),P().innerHTML=`<h1 class="page">Thiết lập nghiệp vụ thuế</h1>${w(`Đang chọn gợi ý theo ngành nghề`)}`;return}}if(d===1){let e=(s.profile.industry||[]).map(e=>(String(e).match(/^\s*(\d{2,5})/)||[])[1]).filter(Boolean);_=`<p class="muted">Quy định chi tiêu nội bộ: mỗi quy định chỉ thêm nhắc nhở cho kế toán khi gặp hóa đơn phù hợp, không làm thay đổi kết quả theo luật.
        ${e.length?`Gợi ý theo ngành ${e.map(t).join(`, `)}.`:`Chưa có ngành nghề trong hồ sơ chung; chỉ hiển thị gợi ý chung.`} Sửa nội dung, số tiền, từ khóa theo quy chế của doanh nghiệp.</p>
        <div class="bar" style="margin-bottom:12px">
          ${T(`Chọn gợi ý theo ngành`,`tertiary`,`id="setup-sync-policies" type="button"`)}
          ${T(`Chọn tất cả gợi ý`,`ghost`,`id="setup-all-policies" type="button"`)}
        </div>
        <div class="preset-list">${r.map((e,t)=>Me({...e,...s.edits[e.id]||{}},t,s.picked.has(e.id))).join(``)}</div>
        <h3 class="sub-h">Quy định riêng của doanh nghiệp</h3>
        <div id="custom-list">${s.custom.map((e,t)=>Me({...e,recommended:!1},t,!0,`cus`)).join(``)||`<p class="muted small">Chưa có. Ví dụ: "Mua văn phòng phẩm từ 1 triệu cần phiếu đề xuất" khi tên hàng có "giấy, bút, mực in".</p>`}</div>
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
</dl><div id="setup-msg"></div>`;P().innerHTML=`${M(`Thiết lập nghiệp vụ`,`Thiết lập nghiệp vụ thuế`,`CẤU HÌNH NGHIỆP VỤ THUẾ`,`Bước ${d}/${f.length}: ${f[d-1]}`)}
      ${Fe(s.profile)}${u}
      <form id="setup">
        <div class="panel" style="padding:26px 28px;border-radius:12px;box-shadow:var(--a3-shadow-sm);margin-bottom:20px;border:1px solid var(--cds-border-subtle)">${_}</div>
        <div class="bar">${d>1?T(`Quay lại`,`ghost`,`id="back"`):T(`Trở về cấu hình doanh nghiệp`,`ghost`,`data-go="#/quan-tri/doanh-nghiep"`)}${T(d===f.length?`Lưu thiết lập`:`Tiếp tục`,`primary`,`type="submit"`)}</div>
      </form>`,P().querySelectorAll(`[data-step]`).forEach(e=>{e.onclick=()=>{g(),d=Number(e.dataset.step),m()}}),e(`#back`)&&(e(`#back`).onclick=()=>{g(),--d,m()}),P().querySelectorAll(`[data-pol],[data-cus]`).forEach(e=>{e.onchange=()=>e.closest(`[data-card]`).classList.toggle(`on`,e.checked)}),e(`#add-pol`)&&(e(`#add-pol`).onclick=()=>{g(),s.custom.push({flag:`Quy định mới: sửa nội dung nhắc`,description_contains:[]}),m()}),e(`#add-cat`)&&(e(`#add-cat`).onclick=()=>{g(),s.ai_categories.length<10&&s.ai_categories.push({name:``,description:``}),m()}),e(`#setup-sync-policies`)&&(e(`#setup-sync-policies`).onclick=()=>{g();let e=0;r.forEach(t=>{(t.industry_fit||t.recommended)&&(s.picked.add(t.id),e++)}),m(),G(`Đã chọn ${e} quy định gợi ý theo ngành`)}),e(`#setup-all-policies`)&&(e(`#setup-all-policies`).onclick=()=>{g(),r.forEach(e=>s.picked.add(e.id)),m(),G(`Đã chọn tất cả gợi ý`)}),e(`#setup-sync-holidays`)&&(e(`#setup-sync-holidays`).onclick=async()=>{try{let t=(await p(`/api/admin/catalog/holidays`)).data?.years||{},n=[];for(let e in t)for(let r of t[e]||[])r.date&&/^\d{4}-\d{2}-\d{2}$/.test(r.date)&&n.push(r.date);let r=e(`#days`).value.split(/\s+/).map(e=>e.trim()).filter(e=>/^\d{4}-\d{2}-\d{2}$/.test(e)),i=Array.from(new Set([...r,...n])).sort();e(`#days`).value=i.join(`
`),s.days_off=i,G(`Đã đồng bộ ngày nghỉ từ hệ thống`,`Tổng cộng ${i.length} ngày`)}catch(e){G(`Chưa đồng bộ được lịch nghỉ`,e.message,`error`)}}),e(`#setup`).onsubmit=async t=>{if(t.preventDefault(),!g())return;if(d<f.length){d+=1,m();return}let r=e(`#setup button[type="submit"]`);r.disabled=!0,e(`#setup-msg`).innerHTML=w(`Đang lưu thiết lập`);try{let e={...n,policies:s.policies,thresholds:s.thresholds,ai_categories:s.ai_categories,days_off:s.days_off};await h(`/api/workspaces/${N.ws}/pack?by=${encodeURIComponent(o.get(`agent3.reviewer`)||``)}`,e),l=!0,sessionStorage.removeItem(c),G(`Đã lưu thiết lập nghiệp vụ thuế`,`Chạy lại phân tích để áp dụng`),location.hash=`#/quan-tri/doanh-nghiep`}catch(t){e(`#setup-msg`)&&(e(`#setup-msg`).innerHTML=C(`error`,`Chưa lưu được`,t.message))}finally{r.isConnected&&(r.disabled=!1)}}},g=()=>{let t=e(`#setup`);if(!t)return!0;if(d===1)s.picked=new Set,t.querySelectorAll(`[data-pol]`).forEach(e=>{let t=r[Number(e.dataset.pol)];s.edits[t.id]=Ne(e.closest(`[data-card]`)),e.checked&&s.picked.add(t.id)}),s.custom=[...t.querySelectorAll(`[data-cus]`)].filter(e=>e.checked).map(e=>({...s.custom[Number(e.dataset.cus)],...Ne(e.closest(`[data-card]`))})).filter(e=>e.flag),s.policies=[...r.filter(e=>s.picked.has(e.id)).map(e=>je({id:e.id,...s.edits[e.id]})),...s.custom.map((e,t)=>je({id:e.id||`RIENG_${t+1}`,...e}))];else if(d===2){let e=Object.fromEntries(new FormData(t).entries());if(s.thresholds={},e.match_days_after_invoice&&(s.thresholds.match_days_after_invoice=Number(e.match_days_after_invoice)),e.non_cash_threshold_override&&(s.thresholds.non_cash_threshold_override=Number(String(e.non_cash_threshold_override).replace(/\D/g,``))),(s.thresholds.match_days_after_invoice||0)>90)return G(`Số ngày không được quá 90 (chỉ được chặt hơn luật)`,``,`error`),!1;if((s.thresholds.non_cash_threshold_override||0)>5e6)return G(`Ngưỡng nội bộ không được cao hơn 5.000.000 đồng theo luật`,``,`error`),!1}else if(d===3){let e={};if(t.querySelectorAll(`[data-cat]`).forEach(t=>{e[t.dataset.cat]||={},e[t.dataset.cat][t.dataset.k]=t.value.trim()}),s.ai_categories=Object.values(e).filter(e=>e.name||e.description),s.ai_categories.some(e=>!e.name||!e.description))return G(`Mỗi nhóm cần cả tên và mô tả`,``,`error`),!1}else if(d===4&&(s.days_off=e(`#days`).value.split(/\s+/).map(e=>e.trim()).filter(Boolean),s.days_off.some(e=>!/^\d{4}-\d{2}-\d{2}$/.test(e))))return G(`Ngày phải có dạng năm-tháng-ngày, ví dụ 2027-02-05`,``,`error`),!1;return!0};try{let e=JSON.parse(sessionStorage.getItem(c)||`null`);e&&(Object.assign(s,e,{profile:n.profile}),s.picked=e.picked?new Set(e.picked):null)}catch{}m()}async function Le(){if(!N.ws){location.hash=`#/`;return}N.schema||=await p(`/api/schema`);let[r,i]=await Promise.all([p(`/api/workspaces/${N.ws}/pack`),p(`/api/workspaces/${N.ws}/pack/history`)]),s={policies:(await p(`/api/presets?industry=${encodeURIComponent((r.profile.industry||[]).join(`;`))}`)).policies},c=async(e,t)=>{try{await h(`/api/workspaces/${N.ws}/pack?by=${encodeURIComponent(o.get(`agent3.reviewer`)||``)}`,e),G(t||`Đã lưu cấu hình`,`Chạy lại phân tích để áp dụng`),await I(),ke()}catch(e){G(`Không lưu được`,e.message,`error`)}},l=(e,n,r,i)=>`<section class="cfg" id="cfg-${e}"><h2 class="section"><span>${t(n)}</span></h2><p class="section-desc">${t(r)}</p>${i}</section>`,u=r.ai_categories||[],d=(r.profile.industry||[]).map(e=>(String(e).match(/^\s*(\d{2,5})/)||[])[1]).filter(Boolean),f=d.length?`ngành VSIC ${d.join(`, `)}`:`ngành`,g=`
    <div class="panel" style="border-radius:12px;padding:18px 22px;background:var(--a3-surface);border:1px solid var(--cds-border-subtle);margin-bottom:24px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:16px;box-shadow:var(--a3-shadow-sm)">
      <div style="max-width:650px">
        <h4 style="margin:0 0 6px 0;font-size:15px;font-weight:600">
          Hướng dẫn thiết lập nghiệp vụ thuế (Wizard 5 bước)
        </h4>
        <p class="muted small" style="margin:0;line-height:1.55">Trình hỗ trợ thiết lập tuần tự: chọn quy định chi tiêu, ngưỡng kiểm soát, nhóm hàng AI và ngày nghỉ theo từng bước có giải thích chi tiết.</p>
      </div>
      <div class="bar" style="margin:0">
        ${T(`Chạy wizard thiết lập 5 bước`,`secondary`,`data-go="#/thiet-lap"`)}
      </div>
    </div>`;P().innerHTML=`${M(`Cấu hình doanh nghiệp`,r.profile.legal_name,`CẤU HÌNH RIÊNG CỦA DOANH NGHIỆP`)}
    ${g}
    <nav class="cfg-nav">${[[`ho-so`,`Hồ sơ`],[`ngan-hang`,`Mẫu sao kê`],[`bang-ke`,`Cột bảng kê`],[`quy-dinh`,`Quy định chi tiêu`],[`nguong`,`Ngưỡng`],[`nhom-hang`,`Nhóm hàng đặc thù`],[`ngay-nghi`,`Ngày nghỉ`],[`rui-ro`,`Danh sách rủi ro`],[`lich-su`,`Lịch sử thay đổi`]].map(([e,n])=>`<a href="javascript:void 0" data-jump="cfg-${e}">${t(n)}</a>`).join(``)}</nav>
    <section id="cfg-ho-so">${Fe(r.profile)}</section>
    ${l(`ngan-hang`,`Mẫu sao kê ngân hàng`,`Mỗi ngân hàng một mẫu; chỉnh cột từ sao kê đã nạp.`,D([`Tên mẫu`,`Cột ngày`,`Cột tiền ra`,`Cột tiền vào`,`Cách viết số`,``],(r.bank_formats||[]).map((e,n)=>`<tr><td>${t(e.name)}</td><td class="mono">${t(e.columns.date)}</td>
      <td class="mono">${t(e.columns.debit)}</td><td class="mono">${t(e.columns.credit||``)}</td><td>${e.thousands===`.`?`1.234.567`:`1,234,567`}</td><td>${T(`Xóa`,`ghost`,`data-delfmt="${n}"`)}</td></tr>`),`Chưa có mẫu. Nạp sao kê tại portal rồi mở Nhận dạng cột.`)+`<div class="bar">${T(`Nhận dạng cột từ sao kê đã nạp`,`ghost`,`data-go="#/quan-tri/mau-sao-ke"`)}</div>`)}
    ${l(`bang-ke`,`Cột của bảng kê cổng thuế`,`Khi cổng hóa đơn điện tử đổi mẫu tệp xuất, chọn lại cột ở đây; không cần sửa tệp.`,`<div id="portal-map"><div class="bar">`+T(`Đọc tiêu đề bảng kê đã nạp`,`ghost`,`id="portal-load"`)+`</div></div>`)}
    ${l(`quy-dinh`,`Quy định chi tiêu nội bộ`,`Chỉ thêm nhắc nhở cho kế toán, không thay đổi kết quả theo luật.`,`
      <div class="bar" style="margin-bottom:14px">
        ${T(`Chọn gợi ý theo ${f}`,`tertiary`,`id="sync-industry-policies" type="button"`)}
        ${T(`Chọn tất cả gợi ý`,`ghost`,`id="select-all-presets" type="button"`)}
        ${T(`Bỏ chọn tất cả`,`ghost`,`id="deselect-all-presets" type="button"`)}
      </div>
      <div class="preset-list">${s.policies.map((e,i)=>`<label class="preset"><input type="checkbox" data-preset="${i}" ${(r.policies||[]).some(t=>t.id===e.id)?`checked`:``}>
      <span><strong>${t(e.flag)}</strong>${e.industry_fit?`<span class="badge-fit">Gợi ý cho ngành của bạn</span>`:``}<span class="muted small">${e.min_gross?`từ ${n(e.min_gross)}`:``}${e.description_contains?` khi tên hàng có: ${e.description_contains.map(t).join(`, `)}`:``}</span></span></label>`).join(``)}
      ${(r.policies||[]).filter(e=>!s.policies.some(t=>t.id===e.id)).map(e=>`<label class="preset"><input type="checkbox" checked data-custom="${t(e.id)}"><span><strong>${t(e.flag)}</strong><span class="muted small">quy định riêng</span></span></label>`).join(``)}</div>
      <form id="f-pol" style="margin-top:.75rem"><div class="form-grid">${E({key:`flag`,label:`Thêm quy định riêng: nội dung nhắc`,example:`Mua văn phòng phẩm từ 1 triệu cần phiếu đề xuất`})}${E({key:`min_gross`,label:`Áp dụng từ số tiền (đồng)`,example:`1000000`})}${E({key:`description_contains`,label:`Tên hàng có chứa (cách nhau dấu chấm phẩy)`,example:`giấy; bút; mực in`})}</div>
      <div class="bar">${T(`Lưu quy định`,`primary`,`type="submit"`)}</div></form>`)}
    ${l(`nguong`,`Ngưỡng nội bộ`,`Chỉ được chặt hơn luật; để trống để dùng mức theo luật.`,`<form id="f-th"><div class="form-grid">
      ${E({key:`match_days_after_invoice`,label:`Số ngày tối đa từ ngày hóa đơn đến ngày thanh toán`,example:`90 (không quá 90)`},r.thresholds?.match_days_after_invoice??``)}
      ${E({key:`non_cash_threshold_override`,label:`Ngưỡng nội bộ yêu cầu chuyển khoản (đồng)`,example:`để trống dùng 5.000.000 theo luật`},r.thresholds?.non_cash_threshold_override??``)}</div>
      <div class="bar">${T(`Lưu ngưỡng`,`primary`,`type="submit"`)}</div></form>`)}
    ${l(`nhom-hang`,`Nhóm hàng đặc thù cho AI`,`AI coi các nhóm này là phục vụ kinh doanh khi phân loại dòng hàng (ví dụ nhà hàng mua thực phẩm). Chạy lại Phân loại dòng hàng sau khi đổi.`,`<form id="f-cat">
      <div class="bar" style="margin-bottom:12px">
        ${T(`Nạp gợi ý nhóm hàng từ hệ thống`,`tertiary`,`id="sync-cats-sys" type="button"`)}
      </div>
      <div id="cat-rows-container">
      ${(u.length?u:[{name:``,description:``}]).concat([{name:``,description:``}]).map((e,n)=>`<div class="form-grid cat-row">
        <div class="cds--form-item cds--text-input-wrapper"><label class="cds--label">Tên nhóm</label><input class="cds--text-input" data-cat="${n}" data-k="name" value="${t(e.name)}" placeholder="Nguyên liệu thực phẩm"></div>
        <div class="cds--form-item cds--text-input-wrapper"><label class="cds--label">Mô tả</label><input class="cds--text-input" data-cat="${n}" data-k="description" value="${t(e.description)}" placeholder="thịt, cá, rau dùng chế biến món ăn"></div></div>`).join(``)}
      </div>
      <div class="bar">${T(`Lưu nhóm hàng`,`primary`,`type="submit"`)}</div></form>`)}
    ${l(`ngay-nghi`,`Ngày nghỉ trong năm`,`Tết và nghỉ bù do Chính phủ công bố hằng năm; thứ Bảy, Chủ nhật và lễ cố định đã có sẵn.`,`<form id="f-days">
      <div class="bar" style="margin-bottom:12px">
        ${T(`Đồng bộ từ lịch nghỉ lễ hệ thống`,`tertiary`,`id="sync-holidays-sys" type="button"`)}
      </div>
      <div class="cds--form-item"><textarea class="cds--text-area" id="days" rows="5" placeholder="2026-02-16&#10;2026-02-17&#10;2027-02-05">${t((r.days_off||[]).join(`
`))}</textarea></div>
      <div class="bar">${T(`Lưu ngày nghỉ`,`primary`,`type="submit"`)}<span id="days-msg" class="muted small"></span></div></form>`)}
    ${l(`rui-ro`,`Danh sách doanh nghiệp rủi ro`,`Người bán trong danh sách sẽ được gắn cờ cần xem; luôn ghi ngày và nguồn.`,D([`Tên danh sách`,`Ngày`,{label:`Số mã số thuế`,num:!0},`Nguồn`],(r.reference_lists||[]).map(e=>`<tr><td>${t(e.name)}</td><td>${a(e.as_of)}</td><td class="num">${e.tax_ids.length}</td><td>${t(e.source||``)}</td></tr>`),`Chưa có.`)+`<div id="riskimp"></div>`)}
    ${l(`lich-su`,`Lịch sử thay đổi cấu hình`,`Ai đổi phần nào, lúc nào.`,D([`Thời điểm`,`Người`,`Phần thay đổi`],i.slice(0,30).map(e=>`<tr><td>${t(e.at.replace(`T`,` `))}</td><td>${t(e.by)}</td><td>${e.created?`Tạo doanh nghiệp`:t(e.changed.join(`, `))}</td></tr>`),`Chưa có thay đổi nào được ghi.`))}`,P().querySelectorAll(`[data-jump]`).forEach(e=>{e.onclick=()=>document.getElementById(e.dataset.jump).scrollIntoView({block:`start`})}),P().querySelectorAll(`[data-delfmt]`).forEach(e=>{e.onclick=()=>c({...r,bank_formats:r.bank_formats.filter((t,n)=>n!==Number(e.dataset.delfmt))},`Đã xóa mẫu sao kê`)});let _=e(`#sync-industry-policies`);_&&(_.onclick=()=>{let e=0;s.policies.forEach((t,n)=>{let r=P().querySelector(`[data-preset="${n}"]`);r&&(t.industry_fit||t.recommended)&&(r.checked=!0,e++)}),G(`Đã chọn ${e} quy định gợi ý`,`Bấm "Lưu quy định" để lưu thay đổi`)});let v=e(`#select-all-presets`);v&&(v.onclick=()=>{s.policies.forEach((e,t)=>{let n=P().querySelector(`[data-preset="${t}"]`);n&&(n.checked=!0)}),G(`Đã chọn tất cả gợi ý`,`Bấm "Lưu quy định" để lưu`)});let y=e(`#deselect-all-presets`);y&&(y.onclick=()=>{s.policies.forEach((e,t)=>{let n=P().querySelector(`[data-preset="${t}"]`);n&&(n.checked=!1)}),G(`Đã bỏ chọn gợi ý`,`Bấm "Lưu quy định" để lưu`)});let b=e(`#sync-holidays-sys`);b&&(b.onclick=async()=>{try{b.disabled=!0;let t=(await p(`/api/admin/catalog/holidays`)).data?.years||{},n=[];for(let e in t)for(let r of t[e]||[])r.date&&/^\d{4}-\d{2}-\d{2}$/.test(r.date)&&n.push(r.date);let r=e(`#days`).value.split(/\s+/).map(e=>e.trim()).filter(e=>/^\d{4}-\d{2}-\d{2}$/.test(e)),i=Array.from(new Set([...r,...n])).sort();e(`#days`).value=i.join(`
`),G(`Đã đồng bộ ngày nghỉ từ hệ thống`,`Tổng cộng ${i.length} ngày (đã hợp nhất). Bấm "Lưu ngày nghỉ" để áp dụng.`)}catch(e){G(`Chưa đồng bộ được lịch nghỉ`,e.message,`error`)}finally{b.isConnected&&(b.disabled=!1)}});let x=e(`#sync-cats-sys`);x&&(x.onclick=async()=>{try{x.disabled=!0;let n=((await p(`/api/admin/catalog/ai_categories`)).data?.categories||[]).filter(e=>![`CA_NHAN`,`KHONG_RO`].includes(e.id));if(!n.length){G(`Không có nhóm hàng mẫu nào`,``,`warning`);return}let r=[...P().querySelectorAll(`.cat-row`)].map(e=>({name:e.querySelector(`[data-k="name"]`)?.value.trim()||``,description:e.querySelector(`[data-k="description"]`)?.value.trim()||``})).filter(e=>e.name||e.description),i=n.map(e=>({name:e.id.replace(/_/g,` `),description:e.description})).filter(e=>!r.some(t=>t.name.toLowerCase()===e.name.toLowerCase())),a=[...r,...i].slice(0,10),o=e(`#cat-rows-container`);o&&(o.innerHTML=a.concat([{name:``,description:``}]).map((e,n)=>`<div class="form-grid cat-row">
          <div class="cds--form-item cds--text-input-wrapper"><label class="cds--label">Tên nhóm</label><input class="cds--text-input" data-cat="${n}" data-k="name" value="${t(e.name)}" placeholder="Nguyên liệu thực phẩm"></div>
          <div class="cds--form-item cds--text-input-wrapper"><label class="cds--label">Mô tả</label><input class="cds--text-input" data-cat="${n}" data-k="description" value="${t(e.description)}" placeholder="thịt, cá, rau dùng chế biến món ăn"></div></div>`).join(``)),G(`Đã nạp nhóm hàng gợi ý`,`Thêm ${i.length} nhóm. Bấm "Lưu nhóm hàng" để áp dụng.`)}catch(e){G(`Chưa nạp được nhóm hàng`,e.message,`error`)}finally{x.isConnected&&(x.disabled=!1)}});let S=()=>[...s.policies.filter((e,t)=>P().querySelector(`[data-preset="${t}"]`).checked).map(e=>je({...e,...(r.policies||[]).find(t=>t.id===e.id)||{}})),...(r.policies||[]).filter(e=>!s.policies.some(t=>t.id===e.id)&&P().querySelector(`[data-custom="${e.id}"]`)?.checked)];e(`#f-pol`).onsubmit=e=>{e.preventDefault();let t=Object.fromEntries(new FormData(e.target).entries()),n=S();if(t.flag){let e={id:`RIENG_${Date.now().toString(36).toUpperCase()}`,flag:t.flag};t.min_gross&&(e.min_gross=Number(String(t.min_gross).replace(/\D/g,``))),t.description_contains&&(e.description_contains=t.description_contains.split(`;`).map(e=>e.trim()).filter(Boolean)),n.push(e)}c({...r,policies:n},`Đã lưu quy định chi tiêu`)},e(`#f-th`).onsubmit=e=>{e.preventDefault();let t=Object.fromEntries(new FormData(e.target).entries()),n={};t.match_days_after_invoice&&(n.match_days_after_invoice=Number(t.match_days_after_invoice)),t.non_cash_threshold_override&&(n.non_cash_threshold_override=Number(String(t.non_cash_threshold_override).replace(/\D/g,``))),c({...r,thresholds:n},`Đã lưu ngưỡng`)},e(`#f-cat`).onsubmit=e=>{e.preventDefault();let t={};e.target.querySelectorAll(`[data-cat]`).forEach(e=>{t[e.dataset.cat]||={},t[e.dataset.cat][e.dataset.k]=e.value.trim()}),c({...r,ai_categories:Object.values(t).filter(e=>e.name&&e.description)},`Đã lưu nhóm hàng đặc thù`)},e(`#f-days`).onsubmit=t=>{t.preventDefault(),c({...r,days_off:e(`#days`).value.split(/\s+/).map(e=>e.trim()).filter(Boolean)},`Đã lưu ngày nghỉ`)},e(`#portal-load`).onclick=async()=>{try{let n=await m(`/api/workspaces/${N.ws}/portal/suggest`);e(`#portal-map`).innerHTML=`<form id="f-portal"><div class="form-grid">${Object.entries(n.fields).map(([e,r])=>`<div class="cds--form-item"><div class="cds--select"><label class="cds--label">${t(r)}</label>
        <div class="cds--select-input__wrapper"><select class="cds--select-input" name="${e}"><option value="">(không có)</option>${n.headers.map(r=>`<option ${r===n.current[e]?`selected`:``}>${t(r)}</option>`).join(``)}</select></div></div></div>`).join(``)}</div>
        <div class="bar">${T(`Lưu cột bảng kê`,`primary`,`type="submit"`)}</div></form>`,e(`#f-portal`).onsubmit=e=>{e.preventDefault();let t=Object.fromEntries([...new FormData(e.target).entries()].filter(([,e])=>e));c({...r,portal_columns:t},`Đã lưu cột bảng kê`)}}catch(t){e(`#portal-map`).insertAdjacentHTML(`beforeend`,C(`warning`,`Chưa đọc được bảng kê`,t.message))}},Oe(e(`#riskimp`))}var q=e=>e.finding_id||`${e.code}|${e.invoice_keys.join(`,`)}`,Re=[],J=null,ze=null,Be=()=>window.dispatchEvent(new Event(`hashchange`));async function Ve(){if(!N.ws){await Pe();return}let i=N.workspaces.find(e=>e.id===N.ws),o=await R(),s=ee(o),c=o?.totals,l=i.files||{},u=e=>e===`undated`?`Chưa rõ ngày`:`Tháng ${e.slice(5)}/${e.slice(0,4)}`,d=o?.totals.series||[],f=()=>{if(c?.missing_vat_invoices)return C(`info`,`Chưa đủ số thuế để vẽ biểu đồ`,`Một số hóa đơn thiếu số thuế; không thay giá trị thiếu bằng 0.`);if(d.length<2)return``;let e=Math.max(...d.map(e=>Number(e.total||0)),1),r=d.map((r,i)=>{let a=10+i*34,o=Math.abs(Number(r.AT_RISK))/e*300,s=Math.abs(Number(r.REVIEW))/e*300,c=[Number(r.AT_RISK)?`${b(r.AT_RISK)||n(r.AT_RISK)} có nguy cơ`:``,Number(r.REVIEW)?`${b(r.REVIEW)||n(r.REVIEW)} cần xem xét`:``].filter(Boolean);return`<text class="t-month" x="0" y="${a+15}">${t(u(r.k))}</text>
        ${o?`<rect class="bar-risk" x="118" y="${a}" width="${o.toFixed(1)}" height="20"/>`:``}${s?`<rect class="bar-review" x="${(118+o).toFixed(1)}" y="${a}" width="${s.toFixed(1)}" height="20"/>`:``}
        <text class="t-val" x="${(118+o+s+10).toFixed(1)}" y="${a+15}">${t(c.join(` · `)||`không có việc`)}</text>`}).join(``);return`<section class="tufte" aria-labelledby="tufte-h"><h2 class="section" id="tufte-h">Phân bổ thuế cần chú ý theo tháng lập hóa đơn</h2>
      <svg class="tufte-svg" viewBox="0 0 700 ${d.length*34+14}" role="img" aria-label="Thuế có nguy cơ và cần xem xét theo tháng">${r}</svg></section>`};(o?.meta.data_warnings||[]).length&&`${o.meta.data_warnings.map(e=>`<div class="data-warning-item">${t(e)}</div>`).join(``)}`,P().innerHTML=`
    ${M(`Tổng quan`,`Tổng quan`,`KHÔNG GIAN DOANH NGHIỆP`,o?`<span class="ctx-chip chip-date">Phân tích: ${a(o.meta.as_of)}</span>`:``)}

    <div id="fresh"></div>
    <div id="watch"></div>
    ${ce(o)}

    <div class="kpis-v2">
      <a href="#/viec?loc=AT_RISK" class="kpi-card-v2 kpi-card-risk">
        <div class="kpi-head-v2">
          <span class="kpi-title-label">Thuế đầu vào có nguy cơ bị loại</span>
          <span class="rev-card-count pill-risk">${s?`${s.atRiskItems} việc`:`0 việc`}</span>
        </div>
        <div class="kpi-money-block">
          <div class="kpi-main-money val-risk">${r(s?.atRiskVat)}</div>
        </div>
        <div class="kpi-footer-v2">
          <span class="kpi-sub-text">${s?`<strong>${s.atRiskInvoices}</strong> hóa đơn mua vào · <strong>${s.atRiskItems}</strong> đầu việc`:`Chưa phân tích`}</span>
          <span class="kpi-arrow-action" aria-hidden="true">Mở việc →</span>
        </div>
      </a>

      <a href="#/viec?loc=REVIEW" class="kpi-card-v2 kpi-card-warn">
        <div class="kpi-head-v2">
          <span class="kpi-title-label">Việc cần rà soát</span>
          <span class="rev-card-count pill-warn">${s?`${s.reviewItems} việc`:`0 việc`}</span>
        </div>
        <div class="kpi-money-block">
          <div class="kpi-main-money val-warn">${s?.reviewItems&&!s.reviewInvoices?`<span class="kpi-amount-empty">Chưa xác định</span>`:r(s?.reviewVat)}</div>
        </div>
        <div class="kpi-footer-v2">
          <span class="kpi-sub-text">${s?s.reviewInvoices?`<strong>${s.reviewInvoices}</strong> hóa đơn mua vào · <strong>${s.reviewItems}</strong> đầu việc`:`<strong>${s.reviewItems}</strong> đầu việc cần rà soát thêm`:`Chưa phân tích`}</span>
          <span class="kpi-arrow-action" aria-hidden="true">Mở việc →</span>
        </div>
      </a>

      <a href="#/viec?loc=OPPORTUNITY" class="kpi-card-v2 kpi-card-opportunity">
        <div class="kpi-head-v2">
          <span class="kpi-title-label">Có thể đang bỏ sót khấu trừ</span>
          <span class="rev-card-count pill-opp">${s?`${s.opportunityItems} việc`:`0 việc`}</span>
        </div>
        <div class="kpi-money-block">
          <div class="kpi-main-money val-opportunity">${r(s?.opportunityVat)}</div>
        </div>
        <div class="kpi-footer-v2">
          <span class="kpi-sub-text">Hóa đơn trên bảng kê cổng thuế chưa có XML</span>
          <span class="kpi-arrow-action" aria-hidden="true">Mở việc →</span>
        </div>
      </a>

      <a href="#/so-lieu" class="kpi-card-v2 kpi-card-penalty">
        <div class="kpi-head-v2">
          <span class="kpi-title-label">Ước tính phạt nếu khai sai</span>
          <span class="rev-card-count pill-progress">Kịch bản</span>
        </div>
        <div class="kpi-money-block">
          <div class="kpi-main-money val-penalty">${r(s?.penaltyEstimate)}</div>
        </div>
        <div class="kpi-footer-v2">
          <span class="kpi-sub-text">${s?`Thuế đầu ra ${n(s.saleVat)} · Đầu vào ${n(s.purchaseVat)}`:`Chưa có số liệu`}</span>
          <span class="kpi-arrow-action" aria-hidden="true">Số liệu →</span>
        </div>
      </a>
    </div>

    <div class="bar a3-overview-toolbar">
      ${T(`Chạy phân tích ngay`,`primary`,`id="run"`)}
      ${o?`<details class="quick-export"><summary>Xuất báo cáo</summary>
        <a class="cds--btn cds--btn--tertiary cds--btn--sm" href="/api/workspaces/${t(N.ws)}/report.html" target="_blank" rel="noopener">Báo cáo in (HTML)</a>
        <a class="cds--btn cds--btn--ghost cds--btn--sm" href="/api/workspaces/${t(N.ws)}/export/hoa-don.xlsx">Danh sách hóa đơn (Excel)</a>
        <a class="cds--btn cds--btn--ghost cds--btn--sm" href="/api/workspaces/${t(N.ws)}/export/quyet-dinh.xlsx">Nhật ký quyết định (Excel)</a>
      </details>`:``}
      <span id="run-msg"></span>
    </div>
    <div id="analysis-stage"></div>

    ${f()}

    <div class="a3-overview-data">

      <div>
        <div class="a3-section-head">
          <h2 class="section" style="margin:0">Nguồn dữ liệu kỳ này</h2>
          <a class="small" href="#/nap">Nạp thêm tệp →</a>
        </div>
        <div class="panel">
          <div class="coverage-grid">
            <div class="coverage-card">
              <span class="cov-title">Hóa đơn mua vào</span>
              <span class="cov-status ${l.purchase_xml?`ok`:`empty`}">${l.purchase_xml?`${l.purchase_xml} tệp XML`:`Chưa nạp`}</span>
            </div>
            <div class="coverage-card">
              <span class="cov-title">Hóa đơn bán ra</span>
              <span class="cov-status ${l.sales_xml?`ok`:`empty`}">${l.sales_xml?`${l.sales_xml} tệp XML`:`0 tệp`}</span>
            </div>
            <div class="coverage-card">
              <span class="cov-title">Sao kê ngân hàng</span>
              <span class="cov-status ${l.bank?`ok`:`empty`}">${l.bank?`${l.bank} tệp`:`Chưa nạp`}</span>
            </div>
            <div class="coverage-card">
              <span class="cov-title">Bảng kê cổng thuế</span>
              <span class="cov-status ${l.portal_list?`ok`:`empty`}">${l.portal_list?`Đã nạp`:`Chưa nạp`}</span>
            </div>
          </div>
        </div>

        <h2 class="section" style="margin-top:20px">Hạn nộp tờ khai</h2>
        ${D([`Kỳ`,`Hạn nộp`,`Tình trạng`],(o?.calendar||[]).slice(0,4).map(e=>`<tr>
          <td><strong>${t(e.period)}</strong></td>
          <td>${a(e.due)}</td>
          <td>${t(e.status)}</td>
        </tr>`),`Chưa có lịch thuế trong kỳ.`)}
      </div>
    </div>
`,se(e(`#fresh`)),le(e(`#watch`),o),e(`#run`).onclick=async()=>{let t=e(`#run`),n=e(`#analysis-stage`),r=e(`#run-msg`);r&&(r.innerHTML=``),await K({triggerBtn:t,stageEl:n,title:`Đang phân tích dữ liệu hóa đơn và sao kê kỳ thuế`,onSuccess:async()=>{Be()},onError:(e,t)=>{t&&t.isConnected?t.innerHTML=C(`error`,`Phân tích không chạy được`,e.message):r&&r.isConnected&&(r.innerHTML=C(`error`,`Phân tích không chạy được`,e.message))}})}}function He(e){return e?t(e).replace(/Lỗi:\s*([A-Z0-9_,\s]+)/g,(e,t)=>`<div class="tech-err-row"><span class="tech-err-label">Mã lỗi:</span> ${t.split(`,`).map(e=>e.trim()).filter(Boolean).map(e=>`<span class="tech-err-pill" title="Mã lỗi kỹ thuật: ${e}">${e}</span>`).join(` `)}</div>`):``}function Ue(e){return e===`AT_RISK`?`<span class="rev-badge rev-badge-risk">Có nguy cơ</span>`:e===`REVIEW`?`<span class="rev-badge rev-badge-warn">Cần xem xét</span>`:e===`OPPORTUNITY`?`<span class="rev-badge rev-badge-opp">Bỏ sót</span>`:S(e)}function We(e,t){return`<div class="rev-money-cell ${t===`AT_RISK`?`val-risk`:t===`REVIEW`?`val-warn`:`val-opp`}">
    ${r(e)}
  </div>`}function Ge(e,t){return e.length?`<div class="table-wrap review-table-wrap">
    <table class="cds--data-table cds--data-table--md review-data-table">
      <thead>
        <tr>
          <th class="pickcell" style="width:40px">
            <input type="checkbox" id="pick-all" aria-label="Chọn tất cả trên trang" title="Chọn tất cả các việc trên trang hiện tại">
          </th>
          <th style="width:120px"><div class="cds--table-header-label">Mức độ</div></th>
          <th style="width:160px"><div class="cds--table-header-label">Chứng từ</div></th>
          <th style="min-width:180px"><div class="cds--table-header-label">Đối tác / MST</div></th>
          <th><div class="cds--table-header-label">Vấn đề phát hiện</div></th>
          <th class="num" style="width:145px"><div class="cds--table-header-label">Số tiền</div></th>
          <th style="width:32px"></th>
        </tr>
      </thead>
      <tbody>
        ${e.map(t).join(``)}
      </tbody>
    </table>
  </div>`:`<div class="review-empty-state">
      <h3 class="empty-title">Không có việc nào khớp bộ lọc</h3>
      <p class="empty-desc">Điều chỉnh từ khóa tìm kiếm, nhóm vấn đề hoặc đặt lại bộ lọc để xem toàn bộ danh sách.</p>
      <button type="button" class="cds--btn cds--btn--secondary cds--btn--sm" id="empty-reset-btn">Đặt lại bộ lọc</button>
    </div>`}async function Ke(){let r=await R();if(!r){P().innerHTML=`<h1 class="page">Việc cần xử lý</h1>${C(`info`,`Chưa phân tích`,`Chạy phân tích ở trang Tổng quan để kiểm tra rủi ro.`)}`;return}if(r.meta.schema_version!==2){P().innerHTML=`<h1 class="page">Việc cần xử lý</h1>${C(`warning`,`Báo cáo phiên bản cũ`,`Về Tổng quan và chạy lại phân tích trước khi lưu quyết định.`)}<a href="#/">Về Tổng quan</a>`;return}let i=F().get(`loc`)||`all`,s=`agent3.review.${N.ws}.${N.platform?.profile_revision}`,c={};try{c=JSON.parse(sessionStorage.getItem(s)||`{}`)}catch{}let l=await g();ee(r);let d=[...new Set(r.invoices.filter(e=>e.issue_date).map(e=>e.issue_date.slice(0,7)))].sort(),f=r.items.filter(e=>i===`all`||e.status===i),p=e=>r.items.filter(t=>t.status===e).length;P().innerHTML=`
    ${M(`Việc cần xử lý`,`Việc cần xử lý`,`RÀ SOÁT & ĐỐI CHIẾU THUẾ`)}

    <div id="fresh"></div>
    <div id="ai-tools"></div>

    <div class="toolbar smart-toolbar">
      <div class="status-filter-pills segmented-pills">
        ${[[`all`,`Tất cả`,r.items.length,`pill-all`],[`AT_RISK`,`Có nguy cơ`,p(`AT_RISK`),`pill-risk`],[`REVIEW`,`Cần xem xét`,p(`REVIEW`),`pill-warn`],[`OPPORTUNITY`,`Bỏ sót`,p(`OPPORTUNITY`),`pill-opp`]].map(([e,n,r,a])=>`<a class="${e===i?`active `+a:``}" href="#/viec?loc=${e}">
          <span class="tab-label">${t(n)}</span>
          <span class="pill-count">${r}</span>
        </a>`).join(``)}
      </div>

      <div class="filter-field filter-field-search" style="flex: 2 1 240px">
        <span class="filter-label">Tìm kiếm</span>
        <div class="search-input-wrap">
          <input class="cds--text-input filter-input search-input" id="q" style="padding-left:12px !important" placeholder="Số hóa đơn, đối tác, lý do..." aria-label="Tìm việc">
          <button type="button" class="search-clear-btn" id="q-clear" title="Xóa tìm kiếm" hidden aria-label="Xóa tìm kiếm">✕</button>
        </div>
      </div>

      <div class="filter-field filter-field-group">
        <span class="filter-label">Nhóm vấn đề</span>
        <select class="cds--select-input filter-select" id="group" aria-label="Lọc theo vấn đề"></select>
      </div>

      <div class="filter-field filter-field-month">
        <span class="filter-label">Kỳ phát sinh</span>
        <select class="cds--select-input filter-select" id="month" aria-label="Lọc theo tháng">
          <option value="">Mọi tháng</option>
          ${d.map(e=>`<option value="${e}">Tháng ${e.slice(5)}/${e.slice(0,4)}</option>`).join(``)}
        </select>
      </div>

      <div class="toolbar-actions">
        <span class="muted small count-tag" id="shown" role="status"></span>
        ${T(`Đặt lại`,`ghost`,`id="reset-filters" class="cds--btn--sm btn-reset"`)}
        <a class="cds--btn cds--btn--ghost cds--btn--sm btn-export" href="/api/workspaces/${t(N.ws)}/export/viec-can-xu-ly.xlsx">Xuất Excel</a>
      </div>
    </div>

    <div class="bulk floating-bulk-dock" id="bulk" hidden>
      <div class="bulk-dock-inner">
        <div class="bulk-badge-group">
          <span class="bulk-count-pill" id="bulk-n">Đã chọn 0 việc</span>
        </div>
        <div class="bulk-controls">
          <select class="cds--select-input bulk-select" id="bulk-action" aria-label="Quyết định hàng loạt"></select>
          <input class="cds--text-input bulk-input" id="bulk-ev" aria-label="Chứng từ hoặc lý do chung" placeholder="Chứng từ hoặc lý do chung...">
          <input class="cds--text-input bulk-input bulk-by" id="bulk-by" aria-label="Người duyệt" placeholder="Người duyệt" value="${t(o.get(`agent3.reviewer`)||``)}">
          <button type="button" class="cds--btn cds--btn--primary bulk-confirm-btn" id="bulk-go">Ghi cho các việc đã chọn</button>
        </div>
      </div>
    </div>

    <div id="list"></div>`;let m=c.shown||50,h=F().get(`nhom`)||c.code||``,v=new Map(r.items.map((e,t)=>[e,t])),y=e=>r.transactions.find(t=>e.txn_ids?.includes(t.txn_id)),b=e=>{let t=z(e.invoice_keys[0]),n=y(e);return`${B(t)} ${t?.seller_name||n?.counterparty_name||``} ${e.title} ${e.detail}`.toLowerCase()},x=e=>(z(e.invoice_keys[0])?.issue_date||y(e)?.booked||``).slice(0,7),S={};f.forEach(e=>{let t=S[e.code]||={title:e.title,status:e.status,n:0,amount:0};t.n+=1,t.amount+=Number(e.amount||0)});let w=()=>{let n=Object.entries(S).sort((e,t)=>t[1].amount-e[1].amount||t[1].n-e[1].n);e(`#group`).innerHTML=`<option value="">Mọi vấn đề</option>${n.map(([e,n])=>`<option value="${t(e)}" ${e===h?`selected`:``}>${t(n.title)} (${n.n})</option>`).join(``)}`},E=new Set,D=e=>{let n=z(e.invoice_keys[0]),r=y(e),i=v.get(e),o=(e.status===`AT_RISK`||e.status===`REVIEW`)&&e.invoice_keys.length,s=E.has(e.finding_id);return`<tr class="clickable review-row ${e.status===`AT_RISK`?`row-risk`:e.status===`REVIEW`?`row-warn`:`row-opp`} ${s?`row-checked`:``}" tabindex="0" data-item="${i}">
      <td class="pickcell">
        ${o?`<input type="checkbox" class="bulk-pick" data-idx="${i}" aria-label="Chọn" ${s?`checked`:``}>`:``}
      </td>
      <td class="status-cell">${Ue(e.status)}</td>
      <td class="invoice-cell">
        <div class="inv-code-pill" title="${t(e.invoice_keys[0]||``)}">
          <span class="inv-badge-text">${t(B(n)||e.invoice_keys[0]||(r?`Giao dịch NH`:`Chưa gắn mã`))}</span>
        </div>
        <div class="inv-date-sub">${a(n?.issue_date||r?.booked)||`—`}</div>
      </td>
      <td class="seller-cell">
        <div class="seller-name" title="${t(n?.seller_name||r?.counterparty_name||``)}">
          ${t(n?.seller_name||r?.counterparty_name||`Đối tác chưa xác định`)}
        </div>
        <div class="seller-tax-sub mono">
          ${n?`MST <code>${t(n.seller_tax_id||`—`)}</code>`:`<span class="bank-tag">${t(r?.source||`Sao kê`)}</span>`}
        </div>
      </td>
      <td class="issue-cell">
        <div class="issue-title">${t(e.title)}</div>
        <div class="issue-detail-wrap">${He(e.detail)}</div>
      </td>
      <td class="amount-cell num">
        ${We(e.amount,e.status)}
        ${e.code.startsWith(`R14`)?`<div class="muted small">Tiền giao dịch</div>`:``}
      </td>
      <td class="action-cell">
        <span class="row-arrow" aria-hidden="true">→</span>
      </td>
    </tr>`},O=[],k=()=>{let n=O.filter(e=>e.checked).map(e=>r.items[Number(e.dataset.idx)]);if(e(`#bulk`).hidden=!n.length,!n.length)return;e(`#bulk-n`).textContent=`Đã chọn ${n.length} việc`;let i=n.map(Y).reduce((e,t)=>e.filter(([e])=>t.some(([t])=>t===e)));e(`#bulk-action`).innerHTML=i.map(([e,n])=>`<option value="${e}">${t(n)}</option>`).join(``)},A=()=>{let t=e(`#q`).value.trim().toLowerCase(),n=e(`#month`).value,a=f.filter(e=>(!h||e.code===h)&&(!t||b(e).includes(t))&&(!n||x(e)===n));Re=a,J=()=>{try{sessionStorage.setItem(s,JSON.stringify({q:e(`#q`).value,month:e(`#month`).value,code:h,shown:m,scroll:window.scrollY,focus:ze}))}catch{}},e(`#shown`).textContent=t||n||h?`${a.length} việc khớp`:`${a.length} việc`;let o=a.length>m?`
      <div class="pagination-bar">
        <div class="pagination-info">
          <span class="muted small">Đang hiển thị <strong>${Math.min(m,a.length)}</strong> / <strong>${a.length}</strong> việc</span>
        </div>
        <div class="pagination-buttons">
          ${T(`Hiện thêm ${Math.min(50,a.length-m)} việc`,`ghost`,`id="more" class="btn-load-more"`)}
          ${T(`Hiện tất cả`,`ghost`,`id="all" class="btn-load-all"`)}
        </div>
      </div>
    `:``;e(`#list`).innerHTML=Ge(a.slice(0,m),D)+o;let c=e(`#pick-all`);O=[...P().querySelectorAll(`.bulk-pick`)],c&&(c.checked=O.length>0&&O.every(e=>e.checked),c.indeterminate=O.some(e=>e.checked)&&!c.checked,c.onchange=()=>{O.forEach(e=>{e.checked=c.checked;let t=r.items[Number(e.dataset.idx)].finding_id;c.checked?E.add(t):E.delete(t);let n=e.closest(`tr`);n&&n.classList.toggle(`row-checked`,c.checked)}),k()}),O.forEach(e=>{e.onclick=e=>e.stopPropagation(),e.onchange=()=>{let t=r.items[Number(e.dataset.idx)].finding_id;e.checked?E.add(t):E.delete(t);let n=e.closest(`tr`);if(n&&n.classList.toggle(`row-checked`,e.checked),c){let e=O.length>0&&O.every(e=>e.checked);c.checked=e,c.indeterminate=O.some(e=>e.checked)&&!e}k()}}),P().querySelectorAll(`[data-item]`).forEach(e=>{e.onclick=()=>Ye(r.items[Number(e.dataset.item)],Number(e.dataset.item)),e.onkeydown=t=>{t.target===e&&[`Enter`,` `].includes(t.key)&&(t.preventDefault(),e.click())}}),e(`#more`)&&(e(`#more`).onclick=()=>{m+=50,A()}),e(`#all`)&&(e(`#all`).onclick=()=>{m=a.length,A()});let l=e(`#empty-reset-btn`);l&&(l.onclick=()=>{i===`all`?(e(`#q`).value=``,e(`#month`).value=``,h=``,e(`#group`).value=``,m=50,A()):location.hash=`#/viec`});let u=e(`#q`),d=e(`#q-clear`);u&&d&&(d.hidden=!u.value,u.oninput=()=>{d.hidden=!u.value,m=50,A()},d.onclick=()=>{u.value=``,d.hidden=!0,m=50,A()}),k()};e(`#group`).onchange=()=>{h=e(`#group`).value,m=50,A()},e(`#month`).onchange=()=>{m=50,A()},e(`#bulk-go`).onclick=async()=>{let t=O.filter(e=>e.checked).map(e=>r.items[Number(e.dataset.idx)]),i={invoice_keys:[...new Set(t.map(e=>e.invoice_keys[0]))],finding_ids:t.map(e=>e.finding_id),action:e(`#bulk-action`).value,evidence:e(`#bulk-ev`).value.trim(),by:e(`#bulk-by`).value.trim()};if(!i.action||!i.evidence||!i.by){G(`Cần quyết định, chứng từ hoặc lý do và người duyệt`,``,`error`);return}o.set(`agent3.reviewer`,i.by);let a=e(`#bulk-go`);a.disabled=!0;try{J?.();let e=await _(`/api/workspaces/${N.ws}/decisions/bulk`,i,l);if(e.report_pending){G(`Quyết định đã lưu; cần chạy lại báo cáo`,e.message,`warning`),a.disabled=!1;return}G(`Đã ghi ${e.decisions} quyết định`,`Thuế có nguy cơ còn ${n(e.totals.at_risk_vat)}`),window.sonStamp?.(i.by),Be()}catch(e){a.isConnected&&(G(`Không ghi được`,e.message,`error`),a.disabled=!1)}},e(`#reset-filters`).onclick=()=>{i===`all`?(e(`#q`).value=``,e(`#month`).value=``,h=``,e(`#group`).value=``,m=50,A()):location.hash=`#/viec`},e(`#q`).value=c.q||``,e(`#month`).value=c.month||``,w(),A(),u(()=>{P().querySelector(`#shown`)&&J?.()}),requestAnimationFrame(()=>{if(P().querySelector(`#shown`)&&!document.querySelector(`.drawer`)){window.scrollTo(0,c.scroll||0);let e=r.items.findIndex(e=>q(e)===c.focus);P().querySelector(`[data-item="${e}"]`)?.focus({preventScroll:!0})}}),Ce(e(`#ai-tools`)).catch(()=>{}),se(e(`#fresh`));let j=null;try{j=sessionStorage.getItem(`agent3.openNext`),sessionStorage.removeItem(`agent3.openNext`)}catch{}if(j){let e=r.items.findIndex(e=>q(e)===j);e>=0&&Ye(r.items[e],e)}let I=F().get(`open`);if(I&&!j){let e=r.items.findIndex(e=>e.code===I||q(e)===I||e.invoice_keys.includes(I));e>=0&&Ye(r.items[e],e)}}function Y(e){if(e.code.startsWith(`R14`))return[[`CONFIRMED_NON_REVENUE`,`Đã kiểm tra: không phải khoản thu bán hàng`],[`SALES_EVIDENCE_ATTACHED`,`Đã bổ sung hóa đơn bán ra liên quan`]];let t=/^R0[123]_/.test(e.code),n=[];return t&&n.push([`PAYMENT_EVIDENCE_ATTACHED`,`Đã có chứng từ thanh toán không dùng tiền mặt`]),e.status===`REVIEW`&&n.push([`CONFIRMED_OK`,`Đã kiểm tra, không có vấn đề (ghi rõ căn cứ kiểm tra)`]),n.push([`NOT_CLAIMED`,`Không kê khai khấu trừ hóa đơn này`]),n}var qe=e=>/^R0[123]_/.test(e.code)||e.status===`REVIEW`?``:`Với loại rủi ro này, chứng từ thanh toán không khắc phục được; cần hóa đơn thay thế hoặc điều chỉnh từ người bán, hoặc không kê khai.`;async function Je(e,r){try{let i=(await p(`/api/workspaces/${N.ws}/exposure`))[r];if(!i)return;e.innerHTML=`<div class="panel exposure-panel">
      <h3 class="exposure-title" style="margin-top:0">Ước tính rủi ro & Phương án xử lý</h3>
      <p class="exposure-note">${t(i.note)}</p>
      ${i.overdue===!0?`<div class="exposure-table-wrap"><table class="mini exposure-table" style="width:100%;font-size:13px">
            <tr><td>Thuế theo giả định</td><td class="num"><strong>${n(i.amount)}</strong></td><td class="muted small">Chưa xác nhận đã khấu trừ hoặc thực tế thiếu thuế</td></tr>
            <tr><td>Chậm nộp theo giả định</td><td class="num">${n(i.interest)||`Chưa đủ dữ liệu`}</td><td class="muted small">${i.days_late} ngày sau hạn lịch</td></tr>
            <tr><td>Phạt theo giả định</td><td class="num">${n(i.penalty)||`Chưa đủ dữ liệu`}</td><td class="muted small">Không phải kết luận xử phạt</td></tr>
          </table></div>`:`<p class="exposure-due-note">${i.due?`Hạn theo lịch: ${a(i.due)}; chưa quá hạn lịch.`:`Chưa xác định được hạn; không tính số ngày chậm.`}</p>`}
      <div class="cite exposure-cite" style="margin-top:8px">${i.basis.filter(Boolean).map(t).join(`<br>`)}</div>
    </div>`}catch{e.innerHTML=``}}function Ye(r,i){ze=q(r);let s=z(r.invoice_keys[0]),c=N.report.matches.find(e=>e.invoice_keys.includes(r.invoice_keys[0])),l=(r.status===`AT_RISK`||r.status===`REVIEW`)&&(r.invoice_keys.length>0||r.txn_ids?.length>0),u=r.code.startsWith(`R14`),d=new Set,f=N.report.transactions.find(e=>r.txn_ids?.includes(e.txn_id)),m=g();m.catch(()=>{}),e(`#modal-root`).innerHTML=`<aside class="drawer" role="dialog" aria-labelledby="drawer-title">
    <div class="drawer-top-bar">
      <div class="drawer-header-content">
        <div class="drawer-subhead">
          ${Ue(r.status)}
          <span class="rule-code-badge">${t(r.code)}</span>
          ${r.amount?`<span class="amount-badge">${u?`Số tiền GD`:`Thuế GTGT`}: <strong>${n(r.amount)}</strong></span>`:``}
        </div>
        <h2 id="drawer-title">${t(r.title)}</h2>
      </div>
      <button class="cds--btn cds--btn--ghost cds--btn--sm close drawer-close-btn" id="close" type="button" aria-label="Đóng ngăn chi tiết">Đóng</button>
    </div>

    <div id="plain" style="margin-top:1rem"></div>

    <div class="dossier-grid">
      <div class="dossier-card">
        <h3 class="dossier-card-title">${u?`Thông tin giao dịch`:`Hóa đơn XML`}</h3>
        ${u&&f?`<dl class="kv"><dt>Ngày</dt><dd>${a(f.booked)}</dd><dt>Số tiền</dt><dd><strong>${n(f.amount)}</strong></dd><dt>Đối tác</dt><dd>${t(f.counterparty_name)}</dd><dt>Nội dung</dt><dd>${t(f.description)}</dd><dt>Nguồn</dt><dd class="mono small">${t(f.source)}</dd></dl>`:``}
        <dl class="kv" ${u?`hidden`:``}>
          <dt>Số hóa đơn</dt><dd><strong>${t(B(s)||r.invoice_keys[0])}</strong></dd>
          <dt>Đối tác</dt><dd><strong>${t(s?.seller_name||``)}</strong> <div class="muted small">MST: ${t(s?.seller_tax_id||``)}</div></dd>
          <dt>Ngày lập</dt><dd>${a(s?.issue_date)}</dd>
          <dt>Tổng thanh toán</dt><dd><strong>${n(s?.gross)}</strong></dd>
          <dt>Tiền thuế GTGT</dt><dd><strong style="color:var(--a3-primary);font-size:15px">${n(s?.vat)}</strong></dd>
          <dt>Tệp XML gốc</dt><dd class="mono small" style="word-break:break-all">${t(s?.file||``)}</dd>
        </dl>
      </div>

      <div class="dossier-card">
        <h3 class="dossier-card-title">Chứng từ Ngân hàng đối chiếu</h3>
        ${c?`
          <div class="match-badge ${c.status===`MATCHED`?`match-ok`:`match-warn`}">
            ${c.status===`MATCHED`?`Đã ghép chứng từ thanh toán`:`Khớp mơ hồ / Cần xem lại`}
          </div>
          <p class="small" style="margin:8px 0 12px">${t(c.note)}</p>
          ${f?`<dl class="kv"><dt>Ngày hạch toán</dt><dd>${a(f.booked)}</dd><dt>Số tiền TT</dt><dd><strong>${n(f.amount)}</strong></dd><dt>Nội dung CK</dt><dd>${t(f.description)}</dd></dl>`:``}
        `:`
          <div class="match-badge match-empty">Chưa ghép được chứng từ thanh toán</div>
          <p class="muted small" style="margin-top:8px">Hóa đơn từ ngưỡng quy định cần chứng từ thanh toán không dùng tiền mặt để đủ điều kiện khấu trừ thuế GTGT.</p>
        `}
      </div>
    </div>

    <div id="exposure"></div>
    <details class="decision-history-details"><summary>Lịch sử quyết định và bằng chứng</summary><div id="decision-history"></div></details>

    <h3 class="section">Chi tiết vấn đề & Khuyến nghị</h3>
    <div style="background:var(--cds-layer);padding:14px 16px;border-radius:8px;border:1px solid var(--cds-border-subtle);margin-bottom:14px">
      <p style="margin:0 0 8px;font-size:13.5px"><strong>Hiện tượng:</strong> ${t(r.detail)}</p>
      <p style="margin:0;font-size:13.5px;color:var(--a3-primary)"><strong>Khuyến nghị:</strong> ${t(r.action)}</p>
    </div>

    <h3 class="section">Căn cứ pháp lý</h3>
    <ul style="font-size:13px;line-height:1.6;margin:0 0 16px 20px;padding:0">
      ${r.basis.map(e=>`<li>${t(e)}</li>`).join(``)}
    </ul>

    ${l?`<h3 class="section">Phê duyệt & Quyết định xử lý</h3>
      <div id="suggest"></div>
      <form id="decide">
        <div class="form-grid">
          ${E({key:`action`,label:`Quyết định xử lý`,type:`choice`,required:!0,choices:Y(r),help:qe(r)},Y(r)[0][0])}
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
  </aside>`,te();let h=e(`#decision-history`);if(m.then(e=>{if(!h.isConnected)return;let n=e.events.filter(e=>e.finding_id===r.finding_id||r.invoice_keys.includes(e.invoice_key)||e.txn_ids?.some(e=>r.txn_ids?.includes(e)));h.innerHTML=D([`Thời điểm`,`Người duyệt`,`Quyết định`,`Bằng chứng`],n.map(e=>`<tr><td>${t(e.at)}${e.legacy?` (dữ liệu cũ)`:``}</td><td>${t(e.by)}</td><td>${t(e.action)}${e.supersedes?`<div class="muted small">Thay thế một quyết định trước; bản trước vẫn được giữ</div>`:``}</td><td>${t(e.evidence)}</td></tr>`),`Chưa có quyết định cho đối tượng này.`)}).catch(e=>{h.isConnected&&(h.innerHTML=C(`error`,`Không tải được lịch sử`,e.message))}),u){let r=N.report.invoices.filter(e=>e.role===`SALE`&&!e.duplicate_of),i=()=>{let a=e(`#sales-query`).value.trim().toLowerCase(),o=r.filter(e=>`${B(e)} ${e.buyer_name}`.toLowerCase().includes(a));e(`#sales-picks`).innerHTML=o.slice(0,50).map(e=>`<label><input type="checkbox" value="${t(e.key)}" ${d.has(e.key)?`checked`:``}> ${t(B(e))} — ${t(e.buyer_name)} — ${n(e.gross)}</label>`).join(``),e(`#sales-selected`).textContent=`Hiện tối đa 50/${o.length} hóa đơn; đã chọn ${d.size}. Tìm để thu hẹp kết quả.`,e(`#sales-picks`).onchange=e=>{e.target.matches(`input`)&&(e.target.checked?d.add(e.target.value):d.delete(e.target.value),i())}};e(`#sales-query`).oninput=i,i()}Number.isInteger(i)&&Se(e(`#plain`),i),r.status===`AT_RISK`&&Number.isInteger(i)&&Je(e(`#exposure`),i);let v=e(`#decide`);if(v){let n=e(`.drawer`);p(`/api/workspaces/${N.ws}/decisions/suggest?key=${encodeURIComponent(r.invoice_keys[0])}&code=${encodeURIComponent(r.code)}`).then(i=>{let a=i.suggestion;a&&n.isConnected&&Y(r).some(([e])=>e===a.action)&&(e(`#suggest`).innerHTML=`<div class="banner banner-info">
        <div><strong>Gợi ý từ quyết định trước</strong><div class="small">${t(a.because)}</div></div>
        <button type="button" class="cds--btn cds--btn--ghost cds--btn--sm" id="use-sugg">Điền theo gợi ý</button>
      </div>`,e(`#use-sugg`).onclick=()=>{v.querySelector(`[name=action]`).value=a.action,v.querySelector(`[name=evidence]`).value=``,v.querySelector(`[name=evidence]`).placeholder=`Lần trước: ${a.evidence}`,v.querySelector(`[name=by]`).value||(v.querySelector(`[name=by]`).value=a.by),v.querySelector(`[name=evidence]`).focus()})}).catch(()=>{}),v.onsubmit=async t=>{t.preventDefault();let n=Object.fromEntries(new FormData(v).entries());o.set(`agent3.reviewer`,n.by);let a=t.submitter&&t.submitter.dataset.next,s=Re.filter(e=>(e.status===`AT_RISK`||e.status===`REVIEW`)&&q(e)!==q(r)&&!e.invoice_keys.includes(r.invoice_keys[0])),c=s[s.indexOf(s.find(e=>N.report.items.indexOf(e)>i))]||s[0];e(`#dmsg`).innerHTML=`<span class="muted">Đang lưu quyết định...</span>`;let l=e(`#dmsg`),f=[...v.querySelectorAll(`button[type="submit"]`)];f.forEach(e=>{e.disabled=!0});try{J?.();let e=await _(`/api/workspaces/${N.ws}/decisions`,{...n,invoice_key:r.invoice_keys[0],finding_id:r.finding_id,invoice_keys:u?[...d]:void 0},await m);if(e.report_pending){l.innerHTML=C(`warning`,`Quyết định đã lưu; cần chạy lại báo cáo`,e.message),f.forEach(e=>{e.disabled=!1});return}if(G(`Đã lưu quyết định`,`Thuế có nguy cơ còn ${Number(e.totals.at_risk_vat).toLocaleString(`vi-VN`)} đ`),window.sonStamp?.(n.by),a&&c)try{sessionStorage.setItem(`agent3.openNext`,q(c))}catch{}W(),Be()}catch(e){v.isConnected&&(l.innerHTML=C(`error`,`Không lưu được`,e.message),f.forEach(e=>{e.disabled=!1}))}}}}var Xe=()=>window.dispatchEvent(new Event(`hashchange`));function Ze(r,i,o){let s=i.matchedMap.get(r.key),c=s?o.transactions.find(e=>s.txn_ids.includes(e.txn_id)):null,l=(i.riskByInvoice.get(r.key)||[]).filter(e=>e.status!==`INFO`),u=r.role===`SALE`?r.buyer_name||`Khách hàng`:r.seller_name||`Nhà cung cấp`,d=r.role===`SALE`?r.buyer_tax_id||`—`:r.seller_tax_id||`—`;e(`#modal-root`).innerHTML=`<aside class="drawer" role="dialog" aria-labelledby="inv-drawer-title">
    <div class="drawer-top-bar">
      <div class="drawer-header-content">
        <div class="drawer-subhead">
          <span class="role-badge ${r.role===`SALE`?`sale`:`purchase`}">${r.role===`SALE`?`Hóa đơn bán ra`:`Hóa đơn mua vào`}</span>
          ${r.duplicate_of?`<span class="dup-pill">Bản trùng XML</span>`:``}
          <span class="amount-badge">Tổng TT: <strong>${n(r.gross)}</strong></span>
        </div>
        <h2 id="inv-drawer-title">Hóa đơn ${t(B(r))}</h2>
      </div>
      <button class="cds--btn cds--btn--ghost cds--btn--sm close drawer-close-btn" id="close" type="button" aria-label="Đóng ngăn chi tiết">Đóng</button>
    </div>

    <div class="dossier-grid" style="margin-top:16px">
      <div class="dossier-card">
        <h3 class="dossier-card-title">Thông tin chứng từ XML</h3>
        <dl class="kv">
          <dt>Ký hiệu / Số</dt><dd><strong>${t(B(r))}</strong></dd>
          <dt>Ngày lập</dt><dd>${a(r.issue_date)||`—`}</dd>
          <dt>${r.role===`SALE`?`Người mua`:`Người bán`}</dt><dd><strong>${t(u)}</strong><div class="muted small">MST: ${t(d)}</div></dd>
          <dt>Tổng thanh toán</dt><dd><strong>${n(r.gross)}</strong></dd>
          <dt>Thuế GTGT</dt><dd><strong style="color:var(--a3-primary)">${n(r.vat)}</strong></dd>
          <dt>Chữ ký số & XML</dt><dd>${r.guard_errors?.length?`Lỗi XML (${r.guard_errors.join(`, `)})`:r.signed?`Chữ ký số hợp lệ`:`Chưa ký số`}</dd>
          <dt>Tệp gốc</dt><dd class="mono small" style="word-break:break-all">${t(r.file||`—`)}</dd>
        </dl>
      </div>

      <div class="dossier-card">
        <h3 class="dossier-card-title">Đối chiếu thanh toán ngân hàng</h3>
        ${r.role===`SALE`?`<p class="muted small">Hóa đơn bán ra không bắt buộc ghép ủy nhiệm chi khấu trừ đầu vào.</p>`:s?`
          <div class="match-badge ${s.status===`MATCHED`?`match-ok`:`match-warn`}">
            ${s.status===`MATCHED`?`Đã ghép giao dịch ngân hàng`:`Khớp mơ hồ / Cần kiểm tra`}
          </div>
          <p class="small" style="margin:8px 0 12px">${t(s.note||``)}</p>
          ${c?`<dl class="kv"><dt>Ngày hạch toán</dt><dd>${a(c.booked)}</dd><dt>Số tiền</dt><dd><strong>${n(c.amount)}</strong></dd><dt>Nội dung</dt><dd>${t(c.description||``)}</dd></dl>`:``}
        `:`
          <div class="match-badge match-empty">Chưa ghép giao dịch ngân hàng</div>
          <p class="muted small" style="margin-top:8px">Chưa tìm thấy giao dịch chi tiền khớp số tiền và tên nhà cung cấp trong sao kê đã nạp.</p>
        `}
      </div>
    </div>

    ${(r.descriptions||[]).length?`
      <h3 class="section">Nội dung hàng hóa / dịch vụ</h3>
      <ul style="font-size:13px;line-height:1.6;margin:0 0 16px 20px;padding:0">
        ${r.descriptions.slice(0,15).map(e=>`<li>${t(e)}</li>`).join(``)}
      </ul>
    `:``}

    <h3 class="section">Kết quả rà soát rủi ro (${l.length} vấn đề)</h3>
    ${l.length?`
      <div style="display:grid;gap:10px;margin-bottom:16px">
        ${l.map(e=>`<div class="panel" style="margin:0">
          <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:6px">
            ${S(e.status)}
            <span class="mono small muted">${t(e.code)}</span>
          </div>
          <div style="font-weight:600;margin-bottom:4px">${t(e.title)}</div>
          <div class="muted small">${t(e.detail)}</div>
        </div>`).join(``)}
      </div>
      <div class="bar">
        <a class="cds--btn cds--btn--primary cds--btn--md" href="#/viec?open=${encodeURIComponent(r.key)}">Mở tại Việc cần xử lý để phê duyệt →</a>
      </div>
    `:`<p class="muted small">Hóa đơn này hiện không có cảnh báo rủi ro.</p>`}
  </aside>`,te()}async function Qe(){if(V())return;let r=await R();if(!r){P().innerHTML=`<h1 class="page">Hóa đơn</h1>${C(`info`,`Chưa phân tích`)}`;return}let o=ee(r),s=o.matchedMap,c=o.riskByInvoice,l=[...new Set(r.invoices.filter(e=>e.issue_date).map(e=>e.issue_date.slice(0,7)))].sort(),d=e=>o.invoiceBucket(e),f=`agent3.invoices.${N.ws}.${N.platform?.profile_revision}`,p={};try{p=JSON.parse(sessionStorage.getItem(f)||`{}`)}catch{}let m=p.page||0,h=p.tabFilter||`all`,g=o.purchaseInvs,_=o.saleInvs,v=o.purchaseGross,y=o.purchaseVat,b=o.saleGross,x=o.saleVat,w=o.atRiskInvoices,E=o.reviewInvoices,D=o.unpaidCount,O=o.duplicateInvs.length,k=r.invoices.filter(e=>!e.duplicate_of),A=k.filter(e=>e.signed).length,j=k.length>0?Math.round(A/k.length*100):100,F=o.scenarioWithReview;P().innerHTML=`
    ${M(`Hóa đơn`,`Hóa đơn`,`QUẢN LÝ CHỨNG TỪ`,`<span class="ctx-chip chip-count">${k.length.toLocaleString(`vi-VN`)} hóa đơn hợp lệ${O?` · ${O} bản trùng`:``}</span>`,`chung-tu`)}

    <div class="inv-balance-hub">
      <div class="hub-main-grid">
        <div class="hub-card hub-card-purchase">
          <div class="hub-card-header">
            <div class="hub-title-box">
              <span class="hub-role-label">HÓA ĐƠN MUA VÀO</span>
              <span class="hub-action-sub">Đã loại trừ ${O} bản trùng XML</span>
            </div>
            <span class="hub-count-tag count-purchase">${g.length.toLocaleString(`vi-VN`)} HĐ</span>
          </div>
          <div class="hub-money-body">
            <div class="hub-money-primary">
              <span class="hub-currency-label">Tổng thanh toán:</span>
              <span class="hub-amount font-num">${n(v)}</span>
            </div>
            <div class="hub-vat-pill vat-purchase">
              <span class="vat-pill-label">Tổng thuế GTGT mua vào:</span>
              <span class="vat-pill-val font-num"><strong>${n(y)}</strong></span>
            </div>
          </div>
        </div>

        <div class="hub-card hub-card-center">
          <div class="center-balance-head">
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span class="balance-title">PHÂN TÁCH THUẾ GTGT ĐẦU VÀO & CÂN ĐỐI</span>
              <a href="#/so-lieu" class="small" style="font-weight:600;text-decoration:none">Bảng tính thuế →</a>
            </div>
            <span class="balance-sub">Khớp 100% với trang Số liệu thuế GTGT</span>
          </div>

          <div class="a3-vat-breakdown">
            <div class="a3-vat-row"><span>Đầu vào chưa có cảnh báo:</span><strong class="font-num">${n(o.noAlertVat)}</strong></div>
            <div class="a3-vat-row"><span>Đầu vào chờ xem xét (${E} HĐ):</span><strong class="font-num">${n(o.reviewVat)}</strong></div>
            <div class="a3-vat-row"><span>Có nguy cơ / Không khai (${w} HĐ):</span><strong class="font-num" style="color:var(--a3-danger)">${n(Number(o.atRiskVat)+o.notClaimedVat)}</strong></div>
          </div>

          <div class="balance-result-box ${F<=0?`result-credit`:`result-payable`}">
            <div class="result-info">
              <div class="result-name">${F<=0?`Đầu vào vượt đầu ra (kể cả chờ duyệt):`:`Đầu ra vượt đầu vào (kể cả chờ duyệt):`}</div>
              <div class="result-value font-num">${n(Math.abs(F))}</div>
            </div>
          </div>
        </div>

        <div class="hub-card hub-card-sale">
          <div class="hub-card-header">
            <div class="hub-title-box">
              <span class="hub-role-label">HÓA ĐƠN BÁN RA</span>
              <span class="hub-action-sub">Phát sinh nghĩa vụ thuế đầu ra</span>
            </div>
            <span class="hub-count-tag count-sale">${_.length.toLocaleString(`vi-VN`)} HĐ</span>
          </div>
          <div class="hub-money-body">
            <div class="hub-money-primary">
              <span class="hub-currency-label">Tổng thanh toán:</span>
              <span class="hub-amount font-num">${n(b)}</span>
            </div>
            <div class="hub-vat-pill vat-sale">
              <span class="vat-pill-label">Tổng thuế GTGT bán ra:</span>
              <span class="vat-pill-val font-num"><strong>${n(x)}</strong></span>
            </div>
          </div>
        </div>
      </div>

      <div class="hub-footer-strip">
        <div class="strip-left">
          <span class="strip-label">Lọc nhanh rủi ro:</span>
          <button type="button" class="audit-badge audit-risk clickable-badge" data-quick-st="AT_RISK">
            <strong>${w.toLocaleString(`vi-VN`)}</strong> HĐ có nguy cơ (${n(o.atRiskVat)})
          </button>
          <button type="button" class="audit-badge audit-review clickable-badge" data-quick-st="REVIEW">
            <strong>${E.toLocaleString(`vi-VN`)}</strong> HĐ cần xem xét (${n(o.reviewVat)})
          </button>
          <button type="button" class="audit-badge audit-bank clickable-badge" data-quick-tab="UNPAID">
            <strong>${D.toLocaleString(`vi-VN`)}</strong> HĐ mua vào chưa ghép sao kê
          </button>
        </div>
        <div class="strip-right">
          <span class="audit-badge audit-signed">
            Chữ ký số hợp lệ: <strong>${j}%</strong> (${A.toLocaleString(`vi-VN`)}/${k.length.toLocaleString(`vi-VN`)})
          </span>
        </div>
      </div>
    </div>

    <div class="inv-segmented-pills">
      ${[[`all`,`Tất cả`,r.invoices.length,`pill-tab-all`],[`PURCHASE`,`Mua vào`,g.length,`pill-tab-purchase`],[`SALE`,`Bán ra`,_.length,`pill-tab-sale`],[`RISK`,`Có cảnh báo`,w+E,`pill-tab-risk`],[`UNPAID`,`Chưa ghép sao kê`,D,`pill-tab-bank`]].map(([e,n,r,i])=>`<button type="button" class="inv-filter-pill ${i} ${e===h?`active`:``}" data-tab="${e}">
        <span class="pill-name">${t(n)}</span>
        <span class="pill-count">${r.toLocaleString(`vi-VN`)}</span>
      </button>`).join(``)}
    </div>

    <div class="inv-toolbar">
      <div class="inv-search-wrap">
        <input class="cds--text-input inv-search-input" id="iq" style="padding-left:12px !important" placeholder="Tìm theo số hóa đơn, đối tác, MST hoặc nội dung hàng hóa..." aria-label="Tìm hóa đơn">
        <button type="button" class="inv-search-clear" id="iq-clear" title="Xóa tìm kiếm" hidden aria-label="Xóa tìm kiếm">✕</button>
      </div>

      <select class="cds--select-input inv-filter-select" id="st" aria-label="Tình trạng">
        <option value="">Mọi tình trạng</option>
        <option value="AT_RISK">Có nguy cơ (${w})</option>
        <option value="REVIEW">Cần xem xét (${E})</option>
        <option value="OK">Không cảnh báo</option>
        <option value="UNPAID">Chưa ghép sao kê (${D})</option>
      </select>

      <select class="cds--select-input inv-filter-select" id="mon" aria-label="Tháng">
        <option value="">Mọi kỳ tháng</option>
        ${l.map(e=>`<option value="${e}">Tháng ${e.slice(5)}/${e.slice(0,4)}</option>`).join(``)}
      </select>

      ${T(`Đặt lại`,`ghost`,`id="reset-invoices" class="cds--btn--sm btn-inv-reset"`)}
      <a class="cds--btn cds--btn--ghost cds--btn--sm btn-inv-export" href="/api/workspaces/${t(N.ws)}/export/hoa-don.xlsx">
        <span>Xuất Excel</span>
      </a>
      <span class="muted small inv-counter" id="icount" role="status"></span>
    </div>

    <div id="ilist"></div>`;let I=p.sort||[`issue_date`,-1],L={issue_date:e=>e.issue_date||``,gross:e=>e.gross||`0`,vat:e=>e.vat||`0`,seller:e=>(e.role===`SALE`?e.buyer_name:e.seller_name)||``},z=e=>{if(e.role!==`PURCHASE`||e.duplicate_of)return!1;let t=s.get(e.key);return!t||t.status!==`MATCHED`},H=()=>{let l=e(`#st`).value,u=e(`#mon`).value,f=e(`#iq`).value.trim().toLowerCase(),p=r.invoices.filter(e=>!(h===`PURCHASE`&&(e.role!==`PURCHASE`||e.duplicate_of)||h===`SALE`&&(e.role!==`SALE`||e.duplicate_of)||h===`RISK`&&![`AT_RISK`,`REVIEW`].includes(d(e))||h===`UNPAID`&&!z(e)||u&&!(e.issue_date||``).startsWith(u)||l&&(l===`UNPAID`&&!z(e)||l!==`UNPAID`&&d(e)!==l)||f&&!`${B(e)} ${e.number} ${e.seller_name} ${e.seller_tax_id} ${e.buyer_name||``} ${(e.descriptions||[]).join(` `)}`.toLowerCase().includes(f))).sort((e,t)=>{let n=L[I[0]](e),r=L[I[0]](t);return([`gross`,`vat`].includes(I[0])?i(n,r):n>r?1:n<r?-1:0)*I[1]}),g=Math.max(1,Math.ceil(p.length/50));m=Math.min(m,g-1);let _=(e,n,r,i=``)=>`<th class="${r?`num `:``}${i} sortable" aria-sort="${I[0]===e?I[1]>0?`ascending`:`descending`:`none`}"><button type="button" class="sort-button" data-sort="${e}">${t(n)}${I[0]===e?I[1]>0?` ↑`:` ↓`:``}</button></th>`;e(`#icount`).textContent=`${p.length.toLocaleString(`vi-VN`)} hóa đơn`;let v=p.slice(m*50,m*50+50);e(`#ilist`).innerHTML=p.length?`<div class="table-wrap inv-table-wrap"><table class="cds--data-table cds--data-table--md inv-data-table">
      <thead>
        <tr>
          <th style="min-width:155px">Hóa đơn & Ký hiệu</th>
          ${_(`issue_date`,`Ngày lập`,!1,`th-date`)}
          ${_(`seller`,`Đối tác / MST`,!1,`th-partner`)}
          ${_(`gross`,`Tổng thanh toán`,!0,`th-gross`)}
          ${_(`vat`,`Thuế GTGT`,!0,`th-vat`)}
          <th style="min-width:105px">Toàn vẹn XML</th>
          <th style="min-width:110px">Sao kê NH</th>
          <th style="min-width:140px">Trạng thái rà soát</th>
        </tr>
      </thead>
      <tbody>
        ${v.map((e,r)=>{let i=s.get(e.key),o=(c.get(e.key)||[]).filter(e=>e.status!==`INFO`),l=d(e),u=e.guard_errors.length?`<span class="integrity-badge badge-err">Lỗi XML (${e.guard_errors.length})</span>`:e.signed?`<span class="integrity-badge badge-ok">Hợp lệ</span>`:`<span class="integrity-badge badge-none">Không ký</span>`,f=e.role===`SALE`?`<span class="muted small">—</span>`:i?i.status===`MATCHED`?`<span class="pay-badge pay-ok">Đã ghép</span>`:`<span class="pay-badge pay-ambig">Mơ hồ</span>`:`<span class="pay-badge pay-none">Chưa ghép</span>`,p=e.role===`SALE`?e.buyer_name||`Khách hàng`:e.seller_name||`Nhà cung cấp`,m=e.role===`SALE`?e.buyer_tax_id||``:e.seller_tax_id||``;return`<tr class="clickable ${o.length?`row-has-risk`:``}" tabindex="0" data-inv-idx="${r}" title="Bấm để xem chi tiết hóa đơn">
            <td>
              <div class="inv-code-pill ${e.role===`SALE`?`pill-sale`:`pill-purchase`}" title="${t(B(e))}">
                <span class="inv-code-text">${t(B(e))}</span>
                ${e.duplicate_of?`<span class="dup-pill">Trùng</span>`:``}
              </div>
              <div class="inv-role-sub">${e.role===`SALE`?`<span class="role-badge sale">Bán ra</span>`:`<span class="role-badge purchase">Mua vào</span>`}</div>
            </td>
            <td class="font-date">${a(e.issue_date)}</td>
            <td>
              <div class="partner-name" title="${t(p)}">${t(p)}</div>
              ${m?`<div class="partner-tax mono">MST <code>${t(m)}</code></div>`:``}
            </td>
            <td class="num font-num"><strong>${n(e.gross)}</strong></td>
            <td class="num font-num vat-cell"><span class="vat-amount">${n(e.vat)}</span></td>
            <td>${u}</td>
            <td>${f}</td>
            <td>
              <div class="chips">
                ${l===`NOT_CLAIMED`?S(`INFO`,`Không kê khai`):o.length?o.map(e=>S(e.status,e.title.length>34?`${e.title.slice(0,32)}…`:e.title)).join(``):`<span class="tag-ok-check">Không cảnh báo</span>`}
              </div>
            </td>
          </tr>`}).join(``)}
      </tbody>
    </table></div>
    <div class="bar pager">
      ${T(`Trang trước`,`ghost`,`id="prev" ${m===0?`disabled`:``}`)}
      <span class="small">Trang <strong>${m+1}</strong> / ${g} (${p.length.toLocaleString(`vi-VN`)} hóa đơn)</span>
      ${T(`Trang sau`,`ghost`,`id="next" ${m>=g-1?`disabled`:``}`)}
    </div>`:`<div class="empty invoice-empty">
        <div style="font-weight:600;font-size:15px;margin-bottom:4px">Không có hóa đơn nào khớp bộ lọc</div>
        <div class="muted small">Thử đặt lại bộ lọc hoặc điều chỉnh từ khóa tìm kiếm.</div>
      </div>`,e(`#prev`)&&(e(`#prev`).onclick=()=>{--m,H()}),e(`#next`)&&(e(`#next`).onclick=()=>{m+=1,H()}),P().querySelectorAll(`[data-inv-idx]`).forEach(e=>{let t=v[Number(e.dataset.invIdx)];e.onclick=()=>Ze(t,o,r),e.onkeydown=t=>{t.target===e&&[`Enter`,` `].includes(t.key)&&(t.preventDefault(),e.click())}}),P().querySelectorAll(`[data-sort]`).forEach(e=>{e.onclick=()=>{let t=e.dataset.sort;I=[t,I[0]===t?-I[1]:-1],H(),P().querySelector(`[data-sort="${t}"]`)?.focus({preventScroll:!0})}})};P().querySelectorAll(`.inv-filter-pill`).forEach(e=>{e.onclick=()=>{P().querySelectorAll(`.inv-filter-pill`).forEach(e=>e.classList.remove(`active`)),e.classList.add(`active`),h=e.dataset.tab,m=0,H()}}),P().querySelectorAll(`[data-quick-st]`).forEach(t=>{t.onclick=()=>{h=`all`,P().querySelectorAll(`.inv-filter-pill`).forEach(e=>e.classList.toggle(`active`,e.dataset.tab===`all`)),e(`#st`).value=t.dataset.quickSt,m=0,H()}}),P().querySelectorAll(`[data-quick-tab]`).forEach(t=>{t.onclick=()=>{h=t.dataset.quickTab,P().querySelectorAll(`.inv-filter-pill`).forEach(e=>e.classList.toggle(`active`,e.dataset.tab===h)),e(`#st`).value=``,m=0,H()}}),[`st`,`mon`].forEach(t=>{e(`#${t}`).onchange=()=>{m=0,H()}});let U=e(`#iq`),W=e(`#iq-clear`);U.oninput=()=>{W.hidden=!U.value,m=0,H()},W.onclick=()=>{U.value=``,W.hidden=!0,m=0,H()},e(`#reset-invoices`).onclick=()=>{h=`all`,P().querySelectorAll(`.inv-filter-pill`).forEach(e=>e.classList.toggle(`active`,e.dataset.tab===`all`)),[`st`,`mon`,`iq`].forEach(t=>{e(`#${t}`).value=``}),W.hidden=!0,m=0,H()},[`st`,`mon`,`iq`].forEach(t=>{e(`#${t}`).value=p[t]||``}),p.iq&&(W.hidden=!1),H(),u(()=>{if(P().querySelector(`#ilist`))try{sessionStorage.setItem(f,JSON.stringify({sort:I,page:m,tabFilter:h,scroll:window.scrollY,...Object.fromEntries([`st`,`mon`,`iq`].map(t=>[t,e(`#${t}`).value]))}))}catch{}}),requestAnimationFrame(()=>{P().querySelector(`#ilist`)&&window.scrollTo(0,p.scroll||0)})}async function $e(){if(V())return;let r=await R();if(!r){P().innerHTML=`<h1 class="page">Ngân hàng</h1>${C(`info`,`Chưa phân tích`)}`;return}let i=new Map(r.matches.flatMap(e=>e.txn_ids.map(t=>[t,e]))),o=[...new Set(r.transactions.filter(e=>e.booked).map(e=>e.booked.slice(0,7)))].sort(),s=0;P().innerHTML=`
    ${M(`Ngân hàng`,`Giao dịch ngân hàng`,`QUẢN LÝ CHỨNG TỪ`,``,`chung-tu`)}
    <div id="props"></div>

    <div class="toolbar inv-toolbar">
      <div class="inv-search-wrap">
        <input class="cds--text-input inv-search-input" id="bq" style="padding-left:14px !important" placeholder="Tìm theo đối ứng, số tài khoản, nội dung chuyển khoản, số hóa đơn..." aria-label="Tìm giao dịch ngân hàng">
        <button type="button" class="inv-search-clear" id="bq-clear" hidden title="Xóa tìm kiếm">✕</button>
      </div>

      <select class="cds--select-input inv-filter-select" id="bdir" aria-label="Chiều giao dịch">
        <option value="">Mọi chiều (Thu & Chi)</option>
        <option value="OUT">Chi ra (Thanh toán)</option>
        <option value="IN">Thu vào</option>
      </select>

      <select class="cds--select-input inv-filter-select" id="bmatch" aria-label="Trạng thái ghép hóa đơn">
        <option value="">Mọi trạng thái ghép</option>
        <option value="MATCHED">Đã ghép hóa đơn</option>
        <option value="AMBIGUOUS">Khớp mơ hồ</option>
        <option value="UNMATCHED">Chưa ghép</option>
      </select>

      <select class="cds--select-input inv-filter-select" id="bmon" aria-label="Tháng giao dịch">
        <option value="">Mọi tháng</option>
        ${o.map(e=>`<option value="${e}">Tháng ${e.slice(5)}/${e.slice(0,4)}</option>`).join(``)}
      </select>

      ${T(`Đặt lại`,`ghost`,`id="breset" class="cds--btn--sm btn-inv-reset"`)}
      <span class="inv-counter" id="bcount" role="status"></span>
    </div>

    <div id="blist"></div>`;let c=()=>{let o=e(`#bq`).value.trim().toLowerCase(),l=e(`#bdir`).value,u=e(`#bmatch`).value,d=e(`#bmon`).value,f=r.transactions.filter(e=>{if(l&&e.direction!==l||d&&!(e.booked||``).startsWith(d))return!1;let t=i.get(e.txn_id);if(u===`MATCHED`&&(!t||t.status!==`MATCHED`)||u===`AMBIGUOUS`&&(!t||t.status===`MATCHED`)||u===`UNMATCHED`&&t)return!1;if(o){let n=t?t.invoice_keys.map(e=>B(z(e))).join(` `):``;if(!`${e.counterparty_name||``} ${e.counterparty_account||``} ${e.description||``} ${e.amount||``} ${e.source||``} ${n}`.toLowerCase().includes(o))return!1}return!0}),p=Math.max(1,Math.ceil(f.length/50));s=Math.min(s,p-1),e(`#bcount`).textContent=`${f.length.toLocaleString(`vi-VN`)} / ${r.transactions.length.toLocaleString(`vi-VN`)} giao dịch`;let m=f.slice(s*50,s*50+50);e(`#blist`).innerHTML=D([`Ngày`,`Chiều`,{label:`Số tiền`,num:!0},`Đối ứng`,`Nội dung`,`Ghép với hóa đơn`,`Nguồn`],m.map(e=>{let r=i.get(e.txn_id);return`<tr><td>${a(e.booked)}</td><td>${e.direction===`OUT`?`Chi`:`Thu`}</td><td class="num"><strong>${n(e.amount)}</strong></td>
          <td>${t(e.counterparty_name||``)}<div class="muted small mono">${t(e.counterparty_account||``)}</div></td><td>${t(e.description)}</td>
          <td>${r?`${r.invoice_keys.map(e=>t(B(z(e)))).join(`, `)}<div class="muted small">${r.status===`MATCHED`?`Đã ghép`:`Mơ hồ`}</div>`:`<span class="muted small">Chưa ghép</span>`}</td><td class="muted small">${t(e.source)}</td></tr>`}),`Không có giao dịch ngân hàng nào khớp bộ lọc.`)+(f.length>50?`<div class="bar pager">
      ${T(`Trang trước`,`ghost`,`id="bprev" ${s===0?`disabled`:``}`)}
      <span class="small">Trang <strong>${s+1}</strong> / ${p} (${f.length.toLocaleString(`vi-VN`)} giao dịch)</span>
      ${T(`Trang sau`,`ghost`,`id="bnext" ${s>=p-1?`disabled`:``}`)}
    </div>`:``),e(`#bprev`)&&(e(`#bprev`).onclick=()=>{--s,c()}),e(`#bnext`)&&(e(`#bnext`).onclick=()=>{s+=1,c()})},l=e(`#bq`),u=e(`#bq-clear`);l.oninput=()=>{u.hidden=!l.value,s=0,c()},u.onclick=()=>{l.value=``,u.hidden=!0,s=0,c()},[`bdir`,`bmatch`,`bmon`].forEach(t=>{e(`#${t}`).onchange=()=>{s=0,c()}}),e(`#breset`).onclick=()=>{[`bq`,`bdir`,`bmatch`,`bmon`].forEach(t=>{e(`#${t}`).value=``}),u.hidden=!0,s=0,c()},c(),we(e(`#props`))}async function et(){if(V())return;let e=await R();P().innerHTML=`
    ${M(`Lịch thuế`,`Lịch thuế`,`TỔNG HỢP & HỒ SƠ THUẾ`,e?`<span class="ctx-chip chip-date">Tính tại ngày ${a(e.meta.as_of)}</span>`:``,`bao-cao`)}
    ${D([`Kỳ thuế`,`Hạn nộp`,`Tình trạng`,`Căn cứ pháp lý`],(e?.calendar||[]).map(e=>`<tr><td><strong>${t(e.period)}</strong></td><td>${a(e.due)}${e.moved_from?`<div class="muted small">Dời từ ${a(e.moved_from)} do ngày nghỉ</div>`:``}</td><td>${t(e.status)}${e.open_items?`<div><a href="#/viec" class="risk-text">còn ${e.open_items} việc chưa xử lý của kỳ này</a></div>`:``}${e.extension?`<div class="muted small">${t(e.extension)}</div>`:``}</td><td class="muted small">${t(e.basis)}</td></tr>`),`Chưa có dữ liệu.`)}`}async function tt(){let n=await p(`/api/law/status`),r=n.stats,i=F().get(`doc`);if(i){let e=await p(`/api/law/docs/${encodeURIComponent(i)}`);P().innerHTML=`<div class="bar">${T(`← Quay lại kho luật`,`ghost`,`data-go="#/luat"`)}</div><h1 class="page">${t(e.doc.doc_type)} ${t(e.doc.doc_num)}</h1>
      <p class="lead">${t(e.doc.title)}</p><dl class="kv"><dt>Ban hành</dt><dd>${a(e.doc.issue_date)}</dd><dt>Hiệu lực</dt><dd>${a(e.doc.eff_from)||`không ghi`}${e.doc.eff_to?` đến `+a(e.doc.eff_to):``}</dd>
      <dt>Tình trạng</dt><dd>${t(e.doc.status_name||`không ghi`)}</dd><dt>Nguồn</dt><dd><a href="${t(e.doc.url)}" target="_blank" rel="noopener">Cơ sở dữ liệu quốc gia về pháp luật</a></dd>
      <dt>Chuyên gia duyệt</dt><dd>${t(e.doc.review_status)}</dd><dt>Dùng để trả lời</dt><dd>${e.doc.indexed?`Có`:`Không (chỉ lưu để đối chiếu)`}</dd></dl>
      ${e.ended?C(`warning`,`Hết hiệu lực từ ${a(e.ended.eff_to)} theo ${e.ended.by_path||e.ended.by_doc_num}`,`${e.ended.path?e.ended.path+`. `:``}Căn cứ nguyên văn: "${e.ended.quote}"${e.ended.exception?` Ngoại lệ: ${e.ended.exception}`:``}`):``}
      ${e.validity_notes.length?`<div class="panel"><h3>Ghi chú hiệu lực cần chuyên gia xem</h3><ul>${e.validity_notes.map(e=>`<li>${t(e.kind===`PARTIAL`?`Hết hiệu lực một phần`:`Được nhắc là văn bản sửa đổi, vẫn giữ hiệu lực`)} theo ${t(e.by_doc_num)}: <span class="muted">${t(e.quote.slice(0,300))}</span></li>`).join(``)}</ul></div>`:``}
      ${e.provisions.length?e.provisions.map(e=>`<div class="law-prov l${e.level}">${t(e.text)}</div>`).join(``):C(`warning`,`Văn bản chưa có toàn văn trong kho`,`Trang nguồn chỉ có tệp đính kèm.`)}`;return}P().innerHTML=`
    ${M(`Kho luật`,`Kho luật thuế`,`TƯ VẤN & TRA CỨU LUẬT`,`<span class="ctx-chip chip-count">${r?r.documents:0} văn bản</span>`,`tu-van`)}
    <div class="kpis" style="margin-top:14px"><div class="kpi"><span class="label">Văn bản pháp luật</span><span class="value">${r?r.documents:0}</span><span class="sub">${r?`${r.in_force} còn hiệu lực`:``}</span></div>
    <div class="kpi"><span class="label">Điều khoản chi tiết</span><span class="value">${r?r.provisions.toLocaleString(`vi-VN`):0}</span><span class="sub">${r?`${r.chunks.toLocaleString(`vi-VN`)} đoạn chỉ mục`:``}</span></div>
    <div class="kpi"><span class="label">Đồng bộ gần nhất</span><span class="value" style="font-size:1.25rem">${r?.last_snapshot?.created_at?a(r.last_snapshot.created_at):`chưa có`}</span>
    <span class="sub">${n.job.running?`đang chạy: ${n.job.done} văn bản`:`Nguồn: vbpl.vn`}</span></div>
    <div class="kpi"><span class="label">Văn bản hết hiệu lực</span><span class="value">${r?r.ended_by_later_act??0:0}</span><span class="sub">theo điều khoản thay thế</span></div></div>
    <h2 class="section">Tra cứu điều khoản</h2><form id="lsearch" class="bar" style="align-items:flex-end"><div class="cds--form-item cds--text-input-wrapper" style="flex:1;min-width:16rem">
    <label class="cds--label" for="lq">Từ khóa hoặc nội dung</label><input class="cds--text-input" id="lq" placeholder="Ví dụ: thời hạn nộp hồ sơ khai thuế theo quý"></div>
    <div class="cds--form-item cds--text-input-wrapper"><label class="cds--label" for="lasof">Ngày áp dụng</label><input class="cds--text-input" id="lasof" type="date" value="${new Date().toISOString().slice(0,10)}"></div>
    ${T(`Tìm kiếm`,`primary`,`type="submit"`)}</form><div id="lres"></div>
    <h2 class="section">Danh mục văn bản</h2><div id="ldocs">${w(`Đang tải danh sách`)}</div><details class="law-management"><summary>Đồng bộ và lịch sử kho luật</summary><div class="bar">${T(n.job.running?`Đang đồng bộ`:`Đồng bộ kho luật`,`primary`,`id="sync" ${n.job.running?`disabled`:``}`)}${T(`Chỉ văn bản lõi`,`tertiary`,`id="sync-core" ${n.job.running?`disabled`:``}`)}
    <span>${n.job.error?C(`error`,`Lỗi đồng bộ`,n.job.error):``}</span></div>
    <div id="alerts"></div>
    <h2 class="section">Thay đổi gần đây</h2>${D([`Lần`,`Loại`,`Văn bản`,`Chi tiết`],(n.changes||[]).slice(0,15).map(e=>`<tr><td>${e.snapshot_id}</td><td>${t(e.kind)}</td><td>${t(e.doc_num||``)}</td><td>${t(e.detail)}</td></tr>`),`Chưa có thay đổi.`)}
</details>`;let o=async t=>{try{await m(`/api/law/sync${t}`),Xe()}catch(t){e(`#lres`).innerHTML=C(`error`,`Chưa đồng bộ được`,t.message)}};if(e(`#sync`).onclick=()=>o(``),e(`#sync-core`).onclick=()=>o(`?core_only=true`),De(e(`#alerts`)).catch(()=>{}),n.job.running){let e=setTimeout(()=>{F().get(`doc`)||Xe()},5e3);u(()=>clearTimeout(e))}e(`#lsearch`).onsubmit=async n=>{n.preventDefault();let r=e(`#lq`).value.trim();if(!r)return;let i=n.target.querySelector(`button[type=submit]`);i.disabled=!0;let o=new AbortController,s=setTimeout(()=>o.abort(),15e3);u(()=>o.abort()),e(`#lres`).innerHTML=w(`Đang tìm`);try{let n=await p(`/api/law/search?q=${encodeURIComponent(r)}&as_of=${e(`#lasof`).value}`,{signal:o.signal});e(`#lres`).innerHTML=n.length?n.map(e=>`<div class="panel"><h3><a href="#/luat?doc=${t(e.doc_id)}">${t(e.path)}</a></h3>
        <div class="muted small">${t(e.status||`không ghi tình trạng`)}, hiệu lực từ ${a(e.eff_from)||`không ghi`}</div><p>${t(e.text.slice(0,900))}${e.text.length>900?`...`:``}</p></div>`).join(``):`<div class="empty">Không tìm thấy điều khoản phù hợp tại ngày này.</div>`}catch(t){e(`#lres`)&&(e(`#lres`).innerHTML=C(`error`,`Không tìm được`,t.name===`AbortError`?`Tra cứu quá thời gian. Hãy thử từ khóa ngắn hơn.`:t.message))}finally{clearTimeout(s),i.isConnected&&(i.disabled=!1)}};try{let n=await p(`/api/law/docs`),r=5,i=()=>{e(`#ldocs`).innerHTML=D([`Văn bản`,`Ban hành`,`Hiệu lực`,`Tình trạng`,{label:`Điều khoản`,num:!0}],n.slice(0,r).map(e=>`<tr class="clickable" data-go="#/luat?doc=${t(e.doc_id)}">
      <td><span class="cell-title">${t(e.doc_type)} ${t(e.doc_num)}</span><div class="muted small">${t((e.title||``).slice(0,140))}</div></td><td>${a(e.issue_date)}</td><td>${a(e.eff_from)}</td>
      <td>${e.ended_on?`Hết hiệu lực từ ${a(e.ended_on)} theo ${t(e.ended_by)}`:t(e.status_name||``)}${e.structure===`none`?`<div class="muted small">chưa có toàn văn</div>`:``}${e.indexed?``:`<div class="muted small">không dùng để trả lời</div>`}</td><td class="num">${e.n_provisions}</td></tr>`),`Kho trống. Bấm Đồng bộ kho luật.`)+(n.length>r?`<div class="bar">${T(`Xem thêm 5 văn bản`,`tertiary`,`id="laws-more"`)}<span class="muted">Đang hiện ${r} / ${n.length}</span></div>`:``);let o=e(`#laws-more`);o&&(o.onclick=()=>{r+=5,i()})};i()}catch{e(`#ldocs`).innerHTML=`<div class="empty">Kho trống. Bấm Đồng bộ kho luật.</div>`}}var nt=null;function rt(e){return`<details class="guide" id="guide" style="border-radius:10px;overflow:hidden;margin-top:20px;border:1px solid var(--cds-border-subtle);background:var(--cds-layer)">
    <summary style="font-size:13.5px;font-weight:600;padding:12px 16px;cursor:pointer">Danh mục câu hỏi hỗ trợ (${e.groups.reduce((e,t)=>e+t.domains.length,0)} nhóm)</summary>
    <p class="muted small" style="margin:4px 16px 12px">Bấm vào câu hỏi mẫu để gửi ngay vào hội thoại.</p>
    ${e.groups.map(e=>`<details class="guide-group" style="margin:6px 16px 10px">
      <summary style="font-size:13px;font-weight:600;cursor:pointer">${t(e.title)} <span class="muted small">(${e.domains.length} nhóm)</span></summary>
      ${e.domains.map(e=>`<div class="guide-domain" style="border-bottom:1px solid var(--cds-border-subtle);padding:10px 0">
        <strong style="font-size:13px;color:var(--a3-primary, #0f766e)">${t(e.title)}</strong>
        <div class="small" style="margin:2px 0 6px">${t(e.what)}</div>
        ${e.limits?`<div class="muted small" style="margin-bottom:6px"><em>Giới hạn:</em> ${t(e.limits)}</div>`:``}
        <div class="chips">${e.examples.map(e=>e.includes(`<`)?`<span class="chip-tpl small">${t(e)}</span>`:`<button type="button" class="cds--btn cds--btn--ghost cds--btn--sm chip-q" data-q="${t(e)}" style="border-radius:9999px;font-size:12px">${t(e)}</button>`).join(``)}</div>
      </div>`).join(``)}
    </details>`).join(``)}
  </details>`}function it(e){let n=e.understood||{};if(!n.title)return``;let r=[n.period&&`kỳ ${n.period}`,n.invoice_numbers&&`hóa đơn ${n.invoice_numbers.join(`, `)}`,n.seller&&`người bán ${n.seller}`,n.issue&&`loại vấn đề: ${n.issue}`,n.top_n&&`${n.top_n} dòng`].filter(Boolean);return`<div class="understood small" style="background:var(--cds-layer-hover, #f4f4f4);padding:5px 12px;border-radius:6px;margin:6px 0 10px;display:inline-block">
    Phân tích câu hỏi: <strong>${t(n.title)}</strong>${r.length?` (${t(r.join(`; `))})`:``}
  </div>`}function at(e,n,r){let i=(n.facts||[]).find(e=>e&&e.passages),a=i?i.sentences.flatMap(e=>e.citations).filter((e,t,n)=>n.findIndex(t=>t.path===e.path)===t).map(e=>`<a href="${t(e.url)}" target="_blank" rel="noopener" style="color:#0f766e;font-weight:600">${t(e.doc_num)}</a>: ${t(e.path.split(` > `).slice(1).join(` > `))}`):(n.citations||[]).map(t),o=n.rows||[],s=n.columns||[],c=o.slice(0,50),l=o.length&&s.length?`<div class="table-wrap" style="margin:12px 0"><table class="cds--data-table cds--data-table--sm"><thead><tr>${s.map(([,e])=>`<th>${t(e)}</th>`).join(``)}</tr></thead>
    <tbody>${c.map(e=>`<tr>${s.map(([n])=>`<td>${t(e[n])}</td>`).join(``)}</tr>`).join(``)}</tbody></table></div>
    ${o.length>c.length?`<div class="muted small">Hiện 50 trên ${o.length} dòng; xem đủ ở trang liên quan.</div>`:``}`:``,u=n.alternatives?.length?`<div class="alts small" style="margin-top:12px;border-top:1px dashed var(--cds-border-subtle);padding-top:8px">${n.domain?`Không đúng ý? Thử hỏi theo loại khác:`:`Có phải bạn muốn hỏi:`} ${n.alternatives.map(n=>`<button type="button" class="cds--btn cds--btn--ghost cds--btn--sm alt-q" data-q="${t(e)}" data-domain="${t(n.domain)}" style="border-radius:9999px;margin:2px">${t(n.title)}</button>`).join(``)}</div>`:``,d={SEMANTIC:`nhận dạng ngữ nghĩa`,STRUCTURE:`nhận dạng theo số hóa đơn/MST đối tác`,MODEL:`mô hình AI phân loại`,CHOSEN_BY_USER:`loại do bạn chọn`,REFUSED:`ngoài phạm vi`,KEYWORD_FALLBACK:`nhận dạng từ khóa`}[n.route?.method]||``;return`<div class="msg-bot-row msg-bot">
    <div class="bot-avatar-box" aria-hidden="true">A3</div>
    <div class="bot-bubble">
      <div class="bot-bubble-head">
        <span class="bot-author">Trợ lý Thuế GTGT</span>
        ${S(n.branch===`REFUSED`?`ABSTAIN`:n.branch,n.branch===`REFUSED`?`Không trả lời`:n.branch===`HELP`?`Hướng dẫn`:void 0)}
        ${i?S(i.mode):``}
        <span class="bot-time">${r}s${d?` · ${t(d)}`:``}</span>
      </div>
      ${it(n)}
      <div class="bot-text">${t(n.text)}</div>
      ${l}
      ${a.length?`<div class="cite-box">
        <div class="cite-head">Căn cứ pháp lý trích dẫn:</div>
        <div class="cite-links">${a.join(`; `)}</div>
      </div>`:``}
      ${i?.dropped?.length?`<div class="cite-warning">${i.dropped.length} câu của mô hình đã bị loại bỏ do không có trích dẫn điều luật bảo đảm.</div>`:``}
      ${(n.links||[]).length?`<div class="chips" style="margin-top:10px">${n.links.map(([e,n])=>`<a class="cds--btn cds--btn--ghost cds--btn--sm" href="${t(n)}" style="border-radius:6px">${t(e)} →</a>`).join(``)}</div>`:``}
      ${u}
      <div class="bot-actions-row">
        <button type="button" class="copy-msg-btn" title="Sao chép nội dung"><span>Sao chép</span></button>
      </div>
    </div>
  </div>`}function ot(e,n){let r=new Date,i=`${String(r.getHours()).padStart(2,`0`)}:${String(r.getMinutes()).padStart(2,`0`)}`;return`<div class="msg-user-row">
    <div class="user-bubble-box">
      <div class="user-bubble">${t(e)}${n?` <span class="small">(đã chọn lại loại câu hỏi)</span>`:``}</div>
      <div class="user-meta"><span>Bạn</span> · <span class="msg-time">${i}</span></div>
    </div>
  </div>`}function st(){return`<div class="chat-hero" id="chat-hero">
    <div class="hero-badge">TRỢ LÝ TRA CỨU DỮ LIỆU & LUẬT THUẾ GTGT</div>
    <h2 class="hero-title">Đặt câu hỏi về hóa đơn, kỳ thuế hoặc quy định pháp luật</h2>
    <p class="hero-desc">Trả lời trực tiếp từ kết quả phân tích của doanh nghiệp hoặc trích dẫn điều khoản từ Cơ sở dữ liệu quốc gia về pháp luật.</p>
    <div class="prompt-cards-grid">
      <div class="prompt-card chip-q" data-q="Quý này có bao nhiêu tiền thuế có nguy cơ bị loại?">
        <div class="card-title">Rủi ro thuế kỳ hiện tại</div>
        <div class="card-sub">Tổng số thuế GTGT có nguy cơ và cần xem xét</div>
      </div>
      <div class="prompt-card chip-q" data-q="Hóa đơn số 340 có vấn đề gì và căn cứ xử lý?">
        <div class="card-title">Đối chiếu hóa đơn</div>
        <div class="card-sub">Kiểm tra tính hợp lệ và cảnh báo nhà cung cấp</div>
      </div>
      <div class="prompt-card chip-q" data-q="Hạn nộp tờ khai thuế giá trị gia tăng quý 1 năm 2026 khi nào?">
        <div class="card-title">Lịch nộp tờ khai</div>
        <div class="card-sub">Theo dõi hạn nộp tờ khai và dời ngày nghỉ</div>
      </div>
      <div class="prompt-card chip-q" data-q="Điều kiện khấu trừ thuế giá trị gia tăng đầu vào gồm những gì?">
        <div class="card-title">Điều kiện khấu trừ</div>
        <div class="card-sub">Trích dẫn luật thuế GTGT và chứng từ thanh toán</div>
      </div>
    </div>
  </div>`}async function ct(){if(V())return;let t=f(),n=N.ws,r;u(()=>clearInterval(r));let i=`agent3.chat2.${N.ws}`,a=[];try{a=JSON.parse(sessionStorage.getItem(i)||`[]`)}catch{a=[]}let o=()=>{try{sessionStorage.setItem(i,JSON.stringify(a.slice(-30)))}catch{}};P().innerHTML=`<div class="ask-wrap">
    ${M(`Hỏi đáp`,`Hỏi đáp thuế & dữ liệu`,`TƯ VẤN & TRA CỨU LUẬT`,``,`tu-van`)}

    <div id="hero-container">${a.length?``:st()}</div>
    <div id="chat" class="chat" role="log" aria-label="Hội thoại" aria-live="polite"></div>
    <div id="pending" role="status"></div>
    <div class="sugg" id="sugg-strip" ${a.length?``:`hidden`}>
      <div class="chips">
        <button type="button" class="cds--btn cds--btn--ghost cds--btn--sm chip-q" data-q="Quý này có bao nhiêu tiền thuế có nguy cơ bị loại?">Rủi ro thuế kỳ hiện tại</button>
        <button type="button" class="cds--btn cds--btn--ghost cds--btn--sm chip-q" data-q="Hóa đơn nào cần xem xét chứng từ thanh toán?">Hóa đơn cần xem xét</button>
        <button type="button" class="cds--btn cds--btn--ghost cds--btn--sm chip-q" data-q="Hạn nộp tờ khai thuế GTGT kỳ này khi nào?">Hạn nộp tờ khai</button>
      </div>
    </div>

    <form id="ask" class="ask-bar-floating">
      <div class="ask-input-pill">
        <input class="ask-text-input" id="q" name="q" autocomplete="off" maxlength="500" placeholder="Nhập câu hỏi về hóa đơn, kỳ thuế hoặc quy định pháp luật... (Enter để gửi)">
        <button type="submit" class="send-btn" id="send-btn" title="Gửi câu hỏi" aria-label="Gửi câu hỏi" style="width:auto;padding:0 16px;font-weight:600;font-size:13px">Gửi</button>
      </div>
      <div class="ask-bar-footer">
        <span class="privacy-badge">Dữ liệu xử lý nội bộ trên máy này</span>
        <div style="display:flex;align-items:center;gap:12px">
          ${a.length?`<button type="button" class="btn-clear-chat" id="clear"><span>Xóa hội thoại</span></button>`:``}
        </div>
      </div>
    </form>

    <div id="guide-box">${w(`Đang tải danh mục câu hỏi`)}</div>
  </div>`;let s=e(`#chat`),c=e(`#pending`),l=e(`#ask`),d=l.querySelector(`[type="submit"]`),h=e(`#q`),g=e(`#hero-container`),_=e(`#sugg-strip`),v=()=>{s.innerHTML=a.join(``),g&&(g.innerHTML=a.length?``:st()),_&&(_.hidden=!a.length)};v();let y=!1,b=async(e,i)=>{if(y||!e||t.aborted)return;y=!0,d.disabled=!0,h.disabled=!0,l.setAttribute(`aria-busy`,`true`),a.push(ot(e,i)),v(),s.lastElementChild?.scrollIntoView({behavior:`smooth`,block:`nearest`});let u=Date.now(),f=()=>{let e=Math.round((Date.now()-u)/1e3);t.aborted||(c.innerHTML=`
          <div class="typing-row">
            <div class="bot-avatar-box" aria-hidden="true">A3</div>
            <div class="typing-bubble">
              <span class="kt-typing-dots"><span class="kt-typing-dot"></span><span class="kt-typing-dot"></span><span class="kt-typing-dot"></span></span>
              <span class="typing-text">${e>3?`Đang tìm điều khoản và trích xuất căn cứ (${e}s)...`:`Đang phân tích câu hỏi...`}</span>
            </div>
          </div>
        `)};f(),r=setInterval(f,1e3);try{let r=await m(`/api/workspaces/${n}/ask`,i?{question:e,domain:i}:{question:e},{signal:t});if(t.aborted)return;a.push(at(e,r,Math.round((Date.now()-u)/1e3)))}catch(n){if(t.aborted)return;a.push(C(`error`,`Không trả lời được`,n.message)),h.value=e}clearInterval(r),c.innerHTML=``,y=!1,d.disabled=!1,h.disabled=!1,l.removeAttribute(`aria-busy`),h.focus(),o(),v(),s.lastElementChild?.scrollIntoView({behavior:`smooth`,block:`nearest`})};e(`#ask`).onsubmit=t=>{t.preventDefault();let n=e(`#q`).value.trim();e(`#q`).value=``,b(n)},P().addEventListener(`click`,e=>{let t=e.target.closest(`.chip-q`);if(t){b(t.dataset.q);return}let n=e.target.closest(`.alt-q`);if(n){b(n.dataset.q,n.dataset.domain);return}let r=e.target.closest(`.copy-msg-btn`);if(r){let e=r.closest(`.bot-bubble`),t=e&&e.querySelector(`.bot-text`)?.innerText||``;t&&navigator.clipboard.writeText(t).then(()=>{r.classList.add(`copied`);let e=r.querySelector(`span`);e&&(e.textContent=`Đã chép`),setTimeout(()=>{r.classList.remove(`copied`),e&&(e.textContent=`Sao chép`)},2e3)}).catch(()=>{})}else e.target.closest(`#clear`)&&(a=[],o(),v())},{signal:t});try{if(nt||=await p(`/api/chat/guide`),t.aborted)return;e(`#guide-box`).innerHTML=rt(nt)}catch(n){if(t.aborted)return;e(`#guide-box`).innerHTML=C(`error`,`Không tải được hướng dẫn`,n.message)}}var lt=[[`#/quan-tri`,`Tổng quan quản trị`],[`#/quan-tri/doanh-nghiep`,`Cấu hình doanh nghiệp`],[`#/quan-tri/danh-muc?ten=policy_presets`,`Quy định chi tiêu gợi ý`],[`#/quan-tri/danh-muc?ten=ai_categories`,`Nhóm hàng cho AI`],[`#/quan-tri/danh-muc?ten=holidays`,`Lịch nghỉ lễ`],[`#/quan-tri/danh-muc?ten=law_topics`,`Chủ đề tin luật`],[`#/quan-tri/danh-muc?ten=chat_domains`,`Câu hỏi của trợ lý`],[`#/quan-tri/kho-luat`,`Kho luật`],[`#/quan-tri/lich-su`,`Lịch sử thay đổi`]],ut=Object.fromEntries(lt.filter(([e])=>e.includes(`ten=`)).map(([e,t])=>[e.split(`ten=`)[1],t]));async function dt(){return p(`/api/admin/status`)}function ft(){let e=location.hash,n=t=>e===t||t===`#/quan-tri/doanh-nghiep`&&e.startsWith(`#/thiet-lap`)||t!==`#/quan-tri`&&e.startsWith(t);return`<nav class="admin-nav" aria-label="Quản trị">${lt.map(([e,r])=>`<a href="${e}" class="${n(e)?`on`:``}">${t(r)}</a>`).join(``)}
    <button type="button" class="cds--btn cds--btn--ghost cds--btn--sm" id="admin-logout">Đăng xuất quản trị</button></nav>`}function pt(){let t=e(`#admin-logout`);t&&(t.onclick=async()=>{await m(`/api/admin/logout`),G(`Đã đăng xuất quản trị`),location.hash=`#/`})}function mt(t){let n=!t.configured,r=n?`Lần đầu sử dụng: đặt mật khẩu quản trị để bảo vệ cấu hình doanh nghiệp, danh mục dùng chung và kho luật.`:`Khu vực quản trị cấu hình và danh mục hệ thống. Vui lòng nhập mật khẩu quản trị để tiếp tục.`;P().innerHTML=`${M(`Quản trị hệ thống`,`Quản trị hệ thống`,`HỆ THỐNG BẢO VỆ`,r)}
    <div style="display:flex;justify-content:center;margin:28px 0">
      <form id="admin-form" class="panel narrow" style="width:100%;max-width:440px">
        <div style="margin-bottom:20px;padding-bottom:14px;border-bottom:1px solid var(--cds-border-subtle)">
          <h3 style="margin:0;font-size:16px;font-weight:600">${n?`Thiết lập mật khẩu quản trị`:`Xác thực quản trị viên`}</h3>
          <span class="muted small">${t.ttl_minutes} phút không thao tác sẽ tự khóa</span>
        </div>
        <div class="cds--form-item cds--text-input-wrapper"><label class="cds--label" for="pw">Mật khẩu${n?` mới (ít nhất 8 ký tự)`:``}</label>
        <input class="cds--text-input son-box" id="pw" type="password" autocomplete="${n?`new-password`:`current-password`}" required></div>
        ${n?`<div class="cds--form-item cds--text-input-wrapper"><label class="cds--label" for="pw2">Nhập lại mật khẩu</label><input class="cds--text-input son-box" id="pw2" type="password" autocomplete="new-password" required></div>`:``}
        <div class="bar" style="margin-top:20px">${T(n?`Đặt mật khẩu`:`Đăng nhập`,`primary`,`type="submit"`)}</div><div id="admin-msg"></div>
        <p class="muted small" style="margin-top:14px">Mật khẩu được mã hóa băm an toàn trên máy cục bộ.</p>
      </form>
    </div>`,e(`#admin-form`).onsubmit=async t=>{t.preventDefault();let r=e(`#pw`).value;if(n&&r!==e(`#pw2`).value)e(`#admin-msg`).innerHTML=C(`error`,`Hai lần nhập không khớp`);else try{await m(n?`/api/admin/setup`:`/api/admin/login`,{password:r}),G(n?`Đã đặt mật khẩu quản trị`:`Đã đăng nhập quản trị`),window.dispatchEvent(new Event(`hashchange`))}catch(t){e(`#admin-msg`).innerHTML=C(`error`,n?`Không đặt được mật khẩu`:`Không đăng nhập được`,t.message)}}}function X(e){return async()=>{let t=await dt();t.logged_in?(await e(),P().insertAdjacentHTML(`afterbegin`,ft()),pt()):mt(t)}}async function ht(){let n=await p(`/api/admin/catalog`);P().innerHTML=`${M(`Tổng quan quản trị`,`Quản trị và Danh mục dùng chung`,`BẢNG ĐIỀU KHIỂN QUẢN TRỊ`,`Mọi thay đổi ở đây được kiểm tra hợp lệ, ghi phiên bản và lưu vào nhật ký lịch sử.`)}
    <div class="grid2">
      <div class="panel" style="border-radius:12px;padding:24px 26px;box-shadow:var(--a3-shadow-sm)">
        <h3 style="margin-top:0;font-size:17px;font-weight:600">
          Doanh nghiệp từ portal
        </h3>
        <p class="muted" style="font-size:13.5px;line-height:1.65">Doanh nghiệp từ hồ sơ chung tại portal: <strong>${t(N.workspaces.find(e=>e.id===N.ws)?.name||`chưa chọn`)}</strong>.</p>
        <div class="bar" style="margin-top:20px">
          ${T(`Cấu hình doanh nghiệp này`,`primary`,`data-go="#/quan-tri/doanh-nghiep"`)}
          ${T(`Chạy wizard thiết lập (5 bước)`,`ghost`,`data-go="#/thiet-lap"`)}
        </div>
      </div>
      <div class="panel" style="border-radius:12px;padding:24px 26px;box-shadow:var(--a3-shadow-sm)">
        <h3 style="margin-top:0;font-size:17px;font-weight:600">
          Danh mục dùng chung toàn hệ thống
        </h3>
        <ul class="list-plain" style="margin-top:14px">
          ${n.map(e=>`<li style="padding:10px 0;border-bottom:1px solid var(--cds-border-subtle);display:flex;justify-content:space-between;align-items:center">
            <a href="#/quan-tri/danh-muc?ten=${e.name}" style="font-weight:500;text-decoration:none">${t(ut[e.name]||e.name)}</a>
            <span class="cds--tag cds--tag--teal" style="font-size:11.5px">v${t(e.version)}</span>
          </li>`).join(``)}
        </ul>
      </div>
    </div>
    <div class="panel narrow" style="border-radius:12px;padding:24px 26px;box-shadow:var(--a3-shadow-sm);margin-top:24px;max-width:560px">
      <h3 style="margin-top:0;font-size:17px;font-weight:600">
        Đổi mật khẩu quản trị
      </h3>
      <form id="pwchg" style="margin-top:16px">
        <div class="form-grid">
          <div class="cds--form-item cds--text-input-wrapper"><label class="cds--label" for="old">Mật khẩu hiện tại</label><input class="cds--text-input" id="old" type="password" autocomplete="current-password"></div>
          <div class="cds--form-item cds--text-input-wrapper"><label class="cds--label" for="new">Mật khẩu mới</label><input class="cds--text-input" id="new" type="password" autocomplete="new-password"></div>
        </div>
        <div class="bar" style="margin-top:18px">${T(`Đổi mật khẩu`,`secondary`,`type="submit"`)}</div>
      </form>
    </div>`,e(`#pwchg`).onsubmit=async t=>{t.preventDefault();try{G(`Đã đổi mật khẩu`,(await m(`/api/admin/password`,{old:e(`#old`).value,new:e(`#new`).value})).note),window.dispatchEvent(new Event(`hashchange`))}catch(e){G(`Không đổi được mật khẩu`,e.message,`error`)}}}var gt=e=>e.split(`
`).map(e=>e.trim()).filter(Boolean),_t=e=>e.split(`,`).map(e=>e.trim()).filter(Boolean),Z=(e,n,r=``)=>`<input class="cds--text-input ${e}" value="${t(n??``)}" ${r}>`,Q={policy_presets:{help:`Mỗi dòng là một quy định gợi ý khi thiết lập doanh nghiệp. "Ngành" là hai chữ số đầu mã VSIC (cách nhau dấu phẩy) để gợi ý theo ngành; để trống là gợi ý cho mọi doanh nghiệp. Quy định chỉ thêm nhắc nhở, không đổi kết quả theo luật.`,render:e=>`<div class="table-wrap"><table class="cds--data-table cds--data-table--sm edit-table"><thead><tr><th>Mã</th><th>Nội dung nhắc</th><th>Nhóm</th><th>Ngành</th><th>Từ số tiền</th><th>Khi tên hàng có</th><th>Đánh dấu sẵn</th><th></th></tr></thead>
      <tbody id="rows">${e.presets.map(e=>Q.policy_presets.row(e)).join(``)}</tbody></table></div>${T(`Thêm quy định`,`ghost`,`id="add-row"`)}`,row:(e={})=>`<tr><td>${Z(`f-id`,e.id,`placeholder="VD: VAN_PHONG_PHAM"`)}</td><td>${Z(`f-flag`,e.flag)}</td><td>${Z(`f-group`,e.group||`Chung`)}</td>
      <td>${Z(`f-for`,(e.for||[]).join(`, `),`placeholder="62, 63"`)}</td><td>${Z(`f-min`,e.min_gross??``,`inputmode="numeric"`)}</td>
      <td>${Z(`f-words`,(e.description_contains||[]).join(`, `))}</td><td><input type="checkbox" class="f-rec" ${e.recommended?`checked`:``}></td>
      <td><button type="button" class="cds--btn cds--btn--ghost cds--btn--sm del-row">Xóa</button></td></tr>`,read:e=>({...e,presets:[...P().querySelectorAll(`#rows tr`)].map(e=>{let t=t=>e.querySelector(t).value.trim(),n={id:t(`.f-id`).toUpperCase(),flag:t(`.f-flag`),group:t(`.f-group`),for:_t(t(`.f-for`)),recommended:e.querySelector(`.f-rec`).checked};return t(`.f-min`)&&(n.min_gross=Number(t(`.f-min`).replace(/\D/g,``))),t(`.f-words`)&&(n.description_contains=_t(t(`.f-words`))),n}).filter(e=>e.id||e.flag)})},ai_categories:{help:`Nhóm hàng mà AI chọn khi phân loại từng dòng hàng trên hóa đơn mua vào. Mô tả càng cụ thể AI càng chọn đúng. Nhóm CA_NHAN (đồ cá nhân) và KHONG_RO (không rõ) là nhóm hệ thống, không xóa được. Đổi danh mục thì nên chạy lại "Phân loại dòng hàng".`,render:e=>`<div class="table-wrap"><table class="cds--data-table cds--data-table--sm edit-table"><thead><tr><th>Mã nhóm</th><th>Mô tả cho AI</th><th></th></tr></thead>
      <tbody id="rows">${e.categories.map(t=>Q.ai_categories.row(t,e.system)).join(``)}</tbody></table></div>${T(`Thêm nhóm`,`ghost`,`id="add-row"`)}`,row:(e={},t=[])=>`<tr><td>${Z(`f-id`,e.id,t.includes(e.id)?`readonly`:`placeholder="VD: THIET_BI_Y_TE"`)}</td><td>${Z(`f-desc`,e.description)}</td>
      <td>${t.includes(e.id)?`<span class="muted small">hệ thống</span>`:`<button type="button" class="cds--btn cds--btn--ghost cds--btn--sm del-row">Xóa</button>`}</td></tr>`,read:e=>({...e,categories:[...P().querySelectorAll(`#rows tr`)].map(e=>({id:e.querySelector(`.f-id`).value.trim().toUpperCase(),description:e.querySelector(`.f-desc`).value.trim()})).filter(e=>e.id)})},holidays:{help:`Ngày nghỉ dùng để dời hạn nộp hồ sơ thuế khi hạn trùng ngày nghỉ (thứ Bảy, Chủ nhật luôn được tính). Ngày lễ cố định lặp lại mỗi năm; nghỉ Tết, nghỉ bù thay đổi theo năm, nhập theo thông báo của Bộ Nội vụ. Bỏ đánh dấu "Đã đối chiếu" với ngày chỉ là phương án dự kiến.`,render:e=>{let n=Object.keys(e.years||{}).sort();return`<h3>Ngày lễ cố định hằng năm</h3><div class="table-wrap"><table class="cds--data-table cds--data-table--sm edit-table"><thead><tr><th>Ngày</th><th>Tháng</th><th>Tên</th><th></th></tr></thead>
        <tbody id="fixed">${e.fixed.map(e=>`<tr><td>${Z(`f-day`,e.day,`inputmode="numeric"`)}</td><td>${Z(`f-month`,e.month,`inputmode="numeric"`)}</td><td>${Z(`f-name`,e.name)}</td><td><button type="button" class="cds--btn cds--btn--ghost cds--btn--sm del-row">Xóa</button></td></tr>`).join(``)}</tbody></table></div>
        ${n.map(t=>`<h3>Năm ${t}</h3><div class="table-wrap"><table class="cds--data-table cds--data-table--sm edit-table"><thead><tr><th>Ngày</th><th>Tên</th><th>Đã đối chiếu</th><th></th></tr></thead>
          <tbody class="year" data-year="${t}">${e.years[t].map(e=>Q.holidays.row(e)).join(``)}</tbody></table></div>
          <button type="button" class="cds--btn cds--btn--ghost cds--btn--sm add-day" data-year="${t}">Thêm ngày nghỉ năm ${t}</button>`).join(``)}
        <div class="bar"><input class="cds--text-input filter-input" id="new-year" placeholder="Năm mới, VD 2028" inputmode="numeric">${T(`Thêm năm`,`ghost`,`id="add-year"`)}</div>
        ${(e.sources||[]).length?`<p class="muted small">Nguồn đã dùng: ${e.sources.map(e=>`<a href="${t(e)}" target="_blank" rel="noopener">${t(new URL(e).hostname)}</a>`).join(`, `)}</p>`:``}`},row:(e={})=>`<tr><td>${Z(`f-date`,e.date,`type="date"`)}</td><td>${Z(`f-name`,e.name)}</td><td><input type="checkbox" class="f-ver" ${e.verified===!1?``:`checked`}></td><td><button type="button" class="cds--btn cds--btn--ghost cds--btn--sm del-row">Xóa</button></td></tr>`,read:e=>({...e,fixed:[...P().querySelectorAll(`#fixed tr`)].map(e=>({day:Number(e.querySelector(`.f-day`).value),month:Number(e.querySelector(`.f-month`).value),name:e.querySelector(`.f-name`).value.trim()})),years:Object.fromEntries([...P().querySelectorAll(`tbody.year`)].map(e=>[e.dataset.year,[...e.querySelectorAll(`tr`)].map(e=>({date:e.querySelector(`.f-date`).value,name:e.querySelector(`.f-name`).value.trim(),verified:e.querySelector(`.f-ver`).checked})).filter(e=>e.date)]))})},law_topics:{help:`Tin luật mới được lọc theo độ gần nghĩa giữa trích yếu văn bản và các chủ đề dưới đây (mô hình bge-m3 chạy trên máy). Viết mỗi chủ đề một dòng, càng cụ thể càng tốt. "Chủ đề loại trừ" là từ khóa của văn bản khu vực công cần bỏ qua.`,render:e=>`<div class="cds--form-item"><label class="cds--label" for="topics">Chủ đề liên quan (mỗi dòng một chủ đề)</label><textarea class="cds--text-area" id="topics" rows="12">${t(e.topics.join(`
`))}</textarea></div>
      <div class="cds--form-item"><label class="cds--label" for="noise">Chủ đề loại trừ (mỗi dòng một cụm từ, viết không dấu)</label><textarea class="cds--text-area" id="noise" rows="6">${t((e.noise||[]).join(`
`))}</textarea></div>`,read:t=>({...t,topics:gt(e(`#topics`).value),noise:gt(e(`#noise`).value)})},chat_domains:{help:`Mỗi loại câu hỏi có mô tả (hiện ở trang Hỏi đáp), câu ví dụ để trợ lý học cách nhận ra loại câu đó, và câu gợi ý hiện cho người dùng. Thêm câu ví dụ đúng cách người dùng hay hỏi giúp trợ lý nhận dạng tốt hơn. Thêm loại câu hỏi mới cần lập trình hàm trả lời nên không làm được ở đây.`,render:e=>e.domains.map(e=>`<details class="guide-group domain-edit" data-id="${t(e.id)}"><summary>${t(e.title)} <span class="muted small">${t(e.id)}, ${e.examples.length} câu ví dụ${e.examples_generated?.length?`, ${e.examples_generated.length} câu do mô hình viết đã lọc`:``}</span></summary>
      <div class="form-grid"><div class="cds--form-item"><label class="cds--label">Tên loại câu hỏi</label>${Z(`f-title`,e.title)}</div>
      <div class="cds--form-item"><label class="cds--label">Giới hạn</label>${Z(`f-limits`,e.limits)}</div></div>
      <div class="cds--form-item"><label class="cds--label">Trả lời được</label><textarea class="cds--text-area f-what" rows="2">${t(e.what)}</textarea></div>
      <div class="form-grid"><div class="cds--form-item"><label class="cds--label">Câu ví dụ để nhận dạng (mỗi dòng một câu, ít nhất 3)</label><textarea class="cds--text-area f-ex" rows="8">${t(e.examples.join(`
`))}</textarea></div>
      <div class="cds--form-item"><label class="cds--label">Câu gợi ý hiện cho người dùng (dùng &lt;...&gt; cho chỗ cần điền)</label><textarea class="cds--text-area f-guide" rows="8">${t((e.guide||[]).join(`
`))}</textarea></div></div></details>`).join(``),read:e=>({...e,domains:e.domains.map(e=>{let t=P().querySelector(`.domain-edit[data-id="${e.id}"]`);return{...e,title:t.querySelector(`.f-title`).value.trim(),limits:t.querySelector(`.f-limits`).value.trim(),what:t.querySelector(`.f-what`).value.trim(),examples:gt(t.querySelector(`.f-ex`).value),guide:gt(t.querySelector(`.f-guide`).value)}})})}};async function vt(){let n=new URLSearchParams(location.hash.split(`?`)[1]||``).get(`ten`)||`policy_presets`,r=Q[n];if(!r){P().innerHTML=C(`error`,`Không có danh mục này`);return}let{data:i,history:a}=await p(`/api/admin/catalog/${n}`);P().innerHTML=`${M(`Danh mục dùng chung`,ut[n],`DANH MỤC HỆ THỐNG`,r.help)}
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:20px">
      <span class="cds--tag cds--tag--teal">Phiên bản ${t(i.version)}</span>
      <span class="muted small">Áp dụng chung cho mọi doanh nghiệp trên máy này</span>
    </div>
    <form id="cat-form"><div id="cat-body" class="panel" style="border-radius:12px;padding:24px 26px;box-shadow:var(--a3-shadow-sm);margin-bottom:24px">${r.render(i)}</div>
    <div class="bar sticky-save"><input class="cds--text-input filter-input" id="by" placeholder="Người sửa" value="${t(o.get(`agent3.reviewer`)||``)}" required>
    ${T(`Lưu danh mục`,`primary`,`type="submit"`)}<span id="cat-msg"></span></div></form>
    ${a.length?`<h2 class="section">Nhật ký phiên bản danh mục</h2><ul class="list-plain small" style="background:var(--a3-surface);border:1px solid var(--cds-border-subtle);border-radius:10px;padding:16px 20px">${a.map(e=>`<li style="padding:6px 0;border-bottom:1px solid var(--cds-border-subtle)">${t(e.at.replace(`T`,` `))}: <strong>${t(e.by)}</strong> ${t(JSON.stringify(e.summary))}</li>`).join(``)}</ul>`:``}`;let s=e(`#cat-body`);s.addEventListener(`click`,e=>{e.target.closest(`.del-row`)&&e.target.closest(`tr`).remove();let t=e.target.closest(`.add-day`);t&&P().querySelector(`tbody.year[data-year="${t.dataset.year}"]`).insertAdjacentHTML(`beforeend`,Q.holidays.row({date:`${t.dataset.year}-01-01`,name:``}))}),e(`#add-row`)&&(e(`#add-row`).onclick=()=>e(`#rows`).insertAdjacentHTML(`beforeend`,r.row({},i.system||[]))),e(`#add-year`)&&(e(`#add-year`).onclick=()=>{let t=e(`#new-year`).value.trim();/^20\d{2}$/.test(t)?(i.years={...r.read(i).years,[t]:[]},s.innerHTML=r.render({...r.read(i),years:i.years})):G(`Năm không hợp lệ`,``,`error`)}),e(`#cat-form`).onsubmit=async t=>{t.preventDefault();let a=e(`#by`).value.trim();if(!a)G(`Cần ghi tên người sửa`,``,`error`);else{o.set(`agent3.reviewer`,a);try{G(`Đã lưu danh mục`,`phiên bản ${(await h(`/api/admin/catalog/${n}?by=${encodeURIComponent(a)}`,r.read(i))).version}`),window.dispatchEvent(new Event(`hashchange`))}catch(t){e(`#cat-msg`).innerHTML=C(`error`,`Chưa lưu được`,t.message)}}}}async function yt(){let e=(await Promise.all(Object.keys(ut).map(e=>p(`/api/admin/catalog/${e}`).then(t=>t.history.map(t=>({...t,label:ut[e]})))))).flat().sort((e,t)=>e.at<t.at?1:-1),n=[];if(N.ws)try{n=await p(`/api/workspaces/${N.ws}/pack/history`)}catch{n=[]}P().innerHTML=`${M(`Lịch sử thay đổi`,`Lịch sử thay đổi`,`NHẬT KÝ QUẢN TRỊ`)}<h2 class="section">Danh mục dùng chung</h2>
    ${e.length?`<ul class="list-plain small">${e.map(e=>`<li>${t(e.at.replace(`T`,` `))}: <strong>${t(e.label)}</strong>, ${t(e.by)}, ${t(JSON.stringify(e.summary))}</li>`).join(``)}</ul>`:`<p class="muted">Chưa có thay đổi.</p>`}
    <h2 class="section">Cấu hình doanh nghiệp đang chọn</h2>
    ${n.length?`<ul class="list-plain small">${n.slice().reverse().map(e=>`<li>${t((e.at||``).replace(`T`,` `))}: ${t(e.by||``)} ${t(JSON.stringify(e.changes||e.diff||e))}</li>`).join(``)}</ul>`:`<p class="muted">Chưa có thay đổi.</p>`}`}var bt=[[`#/`,`Tổng quan`,Ve],[`#/nap`,`Nạp dữ liệu`,ye],[`#/viec`,`Việc cần xử lý`,Ke],[`#/hoa-don`,`Hóa đơn & Sao kê`,Qe],[`#/so-lieu`,`Số liệu & Giải trình`,Ee],[`#/hoi`,`Hỏi đáp & Kho luật`,ct],[`#/quan-tri`,`Cài đặt`,X(ht)]],xt=[[`#/du-lieu`,`Bảng kê đang sử dụng`,ve],[`#/quan-tri/mau-sao-ke`,`Nhận dạng cột sao kê`,X(_e)],[`#/ngan-hang`,`Sao kê ngân hàng`,$e],[`#/giai-trinh`,`Hồ sơ giải trình`,Te],[`#/lich`,`Lịch thuế`,et],[`#/luat`,`Kho luật`,tt],[`#/tin-luat`,`Kho luật`,tt],[`#/quan-tri/doanh-nghiep`,`Cấu hình doanh nghiệp`,X(Le)],[`#/quan-tri/danh-muc`,`Danh mục dùng chung`,X(vt)],[`#/quan-tri/kho-luat`,`Kho luật`,X(tt)],[`#/quan-tri/lich-su`,`Lịch sử thay đổi`,X(yt)],[`#/thiet-lap`,`Thiết lập nghiệp vụ thuế`,X(Ie)],[`#/cai-dat`,`Cấu hình doanh nghiệp`,X(Le)]];function St(n){let r=n;n.startsWith(`#/quan-tri`)||[`#/thiet-lap`,`#/cai-dat`].includes(n)?r=`#/quan-tri`:[`#/ngan-hang`,`#/du-lieu`].includes(n)?r=`#/hoa-don`:[`#/giai-trinh`,`#/lich`].includes(n)?r=`#/so-lieu`:[`#/luat`,`#/tin-luat`].includes(n)&&(r=`#/hoi`),e(`#nav`).innerHTML=bt.map(([e,n])=>`<li class="cds--side-nav__item"><a class="cds--side-nav__link" href="${e}" ${e===r?`aria-current="page"`:``}>
    <span class="cds--side-nav__link-text">${t(n)}</span></a></li>`).join(``),e(`.admin-link`).setAttribute(`aria-current`,r===`#/quan-tri`?`page`:`false`),ne(e(`#nav`))}async function Ct(){let n=d(),r=location.hash.split(`?`)[0]||`#/`;if(n.aborted)return;if(r===`#/nap`&&N.ws&&H()){window.top.location.href=H()+`/#data`;return}St(r);let i=e(`#active-company`);i&&(i.title=i.textContent),document.body.classList.remove(`nav-open`),e(`.menu-toggle`).setAttribute(`aria-expanded`,`false`),e(`#modal-root`).innerHTML=``;let a=bt.find(([e])=>e===r)||xt.find(([e])=>e===r)||bt[0],o=a[2];document.title=`${a[1]} · Trợ lý Thuế`;try{if(V())return;await o()}catch(e){if(n.aborted)return;P().innerHTML=`<h1 class="page">${t(a[1])}</h1>`+C(`error`,`Có lỗi khi tải trang`,e.message)}n.aborted||(ne(P()),document.querySelector(`.drawer`)||P().focus({preventScroll:!0}))}document.addEventListener(`click`,e=>{let t=e.target.closest(`[data-go]`);t&&(location.hash=t.dataset.go)}),e(`.menu-toggle`).setAttribute(`aria-expanded`,`false`),e(`.menu-toggle`).onclick=()=>{let t=document.body.classList.toggle(`nav-open`);e(`.menu-toggle`).setAttribute(`aria-expanded`,String(t))},document.body.className=`cds--g10`;try{localStorage.removeItem(`agent3.theme`),localStorage.removeItem(`agent3.theme.embedded`)}catch{}window.addEventListener(`hashchange`,Ct),re(),e(`.skip-link`).onclick=e=>{e.preventDefault(),P().focus()};var wt=null;new MutationObserver(()=>{wt||=setTimeout(()=>{wt=null,ne(P())},100)}).observe(P(),{childList:!0,subtree:!0}),document.addEventListener(`keydown`,t=>{t.key===`Escape`&&(e(`#modal-root`).innerHTML?e(`#modal-root`).innerHTML=``:document.body.classList.contains(`nav-open`)&&(document.body.classList.remove(`nav-open`),e(`.menu-toggle`).setAttribute(`aria-expanded`,`false`),e(`.menu-toggle`).focus()))}),I().then(async()=>{await Ct(),$()}).catch(e=>{P().innerHTML=C(`error`,`Không kết nối được máy chủ Agent 3`,e.message)});var Tt=!1;async function Et(){if(!(Tt||document.hidden)){Tt=!0;try{let t=await fetch(`/api/platform/context`,{cache:`no-store`});if(!t.ok)return;let n=await t.json();if(!N.platform||n.profile_revision!==N.platform.profile_revision||n.workspace_id!==N.platform.workspace_id||n.state!==N.platform.state){let t=[...P().querySelectorAll(`input,select,textarea`)].filter(e=>![`password`,`file`,`hidden`].includes(e.type)).map(e=>({name:e.name||e.id||e.dataset.f,value:e.value,checked:e.checked}));if(t.length)try{sessionStorage.setItem(`agent3.previous-context-draft`,JSON.stringify({revision:N.platform?.profile_revision,path:location.hash,fields:t}))}catch{}N.platform=n,d(),N.report=null,e(`#modal-root`).replaceChildren(),await I(),await Ct(),t.length&&P().insertAdjacentHTML(`afterbegin`,C(`warning`,`Hồ sơ portal đã thay đổi`,`Bản nháp cũ được giữ riêng trong phiên trình duyệt; không áp dụng sang doanh nghiệp mới.`))}}catch{}finally{Tt=!1}}}setInterval(Et,4e3),document.addEventListener(`visibilitychange`,Et),window.addEventListener(`agent3-context-stale`,Et);var Dt=!1;async function $(e=!1){if(Dt||!N.ws||document.hidden)return;Dt=!0;let t=N.ws;try{let n=await m(`/api/workspaces/${t}/ai/auto${e===!0?`?retry=true`:``}`,{},{signal:new AbortController().signal});n.running&&N.ws===t&&setTimeout($,5e3),n.error&&N.ws===t&&!document.getElementById(`ai-background-status`)&&P().insertAdjacentHTML(`beforeend`,`<div id="ai-background-status">${C(`warning`,`Chưa hoàn tất hỗ trợ tự động`,`Kết quả phân loại bổ sung chưa sẵn sàng. Bạn vẫn có thể rà soát chứng từ và xem số liệu.`)}<button type="button" class="cds--btn cds--btn--tertiary cds--btn--sm" id="ai-retry">Thử lại hỗ trợ tự động</button></div>`);let r=document.getElementById(`ai-retry`);r&&(r.onclick=()=>{document.getElementById(`ai-background-status`)?.remove(),$(!0)})}catch{}finally{Dt=!1}}setInterval($,6e4),document.addEventListener(`visibilitychange`,()=>$());