/* Evidence-only diagnostics. Uses seven EXISTING rule metrics; adds no topology,
   telemetry capability, health rule, threshold or inference about root cause. */
(function(root){'use strict';
const C=typeof module!=='undefined'?require('./masked-core.js'):root.MaskedCore;
const CODES=Object.freeze({h:Object.freeze(['CPU','MEM','FS']),e:Object.freeze(['TTFT','TPOT','E2E','QUEUE'])});
const SHORT=Object.freeze({CPU:'处理器负载',MEM:'内存压力',FS:'文件系统压力',TTFT:'首 Token 延迟',TPOT:'逐 Token 延迟',E2E:'端到端尾延迟',QUEUE:'排队压力'});
const ROLE=Object.freeze({h:{P:'P 侧主机域',D:'D 侧主机域','P/D':'P/D 共享主机域',OTHER:'角色待确认'},e:{P:'P 推理阶段',D:'D 推理阶段',C:'合并推理阶段',ROUTER:'路由实例 · 仅定位'}});
function plan(model,kind,step,active='',code='',offline=false){
 if(!CODES[kind])throw new Error('Unsupported diagnostics domain');
 const codes=CODES[kind],col=kind==='h'?'hosts':'endpoints';
 const ids=offline?[]:model.incidentIDs(kind,step).filter(id=>codes.some(k=>C.anomaly(model.d.tracks[id]?.metrics[k]?.state[step])));
 const unknown=offline||model.cat[col].some(x=>model.state(x.id,step)==='U'||(C.anomaly(model.state(x.id,step))&&!ids.includes(x.id)));
 const displayIDs=kind==='h'?model.cat.hosts.map(x=>x.id):ids;
 const id=displayIDs.includes(active)?active:ids[0]||displayIDs[0]||'';
 const row=model.map[col].get(id)||null;
 const metrics=row?codes.map(k=>({code:k,state:offline?'U':model.d.tracks[id]?.metrics[k]?.state[step]||'U'})):[];
 const hit=metrics.filter(x=>C.anomaly(x.state)).sort((a,b)=>C.SEVERITY[b.state]-C.SEVERITY[a.state]||codes.indexOf(a.code)-codes.indexOf(b.code))[0];
 const selected=metrics.find(x=>x.code===code)||hit||metrics[0]||null;
 return {kind,ids,displayIDs,offline,id,row,codes,metrics,code:selected?.code||'',state:selected?.state||'U',
  overall:offline?'U':ids.some(x=>model.state(x,step)==='R')?'R':ids.length?'W':unknown?'U':'G',unknown,
  role:row?ROLE[kind][row.role]||'角色待确认':'',groups:row?model.groupIDsFor(id):[],businesses:row?model.businessesFor(id):[]};
}
function bridge(p,mode){
 const e=C.esc;
 if(mode==='outbound')return `<div class="diag-bridge outbound ${C.TONE[p.state]}" aria-hidden="true"><svg viewBox="0 0 60 300" preserveAspectRatio="none"><path class="trace-base" d="M0 150H60"/><path class="trace-flow" pathLength="100" d="M0 150H60"/></svg></div>`;
 return `<div class="diag-bridge inbound" aria-hidden="true"><svg viewBox="0 0 60 300" preserveAspectRatio="none">${p.metrics.map((m,i)=>{const y=(i+.5)*300/p.metrics.length,d=`M0 ${y}C32 ${y} 25 150 60 150`;return `<g class="${C.TONE[m.state]}" data-evidence-state="${m.state}" data-evidence-code="${m.code}"><path class="trace-base" d="${d}"/>${m.code===p.code?`<path class="trace-flow" pathLength="100" d="${d}"/>`:''}</g>`;}).join('')}</svg></div>`;
}
function solid(code,state,mini=false){
 const tone=C.TONE[state];return `<div class="solid-object ${tone} ${mini?'mini-solid':''}" aria-hidden="true"><div class="solid-shadow"></div><div class="solid-perspective"><div class="solid-assembly"><div class="solid-layer foundation"></div><div class="solid-layer layer-middle"></div><div class="solid-layer layer-top"><div class="solid-grid">${Array.from({length:25},(_,i)=>`<i style="--cell:${i}"></i>`).join('')}</div><span class="solid-label">${C.esc(code)}</span><i class="solid-scan"></i></div><div class="solid-glass"></div></div></div><div class="solid-base-light"></div></div>`;
}
// Fixed illustrative geometry. No dimension/count/speed reads telemetry or hardware inventory.
function volume(kind,state,label=''){
 const e=C.esc,tone=C.TONE[state]||'muted',id=`h3dv2-${kind}-${state}`;
 const origin=kind==='RESULT'?[168,82]:kind==='HOST'?[156,114]:kind==='MEM'?[158,74]:[158,49];
 const pt=(x,y,z)=>[origin[0]+(x-y)*.88,origin[1]+(x+y)*.33-z];
 const points=xs=>xs.map(x=>x.map(v=>Math.round(v*10)/10).join(',')).join(' ');
 const face=(xs,cls)=>`<polygon class="${cls}" points="${points(xs)}"/>`;
 function box(x,y,z,w,d,h,style='metal'){
  const a=pt(x,y,z+h),b=pt(x+w,y,z+h),c=pt(x+w,y+d,z+h),q=pt(x,y+d,z+h),bb=pt(x+w,y,z),cc=pt(x+w,y+d,z),dd=pt(x,y+d,z);
  return `<g class="h3d-box ${style}">${face([b,c,cc,bb],'h3d-side')}${face([q,c,cc,dd],'h3d-front')}${face([a,b,c,q],'h3d-top')}</g>`;
 }
 const line=(a,b,cls)=>`<path class="${cls}" d="M${pt(...a).join(' ')}L${pt(...b).join(' ')}"/>`;
 const base=(w=140,d=92)=>box(-9,-7,-17,w+18,d+14,9)+box(-3,-3,-7,w+6,d+6,7)+box(0,0,0,w,d,7)+line([0,d,7],[w,d,7],'h3d-base-rim');
 let body='',pins='';
 if(kind==='CPU'){
  body=base(140,92);
  for(let y=0;y<3;y++)for(let x=0;x<3;x++){
   body+=`<g class="h3d-core-cube" style="--piece:${y*3+x}">${box(17+x*37,13+y*24,8,27,19,24,'core')}${line([18+x*37,13+y*24,32],[43+x*37,13+y*24,32],'h3d-core-highlight')}</g>`;
  }
  for(let i=0;i<14;i++)pins+=line([7+i*9,92,3],[7+i*9,92,-3],'h3d-contact-pin');
 }else if(kind==='MEM'){
  body=base(142,87);
  for(let y=0;y<4;y++){
   const yy=8+y*19;body+=`<g class="h3d-memory-board" style="--piece:${y}">${box(14,yy,7,114,5,48,'glass')}${line([18,yy+5,13],[124,yy+5,13],'h3d-memory-light')}${line([14,yy,55],[128,yy,55],'h3d-glass-edge')}</g>`;
   for(let i=0;i<9;i++)pins+=line([23+i*11,yy+5,8],[23+i*11,yy+5,3],'h3d-contact-pin');
  }
 }else if(kind==='FS'){
  body=base(142,88);
  for(let i=0;i<3;i++){
   const yy=14+i*27;body+=`<g class="h3d-io-channel" style="--piece:${i}">${box(7,yy-7,7,16,17,19)}${box(121,yy-7,7,16,17,19)}${line([23,yy+1,17],[121,yy+1,17],'h3d-rail-shell')}${line([23,yy+1,17],[121,yy+1,17],'h3d-rail-light')}${line([26,yy+1,18],[117,yy+1,18],'h3d-rail-glint')}</g>`;
  }
 }else if(kind==='RESULT'){
  body=base(144,104)+box(9,8,8,126,88,12)+box(22,18,24,100,68,10,'result-chip')+box(4,3,47,136,98,2,'glass result-lid');
  body+=`<text class="h3d-result-label" x="177" y="104" text-anchor="middle">${e(label)}</text>`;
 }else if(kind==='HOST'){
  body=base(136,100);
  for(let i=0;i<4;i++){
   const zz=9+i*20;body+=box(17,14,zz,102,75,16,'host-slab');body+=line([18,89,zz+12],[117,89,zz+12],'h3d-host-slot');
   for(let j=0;j<3;j++){const xy=pt(103+j*4,89,zz+7);body+=`<circle class="h3d-host-indicator" cx="${xy[0]}" cy="${xy[1]}" r="1.4"/>`;}
  }
  body+=box(26,23,89,84,57,5)+`<text class="h3d-host-label" x="132" y="117" text-anchor="middle" transform="rotate(20 132 117)">${e(label)}</text>`;
 }
 const vb=kind==='RESULT'?'0 0 340 236':kind==='HOST'?'0 0 320 228':'0 0 320 180';
 return `<span class="h3d-object h3d-${kind.toLowerCase()} ${tone}" data-volume-kind="${kind}" data-volume-state="${e(state)}" aria-hidden="true"><svg class="h3d-svg" viewBox="${vb}" fill="none"><defs><linearGradient id="${id}-metal" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#3d5e76"/><stop offset=".45" stop-color="#1a354b"/><stop offset="1" stop-color="#081725"/></linearGradient><linearGradient id="${id}-glass" x1="0" y1="0" x2="1" y2="1"><stop class="h3d-glass-stop" stop-opacity=".14"/><stop offset=".7" stop-color="#092735" stop-opacity=".55"/><stop offset="1" class="h3d-glass-stop" stop-opacity=".4"/></linearGradient><radialGradient id="${id}-light"><stop class="h3d-glass-stop" stop-opacity=".28"/><stop offset="1" stop-color="#03111b" stop-opacity="0"/></radialGradient></defs><ellipse class="h3d-soft-light" cx="170" cy="86" rx="138" ry="80" fill="url(#${id}-light)"/><ellipse class="h3d-contact-shadow" cx="171" cy="${kind==='HOST'?198:kind==='RESULT'?177:145}" rx="116" ry="${kind==='RESULT'||kind==='HOST'?16:10}"/><g class="h3d-volume" style="--metal:url(#${id}-metal);--glass:url(#${id}-glass)">${body}${pins}</g></svg></span>`;
}
function hostSignals(p,color){
 return `<div class="diag-signals h3d-signals" data-count="3">${p.metrics.map((m,i)=>`<button class="diag-signal h3d-signal ${color(m.state)} ${m.code===p.code?'chosen':''}" data-diag-code="${m.code}" data-metric-state="${m.state}" aria-pressed="${m.code===p.code}" style="--signal-order:${i}"><span class="h3d-signal-copy"><strong>${m.code==='FS'?'文件系统 I/O 压力':C.esc(SHORT[m.code])}</strong><small>${m.code==='FS'?'FS · I/O':m.code}</small><span class="signal-state"><i></i>${C.esc(C.LABEL[m.state])}</span></span>${volume(m.code,m.state)}</button>`).join('')}<span class="h3d-geometry-note">固定几何示意 · 非硬件数量</span></div>`;
}
function renderLegacy(p,{model,step,chart,badge,stateBadge,color,name,cycling,icon}){
 const e=C.esc,st=p.state,tone=color(st),domain=p.kind==='h'?'主机指标':'推理指标';
 const byid=id=>model.map[p.kind==='h'?'hosts':'endpoints'].get(id);
 const metricFor=id=>p.codes.filter(k=>C.anomaly(model.d.tracks[id]?.metrics[k]?.state[step])).sort((a,b)=>C.SEVERITY[model.d.tracks[id].metrics[b].state[step]]-C.SEVERITY[model.d.tracks[id].metrics[a].state[step]])[0]||p.codes[0];
 const top=`<div class="incident-hud diag-hud">${stateBadge(p.overall)}<span>资源监控</span><span class="spacer"></span><span>${cycling?'异常项每 30 秒轮巡':'当前停留'}</span></div>`;
 if(!p.row)return `<section class="diagnostic-screen" data-domain="${p.kind}">${top}<div class="surface diag-empty"><div class="diag-empty-ring ${color(p.overall)}">${solid(p.unknown?'?':'✓',p.overall)}</div><div><span class="eyebrow">EVIDENCE STATUS</span><h2>${p.unknown?'暂无可确认的异常结论':'当前没有已确认异常'}</h2><p>${p.unknown?'存在来源待确认，不据此判断全部正常。':'正常对象不进入异常队列。'}</p><p>只读取${p.kind==='h'?'处理器、内存与文件系统':'TTFT、TPOT、E2E 与排队'}的已有规则结果。</p><button class="quiet-button" data-dialog="diagnostics">查看诊断范围</button></div></div></section>`;
 return `<section class="diagnostic-screen" data-domain="${p.kind}">${top}<div class="diagnostic-shell">
 <section class="surface focus glass diagnostic-main ${tone}" aria-label="已有证据诊断图">
  <header class="diag-panel-head"><div><span class="eyebrow">EVIDENCE / DIAGNOSIS</span><h2>${p.kind==='h'?'基础设施指标诊断':'推理性能指标诊断'}</h2></div><button class="small-chip" data-dialog="diagnostics">诊断范围</button></header>
  <div class="diag-column-heads"><span>指标证据</span><span>规则结果</span><span>关联定位</span></div>
  <div class="evidence-map" data-evidence-map>
   ${p.kind==='h'?hostSignals(p,color):`<div class="diag-signals" data-count="${p.metrics.length}">${p.metrics.map((m,i)=>`<button class="diag-signal ${color(m.state)} ${m.code===p.code?'chosen':''}" data-diag-code="${m.code}" aria-pressed="${m.code===p.code}" style="--signal-order:${i}"><div><span>${e(SHORT[m.code])}</span><b>${e(m.code)}</b></div><span class="signal-state">${e(C.LABEL[m.state])}</span>${chart(p.id,m.code,{compact:true})}<i class="signal-scan" aria-hidden="true"></i></button>`).join('')}</div>`}
   ${bridge(p,'inbound')}
   <div class="diag-core ${tone}" data-diag-core>${p.kind==='h'?volume('RESULT',st,p.code):solid(p.code,st)}<div class="core-copy"><span class="core-overline">${C.anomaly(st)?'已确认命中':st==='G'?'本指标未命中':'本指标待确认'}</span><h3>${e(SHORT[p.code])}</h3>${stateBadge(st)}<span class="core-footnote">已有规则结果 · 非新探测</span></div></div>
   ${bridge(p,'outbound')}
   <section class="diag-location ${tone}" data-diag-location>${p.kind==='h'?volume('HOST',st,['P','D','P/D'].includes(p.row.role)?p.row.role:'—'):solid(p.row.role==='P/D'?'P/D':p.row.role,st,true)}<div class="scope-insignia">${e(p.row.role==='P/D'?'P · D':p.row.role==='P'?'P':p.row.role==='D'?'D':'—')}</div><span class="eyebrow">ASSOCIATED SCOPE</span><h3>${e(p.role)}</h3><div class="location-groups">${p.groups.map(g=>`<button class="small-chip" data-group="${e(g)}">${e(name('groups',g))}</button>`).join('')}</div><div class="location-proof"><span class="proof-dot"></span>${C.anomaly(st)?'异常指标关联已定位':'保留登记关联'}</div><p>按登记关系定位<br>不推断其他组件故障${p.kind==='h'?'<br>颜色随所选指标 · 非主机健康':''}</p></section>
  </div>
  <section class="diag-trend-panel ${tone}" data-diag-trend><header><div><span class="eyebrow">${C.anomaly(st)?'CONFIRMED FINDING':'SELECTED METRIC'}</span><h3>${e(SHORT[p.code])}<span>${e(p.code)}</span></h3></div><div>${stateBadge(st)}<button class="small-chip" data-metric="${p.id}" data-code="${p.code}">展开趋势 ↗</button></div></header><div class="diagnostic-plot">${chart(p.id,p.code,{large:true})}<div class="plot-sweep" aria-hidden="true"></div></div></section>
 </section>
 <aside class="surface diagnostic-sidebar"><header><h2>${p.kind==='h'?'资源定位':'异常定位'}</h2>${badge(p.kind==='h'?'登记资源':'仅异常','amber')}</header><div class="diag-queue" aria-label="${p.kind==='h'?'资源选择':'异常项选择'}">${(p.displayIDs||p.ids).map(id=>{const row=byid(id),s=p.offline?'U':model.state(id,step),code=metricFor(id);return `<button class="diag-incident ${color(s)} ${id===p.id?'selected':''}" data-select-incident="${id}" aria-pressed="${id===p.id}"><div>${stateBadge(s)}<span>${C.anomaly(s)?'待复核':s==='G'?'正常':'待确认'}</span></div><h3>${e(ROLE[p.kind][row.role]||'角色待确认')}</h3><p>${e(SHORT[code])}</p><small>${model.groupIDsFor(id).map(g=>e(name('groups',g))).join(' · ')}</small></button>`;}).join('')}</div>
 <section class="diag-relationships"><h3>当前项 · 配置依赖业务</h3><div>${p.businesses.map(b=>`<button class="small-chip" data-business-detail="${e(b.id)}">${e(b.name)}</button>`).join('')||'<span class="muted">未登记关联</span>'}</div>${p.unknown?'<p class="muted">另有来源待确认。</p>':''}</section><footer><button class="quiet-button" data-dialog="rules">状态规则</button></footer></aside>
 </div></section>`;
}
function render(p,ctx){const html=renderLegacy(p,ctx);return p.kind==='h'&&root.Masked03R4?root.Masked03R4.render(p,ctx,html):html;}

// One shared display clock; observation states never create business health conclusions.
class MonitorCycle{
 constructor(){this.records=new Map()}
 reset(){for(const r of this.records.values())r.elapsed=0}
 pool(items){const hits=items.filter(x=>C.anomaly(x.state));return hits.length?hits.slice().sort((a,b)=>C.SEVERITY[b.state]-C.SEVERITY[a.state]):items}
 selection(owner,items){const pool=this.pool(items),key=this.records.get(owner)?.selected;return pool.find(x=>x.id+':'+x.code===key)||pool[0]||null}
 next({owner,items,id,code,dt,paused}){if(!owner||!items.length||paused)return null;const selected=id+':'+code,current=items.find(x=>x.id===id&&x.code===code)||this.selection(owner,items);if(!current)return null;let r=this.records.get(owner);if(!r){r={elapsed:0,selected};this.records.set(owner,r)}if(r.selected!==selected){r.selected=selected;r.elapsed=0}const pool=this.pool(items);if(pool.length===1&&pool[0].id===id&&pool[0].code===code)return null;r.elapsed+=Math.max(0,Math.min(dt,1));if(r.elapsed<(C.anomaly(current.state)?30:10))return null;r.elapsed=0;const i=pool.findIndex(x=>x.id===id&&x.code===code),next=pool[(i+1)%pool.length];r.selected=next.id+':'+next.code;return next}
}
const api=Object.freeze({CODES,SHORT,ROLE,plan,render,MonitorCycle});if(typeof module!=='undefined')module.exports=api;else root.MaskedDiagnostics=api;
})(typeof window==='undefined'?globalThis:window);
