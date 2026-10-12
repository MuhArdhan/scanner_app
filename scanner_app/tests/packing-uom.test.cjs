const {test} = require('node:test');
const assert = require('node:assert/strict');
const label = require('../public/packing.js');
const box = {status:'Sealed',box_id:'BOX-1210261',qr_payload:'BOX:BOX-1210261',total_qty:12,item_name:'Air',item_code:'AIR'};
const decode = value => value.replace(/_([0-9a-f]{2})/gi,(_,hex)=>String.fromCharCode(parseInt(hex,16)));

test('printed quantity uses the Item unit provided by the server',()=>{
  assert.equal(label.content({...box,label_uom:'Galon'}).qty,'ISI : 12 Galon');
  assert.ok(decode(label.zpl({...box,label_uom:'Galon'})).includes('ISI : 12 Galon'));
});
test('unknown unit is not silently replaced with pcs',()=>{
  assert.equal(label.content(box).qty,'ISI : 12 -');
});
test('unit display does not convert the unique child count',()=>{
  assert.equal(label.content({...box,label_uom:'Box',conversion_factor:24}).qty,'ISI : 12 Box');
});
