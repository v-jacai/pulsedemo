/* No vendor SDK dependency: Finsemble injects FSBL in registered apps. */
(function(root){
 'use strict';
 const query = new URLSearchParams(root.location.search);
 const identity = query.get('user') || 'am23456';
 const hostMode = query.get('host') === 'finsemble' || !!root.FSBL;
 const windowKey = (user,id) => 'pulse_alert_'+user+'_'+id;
 function urlFor(user,id,options={}) {
   const url=new URL('/alert-popup.html',root.location.origin);
   url.searchParams.set('user',user); url.searchParams.set('alert',id);
   if(options.kind)url.searchParams.set('kind',options.kind);
   if(options.payload?.message_id)url.searchParams.set('message',options.payload.message_id);
   if(options.auto)url.searchParams.set('auto','1');
   if(hostMode)url.searchParams.set('host','finsemble');
   return url.href;
 }
 class BrowserAdapter {
   constructor(){this.windows=new Map()}
   openAlert(user,id,options={}) {
     const name=windowKey(user,id); const existing=this.windows.get(name);
     if(existing&&!existing.closed){if(!options.auto)existing.focus();return true}
     const w=root.open(urlFor(user,id,options),name,'popup,width=620,height=760,resizable=yes,scrollbars=yes');
     if(!w)return false;
     this.windows.set(name,w);return true;
   }
   close(){root.close()}
 }
 function call(client,method,...args){return new Promise((resolve,reject)=>{
   const t=root.setTimeout(()=>reject(Error('Finsemble '+method+' timed out')),15000);
   const done=(err,data)=>{root.clearTimeout(t);err?reject(new Error(err.message||String(err))):resolve(data)};
   try{const p=client[method](...args,done);if(p&&typeof p.then==='function')p.then(result=>{if(result&&typeof result==='object'&&('err' in result||'error' in result||'response' in result))done(result.err||result.error,result.data??result.response);}).catch(done)}catch(e){done(e)}
 })}
 function ready(){if(!hostMode)return Promise.resolve();return new Promise((resolve,reject)=>{
   const timeout=root.setTimeout(()=>reject(Error('Finsemble API not available or not ready. Check app registration.')),15000);
   const finish=()=>{root.clearTimeout(timeout);resolve()};
   if(root.FSBL?.addEventListener)root.FSBL.addEventListener('onReady',finish);else root.addEventListener('FSBLReady',finish,{once:true});
 })}
 const readiness=hostMode?ready():Promise.resolve();readiness.catch(()=>{});
 class FinsembleAdapter {
   constructor(){this.pending=new Map()}
   openAlert(user,id,options={}){
     const name=windowKey(user,id);if(this.pending.has(name))return this.pending.get(name);
     const task=this._open(name,user,id,options).finally(()=>this.pending.delete(name));this.pending.set(name,task);return task;
   }
   async _open(name,user,id,options){
     await readiness;const c=root.FSBL?.Clients;const apps=c?.AppsClient||c?.LauncherClient;
     if(!apps)throw Error('Finsemble AppsClient / LauncherClient is unavailable.');
     const active=await call(apps,'getActiveDescriptors');
     const existing=Object.entries(active||{}).find(([key,d])=>key===name||d?.name===name||key.startsWith(name+'-')||d?.customData?.spawnData?.pulseKey===name);
     if(existing){await call(apps,'showWindow',{windowName:existing[0]},{autoFocus:!options.auto,spawnIfNotFound:false});return true}
     await call(apps,'spawn','Pulse Alert Popup',{name,url:urlFor(user,id,options),data:{pulseKey:name,alertId:id,user},width:620,height:760,minWidth:440,minHeight:520,position:'available',monitor:'primary',right:20,bottom:20,autoFocus:!options.auto,addToWorkspace:false,canGroup:false});return true;
   }
   async close(){await readiness;await call(root.FSBL.Clients.WindowClient,'close',{removeFromWorkspace:true,closeWindow:true,userInitiated:true})}
 }
 const adapter=hostMode?new FinsembleAdapter():new BrowserAdapter();
 root.PulseDesktop={adapter,hostMode,identity,urlFor,windowKey,readiness,BrowserAdapter,FinsembleAdapter};
})(window);
