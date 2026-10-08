window.OverviewDOM = `<div class="overview-page">
<section class="overview-heading"><div class="overview-page-title"><span class="mono">01</span><div><h1>全局运维总览</h1><p>单设备观测 · 已登记部署关系</p></div></div><div class="overview-counts" id="overview-counts"></div></section>
<div class="overview-layout">
<div class="overview-col overview-left">
<section class="overview-panel overview-host"><h2>主机健康 / 地域</h2><div class="overview-panel-body" id="c-host"></div></section>
<section class="overview-panel overview-compute"><h2>计算资源利用率</h2><div class="overview-device" id="overview-host-device">HOST 尚未绑定</div><div class="overview-panel-body overview-grid-2"><div id="c-compute-cpu"></div><div id="c-compute-mem"></div></div></section>
<section class="overview-panel overview-gpu"><h2>GPU 单设备指标</h2><div class="overview-device" id="overview-gpu-device">GPU 尚未绑定</div><div class="overview-panel-body overview-grid-6"><div id="c-gpu-1"></div><div id="c-gpu-2"></div><div id="c-gpu-3"></div><div id="c-gpu-4"></div><div id="c-gpu-5"></div><div id="c-gpu-6"></div></div></section>
<section class="overview-panel overview-hetero"><h2>异构算力性能</h2><div class="overview-panel-body overview-grid-2"><div id="c-hetero-1"></div><div id="c-hetero-2"></div></div></section>
</div>
<div class="overview-col overview-center">
<section class="overview-panel overview-topology"><div id="c-map"></div></section>
<div class="overview-bottom"><section class="overview-panel"><h2>基础设施告警</h2><div class="overview-empty overview-alert-note"><b>—</b><span>基础设施告警未接入</span><small>未接入不代表零故障</small></div></section><section class="overview-panel"><h2>RoCE 网络指标</h2><div class="overview-panel-body overview-grid-2"><div id="c-net-1"></div><div id="c-net-2"></div></div></section></div>
</div>
<div class="overview-col overview-right">
<section class="overview-panel overview-model"><h2>全局模型性能</h2><div class="overview-panel-body overview-grid-3"><div id="c-model-1"></div><div id="c-model-2"></div><div id="c-model-3"></div></div></section>
<section class="overview-panel overview-token"><h2>Token 监测</h2><div class="overview-panel-body overview-grid-2"><div id="c-token-1"></div><div id="c-token-2"></div></div></section>
<section class="overview-panel overview-pd"><h2>P/D 阶段指标</h2><div class="overview-panel-body overview-grid-2"><div id="c-pd-1"></div><div id="c-pd-2"></div></div></section>
<div class="overview-right-bottom"><section class="overview-panel"><h2>推理队列</h2><div class="overview-panel-body" id="c-queue"></div></section><section class="overview-panel"><h2>模型风险</h2><div class="overview-panel-body" id="c-risk"></div></section></div>
</div></div></div>`;
