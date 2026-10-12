/* Stage-level process illustration only. This module cannot read telemetry.
   The three optical lanes are visual tracks, NOT runtime KV routes or requests. */
(function(root){
'use strict';
const lanes=(combined=false)=>{
 const paths=combined?['M150 136 H635','M865 136 H1360']:[
  'M412 106 C513 106 560 138 664 138',
  'M412 142 H664',
  'M412 178 C513 178 560 146 664 146',
  'M836 138 C940 138 988 106 1088 106',
  'M836 142 H1088',
  'M836 146 C940 146 988 178 1088 178'
 ];
 return `<svg class="flow-optics" viewBox="0 0 1500 250" preserveAspectRatio="none" aria-hidden="true">${paths.map((d,i)=>`<path d="${d}" class="optical-track"/><path d="${d}" class="optical-soft"/><path d="${d}" pathLength="100" class="flow-packet packet-${i%3} ${i>=3?'cool-packet':''}" style="--travel-delay:${-i*.73}s"/>`).join('')}<path class="optical-axis" d="M44 232 H1456"/>${[80,300,520,750,980,1200,1420].map(x=>`<path class="optical-tick" d="M${x} 228v8"/>`).join('')}</svg>`;
};
const chip=(type)=>`<div class="chip-scene ${type==='P'?'prefill-chip':type==='D'?'decode-chip':'combined-chip'}" aria-hidden="true"><div class="chip-ground"></div><div class="chip-ring"></div><div class="chip-volume"><div class="chip-base base-two"></div><div class="chip-base base-one"></div><div class="chip-face"><div class="chip-traces"></div><div class="chip-pixels">${Array.from({length:36},(_,i)=>`<i style="--cell:${i}"></i>`).join('')}</div><span class="chip-monogram">${type}</span></div></div></div>`;
function split({p,d,complete}){
 return `<div class="process-visual ${complete?'':'no-transfer'}">
   <div class="phase-captions"><div><span class="phase-number">01</span><span><b>Prefill</b><small>输入预处理 · 并行计算上下文</small></span></div><div class="phase-caption-kv"><b>KV CACHE</b><small>上下文交接</small></div><div><span class="phase-number">02</span><span><b>Decode</b><small>逐步解码 · 流式生成 Token</small></span></div></div>
   <div class="process-art">${lanes()}
    <div class="input-motif"><span>PROMPT</span><div class="input-bars"><i></i><i></i><i></i><i></i></div><small>上下文输入</small></div>
    <button class="compute-core core-prefill" data-detail="flow" aria-label="查看 Prefill 处理原理">${chip('P')}<span class="core-caption"><i></i>上下文处理</span></button>
    <button class="kv-relay" data-detail="flow" aria-label="查看 KV 上下文交接原理"><div class="cache-field"><div class="cache-slab slab-back"></div><div class="cache-slab slab-mid"></div><div class="cache-slab slab-front"><span>K</span><i></i><span>V</span></div><i class="cache-glint"></i></div><span class="relay-caption">${complete?'阶段间交接':'登记不完整'}</span></button>
    <button class="compute-core core-decode" data-detail="flow" aria-label="查看 Decode 生成原理">${chip('D')}<span class="core-caption"><i></i>逐步生成</span></button>
    <div class="output-motif"><span>OUTPUT</span><div class="token-sequence">${Array.from({length:5},(_,i)=>`<i style="--token:${i}"></i>`).join('')}</div><small>Token 流</small></div>
   </div>
   <div class="phase-annotations"><span><i class="mint-dot"></i>${p} 个 Prefill 登记实例</span><button data-detail="flow">${complete?'流动仅表达阶段原理':'阶段登记不完整 · 交接动画暂停'}</button><span><i class="sky-dot"></i>${d} 个 Decode 登记实例</span></div>
  </div>`;
}
function combined(){
 return `<div class="process-visual combined-process"><div class="phase-captions"><div><span class="phase-number">01</span><span><b>输入上下文</b><small>Prompt processing</small></span></div><div class="phase-caption-kv"><b>UNIFIED ENGINE</b><small>单实例内完成两个阶段</small></div><div><span class="phase-number">02</span><span><b>输出 Token</b><small>Streaming generation</small></span></div></div><div class="process-art">${lanes(true)}<div class="combined-copy input-copy"><b>Prefill</b><span>输入处理</span><div class="input-bars"><i></i><i></i><i></i><i></i></div></div><button class="compute-core core-combined" data-detail="rules" aria-label="查看合并推理实例的数据规范">${chip('C')}<span class="core-caption">COMBINED</span></button><div class="combined-copy output-copy"><b>Decode</b><span>逐步生成</span><div class="token-sequence">${Array.from({length:5},(_,i)=>`<i style="--token:${i}"></i>`).join('')}</div></div></div><div class="phase-annotations"><span>一个 Endpoint · 两个阶段</span><span>合并模式不绘制跨实例 KV 传输</span><span>下方仅列实际登记实例</span></div></div>`;
}
function colocated(){return `<div class="process-visual colocated-process"><div class="phase-captions"><div><b>PREFILL</b><small>登记阶段引用</small></div><div class="phase-caption-kv"><b>SHARED POD REFERENCE</b><small>P / D 指向同一 Pod</small></div><div><b>DECODE</b><small>登记阶段引用</small></div></div><div class="colocated-art">${chip('P/D')}<div><h3>物理分离待确认</h3><p>按原清单保留 P/D 分离标签；<br>不绘制跨 Pod 的 KV 交接。</p></div></div><div class="phase-annotations"><span>阶段引用不等于独立 Pod</span><span>节点与 Pod 名称一致</span><span>不补造独立 Decode 副本</span></div></div>`;}
root.RefineFlow=Object.freeze({split,combined,colocated});
})(typeof window==='undefined'?globalThis:window);
