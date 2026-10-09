/* Local-PC or explicit remote WSS connection. No queue or automatic print retries. */
(function(root) {
  function settings(value, protocol=root.location?.protocol || 'https:') {
    const mode=value.mode || 'remote'; // preserve pre-existing remote settings
    if(!['local','remote'].includes(mode))throw Error('Pilih mode PC ini atau PC lain.');
    const usingSecure=mode==='remote' || protocol!=='http:';
    const host = mode==='local' ? 'localhost' : String(value.host || '').trim().toLowerCase();
    if (!host || host.length > 253 || !/^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$/.test(host) || host.includes('..')) {
      throw Error('Isi IP / hostname komputer saja, tanpa https://, port atau path.');
    }
    const port = Number(value.port===undefined||value.port===null||value.port==='' ? (usingSecure?8181:8182) : value.port);
    if (!Number.isInteger(port) || port < 1 || port > 65535) throw Error('Port QZ harus 1–65535.');
    return {mode,host,port,usingSecure,printer:String(value.printer || '').trim()};
  }
  class RemoteQz {
    constructor({load,call,protocol=()=>root.location?.protocol || 'https:'}) {Object.assign(this,{load,call,protocol});this.busy=false;}
    async operation(action) {
      if(this.busy)throw Error('Koneksi / cetak QZ sedang diproses.');
      this.busy=true;
      try{return await action();}finally{this.busy=false;}
    }
    async connect(config, boxName=null) {
      const qz=await this.load();
      const args=boxName?{box_name:boxName}:{};
      qz.security.setCertificatePromise(async()=>this.call(boxName?'certificate':'connection_certificate',args),{rejectOnFailure:true});
      qz.security.setSignatureAlgorithm('SHA512');
      qz.security.setSignaturePromise(async request=>this.call(boxName?'sign':'connection_sign',{...args,request}));
      if(qz.websocket.isActive()) {
        const connection=qz.websocket.getConnectionInfo();
        if(String(connection.host).toLowerCase()!==config.host || Number(connection.port)!==config.port || connection.socket!==(config.usingSecure?'wss':'ws')) {
          await qz.websocket.disconnect();
        }
      }
      if(!qz.websocket.isActive()) {
        await qz.websocket.connect({host:[config.host],port:{secure:config.usingSecure?[config.port]:[],insecure:config.usingSecure?[]:[config.port]},usingSecure:config.usingSecure,usingSurf:false,retries:0,keepAlive:30});
      }
      return qz;
    }
    async printers(value) {
      return this.operation(async()=>{
        const config=settings(value,this.protocol()), qz=await this.connect(config);
        const printers=await qz.printers.find();
        if(!Array.isArray(printers)||!printers.length)throw Error('Tidak ada printer di komputer QZ tersebut.');
        return printers;
      });
    }
    async print(value, box, zpl) {
      return this.operation(async()=>{
        const config=settings(value,this.protocol());
        if(!config.printer)throw Error('Hubungkan ke PC dan pilih printer BP-TR110 terlebih dahulu.');
        if(box.status!=='Sealed')throw Error('Selesaikan packing dahulu.');
        const qz=await this.connect(config,box.name);
        const installed=await qz.printers.find();
        if(!installed.includes(config.printer))throw Error('Printer tersimpan tidak ditemukan di komputer ini. Pilih ulang printer.');
        // One invocation: a failed response can still mean the label reached the PC.
        await qz.print(qz.configs.create(config.printer,{encoding:'UTF-8'}),[zpl]);
        return {host:config.host,printer:config.printer};
      });
    }
  }
  root.RemotePackingQz={RemoteQz,settings};
  if(typeof module!=='undefined')module.exports={RemoteQz,settings};
})(typeof window!=='undefined'?window:globalThis);
