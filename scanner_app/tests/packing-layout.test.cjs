const {test}=require('node:test');
const assert=require('node:assert/strict');
const label=require('../public/packing.js');
const box={status:'Sealed',qr_payload:'BOX:BOX-1210261',box_id:'BOX-1210261',total_qty:12,item_name:'Air',item_code:'AIR',label_uom:'Galon'};
test('default layout preserves current positions, dimensions and native name font',()=>{
 const zpl=label.zpl(box);
 for(const fragment of ['^PW480','^LL320','^FO35,70^BQN,2,9','^FO250,70^A0N,32,29^FB225,2','^FO25,265'])assert.ok(zpl.includes(fragment));
 assert.equal(zpl,label.zpl(box,label.defaults));
});
test('shared calibration applies paper size, QR, text and global offsets',()=>{
 const zpl=label.zpl(box,{...label.defaults,width_mm:70,height_mm:50,offset_x:5,offset_y:6,qr_x:40,qr_y:30,qr_scale:7,text_x:260,text_y:50,text_width:250,field_gap:30,id_x:20,id_y:280,id_width:210});
 for(const fragment of ['^PW560','^LL400','^FO45,36^BQN,2,7','^FO265,56^A0N,32,29^FB250,2','^FO25,286','^FO265,131'])assert.ok(zpl.includes(fragment),fragment);
 assert.equal((zpl.match(/\^BQN/g)||[]).length,1);
});
