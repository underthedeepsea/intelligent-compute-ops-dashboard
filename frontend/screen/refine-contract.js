/* Screen contract v1.0.0. Presentation only; never redefines inspection rules. */
(function (root) {
  'use strict';
  const DEFINITIONS = Object.freeze({
    ttft_p95_ms: ['首 Token 延迟 P95', 'ms', 'ENDPOINT'],
    tpot_p95_ms: ['逐 Token 延迟 P95', 'ms/token', 'ENDPOINT'],
    e2e_p99_ms: ['端到端延迟 P99', 'ms', 'ENDPOINT'],
    request_rate: ['请求速率', 'requests/s', 'ENDPOINT'],
    generated_tokens_per_second: ['生成吞吐', 'tokens/s', 'ENDPOINT'],
    input_tokens_per_second: ['输入吞吐', 'tokens/s', 'ENDPOINT'],
    kv_cache_hit_ratio: ['KV 缓存命中率', 'ratio', 'ENDPOINT'],
    ttft_e2e_ratio: ['TTFT / E2E', 'ratio', 'ENDPOINT'],
    running: ['运行请求', 'requests', 'ENDPOINT'], waiting: ['排队请求', 'requests', 'ENDPOINT'],
    utilization_ratio: ['GPU 利用率', 'ratio', 'DEVICE'],
    temperature_celsius: ['GPU 温度', '°C', 'DEVICE'],
    cpu_busy_ratio: ['CPU 忙碌率', 'ratio', 'DEVICE'], filesystem_usage_ratio:['文件系统使用率','ratio','DEVICE'],
    memory_usage_ratio: ['内存 / 显存使用率', 'ratio', 'DEVICE']
  });
  const LABELS = Object.freeze({ FRESH:'有效窗口', STALE:'来源过期', UNVERIFIED:'来源待验证',
    MISSING:'无观测', UNSUPPORTED:'尚未接入', UNMAPPED:'未绑定', INVALID:'数据无效',
    SOURCE_ERROR:'链路异常', UNKNOWN:'状态未知', CSV_SNAPSHOT:'CSV 静态快照',
    REPLAY:'回放窗口', SIMULATION:'回放窗口', RESET:'计数重置', LOADING:'正在读取' });
  function escape(v) { return String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
  function finite(v) { return typeof v === 'number' && Number.isFinite(v); }
  function stamp(v) { return typeof v === 'string' && /(?:Z|[+-]\d\d:\d\d)$/.test(v) ? Date.parse(v) : NaN; }
  function revision(v) { if ((Number.isSafeInteger(v) && v >= 0) || (typeof v === 'string' && /^\d+$/.test(v))) return BigInt(v); throw new Error('无效 view_revision'); }
  function unique(rows) {
    const seen = new Map();
    for (const x of rows || []) {
      if (!x || typeof x.id !== 'string') continue;
      const key = `${x.environment_code || ''}:${x.id}`;
      if (!seen.has(key)) seen.set(key, x);
    }
    return [...seen.values()];
  }
  function endpoints(data) {
    return unique((data?.items || []).flatMap(x => x.dependency_services ? x.dependency_services.flatMap(s=>s.endpoints || []) : x.endpoints || (x.metrics && x.service_id ? [x] : [])));
  }
  function quality(entity, now = Date.now(), opts = {}) {
    if (!entity) return 'MISSING';
    const o = entity.observation;
    const base = entity.data_state || o?.data_state || 'UNKNOWN';
    if (['INVALID','UNSUPPORTED','UNMAPPED','MISSING','RESET'].includes(base)) return base;
    if (!o) return 'MISSING';
    if (opts.transportError || (o.transport_status && o.transport_status !== 'OK')) return 'SOURCE_ERROR';
    if (o.transport_status !== 'OK') return 'UNKNOWN';
    const start = stamp(o.source_window?.start), end = stamp(o.source_window?.end);
    if (!finite(start) || !finite(end) || start >= end || end > now + 30000) return 'INVALID';
    if (o.source_type === 'CSV' && base === 'CSV_SNAPSHOT' && o.data_state === 'CSV_SNAPSHOT') return 'CSV_SNAPSHOT';
    const ttl = o.max_age_seconds;
    if (!finite(ttl) || ttl <= 0) return 'UNKNOWN';
    if (base === 'STALE' || o.freshness === 'STALE' || now-end > Math.min(ttl,300)*1000) return 'STALE';
    if (base === 'SOURCE_ERROR') return 'SOURCE_ERROR';
    if (opts.replay && o.origin === 'SYNTHETIC') return 'REPLAY';
    if (opts.demo && o.origin === 'SIMULATION') return 'SIMULATION';
    if (o.origin !== 'VERIFIED' || base === 'UNVERIFIED') return 'UNVERIFIED';
    return base === 'FRESH' ? 'FRESH' : 'UNKNOWN';
  }
  function present(entity, key, now = Date.now(), opts = {}) {
    const def = DEFINITIONS[key];
    const point = entity?.metrics?.[key];
    let state = quality(entity, now, opts);
    const out = { key, label:def?.[0] || key, text:'—', value:null, unit:def?.[1] || '',
      state, origin:entity?.observation?.origin || 'UNKNOWN', usable:false, source:entity?.observation || null };
    if (!def) { out.state='UNSUPPORTED'; return out; }
    if (!point) { out.state = state === 'UNSUPPORTED' ? state : 'MISSING'; return out; }
    if (!['AVAILABLE','VALID'].includes(point.state || point.quality)) { out.state=LABELS[point.state || point.quality] ? (point.state || point.quality) : 'INVALID'; return out; }
    if (!finite(point.value) || point.value < 0 || point.unit !== def[1] || point.scope !== def[2] || entity?.observation?.identity?.scope !== def[2] || (point.unit === 'ratio' && point.value > 1)) {out.state='INVALID';return out;}
    if (point.collected_at !== undefined) {
      const t=stamp(point.collected_at), start=stamp(entity?.observation?.source_window?.start), end=stamp(entity?.observation?.source_window?.end);
      if (!finite(t) || t < start || t > end+300000 || t > now+30000) {out.state='INVALID';return out;}
      if (state !== 'CSV_SNAPSHOT' && now-t > Math.min(entity.observation.max_age_seconds,300)*1000) state='STALE';
    }
    if (['INVALID','UNSUPPORTED','UNMAPPED','MISSING','UNKNOWN','RESET'].includes(state)) {out.state=state;return out;}
    out.state=state; out.value=point.value;
    out.text=(point.unit==='ratio' ? point.value*100 : point.value).toLocaleString('zh-CN',{maximumFractionDigits:point.unit==='ratio'?1: key.includes('temperature')?1: 1});
    if (point.unit==='ratio') out.unit='%';
    out.usable=['FRESH','REPLAY','SIMULATION'].includes(state) && entity.observation.transport_status==='OK';
    return out;
  }
  function endpointStatus(e, now, opts={}) {
    const q=quality(e,now,opts);
    if (!['FRESH','REPLAY','SIMULATION'].includes(q) || e?.observation?.transport_status!=='OK') return 'UNKNOWN';
    return ['NORMAL','WARNING','CRITICAL','OK','PASS','FAIL','ERROR'].includes(e.status) ? e.status : 'UNKNOWN';
  }
  function coverage(rows,now,opts={}) {
    const list=unique(rows); const values=list.map(e=>quality(e,now,opts));
    const fresh=values.filter(s=>['FRESH','REPLAY','SIMULATION'].includes(s)).length;
    return {total:list.length, fresh, stale:values.filter(s=>s==='STALE').length,
      unknown:values.filter(s=>!['FRESH','REPLAY','SIMULATION','STALE'].includes(s)).length,
      ratio:list.length?fresh/list.length:null};
  }
  function validateEnvelope(v, kind) {
    if (![1,'1','1.0'].includes(v?.schema_version)) throw new Error('不兼容的 API schema');
    revision(v.view_revision);
    const d=v.data;
    if (!d || !Array.isArray(d.items) || !d.summary || !d.coverage || !d.source_window || d.kind!==kind) throw new Error('投影契约不匹配');
    const seen=new Set();
    for (const x of d.items) {
      if (!x || typeof x.id!=='string' || typeof x.name!=='string' || seen.has(x.id)) throw new Error('对象身份缺失或重复');
      seen.add(x.id);
      if (kind==='services' && (!Array.isArray(x.endpoints) || !Array.isArray(x.configured_businesses))) throw new Error('服务投影缺少关系集合');
      if (kind==='critical-apps' && (!Array.isArray(x.service_ids) || !Array.isArray(x.dependency_services))) throw new Error('业务投影缺少依赖集合');
    }
    return v;
  }
  const api={DEFINITIONS,LABELS,escape,finite,stamp,revision,unique,endpoints,quality,present,endpointStatus,coverage,validateEnvelope};
  root.RefineContract=api; if (typeof module!=='undefined') module.exports=api;
})(typeof window!=='undefined'?window:globalThis);
