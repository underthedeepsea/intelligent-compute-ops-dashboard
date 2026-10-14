/* Metric-specific history, status-coloured lines and explicit adaptive Y axes. */
(function(root){'use strict';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function plot(points,{level='NORMAL',threshold=null,unit='',label='',height=145,width=600}={}){
 const valid=points.filter(p=>typeof p.v==='number'&&Number.isFinite(p.v));
 if(!valid.length)return '<div class="trend-unavailable">同口径时间序列未接入</div>';
 const ratio=unit==='%',values=valid.map(p=>p.v),t=typeof threshold==='number'&&Number.isFinite(threshold)?threshold:null;
 const range=t===null?values:values.concat(t),min=Math.min(...range),max=Math.max(...range),pad=Math.max((max-min)*.15,Math.abs(max)*.025,.001);
 const low=Math.max(0,min-pad),high=ratio?Math.min(1,max+pad):max+pad,L=52,R=width-12,T=12,B=height-25;
 const x=i=>L+i/Math.max(1,points.length-1)*(R-L),y=v=>B-(v-low)/(high-low||1)*(B-T);
 let path='',pen=false;points.forEach((p,i)=>{if(typeof p.v!=='number'||!Number.isFinite(p.v)){pen=false;return;}path+=(pen?'L':'M')+x(i).toFixed(2)+' '+y(p.v).toFixed(2)+' ';pen=true;});
 const value=v=>(ratio?v*100:v).toLocaleString('zh-CN',{maximumFractionDigits:ratio?1:Math.abs(v)<10?2:1});
 const time=v=>new Date(v).toLocaleTimeString('zh-CN',{hour12:false,timeZone:'Asia/Shanghai'});
 const tone=['CRITICAL','ERROR','FAIL'].includes(level)?'red':level==='WARNING'?'amber':level==='UNKNOWN'?'unknown':'mint';
 const ticks=[low,(low+high)/2,high].map(v=>`<path class="chart-grid" d="M${L} ${y(v)}H${R}"/><text class="chart-y" x="${L-7}" y="${y(v)+4}" text-anchor="end">${esc(value(v))}</text>`).join('');
 const thresholdPath=t===null?'':`<path class="chart-threshold" d="M${L} ${y(t)}H${R}"/><text class="chart-threshold-label" x="${R}" y="${Math.max(12,y(t)-4)}" text-anchor="end">阈值 ${esc(value(t))}${esc(unit)}</text>`;
 return `<svg class="metric-history chart-${tone}" data-severity="${esc(level)}" data-metric-label="${esc(label)}" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="${esc(label)}；${esc(level)}；纵轴自适应"><title>${esc(label)} · ${esc(unit)} · Y轴 ${esc(value(low))}–${esc(value(high))}</title>${ticks}${thresholdPath}<path class="chart-series" d="${path}"/><text x="${L}" y="${height-5}">${esc(time(points[0].t))}</text><text x="${R}" y="${height-5}" text-anchor="end">${esc(time(points.at(-1).t))}</text></svg>`;
}
root.RefineCharts={plot};if(typeof module!=='undefined')module.exports={plot};
})(typeof window==='undefined'?globalThis:window);
