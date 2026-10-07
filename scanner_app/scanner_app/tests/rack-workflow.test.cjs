const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const html = fs.readFileSync(path.join(__dirname, '../../www/scanner/index.html'), 'utf8');
const original = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)].at(-1)[1];
function harness() {
 const elements = new Map(), storage = new Map();
 function element() {
  const classes = new Set();
  return {value:'',textContent:'',className:'',children:[],options:[],disabled:false,listeners:{},
   classList:{add:x=>classes.add(x),remove:x=>classes.delete(x),contains:x=>classes.has(x),toggle(x,on){if(on===undefined) on=!classes.has(x);on?classes.add(x):classes.delete(x);}},
   append(...nodes){this.children.push(...nodes);},replaceChildren(...nodes){this.children=[...nodes];},
   add(option){this.options.push(option);},setAttribute(){},addEventListener(type,handler){this.listeners[type]=handler;},focus(){},remove(){}};
 }
 for(const match of html.matchAll(/id="([^"]+)"/g)) elements.set(match[1],element());
 elements.get('purpose').value='Material Transfer';elements.get('company').value='ROPI';
 const document={getElementById:id=>elements.get(id),createElement:element,cookie:'',documentElement:{dataset:{theme:'dark'}},body:element(),querySelector:()=>element(),addEventListener(){}};
 const fixtures=new Map(), writes=[];
 const context={document,console,URLSearchParams,setTimeout,clearTimeout,Date,Map,Set,JSON,
  localStorage:{getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)},
  navigator:{},window:{frappe:{},addEventListener(){},confirm:()=>true},Option:function(text,value){this.text=text;this.value=value;},
  fetch:async(url,options)=>{if(options?.method==='POST') writes.push(url);const params=new URL('http://test'+url).searchParams;const method=url.split('?')[0].split('.').at(-1);const data=method==='validate_source_scan'?fixtures.get(method):fixtures.get(params.get('code')) || fixtures.get(method);if(data instanceof Error) throw data;return {ok:!data?.error,json:async()=>({message:data?.error || data})};}};
 vm.createContext(context);
 const exported=`globalThis.workflow={resolveScan,resolvePickScan,undoScan,render,renderPick,scanStockRack,persistSession,restoreSession,sourceFingerprint,guideNeedsWarehouse,
 set(s){if(s.guide!==undefined) sourceGuide=s.guide;if(s.pick!==undefined) pickDraft=s.pick;if(s.mode) mode=s.mode;if(s.user) sessionUser=s.user;if(s.saved) savedSession=s.saved;if(s.setup) setup=s.setup;},
 state(){return {rows:[...rows.values()],sourceRack,pickScans,undo:stockUndo.length,savedSession};}};`;
 vm.runInContext(original.replace(/init\(\);\s*\}\)\(\);/,exported+'})();'),context);
 return {api:context.workflow,e:elements,storage,fixtures,writes};
}
const guide=(key,item,source,target)=>({key,item_code:item,item_name:item,qty:1,stock_qty:1,uom:'Nos',s_warehouse:source,t_warehouse:target});
const product=item=>({item_code:item,item_name:item,uom:'Nos',conversion_factor:1,qr_value:item+'-QR'});

test('multiple MR targets: each group must close at the matching rack',async()=>{
 const h=harness();h.api.set({guide:{items:[guide('0','A','S','T1'),guide('1','B','S','T2')]}});
 h.fixtures.set('A-QR',product('A'));h.fixtures.set('B-QR',product('B'));
 await assert.rejects(h.api.resolveScan('A-QR'),/rak asal/);
 h.api.scanStockRack('S');await h.api.resolveScan('A-QR');
 assert.equal(h.e.get('camera-title').textContent,'Scan rak tujuan');
 assert.equal(h.e.get('guide-count').textContent,'0 / 2 lengkap');
 await assert.rejects(h.api.resolveScan('B-QR'),/tujuan lain/);
 assert.throws(()=>h.api.scanStockRack('T2'),/harus T1/);
 h.api.scanStockRack('T1');assert.equal(h.e.get('guide-count').textContent,'1 / 2 lengkap');
 h.api.scanStockRack('S');await h.api.resolveScan('B-QR');h.api.scanStockRack('T2');
 assert.equal(h.e.get('guide-count').textContent,'2 / 2 lengkap');assert.equal(h.e.get('save').disabled,false);
});

test('undo target then item restores quantity and QR eligibility',async()=>{
 const h=harness();h.fixtures.set('A-QR',product('A'));h.api.scanStockRack('S');await h.api.resolveScan('A-QR');h.api.scanStockRack('T');
 h.api.undoScan();assert.equal(h.api.state().rows[0].target_rack_code,undefined);assert.equal(h.e.get('save').disabled,true);
 h.api.undoScan();assert.equal(h.api.state().rows.length,0);await h.api.resolveScan('A-QR');assert.equal(h.api.state().rows.length,1);
});

test('receipt requires only target; issue requires only source',async()=>{
 const receipt=harness();receipt.e.get('purpose').value='Material Receipt';receipt.fixtures.set('A-QR',product('A'));
 await receipt.api.resolveScan('A-QR');assert.equal(receipt.e.get('save').disabled,true);receipt.api.scanStockRack('T');assert.equal(receipt.e.get('save').disabled,false);
 const issue=harness();issue.e.get('purpose').value='Material Issue';issue.fixtures.set('A-QR',product('A'));
 await assert.rejects(issue.api.resolveScan('A-QR'),/rak asal/);issue.api.scanStockRack('S');await issue.api.resolveScan('A-QR');assert.equal(issue.e.get('save').disabled,false);
});

test('same item in different source racks selects the correct guide row',async()=>{
 const h=harness();h.api.set({guide:{items:[guide('0','A','S1','T'),guide('1','A','S2','T')]}});h.fixtures.set('A-QR',product('A'));
 h.api.scanStockRack('S2');await h.api.resolveScan('A-QR');assert.equal(h.api.state().rows[0].guide_key,'1');
});

test('pick list requires source rack and undo removes the last scan',async()=>{
 const h=harness();h.api.set({mode:'pick',pick:{items:[{name:'r',item_code:'A',qty:1,stock_qty:1,conversion_factor:1,warehouse:'S'}]}});
 h.fixtures.set('A-QR',product('A'));h.fixtures.set('S',{warehouse:'S'});
 await assert.rejects(h.api.resolvePickScan('A-QR'),/rak asal/);await h.api.resolvePickScan('S');await h.api.resolvePickScan('A-QR');
 assert.equal(h.e.get('pick-save').disabled,false);h.api.undoScan();assert.equal(h.e.get('pick-save').disabled,true);
});

test('session is scoped per user and changed source blocks restore without writing',async()=>{
 const h=harness(), source={type:'Material Request',name:'MR',options:{},items:[guide('0','A','S','T')],fingerprint:'old'};
 h.api.set({user:'fixture@test',guide:source});h.api.persistSession();assert.ok(h.storage.has('scanner-session-v1:fixture@test'));
 const saved=JSON.parse(h.storage.get('scanner-session-v1:fixture@test'));h.api.set({saved,setup:{companies:['ROPI'],purposes:['Material Transfer']}});
 h.fixtures.set('get_source_items',{company:'ROPI',purpose:'Material Transfer',items:[],from_warehouse:'S',to_warehouse:'T'});
 await h.api.restoreSession();assert.match(h.e.get('status').textContent,/sudah berubah/);assert.equal(h.writes.length,0);
});

test('manufacture input and output follow their warehouse roles',async()=>{
 const h=harness();h.e.get('purpose').value='Manufacture';const raw=guide('0','RAW','S',''),fg={...guide('1','FG','','T'),is_finished_item:true};
 h.api.set({guide:{items:[raw,fg]}});h.fixtures.set('RAW-QR',product('RAW'));h.fixtures.set('FG-QR',product('FG'));
 h.api.scanStockRack('S');await h.api.resolveScan('RAW-QR');await h.api.resolveScan('FG-QR');h.api.scanStockRack('T');
 assert.equal(h.e.get('save').disabled,false);assert.equal(h.api.state().rows[0].source_rack_code,'S');assert.equal(h.api.state().rows[1].target_rack_code,'T');
});

test('restored session rechecks source and retains duplicate-QR protection',async()=>{
 const h=harness(),data={company:'ROPI',purpose:'Material Transfer',items:[guide('0','A','S','T')],from_warehouse:'S',to_warehouse:'T'};
 const source={type:'Material Request',name:'MR',options:{},items:data.items,fingerprint:h.api.sourceFingerprint(data)};
 h.api.set({user:'fixture@test',guide:source});h.e.get('source').value='S';h.e.get('target').value='T';h.fixtures.set('A-QR',product('A'));
 h.api.scanStockRack('S');await h.api.resolveScan('A-QR');h.api.scanStockRack('T');
 const saved=JSON.parse(h.storage.get('scanner-session-v1:fixture@test'));
 h.api.set({saved,setup:{companies:['ROPI'],purposes:['Material Transfer'],warehouses:[{name:'S',company:'ROPI'},{name:'T',company:'ROPI'}]}});
 h.fixtures.set('get_source_items',data);await h.api.restoreSession();
 assert.match(h.e.get('status').textContent,/Sesi dipulihkan/);assert.equal(h.e.get('save').disabled,false);
 await assert.rejects(h.api.resolveScan('A-QR'),/sudah discan/);assert.equal(h.writes.length,0);
});

test('rescan-target action disables submit until the corrected QR is verified',async()=>{
 const h=harness();h.e.get('purpose').value='Material Receipt';h.fixtures.set('A-QR',product('A'));
 await h.api.resolveScan('A-QR');h.api.scanStockRack('T');
 const info=h.e.get('items').children[0].children[0],actions=info.children.find(child=>child.className==='scan-row-actions');
 actions.children[0].listeners.click();assert.equal(h.e.get('save').disabled,true);assert.equal(h.e.get('camera-title').textContent,'Scan rak tujuan');
 h.api.scanStockRack('T2');assert.equal(h.e.get('save').disabled,false);assert.equal(h.api.state().rows[0].target_rack_code,'T2');
});

test('repack and disassemble differentiate incoming and outgoing rows',async()=>{
 for(const purpose of ['Repack','Disassemble']) {
  const h=harness();h.e.get('purpose').value=purpose;
  const outgoing={...guide('0','OUT','S',''),is_finished_item:purpose==='Disassemble'},incoming={...guide('1','IN','','T'),is_finished_item:purpose==='Repack'};
  h.api.set({guide:{items:[outgoing,incoming]}});h.fixtures.set('OUT-QR',product('OUT'));h.fixtures.set('IN-QR',product('IN'));
  h.api.scanStockRack('S');await h.api.resolveScan('OUT-QR');await h.api.resolveScan('IN-QR');h.api.scanStockRack('T');assert.equal(h.e.get('save').disabled,false);
 }
});

test('network loss retains previous scans and duplicate labels are rejected',async()=>{
 const h=harness();h.e.get('purpose').value='Material Issue';h.api.set({user:'fixture@test'});h.fixtures.set('A-QR',product('A'));
 h.api.scanStockRack('S');await h.api.resolveScan('A-QR');await assert.rejects(h.api.resolveScan('A-QR'),/sudah discan/);
 h.fixtures.set('B-QR',new Error('offline'));await assert.rejects(h.api.resolveScan('B-QR'),/Koneksi terputus/);
 assert.equal(h.api.state().rows.length,1);assert.equal(JSON.parse(h.storage.get('scanner-session-v1:fixture@test')).stock.rows.length,1);
});

test('changed Pick List prevents session restore and no submission occurs',async()=>{
 const h=harness(),draft={name:'PL',modified:'old',items:[]};h.api.set({user:'fixture@test',mode:'pick',pick:draft});h.api.persistSession();
 const saved=JSON.parse(h.storage.get('scanner-session-v1:fixture@test'));h.api.set({saved,setup:{companies:['ROPI'],purposes:['Material Transfer']}});
 h.fixtures.set('get_draft',{...draft,modified:'new'});await h.api.restoreSession();
 assert.match(h.e.get('status').textContent,/Pick List sudah berubah/);assert.equal(h.writes.length,0);
});

test('wrong-rack batch stock is rejected before counting or remembering QR',async()=>{
 const h=harness();h.e.get('purpose').value='Material Issue';h.fixtures.set('A-QR',{...product('A'),has_batch_no:true,batch_no:'B1'});h.api.scanStockRack('S');
 h.fixtures.set('validate_source_scan',{error:'Batch B1 tidak tersedia di rak S'});
 await assert.rejects(h.api.resolveScan('A-QR'),/tidak tersedia/);assert.equal(h.api.state().rows.length,0);
 h.fixtures.set('validate_source_scan',{available_stock_qty:1});await h.api.resolveScan('A-QR');assert.equal(h.api.state().rows.length,1);
});

test('Pick List does not count items rejected by rack stock validation',async()=>{
 const h=harness();h.api.set({mode:'pick',pick:{items:[{name:'r',item_code:'A',qty:1,stock_qty:1,conversion_factor:1,warehouse:'S'}]}});h.fixtures.set('S',{warehouse:'S'});h.fixtures.set('A-QR',product('A'));
 await h.api.resolvePickScan('S');h.fixtures.set('validate_source_scan',{error:'Stok batch di rak S kosong'});
 await assert.rejects(h.api.resolvePickScan('A-QR'),/kosong/);assert.equal(h.api.state().pickScans.length,0);
});

test('history renders server records and loads subsequent pages',async()=>{
 const h=harness();const record={operation:'Material Transfer',reference_doctype:'Stock Entry',reference_name:'STE-1',recorded_at:'2026-10-07 10:00:00',scanned_by:'operator@test',company:'ROPI',details:[{item_code:'<img src=x>',qty:1,uom:'Nos',batch_no:'B1',source_warehouse:'S',target_warehouse:'T',qr_values:['QR1']}]};
 h.fixtures.set('get_history',{rows:[record],has_more:true,next_start:20,can_view_all:false});
 await h.e.get('open-history').listeners.click();
 // The click starts an async load; allow the mocked request to complete.
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(h.e.get('history-list').children.length,1);
 const entry=h.e.get('history-list').children[0];assert.equal(entry.children[0].textContent,'Material Transfer · STE-1');
 assert.equal(entry.children[3].children[0].textContent,'<img src=x>');
 assert.equal(entry.children[2].href,'/app/stock-entry/STE-1');
 await h.e.get('history-more').listeners.click();assert.equal(h.e.get('history-list').children.length,2);
});
