# 原布局统一接入合同

本次沿用根目录原五屏的 DOM/class、布局比例、主题、字体与面板空间。原目录只作参考，不加载原 demo 脚本，不连接 demo_server，不在错误时回退固定数据。正常模式唯一数据入口是同源 `/api/v1/`；当前由 `ControlAPI.ensureAccess()` 读取直接访问元数据与 CSRF token，不建立登录会话。

## 启动与共享接口

各 HTML 顺序加载 `api.js`、`live-provider.js`、专属 `restoredXX.js`、`screens.js`。01另加载原DOM模板 `overview-dom.js`。共有容器为 `.screen`、`#app-header`、`#app`、`#app-footer`。

注册形式为 `window.ScreenRenderers['02'] = { render(data,ctx), bind(root,ctx), tick(ctx) }`。render返回HTML，bind在每次渲染后绑定可见控件，tick每个可见秒调用一次。tick在暂停时仍调用，renderer自行冻结轮播；bootstrap处理60秒人工暂停到期，隐藏页冻结人工暂停时间。

ctx提供 `e`、`m`、`ageState`、`endpointState`、`stateLabel`、`tag`、`source`、`link(screen,id,label)`、`navigate(screen,id,extra)`、`refresh()`、`pause(bool)`。`ctx.data`为原始最新投影，`ctx.now`为当前毫秒，`ctx.state`为持久对象，保留selected、endpoint、paused、cycle、manualUntil及专属状态字段。

`ctx.catalog`按collection名提供clusters、services、models、businesses、endpoints、pd-groups、runtime-members；仅GET访问已有catalog接口，按100条游标分页并排除disabled对象。失败保留已知目录并标记目录补充不可用，不将目录身份扩展成运行健康。目录元数据不得覆盖Endpoint原始ID、来源或窗口。

## 数据与错误

每屏只有一个LiveProvider轮询对应overview / services / infrastructure / services / critical-apps投影。只有校验通过且revision递增的响应替换有效帧；旧响应、无效响应、网络错误保留旧帧，通信错误单独提示。来源年龄由原source_window和max_age_seconds判断；浏览器收到响应不刷新来源年龄。只在FRESH且巡检transport=OK时显示Endpoint原始状态。

目录来源按已读取实体origin显示（单一来源/混合/未知），观测origin按原始observation显示，两者分离。当前DEMO目录、UNVERIFIED观测均保持可见，来源过期状态不会抹去原始来源标记。未知采用中性色，不作good。01保留原三栏与地图空间，地域、硬件和全局聚合未接入留空；05保留原固定w-card布局和watch_order，SLI、趋势和健康统计空值，真实配置服务依赖可下钻04。配置依赖不代表业务实际影响。02/03/04边界由各专属renderer保持。

## 门户

portal保留原1920×1080 iframe整体缩放，按stage宽高取较小缩放比。手动展示为默认，开启轮播后每屏90秒；隐藏页面冻结剩余时间。子屏跨屏链接保留对象参数，同步顶部按钮、地址及独立打开链接。无尚未实现的场景切换入口。

历史首版HTML的CSS/JS标记为restore-original-1；当前以各HTML中的资源版本为准。未新增构建框架或外部CDN。大屏只读取后端，目录写入在Gateway进行。

## 历史指标接入记录

2026-09-26 已批准指标接入：01五个CPU/GPU/内存/显存/温度槽位接单设备，GPU标题为SINGLE GPU，多设备每12个可见秒轮播，来源和逐点过期仍独立老化。02底部四槽换E2E P99、TTFT P95、TTFT占总延迟比例、TPOT P95，仍按所选单Endpoint；原延迟条保留占位但隐藏，不相加。CSS、卡数和布局不变，01/02相关JS的HTML缓存标记更新为approved-metrics-1。详见 `../../docs/approved-metrics-integration.md`；此前“硬件未接入”仅适用于本次五槽之外与03异常定位。

候选3（R2）：01及别名restored01.js缓存版本为approved-metrics-3。硬件槽保持三行，来源标记中文“演示 · 未验证”/“未验证”，原始来源与完整身份保留title。未改CSS文件；仅标签行局部inline-size包含与单行省略约束，避免长设备名参与网格固有宽度。02资源版本不变。

## 2026-10-10 部署视图与电视字阶

02 使用唯一 services LiveProvider，按现有 services 与 pd-groups 目录显示 P/D 分离组和合并推理服务；保留原组 ID 与 Endpoint 导航。合并推理仅表示单实例完整推理，不表示同服务混合模式。目录缺失时保留 Endpoint 原始观测并标记部署模式待确认。Router 只展示登记名称、数量和所选单 Endpoint 原始指标。正常模式的请求槽位负载、阶段与 KV 观测继续未接入；下面明确开启的 DEMO 模式补充独立模拟观测。

每个当前可见 P/D 卡片各有一条到组枢纽的 DOM 锚点分支，沿网格空隙走线；这是登记部署关系示意，非真实 KV 路由。P 的不完整末行右对齐，DOM 阅读顺序不变。02 renderer 提供可选 destroy()，每次替换 DOM 前及 pagehide 时断开 ResizeObserver、取消待执行帧并移除监听；隐藏页取消待执行绘制。暂停、动效关闭和 reduced-motion 保留静态关系。

01/02/04/05 服务处使用中文部署模式，05 每个依赖服务单独标记；未知不推测。01 仅门户嵌入时隐藏重复标题，登记统计保留。tv-legibility.css 以页面与 portal-bar 作用域放大正文、单位、状态和菜单；别名入口同步加载与资源版本。


## 完整五屏演示（2026-10-10）

直接打开 `/screen/?demo=1&screen=01`，或任一 `01.html` 至 `05.html?demo=1`。门户、独立打开、按钮导航与跨屏对象链接保留 `demo=1`。顶栏与页脚均标注 DEMO 演示数据 / 模拟场景；门户关键应用统计使用同一模拟业务集合。Gateway 仍是普通真实目录入口，不接收 DEMO 对象 ID。

`demo-data.js` 是仓库内持久、确定性的独立模拟快照，固定窗口为 2026-10-10 11:25–11:30 UTC+8；不调用 API、不写数据库、不依赖测试 route.fulfill。缺数据或 API 失败不会自动开启此模式。正常模式的 03 未接入、05 UNKNOWN 和过期来源语义继续保留；完成演示不等于完成真实监控接入。

模拟目录包含 2 集群、3 服务、3 业务、22 Endpoint。同一华东集群内 P/D 分离与合并推理服务并存，智能客户服务分别依赖这两种服务；同一服务 HYBRID 仍不支持。02 请求槽位占用按同一阶段 `sum(occupied)/sum(effective_capacity)` 计算，P/D 组展示两阶段最大值，合并服务使用自身实例槽位。阶段 tokens/s 是对应角色原始 Endpoint tokens/s 求和；GPU P95 和 KV 传输 P99 / 带宽是独立合成观测。登记连线始终不表示已验证 KV 路由。

03 模拟 GPU / NIC / Pod 三条活动资源异常，含身份、阈值、12 点趋势、证据与处置。04 默认仅展示活动异常服务及其业务影响；显式下钻正常服务时可查看正常模拟详情。05 五项业务 SLI 为独立业务入口观测，成功率 `100−错误率`，99.9% 目标下 Burn 为 `错误率/0.1%`，P99 不从 Endpoint 分位数相加。所有趋势末点与所示当前值一致；五屏 global、service、business、endpoint 数值各有独立统计范围，不能跨层相加。

`demo.css` 仅作用于 `body.demo-mode`。正常渲染器保持原质量判定。逐槽位范围、数值与验证见本批 evidence 目录中的 `demo-completeness.md`；静态资源版本为 `demo-complete-20261010`（本批未再修改的 screen01.css/restored02.css 保留 deployment-tv-20261010）。
