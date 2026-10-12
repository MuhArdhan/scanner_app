const test=require('node:test');
const assert=require('node:assert/strict');
const PackingLabel=require('../public/packing.js');
const decodeText=zpl=>zpl.replace(/_([0-9a-f]{2})/gi,(_,hex)=>String.fromCharCode(parseInt(hex,16))).replace(/\\&/g,' ');
const box={status:'Sealed',qr_payload:'BOX:BOX-20261009-00001',box_id:'BOX-20261009-00001',total_qty:12,item_code:'ROTI-01',item_name:'Roti Coklat',earliest_expiry:'2026-10-15',expiry_unknown:0,receipt_date:'2026-10-25',receipt_dates:['2026-10-25'],receipt_unknown:0};

box.label_uom='pcs';

test('60 x 40 label has QR on left, ID below and requested fields on right',()=>{
  const zpl=PackingLabel.zpl(box),text=decodeText(zpl);
  assert.ok(zpl.includes('^PW480'));assert.ok(zpl.includes('^LL320'));
  assert.ok(zpl.includes('^FO35,70^BQN,2,7'));assert.ok(zpl.includes('^FO25,265'));
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
  assert.equal((zpl.match(/\^XZ/g)||[]).length,1);assert.ok(zpl.replace(/\\&/g,'').includes('_5e_58_5a_7e_4a_41_5f'));
});
test('unsealed box cannot print',()=>{
  assert.throws(()=>PackingLabel.zpl({...box,status:'Open'}),/Seal a nonempty box/);
});
test('compact daily Box ID is accepted alongside legacy Box IDs',()=>{
  const text=decodeText(PackingLabel.zpl({...box,box_id:'BOX-0910261',qr_payload:'BOX:BOX-0910261'}));
  assert.ok(text.includes('QA,BOX:BOX-0910261'));
  assert.ok(text.includes('BOX-0910261'));
});
test('following fields adapt to name height without changing the name field',()=>{
  const positions=name=>[...PackingLabel.zpl({...box,item_name:name}).matchAll(/\^FO240,(\d+)\^A0N,(\d+),/g)].map(match=>({y:Number(match[1]),size:Number(match[2])}));
  const short=positions('Roti'),long=positions('Tes Air Galon Produksi');
  assert.equal(short[1].y,115);
  assert.equal(long[1].y,147);
  assert.deepEqual(long.slice(2).map(field=>field.y-long[1].y),[40,80,120]);
  assert.ok(long.at(-1).y+long.at(-1).size<=304);
});
test('name font and native wrapping stay unchanged without truncation or forced breaks',()=>{
  const name='Roti Coklat Premium Special dengan tambahan Keju dan Kacang Panggang '.repeat(5);
  const zpl=PackingLabel.zpl({...box,item_name:name});
  const fields=[...zpl.matchAll(/\^FO240,(\d+)\^A0N,(\d+),\d+\^FB225,(\d+),/g)].map(match=>({y:Number(match[1]),size:Number(match[2]),lines:Number(match[3])}));
  assert.equal(fields[0].size,32);assert.equal(fields[0].lines,2);
  assert.ok(fields[1].y>=fields[0].y+fields[0].size*fields[0].lines+13);
  assert.ok(fields.at(-1).y+fields.at(-1).size<=304);
  assert.ok(decodeText(zpl).includes(name));
  assert.ok(!zpl.includes('\\&'));
});
test('proportional width, not a fixed word or character count, controls spacing',()=>{
  const skuY=name=>Number([...PackingLabel.zpl({...box,item_name:name}).matchAll(/\^FO240,(\d+)\^A0N/g)][1][1]);
  assert.equal(skuY('Tes Air Galon'),115);
  assert.equal(skuY('Tes Air Galon Produksi'),147);
  assert.equal(skuY('iiiiiiiiiiiiiiiiiiii'),115);
  assert.equal(skuY('WWWWWWWWWWWWWWWWWWWW'),147);
});
