const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.resolve(__dirname, '../www/scanner/index.html'), 'utf8');
const script = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)].at(-1)[1];

function harness(options={}) {
  const elements = new Map(),listeners=new Map(),main={inert:false},calls=[];let created=0;
  const element = id => {
    if (!elements.has(id)) {
      const classes=new Set(),attributes={};
      const node={id,textContent:'',value:'',dataset:{},style:{},attributes,children:[],
        classList:{add:name=>classes.add(name),remove:name=>classes.delete(name),toggle:(name,force)=>force?classes.add(name):classes.delete(name),contains:name=>classes.has(name)},
        addEventListener:(event,fn)=>listeners.set(id+':'+event,fn),replaceChildren(){this.children=[];},append(...children){this.children.push(...children);},focus(){},setAttribute:(key,value)=>{attributes[key]=value;}};
      elements.set(id,node);
    }
    return elements.get(id);
  };
  const context = {
    document:{getElementById:element,createElement:()=>element('created-'+created++),querySelector:selector=>selector==='main'?main:({content:''}),addEventListener(){},documentElement:{dataset:{}}},
    window:{addEventListener(){},mockCall:async (method,args)=>{calls.push({method,args});if(method==='list_boxes')return options.listBoxes?options.listBoxes():[];if(method==='read_box')return options.box;if(method==='get_history')return {rows:[],next_start:0,can_view_all:false,has_more:false};throw Error('Unexpected '+method);}},localStorage:{getItem:key=>key==='scanner-packing-pending'&&options.savedPending?JSON.stringify({children:options.savedPending}):null,setItem(){},removeItem(){}},
    location:{hash:'#packing'},history:{replaceState(){}},navigator:{},URLSearchParams,console,setTimeout,clearTimeout,
  };
  const instrumented = script.replace(/init\(\);\s*\}\)\(\);\s*$/, `
    initPackingQzSettings=()=>{};
    call=async (method,args)=>window.mockCall(method,args);message=()=>{};
    window.packingUI={render:renderPacking,setPending:children=>{packingBox=null;packingPending=children;},setBox:box=>{packingBox=box;},confirm:confirmPackingPrint,close:closePackingPrint,history:loadHistory,historyPanel:setHistoryPanel,boxEntry:renderBoxHistoryEntry};
  })();`);
  for(const id of ['camera-modal','source-modal','review-modal','history-panel','settings-panel','settings-menu'])element(id).classList.add('hidden');
  vm.runInNewContext(instrumented, context);
  return {ui:context.window.packingUI,elements,listeners,main,calls};
}

test('redesigned CSS is scoped exclusively to the packing page', () => {
  const css = [...html.matchAll(/<style>([\s\S]*?)<\/style>/g)].map(match=>match[1]).find(value=>value.includes('Packing-only visual redesign'));
  assert.ok(css);
  const clean = css.replace(/\/\*[\s\S]*?\*\//g, '');
  for (const [,selector] of clean.matchAll(/([^{}]+)\{/g)) {
    if (selector.trim().startsWith('@media')) continue;
    assert.ok(selector.split(',').every(part=>part.includes('#packing')),selector);
  }
  assert.ok(!css.includes('{#'));
  assert.ok(!html.includes('scanner-ui.css'));
});

test('single workspace preserves every packing action without a preview', () => {
  const packing = html.slice(html.indexOf('<section id="packing"'),html.indexOf('<section id="pick"'));
  assert.equal((packing.match(/class="card packing-workspace"/g)||[]).length,1);
  for (const id of ['packing-camera-button','packing-input','packing-scan','packing-seal','packing-print','packing-create']) {
    assert.equal((packing.match(new RegExp(`id="${id}"`,'g'))||[]).length,1,id);
  }
  assert.ok(!packing.includes('packing-preview'));
  assert.ok(!packing.includes('Petunjuk packing'));
  assert.ok(!html.includes('packing-reload'));
  assert.match(packing,/id="packing-summary"[^>]*aria-live="polite"/);
});

test('overview updates for empty, scanned, and sealed boxes', () => {
  const app=harness();app.ui.render();
  assert.equal(app.elements.get('packing-total').textContent,'0');
  assert.equal(app.elements.get('packing-state').textContent,'Siap scan');
  app.ui.setPending([{product_qr_serial:'PQR-1',item_name:'Tes Air Galon Produksi',item_code:'AIR',batch_no:null,label_uom:'Galon'}]);app.ui.render();
  assert.equal(app.elements.get('packing-total').textContent,'1');
  assert.equal(app.elements.get('packing-uom').textContent,'Galon');
  assert.equal(app.elements.get('packing-product-name').textContent,'Tes Air Galon Produksi');
  assert.equal(app.elements.get('packing-state').dataset.state,'active');
  app.ui.setBox({name:'BOX-1210261',box_id:'BOX-1210261',item_name:'Tes Air Galon Produksi',item_code:'AIR',total_qty:12,status:'Sealed',children:[],label_uom:'Galon'});app.ui.render();
  assert.equal(app.elements.get('packing-total').textContent,'12');
  assert.equal(app.elements.get('packing-uom').textContent,'Galon');
  assert.equal(app.elements.get('packing-state').textContent,'Selesai');
  assert.equal(app.elements.get('packing-state').dataset.state,'sealed');
  assert.equal(app.elements.get('packing-product-meta').textContent,'BOX-1210261 · AIR');
});
test('new packing action is in the header and back retains a border',()=>{
  const heading=html.slice(html.indexOf('<div class="packing-heading">'),html.indexOf('<div class="card packing-workspace">'));
  assert.match(heading,/id="packing-create"/);
  assert.match(heading,/id="packing-back"/);
  assert.ok(heading.indexOf('id="packing-create"')<heading.indexOf('id="packing-back"'));
  assert.match(html,/#packing #packing-back\{[^}]*border:1px solid var\(--line\)/);
});
test('gear dropdown contains theme switch and opens a separate printer modal',()=>{
  const packing=html.slice(html.indexOf('<section id="packing"'),html.indexOf('<section id="pick"'));
  const settings=html.slice(html.indexOf('<div id="settings-panel"'),html.indexOf('<div id="source-modal"'));
  const menu=html.slice(html.indexOf('<div id="settings-menu"'),html.indexOf('<div id="status"'));
  assert.ok(!packing.includes('packing-qz-mode'));assert.ok(!html.includes('id="packing-list"'));
  for(const id of ['packing-qz-mode','packing-qz-connect','packing-qz-printer'])assert.ok(settings.includes(`id="${id}"`));
  for(const id of ['theme-toggle','settings-printer-open'])assert.ok(menu.includes(`id="${id}"`));
  assert.ok(!settings.includes('theme-toggle'));assert.match(settings,/role="dialog"/);
  const header=html.slice(html.indexOf('<div class="bar app-header"'),html.indexOf('<div id="status"'));
  assert.ok(header.indexOf('id="open-settings"')>header.indexOf('id="open-history"'));
  assert.ok(html.includes('<option>Packing Box</option>'));
});
test('minimal theme switch stays synchronized with the theme and remains labeled',()=>{
 const app=harness(),toggle=app.listeners.get('theme-toggle:click');
  assert.equal(app.elements.get('theme-toggle').attributes['aria-checked'],'false');
  assert.match(app.elements.get('settings-theme-label').innerHTML,/Mode gelap/);
  assert.match(app.elements.get('settings-theme-label').innerHTML,/M20.2 15.1/);
  toggle();assert.equal(app.elements.get('theme-toggle').attributes['aria-checked'],'true');
  assert.match(app.elements.get('settings-theme-label').innerHTML,/Mode terang/);
  assert.match(app.elements.get('settings-theme-label').innerHTML,/<circle/);
  toggle();assert.equal(app.elements.get('theme-toggle').attributes['aria-checked'],'false');
  assert.match(app.elements.get('settings-theme-label').innerHTML,/Mode gelap/);
  assert.match(app.elements.get('settings-theme-label').innerHTML,/M20.2 15.1/);
 assert.match(html,/id="theme-toggle"[^>]*role="switch"[^>]*aria-labelledby="settings-theme-label"/);
 assert.ok(html.includes('#settings-menu #theme-toggle[aria-checked="true"]::after'));
});
test('navbar history can open and close with accessible toggle state',async()=>{
  const app=harness(),click=app.listeners.get('open-history:click');
  await click();
  assert.equal(app.elements.get('open-history').attributes['aria-expanded'],'true');
  assert.equal(app.elements.get('history-panel').classList.contains('hidden'),false);
  await click();
  assert.equal(app.elements.get('open-history').attributes['aria-expanded'],'false');
  assert.equal(app.elements.get('history-panel').classList.contains('hidden'),true);
});
test('closing history during loading prevents a late response from reopening it',async()=>{
  let resolve;
  const app=harness({listBoxes:()=>new Promise(done=>{resolve=done;})});
  app.elements.get('history-activity').value='Packing Box';app.ui.historyPanel(true);
  const opening=app.ui.history();
  app.ui.historyPanel(false);resolve([]);await opening;
  assert.equal(app.elements.get('history-panel').classList.contains('hidden'),true);
  assert.equal(app.elements.get('open-history').attributes['aria-expanded'],'false');
  assert.equal(app.elements.get('history-list').children.length,0);
});
test('box history uses its API and supports search and pagination',async()=>{
 const app=harness({listBoxes:()=>Array.from({length:20},(_,i)=>({name:'BOX-'+i,status:'Sealed',item_code:'AIR',total_qty:1}))});
 app.elements.get('history-activity').value='Packing Box';app.elements.get('history-search').value='AIR';
 await app.ui.history();await app.ui.history(true);
 assert.equal(app.calls[0].method,'list_boxes');assert.equal(app.calls[0].args.search,'AIR');
 assert.equal(app.calls[1].args.start,20);assert.equal(app.elements.get('history-list').children.length,40);
});
test('gear toggles dropdown, printer action opens modal, and close restores background',()=>{
 const app=harness();app.ui.historyPanel(true);
 app.listeners.get('open-settings:click')();
 assert.equal(app.elements.get('settings-menu').classList.contains('hidden'),false);
 assert.equal(app.elements.get('settings-panel').classList.contains('hidden'),true);
 assert.equal(app.elements.get('history-panel').classList.contains('hidden'),true);
 app.listeners.get('open-settings:click')();
 assert.equal(app.elements.get('settings-menu').classList.contains('hidden'),true);
 app.listeners.get('open-settings:click')();app.listeners.get('settings-printer-open:click')();
 assert.equal(app.elements.get('settings-menu').classList.contains('hidden'),true);
 assert.equal(app.elements.get('settings-panel').classList.contains('hidden'),false);
 assert.equal(app.main.inert,true);
 app.listeners.get('close-settings:click')();
 assert.equal(app.elements.get('settings-panel').classList.contains('hidden'),true);
 assert.equal(app.main.inert,false);
});
test('opening a history box loads it without printing and protects locally saved scans',async()=>{
 const box={name:'BOX-1210261',box_id:'BOX-1210261',item_code:'AIR',item_name:'Air',total_qty:12,label_uom:'Galon',status:'Sealed',children:[]};
 const app=harness({box}),card=app.ui.boxEntry(box),button=card.children[2];
 await app.listeners.get(button.id+':click')();
 assert.deepEqual(app.calls.map(call=>call.method),['read_box']);
 assert.equal(app.elements.get('packing-total').textContent,'12');
 const protectedApp=harness({box,savedPending:[{qr_payload:'QR-1'}]});
 const protectedButton=protectedApp.ui.boxEntry(box).children[2];
 await protectedApp.listeners.get(protectedButton.id+':click')();
 assert.equal(protectedApp.calls.length,0);
});
test('custom popup shows pending item, unit and printer and supports cancel',async()=>{
 const app=harness();
 app.ui.setPending([{item_name:'Air Galon',item_code:'AIR',label_uom:'Galon'}]);
 app.elements.get('packing-qz-printer').value='BP-TR110';
 const result=app.ui.confirm();
 assert.equal(app.main.inert,true);
 assert.equal(app.elements.get('packing-confirm-item').textContent,'Air Galon');
 assert.equal(app.elements.get('packing-confirm-qty').textContent,'1 Galon');
 assert.equal(app.elements.get('packing-confirm-printer').textContent,'BP-TR110');
 assert.equal(app.elements.get('packing-confirm-box').textContent,'Dibuat setelah konfirmasi');
 app.ui.close();assert.equal(await result,false);assert.equal(app.main.inert,false);
});
test('reprint popup keeps duplicate-label warning and requires explicit confirmation',async()=>{
 const app=harness();app.ui.setBox({box_id:'BOX-1210261',item_name:'Air',total_qty:12,label_uom:'Galon',status:'Sealed'});
 const result=app.ui.confirm(true);
 assert.equal(app.elements.get('packing-confirm-box').textContent,'BOX-1210261');
 assert.match(app.elements.get('packing-print-warning').textContent,/label tambahan/);
 assert.equal(await app.ui.confirm(true),false);
 app.ui.close(true);assert.equal(await result,true);
});
