/* Current-screen only. Wall-clock dwell, never replay-clock dwell or navigation. */
(function(root){'use strict';
const bad=s=>['WARNING','CRITICAL','ERROR','FAIL'].includes(s),good=s=>['NORMAL','OK','PASS'].includes(s);
class LocalCycle{
 constructor(){this.enabled=true;this.elapsed=0;this.last=null;this.signature='';this.interval=10000;this.total=0;this.mode='empty';}
 reset(){this.elapsed=0;this.last=null;}
 tick(time,rows,current,status,{blocked=false,abnormalOnly=false,scope=''}={}){
  const abnormal=rows.filter(x=>bad(status(x))),normal=rows.filter(x=>good(status(x)));
  const candidates=(abnormal.length?abnormal:abnormalOnly?[]:normal).slice().sort((a,b)=>a.id.localeCompare(b.id));
  this.mode=abnormal.length?'abnormal':candidates.length?'normal':'empty';this.total=candidates.length;
  this.interval=abnormal.length?30000:10000;
  const sig=scope+':'+this.mode+':'+candidates.map(x=>x.id).join('|');
  if(sig!==this.signature){this.signature=sig;this.elapsed=0;this.last=time;}
  const delta=this.last===null?0:Math.max(0,Math.min(time-this.last,30000));this.last=time;
  if(!this.enabled||blocked||!candidates.length)return null;
  this.elapsed+=delta;
  if(this.elapsed<this.interval)return null;
  this.elapsed=0;
  if(candidates.length===1&&candidates[0].id===current)return null;
  const index=candidates.findIndex(x=>x.id===current);
  return candidates[(index+1)%candidates.length].id;
 }
 get snapshot(){return {enabled:this.enabled,mode:this.mode,total:this.total,interval:this.interval,remaining:Math.ceil((this.interval-this.elapsed)/1000)};}
}
const api={LocalCycle};root.RefineCycle=api;if(typeof module!=='undefined')module.exports=api;
})(typeof window==='undefined'?globalThis:window);
