"use strict";
const {test}=require('node:test');
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');

function harness(){
  const source=fs.readFileSync('review_ui/company_ml.js','utf8'),html=fs.readFileSync('review_ui/company_ml.html','utf8');
  const nodes={};
  for(const [,id] of html.matchAll(/id="([^"]+)"/g)){
    const node={id,value:'',disabled:false,hidden:true,textContent:'',className:'',listeners:{},files:[],options:[],
      addEventListener(name,fn){this.listeners[name]=fn;},setAttribute(name,value){this[name]=value;},focus(){},querySelectorAll(){return [];}};
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
  const requests=[];let failNextWrite=false,delayStatus=null,delayReadiness=null,failReadiness=false;
  const policies={},labelPlans={};let delayLabels=null;
  const overview={can_manage:true,mode:'shadow',companies:[{company_id:'C001',name:'One'},{company_id:'C002',name:'Two'}],
    algorithms:['isolation_forest','autoencoder','ecod','lof','catboost'].map(id=>({id,label:id,installed:true,requires_labels:id==='catboost'}))};
  const context=vm.createContext({document:{getElementById:id=>nodes[id]},URLSearchParams,console,setTimeout,clearTimeout,
    fetch:async(path,options)=>{
      const body=options?.body?JSON.parse(options.body):null;requests.push({path,body});
      if(body&&failNextWrite){failNextWrite=false;throw new Error('offline');}
      let value;
      if(path==='/api/meta')value={csrf_token:'TEST_TOKEN',scenarios:['003'],default_scenario:'003',qa:true};
      else if(path.startsWith('/api/company-ml/status')){
        const company=new URLSearchParams(path.split('?')[1]).get('company');
        if(delayStatus)await delayStatus;
        value=states[company];
      }else if(path.startsWith('/api/company-ml/readiness?')){
        const query=new URLSearchParams(path.split('?')[1]),company=query.get('company'),s=states[company];
        if(failReadiness){failReadiness=false;throw new Error('offline');}
        const policy=typeof policies[company]==='function'?policies[company](query):policies[company]||{};
        value={company_id:company,scenario:query.get('scenario'),data_revision:s.data?.revision||null,active_version:s.active_version,
          evaluation:{eligible:true,reason:'',train_rows:10,calibration_rows:5,evaluation_rows:5},
          catboost:{eligible:false,reason:'CatBoost: thiếu nhãn cho kỳ train.',train_rows:10,verified_train_rows:0,class_counts:{'0':0,'1':0}},
          model:{compatible:!!s.active_version,can_keep:!!s.active_version,can_score:!!s.active_version,inference_rows:5,
            reason:s.active_version?'':'Xác nhận model trước khi chấm.'},...policy};
        value=JSON.parse(JSON.stringify(value));
        const wait=delayReadiness;delayReadiness=null;if(wait)await wait;
      }else if(path.startsWith('/api/company-ml?')||path==='/api/company-ml')value=overview;
      else if(path.endsWith('/data-update')){
        const s=states[body.company_id];s.data={revision:'revision-'+body.company_id,scenario:'003',columns:['x'],rows:20,labels_count:0,
          first_at:'2024-01-01T00:00:00+07:00',last_at:'2025-01-01T00:00:00+07:00',
          suggested_windows:{train_end:'2024-06-01T00:00:00+07:00',calibration_end:'2024-09-01T00:00:00+07:00'}};value=s;
      }else if(path.endsWith('/labels-preview')){
        value={company_id:body.company_id,scenario:body.scenario,expected_revision:body.expected_revision,preview_hash:'PREVIEW',
          counts:{existing:15,incoming:1,added:0,unchanged:1,conflicts:0,total:15},conflicts:[],...labelPlans[body.company_id]};
        const wait=delayLabels;delayLabels=null;if(wait)await wait;
      }else if(path.endsWith('/labels-update')){
        const s=states[body.company_id],plan=labelPlans[body.company_id]||{},counts=plan.counts||{existing:15,incoming:1,added:0,unchanged:1,conflicts:0,total:15};
        s.data.labels_count=counts.total;
        if(counts.added||(counts.conflicts&&body.conflict_policy==='replace_conflicts'))s.data.revision+='-labels';
        value={...s,label_update:{...counts,updated:body.conflict_policy==='replace_conflicts'?counts.conflicts:0,
          skipped:body.conflict_policy==='keep_existing'?counts.conflicts:0,policy:body.conflict_policy}};
      }else if(path.endsWith('/evaluate')){
        const s=states[body.company_id];s.versions=[{version_id:'V1',number:1,algorithm:body.algorithm,data_revision:s.data.revision,
          evaluation_rows:5,evaluation_alerts:0,evaluation_alert_rate:0,labelled_evaluation_rows:0,precision:null,recall:null,
          seconds:1,calibration_end:body.calibration_end}];value=s;
      }else throw new Error('Unexpected test request '+path);
      const copy=JSON.parse(JSON.stringify(value));return {ok:true,json:async()=>copy};
    }});
  new vm.Script(source).runInContext(context);
  const tick=async()=>{for(let i=0;i<6;i++)await new Promise(resolve=>setImmediate(resolve));};
  return {nodes,states,requests,tick,overview,policies,labelPlans,delayNextLabels(value){delayLabels=value;},failNext(){failNextWrite=true;},delay(value){delayStatus=value;},
    delayNextReadiness(value){delayReadiness=value;},failNextReadiness(){failReadiness=true;},
    async reload(){nodes['ml-reload'].listeners.click();await tick();},
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

async function labelHarness(plan){
  const h=harness();await h.tick();await h.submit('ml-data-form');
  h.states.C001.data.source='csv_excel_upload';h.states.C001.data.labels_count=15;await h.reload();
  if(plan)h.labelPlans.C001=plan;
  h.nodes['ml-labels'].files=[{size:80,text:async()=> 'SIM_LABEL_CSV'}];h.nodes['ml-labels'].listeners.change();
  return h;
}
const conflictPlan={counts:{existing:15,incoming:2,added:1,unchanged:0,conflicts:1,total:16},
  conflicts:[{transaction_id:'<SIM_TRANSACTION>',existing:{label:0,reviewer_id:'SIM_OLD',reviewed_at:'2024-01-02T00:00:00+07:00',evidence_ref:'<SIM_OLD>'},
    incoming:{label:1,reviewer_id:'SIM_NEW',reviewed_at:'2024-01-03T00:00:00+07:00',evidence_ref:'<SIM_NEW>'}}]};

test('labels are previewed without writing and an identical upload reports fifteen to fifteen',async()=>{
  const h=await labelHarness();await h.submit('ml-data-form');
  assert.equal(h.requests.filter(r=>r.path.endsWith('/labels-update')).length,0);
  assert.equal(h.nodes['ml-label-preview'].hidden,false);assert.equal(h.nodes['ml-label-save'].disabled,false);
  assert.match(h.nodes['ml-label-counts'].textContent,/Đang có 15 nhãn/);
  h.nodes['ml-label-save'].listeners.click();await h.tick();
  const call=h.requests.find(r=>r.path.endsWith('/labels-update'));
  assert.equal(call.body.labels_text,'SIM_LABEL_CSV');assert.equal(call.body.preview_hash,'PREVIEW');assert.equal(call.body.conflict_policy,'reject');
  assert.match(h.nodes['ml-notice'].textContent,/15 → 15/);assert.equal(h.nodes['ml-label-preview'].hidden,true);
});

test('conflicts require a choice and corrections require reason plus confirmation',async()=>{
  const h=await labelHarness(conflictPlan);await h.submit('ml-data-form');
  assert.equal(h.nodes['ml-label-save'].disabled,true);assert.match(h.nodes['ml-label-conflicts'].innerHTML,/&lt;SIM_OLD&gt;/);
  assert.doesNotMatch(h.nodes['ml-label-conflicts'].innerHTML,/<SIM_NEW>/);
  await h.change('ml-label-policy','replace_conflicts');
  assert.equal(h.nodes['ml-label-correction-fields'].hidden,false);assert.equal(h.nodes['ml-label-save'].disabled,true);
  h.nodes['ml-label-reason'].value='SIM: verified correction';h.nodes['ml-label-reason'].listeners.input();
  assert.equal(h.nodes['ml-label-save'].disabled,true);
  h.nodes['ml-label-acknowledge'].checked=true;h.nodes['ml-label-acknowledge'].listeners.input();
  assert.equal(h.nodes['ml-label-save'].disabled,false);
  h.nodes['ml-label-save'].listeners.click();await h.tick();
  const call=h.requests.find(r=>r.path.endsWith('/labels-update'));
  assert.equal(call.body.conflict_policy,'replace_conflicts');assert.equal(call.body.acknowledge,true);assert.equal(call.body.reason,'SIM: verified correction');
  assert.match(h.nodes['ml-notice'].textContent,/15 → 16/);assert.match(h.nodes['ml-notice'].textContent,/sửa 1/);
});

test('keeping existing conflicts saves new labels without correction confirmation',async()=>{
  const h=await labelHarness(conflictPlan);await h.submit('ml-data-form');await h.change('ml-label-policy','keep_existing');
  assert.equal(h.nodes['ml-label-save'].disabled,false);assert.equal(h.nodes['ml-label-correction-fields'].hidden,true);
  h.nodes['ml-label-save'].listeners.click();await h.tick();
  assert.equal(h.requests.find(r=>r.path.endsWith('/labels-update')).body.conflict_policy,'keep_existing');
  assert.match(h.nodes['ml-notice'].textContent,/giữ nhãn cũ do xung đột 1/);
});

test('cancel and changed file discard the preview without mutating labels',async()=>{
  const h=await labelHarness(conflictPlan);await h.submit('ml-data-form');
  h.nodes['ml-label-cancel'].listeners.click();await h.tick();assert.equal(h.nodes['ml-label-preview'].hidden,true);
  assert.equal(h.requests.filter(r=>r.path.endsWith('/labels-update')).length,0);
  await h.submit('ml-data-form');h.nodes['ml-labels'].listeners.change();
  assert.equal(h.nodes['ml-label-preview'].hidden,true);assert.equal(h.nodes['ml-label-save'].disabled,true);
});

test('failed label save retains the decision and never automatically repeats the mutation',async()=>{
  const h=await labelHarness(conflictPlan);await h.submit('ml-data-form');await h.change('ml-label-policy','keep_existing');
  h.failNext();h.nodes['ml-label-save'].listeners.click();await h.tick();
  assert.equal(h.requests.filter(r=>r.path.endsWith('/labels-update')).length,1);
  assert.equal(h.nodes['ml-label-preview'].hidden,false);assert.equal(h.nodes['ml-label-policy'].value,'keep_existing');
  assert.match(h.nodes['ml-notice'].textContent,/Mất kết nối/);
});

test('late label preview from another company cannot become a saveable draft',async()=>{
  const h=await labelHarness();let release;h.delayNextLabels(new Promise(resolve=>{release=resolve;}));
  await h.submit('ml-data-form');await h.change('ml-company','C002');release();await h.tick();
  assert.equal(h.nodes['ml-label-preview'].hidden,true);assert.equal(h.nodes['ml-label-save'].disabled,true);
  assert.equal(h.requests.filter(r=>r.path.endsWith('/labels-update')).length,0);
});
test('evaluate sends company/version and timezone windows, never auto activates',async()=>{
  const h=harness();await h.tick();await h.submit('ml-data-form');
  await h.change('ml-train-end','2024-05-01T12:30');await h.change('ml-calibration-end','2024-08-01T12:30');
  await h.change('ml-algorithm','lof');await h.submit('ml-evaluate-form');
  const call=h.requests.find(r=>r.path.endsWith('/evaluate'));
  assert.equal(call.body.company_id,'C001');assert.equal(call.body.expected_revision,'revision-C001');
  assert.equal(call.body.train_end,'2024-05-01T12:30:00+07:00');assert.equal(call.body.algorithm,'lof');
  assert.equal(h.requests.filter(r=>r.path.endsWith('/activate')).length,0);
  assert.match(h.nodes['ml-versions'].innerHTML,/Xác nhận dùng v1/);
});
test('failed write preserves date draft and never replays POST',async()=>{
  const h=harness();await h.tick();await h.submit('ml-data-form');
  await h.change('ml-train-end','2024-03-02T10:35');h.failNext();
  const before=h.requests.filter(r=>r.body).length;await h.submit('ml-evaluate-form');
  assert.match(h.nodes['ml-notice'].textContent,/Mất kết nối/);
  assert.equal(h.nodes['ml-train-end'].value,'2024-03-02T10:35');
  assert.equal(h.requests.filter(r=>r.body).length,before+1);
});

test('CatBoost follows backend coverage for selected period rather than overall label count',async()=>{
  const h=harness();await h.tick();await h.submit('ml-data-form');
  h.states.C001.data.labels_count=100;
  h.policies.C001={catboost:{eligible:false,reason:'1/10 dòng train có nhãn hợp lệ.',train_rows:10,verified_train_rows:1,class_counts:{'0':1,'1':0}}};
  await h.reload();
  assert.equal(h.nodes['ml-algorithm'].options.find(o=>o.value==='catboost').disabled,true);
  assert.match(h.nodes['ml-catboost-readiness'].textContent,/1\/10/);
  h.policies.C001={catboost:{eligible:true,reason:'',train_rows:10,verified_train_rows:10,class_counts:{'0':5,'1':5}}};
  await h.change('ml-train-end','2024-05-01T12:00');
  assert.equal(h.nodes['ml-algorithm'].options.find(o=>o.value==='catboost').disabled,false);
  assert.match(h.nodes['ml-catboost-readiness'].textContent,/10\/10/);
  await h.change('ml-algorithm','catboost');assert.equal(h.nodes['ml-evaluate'].disabled,false);
  await h.submit('ml-evaluate-form');assert.equal(h.requests.find(r=>r.path.endsWith('/evaluate')).body.algorithm,'catboost');
});

test('editing a period locks immediately and keeps CatBoost selection when new period is ineligible',async()=>{
  const h=harness();await h.tick();await h.submit('ml-data-form');
  h.policies.C001={catboost:{eligible:true,reason:'',train_rows:10,verified_train_rows:10,class_counts:{'0':5,'1':5}}};
  await h.reload();await h.change('ml-algorithm','catboost');
  h.nodes['ml-train-end'].value='2024-07-01T12:00';h.nodes['ml-train-end'].listeners.input();
  assert.equal(h.nodes['ml-evaluate'].disabled,true);
  assert.equal(h.nodes['ml-algorithm'].options.find(o=>o.value==='catboost').disabled,true);
  h.policies.C001={catboost:{eligible:false,reason:'Có nhãn biết muộn trong kỳ train.',train_rows:12,verified_train_rows:10,class_counts:{'0':5,'1':5}}};
  await h.change('ml-train-end','2024-07-01T12:00');
  assert.equal(h.nodes['ml-algorithm'].value,'catboost');assert.equal(h.nodes['ml-evaluate'].disabled,true);
  const before=h.requests.filter(r=>r.body).length;await h.submit('ml-evaluate-form');
  assert.equal(h.requests.filter(r=>r.body).length,before);
  assert.match(h.nodes['ml-catboost-readiness'].textContent,/biết muộn/);
});

test('incompatible active model locks scoring and keep while allowing an eligible new candidate',async()=>{
  const h=harness();await h.tick();await h.submit('ml-data-form');h.states.C001.active_version='OLD';
  h.policies.C001={model:{compatible:false,can_keep:false,can_score:false,inference_rows:0,reason:'Nguồn mới khác hợp đồng feature/định dạng.'}};
  await h.reload();
  assert.equal(h.nodes['ml-score'].disabled,true);assert.equal(h.nodes['ml-keep'].disabled,true);
  assert.equal(h.nodes['ml-evaluate'].disabled,false);assert.match(h.nodes['ml-score-readiness'].textContent,/khác hợp đồng/);
  const before=h.requests.filter(r=>r.body).length;h.nodes['ml-score'].listeners.click();await h.tick();
  assert.equal(h.requests.filter(r=>r.body).length,before);
  h.policies.C001={model:{compatible:true,can_keep:true,can_score:true,inference_rows:5,reason:''}};
  await h.reload();assert.equal(h.nodes['ml-score'].disabled,false);assert.equal(h.nodes['ml-keep'].disabled,false);
});

test('no inference rows blocks scoring independently of keep',async()=>{
  const h=harness();await h.tick();await h.submit('ml-data-form');h.states.C001.active_version='OLD';
  h.policies.C001={model:{compatible:true,can_keep:true,can_score:false,inference_rows:0,reason:'Không có giao dịch ngoài kỳ train/calibration.'}};
  await h.reload();assert.equal(h.nodes['ml-score'].disabled,true);assert.equal(h.nodes['ml-keep'].disabled,false);
});

test('readiness failure closes actions and explicit reload recovers without replaying a POST',async()=>{
  const h=harness();await h.tick();await h.submit('ml-data-form');h.states.C001.active_version='OLD';
  h.failNextReadiness();await h.reload();
  assert.equal(h.nodes['ml-score'].disabled,true);assert.equal(h.nodes['ml-keep'].disabled,true);
  assert.equal(h.nodes['ml-evaluate'].disabled,true);assert.match(h.nodes['ml-score-readiness'].textContent,/Mất kết nối/);
  const writes=h.requests.filter(r=>r.body).length;await h.reload();
  assert.equal(h.nodes['ml-score'].disabled,false);assert.equal(h.nodes['ml-evaluate'].disabled,false);
  assert.equal(h.requests.filter(r=>r.body).length,writes);
});

test('failed scoring refreshes backend eligibility without replaying the mutation',async()=>{
  const h=harness();await h.tick();await h.submit('ml-data-form');h.states.C001.active_version='OLD';await h.reload();
  assert.equal(h.nodes['ml-score'].disabled,false);
  h.policies.C001={model:{compatible:false,can_keep:false,can_score:false,inference_rows:0,reason:'Model vừa thay đổi hoặc không còn tương thích.'}};
  h.failNext();const writes=h.requests.filter(r=>r.body).length;
  h.nodes['ml-score'].listeners.click();await h.tick();
  assert.equal(h.requests.filter(r=>r.body).length,writes+1);
  assert.equal(h.nodes['ml-score'].disabled,true);assert.equal(h.nodes['ml-keep'].disabled,true);
  assert.match(h.nodes['ml-score-readiness'].textContent,/không còn tương thích/);
});

test('late readiness reply from old period cannot reopen CatBoost',async()=>{
  const h=harness();await h.tick();await h.submit('ml-data-form');
  h.policies.C001={catboost:{eligible:true,reason:'',train_rows:10,verified_train_rows:10,class_counts:{'0':5,'1':5}}};
  let release;h.delayNextReadiness(new Promise(resolve=>{release=resolve;}));
  await h.change('ml-train-end','2024-05-01T12:00');
  h.policies.C001={catboost:{eligible:false,reason:'Thiếu nhãn cho kỳ mới.',train_rows:12,verified_train_rows:10,class_counts:{'0':5,'1':5}}};
  await h.change('ml-train-end','2024-07-01T12:00');release();await h.tick();
  assert.equal(h.nodes['ml-algorithm'].options.find(o=>o.value==='catboost').disabled,true);
  assert.match(h.nodes['ml-catboost-readiness'].textContent,/kỳ mới/);
});

test('late readiness reply from another company cannot enable its actions',async()=>{
  const h=harness();await h.tick();await h.submit('ml-data-form');h.states.C001.active_version='OLD';
  let release;h.delayNextReadiness(new Promise(resolve=>{release=resolve;}));await h.reload();
  await h.change('ml-company','C002');release();await h.tick();
  assert.equal(h.nodes['ml-score'].disabled,true);assert.equal(h.nodes['ml-evaluate'].disabled,true);
  assert.equal(h.nodes['ml-algorithm'].options.find(o=>o.value==='catboost').disabled,true);
});

test('read-only role never gains write controls from an eligible readiness response',async()=>{
  const h=harness();await h.tick();await h.submit('ml-data-form');h.states.C001.active_version='OLD';h.overview.can_manage=false;
  await h.reload();assert.equal(h.nodes['ml-score'].disabled,true);assert.equal(h.nodes['ml-keep'].disabled,true);
  assert.equal(h.nodes['ml-evaluate'].disabled,true);assert.equal(h.nodes['ml-update'].disabled,true);
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
