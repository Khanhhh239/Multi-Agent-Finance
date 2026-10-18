// Dependency-free DOM harness. It checks client behavior, not browser layout/accessibility acceptance.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
class Element{
 constructor(){this.children=[];this.handlers={};this.value='';this.hidden=false;this.checked=false;this.disabled=false;this.textContent='';this.style={};this.classList={add(){},remove(){},toggle(){}};}
 append(...children){this.children.push(...children);}
 replaceChildren(...children){this.children=children;}
 addEventListener(type,handler){this.handlers[type]=handler;}
 setAttribute(key,value){this[key]=value;}
 getAttribute(key){return this[key];}
 get firstElementChild(){return this.children[0];}
 click(){}
}
const ids=new Map();const calls=[];
const html=fs.readFileSync('src/review/static/index.html','utf8');
for(const match of html.matchAll(/id="([^"]+)"/g)){assert(!ids.has(match[1]),'duplicate DOM ID');ids.set(match[1],new Element());}
const code=fs.readFileSync('src/review/static/app.js','utf8');
for(const match of code.matchAll(/\$\('([^']+)'\)/g))assert(ids.has(match[1]),'missing DOM ID '+match[1]);
const events=[];
const context={CustomEvent:class{constructor(type,options){this.type=type;this.detail=options?.detail;}},document:{dispatchEvent:event=>events.push(event),getElementById:id=>ids.get(id),createElement:()=>new Element(),createElementNS:()=>new Element()},
 location:{origin:'http://127.0.0.1:8000'},window:{addEventListener(){},confirm:()=>true},navigator:{},URL,Blob,crypto:{randomUUID:()=> 'functional-id'},console,setTimeout,clearTimeout,
 fetch:async(url,options)=>{calls.push({url:String(url),options});return {ok:true,json:async()=>({token:'signed-proof',geometry_available:true}),blob:async()=>new Blob(['png'])};}};
vm.createContext(context);vm.runInContext(code+'\nglobalThis.client={state,api,getField,renderFields,syncVat,showPage,message,reset,showField,formatDecimalVI,parseDecimalVI,canonicalValue,displayValue,showConflict};',context);
async function main(){
 const c=context.client;
 await assert.rejects(()=>c.api('/v1/records'),/token/);
 c.state.token='test-memory-only';c.state.payer='payer-a';
 const field=value=>({status:'PRESENT',value,confidence_basis:'UNAVAILABLE'});
 c.state.view={extraction_artifact_id:'artifact-a',page_count:1,record:{parties:{seller:{tax_id:field('1234567890')},buyer:{}},invoice:{},totals:{},items:[{item_id:'immutable-item',line_number:3,net:field('100.01'),vat_treatment:field('KCT'),vat_rate:{status:'NOT_APPLICABLE',value:null}}]}};
 assert.equal(c.getField(c.state.view.record,'items.immutable-item.net').value,'100.01');
 assert.equal(c.getField(c.state.view.record,'items.other.net'),undefined);
 c.renderFields();assert.equal(c.state.edits.size,19);assert.equal(c.state.edits.get('items.immutable-item.vat_rate').input.disabled,true);
 assert.equal(c.formatDecimalVI('12345678901234567890.1234'),'12.345.678.901.234.567.890,1234');
 assert.equal(c.parseDecimalVI('12.345.678.901.234.567.890,1234'),'12345678901234567890.1234');
 assert.throws(()=>c.parseDecimalVI('1.23'),/định dạng/);
 assert.equal(c.canonicalValue('invoice.issue_date','02/12/2023'),'2023-12-02');
 assert.throws(()=>c.canonicalValue('invoice.issue_date','31/02/2023'),/tồn tại/);
 assert.equal(c.canonicalValue('items.id.vat_rate','8,5'),'0.085');
 assert.equal(c.displayValue('items.id.vat_rate','0.085'),'8,5');
 const treatment=c.state.edits.get('items.immutable-item.vat_treatment');treatment.input.value='TAXABLE_RATE';treatment.input.handlers.input();assert.equal(treatment.checked.checked,true);assert.equal(c.state.edits.get('items.immutable-item.vat_rate').input.disabled,false);
 const rate=c.state.edits.get('items.immutable-item.vat_rate');rate.input.value='8,5';rate.checked.checked=true;
 treatment.input.value='KCT';treatment.input.handlers.input();assert.equal(rate.input.value,'');assert.equal(rate.checked.checked,false);
 treatment.input.value='TAXABLE_RATE';treatment.input.handlers.input();assert.equal(rate.input.value,'8,5');assert.equal(rate.checked.checked,true);
 await c.showPage(0,[{page_index:0,bbox:[.1,.2,.4,.5]}]);assert.equal(ids.get('overlay').children.length,1);
 assert.equal(Number(ids.get('overlay').children[0].width),.4-.1);
 assert(calls.every(call=>call.options.headers.Authorization==='Bearer test-memory-only'));
 assert(calls.every(call=>!call.url.includes('signed-proof')&&!call.url.includes('test-memory-only')));
 assert.equal(JSON.parse(calls[1].options.body).token,'signed-proof');
 c.state.view.candidates=[{candidate_id:'candidate-a',semantic_field:'seller.tax_id',raw_value:'1234567890',normalized_value:'1234567890',evidence_refs:[{page_index:0,bbox:[.1,.2,.4,.5]}]}];
 const seller=c.state.edits.get('parties.seller.tax_id');seller.input.value='9876543210';seller.checked.checked=false;
 await c.showField('parties.seller.tax_id');
 assert.equal(events.at(-1).type,'agent3:field-selected');assert.equal(events.at(-1).detail.path,'parties.seller.tax_id');
 assert.equal(seller.input.value,'9876543210','viewing source must not apply a candidate');assert.equal(seller.checked.checked,false);
 const candidateActions=ids.get('candidates').children[0].children[1];await candidateActions.children[1].handlers.click();
 assert.equal(seller.input.value,'1234567890');assert.equal(seller.checked.checked,true);
 seller.checked.checked=false;c.showConflict([{path:'parties.seller.tax_id',value:'9876543210',before:'1234567890'}]);
 assert.equal(c.state.conflictDraft.length,1);assert.equal(seller.checked.checked,false,'conflict must not silently overwrite latest');
 c.message('<img src=x onerror=alert(1)>',true);assert.equal(ids.get('status').textContent,'<img src=x onerror=alert(1)>');
 context.fetch=async()=>({ok:false,status:409,json:async()=>({error:{latest_revision:2}})});
 await assert.rejects(()=>c.api('/v1/corrections',{method:'POST',body:{}}),error=>error.status===409);
 c.reset();assert.equal(c.state.view,null);assert.equal(ids.get('workspace').hidden,true);
 console.log('PASS client: DOM IDs, field identity, exempt VAT, signed image/bbox, memory auth, safe text, conflict and reset.');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
