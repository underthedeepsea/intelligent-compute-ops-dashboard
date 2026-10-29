/* Only consumes masked.v3. No original dataset, thresholds or numeric readings. */
(function(root){'use strict';
const LABEL={G:'正常',W:'WARNING · 告警',R:'ERROR · 严重',U:'状态待确认',O:'同期对比'};
const TONE={G:'mint',W:'amber',R:'red',U:'muted',O:'sky'};
const METRICS={TTFT:'首 Token 延迟 · TTFT',TPOT:'逐 Token 延迟 · TPOT',E2E:'端到端尾延迟 · E2E',QUEUE:'排队压力',QPS:'请求流量',OUT:'输出 Token 吞吐',IN:'输入 Token 吞吐',KV:'KV 缓存命中',CPU:'处理器负载',MEM:'内存压力',FS:'文件系统压力'};
const SEVERITY={O:0,G:1,U:2,W:3,R:4};
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const aggregate=ss=>{const a=[...ss];return a.includes('R')?'R':a.includes('W')?'W':!a.length||a.includes('U')?'U':'G';};
const anomaly=s=>s==='W'||s==='R';
function validate(d){
 const exact=(o,keys)=>o&&typeof o==='object'&&!Array.isArray(o)&&Object.keys(o).sort().join('|')===[...keys].sort().join('|');
 if(!exact(d,['schema','mode','frames','interval_ms','default_frame','catalog','tracks'])||d.schema!=='masked.v3'||d.mode!=='REPLAY'||!Number.isInteger(d.frames)||d.frames<1||d.frames>10000||!Number.isInteger(d.interval_ms)||d.interval_ms<1000||d.interval_ms>300000||!Number.isInteger(d.default_frame)||d.default_frame<0||d.default_frame>=d.frames)throw new Error('脱敏数据契约不匹配');
 const fields={services:['id','name','mode'],groups:['id','name','service'],businesses:['id','name','services','groups','endpoints','recovery','candidates','representatives'],endpoints:['id','role','service','group','hosts'],hosts:['id','role','groups']};
 if(!exact(d.catalog,Object.keys(fields)))throw new Error('脱敏目录契约不匹配');
 const ids=new Set(), maps={};
 for(const [col,keys] of Object.entries(fields)){
  if(!Array.isArray(d.catalog[col])||d.catalog[col].length>5000)throw new Error('目录数量无效');
  maps[col]=new Map();
  for(const row of d.catalog[col]){
   if(!exact(row,keys)||typeof row.id!=='string'||! /^[csgbeh][a-f0-9]{24}$/.test(row.id)||ids.has(row.id))throw new Error('目录字段无效');
   ids.add(row.id);maps[col].set(row.id,row);
   for(const k of ['name'])if(k in row&&(typeof row[k]!=='string'||!row[k]||row[k].length>160||/[\x00-\x1f]/.test(row[k])))throw new Error('名称无效');
  }
 }
 const refs=(a,col)=>{if(!Array.isArray(a)||new Set(a).size!==a.length||a.some(x=>!maps[col].has(x)))throw new Error('目录引用无效');};
 for(const g of d.catalog.groups){refs([g.service],'services');}
 for(const s of d.catalog.services)if(!['SPLIT_PD','COMBINED'].includes(s.mode))throw new Error('模式无效');
 for(const e of d.catalog.endpoints){refs([e.service],'services');refs(e.hosts,'hosts');if(e.group!==null)refs([e.group],'groups');if(!['P','D','C','ROUTER'].includes(e.role))throw new Error('阶段无效');}
 for(const h of d.catalog.hosts){refs(h.groups,'groups');if(!['P','D','P/D','OTHER'].includes(h.role))throw new Error('阶段无效');}
 for(const b of d.catalog.businesses){for(const k of ['services','groups','endpoints'])refs(b[k],k);refs(b.candidates,'groups');if(!['PLAN','POOL','NONE'].includes(b.recovery)||!exact(b.representatives,['P','D']))throw new Error('预案无效');for(const [role,a] of Object.entries(b.representatives)){if(!Array.isArray(a)||a.length!==d.frames||a.some(x=>x!==null&&(!b.endpoints.includes(x)||maps.endpoints.get(x)?.role!==role)))throw new Error('代表实例无效');}}
 const trackIDs=[...maps.endpoints.keys(),...maps.hosts.keys()];
 if(!exact(d.tracks,trackIDs))throw new Error('序列对象无效');
 for(const [id,t] of Object.entries(d.tracks)){
  if(!exact(t,['state','metrics'])||typeof t.state!=='string'||t.state.length!==d.frames||/[^GWRU]/.test(t.state))throw new Error('状态序列无效');
  const codes=maps.endpoints.has(id)?Object.keys(METRICS).slice(0,8):Object.keys(METRICS).slice(8);
  if(!exact(t.metrics,codes))throw new Error('趋势指标无效');
  for(const m of Object.values(t.metrics))if(!exact(m,['shape','state','comparison','comparison_basis'])||typeof m.shape!=='string'||typeof m.state!=='string'||m.shape.length!==d.frames||m.state.length!==d.frames||/[^abcdefghi-]/.test(m.shape)||/[^GWRUO]/.test(m.state)||typeof m.comparison!=='string'||m.comparison.length!==d.frames||/[^HLSN]/.test(m.comparison)||typeof m.comparison_basis!=='string'||m.comparison_basis.length!==d.frames||/[^DRN]/.test(m.comparison_basis)||[...m.comparison].some((x,i)=>(x==='N')!==(m.comparison_basis[i]==='N')))throw new Error('趋势只能包含区间与状态');
 }
 return d;
}
class Model{
 constructor(d){this.d=validate(d);this.cat=d.catalog;this.map=Object.fromEntries(Object.entries(this.cat).map(([k,a])=>[k,new Map(a.map(x=>[x.id,x]))]));}
 compare(id,code,step){const m=this.d.tracks[id]?.metrics[code];const direction=m?.comparison[step]||'N',basis=m?.comparison_basis[step]||'N';return {direction,basis,label:{H:'较高',L:'较低',S:'平稳',N:'样本不足'}[direction],basisLabel:{D:'历史同期',R:'近时段',N:'无可比基线'}[basis]};}
 state(id,step){return this.d.tracks[id]?.state[step]||'U';}
 eps(group){return this.cat.endpoints.filter(x=>x.group===group);}
 groupState(id,step){return aggregate(this.eps(id).map(x=>this.state(x.id,step)));}
 businessState(b,step){return aggregate(b.endpoints.map(id=>this.state(id,step)));}
 serviceState(id,step){return aggregate(this.cat.endpoints.filter(x=>x.service===id).map(x=>this.state(x.id,step)));}
 incidentIDs(kind,step){const a=kind==='h'?this.cat.hosts:this.cat.endpoints;return a.filter(x=>anomaly(this.state(x.id,step))).sort((a,b)=>SEVERITY[this.state(b.id,step)]-SEVERITY[this.state(a.id,step)]||a.id.localeCompare(b.id)).map(x=>x.id);}
 incident(id,step){const t=this.d.tracks[id];const keys=Object.keys(t.metrics);const hits=keys.filter(k=>anomaly(t.metrics[k].state[step]));hits.sort((a,b)=>SEVERITY[t.metrics[b].state[step]]-SEVERITY[t.metrics[a].state[step]]||keys.indexOf(a)-keys.indexOf(b));return hits[0]||keys[0];}
 businessesFor(id){const ep=this.map.endpoints.get(id);const eps=ep?[ep.id]:this.cat.endpoints.filter(x=>x.hosts.includes(id)).map(x=>x.id);return this.cat.businesses.filter(b=>eps.some(x=>b.endpoints.includes(x)));}
 groupIDsFor(id){const e=this.map.endpoints.get(id);return e?[e.group].filter(Boolean):this.map.hosts.get(id)?.groups||[];}
 metricChoice(b,code,step){const role=['TPOT','OUT','KV'].includes(code)?'D':'P';let id=b.representatives[role][step];if(['E2E','QUEUE'].includes(code)){const hits=b.endpoints.filter(x=>anomaly(this.d.tracks[x]?.metrics[code]?.state[step]));hits.sort((a,z)=>SEVERITY[this.d.tracks[z].metrics[code].state[step]]-SEVERITY[this.d.tracks[a].metrics[code].state[step]]||a.localeCompare(z));id=hits[0]||b.representatives[code==='E2E'?'D':'P'][step];}return {id,code};}
 businessChart(b,step){const hits=[];for(const id of b.endpoints)for(const [code,m]of Object.entries(this.d.tracks[id]?.metrics||{}))if(anomaly(m.state[step]))hits.push({id,code,state:m.state[step]});hits.sort((a,z)=>SEVERITY[z.state]-SEVERITY[a.state]||['QUEUE','TTFT','TPOT','E2E'].indexOf(a.code)-['QUEUE','TTFT','TPOT','E2E'].indexOf(z.code)||a.id.localeCompare(z.id));return hits[0]||{id:b.representatives.D[step]||b.endpoints[0],code:'E2E',state:'G'};}
}
// Real elapsed seconds, not source time or playback speed. Never navigates screens.
class Cycle{
 constructor(){this.elapsed=0;this.key='';}
 reset(){this.elapsed=0;}
 next({screen,ids,active,abnormal,allNormal,dt,paused}){const key=screen+'|'+ids.join('|')+'|'+abnormal;if(key!==this.key){this.key=key;this.elapsed=0;}if(paused||ids.length<2||!['02','03','04'].includes(screen)||(!abnormal&&!allNormal)){return null;}this.elapsed+=Math.max(0,Math.min(dt,1));const limit=abnormal?30:10;if(this.elapsed<limit)return null;this.elapsed=0;return ids[(Math.max(0,ids.indexOf(active))+1)%ids.length];}
}
const api={LABEL,TONE,METRICS,SEVERITY,esc,aggregate,anomaly,validate,Model,Cycle};
if(typeof module!=='undefined')module.exports=api;else root.MaskedCore=Object.freeze(api);
})(typeof window==='undefined'?globalThis:window);
