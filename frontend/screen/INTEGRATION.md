# 原布局统一接入合同

本次沿用根目录原五屏的 DOM/class、布局比例、主题、字体与面板空间。原目录只作参考，不加载原 demo 脚本，不连接 demo_server，不在错误时回退固定数据。唯一数据入口是同源 `/api/v1/`；当前由 `ControlAPI.ensureAccess()` 读取直接访问元数据与 CSRF token，不建立登录会话。

## 启动与共享接口

各 HTML 顺序加载 `api.js`、`live-provider.js`、专属 `restoredXX.js`、`screens.js`。01另加载原DOM模板 `overview-dom.js`。共有容器为 `.screen`、`#app-header`、`#app`、`#app-footer`。

注册形式为 `window.ScreenRenderers['02'] = { render(data,ctx), bind(root,ctx), tick(ctx) }`。render返回HTML，bind在每次渲染后绑定可见控件，tick每个可见秒调用一次。tick在暂停时仍调用，renderer自行冻结轮播；bootstrap处理60秒人工暂停到期，隐藏页冻结人工暂停时间。

ctx提供 `e`、`m`、`ageState`、`endpointState`、`stateLabel`、`tag`、`source`、`link(screen,id,label)`、`navigate(screen,id,extra)`、`refresh()`、`pause(bool)`。`ctx.data`为原始最新投影，`ctx.now`为当前毫秒，`ctx.state`为持久对象，保留selected、endpoint、paused、cycle、manualUntil及专属状态字段。

`ctx.catalog`按collection名提供clusters、services、models、businesses、endpoints、pd-groups、runtime-members；仅GET访问已有catalog接口，按100条游标分页并排除disabled对象。失败保留已知目录并标记目录补充不可用，不将目录身份扩展成运行健康。目录元数据不得覆盖Endpoint原始ID、来源或窗口。

## 数据与错误

每屏只有一个LiveProvider轮询对应overview / pd-groups / infrastructure / services / critical-apps投影。只有校验通过且revision递增的响应替换有效帧；旧响应、无效响应、网络错误保留旧帧，通信错误单独提示。来源年龄由原source_window和max_age_seconds判断；浏览器收到响应不刷新来源年龄。只在FRESH且巡检transport=OK时显示Endpoint原始状态。

目录来源按已读取实体origin显示（单一来源/混合/未知），观测origin按原始observation显示，两者分离。当前DEMO目录、UNVERIFIED观测均保持可见，来源过期状态不会抹去原始来源标记。未知采用中性色，不作good。01保留原三栏与地图空间，地域、硬件和全局聚合未接入留空；05保留原固定w-card布局和watch_order，SLI、趋势和健康统计空值，真实配置服务依赖可下钻04。配置依赖不代表业务实际影响。02/03/04边界由各专属renderer保持。

## 门户

portal保留原1920×1080 iframe整体缩放，按stage宽高取较小缩放比。手动展示为默认，开启轮播后每屏90秒；隐藏页面冻结剩余时间。子屏跨屏链接保留对象参数，同步顶部按钮、地址及独立打开链接。无尚未实现的场景切换入口。

历史首版HTML的CSS/JS标记为restore-original-1；当前以各HTML中的资源版本为准。未新增构建框架或外部CDN。大屏只读取后端，目录写入在Gateway进行。

## 历史指标接入记录

2026-09-26 已批准指标接入：01五个CPU/GPU/内存/显存/温度槽位接单设备，GPU标题为SINGLE GPU，多设备每12个可见秒轮播，来源和逐点过期仍独立老化。02底部四槽换E2E P99、TTFT P95、TTFT占总延迟比例、TPOT P95，仍按所选单Endpoint；原延迟条保留占位但隐藏，不相加。CSS、卡数和布局不变，01/02相关JS的HTML缓存标记更新为approved-metrics-1。详见 `../../docs/approved-metrics-integration.md`；此前“硬件未接入”仅适用于本次五槽之外与03异常定位。

候选3（R2）：01及别名restored01.js缓存版本为approved-metrics-3。硬件槽保持三行，来源标记中文“演示 · 未验证”/“未验证”，原始来源与完整身份保留title。未改CSS文件；仅标签行局部inline-size包含与单行省略约束，避免长设备名参与网格固有宽度。02资源版本不变。
