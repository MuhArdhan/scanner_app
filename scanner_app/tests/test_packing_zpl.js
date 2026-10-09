const test=require('node:test');
const assert=require('node:assert/strict');
const PackingLabel=require('../public/packing.js');
const decodeText=zpl=>zpl.replace(/_([0-9a-f]{2})/gi,(_,hex)=>String.fromCharCode(parseInt(hex,16)));
const box={status:'Sealed',qr_payload:'BOX:BOX-20261009-00001',box_id:'BOX-20261009-00001',total_qty:12,item_code:'ROTI-01',item_name:'Roti Coklat',earliest_expiry:'2026-10-15',expiry_unknown:0,receipt_date:'2026-10-25',receipt_dates:['2026-10-25'],receipt_unknown:0};

test('60 x 40 label has QR on left, ID below and requested fields on right',()=>{
  const zpl=PackingLabel.zpl(box),text=decodeText(zpl);
  assert.ok(zpl.includes('^PW480'));assert.ok(zpl.includes('^LL320'));
  assert.ok(zpl.includes('^FO35,50^BQN,2,7'));assert.ok(zpl.includes('^FO25,265'));
  for(const expected of ['Roti Coklat','SKU : ROTI-01','ISI : 12 pcs','RCP : 25-10-26','EXP : 15-10-26','BOX-20261009-00001'])assert.ok(text.includes(expected),expected);
  assert.ok(!text.includes('BATCH:'));
  assert.equal((zpl.match(/\^XA/g)||[]).length,1);assert.equal((zpl.match(/\^XZ/g)||[]).length,1);
});
test('mixed receipt dates show MIXED and incomplete expiry shows dash',()=>{
  const text=decodeText(PackingLabel.zpl({...box,receipt_date:null,receipt_dates:['2026-10-01','2026-10-02'],expiry_unknown:1}));
  assert.ok(text.includes('RCP : MIXED'));assert.ok(text.includes('EXP : -'));
});
test('unknown RCP does not substitute packing date',()=>{
  const text=decodeText(PackingLabel.zpl({...box,receipt_date:null,receipt_dates:[],receipt_unknown:1,packed_at:'2026-10-25'}));
  assert.ok(text.includes('RCP : -'));assert.ok(!text.includes('25-10-26'));
});
test('ZPL control characters are encoded, not interpreted',()=>{
  const zpl=PackingLabel.zpl({...box,item_name:'Gelas^XZ~JA_'});
  assert.equal((zpl.match(/\^XZ/g)||[]).length,1);assert.ok(zpl.includes('_5e_58_5a_7e_4a_41_5f'));
});
test('unsealed box cannot print',()=>{
  assert.throws(()=>PackingLabel.zpl({...box,status:'Open'}),/Seal a nonempty box/);
});
