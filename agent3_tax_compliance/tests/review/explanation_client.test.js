// Exercises async stale-result handling and untrusted text with a small DOM harness.
const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');
class Element{constructor(){this.children=[];this.handlers={};this.hidden=false;this.disabled=false;this.textContent='';this.checked=false;}
 append(...items){this.children.push(...items);}replaceChildren(...items){this.children=items;}addEventListener(name,fn){this.handlers[name]=fn;}}
const ids=new Map();const html=fs.readFileSync('src/review/static/index.html','utf8');
for(const match of html.matchAll(/id="([^"]+)"/g)){assert(!ids.has(match[1]));ids.set(match[1],new Element());}
const code=fs.readFileSync('src/review/static/explanation.js','utf8');
for(const match of code.matchAll(/\$\('([^']+)'\)/g))assert(ids.has(match[1]),'Missing DOM ID '+match[1]);
const events={};let handler=async()=>({explanation:null});
const context={$:id=>ids.get(id),document:{addEventListener:(name,fn)=>events[name]=fn},
 element:(tag,text)=>{const el=new Element();el.textContent=text||'';return el;},
 state:{saving:false},compliance:{current:null},snapshotDraft:()=>[],crypto:{randomUUID:()=> 'request-key'},
 api:(...args)=>handler(...args),perform:fn=>fn(),console};
vm.createContext(context);vm.runInContext(code+'\nglobalThis.ui={clearExplanation,loadExplanation,generateExplanation,renderExplanation,explanationView};',context);
async function main(){
 const {ui}=context;const view={evaluation_id:'evaluation-a',record_revision:2,report:{}};
 context.compliance.current=view;await ui.loadExplanation(view);assert.equal(ids.get('explanation-detail').hidden,false);
 const item={mode:'TEMPLATE',fallback_reason:'LLM_DISABLED',record_revision:2,claims:[{text:'<img src=x onerror=alert(1)>',refs:['evaluation:a']}],excerpts:[]};
 handler=async()=>item;await ui.generateExplanation();assert.match(ids.get('explanation-status').textContent,/bản dữ liệu 2/);
 assert.equal(ids.get('explanation-claims').children[0].children[0].textContent,item.claims[0].text);
 assert.equal(ids.get('generate-explanation').disabled,false);
 let resolve;handler=()=>new Promise(r=>resolve=r);
 const pending=ui.generateExplanation();ui.clearExplanation();resolve(item);await pending;
 assert.equal(ids.get('explanation-detail').hidden,true);assert.equal(ids.get('explanation-claims').children.length,0);
 context.compliance.current=view;ui.clearExplanation(view);context.state.saving=true;
 await assert.rejects(()=>ui.generateExplanation(),/Lưu hoặc bỏ/);context.state.saving=false;
 handler=async()=>{throw new Error('offline');};await assert.rejects(()=>ui.generateExplanation(),/offline/);
 assert.match(ids.get('explanation-status').textContent,/giải thích gốc/);assert.equal(ids.get('generate-explanation').disabled,false);
 assert.equal(ui.explanationView.key,'request-key');
 handler=async()=>({explanation:item});await ui.loadExplanation(view);events['agent3:record-opened']();
 assert.equal(ids.get('explanation-detail').hidden,true);assert.equal(ids.get('explanation-claims').children.length,0);
 console.log('Explanation DOM: escaped text, pending/reset, draft guard, failure/retry, revision reset PASS');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
