'use strict';
(() => {
  const $=id=>document.getElementById(id),mount=location.pathname.startsWith('/agent2/')?'/agent2':'';
  const periods=['history_start','history_end','reference_start','reference_end','evaluation_start'];
  let token='',actorID='',contextID='',company='',epoch=0,controller=null,state=null,busy=false,timer=null;
  const keys=new Map();
  const node=(tag,text)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=String(text);return e;};
  function notice(text){$('notice').textContent=text;$('notice').hidden=!text;}
  function controls(){const allowed=!!state?.can_fit&&!busy;for(const id of [...periods,'snapshot','minimum_history','evaluation_mode','draft'])$(id).disabled=!allowed;$('fit').disabled=!allowed||!state.draft||['fitting','succeeded'].includes(state.fit?.status);$('activate').disabled=!allowed||state.fit?.status!=='succeeded'||state.activation?.status==='active';}
  async function api(path,body){
    const headers={'X-Session':token,'X-Platform':'1'};let key;
    if(body!==undefined){headers['Content-Type']='application/json';const identity=path+'|'+JSON.stringify(body);if(!keys.has(identity))keys.set(identity,crypto.randomUUID());key=keys.get(identity);headers['Idempotency-Key']=key;}
    const response=await fetch(mount+path,{method:body===undefined?'GET':'POST',headers,body:body===undefined?undefined:JSON.stringify(body),cache:'no-store',signal:controller?.signal});
    const value=await response.json();if(!response.ok){const error=Error(value.errors?.map(e=>e.message+' '+e.action).join('\n')||value.error||'Chưa thực hiện được thao tác.');error.status=response.status;throw error;}return value;
  }
  const base=()=>'/api/v1/companies/'+encodeURIComponent(company)+'/analysis-config';
  function local(iso){if(!iso)return '';const d=new Date(iso);return new Date(d.getTime()+7*3600000).toISOString().slice(0,19);}
  function render(value,fill){state=value;$('settings').hidden=false;$('permission').textContent=value.can_fit?'Bạn có quyền chuẩn bị và kích hoạt phiên bản cho doanh nghiệp này.':'Bạn có quyền xem cấu hình; cần quyền model.fit để thay đổi phiên bản.';
    $('status').textContent=({fitting:'Đang chuẩn bị model. Có thể tải lại để xem trạng thái.',succeeded:'Đã chuẩn bị đủ hai phiên bản. Chưa có kết luận về độ chính xác nghiệp vụ.',failed:'Chưa chuẩn bị được đủ model. Kiểm tra dữ liệu và kỳ đã chọn rồi thử lại.',interrupted:'Lượt chuẩn bị bị gián đoạn. Kiểm tra rồi bấm chuẩn bị lại; phiên bản đang dùng được giữ nguyên.'})[value.fit?.status]||'Chưa chuẩn bị phiên bản theo cấu hình này.';
    if(value.activation?.status==='active')$('status').textContent='Đã kích hoạt phiên bản cho chế độ kiểm chứng kỹ thuật.';
    $('history').textContent=JSON.stringify({revision:value.revision,active:value.active,history:value.history,fit:value.fit},null,2);
    if(fill&&value.draft){$('snapshot').value=value.draft.snapshot_id;for(const id of periods)$(id).value=local(value.draft[id]);$('minimum_history').value=value.draft.minimum_history;$('evaluation_mode').value=value.draft.evaluation_mode;}
    clearTimeout(timer);if(value.fit?.status==='fitting'){const e=epoch;timer=setTimeout(async()=>{try{const next=await api(base());if(e===epoch)render(next,false);}catch(error){if(e===epoch)notice(error.message);}},2000);}controls();
  }
  async function load(){epoch++;const e=epoch;controller?.abort();controller=new AbortController();clearTimeout(timer);state=null;busy=false;keys.clear();$('settings').hidden=true;$('history').textContent='';$('snapshot').replaceChildren();for(const id of periods)$(id).value='';$('minimum_history').value='20';$('evaluation_mode').value='backtest';notice('');controls();
    try{const value=await api(base());if(e!==epoch)return;const data=await api('/api/v1/companies/'+encodeURIComponent(company)+'/he/datasets');if(e!==epoch)return;$('snapshot').replaceChildren(...data.datasets.map(s=>{const o=node('option',s.record_count+' giao dịch · '+new Date(s.created_at).toLocaleString('vi-VN'));o.value=s.snapshot_id;return o;}));render(value,true);}catch(error){if(e===epoch&&error.name!=='AbortError'){$('permission').textContent=error.status===403?'Bạn chưa được cấp quyền quản lý phân tích tại doanh nghiệp này.':error.message;}}
  }
  async function action(name,body){if(busy)return;const e=epoch;busy=true;controls();notice('');try{const value=await api(base()+'/'+name,body);if(e===epoch)render(value,false);}catch(error){if(e===epoch&&error.name!=='AbortError')notice(error.message);}finally{if(e===epoch){busy=false;controls();}}}
  function remember(){
    try{if(company&&actorID)sessionStorage.setItem('agent2.company.selection',JSON.stringify({version:1,actor:actorID,context:contextID,company,page:'analysis-settings'}));}catch{/* optional selection */}
    history.replaceState(null,'',location.pathname+location.search+(company?'#company='+encodeURIComponent(company):''));
    for(const a of document.querySelectorAll('header a[href]'))if(new URL(a.href).pathname.endsWith('/workspace'))a.href=mount+'/workspace'+(company?'#company='+encodeURIComponent(company):'');
  }
  $('company').addEventListener('change',()=>{company=$('company').value;remember();load();});
  $('draft').addEventListener('click',()=>{const config={version:'company-fit-config/1.0.0',snapshot_id:$('snapshot').value,method_id:'robust_z',missing_policy:'strict',minimum_history:Number($('minimum_history').value),profile_id:'technical-shadow-he4',evaluation_mode:$('evaluation_mode').value,selected_columns:['log_abs_amount','event_hour_sin']};for(const id of periods){if(!$(id).value){notice('Điền đủ các mốc thời gian trước khi lưu.');return;}const value=$(id).value;config[id]=value+(value.length===16?':00':'')+'+07:00';}action('draft',{expected_revision:state.revision,config});});
  $('fit').addEventListener('click',()=>action('fit',{expected_revision:state.revision}));
  $('activate').addEventListener('click',()=>action('activate',{expected_revision:state.revision}));
  async function init(){try{token=sessionStorage.getItem('kt-session')||'';if(!token||!mount){notice('Mở cấu hình từ Portal và đăng nhập để tiếp tục.');return;}const context=await api('/api/v1/ui/context');actorID=context.actor_id;contextID=context.context_id||'';$('company').replaceChildren(...context.companies.map(c=>{const o=node('option',c);o.value=c;return o;}));$('company').disabled=!context.companies.length;let shared;try{shared=JSON.parse(sessionStorage.getItem('agent2.company.selection'));}catch{/* optional */}const desired=new URLSearchParams(location.hash.slice(1)).get('company'),remembered=shared?.version===1&&shared.actor===actorID&&shared.context===contextID&&context.companies.includes(shared.company)?shared.company:null;company=context.companies.includes(desired)?desired:remembered||context.companies[0]||'';$('company').value=company;remember();if(company)await load();else{state=null;$('settings').hidden=true;$('history').textContent='';notice('Bạn chưa có doanh nghiệp được cấp quyền.');controls();}}catch(error){notice(error.message);}}
  window.addEventListener('storage',e=>{if(e.key==='kt-session'){controller?.abort();state=null;$('settings').hidden=true;init();}});window.addEventListener('focus',()=>{if((sessionStorage.getItem('kt-session')||'')!==token)init();});init();
})();
