# SZF 五屏展示与中央装饰

本配置是离线合成数据的展示模式，仅通过 `/screen/?demo=1` 或 `/screen/01.html?demo=1`（02–05 同理）显式启用。2026-10-10 这一批根据用户要求，在界面使用「数据源 SZF机房」和 PRD 环境显示别名；这些标牌不代表真实接入、来源核验或生产环境身份。

数据仍来自 `frontend/screen/demo-data.js` 的确定性合成快照，采样窗口固定为 2026-10-10 11:25–11:30（UTC+8）。原始对象 ID、`environment_code: DEMO`、`origin: DEMO`、`source_type: SIMULATION`、`data_state: DEMO`、`data_mode: DEMO` 及所有数值和投影保留。界面上的 PRD 和 GPU 短名只是展示别名；筛选、链接、目录关系继续使用原始 ID/环境。数据源标牌、PRD 别名不能作为部署或接入证据。

入口、iframe、独立页面、跨屏链接均显式携带 `demo=1`。未带该参数时仍读取正常 API，沿用 UNKNOWN、未接入、CSV 快照、来源过期和错误规则；不会使用合成数值作为失败回退。内部 provenance 不通过文本替换更改。

02 中央采用固定六条镜像曲线围绕 hub 的装饰，不计算卡片端点，不读取卡片坐标，不随 P/D 数量或分批变化。曲线限制在中央栏范围；P/D 计数来自当前登记 Endpoint，KV 指标保留原先数据规则。图形不表示真实请求路径、KV 路由、路由健康或吞吐方向。合并部署不显示中央 P/D 装饰；阶段登记不完整保留提示。

动效沿用页面巡播暂停、恢复、动效开关、隐藏暂停及 `prefers-reduced-motion`。静态轨迹、hub、阶段计数和指标在关闭动效后仍可读。动画只是视觉节奏，不是新采样或实时监控。

本批 HTML 资源版本标记为 `central-szf-20261010`。本地验收为 GET/HEAD，只读浏览器夹具不写数据库。验收脚本：`frontend/screen/tests/central-szf-browser.cjs`（20 个展示组合、详情、provenance、资源 SHA）、`demo-completeness.cjs`（实际合成快照及正常模式边界）、`deployment-tv-browser.cjs --fixtures-only`（固定六曲线、密度、播放/暂停/静态、缺失与合并部署）。旧卡片端点验收已由用户撤销，本批改为中央装饰边界验收；旧证据目录保留。
