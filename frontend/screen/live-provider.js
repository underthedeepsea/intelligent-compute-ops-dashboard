(function(root){
'use strict';
function revision(value){ if(typeof value==='number' && Number.isSafeInteger(value))return BigInt(value);if(typeof value==='string' && /^\d+$/.test(value))return BigInt(value);throw new Error('无效 view_revision'); }
function freshness(item, now=Date.now()){
 const state=item?.data_state || item?.quality || 'UNKNOWN';
 const observation=item?.observation || item;
 const rawEnd=observation?.source_window?.end;
 if(observation?.source_type==='CSV' && state==='CSV_SNAPSHOT' && observation?.data_state==='CSV_SNAPSHOT'){const sampled=Date.parse(observation.sampled_at||rawEnd);return Number.isFinite(sampled)&&sampled-now<=30000?'CSV_SNAPSHOT':'INVALID';}
 const end=typeof rawEnd==='string'?Date.parse(rawEnd):NaN;
 const ttl=observation?.max_age_seconds;
 if(state==='FRESH' && (!Number.isFinite(end)||typeof ttl!=='number'||!Number.isFinite(ttl)||ttl<=0))return 'UNKNOWN';
 if(Number.isFinite(end)&&typeof ttl==='number'&&Number.isFinite(ttl)&&ttl>0){
  if(end-now>30000)return 'INVALID';
  if(now-end>Math.min(ttl,300)*1000)return 'STALE';
 }
 return state==='CSV_SNAPSHOT'?'UNKNOWN':state;
}
function sourceTransport(item){return item?.observation?.transport_status || 'UNKNOWN';}
function endpointState(item,now=Date.now()){
 return freshness(item,now)==='FRESH' && sourceTransport(item)==='OK' ? item.status : 'UNKNOWN';
}

class LiveProvider {
 constructor({path,onData,onError,onAge=()=>{},onContact=()=>{},request,interval=15000,document:doc=root.document}){Object.assign(this,{path,onData,onError,onAge,onContact,request:request || root.ControlAPI.request,interval,doc});this.value=null;this.lastRevision=null;this.running=false;this.generation=0;this.visibility=()=>{if(this.doc.hidden)this.cancel();else if(this.running)this.poll();};}
 start(){if(this.running)return;this.running=true;this.doc?.addEventListener('visibilitychange',this.visibility);this.ageTimer=setInterval(()=>{if(!this.doc?.hidden && this.value)this.onAge(this.value);},1000);this.poll();}
 cancel(){this.generation++;clearTimeout(this.timer);this.controller?.abort();this.controller=null;}
 stop(){this.running=false;this.cancel();clearInterval(this.ageTimer);this.doc?.removeEventListener('visibilitychange',this.visibility);}
 async poll(){if(!this.running || this.doc?.hidden)return;this.cancel();const generation=this.generation;this.controller=new AbortController();const controller=this.controller;const timeout=setTimeout(()=>controller.abort(),10000);
 try{const value=await this.request(this.path,{signal:this.controller.signal});if(generation!==this.generation || !this.running)return;const next=revision(value.view_revision);this.onContact();if(this.lastRevision===null || next>this.lastRevision){this.onData(value);this.value=value;this.lastRevision=next;}else if(next===this.lastRevision){this.onAge(this.value);}}
 catch(error){if(generation===this.generation && this.running)this.onError(error,this.value);}finally{clearTimeout(timeout);if(generation===this.generation && this.running && !this.doc?.hidden)this.timer=setTimeout(()=>this.poll(),this.interval);}
 }
}
const api={LiveProvider,revision,freshness,sourceTransport,endpointState};if(typeof module!=='undefined')module.exports=api;root.LiveData=api;
})(typeof window!=='undefined'?window:globalThis);
