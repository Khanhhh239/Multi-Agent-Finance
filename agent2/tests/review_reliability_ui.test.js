"use strict";
const {test}=require('node:test');
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function harness(file,responses){
  const source=fs.readFileSync(file,'utf8');
  const start=source.indexOf('async function api('),end=source.indexOf('\nfunction notice(',start);
  assert.ok(start>=0&&end>start);
  const calls=[],context=vm.createContext({
    state:{meta:{csrf_token:'old'}},
    fetch:async(path,options)=>{calls.push({path,options});const next=responses.shift();if(next instanceof Error)throw next;return next;}
  });
  vm.runInContext(source.slice(start,end),context);
  return {api:vm.runInContext('api',context),context,calls};
}
const response=(status,result)=>({status,ok:status===200,json:async()=>result});
for(const [file,meta] of [['review_ui/app.js','/api/meta'],['review_ui/p2_controls.js','/api/p2-controls/meta']]){
  test(`${file}: dropped request is localized and never replayed`,async()=>{
    const h=harness(file,[new TypeError('Failed to fetch')]);
    await assert.rejects(h.api('/write',{reason:'Draft'}),/Mất kết nối.*lịch sử/);
    assert.equal(h.calls.length,1);
    assert.equal(JSON.parse(h.calls[0].options.body).reason,'Draft');
  });
  test(`${file}: invalid response does not become a success`,async()=>{
    const h=harness(file,[{ok:true,json:async()=>{throw new SyntaxError('Unexpected <');}}]);
    await assert.rejects(h.api('/read'),/dữ liệu chưa đọc được/);assert.equal(h.calls.length,1);
  });
  test(`${file}: restart refreshes metadata without replaying the write`,async()=>{
    const h=harness(file,[response(403,{error:'Phiên làm việc đã thay đổi. Tải lại trang để tiếp tục.'}),response(200,{csrf_token:'fresh'}),response(200,{saved:true})]);
    const body={reason:'Draft'};
    await assert.rejects(h.api('/write',body),/đã được nạp lại/);
    assert.deepEqual(h.calls.map(c=>c.path),['/write',meta]);
    assert.equal(JSON.stringify(h.calls[1].options),'{}');
    assert.equal(h.context.state.meta.csrf_token,'fresh');
    assert.equal((await h.api('/write',body)).saved,true);
    assert.equal(h.calls[2].options.headers['X-CSRF-Token'],'fresh');
    assert.equal(h.calls.filter(c=>c.options.method==='POST').length,2);
  });
  test(`${file}: permission rejection does not refresh or retry`,async()=>{
    const h=harness(file,[response(403,{error:'Không có quyền chốt kết luận.'})]);
    await assert.rejects(h.api('/write',{}),/Không có quyền/);assert.equal(h.calls.length,1);
  });
  test(`${file}: metadata failure keeps the existing session and does not write again`,async()=>{
    const h=harness(file,[response(403,{error:'Phiên làm việc đã thay đổi. Tải lại trang để tiếp tục.'}),new TypeError('offline')]);
    await assert.rejects(h.api('/write',{}),/Mất kết nối/);
    assert.equal(h.context.state.meta.csrf_token,'old');assert.equal(h.calls.length,2);
  });
}
test('standalone P2 restart also refreshes its own metadata',async()=>{
  const h=harness('review_ui/p2_controls.js',[response(403,{error:'Phiên đã thay đổi. Tải lại trang để tiếp tục.'}),response(200,{csrf_token:'fresh'})]);
  await assert.rejects(h.api('/api/p2-controls/review',{}),/đã được nạp lại/);
  assert.equal(h.calls[1].path,'/api/p2-controls/meta');
});
