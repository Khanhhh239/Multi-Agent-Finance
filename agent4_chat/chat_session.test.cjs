const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

class Element {
  constructor() { this.nodeType = 1; this.children = []; this.value = ''; this.disabled = false; this.dataset = {}; this.classList = {remove(){},add(){}}; }
  append(...items) { this.children.push(...items); }
  prepend(...items) { this.children.unshift(...items); }
  replaceChildren(...items) { this.children = items; }
  setAttribute() {}
  addEventListener() {}
  scrollIntoView() {}
  focus() {}
}
function deferred() {
  let resolve;
  const promise = new Promise(r => { resolve = r; });
  return {promise, resolve};
}

test('reset discards a pending response without changing the new conversation or send state', async () => {
  const nodes = new Map(['thread','question','send'].map(id => [id,new Element()]));
  const storage = new Map();
  const requests = [];
  const sandbox = {
    window: {}, document: {getElementById:id=>nodes.get(id),createElement:()=>new Element()},
    sessionStorage: {getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value)},
    crypto: require('node:crypto').webcrypto, console, Intl, BigInt, Date,
    fetch: (url, opts) => { const task=deferred(); requests.push({...task,body:JSON.parse(opts.body)}); return task.promise; }
  };
  const script = fs.readFileSync(path.join(__dirname,'chat.js'),'utf8').replace('  // Wire up DOM', '  window.__test = {ask, resetConversation, context: () => ({sessionId,lastAnswered,activeClarification})};\n  // Wire up DOM');
  vm.runInNewContext(script,sandbox);
  const api=sandbox.window.__test;
  const oldAsk=api.ask('Doanh thu quý 3?');
  assert.equal(nodes.get('send').disabled,true);
  api.resetConversation();
  assert.equal(nodes.get('send').disabled,false);
  const resetSession=api.context().sessionId;
  const newAsk=api.ask('Tiền mặt cuối tháng 8?');
  assert.equal(requests.length,2);
  assert.equal(requests[1].body.session_id,resetSession);
  requests[0].resolve({ok:true,status:200,json:async()=>({status:'needs_clarification',session_id:'stale-session',clarification:{session_id:'stale-clarification'}})});
  await oldAsk;
  assert.equal(api.context().sessionId,resetSession);
  assert.equal(api.context().activeClarification,null);
  assert.equal(api.context().lastAnswered,null);
  assert.equal(nodes.get('send').disabled,true, 'old completion must not enable send while new request is pending');
  requests[1].resolve({ok:true,status:200,json:async()=>({status:'ready',session_id:'new-session',answer:'100 đồng'})});
  await newAsk;
  assert.equal(api.context().sessionId,'new-session');
  assert.equal(api.context().lastAnswered.question,'Tiền mặt cuối tháng 8?');
  assert.equal(nodes.get('send').disabled,false);
});
