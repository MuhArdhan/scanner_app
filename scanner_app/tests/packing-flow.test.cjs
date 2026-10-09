const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.resolve(__dirname, '../www/scanner/index.html'), 'utf8');
const script = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)].at(-1)[1];

function harness(options={}) {
 const listeners = new Map(), elements = new Map(), calls = [], storage = new Map();let created=0;
 if(options.savedPrinter)storage.set('scanner-packing-qz',JSON.stringify(options.savedPrinter));
 const element = id => {
  if (!elements.has(id)) elements.set(id, {value:'', textContent:'', classList:{add(){},remove(){},contains(){return true;},toggle(){}},
   addEventListener(event, fn){listeners.set(id+':'+event,fn);},setAttribute(){},replaceChildren(){},append(){},focus(){},style:{},dataset:{}});
  return elements.get(id);
 };
 let printed = 0;
 const context = {document:{getElementById:element,createElement:()=>element('created-'+created++),querySelector:()=>({content:''}),addEventListener(){},documentElement:{dataset:{}}},window:{addEventListener(){},confirm:()=>true},
  localStorage:{getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)},location:{hash:'#packing',protocol:options.protocol||'https:'},history:{replaceState(){}},navigator:{},
  RemotePackingQz:{settings:value=>require('../public/remote-qz.js').settings(value,options.protocol||'https:')},
   URLSearchParams,console,setTimeout,clearTimeout,PackingLabel:{...require('../public/packing.js'),zpl:()=>'^XA^XZ'},crypto:{randomUUID:()=> '12345678-1234-1234-1234-123456789abc'}};
 const instrumented=script.replace('init();\n})();', `
 call=async(method,args)=>window.mockCall(method,args);
  ${options.render ? '' : 'renderPacking=()=>{};'}savePackingPending=()=>{};message=()=>{};
 ${options.direct ? "getPackingQzSettings=()=>({host:'192.168.1.5',port:8181,printer:'BP-TR110'});getPackingQzClient=()=>({print:async()=>window.printed()});" : 'printPackingBox=async()=>window.printed();'}
 window.flow={scan:submitPackingScan,pending:()=>packingPending,box:()=>packingBox,initSettings:initPackingQzSettings,getSettings:getPackingQzSettings,saveSettings:savePackingQzSettings};
 })();`);
 context.window.mockCall=async(method,args)=>{
  calls.push({method,args});
  if(method==='validate_scan')return {product_qr_serial:args.qr_payload,qr_payload:args.qr_payload,item_code:args.qr_payload==='OTHER'?'I-2':'I-1',batch_no:args.qr_payload,item_name:'Bread'};
  if(method==='finish_packing'){if(options.finishFails)throw Error('Timeout');return {name:'BOX-1',status:'Sealed'};}
  if(method==='print_data')return {name:'BOX-1',status:'Sealed'};
  throw Error('Unexpected '+method);
 };
 context.window.printed=()=>{printed++;if(options.printFails)throw Error('Printer disconnected');};
 vm.runInNewContext(instrumented,context);
 return {flow:context.window.flow,calls,listeners,elements,printed:()=>printed};
}

test('scans stage children without box creation, mixed batch accepted',async()=>{
 const app=harness();await app.flow.scan('A');await app.flow.scan('B');
 assert.equal(app.flow.pending().length,2);assert.equal(app.flow.box(),null);
 assert.deepEqual(app.calls.map(c=>c.method),['validate_scan','validate_scan']);
});
test('duplicate and mixed Item do not change pending count',async()=>{
 const app=harness();await app.flow.scan('A');
 await assert.rejects(app.flow.scan('A'),/sudah ada/);
 await assert.rejects(app.flow.scan('OTHER'),/satu Item/);
 assert.equal(app.flow.pending().length,1);
});
test('finish creates mother after scans, clears staging and then prints',async()=>{
 const app=harness();await app.flow.scan('A');
 await app.listeners.get('packing-seal:click')();
 assert.equal(app.calls.at(-1).method,'finish_packing');
 assert.equal(app.flow.box().status,'Sealed');assert.equal(app.flow.pending().length,0);assert.equal(app.printed(),1);
});
test('finish on empty list cannot allocate a box',async()=>{
 const app=harness();await app.listeners.get('packing-seal:click')();assert.equal(app.calls.length,0);
});
test('failed finalize preserves scan list and retry key',async()=>{
 const app=harness({finishFails:true});await app.flow.scan('A');
 await app.listeners.get('packing-seal:click')();const key=app.calls.at(-1).args.request_key;
 assert.equal(app.flow.pending().length,1);assert.equal(app.flow.box(),null);assert.equal(app.printed(),0);
 await app.listeners.get('packing-seal:click')();assert.equal(app.calls.at(-1).args.request_key,key);
});
test('printer failure leaves saved box ready to reprint, not staged again',async()=>{
 const app=harness({printFails:true});await app.flow.scan('A');await app.listeners.get('packing-seal:click')();
 assert.equal(app.flow.box().status,'Sealed');assert.equal(app.flow.pending().length,0);
 await app.listeners.get('packing-seal:click')();assert.equal(app.calls.filter(c=>c.method==='finish_packing').length,1);
});
test('phone finish fetches sealed snapshot and prints through remote QZ without a queue',async()=>{
 const app=harness({direct:true});await app.flow.scan('A');await app.listeners.get('packing-seal:click')();
 assert.deepEqual(app.calls.map(c=>c.method),['validate_scan','finish_packing','print_data']);
 assert.equal(app.printed(),1);
});
test('printer UI defaults to local PC for new users on HTTP',()=>{
 const app=harness({protocol:'http:'});app.flow.initSettings();
 const config=app.flow.getSettings();assert.equal(config.mode,'local');assert.equal(config.host,'localhost');assert.equal(config.port,8182);assert.equal(config.usingSecure,false);
});
test('legacy remote config is preserved when switching to local PC and back',()=>{
 const app=harness({protocol:'http:',savedPrinter:{host:'192.168.3.51',port:8181,printer:'BP-TR110'}});app.flow.initSettings();
 assert.equal(app.flow.getSettings().mode,'remote');
 app.elements.get('packing-qz-mode').value='local';app.listeners.get('packing-qz-mode:change')();app.flow.saveSettings(app.flow.getSettings());
 assert.equal(app.flow.getSettings().host,'localhost');
 app.elements.get('packing-qz-mode').value='remote';app.listeners.get('packing-qz-mode:change')();
 const config=app.flow.getSettings();assert.equal(config.host,'192.168.3.51');assert.equal(config.port,8181);assert.equal(config.printer,'BP-TR110');assert.equal(config.usingSecure,true);
});
test('packing supporting controls are collapsed by default',()=>{
 for(const className of ['packing-manual','packing-contents','packing-settings','packing-help']) {
  assert.ok(html.includes(`<details class="${className}">`),className);
 }
 assert.ok(!html.includes('<div class="packing-steps">'));
});
test('inline styles do not accidentally open Jinja comment tags',()=>{
 for(const [,css] of html.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/gi)) {
  assert.ok(!css.includes('{#'),'Separate CSS braces from ID selectors so Jinja does not parse them as comments');
 }
});
test('packing renders a compact scan summary and keeps membership available',async()=>{
 const app=harness({render:true});await app.flow.scan('A');await app.flow.scan('B');
 assert.equal(app.elements.get('packing-summary').textContent,'2 produk · 2 batch\nBread · I-1');
 assert.equal(app.elements.get('packing-contents-title').textContent,'Lihat isi box · 2 produk');
 assert.equal(app.elements.get('packing-seal').disabled,false);
 assert.equal(app.elements.get('packing-preview-name').textContent,'Bread');
 assert.equal(app.elements.get('packing-preview-qty').textContent,'ISI : 2 pcs');
 assert.equal(app.elements.get('packing-preview-id').textContent,'BELUM DIBUAT');
 assert.equal(app.elements.get('packing-preview-receipt').textContent,'RCP : -');
});
