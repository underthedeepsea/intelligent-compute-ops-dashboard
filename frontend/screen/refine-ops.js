/* Pure display models. No thresholds, percentile aggregation, or failover execution. */
(function(root){'use strict';
const order={UNKNOWN:0,NORMAL:1,OK:1,PASS:1,WARNING:2,CRITICAL:3,FAIL:3,ERROR:3};
const tone=s=>order[s]===3?'red':s==='WARNING'?'amber':order[s]===1?'mint':'';
const statusLabel=s=>order[s]===3?'ERROR · 严重':s==='WARNING'?'WARNING · 告警':order[s]===1?'正常':'状态未知';
function unique(rows){return [...new Map(rows.filter(x=>x&&x.id).map(x=>[(x.environment_code||'')+':'+x.id,x])).values()];}
function rollup(rows,status=x=>x?.status){const states=rows.map(x=>status(x)||'UNKNOWN'),severe=states.filter(s=>order[s]===3).length,warn=states.filter(s=>s==='WARNING').length,unknown=states.filter(s=>!order[s]).length;return {status:severe?'CRITICAL':warn?'WARNING':unknown||!states.length?'UNKNOWN':'NORMAL',severe,warn,unknown,total:states.length};}
function belongs(b,ep){return (b.pd_group_ids||[]).includes(ep.pd_group_id)&&(!b.deployment_scope_declared||(b.deployment_scope_ids||[]).includes(ep.deployment_scope_id));}
function groups(catalog,service,observed,status){
 const obs=new Map(observed.map(e=>[e.id,e]));
 return (catalog['pd-groups']||[]).filter(g=>g.enabled!==false&&g.service_id===service.id&&g.environment_code===service.environment_code).map(g=>{
  const members=(catalog.endpoints||[]).filter(ep=>ep.enabled!==false&&ep.pd_group_id===g.id);
  const rows=members.map(ep=>({...ep,...(obs.get(ep.id)||{status:'UNKNOWN',data_state:'MISSING',observation:null,metrics:{}})}));
  const deployments=(catalog['deployment-scopes']||[]).filter(d=>d.pd_group_id===g.id).map(d=>{const subset=rows.filter(ep=>ep.deployment_scope_id===d.id||(ep.namespace===d.namespace&&ep.cluster_id===d.cluster_id));return {...d,rows:subset,health:rollup(subset,status)};});
  return {...g,rows,deployments,p:rollup(rows.filter(e=>e.role==='PREFILL'),status),d:rollup(rows.filter(e=>e.role==='DECODE'),status),health:rollup(rows,status)};
 });
}
function families(gs){
 // One visual card IS one logical PD Group ID, not a grouping facade over four IDs.
 return gs.map(g=>({key:g.id,name:g.name,label:g.name.endsWith('-fallback')?'fallback':g.name.match(/-(\d+)$/)?.[1]||g.name,groups:[g]})).sort((a,b)=>a.label==='fallback'?1:b.label==='fallback'?-1:a.label.localeCompare(b.label));
}
function pick(rows,key,present){const values=rows.map(entity=>({entity,m:present(entity,key),key})).filter(x=>x.m.value!==null&&Number.isFinite(x.m.value)),current=values.filter(x=>x.m.usable),pool=current.length?current:values.filter(x=>['STALE','SOURCE_ERROR','UNVERIFIED','CSV_SNAPSHOT'].includes(x.m.state));return pool.sort((a,b)=>b.m.value-a.m.value||a.entity.id.localeCompare(b.entity.id))[0]||{entity:null,m:present(null,key),key};}
function representative(rows,key,present,status=x=>x?.status){
 const candidates=rows.map(entity=>({entity,m:present(entity,key)})).filter(x=>x.m.value!==null&&Number.isFinite(x.m.value));
 const current=candidates.filter(x=>x.m.usable),history=candidates.filter(x=>['STALE','SOURCE_ERROR','UNVERIFIED','CSV_SNAPSHOT'].includes(x.m.state));
 const pool=current.length?current:history;
 return pool.sort((a,b)=>(order[status(b.entity)]||0)-(order[status(a.entity)]||0)||b.m.value-a.m.value||a.entity.id.localeCompare(b.entity.id))[0]?.entity||null;
}
function finding(entity,key,status=x=>x?.status){
 if(!['WARNING','CRITICAL','FAIL','ERROR'].includes(status(entity)))return null;
 return (entity?.findings||[]).filter(f=>!key||f.key===key).slice().sort((a,b)=>(order[b.level]||0)-(order[a.level]||0)||(b.observed_value/(b.threshold||Infinity))-(a.observed_value/(a.threshold||Infinity))||String(a.rule_id).localeCompare(String(b.rule_id)))[0]||null;
}
function businessMetrics(app,present,status=x=>x?.status){
 const eps=unique((app.dependency_services||[]).flatMap(s=>s.endpoints||[])),p=eps.filter(e=>['PREFILL','COMBINED'].includes(e.role)),d=eps.filter(e=>['DECODE','COMBINED'].includes(e.role));
 const latencyP=pick(p,'ttft_p95_ms',present),latencyD=pick(d,'tpot_p95_ms',present);
 const rp=representative(p,'ttft_p95_ms',present,status),rd=representative(d,'tpot_p95_ms',present,status);
 const metricAt=(entity,key)=>({entity,key,m:present(entity,key)});
 const active=eps.flatMap(entity=>(entity.findings||[]).map(f=>({entity,key:f.key,f,m:present(entity,f.key)}))).filter(x=>x.m.usable&&finding(x.entity,null,status));
 active.sort((a,b)=>(order[b.f.level]||0)-(order[a.f.level]||0)||(b.f.observed_value/(b.f.threshold||Infinity))-(a.f.observed_value/(a.f.threshold||Infinity))||a.entity.id.localeCompare(b.entity.id)||a.key.localeCompare(b.key));
 const trend=active[0]||{...metricAt(rd,'e2e_p99_ms'),f:null};
 return {endpoints:eps,p:rp,d:rd,trend,activeFindings:active,selection_rule:'CURRENT_THEN_SEVERITY_THEN_PHASE_LATENCY_THEN_ID',tiles:[
 {...latencyP,label:'最慢 P · TTFT P95'}, {...latencyD,label:'最慢 D · TPOT P95'},
 {...pick(eps,'e2e_p99_ms',present),label:'最慢实例 · E2E P99'},
 {...metricAt(rp,'request_rate'),label:'代表 P · QPS'},
 {...metricAt(rd,'generated_tokens_per_second'),label:'代表 D · 输出 Token'},
 {...pick(eps,'waiting',present),label:'最大实例 · 排队请求'}
 ].map(t=>({...t,finding:finding(t.entity,t.key,status)})),cache:metricAt(rd,'kv_cache_hit_ratio'),prompt:metricAt(rp,'input_tokens_per_second')};
}
function hostContext(entity,catalog){
 const isHost=['HOST','GPU_POOL'].includes(entity?.resource_type),names=isHost?[entity.node_name||entity.host_id]:(entity?.configured_nodes||[]);
 const hs=(catalog['gpu-hosts']||[]).filter(h=>names.includes(h.node_name)&&h.cluster_id===entity?.cluster_id&&h.environment_code===entity?.environment_code);
 const roles=isHost?[...new Set(hs.flatMap(h=>h.roles||[]))]:[entity?.role||'UNKNOWN'];
 const role=roles.includes('PREFILL')&&roles.includes('DECODE')?'P / D 共享主机':roles.includes('PREFILL')?'P 实例主机':roles.includes('DECODE')?'D 实例主机':roles.includes('COMBINED')?'合并推理主机':'主机角色待登记';
 const models=[...new Set(hs.map(h=>h.gpu_model).filter(Boolean))];
 return {role,models,modelText:models.join(' / ')||'卡型待登记',modelSource:hs.some(h=>h.gpu_model_source==='SCENARIO')?'SCENARIO':'REGISTERED',hosts:hs};
}
function escape(app,status){const plan=app.recovery||{},targets=unique((app.recovery_dependencies||[]).flatMap(s=>s.endpoints||[]));const health=rollup(targets,status);
 return {configured:!!plan.configured,role:plan.role||'UNCONFIGURED',targets:plan.target_group_ids||[],health,readiness:'UNVERIFIED',automatic_switch:false,label:plan.configured?'可逃生 · 双活预案':plan.role==='FALLBACK_POOL'?'双活承接池':'未登记逃生预案',note:plan.configured?(health.severe||health.warn?'候选池存在告警 · 承载能力待验证':health.unknown||!targets.length?'候选池状态未知 · 承载能力待验证':'候选池当前无告警 · 承载能力待验证'):plan.role==='FALLBACK_POOL'?'已承担 fallback 角色 · 不自指逃生':'需补齐目标与切换验证'};
}
const api={belongs,tone,statusLabel,rollup,groups,families,businessMetrics,representative,finding,hostContext,escape,unique};root.RefineOps=api;if(typeof module!=='undefined')module.exports=api;
})(typeof window==='undefined'?globalThis:window);
