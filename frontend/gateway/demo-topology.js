/* Version 2: configured topology. Legacy global is retained for existing callers. */
(function(root){'use strict';
const ORDER=[['team'],['business'],['key','model'],['service'],['pd_group'],['endpoint'],['cluster'],['pod','runtime_member','node']];
const LABEL={team:'团队',business:'业务',key:'API KEY',model:'模型',service:'推理服务',pd_group:'P/D 组',endpoint:'阶段入口',cluster:'集群',pod:'Pod',runtime_member:'运行成员',node:'节点'};
const REL={owns:'归属',depends_on:'服务依赖',serves:'提供服务',contains_pd_group:'部署分组',contains_endpoint:'阶段入口',deployed_on:'业务部署范围',member_of_pd:'属于分组',runs_in:'位于集群',scheduled_on:'调度于',backs_endpoint:'承载入口'};
const E=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function branches(){return new Map();}
function project(graph,closed=new Set()){
 const all=new Map(graph.nodes.map(n=>[n.id,n]));
 // Services and businesses are never collapsed; they carry direct dependency evidence.
 const nodes=graph.nodes.filter(n=>!closed.has(n.type)&&ORDER.flat().includes(n.type)),ids=new Set(nodes.map(n=>n.id));
 const types=ORDER.map(c=>c.filter(t=>nodes.some(n=>n.type===t))).filter(c=>c.length);
 const hasGroups=new Set(graph.edges.filter(e=>e.type==='contains_pd_group').map(e=>e.source));
 const hasEPs=new Set(graph.edges.filter(e=>e.type==='contains_endpoint').map(e=>e.target));
 const primary=[],secondary=[];
 graph.edges.forEach((edge,index)=>{
  const item={...edge,index,evidence:[index]};
  const duplicate=(edge.type==='serves'&&all.get(edge.source)?.type==='service'&&hasGroups.has(edge.source)&&hasEPs.has(edge.target))||edge.type==='member_of_pd';
  const detailed=edge.type==='deployed_on';
  if(ids.has(edge.source)&&ids.has(edge.target)&&!duplicate&&!detailed)primary.push(item);else secondary.push(item);
 });
 return {nodes,types,primary,secondary,hidden:graph.nodes.filter(n=>!ids.has(n.id)),branches:new Map(),retained:new Set()};
}
function layout(view,sizes={},available=1200){
 const cardWidth=202,gap=56,pad=28,cols=view.types;
 const groups=cols.map(types=>view.nodes.filter(n=>types.includes(n.type)).sort((a,b)=>String(a.name).localeCompare(String(b.name),'zh-CN')||a.id.localeCompare(b.id)));
 const height=Math.max(500,...groups.map(ns=>90+ns.reduce((v,n)=>v+(sizes[n.id]?.height||90)+18,0)));
 const width=Math.max(720,pad*2+cols.length*cardWidth+(cols.length-1)*gap);const rects=new Map();
 groups.forEach((ns,i)=>{const total=ns.reduce((v,n)=>v+(sizes[n.id]?.height||90)+18,0)-18;let y=cols[i].every(t=>['model','key'].includes(t))?65:56+(height-80-total)/2;for(const n of ns){const h=sizes[n.id]?.height||90;rects.set(n.id,{x:pad+i*(cardWidth+gap),y,width:cardWidth,height:h});y+=h+18;}});
 const routes=view.primary.map(edge=>{const a=rects.get(edge.source),b=rects.get(edge.target),forward=b.x>a.x,x1=forward?a.x+a.width:a.x,x2=forward?b.x:b.x+b.width,y1=a.y+a.height/2,y2=b.y+b.height/2,mid=(x1+x2)/2;
  // Skip-column dependency curves remain real edges, not invented adjacency.
  return {...edge,d:`M${x1},${y1} C${mid},${y1} ${mid},${y2} ${x2},${y2}`,points:[[x1,y1],[mid,y1],[mid,y2],[x2,y2]]};});
 return {rects,routes,width,height,types:cols,columnX:cols.map((_,i)=>pad+i*(cardWidth+gap))};
}
function mount(container,graph,options={}){
 let dead=false,scale=1,panX=0,panY=0,fitMode=true,paused=false,drag=null,moved=false,raf=0,geometry=null;
 const focus=options.focusType+':'+options.focusId,byId=new Map(graph.nodes.map(n=>[n.id,n])),view=project(graph),media=matchMedia('(prefers-reduced-motion: reduce)');
 const title=byId.get(focus)?.name||'资源关系';
 const direct=view.primary.filter(e=>e.type==='depends_on').length;
 const detailButton=id=>{const n=byId.get(id);return `<button type="button" data-gt-focus="${E(id)}">${E(n?.name||id)}</button>`;};
 const fullName=n=>[n.name,n.namespace].filter(Boolean).join(' / ');
 const role=n=>n.type==='endpoint'?({PREFILL:'P · Prefill',DECODE:'D · Decode',COMBINED:'合并推理',ROUTER:'Router'}[n.role||options.endpointRoles?.[n.id]]||'阶段入口'):LABEL[n.type]||n.type;
 container.innerHTML=`<section class="gt-shell"><header class="gt-header"><div><b>${E(title)}</b><p>业务直接依赖服务 · PD组按名称识别 · namespace为部署范围</p></div><span class="gt-count">${graph.nodes.length} 对象 · ${direct} 条服务依赖</span></header><div class="gt-toolbar" role="group" aria-label="拓扑视图控制"><span class="gt-legend"><i></i> 实线：登记关系 <small>非实时流量</small></span><button type="button" data-gt-action="out" aria-label="缩小拓扑">−</button><output class="gt-scale" aria-live="polite">100%</output><button type="button" data-gt-action="in" aria-label="放大拓扑">＋</button><button type="button" data-gt-action="fit">适应画布</button><button type="button" data-gt-action="reset">100%</button><button type="button" data-gt-action="motion">暂停动效</button><button type="button" data-gt-action="fullscreen" aria-pressed="false">全屏展示 ⛶</button></div><div class="gt-viewport" tabindex="0" aria-label="资源关系画布。拖动空白平移，Ctrl加滚轮缩放，0适应画布。"><div class="gt-world"><svg class="gt-svg" aria-hidden="true"></svg>${view.types.map((c,i)=>`<div class="gt-column" data-column="${i}">${E(c.map(t=>LABEL[t]).join(' / '))}</div>`).join('')}${view.nodes.map(n=>`<button type="button" class="gt-card type-${E(n.type)} ${n.id===focus?'is-focused':''}" data-gt-focus="${E(n.id)}" title="${E(fullName(n))}" ${n.id===focus?'aria-current="true"':''}><span class="gt-type">${E(role(n))}</span><strong>${E(n.type==='pd_group'?n.name:n.type==='endpoint'?n.workload_ref||n.name:n.name)}</strong><span class="gt-meta">${E(n.namespace||n.environment_code||'登记配置')}</span>${n.type==='business'?'<span class="gt-route-hint">直接依赖 → 推理服务</span>':''}</button>`).join('')}</div></div><footer class="gt-footer"><span>拖动空白平移 · Ctrl / ⌘ + 滚轮缩放 · 0 适应画布 · Esc 退出全屏</span><span role="status" class="gt-status">${graph.truncated?'返回范围已截断，请缩小范围':''}</span></footer><details class="gt-evidence"><summary>完整关系证据（${graph.edges.length} 条）</summary><div>${graph.edges.map(edge=>`<p>${detailButton(edge.source)} <span>→ ${E(REL[edge.type]||edge.type)} →</span> ${detailButton(edge.target)}</p>`).join('')}</div></details></section>`;
 const shell=container.querySelector('.gt-shell'),vp=container.querySelector('.gt-viewport'),world=container.querySelector('.gt-world'),svg=container.querySelector('.gt-svg');
 function measure(){if(dead)return;const sizes={};container.querySelectorAll('.gt-card').forEach(el=>sizes[el.dataset.gtFocus]={height:el.offsetHeight});geometry=layout(view,sizes,vp.clientWidth);world.style.width=geometry.width+'px';world.style.height=geometry.height+'px';svg.setAttribute('viewBox',`0 0 ${geometry.width} ${geometry.height}`);
  container.querySelectorAll('.gt-card').forEach(el=>{const r=geometry.rects.get(el.dataset.gtFocus);el.style.left=r.x+'px';el.style.top=r.y+'px';});container.querySelectorAll('[data-column]').forEach(el=>el.style.left=geometry.columnX[Number(el.dataset.column)]+'px');
  svg.innerHTML=geometry.routes.map(r=>`<path class="gt-edge ${r.type==='depends_on'?'direct-dependency':''}" data-relation="${E(r.type)}" data-source="${E(r.source)}" data-target="${E(r.target)}" d="${r.d}"><title>${E(REL[r.type]||r.type)}</title></path><path class="gt-edge-motion" d="${r.d}"/>`).join('');
  if(fitMode)fit();else paint();
 }
 function paint(){if(dead)return;world.style.transform=`translate(${panX}px,${panY}px) scale(${scale})`;container.querySelector('.gt-scale').textContent=Math.round(scale*100)+'%';}
 function fit(){fitMode=true;scale=Math.max(.15,Math.min(1.15,(vp.clientWidth-28)/geometry.width,(vp.clientHeight-24)/geometry.height));panX=(vp.clientWidth-geometry.width*scale)/2;panY=(vp.clientHeight-geometry.height*scale)/2;paint();}
 function zoom(next,x=vp.clientWidth/2,y=vp.clientHeight/2){fitMode=false;next=Math.max(.15,Math.min(2.5,next));const factor=next/scale;panX=x-(x-panX)*factor;panY=y-(y-panY)*factor;scale=next;paint();}
 function syncMotion(){shell.classList.toggle('gt-paused',paused||media.matches||document.hidden);const b=container.querySelector('[data-gt-action="motion"]');b.disabled=media.matches;b.textContent=media.matches?'静态视图':paused?'开启动效':'暂停动效';}
 function fullChanged(){if(dead)return;const on=document.fullscreenElement===shell||shell.classList.contains('is-expanded');const b=container.querySelector('[data-gt-action="fullscreen"]');b.textContent=on?'退出全屏 ⤡':'全屏展示 ⛶';b.setAttribute('aria-pressed',String(on));fitMode=true;resize();}
 async function fullscreen(){if(document.fullscreenElement===shell){await document.exitFullscreen();return;}if(shell.classList.contains('is-expanded')){shell.classList.remove('is-expanded');fullChanged();return;}try{if(!shell.requestFullscreen)throw Error('unsupported');await shell.requestFullscreen();}catch{if(dead)return;shell.classList.add('is-expanded');container.querySelector('.gt-status').textContent='当前浏览器使用页内最大化';fullChanged();}}
 function click(ev){if(moved){moved=false;return;}const b=ev.target.closest('[data-gt-action]');if(b){const a=b.dataset.gtAction;if(a==='in')zoom(scale*1.2);if(a==='out')zoom(scale/1.2);if(a==='fit')fit();if(a==='reset')zoom(1);if(a==='fullscreen')fullscreen();if(a==='motion'){paused=!paused;syncMotion();}return;}const focusBtn=ev.target.closest('[data-gt-focus]');if(focusBtn){const id=focusBtn.dataset.gtFocus,i=id.indexOf(':');options.onFocus?.(id.slice(0,i),id.slice(i+1));}}
 function wheel(ev){if(!(ev.ctrlKey||ev.metaKey))return;ev.preventDefault();const r=vp.getBoundingClientRect();zoom(scale*Math.exp(-ev.deltaY*.002),ev.clientX-r.left,ev.clientY-r.top);}
 function down(ev){if(ev.button!==0||ev.target.closest('button'))return;drag={x:ev.clientX,y:ev.clientY,px:panX,py:panY};moved=false;vp.setPointerCapture?.(ev.pointerId);vp.classList.add('is-dragging');}
 function move(ev){if(!drag)return;const dx=ev.clientX-drag.x,dy=ev.clientY-drag.y;if(Math.abs(dx)+Math.abs(dy)>3)moved=true;fitMode=false;panX=drag.px+dx;panY=drag.py+dy;paint();}
 function up(){drag=null;vp.classList.remove('is-dragging');}
 function key(ev){if(ev.target.matches('input,textarea,select'))return;if(ev.key==='Escape'&&shell.classList.contains('is-expanded')){shell.classList.remove('is-expanded');fullChanged();return;}if(!shell.contains(document.activeElement))return;if(['+','=','-','0'].includes(ev.key)){ev.preventDefault();if(ev.key==='0')fit();else zoom(scale*(ev.key==='-'?1/1.2:1.2));}}
 function resize(){cancelAnimationFrame(raf);raf=requestAnimationFrame(measure);}
 container.addEventListener('click',click);vp.addEventListener('wheel',wheel,{passive:false});vp.addEventListener('pointerdown',down);vp.addEventListener('pointermove',move);vp.addEventListener('pointerup',up);vp.addEventListener('pointercancel',up);document.addEventListener('keydown',key);document.addEventListener('fullscreenchange',fullChanged);document.addEventListener('visibilitychange',syncMotion);media.addEventListener('change',syncMotion);const observer=new ResizeObserver(resize);observer.observe(vp);measure();syncMotion();
 return {getGeometry:()=>({...geometry,scale,panX,panY}),fit,zoom:next=>zoom(next),destroy(){if(dead)return;dead=true;cancelAnimationFrame(raf);observer.disconnect();if(document.fullscreenElement===shell)document.exitFullscreen?.().catch(()=>{});container.removeEventListener('click',click);vp.removeEventListener('wheel',wheel);vp.removeEventListener('pointerdown',down);vp.removeEventListener('pointermove',move);vp.removeEventListener('pointerup',up);vp.removeEventListener('pointercancel',up);document.removeEventListener('keydown',key);document.removeEventListener('fullscreenchange',fullChanged);document.removeEventListener('visibilitychange',syncMotion);media.removeEventListener('change',syncMotion);container.innerHTML='';}};
}
const api={branches,project,layout,mount};if(typeof module!=='undefined')module.exports=api;root.GatewayTopology=api;root.GatewayDemoTopology=api;
})(typeof window==='undefined'?globalThis:window);
