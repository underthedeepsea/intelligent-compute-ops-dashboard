(function(){
'use strict';
// module-version: masked03-04-glass-20261030-r9a
function install(key,source,render){const descriptors=Object.getOwnPropertyDescriptors(source);descriptors.render={value:render,enumerable:true,writable:false,configurable:false};window[key]=Object.freeze(Object.create(Object.getPrototypeOf(source),descriptors));}
const C=window.MaskedCore,I=window.MaskedInference,R=window.Masked03R4;
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const status={G:'正常',W:'告警',R:'严重',U:'待确认',O:'同期对比'};
const full=code=>(C.METRICS[code]||code).replace(/\s*·\s*(TTFT|TPOT|E2E)$/,'');
function chartOf(x,ctx){const box=document.createElement('div');box.innerHTML=ctx.chart(x.id,x.code,{compact:true});if(x.state!=='U')box.querySelectorAll('path.line:not(.unknown)').forEach(line=>{if(line.classList.contains(ctx.color('U')))return;const glow=line.cloneNode();glow.classList.add('g25-flow');glow.setAttribute('pathLength','100');glow.setAttribute('aria-hidden','true');line.after(glow);});return box.innerHTML;}
function stateOf(x,chart){if(x.state==='U')return '来源待确认';if(x.state!=='O')return status[x.state]||'待确认';const box=document.createElement('div');box.innerHTML=chart;return box.querySelector('svg')?.getAttribute('aria-label')?.split('，')[1]||'同期对比';}
function attrs(x,kind){return kind==='h'?`data-diag-code="${esc(x.code)}"`:`data-pd-observation="${esc(x.id)}" data-pd-code="${esc(x.code)}"`;}

function swap(html,content,kind){const box=document.createElement('div');box.innerHTML=html;const aside=box.querySelector('aside');if(!aside)return html;aside.classList.add('volume-side',kind);aside.innerHTML=content;return box.innerHTML;}
function lamp(){return '<i class="g25-lamp" aria-hidden="true"></i>';}
function cell(x,ctx){const chart=chartOf(x,ctx);return `<button class="g25-slab g25-cell ${ctx.color(x.state)}" data-gauge-state="${esc(x.state)}" ${attrs(x,'e')}><div class="g25-name">${esc(full(x.code))}</div><div class="g25-value">${lamp()}${esc(stateOf(x,chart))}</div>${chart}</button>`;}
function renderInference(p,ctx){
 const items=I.monitorItems(p,ctx.model,ctx.step).filter(x=>x.id===p.id).map(x=>({...x,selected:x.code===p.code}));
 if(!items.length)return I.render(p,ctx);
 const hits=items.filter(x=>['W','R'].includes(x.state)),unknown=items.some(x=>x.state==='U'),tone=hits.some(x=>x.state==='R')?'R':hits.length?'W':unknown?'U':'G';
 const title=hits.length?`${hits.length} 项异常`:unknown?'指标待确认':'未见确认异常';
 const detail=hits.length?hits.map(x=>`${full(x.code)} · ${status[x.state]}`).join('；'):unknown?'存在待确认指标，不判断健康':'相对变化不作为异常判定';
 const phase=p.row?.role==='P'?'PREFILL':p.row?.role==='D'?'DECODE':p.row?.role||'阶段待确认';
 return swap(I.render(p,ctx),`<header class="g8-stage-head"><div class="g5-head"><h2>阶段状态</h2><span class="g8-phase">${esc(phase)}</span></div>${p.conflict?'<p class="g25-alert">登记引用冲突 · 仅保留可验证关系</p>':''}</header><div class="g7-panel" style="--metric-count:${items.length}"><div class="g7-summary ${ctx.color(tone)}" data-summary-state="${tone}"><span class="g7-eyebrow">当前阶段 · 指标结论</span><strong>${title}</strong><p>${esc(detail)}</p></div><div class="g7-metrics">${items.map(x=>instrument(x,ctx,p.offline)).join('')}</div><div class="g7-legend"><span class="mint">正常</span><span class="amber">告警</span><span class="red">严重</span><span class="muted">待确认</span><span class="sky">相对比较</span></div></div><p class="g8-footnote">状态轨迹来自回放 · 未提供原始读数</p>`,'g8-inference');
}
install('MaskedInference',I,renderInference);
function gauge(state){const paths=['M16 69 A44 44 0 0 1 34 34','M39 31 A44 44 0 0 1 81 31','M86 34 A44 44 0 0 1 104 69'],colors={G:'#76d9bd',W:'#f0b86a',R:'#ef7b89'},selected={G:0,W:1,R:2}[state];return `<svg data-gauge-state="${esc(state)}" class="g25-gauge" viewBox="0 0 120 84" role="img" aria-label="状态分区仪表：${esc(status[state]||'待确认')}，非数值刻度"><ellipse cx="60" cy="77" rx="49" ry="5" fill="#020b14" opacity=".8"/><path d="M9 73L22 80H98L111 73" fill="none" stroke="#799eaf" stroke-opacity=".3" stroke-width="2"/>${paths.map((path,i)=>`<path d="${path}" transform="translate(0 5)" stroke="#03101b" stroke-width="13" stroke-linecap="butt" fill="none"/><path d="${path}" stroke="${i===selected?colors[state]:'#375264'}" stroke-width="10" stroke-linecap="butt" fill="none"/><path d="${path}" transform="translate(0 -1)" stroke="#d8f0f6" stroke-opacity="${i===selected?'.4':'.09'}" stroke-width="1" fill="none"/>`).join('')}${selected!==undefined?`<path class="g25-flow" d="${paths[selected]}" pathLength="100"/>`:""}<circle cx="60" cy="63" r="11" fill="#102637" stroke="#92b8c7" stroke-opacity=".3"/><circle cx="60" cy="63" r="4" fill="${colors[state]||'#91a5af'}"/></svg>`;}
// Discrete source states, not a utilization scale or a second device illustration.
function historyStrip(x,ctx,offline){
 const step=ctx.step,source=ctx.model.d.tracks[x.id]?.metrics[x.code]?.state;
 if(offline||!source)return '<div class="g7-history-unavailable">来源待确认 · 不展示历史占位</div>';
 const first=Math.max(0,step-40),samples=[...source.slice(first,step+1)],runs=[];
 for(const state of samples){const s=['G','W','R','U','O'].includes(state)?state:'U',last=runs[runs.length-1];if(last?.state===s)last.count++;else runs.push({state:s,count:1});}
 const mins=(step-first)*ctx.model.d.interval_ms/60000,label=mins?`近 ${Number(mins.toFixed(1))} 分钟`:'当前窗口';
 return `<div class="g7-history" role="img" aria-label="${esc(full(x.code))}回放状态轨迹，${label}，${samples.length}个已有采样窗口" data-source-first="${first}" data-source-last="${step}" data-state-sequence="${samples.join('')}"><div class="g7-history-track">${runs.map(r=>`<i class="g7-segment" data-state="${r.state}" style="flex-grow:${r.count}"></i>`).join('')}</div><div class="g7-history-axis"><span>${label}</span><span>当前</span></div></div>`;
}
function instrument(x,ctx,offline){
 const comparison=x.state==='O'&&!offline?ctx.model.compare(x.id,x.code,ctx.step):null,label=x.state==='U'?'待确认':comparison?.label||status[x.state]||'待确认';
 const direction=comparison?({H:'↗',L:'↘',S:'→',N:'—'}[comparison.direction]||'—'):'';
 const evidence=comparison?`<div class="g8-comparison"><span>相对比较 · ${esc(comparison.basisLabel)}</span><b aria-hidden="true">${direction}</b></div>`:historyStrip(x,ctx,offline);
 return `<section class="g7-metric ${ctx.color(x.state)}${x.selected?' is-selected':''}" data-monitor-state="${esc(x.state)}" data-instrument="${esc(x.code)}" aria-label="${esc(full(x.code))}：${esc(label)}"><div class="g7-metric-heading"><h3>${esc(full(x.code))}</h3><strong>${esc(label)}</strong></div>${evidence}</section>`;
}
function picker(p,ctx){return `<details class="g25-picker"><summary>切换资源</summary><div class="g25-picker-panel">${(p.displayIDs||p.ids||[]).map(id=>`<button class="small-chip ${ctx.color(p.offline?'U':ctx.model.state(id,ctx.step))}" data-select-incident="${esc(id)}" aria-pressed="${id===p.id}">${esc(hostLabel(ctx.model,id))}<span>${ctx.model.groupIDsFor(id).map(g=>esc(ctx.model.map.groups.get(g)?.name||g)).join(' · ')}</span></button>`).join('')}</div></details>`;}
function hostLabel(model,id){const h=model.map.hosts.get(id);return h?.name||h?.label||`${h?.role||'未知'} 主机 ${String(model.cat.hosts.findIndex(x=>x.id===id)+1).padStart(2,'0')}`;}
function renderHost(p,ctx,legacy){
 if(!p.row)return R.render(p,ctx,legacy);
 const ids=p.displayIDs||p.ids||[],items=(p.metrics||[]).map(x=>({id:p.id,code:x.code,state:x.state||'U',selected:x.code===p.code})),counts={G:0,W:0,R:0,U:0};
 ids.forEach(id=>{const st=p.offline?'U':ctx.model.state(id,ctx.step);counts[st in counts?st:'U']++});
 const hits=items.filter(x=>['W','R'].includes(x.state)),unknown=items.filter(x=>x.state==='U'),tone=hits.some(x=>x.state==='R')?'R':hits.length?'W':unknown.length?'U':'G';
 const summary=hits.length?`${hits.length} 项异常`:unknown.length?(p.offline?'来源待确认':'指标待确认'):'三项正常';
 const detail=hits.length?hits.map(x=>`${full(x.code)} · ${status[x.state]}`).join('；'):unknown.length?(p.offline?'当前来源不可用，不判断健康':'存在待确认指标，不判断健康'):'当前未见已确认异常';
 return swap(R.render(p,ctx,legacy),`<header class="g5-head"><div><h2>资源状态</h2><span class="g5-resource">${esc(hostLabel(ctx.model,p.id))}</span></div>${picker(p,ctx)}</header><div class="g7-panel"><div class="g7-summary ${ctx.color(tone)}" data-summary-state="${tone}"><span class="g7-eyebrow">当前资源 · 指标结论</span><strong>${summary}</strong><p>${esc(detail)}</p></div><div class="g7-metrics">${items.map(x=>instrument(x,ctx,p.offline)).join('')}</div><div class="g7-legend" aria-label="状态轨迹图例"><span class="mint">正常</span><span class="amber">告警</span><span class="red">严重</span><span class="muted">待确认</span></div></div><footer class="g5-footer"><div class="g7-scope-label">登记资源状态</div><div class="g5-counts">${['G','W','R','U'].map(st=>`<span class="${ctx.color(st)}"><b>${counts[st]}</b><small>${status[st]}</small></span>`).join('')}</div><div class="g5-related"><span>配置依赖</span><p>${(p.businesses||[]).map(x=>esc(x.name)).join(' · ')||'未登记关联'}</p></div><div class="g5-note">状态轨迹来自回放 · 未提供原始读数</div></footer>`,'g25-host');
}
install('Masked03R4',R,renderHost);
})();
