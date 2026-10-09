const {test}=require('node:test');
const assert=require('node:assert/strict');
const {RemoteQz,settings}=require('../public/remote-qz.js');
const config={host:'192.168.1.5',port:8181,printer:'BP-TR110'};
const box={name:'BOX-1',status:'Sealed'};

function harness({connected=null,printers=['BP-TR110'],printError=false,protocol='https:'}={}) {
 const events=[],callbacks={};let connection=connected;
 const qz={security:{setCertificatePromise(fn){callbacks.cert=fn;},setSignaturePromise(fn){callbacks.sign=fn;},setSignatureAlgorithm(a){events.push(['algorithm',a]);}},
  websocket:{isActive:()=>!!connection,getConnectionInfo:()=>connection,disconnect:async()=>{events.push(['disconnect']);connection=null;},connect:async options=>{events.push(['connect',options]);connection={host:options.host[0],port:options.usingSecure?options.port.secure[0]:options.port.insecure[0],socket:options.usingSecure?'wss':'ws'};}},
  printers:{find:async()=>printers},configs:{create:(printer,options)=>({printer,...options})},
  print:async(settings,jobs)=>{events.push(['print',settings,jobs]);if(printError)throw Error('Connection lost');}
 };
 const calls=[];
 const client=new RemoteQz({load:async()=>qz,protocol:()=>protocol,call:async(method,args)=>{calls.push([method,args]);return 'signed';}});
 return {client,events,calls,callbacks};
}

test('requires explicit host and valid port, rejects URL input',()=>{
 for(const host of ['', 'https://192.168.1.5','pc:8181','pc/path','pc host'])assert.throws(()=>settings({...config,host}));
 assert.throws(()=>settings({...config,port:0}));
 assert.equal(settings({...config,host:' PRINTER-PC.local '}).host,'printer-pc.local');
});
test('local mode on HTTP uses only localhost WS, suitable for desktop testing',async()=>{
 const h=harness({protocol:'http:'});await h.client.printers({mode:'local'});
 const options=h.events.find(e=>e[0]==='connect')[1];
 assert.deepEqual(options.host,['localhost']);assert.equal(options.usingSecure,false);
 assert.deepEqual(options.port,{secure:[],insecure:[8182]});
});
test('local HTTPS stays WSS and cannot be redirected to a remote host',async()=>{
 const h=harness();await h.client.printers({mode:'local',host:'192.168.1.5'});
 const options=h.events.find(e=>e[0]==='connect')[1];
 assert.deepEqual(options.host,['localhost']);assert.equal(options.usingSecure,true);
 assert.deepEqual(options.port,{secure:[8181],insecure:[]});
});
test('remote mode remains WSS even when scanner is opened on HTTP',async()=>{
 const h=harness({protocol:'http:'});await h.client.printers({...config,mode:'remote'});
 const options=h.events.find(e=>e[0]==='connect')[1];
 assert.equal(options.usingSecure,true);assert.deepEqual(options.port.insecure,[]);
});
test('switching from remote PC to local explicitly closes the old connection',async()=>{
 const h=harness({protocol:'http:',connected:{host:'192.168.1.5',port:8181,socket:'wss'}});
 await h.client.print({mode:'local',printer:'BP-TR110'},box,'^XA^XZ');
 assert.equal(h.events.filter(e=>e[0]==='disconnect').length,1);
 assert.equal(h.events.filter(e=>e[0]==='print').length,1);
});
test('discovery connects only to configured WSS host, no localhost or WS fallback',async()=>{
 const h=harness();assert.deepEqual(await h.client.printers(config),['BP-TR110']);
 const options=h.events.find(e=>e[0]==='connect')[1];
 assert.deepEqual(options.host,['192.168.1.5']);assert.deepEqual(options.port,{secure:[8181],insecure:[]});assert.equal(options.usingSecure,true);assert.equal(options.usingSurf,false);assert.equal(options.retries,0);
 await h.callbacks.cert();await h.callbacks.sign('hash');
 assert.deepEqual(h.calls.map(c=>c[0]),['connection_certificate','connection_sign']);
});
test('changes existing local or wrong-host connection to selected PC',async()=>{
 const h=harness({connected:{host:'localhost',port:8181,socket:'wss'}});
 await h.client.print(config,box,'^XA^XZ');
 assert.equal(h.events.filter(e=>e[0]==='disconnect').length,1);assert.equal(h.events.filter(e=>e[0]==='print').length,1);
 await h.callbacks.sign('hash');assert.equal(h.calls[0][1].box_name,'BOX-1');
});
test('reuses matching secure connection and selected printer',async()=>{
 const h=harness({connected:{host:config.host,port:8181,socket:'wss'}});await h.client.print(config,box,'^XA^XZ');
 assert.equal(h.events.filter(e=>e[0]==='connect').length,0);
 const printed=h.events.find(e=>e[0]==='print');assert.equal(printed[1].printer,'BP-TR110');assert.deepEqual(printed[2],['^XA^XZ']);
});
test('missing printer or unsealed box never invokes print',async()=>{
 const h=harness({printers:['OTHER']});await assert.rejects(h.client.print(config,box,'zpl'),/tidak ditemukan/);
 await assert.rejects(h.client.print(config,{status:'Open'},'zpl'),/packing/);
 assert.equal(h.events.filter(e=>e[0]==='print').length,0);
});
test('network error does not trigger automatic reprint',async()=>{
 const h=harness({printError:true});await assert.rejects(h.client.print(config,box,'zpl'),/Connection lost/);
 assert.equal(h.events.filter(e=>e[0]==='print').length,1);assert.equal(h.client.busy,false);
});
test('simultaneous calls cannot alter signing context during a print',async()=>{
 const h=harness();let release;h.client.load=()=>new Promise(r=>release=r);
 const first=h.client.printers(config);
 await assert.rejects(h.client.printers(config),/sedang diproses/);
 // Finish with a deliberately failed load, without opening a socket.
 release({security:{setCertificatePromise(){throw Error('Stop');}}});await assert.rejects(first,/Stop/);
});
