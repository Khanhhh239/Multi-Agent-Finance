"use strict";
const {test}=require('node:test');
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');

function harness(){
  const source=fs.readFileSync('review_ui/company_ml.js','utf8'),html=fs.readFileSync('review_ui/company_ml.html','utf8');
  const nodes={};
  for(const [,id] of html.matchAll(/id="([^"]+)"/g)){
    const node={id,value:'',disabled:false,hidden:true,textContent:'',className:'',listeners:{},files:[],options:[],
      addEventListener(name,fn){this.listeners[name]=fn;},focus(){},querySelectorAll(){return [];}};
    let markup='';
    Object.defineProperty(node,'innerHTML',{get(){return markup;},set(value){
      markup=value;
      if(['ml-company','ml-scenario','ml-algorithm'].includes(id)){
        node.options=Array.from(value.matchAll(/<option value="([^"]*)"([^>]*)>/g),m=>({value:m[1],disabled:m[2].includes('disabled')}));
        node.value=node.options[0]?.value||'';
      }
    }});
    Object.defineProperty(node,'selectedOptions',{get(){return node.options.filter(o=>o.value===node.value);}});
    nodes[id]=node;
  }
  nodes['ml-budget'].value='1';
  const state=company=>({company_id:company,data:null,active_version:null,versions:[],history:[],runs:[]});
  const states={C001:state('C001'),C002:state('C002')};
  const requests=[];let failNextWrite=false,delayStatus=null;
  const overview={can_manage:true,mode:'shadow',companies:[{company_id:'C001',name:'One'},{company_id:'C002',name:'Two'}],
    algorithms:['isolation_forest','autoencoder','ecod','lof','catboost'].map(id=>({id,label:id,installed:true,requires_labels:id==='catboost'}))};
  const context=vm.createContext({document:{getElementById:id=>nodes[id]},URLSearchParams,console,
    fetch:async(path,options)=>{
      const body=options?.body?JSON.parse(options.body):null;requests.push({path,body});
      if(body&&failNextWrite){failNextWrite=false;throw new Error('offline');}
      let value;
      if(path==='/api/meta')value={csrf_token:'TEST_TOKEN',scenarios:['003'],default_scenario:'003',qa:true};
      else if(path.startsWith('/api/company-ml/status')){
        const company=new URLSearchParams(path.split('?')[1]).get('company');
        if(delayStatus)await delayStatus;
        value=states[company];
      }else if(path.startsWith('/api/company-ml?')||path==='/api/company-ml')value=overview;
      else if(path.endsWith('/data-update')){
        const s=states[body.company_id];s.data={revision:'revision-'+body.company_id,scenario:'003',columns:['x'],rows:20,labels_count:0,
          first_at:'2024-01-01T00:00:00+07:00',last_at:'2025-01-01T00:00:00+07:00',
          suggested_windows:{train_end:'2024-06-01T00:00:00+07:00',calibration_end:'2024-09-01T00:00:00+07:00'}};value=s;
      }else if(path.endsWith('/evaluate')){
        const s=states[body.company_id];s.versions=[{version_id:'V1',number:1,algorithm:body.algorithm,data_revision:s.data.revision,
          evaluation_rows:5,evaluation_alerts:0,evaluation_alert_rate:0,labelled_evaluation_rows:0,precision:null,recall:null,
          seconds:1,calibration_end:body.calibration_end}];value=s;
      }else throw new Error('Unexpected test request '+path);
      const copy=JSON.parse(JSON.stringify(value));return {ok:true,json:async()=>copy};
    }});
  new vm.Script(source).runInContext(context);
  const tick=async()=>{for(let i=0;i<6;i++)await new Promise(resolve=>setImmediate(resolve));};
  return {nodes,states,requests,tick,failNext(){failNextWrite=true;},delay(value){delayStatus=value;},
    async submit(id){nodes[id].listeners.submit({preventDefault(){}});await tick();},
    async change(id,value){nodes[id].value=value;nodes[id].listeners.change();await tick();}};
}

test('web starts with data update, then enables ML and gates CatBoost without labels',async()=>{
  const h=harness();await h.tick();
  assert.equal(h.nodes['ml-update'].disabled,false);
  assert.equal(h.nodes['ml-evaluate'].disabled,true);
  await h.submit('ml-data-form');
  assert.equal(h.nodes['ml-evaluate'].disabled,false);
  assert.equal(h.nodes['ml-algorithm'].options.find(o=>o.value==='catboost').disabled,true);
  assert.match(h.nodes['ml-data-summary'].innerHTML,/20 giao dịch/);
});
test('evaluate sends company/version and timezone windows, never auto activates',async()=>{
  const h=harness();await h.tick();await h.submit('ml-data-form');
  h.nodes['ml-train-end'].value='2024-05-01T12:30';h.nodes['ml-calibration-end'].value='2024-08-01T12:30';
  await h.change('ml-algorithm','lof');await h.submit('ml-evaluate-form');
  const call=h.requests.find(r=>r.path.endsWith('/evaluate'));
  assert.equal(call.body.company_id,'C001');assert.equal(call.body.expected_revision,'revision-C001');
  assert.equal(call.body.train_end,'2024-05-01T12:30:00+07:00');assert.equal(call.body.algorithm,'lof');
  assert.equal(h.requests.filter(r=>r.path.endsWith('/activate')).length,0);
  assert.match(h.nodes['ml-versions'].innerHTML,/Xác nhận dùng v1/);
});
test('failed write preserves date draft and never replays POST',async()=>{
  const h=harness();await h.tick();await h.submit('ml-data-form');
  h.nodes['ml-train-end'].value='2024-03-02T10:35';h.failNext();
  const before=h.requests.filter(r=>r.body).length;await h.submit('ml-evaluate-form');
  assert.match(h.nodes['ml-notice'].textContent,/Mất kết nối/);
  assert.equal(h.nodes['ml-train-end'].value,'2024-03-02T10:35');
  assert.equal(h.requests.filter(r=>r.body).length,before+1);
});
test('switching company clears old versions and disables training until new data is ready',async()=>{
  const h=harness();await h.tick();await h.submit('ml-data-form');await h.submit('ml-evaluate-form');
  await h.change('ml-company','C002');
  assert.equal(h.nodes['ml-evaluate'].disabled,true);assert.doesNotMatch(h.nodes['ml-versions'].innerHTML,/Xác nhận dùng v1/);
  assert.match(h.nodes['ml-current'].innerHTML,/chưa có model/);
  await h.submit('ml-data-form');
  const last=h.requests.filter(r=>r.path.endsWith('/data-update')).at(-1);
  assert.equal(last.body.company_id,'C002');assert.equal(last.body.expected_revision,null);
});
