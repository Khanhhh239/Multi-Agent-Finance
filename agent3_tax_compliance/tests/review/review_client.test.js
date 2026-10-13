// Dependency-free DOM harness. It checks client behavior, not browser layout/accessibility acceptance.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
class Element{
 constructor(){this.children=[];this.handlers={};this.value='';this.hidden=false;this.checked=false;this.disabled=false;this.textContent='';this.classList={add(){},remove(){},toggle(){}};}
 append(...children){this.children.push(...children);}
 replaceChildren(...children){this.children=children;}
 addEventListener(type,handler){this.handlers[type]=handler;}
 setAttribute(key,value){this[key]=value;}
 get firstElementChild(){return this.children[0];}
 click(){}
}
const ids=new Map();const calls=[];
const html=fs.readFileSync('src/review/static/index.html','utf8');
for(const match of html.matchAll(/id="([^"]+)"/g)){assert(!ids.has(match[1]),'duplicate DOM ID');ids.set(match[1],new Element());}
const code=fs.readFileSync('src/review/static/app.js','utf8');
for(const match of code.matchAll(/\$\('([^']+)'\)/g))assert(ids.has(match[1]),'missing DOM ID '+match[1]);
const context={document:{getElementById:id=>ids.get(id),createElement:()=>new Element(),createElementNS:()=>new Element()},
 location:{origin:'http://127.0.0.1:8000'},URL,Blob,crypto:{randomUUID:()=> 'functional-id'},console,setTimeout,clearTimeout,prompt:()=>null,
 fetch:async(url,options)=>{calls.push({url:String(url),options});return {ok:true,json:async()=>({token:'signed-proof',geometry_available:true}),blob:async()=>new Blob(['png'])};}};
vm.createContext(context);vm.runInContext(code+'\nglobalThis.client={state,api,getField,renderFields,syncVat,showPage,message,reset};',context);
async function main(){
 const c=context.client;
 await assert.rejects(()=>c.api('/v1/records'),/token/);
 c.state.token='test-memory-only';c.state.payer='payer-a';
 const field=value=>({status:'PRESENT',value,confidence_basis:'UNAVAILABLE'});
 c.state.view={extraction_artifact_id:'artifact-a',page_count:1,record:{parties:{seller:{tax_id:field('1234567890')},buyer:{}},invoice:{},totals:{},items:[{item_id:'immutable-item',line_number:3,net:field('100.01'),vat_treatment:field('KCT'),vat_rate:{status:'NOT_APPLICABLE',value:null}}]}};
 assert.equal(c.getField(c.state.view.record,'items.immutable-item.net').value,'100.01');
 assert.equal(c.getField(c.state.view.record,'items.other.net'),undefined);
 c.renderFields();assert.equal(c.state.edits.size,19);assert.equal(c.state.edits.get('items.immutable-item.vat_rate').input.disabled,true);
 const treatment=c.state.edits.get('items.immutable-item.vat_treatment');treatment.input.value='TAXABLE_RATE';treatment.input.handlers.input();assert.equal(treatment.checked.checked,true);assert.equal(c.state.edits.get('items.immutable-item.vat_rate').input.disabled,false);
 await c.showPage(0,[{page_index:0,bbox:[.1,.2,.4,.5]}]);assert.equal(ids.get('overlay').children.length,1);
 assert.equal(Number(ids.get('overlay').children[0].width),.4-.1);
 assert(calls.every(call=>call.options.headers.Authorization==='Bearer test-memory-only'));
 assert(calls.every(call=>!call.url.includes('signed-proof')&&!call.url.includes('test-memory-only')));
 assert.equal(JSON.parse(calls[1].options.body).token,'signed-proof');
 c.message('<img src=x onerror=alert(1)>',true);assert.equal(ids.get('status').textContent,'<img src=x onerror=alert(1)>');
 context.fetch=async()=>({ok:false,status:409,json:async()=>({error:{latest_revision:2}})});
 await assert.rejects(()=>c.api('/v1/corrections',{method:'POST',body:{}}),error=>error.status===409);
 c.reset();assert.equal(c.state.view,null);assert.equal(ids.get('workspace').hidden,true);
 console.log('PASS client: DOM IDs, field identity, exempt VAT, signed image/bbox, memory auth, safe text, conflict and reset.');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
