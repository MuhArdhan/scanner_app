const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.resolve(__dirname, '../www/scanner/index.html'), 'utf8');
const script = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)].at(-1)[1];

function harness(options={}) {
  const elements = new Map(),listeners=new Map(),main={inert:false};
  const element = id => {
    if (!elements.has(id)) {
      const classes=new Set(),attributes={};
      elements.set(id, {textContent:'',value:'',dataset:{},style:{},attributes,
        classList:{add:name=>classes.add(name),remove:name=>classes.delete(name),toggle:(name,force)=>force?classes.add(name):classes.delete(name),contains:name=>classes.has(name)},
        addEventListener:(event,fn)=>listeners.set(id+':'+event,fn),replaceChildren(){},append(){},focus(){},setAttribute:(key,value)=>{attributes[key]=value;}});
    }
    return elements.get(id);
  };
  const context = {
    document:{getElementById:element,createElement:()=>element(Symbol()),querySelector:selector=>selector==='main'?main:({content:''}),addEventListener(){},documentElement:{dataset:{}}},
    window:{addEventListener(){},mockCall:async method=>{if(method==='list_boxes')return options.listBoxes?options.listBoxes():[];throw Error('Unexpected '+method);}},localStorage:{getItem:()=>null,setItem(){},removeItem(){}},
    location:{hash:'#packing'},history:{replaceState(){}},navigator:{},URLSearchParams,console,setTimeout,clearTimeout,
  };
  const instrumented = script.replace(/init\(\);\s*\}\)\(\);\s*$/, `
    initPackingQzSettings=()=>{};
    call=async method=>window.mockCall(method);message=()=>{};
    window.packingUI={render:renderPacking,setPending:children=>{packingBox=null;packingPending=children;},setBox:box=>{packingBox=box;},confirm:confirmPackingPrint,close:closePackingPrint};
  })();`);
  vm.runInNewContext(instrumented, context);
  return {ui:context.window.packingUI,elements,listeners,main};
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
  for (const id of ['packing-camera-button','packing-input','packing-scan','packing-seal','packing-print','packing-create','packing-list','packing-qz-mode','packing-qz-connect','packing-qz-printer']) {
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
test('history toggle is grouped with printer settings in packing utilities',()=>{
  const packing=html.slice(html.indexOf('<section id="packing"'),html.indexOf('<section id="pick"'));
  const utilities=packing.indexOf('<div class="packing-utilities">');
  assert.ok(utilities<packing.indexOf('id="packing-list"'));
  assert.ok(packing.indexOf('id="packing-list"')<packing.indexOf('<details class="packing-settings">'));
});
test('history can open and close again with accessible toggle state',async()=>{
  const app=harness(),click=app.listeners.get('packing-list:click');
  await click();
  assert.equal(app.elements.get('packing-list').attributes['aria-expanded'],'true');
  assert.equal(app.elements.get('packing-boxes').classList.contains('hidden'),false);
  await click();
  assert.equal(app.elements.get('packing-list').attributes['aria-expanded'],'false');
  assert.equal(app.elements.get('packing-boxes').classList.contains('hidden'),true);
});
test('closing history during loading prevents a late response from reopening it',async()=>{
  let resolve;
  const app=harness({listBoxes:()=>new Promise(done=>{resolve=done;})});
  const click=app.listeners.get('packing-list:click'),opening=click();
  await click();resolve([]);await opening;
  assert.equal(app.elements.get('packing-boxes').classList.contains('hidden'),true);
  assert.equal(app.elements.get('packing-list').attributes['aria-expanded'],'false');
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
