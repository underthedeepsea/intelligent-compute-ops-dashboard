/* Native, dependency-free replacement shell for v0.5.0 /screen/. Read-only. */
(() => {
'use strict';
const C=window.RefineContract, O=window.RefineOps, e=C.escape;
const SCREENS={ '01':['全局总览','智算运行态势','COMPUTE OPERATIONS / OVERVIEW','目录与观测，分层呈现'], '02':['推理部署','分离推理工作台','INFERENCE / DEPLOYMENT','计算分离，连接上下文'], '03':['基础设施','基础设施异常定位','INFRASTRUCTURE / INCIDENTS','只呈现异常对象与命中证据'], '04':['服务诊断','推理服务异常定位','INFERENCE / SERVICE INCIDENTS','按部署组定位，业务关联不越界'], '05':['关键应用','关键应用守望','BUSINESS / CRITICAL APPLICATIONS','配置依赖不等于实际影响'] };
const PATHS={'01':'overview','02':'services','03':'overview','04':'services','05':'critical-apps'};
const q=new URLSearchParams(location.search);
const replay=document.body.dataset.offlinePreview==='true'||q.get('replay')==='szg-8h';
let screen=SCREENS[q.get('screen')]?q.get('screen'):(SCREENS[document.body.dataset.screen]?document.body.dataset.screen:'01');
let selected=q.get('id')||q.get('service')||'', endpointID=q.get('endpoint')||'', data=null, catalog={},
    loading=true, transportError='', catalogError='', emptyReplay=false, clockNow=Date.now(),
    generation=0, currentController=null, pollTimer=null, disposed=false, auto=false, visibleSeconds=0,
    refreshSeconds=15, pollBusy=false, drawerTrigger=null, activeDialog=null, activeMetric=null, workerPageP=0, workerPageD=0, groupID=q.get('group')||'', deploymentScopeID=q.get('scope')||'', selectedFault='';
const cache=new Map(), preference=matchMedia('(prefers-reduced-motion: reduce)');
let motion=true;try{motion=localStorage.getItem('ico-motion')!=='off';}catch{}
const icons={
 cube:'<path d="M12 3 3 8v8l9 5 9-5V8L12 3Zm0 0v9m-9-4 9 4 9-4m-9 4v9"/>',
 chip:'<rect x="6" y="6" width="12" height="12" rx="3"/><path d="M9 2v4m6-4v4M9 18v4m6-4v4M2 9h4m-4 6h4m12-6h4m-4 6h4"/><rect x="9" y="9" width="6" height="6" rx="1"/>',
 grid:'<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>',
 nodes:'<rect x="8" y="2" width="8" height="6" rx="2"/><rect x="2" y="16" width="7" height="6" rx="2"/><rect x="15" y="16" width="7" height="6" rx="2"/><path d="M12 8v4H5v4m7-4h7v4"/>',
 shield:'<path d="m12 2 8 3v7c0 5-8 10-8 10S4 17 4 12V5l8-3Z"/><path d="m8 12 3 3 5-6"/>',
 pause:'<path d="M8 5v14M16 5v14"/>',play:'<path d="m8 4 12 8-12 8V4Z"/>',
 motion:'<path d="m12 2-2 8H3l9 12 2-8h7L12 2Z"/>',
 full:'<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/>',
 info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v.5"/>',
 check:'<path d="m4 12 5 5L20 6"/>',
 host:'<rect x="3" y="3" width="18" height="7" rx="2"/><rect x="3" y="14" width="18" height="7" rx="2"/><path d="M6 6.5h1m3 0h1m-5 11h1m3 0h1M17 6.5h1m-1 11h1"/>',
 book:'<path d="M12 5c-4-3-9-2-9-2v17s5-1 9 2c4-3 9-2 9-2V3s-5-1-9 2Zm0 0v17"/>',
 refresh:'<path d="M20 7v5h-5M4 17v-5h5"/><path d="M6 6a8 8 0 0 1 13 2M18 18A8 8 0 0 1 5 16"/>',
 alert:'<path d="m12 3 10 18H2L12 3Z"/><path d="M12 9v5m0 3v.5"/>',
 graph:'<path d="M3 3v18h18M6 15l4-5 4 3 7-8"/>',
 link:'<path d="m9 15 6-6m-6-2 2-2a5 5 0 0 1 7 7l-2 2m-1 3-2 2a5 5 0 0 1-7-7l2-2"/>'
};
const icon=name=>`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name]||icons.cube}</svg>`;
const fmt=v=>C.finite(v)?v.toLocaleString('zh-CN'):'—';
const opts=()=>({replay,transportError:!!transportError});
const now=()=>replay?window.SceneReplay.NOW:Date.now();
const stateLabel=s=>C.LABELS[s]||s;
const badge=(text,tone='')=>`<span class="badge ${e(tone)}">${e(text)}</span>`;
const statusText=s=>({NORMAL:'上游正常',OK:'上游 OK',PASS:'上游 PASS',WARNING:'WARNING · 告警',CRITICAL:'ERROR · 严重',FAIL:'上游 FAIL',ERROR:'上游 ERROR',UNKNOWN:'状态未知'})[s]||'状态未知';
const statusTone=s=>['CRITICAL','FAIL','ERROR'].includes(s)?'red':s==='WARNING'?'amber':['NORMAL','OK','PASS'].includes(s)?'mint':'';
const anomaly=s=>['WARNING','CRITICAL','FAIL','ERROR'].includes(s);
function env(){const values=[...new Set(C.endpoints(data).map(x=>x.environment_code).filter(Boolean))];return replay?(catalog.clusters?.[0]?.environment_code||'PRD'):values.length===1?values[0]:values.length>1?'多环境视图':'环境待确认';}
function origin(){const values=[...new Set(Object.values(catalog).flat().map(x=>x.origin||'UNKNOWN'))];return replay?'Gateway 登记目录':values.length===1?`目录 ${values[0]}`:values.length>1?'混合目录来源':'目录来源待确认';}
function summaryCount(key,collection=key){return C.finite(data?.summary?.[key])?data.summary[key]:Object.prototype.hasOwnProperty.call(catalog,collection)?catalog[collection].length:null;}
function metric(x,key){return C.present(x,key,now(),opts());}
function epStatus(x){return C.endpointStatus(x,now(),opts());}
function allEndpoints(){return C.endpoints(data);}
function cover(){return C.coverage(allEndpoints(),now(),opts());}
function titlePanel(title,english='',trailing=''){return `<div class="panel-head"><h2>${e(title)}${english?`<span class="overline">${e(english)}</span>`:''}</h2>${trailing}</div>`;}
function deployment(s){const entry=(catalog.services||[]).find(x=>x.id===s.id&&x.environment_code===s.environment_code);return {code:entry?.deployment_mode||'UNKNOWN',label:({SPLIT_PD:'P/D 分离',COMBINED:'合并推理'})[entry?.deployment_mode]||'部署模式待确认'};}
function selectedService(){const rows=data?.items||[];const direct=rows.find(x=>x.id===selected);if(direct)return direct;if(selected){const related=rows.find(x=>(x.endpoints||[]).some(ep=>ep.id===selected||ep.pd_group_id===selected||ep.deployment_scope_id===selected));if(related){const ep=related.endpoints.find(ep=>ep.id===selected);if(ep)endpointID=ep.id;else{const dep=(catalog['deployment-scopes']||[]).find(d=>d.id===selected);groupID=dep?.pd_group_id||selected;deploymentScopeID=dep?.id||'';}selected=related.id;return related;}return null;}return rows[0];}
function selectedEndpoint(service){const rows=service?.endpoints||allEndpoints();return rows.find(x=>x.id===endpointID)||rows[0];}
function sourceCaption(x){const quality=C.quality(x,now(),opts());return `${replay&&quality!=='REPLAY'?'回放窗口 · ':''}${stateLabel(quality)} · ${x?.observation?.identity?.scope==='DEVICE'?'单设备':'单 Endpoint'}`;}
function detailButton(entity,key,content,classes=''){return `<button class="${classes}" data-detail="metric" data-entity="${e(entity?.id||'')}" data-key="${e(key)}">${content}</button>`;}
function metricCard(x,key){const m=metric(x,key);return detailButton(x,key,`<span>${e(m.label)}</span><strong class="number ${m.usable?'':'muted'}">${e(m.text)}<small>${e(m.unit)}</small></strong><small>${e(sourceCaption(x))}</small>`,'surface metric-card');}
function kpi(label,value,sub,unit='',tone='',glyph=''){return `<section class="surface kpi"><div><div class="kpi-label">${e(label)}</div><div class="kpi-sub">${e(sub)}</div></div><div class="kpi-value number ${tone}">${value}${unit?`<em>${e(unit)}</em>`:''}</div>${glyph?`<div class="kpi-icon">${icon(glyph)}</div>`:''}</section>`;}
function globalKpis(){const c=cover();return `<div class="kpis">${kpi('已登记集群',fmt(summaryCount('clusters')),'Gateway 目录 · 非健康集群数','个')}${kpi('已登记推理服务',fmt(summaryCount('services')),'服务目录 · 保留部署模式','项')}${kpi('已登记 Endpoint',fmt(summaryCount('endpoints')),'阶段入口 · 非独立 Pod 数','个')}${kpi(replay?'当前窗口覆盖':'有效观测覆盖',`${c.fresh}<small> / ${c.total}</small>`,replay?'采样窗口 · 不代表实时状态':'当前投影 · 新鲜且来源可信','','ratio')}</div>`;}
function meter(x,key,label,sky=false){const m=metric(x,key);return `<div class="meter-line"><div class="meter-heading"><span>${e(label||m.label)}</span><b>${e(m.text)}<small>${e(m.unit)}</small></b></div><div class="track ${sky?'sky':''}">${m.value!==null&&m.unit==='%'?`<i style="width:${m.value*100}%"></i>`:''}</div></div>`;}
function coveragePanel(){const c=cover();return `<section class="surface panel coverage-panel">${titlePanel('观测覆盖','OBSERVATION COVERAGE')}<div class="coverage-numbers"><strong>${c.ratio===null?'—':(c.ratio*100).toFixed(1)}<small>%</small></strong><span>有效窗口 / 登记 Endpoint</span></div><div class="segmented-track">${c.total?`<i style="width:${c.fresh/c.total*100}%"></i><i style="width:${c.stale/c.total*100}%"></i><i style="width:${c.unknown/c.total*100}%"></i>`:''}</div><div class="legend"><span>有效 ${c.fresh}</span><span class="stale">过期 ${c.stale}</span><span class="unknown">其他 ${c.unknown}</span></div><div class="divider"></div><p class="tiny-note">覆盖率不是健康率。${replay?'当前回放窗口内的观测覆盖。':'分母仅为当前可见、已登记 Endpoint。'}</p></section>`;}
function hardwareMini(){const x=(data.hardware||[]).find(x=>x.resource_type==='HOST')||(data.hardware||[])[0],host=x?.resource_type==='HOST';return `<section class="surface panel hardware-mini">${titlePanel('节点资源观测','NODE OBSERVATION',`<button data-nav="03" aria-label="查看基础设施异常">↗</button>`)}<div class="device-label">${icon(host?'host':'chip')}<span>${e(x?.name||'尚未绑定设备')}</span></div>${meter(x,host?'cpu_busy_ratio':'utilization_ratio',host?'CPU 忙碌率':'GPU 利用率')}${meter(x,'memory_usage_ratio',host?'内存使用率':'显存使用率',true)}<div class="divider"></div><p class="tiny-note">${e(sourceCaption(x))}<br>仅当前节点，不外推为资源池利用率</p></section>`;}
function topology(){
 const bs=(catalog.businesses||[]).slice(0,3), ss=(catalog.services||[]).slice(0,3);
 // Unconnected rays meet a DIRECTORY hub; they are NOT business→service dependencies.
 const canDraw=bs.length||ss.length;
 const rays=[...bs.map((_,i)=>`<path class="diagram-line" d="M190 ${65+i*120} C290 ${65+i*120} 280 205 400 205"/>`),...ss.map((_,i)=>`<path class="diagram-line" d="M610 ${65+i*120} C510 ${65+i*120} 520 205 400 205"/>`)].join('');
 return `<section class="surface glass focus topology">${titlePanel('服务关系视图','REGISTERED DIRECTORY',badge('登记关系示意','mint'))}<div class="topology-canvas">${canDraw?`<svg class="graph-svg" viewBox="0 0 800 450" preserveAspectRatio="none" aria-hidden="true"><ellipse class="diagram-orbit" cx="400" cy="205" rx="132" ry="133"/><ellipse class="diagram-orbit" cx="400" cy="205" rx="176" ry="177"/>${rays}</svg><div class="topo-hub">${icon('nodes')}<b>统一资源目录</b><small>DIRECTORY</small></div>${bs.map((b,i)=>`<button class="topo-node left n${i+1}" data-nav="05" data-id="${e(b.id)}"><span class="node-label">${e(b.name)}</span><small>登记业务 · 查看依赖 ↗</small><i class="node-dot"></i></button>`).join('')}${ss.map((s,i)=>`<button class="topo-node right n${i+1}" data-nav="02" data-id="${e(s.id)}"><span class="node-label">${e(s.name)}</span><small>${e(deployment(s).label)} · 服务目录</small><i class="node-dot"></i></button>`).join('')}<div class="topo-count"><strong>${fmt(summaryCount('endpoints'))}</strong>已登记 Endpoint</div>`:`<div class="topology-empty">目录尚未读取，不生成关系节点。</div>`}</div><div class="topo-foot"><span>左：登记业务　·　右：登记服务</span><span>目录关联，非真实请求流</span></div>${(catalog.businesses?.length>3||catalog.services?.length>3)?'<p class="tiny-note">总览各显示前 3 项；完整列表请进入关键应用或推理部署。</p>':''}</section>`;
}
function riskPanel(){const rows=allEndpoints().filter(x=>anomaly(epStatus(x))).sort((a,b)=>Number(epStatus(b)==='CRITICAL')-Number(epStatus(a)==='CRITICAL'));return `<section class="surface panel notice-panel">${titlePanel('需要关注','OBSERVED SIGNALS',`<span class="tag">${rows.length} 条已知异常</span>`)}${rows.length?rows.slice(0,3).map(x=>`<div class="risk-row"><i class="risk-dot ${epStatus(x)==='CRITICAL'?'red':''}"></i><div class="risk-copy"><strong>${e(x.name)}</strong><p>${e(statusText(epStatus(x)))} · ${replay?'回放样本':'原始上游状态'}</p></div><button data-nav="04" data-id="${e(x.service_id)}" data-endpoint="${e(x.id)}" aria-label="查看 ${e(x.name)}">↗</button></div>`).join(''):`<div class="callout">当前没有<strong>可确认的上游异常</strong>。这不代表所有资源健康，仍需检查来源覆盖与时效。</div>`}</section>`;}
function capabilityPanel(){const groups=catalog['pd-groups']||[],pods=catalog.pods||[];return `<section class="surface panel capability-panel">${titlePanel('部署目录','DEPLOYMENT REGISTER')}<div class="cap-row"><span>Namespace / 部署组</span><span>${new Set(groups.flatMap(g=>g.namespaces||[g.namespace]).filter(Boolean)).size} / ${groups.length}</span></div><div class="cap-row"><span>去重 Pod 引用</span><span>${pods.length} 个</span></div><div class="cap-row"><span>登记节点</span><span>${new Set(pods.map(p=>p.node_name).filter(Boolean)).size} 台</span></div><div class="cap-row"><span>业务入口 SLI / KV 实测</span><span>未接入</span></div><a class="quiet-button" style="margin-top:15px" href="/gateway/production-catalog.html">打开生产目录 ↗</a></section>`;}
function overview(){return `${globalKpis()}<div class="overview-grid"><div class="stack">${hardwareMini()}${coveragePanel()}</div>${topology()}<div class="stack">${riskPanel()}${capabilityPanel()}</div></div>`;}
function role(x){return ['P','PREFILL'].includes(x.role)?'P':['D','DECODE'].includes(x.role)?'D':x.role==='COMBINED'?'COMBINED':x.role==='ROUTER'?'ROUTER':'UNKNOWN';}
function worker(x,ep){
 const st=epStatus(x),type=['CRITICAL','FAIL','ERROR'].includes(st)?'critical':st==='WARNING'?'warning':st==='UNKNOWN'?'unknown':'normal';
 return `<button class="worker is-${type} ${x.id===ep?.id?'active':''}" data-endpoint-select="${e(x.id)}" title="${e(x.name)} · ${e(statusText(st))}" aria-pressed="${x.id===ep?.id}"><span class="worker-indicator">${icon('chip')}</span><span class="worker-copy"><strong>${e(x.name)}</strong><small>${e(st==='UNKNOWN'?stateLabel(C.quality(x,now(),opts())):statusText(st))}</small></span><i class="worker-check">${x.id===ep?.id?'✓':''}</i></button>`;
}
function flowBank(title,rows,ep,bank){
 const health=O.rollup(rows,epStatus);
 const count=Math.max(1,Math.ceil(rows.length/8)),current=Math.min(bank==='P'?workerPageP:workerPageD,count-1);
 if(bank==='P')workerPageP=current;else workerPageD=current;
 const podids=new Set(rows.flatMap(x=>(catalog.endpoints||[]).find(c=>c.id===x.id)?.pod_ids||x.pod_ids||[])),pods=(catalog.pods||[]).filter(p=>podids.has(p.id));
 return `<section class="endpoint-bank ${bank==='D'?'decode-bank':''} health-${O.tone(health.status)}" data-stage-status="${health.status}"><header class="endpoint-bank-head"><span><b>${e(title)} ${badge(O.statusLabel(health.status),O.tone(health.status))}</b><small>${rows.length} 工作负载 · ${pods.length} Pod 登记</small></span><div class="bank-tools">${count>1?`<button data-bank="${bank}" data-delta="-1" ${current===0?'disabled':''}>←</button><small>${current+1} / ${count}</small><button data-bank="${bank}" data-delta="1" ${current===count-1?'disabled':''}>→</button>`:'<small>工作负载指标 / Pod 登记分开</small>'}</div></header><div class="workers ${rows.length===1?'one-workload':''}">${rows.slice(current*8,current*8+8).map(x=>worker(x,ep)).join('')||'<p class="bank-empty">尚未登记该阶段工作负载</p>'}</div><div class="pod-reference-grid">${pods.slice(0,8).map(p=>`<button data-detail="pod" data-entity="${e(p.id)}" title="${e(p.pod_name)} · ${e(p.node_name)}"><span>${e(p.pod_name.replace(p.workload_ref,'')||p.pod_name)}</span><small>${e(p.node_name||'节点待登记')}</small></button>`).join('')}</div></section>`;
}
function deploymentScreen(){
 const svc=selectedService();if(!svc)return noItems(selected?'请求的服务 / 分组不在当前可见目录':'尚未登记推理服务');
 const mode=deployment(svc),es=svc.endpoints||[],coverage=C.coverage(es,now(),opts()),gs=O.groups(catalog,svc,es,epStatus),families=O.families(gs);
 const aliased=(catalog['deployment-scopes']||[]).find(d=>d.id===groupID);if(aliased){deploymentScopeID=aliased.id;groupID=aliased.pd_group_id;}
 const groups=gs.map(g=>g.id);if(!groups.includes(groupID))groupID=(gs.slice().sort((a,b)=>(b.health.severe*3+b.health.warn)-(a.health.severe*3+a.health.warn)).find(g=>g.health.severe||g.health.warn)||gs.find(g=>g.placement_state==='SEPARATE_REPORTED')||gs[0])?.id||'';
 const groupMeta=gs.find(g=>g.id===groupID)||{},scopes=groupMeta.deployments||[],scopeMeta=scopes.find(d=>d.id===deploymentScopeID)||scopes.slice().sort((a,b)=>(b.health.severe*3+b.health.warn)-(a.health.severe*3+a.health.warn))[0]||groupMeta;deploymentScopeID=scopeMeta.id||'';const colocated=scopeMeta.placement_state==='COLOCATED_REPORTED',split=mode.code==='SPLIT_PD',combined=mode.code==='COMBINED';
 const rows=split?scopeMeta.rows||groupMeta.rows||es.filter(x=>x.pd_group_id===groupID):es,ep=rows.find(x=>x.id===endpointID)||rows[0]||selectedEndpoint(svc);
 const prefills=rows.filter(x=>role(x)==='P'),decodes=rows.filter(x=>role(x)==='D'),complete=split&&!colocated&&prefills.length>0&&decodes.length>0;
 const health=O.rollup(rows,epStatus),pHealth=O.rollup(prefills,epStatus),dHealth=O.rollup(decodes,epStatus);
 return `<div class="pd-workspace pd-multigroup">
  <section class="service-ribbon" aria-label="选择推理服务"><div class="ribbon-label">推理服务<span>SERVICES</span></div><div class="service-tabs">${(data.items||[]).map(x=>`<button class="service-option ${x.id===svc.id?'selected':''}" data-service="${e(x.id)}" title="${e(x.name)}"><span class="service-tab-mark">${icon('nodes')}</span><span><strong>${e(x.name)}</strong><small>${e(deployment(x).label)} · ${gs.length} 个 PD Group / ${gs.reduce((n,g)=>n+g.deployments.length,0)} 个部署范围</small></span></button>`).join('')}</div><div class="ribbon-coverage"><b>${coverage.fresh}<small> / ${coverage.total}</small></b><span>当前窗口覆盖<small>阶段入口 · 非健康率</small></span></div></section>
  <nav class="pd-family-rail" aria-label="P/D 分组全景">${families.map(f=>{const h=O.rollup(f.groups.flatMap(g=>g.rows),epStatus),active=f.groups.some(g=>g.id===groupID),target=f.groups.slice().sort((a,b)=>(b.health.severe*3+b.health.warn)-(a.health.severe*3+a.health.warn))[0];return `<button class="pd-family health-${O.tone(h.status)} ${active?'selected':''}" data-pd-group="${e(target.id)}" data-pd-family="${e(f.label)}" data-logical-group-id="${e(target.id)}" title="${e(f.name)}" aria-pressed="${active}"><span class="family-name"><b>${f.label==='fallback'?'Fallback 双活池':'PD Group '+e(f.label)}</b>${badge(O.statusLabel(h.status),O.tone(h.status))}</span><span class="family-meta"><code>${e(f.name)}</code><small>${f.groups.reduce((n,g)=>n+g.deployments.length,0)} 范围 · ${f.groups.reduce((n,g)=>n+g.rows.length,0)} 阶段</small></span><span class="family-health">${h.severe} ERROR　${h.warn} WARNING　${h.unknown} 待确认 <i>查看 →</i></span></button>`;}).join('')}</nav>
  <section class="surface glass focus flow-stage health-${O.tone(health.status)} ${split?'is-split':combined?'is-combined':'is-unresolved'} ${complete?'flow-complete':'flow-incomplete'}" data-flow-kind="${split?'split':combined?'combined':'unknown'}" data-flow-semantics="conceptual">
   <header class="flow-head"><div class="flow-title"><i></i><div><h2>${e(groupMeta.name||svc.name)} ${badge(O.statusLabel(health.status),O.tone(health.status))}</h2><small>${e(scopeMeta.namespace||svc.model_name||'范围待登记')} <span> / ${colocated?'同 Pod 阶段登记':'P/D 分离登记'}</span></small></div></div><div class="flow-controls"><button class="flow-legend" data-detail="flow">${icon('info')} 原理示意 · 非实时流量</button></div></header>
   <div class="pd-scope-row"><span>${scopes.length>1?'同一 PD Group 下的部署范围':'部署范围'}</span>${scopes.map(d=>`<button data-deployment-scope="${e(d.id)}" class="pd-scope ${d.id===deploymentScopeID?'active':''} health-${O.tone(d.health.status)}" title="${e(groupMeta.name)} / ${e(d.namespace)}" aria-pressed="${d.id===deploymentScopeID}">${e(d.namespace)}<i>${e(O.statusLabel(d.health.status))}</i></button>`).join('')}<label class="pd-select-label">PD Group<select id="pd-group" aria-label="选择 PD Group">${gs.map(g=>`<option value="${e(g.id)}" ${g.id===groupID?'selected':''}>${e(g.name)}</option>`).join('')}</select></label></div>
   <div class="phase-health-band"><span class="health-${O.tone(pHealth.status)}">PREFILL　${e(O.statusLabel(pHealth.status))}</span><small>${colocated?'同 Pod：不表示跨实例传输':'上下文交接：仅原理动画'}</small><span class="health-${O.tone(dHealth.status)}">DECODE　${e(O.statusLabel(dHealth.status))}</span></div>
   ${split?(colocated?window.RefineFlow.colocated():window.RefineFlow.split({p:prefills.length,d:decodes.length,complete})):combined?window.RefineFlow.combined():'<div class="unresolved-flow">模式尚未明确</div>'}
   <div class="endpoints-deck ${split?'':'combined-bank'}">${split?flowBank('PREFILL 实例池',prefills,ep,'P')+flowBank('DECODE 实例池',decodes,ep,'D'):flowBank('完整推理实例',rows,ep,'P')}</div>
   <footer class="flow-foot"><span>当前部署范围独立读数 · 同组不同 namespace 不混算 <button class="inline-action" data-detail="objects">全部实例 ↗</button></span><button data-detail="flow">KV 传输观测未接入 · 动画不映射负载 ${icon('info')}</button></footer>
  </section>
  <section class="surface endpoint-observer health-${statusTone(epStatus(ep))}"><div class="observer-identity"><div class="eyebrow">ENDPOINT INSPECTOR</div><h3 title="${e(ep?.name||'未选择实例')}">${e(ep?.name||'未选择实例')}</h3><div>${badge(statusText(epStatus(ep)),statusTone(epStatus(ep)))}</div><small>${e(sourceCaption(ep))}</small></div><div class="metrics-strip">${['ttft_p95_ms','tpot_p95_ms','e2e_p99_ms','waiting'].map(key=>metricCard(ep,key)).join('')}</div></section>
 </div>`;
}
function deviceCard(x){const gpu=x.resource_type==='GPU_POOL',m=metric(x,gpu?'utilization_ratio':'cpu_busy_ratio'),m2=metric(x,'memory_usage_ratio'),temp=metric(x,'temperature_celsius'),radius=50,circ=2*Math.PI*radius,fill=m.value!==null?m.value:0;return `<section class="surface device-card"><div class="device-card-head">${icon(gpu?'chip':'host')}<div><h3>${e(x.name)}</h3><small>${gpu?'GPU · 单设备':'HOST · 单主机'}　${e(x.host_id||'')}</small></div></div><div class="device-visual"><div class="device-dial"><svg viewBox="0 0 124 124" aria-hidden="true"><circle cx="62" cy="62" r="50" fill="none" stroke="rgba(127,185,208,.12)" stroke-width="4"/>${m.value!==null?`<circle cx="62" cy="62" r="50" fill="none" stroke="var(--accent-soft)" stroke-width="4" stroke-linecap="round" stroke-dasharray="${fill*circ} ${circ}"/>`:''}</svg><b>${e(m.text)}<small>${e(m.unit)}</small></b><small>${gpu?'GPU 利用率':'CPU 忙碌率'}</small></div><div class="device-values"><div class="meter-heading"><span>${gpu?'显存使用率':'内存使用率'}</span><b>${e(m2.text)}<small>${e(m2.unit)}</small></b></div>${gpu?`<div class="meter-heading" style="margin-top:20px"><span>GPU 温度</span><b>${e(temp.text)}<small>°C</small></b></div>`:''}<button class="quiet-button" style="margin-top:18px" data-detail="metric" data-entity="${e(x.id)}" data-key="${gpu?'utilization_ratio':'cpu_busy_ratio'}">查看来源 ↗</button></div></div><p class="tiny-note">${e(sourceCaption(x))} · 风险结论尚未接入</p></section>`;}
function hardwareScreen(){return faultScreen('HOST');}
function diagnostics(){return faultScreen('ENDPOINT');}

function faultEntities(kind){const list=kind==='HOST'?(data.hardware||[]):allEndpoints();return list.filter(x=>anomaly(epStatus(x))).sort((a,b)=>Number(epStatus(b)==='CRITICAL')-Number(epStatus(a)==='CRITICAL'));}
function relatedBusinesses(entity){const eps=entity.pd_group_id?[entity]:(catalog.endpoints||[]).filter(ep=>(ep.configured_nodes||[]).includes(entity.node_name||entity.host_id));return (catalog.businesses||[]).filter(b=>eps.some(ep=>O.belongs(b,ep)));}
function firstFinding(x){return [...(x?.findings||[])].sort((a,b)=>Number(b.level==='CRITICAL')-Number(a.level==='CRITICAL'))[0];}
function formatFinding(f){const ratio=['cpu_busy_ratio','memory_usage_ratio','filesystem_usage_ratio'].includes(f?.key);return {value:f?(ratio?f.observed_value*100:f.observed_value).toFixed(ratio?1:0):'—',threshold:f?(ratio?f.threshold*100:f.threshold).toFixed(ratio?1:0):'—',unit:ratio?'%':f?.key==='waiting'?'请求':f?.key?.startsWith('tpot')?'ms/token':'ms'};}
function incidentTrend(entity,f){const points=replay&&f?SceneReplay.history(entity.id,f.key,48):[];if(!points.some(p=>p.v!==null))return '<div class="trend-unavailable">未接入同口径时间序列</div>';const numbers=points.map(p=>p.v).filter(v=>v!==null),low=Math.min(...numbers,f.threshold)*.9,high=Math.max(...numbers,f.threshold)*1.06,scale=v=>157-(v-low)/(high-low||1)*127;let path='';points.forEach((p,i)=>{if(p.v===null)return;path+=(i&&points[i-1].v!==null?'L':'M')+(20+i/Math.max(1,points.length-1)*580).toFixed(1)+' '+scale(p.v).toFixed(1)+' ';});const threshold=scale(f.threshold);return `<svg class="incident-chart" viewBox="0 0 620 185" role="img" aria-label="当前规则指标时间序列"><path class="chart-grid" d="M20 30H600M20 93H600M20 157H600"/><path class="chart-threshold" d="M20 ${threshold}H600"/><path class="chart-series" d="${path}"/><text x="20" y="181">${e(new Date(points[0].t).toLocaleTimeString('zh-CN',{hour12:false,timeZone:'Asia/Shanghai'}))}</text><text x="520" y="181">${e(new Date(points.at(-1).t).toLocaleTimeString('zh-CN',{hour12:false,timeZone:'Asia/Shanghai'}))}</text></svg>`;}
function faultScreen(kind){const rows=faultEntities(kind),all=kind==='HOST'?(data.hardware||[]):allEndpoints(),unknown=all.filter(x=>epStatus(x)==='UNKNOWN').length,critical=rows.filter(x=>['CRITICAL','FAIL','ERROR'].includes(epStatus(x))).length,sel=rows.find(x=>x.id===selectedFault)||rows.find(x=>x.id===endpointID)||rows[0],f=firstFinding(sel),reading=formatFinding(f),linked=sel?relatedBusinesses(sel):[];
 return `<div class="kpis incident-kpis">${kpi(kind==='HOST'?'异常基础设施对象':'异常推理工作负载',fmt(rows.length),'仅有效窗口内已确认异常','个',rows.length?'warning':'')}${kpi('严重异常',fmt(critical),'CRITICAL / FAIL / ERROR','个',critical?'warning':'')}${kpi('告警对象',fmt(rows.length-critical),'WARNING · 正常对象不进入列表','个')}${kpi('待确认状态',fmt(unknown),'单独计数，不伪装为正常','个')}</div>${!rows.length?`<section class="surface glass incident-empty"><div class="incident-empty-glyph">${icon('shield')}</div><h2>当前窗口无已确认异常</h2><p>本屏只展示异常，正常对象不占用列表。</p><small>${unknown?'仍有 '+unknown+' 个对象状态待确认；无已确认异常不等于全部健康。':'采样窗口 '+e(sourceTime(data.source_window?.end))}</small>${replay?'<button class="quiet-button" id="next-incident">跳至下一异常窗口</button>':''}</section>`:`<div class="incident-layout"><section class="surface incident-list">${titlePanel(kind==='HOST'?'异常节点队列':'异常服务队列','ACTIVE INCIDENTS',badge('仅异常','amber'))}<div class="incident-scroll">${rows.map(x=>{const f=firstFinding(x),n=formatFinding(f);return `<button class="incident-item ${x.id===sel.id?'selected':''}" data-fault="${e(x.id)}" data-status="${e(epStatus(x))}"><div>${badge(statusText(epStatus(x)),statusTone(epStatus(x)))}<span>${e(f?.revalidation_state==='RECOVERING'?'复验中':'待处置')}</span></div><h3>${e(f?.label||'上游异常状态')}</h3><p title="${e(x.name)}">${e(x.node_name||x.workload_ref||x.name)}</p><small>${e(x.namespace||(catalog.clusters||[]).find(c=>c.id===x.cluster_id)?.name||'集群待登记')}</small><strong>${n.value}<em>${e(n.unit)}</em></strong><footer>命中阈值 ≥ ${n.threshold} ${e(n.unit)}<span>查看证据 ↗</span></footer></button>`;}).join('')}</div></section><aside class="surface glass incident-detail">${titlePanel('异常证据与定位','EVIDENCE / CONTEXT',badge('只读'))}<div class="incident-headline">${icon(kind==='HOST'?'host':'nodes')}<div><h2>${e(f?.label||'上游异常')}</h2><p>${e(sel.node_name||sel.workload_ref||sel.name)}</p></div></div><div class="incident-reading"><div><span>当前值</span><strong>${reading.value}<small>${e(reading.unit)}</small></strong></div><div><span>命中阈值</span><b>≥ ${reading.threshold}<small>${e(reading.unit)}</small></b></div><div><span>持续确认</span><b>${f?.matched??'—'}<small>窗口</small></b></div></div>${incidentTrend(sel,f)}<div class="incident-proof"><span>规则 <b>${e(f?.rule_id||'未提供')} / ${e(f?.version||'—')}</b></span><span>首次命中 <b>${e(f?.first_seen?new Date(f.first_seen).toLocaleTimeString('zh-CN',{hour12:false,timeZone:'Asia/Shanghai'}):'—')}</b></span><span>复验条件 <b>${f?'连续 '+f.recover_windows+' 个有效窗口回落':'依上游复验协议'}</b></span></div><div class="incident-dependencies"><h3>配置关联业务 <small>非已证实影响</small></h3><div>${linked.map(b=>`<button data-nav="05" data-id="${e(b.id)}">${e(b.name)} ↗</button>`).join('')||'<span>无明确组级关联</span>'}</div></div><div class="incident-bottom"><span>核对证据 → 人工处置 → 有效窗口复验</span><button class="quiet-button" data-detail="metric" data-entity="${e(sel.id)}" data-key="${e(f?.key||'ttft_p95_ms')}">完整来源 ↗</button></div></aside></div>`}`;
}

function businessSpark(ep){
 const points=replay&&ep?SceneReplay.history(ep.id,'e2e_p99_ms',32):[];
 if(!points.some(p=>p.v!==null))return '<div class="app-spark-empty">焦点 D 历史序列未接入</div>';
 const valid=points.filter(p=>p.v!==null).map(p=>p.v),lo=Math.min(...valid)*.92,hi=Math.max(...valid)*1.08||1;
 let drawing='',pen=false;points.forEach((p,i)=>{if(p.v===null){pen=false;return;}drawing+=(pen?'L':'M')+(i/Math.max(1,points.length-1)*420).toFixed(1)+','+(42-(p.v-lo)/(hi-lo)*34).toFixed(1)+' ';pen=true;});
 return `<svg class="app-spark" viewBox="0 0 420 48" preserveAspectRatio="none" aria-label="焦点 D E2E P99 历史趋势"><path class="app-spark-axis" d="M0 44H420"/><path d="${drawing}"/></svg>`;
}
function recoveryDetail(app){const r=O.escape(app,epStatus),groups=catalog['pd-groups']||[];return `<div class="callout"><strong>${e(r.label)}</strong><br>${e(r.note)}</div><p>用户已确认 fallback 为其他池子的双活逃生通道。这里记录预案；自动切换：关闭。不发送切换请求，不代表授权、容量、网络或恢复时延已经验证。</p><h3>候选承接范围</h3>${r.targets.map(id=>{const g=groups.find(g=>g.id===id);return `<div class="callout"><strong>${e(g?.name||id)}</strong><br>${e((g?.namespaces||[]).join(' / ')||g?.namespace||'范围待确认')}</div>`;}).join('')||'<p>当前业务是承接池使用方，未为它登记自指或外逃路径。</p>'}<h3>执行前的人工核对</h3><p>确定实际承接 namespace、Key/模型授权、服务地址与连通性、剩余有效容量、切换规程及回切复验。候选池没有告警也不能代替这些验证。</p>`;}
function businessCard(b){const info=O.businessMetrics(b,metric),eps=info.endpoints,h=O.rollup(eps,epStatus),c=C.coverage(eps,now(),opts()),recovery=O.escape(b,epStatus),team=(catalog.teams||[]).find(t=>t.id===b.team_id);
 return `<section class="surface app-card engine-app health-${O.tone(h.status)}" data-business="${e(b.id)}"><header class="engine-app-head"><div>${icon('book')}<span><b>${e(b.name)}</b><small>${e(team?.name||b.owner||'责任团队待登记')}</small></span></div>${badge('依赖 '+O.statusLabel(h.status),O.tone(h.status))}</header>
 <div class="app-scope"><span>${(b.pd_group_ids||[]).length} PD组 / ${(b.deployment_scope_ids||[]).length||'—'} 范围 · 覆盖 ${c.fresh}/${c.total}${info.tiles.some(t=>t.m.value!==null&&!t.m.usable)?' · 含历史值':''}</span><span>${h.severe} ERROR / ${h.warn} WARNING</span></div>
 <div class="app-engine-metrics">${info.tiles.map(t=>detailButton(t.entity,t.key,`<span>${e(t.label)}${t.m.value!==null&&!t.m.usable?' · 历史':''}</span><strong>${e(t.m.text)}<small>${e(t.m.unit)}</small></strong>`,'engine-tile'+(t.m.value!==null&&!t.m.usable?' historical':''))).join('')}</div>
 <div class="engine-aux"><button data-detail="metric" data-entity="${e(info.cache.entity?.id||'')}" data-key="kv_cache_hit_ratio">焦点 D · KV 命中 <b>${e(info.cache.m.text)}${e(info.cache.m.unit)}</b></button><button data-detail="metric" data-entity="${e(info.prompt.entity?.id||'')}" data-key="input_tokens_per_second">焦点 P · 输入 <b>${e(info.prompt.m.text)} <small>tok/s</small></b></button></div>
 <div class="app-trend-row"><span>焦点 D<br>E2E P99</span>${businessSpark(info.d)}</div>
 <div class="app-group-chips">${(b.pd_group_ids||[]).map(id=>{const g=(catalog['pd-groups']||[]).find(g=>g.id===id);return `<button data-nav="02" data-id="${e(id)}" title="${e((g?.namespaces||[]).join(' / ')||g?.namespace)} / ${e(g?.name)}">${e(g?.name?.replace('pd-server-dsv4flash-','')||id)} ↗</button>`;}).join('')}<span>点击指标核对原始实例</span></div>
 <button class="escape-strip ${recovery.configured?'protected':'receiver'} ${recovery.configured&&(recovery.health.severe||recovery.health.warn)?'target-alert':''}" data-detail="recovery" data-entity="${e(b.id)}"><span>${icon('shield')}<b>${e(recovery.label)}</b></span><small>${e(recovery.note)}</small><i>↗</i></button>
 <footer>引擎观测 ≠ 业务 SLI · 业务入口状态 <b>UNKNOWN</b></footer></section>`;
}
function businessScreen(){let apps=data.items||[];if(selected){const found=apps.find(x=>x.id===selected);if(found)apps=[found,...apps.filter(x=>x!==found)];}return `<div class="proof-banner surface"><span>${icon('info')}关键应用 × 推理引擎 · 最慢实例定位 · 双活逃生预案</span>${badge('分位数不跨实例合并')}</div><div class="app-grid six-apps engines-grid">${apps.slice(0,6).map(businessCard).join('')||noItems('尚未登记关键应用')}</div>${apps.length>6?'<button class="quiet-button" data-detail="objects">更多关键应用 ↗</button>':''}`;
}
function noItems(title){return `<section class="surface missing-block" style="flex:1">${icon('nodes')}<h3>${e(title)}</h3><p>在 Gateway 中维护目录。未登记和未接入都不代表资源健康。</p><a class="quiet-button" href="/gateway/">打开统一控制台 ↗</a></section>`;}
function noData(){return `<div class="empty-layout"><section class="surface glass"><div class="eyebrow">${loading?'CONNECTING TO DATA SOURCE':'NO VERIFIED SNAPSHOT'}</div><h2>${loading?'正在读取统一数据源':'当前没有可用的观测快照'}</h2><p>${e(transportError||'正在读取同源 API、目录和观测投影。')}</p><p class="tiny-note">不会自动切换到回放数据；不会用零填补缺失值。网络恢复后自动重试。</p><button class="quiet-button" data-retry>重新读取</button> <a class="quiet-button" href="/gateway/">统一控制台 ↗</a></section></div>`;}
function paint(animate=false){
 if(disposed)return;
 const focus=document.activeElement,focusId=focus?.id;
 document.body.dataset.view=screen;
 document.querySelector('#navigation').innerHTML=Object.entries(SCREENS).map(([id,x])=>`<button class="${id===screen?'active':''}" data-nav="${id}" ${id===screen?'aria-current="page"':''}><span class="idx">${id}</span><span class="rail-glyph">${icon(({'01':'grid','02':'nodes','03':'chip','04':'graph','05':'shield'})[id])}</span><span class="rail-label">${e(x[0])}</span></button>`).join('');
 const title=SCREENS[screen];document.title=`${title[1]} · 智算运维`;
 document.querySelector('#heading').innerHTML=`<div><div class="eyebrow">${e(title[2])}</div><h1>${e(title[1])}<span class="${transportError&&data?'transport-inline':''}">${e(transportError&&data?'通信中断 · 最近已知帧，非当前健康结论':title[3])}</span></h1></div><div class="heading-right">${badge(env())}${replay?`<button class="quiet-button" data-detail="timeline">时间轴 / 回放</button>`:badge(transportError?'通信中断':'同源只读 API',transportError?'red':'')}<button class="quiet-button" data-detail="rules">${icon('info')}数据规范</button></div>`;
 const content=document.querySelector('#content');content.classList.toggle('page-enter',animate);
 content.innerHTML=(data?({'01':overview,'02':deploymentScreen,'03':hardwareScreen,'04':diagnostics,'05':businessScreen}[screen])():noData());
 document.querySelector('#footer').innerHTML=`<span class="${replay?'data-ribbon':''}">${replay?`场景回放 · ${e(sourceTime(data?.source_window?.start))} → ${e(sourceTime(data?.source_window?.end))}（UTC+8）`:`${e(origin())} · ${catalogError?'目录读取异常 · ':''}来源窗口 ${e(data?.source_window?.end||'—')}`}</span><span>${replay?`采样 ${SceneReplay.step+1} / 960　·　${SceneReplay.speed}×　·　${SceneReplay.playing?'播放中':'已暂停'}`:'未接入 ≠ 零　·　UNKNOWN ≠ 健康'}</span><span class="source-id">COMPUTE OPS / ${screen}　${replay?'SZG / 8H':'LIVE / CATALOG'}</span>`;
 layoutConnections();
 if(focusId)document.getElementById(focusId)?.focus({preventScroll:true});
 else if(focus?.dataset?.pdGroup)document.querySelectorAll('[data-pd-group]').forEach(el=>{if(el.dataset.pdGroup===focus.dataset.pdGroup)el.focus({preventScroll:true});});
 else if(focus?.dataset?.endpointSelect)document.querySelectorAll('[data-endpoint-select]').forEach(el=>{if(el.dataset.endpointSelect===focus.dataset.endpointSelect)el.focus({preventScroll:true});});
 else if(focus?.dataset?.service)document.querySelectorAll('[data-service]').forEach(el=>{if(el.dataset.service===focus.dataset.service)el.focus({preventScroll:true});});
 updateMotion();updateClock();
}
function showDrawer(title,body){
 drawerTrigger=document.activeElement;activeDialog=title;
 const root=document.getElementById('modal');root.hidden=false;root.innerHTML=`<div class="dialog-backdrop" id="backdrop"><section class="drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title" tabindex="-1"><div class="drawer-head"><h2 id="drawer-title">${e(title)}</h2><button id="close-dialog" aria-label="关闭详情">×</button></div>${body}</section></div>`;
 document.getElementById('app-shell').inert=true;document.getElementById('close-dialog').focus();
}
function closeDrawer(){document.getElementById('modal').hidden=true;document.getElementById('modal').innerHTML='';document.getElementById('app-shell').inert=false;activeDialog=null;activeMetric=null;drawerTrigger?.isConnected&&drawerTrigger.focus();}
function detail(kind,entityID,key){
 if(kind==='recovery'){const app=(data?.items||[]).find(x=>x.id===entityID);if(app)return showDrawer(app.name+' · 双活逃生预案',recoveryDetail(app));return;}
 if(kind==='timeline'){const dataset=SceneReplay.dataset;return showDrawer('八小时场景时间轴',`<p>采样时间与当前系统时间分离。回放不写入生产观测。</p><label class="timeline-control">当前窗口 <input id="scene-position" type="range" min="0" max="959" value="${SceneReplay.step}"><b id="scene-position-label">${new Date(SceneReplay.NOW).toLocaleString('zh-CN',{hour12:false,timeZone:'Asia/Shanghai'})}</b></label><label class="timeline-control">播放速度 <select id="scene-speed">${[1,10,60,120].map(v=>`<option value="${v}" ${v===SceneReplay.speed?'selected':''}>${v}×</option>`).join('')}</select></label><button id="scene-playing" class="quiet-button">${SceneReplay.playing?'暂停回放':'继续回放'}</button><h3>异常窗口定位</h3><div class="timeline-events"><button data-scene-seek="0">08:00 · 正常基线</button>${dataset.episodes.map(ep=>`<button data-scene-seek="${ep.start_minute*2+2}">${String(8+Math.floor(ep.start_minute/60)).padStart(2,'0')}:${String(ep.start_minute%60).padStart(2,'0')} · ${e(ep.name)}</button>`).join('')}<button data-scene-seek="950">15:55 · 恢复后窗口</button></div>`);}
 if(kind==='pod'){const p=(catalog.pods||[]).find(p=>p.id===entityID);return showDrawer('Pod 登记引用',`<h3>${e(p?.pod_name||'未找到')}</h3><dl><dt>Namespace</dt><dd>${e(p?.namespace)}</dd><dt>工作负载</dt><dd>${e(p?.workload_ref)}</dd><dt>节点名称</dt><dd>${e(p?.node_name)}</dd><dt>登记身份</dt><dd>仅名称引用 · 未提供 Pod UID / Node UID / 采样时间</dd></dl><p>来源为用户提供的资源清单；不代表此 Pod 当前在线，也不把阶段工作负载指标分摊给 Pod。</p>`);}

 activeMetric=null;
 if(kind==='objects') {return showDrawer('当前投影中的对象',`<p>仅当前可见投影；点击选择不会写入后端。</p><div class="relation-list">${(screen==='05'?(data?.items||[]):screen==='03'?(data?.hardware||[]):[...allEndpoints(),...(data?.hardware||[])]).map(x=>`<span>${e(x.name)} <button data-select-object="${e(x.id)}">查看 ↗</button></span>`).join('')}</div>`);}
 if(kind==='flow')return showDrawer('分离推理 · 动效与数据边界',`<div class="callout"><strong>这是阶段级原理示意，不是运行时 KV 路由。</strong><br>轨道条数、粒子数量、动画速度与亮度均为固定视觉参数，不表达流量、耗时、负载或健康。</div><h3>01 · Prefill</h3><p>矩阵块并行亮起，表达输入上下文的处理。实例池来自当前服务、当前登记组的 Prefill Endpoint；光块不等于实时请求。</p><h3>02 · KV 交接</h3><p>中间的玻璃缓存层与定向光束表达阶段间上下文交接。当前没有读取传输带宽、延迟或具体路由；不绘制某个 P 实例连接某个 D 实例的虚构链路。</p><h3>03 · Decode</h3><p>顺序亮起的 Token 片段表达逐步生成，和 Prefill 的矩阵动画区分。片段不是模型实际输出，也没有绑定输出吞吐。</p><h3>可验证的部分</h3><p>下方两个池只呈现登记实例，选择后读取该 Endpoint 的原始指标。没有 P 或没有 D 时不启动交接流动；无遥测但目录完整时可继续展示明确标注的原理动画。</p><p>系统减少动态效果和顶部动效按钮同时控制光束、缓存、矩阵与 Token。暂停不停止真实数据的时效检查。</p><div class="drawer-actions"><button class="quiet-button" id="close-dialog-alt">返回工作台</button></div>`);
 if(kind==='rules')return showDrawer('数据与展示规范',`<p>数据先经过来源、范围、窗口与状态校验，再参与可视化；大屏只展示事实，不另建巡检规则引擎。</p><h3>三条数据边界</h3><div class="callout"><strong>Gateway</strong>：业务、模型、服务、集群与 P/D 关系；只能称“已登记”，不能称“健康”。</div><div class="callout"><strong>智能巡检</strong>：单 Endpoint 性能、部分单设备硬件观测。原始状态与原始数值都保留来源。</div><div class="callout"><strong>未完成接入</strong>：业务入口 SLI、KV 传输、阶段请求容量，以及硬件风险证据与复验状态。</div><h3>禁止的计算</h3><p>不相加或平均 P95/P99；不跨 P/D 相加 QPS；不把 TTFT P95 / E2E P99 当作延迟占比；不以单 GPU 代表整个集群；不以缺失值代替零。</p><h3>动效的含义</h3><p>背景光晕和呼吸仅为装饰。目录图不表示实际请求流；P/D 定向动效仅表达阶段原理，不代表实时 KV 路由或流量；回放画面固定显示来源与采样窗口。动效暂停不会停止来源老化。</p><h3>当前运行边界</h3><p>仅调用同源 GET /api/v1/，不修改目录、不改变权限、不执行运维动作。缺失规则不能用 LLM 猜测补齐。</p><div class="drawer-actions"><button class="quiet-button" data-detail="objects">查看当前对象</button><button class="quiet-button" id="close-dialog-alt">关闭</button></div>`);
 const entity=[...allEndpoints(),...(data?.hardware||[])].find(x=>x.id===entityID),m=metric(entity,key),o=entity?.observation||{};
 activeMetric={entityID,key};
 showDrawer('指标来源与口径',`<div id="metric-state-badge">${badge(replay?'场景回放 · 采样窗口':`${m.origin} · ${stateLabel(m.state)}`,replay?'amber':m.usable?'mint':'amber')}</div><h3>${e(m.label)}</h3><div class="source-value">${e(m.text)}<small>${e(m.unit)}</small></div><dl><dt>原始对象</dt><dd>${e(entity?.name||'未选择')}<br><small class="mono">${e(entityID)}</small></dd><dt>指标键 / 原始值</dt><dd class="mono">${e(key)} / ${e(m.value===null?'null':m.value)}</dd><dt>统计范围</dt><dd>${e(entity?.metrics?.[key]?.scope||'未知')} · 不向服务 / 集群层外推</dd><dt>来源身份</dt><dd>${e(replay?'场景回放':(o.origin||'UNKNOWN'))} / ${e(replay?'SCENARIO':(o.source_type||entity?.source_type||'UNKNOWN'))}</dd><dt>原始采样窗口</dt><dd>${e(o.source_window?.start||'—')}<br>${e(o.source_window?.end||'—')}</dd><dt>快照 ID</dt><dd class="mono">${e(o.provider_snapshot_id||'—')}</dd><dt>时效与传输</dt><dd id="metric-state-line">${e(stateLabel(m.state))} · ${e(o.transport_status||'UNKNOWN')} · TTL ${e(o.max_age_seconds||'—')} s</dd><dt>原始上游状态</dt><dd>${e(entity?.status||'UNKNOWN')}（不等于大屏独立判断）</dd></dl><h3>计算与判断限制</h3><p>${key==='ttft_e2e_ratio'?'只读上游 ttft.e2e_ratio；不以不同分位数相除。':key==='memory_usage_ratio'?(replay?'当前为构造的单 HOST 比例读数；未捏造主机物理容量。':'读取后端 DEVICE 范围派生值：GPU used / total；HOST 1 − available / total。配对身份与旧值时间由后端保留。'):key.includes('p95')||key.includes('p99')?'原样展示当前 Endpoint 分位数；不跨实例求和或平均。':'原样展示当前对象的观测值；不推算未知总体。'}</p><p style="margin-top:15px">${replay?'当前证据来自场景规则，不能用于生产健康判定；生产规则仍由巡检平台维护。':'当前投影缺少完整风险协议。此处不新增阈值、不自动宣告风险消除。'}</p><div class="drawer-actions"><button class="quiet-button" id="close-dialog-alt">返回大屏</button></div>`);
}
function fit(){const el=document.getElementById('stage');if(innerWidth>1000){const scale=Math.min(innerWidth/1920,innerHeight/1080);el.style.transform=`scale(${scale})`;el.style.left=`${(innerWidth-1920*scale)/2}px`;el.style.top=`${(innerHeight-1080*scale)/2}px`;}else{el.style.transform='';el.style.left='';el.style.top='';}layoutConnections();}
function layoutConnections(){
 const canvas=document.querySelector('.topology-canvas'),svg=canvas?.querySelector('.graph-svg'),hub=canvas?.querySelector('.topo-hub');
 if(!svg||!hub)return;
 const parent=canvas.getBoundingClientRect(),h=hub.getBoundingClientRect();
 const sx=parent.width/canvas.clientWidth,sy=parent.height/canvas.clientHeight;
 const cx=(h.left+h.width/2-parent.left)/sx,cy=(h.top+h.height/2-parent.top)/sy;
 svg.setAttribute('viewBox',`0 0 ${canvas.clientWidth} ${canvas.clientHeight}`);
 let parts=`<ellipse class="diagram-orbit" cx="${cx}" cy="${cy}" rx="132" ry="132"/><ellipse class="diagram-orbit" cx="${cx}" cy="${cy}" rx="176" ry="176"/>`;
 canvas.querySelectorAll('.topo-node').forEach((node,i)=>{
  const r=node.getBoundingClientRect(),left=node.classList.contains('left');
  const x=(left?r.right-parent.left:r.left-parent.left)/sx,y=(r.top+r.height/2-parent.top)/sy;
  const ex=(left?h.left-parent.left:h.right-parent.left)/sx;
  const bend=(x+ex)/2;
  const d=`M${x} ${y} C${bend} ${y} ${bend} ${cy} ${ex} ${cy}`;
  parts+=`<path class="diagram-line" d="${d}"/><path class="diagram-line highlight ${i%2?'delay':''}" d="${d}"/>`;
 });
 svg.innerHTML=parts;
}
function sourceTime(v){const d=new Date(v);return Number.isFinite(+d)?d.toLocaleString('zh-CN',{hour12:false,timeZone:'Asia/Shanghai'}):'—';}
function offlineLinks(){if(document.body.dataset.offlinePreview==='true')document.querySelectorAll('a[href^="/gateway/"]').forEach(a=>a.setAttribute('href','gateway_preview.html'));}
function updateClock(){const el=document.getElementById('clock');if(el)el.textContent=new Date(now()).toLocaleTimeString('zh-CN',{hour12:false,timeZone:'Asia/Shanghai'});}
function updateMotion(){const enabled=motion&&!preference.matches;document.body.classList.toggle('motion-off',!enabled);const b=document.getElementById('motion');b.setAttribute('aria-pressed',String(enabled));b.title=preference.matches?'系统已启用减少动态效果':enabled?'暂停装饰动效':'开启装饰动效';b.disabled=preference.matches;document.getElementById('autoplay').setAttribute('aria-pressed',String(auto));document.getElementById('autoplay').title=auto?'关闭轮播（数据继续刷新）':'开启 90 秒轮播';}
function navigate(id,obj='',endpoint=''){
 if(!SCREENS[id])return;closeDrawer();screen=id;selected=obj;groupID='';deploymentScopeID='';endpointID=endpoint;workerPageP=workerPageD=0;visibleSeconds=0;
 const url=new URL(location.href);url.searchParams.set('screen',id);obj?url.searchParams.set('id',obj):url.searchParams.delete('id');endpoint?url.searchParams.set('endpoint',endpoint):url.searchParams.delete('endpoint');try{history.pushState({},'',url);}catch{/* Local opaque previews still support in-page navigation. */}
 load(true);
}
async function request(path,signal){
 if(!/^\/api\/v1\/(session$|screens\/(bootstrap|overview|services|critical-apps)$|production-scene\/(catalog|live\/(overview|services|critical-apps))$|catalog\/(clusters|services|businesses|models|pd-groups|endpoints)(\?|$))/.test(path))throw new Error('只允许已登记的同源只读接口');
 const response=await fetch(path,{method:'GET',credentials:'same-origin',cache:'no-store',headers:{Accept:'application/json'},signal});
 if(!response.ok){const error=new Error(`HTTP ${response.status}`);error.status=response.status;throw error;}
 const payload=await response.json();if(![1,'1','1.0'].includes(payload?.schema_version))throw new Error('不兼容的 API schema');return payload;
}
async function getCatalog(signal){const v=await request('/api/v1/production-scene/catalog',signal);if(!v.data?.catalog)throw Error('生产目录扩展返回不完整');return v.data.catalog;}
async function liveLoad(animate){
 if(document.hidden||disposed)return;clearTimeout(pollTimer);currentController?.abort();const gen=++generation;const controller=new AbortController();currentController=controller;pollBusy=true;
 const timer=setTimeout(()=>controller.abort(),15000);const path=PATHS[screen];
 try{
  await request('/api/v1/session',controller.signal);
  const boot=await request('/api/v1/screens/bootstrap',controller.signal);if(boot.data?.data_mode!=='live')throw new Error('只接受 live 投影');
  refreshSeconds=Math.max(5,Math.min(60,Number(boot.data.refresh_seconds)||15));
  const v=await request('/api/v1/production-scene/live/'+path,controller.signal);C.validateEnvelope(v,path);
  if(gen!==generation||disposed)return;
  const previous=cache.get(path),rev=C.revision(v.view_revision);
  if(previous&&rev<C.revision(previous.view_revision))throw new Error('投影 revision 回退，保留旧帧');
  if(!previous||rev>C.revision(previous.view_revision)){cache.set(path,v);data=v.data;}
  else data=previous.data;
  transportError='';loading=false;paint(animate);
  try{const freshCatalog=await getCatalog(controller.signal);if(gen===generation){catalog=freshCatalog;catalogError='';paint(false);}}catch(err){if([401,403].includes(err.status))throw err;if(gen===generation){catalogError='目录刷新失败，保留上次目录';paint(false);}}
 }catch(err){if(gen!==generation||disposed)return;if([401,403].includes(err.status)){cache.clear();catalog={};data=null;catalogError='访问权限已变化';}transportError=err.name==='AbortError'?'读取超时':err.message;loading=false;paint(false);}
 finally{clearTimeout(timer);if(gen===generation){pollBusy=false;if(!document.hidden&&!disposed)pollTimer=setTimeout(()=>liveLoad(false),refreshSeconds*1000);}}
}
async function ensureReplay(){await SceneReplay.init();}
async function load(animate=false){
 clearTimeout(pollTimer);currentController?.abort();generation++;
 if(replay){try{await ensureReplay();catalog=SceneReplay.catalog;data=SceneReplay.projection(screen).data;transportError='';loading=false;paint(animate);}catch(err){transportError=err.message;loading=false;paint();}return;}
 data=cache.get(PATHS[screen])?.data||null;loading=!data;paint(animate);liveLoad(animate);
}
function setup(){
 document.getElementById('stage').innerHTML=`<div class="ambient" aria-hidden="true">${Array.from({length:14},(_,i)=>`<i style="left:${7+i*6.3}%;top:${17+(i*17)%73}%"></i>`).join('')}</div><div id="app-shell" style="display:contents"><header class="topbar"><a class="brand" href="#" id="brand-home"><span class="brand-mark">${icon('cube')}</span><span><strong>智算运维 · 可观测中心</strong><small>INTELLIGENT COMPUTE OPERATIONS</small></span></a><div class="tools"><span class="clock" id="clock"></span><button class="icon-button" id="autoplay" aria-label="切换自动轮播" aria-pressed="false">${icon('play')}</button><button class="icon-button" id="motion" aria-label="切换装饰动效" aria-pressed="true">${icon('motion')}</button><button class="icon-button" id="fullscreen" aria-label="进入全屏">${icon('full')}</button></div></header><nav class="nav" id="navigation" aria-label="大屏导航"></nav><section class="heading" id="heading"></section><main id="content"></main><footer class="bottomline" id="footer"></footer></div><div id="modal" hidden></div>`;
 document.addEventListener('click',ev=>{
  const target=ev.target.closest('button,a');if(ev.target.id==='backdrop'){closeDrawer();return;}if(!target)return;
  if(target.dataset.deploymentScope){deploymentScopeID=target.dataset.deploymentScope;endpointID='';workerPageP=workerPageD=0;paint(false);return;}
  if(target.dataset.fault){selectedFault=target.dataset.fault;paint(false);return;}
  if(target.id==='next-incident'){const ep=SceneReplay.dataset.episodes.find(ep=>ep.start_minute*2>SceneReplay.step)||SceneReplay.dataset.episodes[0];SceneReplay.seek(ep.start_minute*2+2);return;}
  if(target.hasAttribute('data-scene-seek')){SceneReplay.seek(Number(target.dataset.sceneSeek));closeDrawer();return;}
  if(target.id==='scene-playing'){SceneReplay.playing=!SceneReplay.playing;target.textContent=SceneReplay.playing?'暂停回放':'继续回放';paint(false);return;}
  if(target.dataset.nav){ev.preventDefault();navigate(target.dataset.nav,target.dataset.id||'',target.dataset.endpoint||'');return;}
  if(target.id==='brand-home'){ev.preventDefault();navigate('01');return;}
  if(target.dataset.detail){detail(target.dataset.detail,target.dataset.entity,target.dataset.key);return;}
  if(target.id==='close-dialog'||target.id==='close-dialog-alt'){closeDrawer();return;}
  if(target.id==='motion'){motion=!motion;try{localStorage.setItem('ico-motion',motion?'on':'off');}catch{}updateMotion();return;}
  if(target.id==='autoplay'){auto=!auto;visibleSeconds=0;updateMotion();return;}
  if(target.id==='fullscreen'){if(document.fullscreenElement)document.exitFullscreen?.();else document.documentElement.requestFullscreen?.().catch(()=>{});return;}
  if(target.id==='replay-empty'){emptyReplay=!emptyReplay;load(true);return;}
  if(target.hasAttribute('data-retry')){load(false);return;}
  if(target.dataset.pdGroup){groupID=target.dataset.pdGroup;deploymentScopeID='';endpointID='';workerPageP=workerPageD=0;paint(false);return;}
  if(target.dataset.service){selected=target.dataset.service;endpointID='';groupID='';workerPageP=workerPageD=0;paint(false);return;}
  if(target.dataset.endpointSelect){endpointID=target.dataset.endpointSelect;paint(false);return;}
  if(target.dataset.bank){if(target.dataset.bank==='P')workerPageP=Math.max(0,workerPageP+Number(target.dataset.delta));else workerPageD=Math.max(0,workerPageD+Number(target.dataset.delta));paint(false);return;}
  if(target.dataset.selectObject){const id=target.dataset.selectObject;closeDrawer();if(screen==='05'){selected=id;paint(true);}else{const entity=[...allEndpoints(),...(data?.hardware||[])].find(x=>x.id===id);detail('metric',id,entity?.resource_type==='HOST'?'cpu_busy_ratio':entity?.resource_type==='GPU_POOL'?'utilization_ratio':'ttft_p95_ms');}}
 });
 document.addEventListener('change',ev=>{if(ev.target.id==='scene-speed'){SceneReplay.speed=ev.target.value;paint(false);return;}if(ev.target.id==='scene-position'){SceneReplay.seek(Number(ev.target.value));const label=document.getElementById('scene-position-label');if(label)label.textContent=new Date(SceneReplay.NOW).toLocaleString('zh-CN',{hour12:false,timeZone:'Asia/Shanghai'});return;}if(ev.target.id==='pd-group'){groupID=ev.target.value;deploymentScopeID='';endpointID='';workerPageP=workerPageD=0;paint(false);return;}if(ev.target.id==='diagnostic-service'){selected=ev.target.value;paint(false);}});
 document.addEventListener('keydown',ev=>{
  if(activeDialog){if(ev.key==='Escape'){closeDrawer();ev.preventDefault();}if(ev.key==='Tab'){const nodes=[...document.querySelectorAll('.drawer button,.drawer a,.drawer select,.drawer input,.drawer textarea')].filter(x=>!x.disabled),first=nodes[0],last=nodes.at(-1);if(ev.shiftKey&&document.activeElement===first){last?.focus();ev.preventDefault();}else if(!ev.shiftKey&&document.activeElement===last){first?.focus();ev.preventDefault();}}return;}
  if(ev.target.matches('input,select,textarea'))return;
  if(['ArrowRight','ArrowLeft'].includes(ev.key)){const ids=Object.keys(SCREENS),next=(ids.indexOf(screen)+(ev.key==='ArrowRight'?1:4))%5;navigate(ids[next]);ev.preventDefault();}
 });
 preference.addEventListener('change',updateMotion);addEventListener('resize',fit);
 addEventListener('popstate',()=>{const params=new URLSearchParams(location.search);screen=SCREENS[params.get('screen')]?params.get('screen'):'01';selected=params.get('id')||'';endpointID=params.get('endpoint')||'';load(true);});
 document.addEventListener('visibilitychange',()=>{document.body.classList.toggle('page-hidden',document.hidden);if(document.hidden){clearTimeout(pollTimer);currentController?.abort();generation++;}else{paint(false);if(!replay)liveLoad(false);}});
 addEventListener('scene-step',()=>{if(replay&&SceneReplay.initialized){data=SceneReplay.projection(screen).data;paint(false);}});
 const tick=setInterval(()=>{if(disposed)return;if(replay&&SceneReplay.tick(performance.now(),document.hidden,!!activeDialog)){data=SceneReplay.projection(screen).data;paint(false);}if(document.hidden)return;updateClock();if(auto&&!activeDialog&&++visibleSeconds>=90){const ids=Object.keys(SCREENS);navigate(ids[(ids.indexOf(screen)+1)%5]);}if(!replay&&data){const signature=JSON.stringify([...allEndpoints(),...(data.hardware||[])].map(x=>[C.quality(x,now(),opts()),...Object.keys(x.metrics||{}).map(k=>C.DEFINITIONS[k]?metric(x,k).state:null)]));if(signature!==window.__qualitySignature){window.__qualitySignature=signature;paint(false);if(activeMetric){const entity=[...allEndpoints(),...(data?.hardware||[])].find(x=>x.id===activeMetric.entityID),m=metric(entity,activeMetric.key);document.getElementById('metric-state-badge').innerHTML=badge(`${m.origin} · ${stateLabel(m.state)}`,m.usable?'mint':'amber');document.getElementById('metric-state-line').textContent=`${stateLabel(m.state)} · ${entity?.observation?.transport_status||'UNKNOWN'} · TTL ${entity?.observation?.max_age_seconds||'—'} s`;}}}},1000);
 addEventListener('pagehide',()=>{disposed=true;clearTimeout(pollTimer);clearInterval(tick);currentController?.abort();});
 fit();updateMotion();load(true);
 if(document.body.dataset.offlinePreview==='true')new MutationObserver(offlineLinks).observe(document.getElementById('stage'),{childList:true,subtree:true});
 window.RefineApp={get screen(){return screen;},get data(){return data;},get catalog(){return catalog;},navigate,get isReplay(){return replay;},get now(){return now();},get transportError(){return transportError;}};
}
setup();
})();
