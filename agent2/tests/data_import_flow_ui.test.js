"use strict";
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');

function harness(options={}){
  const nodes={},requests=[],navigations=[];
  const html=fs.readFileSync('review_ui/data_import.html','utf8');
  for(const [,id] of html.matchAll(/id="([^"]+)"/g)){
    const node={id,value:'',files:[],disabled:true,hidden:false,checked:false,textContent:'',className:'',listeners:{},
      addEventListener(event,fn){this.listeners[event]=fn;},setAttribute(name,value){this[name]=value;},focus(){}};
    let markup='';Object.defineProperty(node,'innerHTML',{get(){return markup;},set(value){
      markup=value;if(['import-scenario','import-company'].includes(id))node.value=Array.from(value.matchAll(/<option value="([^"]+)"/g))[0]?.[1]||'';
    }});nodes[id]=node;
  }
  nodes['import-date-order'].value='iso';nodes['import-encoding'].value='utf-8-sig';nodes['import-delimiter'].value='auto';
  const overview={can_manage:options.manage!==false,companies:options.noCompanies?[]:[{company_id:'C001',name:'SIM One'},{company_id:'C002',name:'SIM Two'}]};
  const failures=[];if(options.failure)failures.push(options.failure);
  const app=vm.createContext({document:{getElementById:id=>nodes[id]},URLSearchParams,console,
    location:{search:'?company=C001&scenario=003',assign:url=>navigations.push(url)},
    btoa:value=>Buffer.from(value,'binary').toString('base64'),
    fetch:async(path,opts)=>{
      const body=opts?.body?JSON.parse(opts.body):null;requests.push({path,body,headers:opts?.headers});
      const index=failures.findIndex(failure=>path.includes(failure.match));
      if(index>=0){const failure=failures.splice(index,1)[0];if(failure.network)throw new Error('offline');
        return {ok:false,status:failure.status||503,json:async()=>{if(failure.invalidJSON)throw new Error('HTML');return {error:failure.message||'SIM context unavailable'};}};
      }
      let value;
      if(path==='/api/meta')value={csrf_token:'TOKEN_'+requests.filter(r=>r.path==='/api/meta').length,scenarios:['003'],default_scenario:'003',qa:true};
      else if(path.startsWith('/api/company-ml'))value=overview;
      else if(path.startsWith('/api/data-import/context')){
        const company=new URLSearchParams(path.split('?')[1]).get('company');
        value={required:['transaction_id'],optional:['vendor_id'],txn_types:['vendor_payment'],max_bytes:10485760,max_rows:10000,
          status:{company_id:company,data:{rows:30,revision:'REV_'+company},active_version:'ACTIVE_'+company},references:{employees:['SIM_E1'],vendors:['SIM_V1'],customers:[]}};
      }else if(path.endsWith('/preview'))value={valid:true,token:'PREVIEW_TOKEN',error_count:0,errors:[],warnings:['SIM: THAY THẾ'],feature_count:194,
        summary:{company_id:body.company_id,rows:15,previous_rows:30,skipped_blank_rows:0,trimmed_cells:0,first_at:'2024-01-01',last_at:'2024-01-15'},normalized_preview:[{transaction_id:'000001',company_id:body.company_id}]};
      else if(path.endsWith('/commit'))value={next_url:'/company-ml?company='+body.company_id+'&scenario=003'};
      else throw new Error('Unexpected '+path);
      return {ok:true,status:200,json:async()=>JSON.parse(JSON.stringify(value))};
    }});
  new vm.Script(fs.readFileSync('review_ui/data_import.js','utf8')).runInContext(app);
  const tick=async()=>{for(let i=0;i<8;i++)await new Promise(resolve=>setImmediate(resolve));};
  return {nodes,requests,navigations,overview,tick,fail:failure=>failures.push(failure),
    async click(id){await nodes[id].listeners.click();await tick();},
    async change(id,value){nodes[id].value=value;await nodes[id].listeners.change();await tick();},
    async file(name='SIM.csv'){nodes['import-file'].files=[{name,size:12,arrayBuffer:async()=>Uint8Array.from(Buffer.from('SIM file')).buffer}];await nodes['import-file'].listeners.change();await tick();},
    async submit(){await nodes['import-form'].listeners.submit({preventDefault(){}});await tick();}};
}

test('authorized import opens file input and explains the next action beside it',async()=>{
  const h=harness();await h.tick();
  assert.equal(h.nodes['import-file'].disabled,false);assert.match(h.nodes['import-file-status'].textContent,/sẵn sàng.*C001/);
  assert.equal(h.nodes['import-check'].disabled,true);await h.file();assert.equal(h.nodes['import-check'].disabled,false);
});

test('readonly import explains why file is locked and cannot submit through an injected event',async()=>{
  const h=harness({manage:false});await h.tick();
  assert.equal(h.nodes['import-file'].disabled,true);assert.match(h.nodes['import-file-status'].textContent,/chỉ có quyền xem.*bị khóa/);
  await h.submit();assert.equal(h.requests.filter(r=>r.body).length,0);
});

test('missing company scope has an explanation and keeps reload available',async()=>{
  const h=harness({noCompanies:true});await h.tick();
  assert.equal(h.nodes['import-file'].disabled,true);assert.match(h.nodes['import-file-status'].textContent,/Chưa có doanh nghiệp.*đăng nhập/);
  assert.equal(h.nodes['import-reload'].disabled,false);assert.equal(h.requests.filter(r=>r.path.includes('/context')).length,0);
});

test('initial connection failure can recover with the adjacent retry button',async()=>{
  const h=harness({failure:{match:'/api/meta',network:true}});await h.tick();
  assert.equal(h.nodes['import-file'].disabled,true);assert.equal(h.nodes['import-retry'].hidden,false);
  assert.equal(h.nodes['import-reload'].disabled,false);assert.match(h.nodes['import-file-status'].textContent,/Mất kết nối/);
  await h.click('import-retry');assert.equal(h.nodes['import-file'].disabled,false);assert.equal(h.nodes['import-retry'].hidden,true);
  assert.equal(h.requests.filter(r=>r.body).length,0);
});

test('malformed server response is understandable and reload recovers initialization',async()=>{
  const h=harness({failure:{match:'/api/company-ml',invalidJSON:true}});await h.tick();
  assert.match(h.nodes['import-file-status'].textContent,/Chưa đọc được dữ liệu từ máy chủ/);
  assert.equal(h.nodes['import-retry'].disabled,false);await h.click('import-reload');
  assert.equal(h.nodes['import-file'].disabled,false);
});

test('missing import route explains an old server and can retry without refreshing the browser',async()=>{
  const h=harness({failure:{match:'/api/data-import/context',status:404}});await h.tick();
  assert.equal(h.nodes['import-file'].disabled,true);assert.match(h.nodes['import-file-status'].textContent,/chưa hỗ trợ nhập CSV\/Excel/);
  await h.click('import-retry');assert.equal(h.nodes['import-file'].disabled,false);
});

test('file preview then explicit confirmation saves and opens ML for the selected company',async()=>{
  const h=harness();await h.tick();await h.change('import-company','C002');await h.file('SIM.xlsx');await h.submit();
  const preview=h.requests.find(r=>r.path.endsWith('/preview'));
  assert.equal(preview.body.filename,'SIM.xlsx');assert.equal(preview.body.company_id,'C002');assert.equal(preview.body.expected_revision,'REV_C002');
  assert.equal(h.nodes['import-save'].disabled,true);assert.equal(h.requests.filter(r=>r.path.endsWith('/commit')).length,0);
  h.nodes['import-ack'].checked=true;await h.nodes['import-ack'].listeners.change();
  await h.click('import-save');assert.equal(h.navigations[0],'/company-ml?company=C002&scenario=003');
  assert.equal(h.requests.find(r=>r.path.endsWith('/commit')).body.acknowledge,true);
});

test('changing file or import options invalidates the previous confirmation',async()=>{
  const h=harness();await h.tick();await h.file();await h.submit();
  h.nodes['import-ack'].checked=true;await h.change('import-date-order','dmy');
  assert.equal(h.nodes['import-save'].disabled,true);assert.equal(h.nodes['import-save-section'].hidden,true);
  await h.click('import-save');assert.equal(h.requests.filter(r=>r.path.endsWith('/commit')).length,0);
});

test('expired CSRF refreshes the token but never automatically repeats a save',async()=>{
  const h=harness();await h.tick();await h.file();await h.submit();h.nodes['import-ack'].checked=true;
  h.fail({match:'/api/data-import/commit',status:403,message:'Phiên làm việc đã thay đổi. Tải lại trang để tiếp tục.'});
  await h.click('import-save');
  assert.equal(h.requests.filter(r=>r.path.endsWith('/commit')).length,1);assert.equal(h.navigations.length,0);
  assert.match(h.nodes['import-notice'].textContent,/Tải lại và kiểm tra lại tệp/);
  await h.submit();assert.equal(h.requests.filter(r=>r.path.endsWith('/preview')).at(-1).headers['X-CSRF-Token'],'TOKEN_2');
});
