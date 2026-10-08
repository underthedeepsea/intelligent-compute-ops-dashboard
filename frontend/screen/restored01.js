(()=>{
function hardware(root,c){
 const devices=c.data.hardware||[],index=Math.floor((c.state.hardwareElapsed||0)/12);
 const pick=type=>{const list=devices.filter(x=>x.resource_type===type);return list[index%Math.max(1,list.length)];};
 const gpu=pick('GPU_POOL'),host=pick('HOST');
 for(const [id,label,device,key] of [['c-compute-cpu','CPU 利用率',host,'cpu_busy_ratio'],['c-compute-mem','内存利用率',host,'memory_usage_ratio'],['c-gpu-1','GPU 利用率',gpu,'utilization_ratio'],['c-gpu-2','显存使用率',gpu,'memory_usage_ratio'],['c-gpu-3','GPU 温度',gpu,'temperature_celsius']]){
  const el=root.querySelector('#'+id);if(!el||!device)continue;
  const p=device.metrics?.[key],age=c.ageState(device,c.now),collected=Date.parse(p?.collected_at);
  const csv=device.observation?.source_type==='CSV'&&device.observation?.data_state==='CSV_SNAPSHOT'&&age==='CSV_SNAPSHOT';
  const freshPoint=Number.isFinite(collected)&&(csv||c.now-collected<=300000)&&collected-c.now<=30000;
  const usable=p?.state==='AVAILABLE'&&p.quality==='VALID'&&typeof p.value==='number'&&Number.isFinite(p.value)&&freshPoint&&['FRESH','UNVERIFIED','CSV_SNAPSHOT'].includes(age);
  const value=usable?`${c.m(p.value*(p.unit==='ratio'?100:1),1)}${p.unit==='ratio'?'%':c.e(p.unit)}`:'—';
  const origin=csv?'CSV 快照':device.observation?.demo?'DEMO / UNVERIFIED':'UNVERIFIED';
  const status=csv?'CSV 快照 '+new Date(device.observation.sampled_at||p?.collected_at).toLocaleString('zh-CN',{year:'2-digit',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}):age==='STALE'||(!freshPoint&&p?.state==='AVAILABLE')?'STALE':age==='SOURCE_ERROR'?'来源异常':usable?(device.observation?.demo?'演示 · 未验证':'未验证'):(p?.state||'未接入');
  el.innerHTML=`<div class="overview-empty" title="${c.e(device.name+' · '+device.host_id+' · '+(device.gpu_uuid||'HOST')+' · '+(p?.collected_at||'无采样时间')+' · '+origin)}"><span>${c.e(label)}</span><b>${value}</b><small class="${status==='STALE'||age==='SOURCE_ERROR'?'overview-attention':''}">${c.e(status)}</small></div>`;

 }
}
function directory(c){
 const rows=key=>(c.catalog[key]||[]).filter(x=>x.enabled!==false);
 const clusters=rows('clusters'),services=rows('services'),endpoints=(c.catalog.endpoints||c.data.items||[]).filter(x=>x.enabled!==false);
 const clusterMap=new Map(clusters.map(x=>[x.id,x])),serviceMap=new Map(services.map(x=>[x.id,x]));
 const unresolved=endpoints.filter(x=>!clusterMap.has(x.cluster_id)||!serviceMap.has(x.service_id));
 const valid=endpoints.filter(x=>clusterMap.has(x.cluster_id)&&serviceMap.has(x.service_id));
 const choices=clusters.map(cluster=>({id:cluster.id,name:cluster.name,cluster,endpoints:valid.filter(x=>x.cluster_id===cluster.id)}));
 if(unresolved.length)choices.push({id:'__unresolved__',name:'关联待确认',cluster:null,endpoints:unresolved});
 const chosen=choices.find(x=>x.id===c.state.overviewCluster)||choices[0];
 c.state.overviewCluster=chosen?.id||'';
 const groups=chosen?.cluster?services.map(service=>({id:service.id,service,endpoints:chosen.endpoints.filter(x=>x.service_id===service.id)})).filter(x=>x.endpoints.length):chosen?[{id:'__unresolved__',service:null,endpoints:chosen.endpoints}]:[];
 const pages=Math.max(1,Math.ceil(groups.length/2));
 c.state.overviewPage=Math.max(0,Math.min(c.state.overviewPage||0,pages-1));
 c.state.overviewBatches??={};
 const visible=groups.slice(c.state.overviewPage*2,c.state.overviewPage*2+2).map(group=>{
  const key=(chosen?.id||'')+'|'+group.id,total=Math.max(1,Math.ceil(group.endpoints.length/4));
  const page=Math.max(0,Math.min(c.state.overviewBatches[key]||0,total-1));c.state.overviewBatches[key]=page;
  return {...group,key,page,total,visible:group.endpoints.slice(page*4,page*4+4)};
 });
 const identities=[...clusters,...services,...endpoints,...(c.data.hardware||[])];
 if(!identities.some(x=>x.id===c.state.overviewInspect))c.state.overviewInspect='';
 return {clusters,services,endpoints,choices,chosen,groups,pages,visible,identity:identities.find(x=>x.id===c.state.overviewInspect)};
}
const endpointLink=ep=>'04.html?id='+encodeURIComponent(ep.service_id)+'&endpoint='+encodeURIComponent(ep.id);
function topology(c){
 const {e}=c,v=directory(c),chosen=v.chosen;
 const controls=(attr,page,total)=>`<div class="overview-pager"><button ${attr}="-1" ${page===0?'disabled':''} aria-label="上一页">←</button><span>${page+1} / ${total}</span><button ${attr}="1" ${page===total-1?'disabled':''} aria-label="下一页">→</button></div>`;
 const groupHTML=v.visible.map(g=>`<div class="overview-branch"><div class="overview-service"><span>${g.service?'登记服务':'缺失关联'}</span><button data-overview-inspect="${e(g.service?.id||'')}">${e(g.service?.name||'关联待确认')}</button>${g.service?`<small>${e((c.catalog.models||[]).find(x=>x.id===g.service.model_id)?.name||'模型未登记')}</small><a href="04.html?id=${encodeURIComponent(g.service.id)}">服务观测 ↗</a>`:'<small>缺少可验证的集群或服务，未建立部署边</small>'}<div class="overview-group-count">${g.page*4+1}–${Math.min((g.page+1)*4,g.endpoints.length)} / ${g.endpoints.length} 个${g.service?'本集群':''}实例</div>${controls('data-overview-batch="'+e(g.key)+'" data-overview-step',g.page,g.total)}</div><div class="overview-endpoints">${g.visible.map(ep=>`<div class="overview-endpoint"><button data-overview-inspect="${e(ep.id)}">${e(ep.name)}</button><div><span>${e(ep.role||'角色未登记')}</span>${g.service?`<a href="${endpointLink(ep)}" aria-label="查看 ${e(ep.name)} 原始观测">观测 ↗</a>`:'<span>关联待确认</span>'}</div>${g.service?'':`<small>集群 ${e(ep.cluster_id||'未登记')} · 服务 ${e(ep.service_id||'未登记')}</small>`}</div>`).join('')}</div></div>`).join('');
 const displayed=v.visible.reduce((n,g)=>n+g.visible.length,0);
 return `<div class="overview-topology-head"><div><h2>登记部署拓扑</h2><p>集群 → 服务 → Endpoint 实例</p></div><div><strong>本帧 ${displayed} / ${chosen?.endpoints.length||0}</strong><span>所选集群登记实例</span></div></div><div class="overview-topology-tools"><label>集群 <select id="overview-cluster">${v.choices.map(x=>`<option value="${e(x.id)}" ${x.id===chosen?.id?'selected':''}>${e(x.name)} · ${x.endpoints.length} 实例</option>`).join('')||'<option>尚未登记集群</option>'}</select></label><span>全部 ${v.endpoints.length} 实例 · ${e(c.catalogOrigin())}</span></div><div class="overview-tree ${chosen?.cluster?'':'overview-unresolved'}">${chosen?.cluster?`<div class="overview-cluster-node"><span>登记集群</span><button data-overview-inspect="${e(chosen.id)}">${e(chosen.name)}</button><small>${e(chosen.cluster.environment_code||'环境未登记')} · ${e(chosen.cluster.region||'地域未登记')}</small><b>${chosen.endpoints.length}</b><span>登记实例</span></div>`:''}<div class="overview-branches">${groupHTML||`<div class="overview-empty"><b>${chosen?'尚未登记部署实例':'等待目录数据'}</b><span>完整登记关系可用后在此展示</span></div>`}</div></div><div class="overview-topology-foot"><span>服务分组 ${v.groups.length} 项</span>${controls('data-overview-page',c.state.overviewPage,v.pages)}<span>登记关系不代表实时流量或运行健康</span></div><div class="overview-name-detail" aria-live="polite">${v.identity?`<strong>完整名称</strong><span>${e(v.identity.name)}</span><small>ID ${e(v.identity.id)}</small>`:'点击节点名称查看完整名称与 ID'}</div>`;
}
const labels={'c-host':'主机健康 / 地域','c-compute-cpu':'CPU 利用率','c-compute-mem':'内存利用率','c-gpu-1':'GPU 利用率','c-gpu-2':'显存使用率','c-gpu-3':'GPU 温度','c-gpu-4':'GPU 功率','c-gpu-5':'显存温度','c-gpu-6':'GPU 时钟','c-hetero-1':'异构算力吞吐','c-hetero-2':'异构算力延迟','c-net-1':'RoCE 流量','c-net-2':'网络丢包','c-model-1':'全局 TTFT','c-model-2':'全局 TPOT','c-model-3':'全局吞吐','c-token-1':'输入 Token/s','c-token-2':'输出 Token/s','c-pd-1':'Prefill 阶段','c-pd-2':'Decode 阶段','c-queue':'全局队列','c-risk':'模型风险'};
function devices(root,c){
 const index=Math.floor((c.state.hardwareElapsed||0)/12);
 for(const [id,type] of [['overview-host-device','HOST'],['overview-gpu-device','GPU_POOL']]){
  const list=(c.data.hardware||[]).filter(x=>x.resource_type===type),device=list[index%Math.max(1,list.length)],el=root.querySelector('#'+id);
  if(el)el.innerHTML=device?`<button data-overview-inspect="${c.e(device.id)}">${c.e(device.name)}</button><small>${c.e(device.host_id||'')} · ${c.e(device.gpu_uuid||'HOST')} · ${c.e(c.stateLabel(c.ageState(device,c.now)))}</small>`:type+' 尚未绑定';
 }
}
window.OverviewTopology={directory,endpointLink,topology};
window.ScreenRenderers=window.ScreenRenderers||{};
window.ScreenRenderers['01']={
 render(){return window.OverviewDOM;},
 bind(root,c){
  for(const [id,label] of Object.entries(labels)){const el=root.querySelector('#'+id);if(el)el.innerHTML=`<div class="overview-empty"><span>${c.e(label)}</span><b>—</b><small>未接入</small></div>`;}
  root.querySelector('#overview-counts').innerHTML=[['集群','clusters'],['服务','services'],['Endpoint','endpoints']].map(([label,key])=>`<div><strong class="mono">${c.m(c.data.summary[key])}</strong><span>已登记${label}</span></div>`).join('')+'<small>登记数量不代表健康</small>';
  root.querySelector('#c-map').innerHTML=topology(c);hardware(root,c);devices(root,c);
  root.onclick=ev=>{const b=ev.target.closest('button');if(!b)return;const s=c.state;if(b.dataset.overviewInspect!==undefined)s.overviewInspect=b.dataset.overviewInspect;if(b.dataset.overviewPage)s.overviewPage+=Number(b.dataset.overviewPage);if(b.dataset.overviewBatch)s.overviewBatches[b.dataset.overviewBatch]+=Number(b.dataset.overviewStep);c.refresh();};
  root.onchange=ev=>{if(ev.target.id!=='overview-cluster')return;c.state.overviewCluster=ev.target.value;c.state.overviewPage=0;c.state.overviewInspect='';c.refresh();};
 },
 tick(c){if(!c.state.paused)c.state.hardwareElapsed=(c.state.hardwareElapsed||0)+1;const root=document.querySelector('#app');if(root){hardware(root,c);devices(root,c);}}
};})();
