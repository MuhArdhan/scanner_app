const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const upgrade=fs.readFileSync(path.resolve(__dirname,'../../picking_upgrade.py'),'utf8');
const script=upgrade.match(/PL_STATUS_SCRIPT = """([\s\S]*?)"""/)[1];

test('header shows picking progress without hiding unsaved, cancelled, or shipping status',()=>{
 let handlers,indicator;
 const frm={doc:{docstatus:0,status:'Draft',custom_picking_status:'Not Picked'},is_new:()=>false,
  page:{set_indicator:(label,color)=>{indicator=[label,color];}},toolbar:{set_indicator(){indicator=['native','red'];}}};
 vm.runInNewContext(script,{frappe:{user:{has_role:()=>true},ui:{form:{on:(type,value)=>{handlers=value;}}}},__:s=>s});
 handlers.refresh(frm);assert.deepEqual(indicator,['Not Picked','gray']);
 frm.doc.custom_picking_status='Partially Picked';frm.toolbar.set_indicator();assert.deepEqual(indicator,['Partially Picked','orange']);
 frm.doc.custom_picking_status='Picked';frm.doc.docstatus=1;frm.doc.status='Open';handlers.refresh(frm);assert.deepEqual(indicator,['Picked','green']);
 frm.doc.status='Completed';frm.toolbar.set_indicator();assert.equal(indicator[0],'native');
 frm.doc.status='Partly Delivered';frm.toolbar.set_indicator();assert.equal(indicator[0],'native');
 frm.doc.docstatus=2;frm.toolbar.set_indicator();assert.equal(indicator[0],'native');
 frm.doc.docstatus=0;frm.doc.__unsaved=1;frm.toolbar.set_indicator();assert.equal(indicator[0],'native');
});
