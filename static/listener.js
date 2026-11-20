'use strict';
const {adapter,hostMode,identity,urlFor,readiness}=window.PulseDesktop;
const el=id=>document.getElementById(id);
let cursor=0,stream,queue=Promise.resolve(),retry,stopped=false;const notices=[];
const endpoint=(p)=>p+(p.includes('?')?'&':'?')+'user='+encodeURIComponent(identity);
function status(text,online=false){el('listenerStatus').className='connection '+(online?'online':'offline');el('listenerStatus').textContent=text}
function draw(){const list=el('listenerEvents');list.replaceChildren();if(!notices.length){list.textContent='No new alerts yet.';return}for(const n of notices){const row=document.createElement('div');row.className='listener-event';const text=document.createElement('div'),title=document.createElement('strong'),meta=document.createElement('small');title.textContent=n.title;meta.textContent=n.kind.replaceAll('_',' ')+' · '+n.result;text.append(title,meta);const btn=document.createElement('button');btn.className='button secondary small';btn.textContent='Open alert ↗';btn.onclick=async()=>{try{const ok=await adapter.openAlert(identity,n.alert_id,{...n,auto:false});n.result=ok?'Window opened':'Blocked — allow pop-ups';}catch(e){n.result=e.message}draw()};row.append(text,btn);list.append(row)}}
async function get(p){const r=await fetch(endpoint(p));if(!r.ok)throw Error('Server request failed: '+r.status);return r.json()}
async function handle(event){if(event.id<=cursor)return;if(['alert_created','mention','invited'].includes(event.kind)){
 const snapshot=await get('/api/snapshot');const a=snapshot.alerts.find(a=>a.id===event.alert_id);
 if(a&&a.status!=='Resolved'){
   const n={...event,title:a.title,result:'Opening…'};notices.unshift(n);if(notices.length>30)notices.pop();draw();
   try{const opened=await adapter.openAlert(identity,event.alert_id,{...event,auto:true});n.result=opened?'Window opened':'Blocked — click Open alert';}catch(e){n.result='Failed: '+e.message;console.error(e)}draw();
 }
 }cursor=event.id;
}
function connect(){if(stopped)return;stream=new EventSource(endpoint('/api/stream?after='+cursor));const current=stream;current.onopen=()=>status('Live connected',true);current.onerror=()=>status('Reconnecting');current.onmessage=message=>{queue=queue.catch(()=>{}).then(()=>{if(stream===current)return handle(JSON.parse(message.data))}).catch(e=>{status(e.message);current.close();if(stream===current){stream=null;clearTimeout(retry);retry=setTimeout(connect,1500)}})}}
async function init(){try{await readiness;const snapshot=await get('/api/snapshot');cursor=snapshot.cursor;el('listenerUser').textContent='Listening as '+snapshot.user.name+' · '+identity;el('listenerInbox').href='/?user='+encodeURIComponent(identity)+(hostMode?'&host=finsemble':'&listener=1');if(hostMode){el('listenerMode').textContent='Finsemble app service';el('listenerHelp').textContent='Receives server events and opens registered Pulse web windows.'}connect()}catch(e){status('Startup failed: '+e.message);if(!stopped)retry=setTimeout(init,3000)}}
window.addEventListener('pagehide',()=>{stopped=true;clearTimeout(retry);stream?.close()});init();
