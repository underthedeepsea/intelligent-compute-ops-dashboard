# 整项服务接入实施与验收

状态：候选1独立审查为CHANGES_REQUIRED；候选2已完成全部3项P2修复与定点验收，冻结等待Review 2，尚未发布。依赖 `service-entry-integration-design.md`；episode预算为2候选、2审查、1preflight，不重开原型或no-built-in-auth合同。

## 实施顺序

1. 锁定当前source/protected基线；本次preflight仅读产品源码。补Endpoint配置字段和0006迁移，有限修正退休mode校验。先以历史多组+RuntimeMember/EngineBinding夹具验证模式切换、cluster替代不会损坏历史身份。
2. 新service_entry领域模块：完整快照、refs与边界验证、全局revision CAS、对象version和原子保存、增量业务关联、匿名审计。HTTP wrapper接入既有CSRF/envelope。验证故障回滚和实际SQLite并发，旧CRUD写入也能导致bundle冲突。
3. 新后端CSV parser/模板，validate无写、apply全批atomic、reserved alias与名称歧义；配置复制CSV与完整JSON导出。禁止复用旧原型持久层/parser。
4. 正式catalog入口挂载新service controller与CSS，保留原helper资源配置；三入口、现有/新父资源、分组多实例、配置Node、目录编辑、批量逐行修正、dirty/epoch与保存后刷新处理。app.js仅调整挂载和焦点路由，映射HTML/CSS保持。
5. 全新临时数据库迁移并运行本地服务，真实浏览器完成直接保存→刷新读取→目录整项修改→CSV validate/apply→映射查看，拍实际页面；证明CSRF、配置节点非观测和新资源版本。执行有针对性的旧映射/匿名回归，再集中只读review；剩余预算允许一次集中修复及定点复查。
6. 更新使用/API/升级文档与实施状态，核对278 protected/原型/历史DB、NAS备份片段原文；保留v0.4镜像标记，不部署生产。交付真实预览URL、检查证据、局限。

## scope_files

允许候选改动/新增（实施开始前协调者冻结到episode范围）：

| 文件 | 修改目的 |
| --- | --- |
| backend/control/models.py | Endpoint配置与退休有限校验 |
| backend/control/migrations/0006_endpoint_deployment_configuration.py | 可逆仅字段迁移，无历史观测回填 |
| backend/control/service_entry.py | 读取/验证/atomic业务逻辑 |
| backend/control/service_entry_csv.py | 严格CSV、模板、validate/apply计划 |
| backend/control/service_entry_views.py | 新HTTP入口、limits与错误 |
| backend/config/urls.py | 明确路由，优先于通用catalog |
| backend/tests/test_service_entry.py | 核心关系/退休/atomic/version/并发 |
| backend/tests/test_service_entry_csv.py | 全批解析与导出/边界 |
| frontend/gateway/service-entry.js | 单页表单、目录、批量、生命周期 |
| frontend/gateway/service-entry.css | scope限定的录入视觉 |
| frontend/gateway/catalog-entry.js | 保留helper入口并提供必要focus接入 |
| frontend/gateway/app.js | mount/destroy、route/focus最小接入 |
| frontend/gateway/index.html | 新资源与同步版本 |
| frontend/gateway/tests/service-entry.test.cjs | 序列化/dirty/结果未知等状态验证 |
| frontend/gateway/tests/service-entry-browser.cjs | 真后端浏览器验收 |
| contracts/frontend-api.md | 追加service-entry契约，不改旧合同 |
| docs/catalog-entry.md | 当前操作说明、移除过期身份限制文字 |
| docs/service-entry-integration-design.md | 冻结设计及有证据的必要勘误 |
| docs/service-entry-integration-implementation.md | 实际实施/验收状态 |
| README.md、deploy/README.md | 新schema升级/资源版本说明；备份代码逐字保护 |

用户追加显示范围由独立视觉代理承接：`frontend/screen/portal.js`的embed参数、`screens.js`/`restored02.js`的embed状态与P/D关系连线、`restored02.css`/`screen02-tv.css`的作用域样式、相关02/别名HTML资源版本及`frontend/screen/tests/service-entry-visual-browser.cjs`。具体最小文件由视觉代理取证后冻结；本设计代理不改产品。Gateway「查看关联关系图」入口涉及`app.js/index.html`时由协调者独占合并，或在单独视觉模块提供挂载，不与录入作者同时修改。动画只能表示配置关系；KV未接入保持`—`。新增显示范围不重开旧原型预算。

`.codex/cost-aware/gateway-service-entry-integration-v1/`仅预算、路由、候选和审查证据；不扩展其他产品范围。不修改demo、prototype、overview-mapping、demo-topology、callflow原样式/布局、认证合同、上游、deploy镜像tag。若未来确定必须改projection/topology/monitoring，先说明具体必要性并更新冻结范围，不顺手做映射重构。

## 验收矩阵

| ID | 输入/操作 | 必须断言 |
| --- | --- | --- |
| S01 | 新建COMBINED；已有父资源/同页新建父资源 | 一次请求、真实DB保存，UUID/code服务器生成，重启/刷新仍完整 |
| S02 | 两PD组、各多P/D、可选Router | group/endpoint身份独立，读/改/导出不合并多组 |
| S03 | 多配置Node、LWS/Deployment | 数组/Namespace/工作负载完整往返；不创建成员/观测/健康 |
| S04 | 历史RuntimeMember、EngineBinding、Telemetry关联切换模式/删实例 | 旧group/endpoint退休；成员/binding全部字段、身份、环境关系不变；父full_clean通过 |
| S05 | 有历史实例换集群/组/角色 | 旧实例退休，新实例新身份；旧成员仍关联旧集群；无自动重绑 |
| S06 | 旧缺配置、旧环境、额外业务关联、Key授权 | 未改实例可保留；主动修改补全；全部旧合法关联/KeyModelGrant不被清空 |
| S07 | 最后一实例字段错/唯一约束错/关系跨环境 | 整批/整项0写入，审计/revision一起回滚 |
| S08 | bundle读取后旧CRUD改child、新增group/Endpoint、改business binding | 409不覆盖；details定位冲突；草稿保持；不复用新读version |
| S09 | 两SQLite连接并发、同version两写者 | 至多一个成功，另一个结构化冲突/繁忙；无部分保存/500 |
| S10 | CSRF缺失/伪造、新API匿名direct | CSRF拒绝；有效匿名可写；无账号登录；unknown/采样字段拒绝 |
| C01 | 模板下载→100以内服务有效批次validate/apply | validate数据库完全不变；一次apply原子保存；字段/refs正确 |
| C02 | ID/唯一名称/同批alias；重复/歧义/保留词/跨环境 | 明确逐行错误；不生成UUID cache；不fallback别名或跨环境 |
| C03 | 重复validate、修正后apply旧hash、校验后目录变化、apply最后一行失败 | 不分配身份；过期计划拒绝；全批0写入，草稿仍在 |
| C04 | quoting/BOM/逗号换行/非法UTF-8/重复未知header/超限/UUID采样列 | 标准CSV正确；非法拒绝不截断；每条限额覆盖边界 |
| E01 | 全配置、退休、真实UID的完整JSON导出 | 字段/计数/关系齐全；无凭证；配置CSV清楚标注非完整观测导出 |
| U01 | 直接录入、模式切换、删Node/实例、切环境、后退/刷新/navigation | dirty保护、取消保留输入；保存锁防重入；异步旧结果不污染 |
| U02 | 保存成功但目录刷新失败；HTTP响应丢失 | 成功UUID留存，不重复POST；结果未知明确核对目录 |
| U03 | 新页长名称、多个PD、批量逐行修正、Node增删 | 真实浏览器无溢出/控制台错误；用户能直接完成录入与编辑 |
| U04 | 总览和完整映射同夹具前后画面 | 样式/结构保持；实际观测仍可读；配置Node不伪装观测 |
| D01 | 全新DB与旧数据copy迁移 | 0006生效，现有members/bindings计数及字段保持；不接原DB |
| D02 | 静态资源、protected、NAS备份 | 浏览器加载service-entry-v1；保护文件hash无变化；备份片段逐字一致；v0.4标记保持 |
| V01 | 02中央P/D关联动画实际播放片段、暂停/关闭/reduced-motion | 登记关系连线可见，暂停与静态仍可读；KV未接入仍`—`，不表述实时传输 |
| V02 | 五屏portal嵌入02与独立打开/别名页 | 嵌入只保留外层导航和02标题，无重复app-bar；独立页内部品牌/页签/按钮正常；可用暂停路径 |
| V03 | Gateway总览/完整映射发现并打开关联关系图 | 清楚可发现的入口、正确focus；现有表格/完整信息映射样式不变 |

测试用自有/tmp数据库和空闲端口，不能写原8767/8768库。历史关系和并发使用真正Django/SQLite夹具，不以纯mock代替；浏览器需要完整真实保存链路，不能只证明DOM存在。现有充分回归不无意义重复整套，只执行受影响catalog/direct/mapping与新增合同。review至少独立检查退休parent验证、global revision对象版本、批量source→sink和dirty lifecycle。

## 当前证据

preflight见 `.codex/cost-aware/gateway-service-entry-integration-v1/evidence/preflight-001.md`。计划文档本身不表示实现/测试通过；发布镜像未构建或发布，真实NAS/巡检/生产联调仍保留原缺口。

## 候选1实际完成记录（待集中审查）

后端以真实文件SQLite运行54项相关检查，53通过、1项历史PostgreSQL专用跳过；后续CSV错误列定位14项通过。0006旧数据库副本迁移保留members、bindings、telemetry、poll、业务关系与授权逐字段一致。新批量parser不复用原型cache。高档接手时保留原始source、失败夹具日志与修正后输出；medium最初共享内存并发失败仅收到原作者消息说明，原工具输出未找到，不将其描述为已归档证据。

视觉完成v1后按用户追加修订由Sol6.1 high完成v2：中央320px/6阶段曲线、02去重复标题/底来源栏、实例来源窗口保留；播放/暂停/off/reduced-motion/隐藏/空侧/密集卡片实测。Gateway前端已完成匹配最终high后端的完整真实浏览器闭环与定点边界验收，11次真实写请求、22项前端单测、8次资源字节核对、14张截图，错误0；原始中间结果均保留。证据分别见episode的backend-result-high.md、visual-high-result.md和后续frontend-result-high.md。

相关设计实际接口勘误及helper收窄均在design当前段记录；旧冻结文件原件保存在episode evidence/pre-errata-design，预算不变。未发布生产镜像，未执行实际AMD64/NAS/巡检验收。


## Review 1 与最后候选2

Review 1在完整候选1快照上一次收齐3项P2：已解除业务关系在下一次编辑中被重新启用、零业务服务提交空team_ref、并发切环境旧目录响应覆盖新环境。均属既有关系保留和请求生命周期合同；后端、CSV、历史身份和视觉范围没有新增阻塞。候选1冻结与审查原件保留。

候选2仅修前端hydrate/bundle的活动关联与可选团队语义，以及目录请求序列、固定分页环境、旧结果/错误和destroy失效；同步HTML缓存标记并执行对应正向保留和真实HTTP浏览器往返。复用原视觉/后端验收，不开启新preflight。预算累计2/2候选，Review 1/2；候选2完成后只剩一次集中定点Review 2。


候选2实际验收：16项单测、2项语法检查通过；8770隔离库真实浏览器8次成功写入及2次预期拒绝，解除后再次改名仍解除、disabled业务实体活跃关联保留、零业务无团队保存往返、业务团队校验及DEV/PRD响应倒序通过。页面和控制台错误0，service-entry.js v2字节匹配。278保护文件未变。候选1后端、CSV、完整链路与视觉证据复用。此段只记录已执行验收，不表示Review 2已通过或发布已完成。
