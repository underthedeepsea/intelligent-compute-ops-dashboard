# 正式 Gateway 整项服务录入设计

状态：实施合同；2026-10-09。episode：`gateway-service-entry-integration-v1`。本设计接入用户已确认的单页录入流程，保存到现有 Django 数据库；原型历史失败项和本地存储实现不作为复用代码。

## 页面与范围

`/gateway/?view=catalog` 在页内提供「直接录入」「批量导入」「已录入服务目录」。直接录入使用一张整项服务表单：环境 PRD/DR/STG/DEV、团队/业务、模型、是否 P/D、Router、P/D 多实例、K8s 集群、Namespace、LWS/Deployment、工作负载、地址引用、多配置 Node。团队、业务、模型、集群支持选择现有或同页新建。保存只发送一次整项请求。服务目录支持搜索、读取、整项编辑、配置导出；已有多个 P/D 组分别展示并保持身份。新建 COMBINED 至少一个 COMBINED 实例；SPLIT_PD 每个活跃组至少一个 P、一个 D，可选 Router；Router 属于明确组，符合现有关系模型。

字段不填人工 code、UUID、Pod 名、Pod UID、Node UID、观测时间。新配置 Node 仅填写节点名称/部署范围，界面标注「配置节点 · 未验证运行位置」，不会生成 RuntimeMember、图中实际 Pod/Node 或健康值。保留 API Key 管理外部引用入口及配置意图，不签发实际 Key。整项服务保存不修改已有 Key、授权或额外业务依赖。

总览及完整信息映射的结构、样式、动画保持原样；仅将其「配置当前对象」入口按对象归属路由至新编辑页。service/PD/Endpoint/Pod/Node 焦点可解析所属服务并打开对应组/实例；共享 Node 先选择已有成员所属 Endpoint；无法归属服务的 team/business/model/cluster 焦点继续原有辅助资源配置。旧按类型目录作为「基础资源配置」次入口保留，团队/业务/模型/集群可维护且新建内部代码自动生成；服务/PD/Endpoint转整项编辑，运行成员身份只读，避免旧入口重新暴露手工Pod/UID录入。新服务不经过分散 CRUD。监控 CSV 仍在监控数据管理。

## 数据模型与退休

Endpoint 新增 `namespace`(120，空默认)、`workload_kind`(LWS/Deployment/空)、`workload_ref`(160，空默认)、`configured_nodes`(JSON 字符串数组，默认空)。迁移只添加配置字段，绝不从 RuntimeMember 猜测并填充；历史未补录配置显示「未登记」。新配置 Namespace 校验 K8s label 规范；工作负载为明确名称；Node 数组去首尾空白、拒绝空值/重复，最多32项，每项≤160字符。新/修改实例要求 Namespace、部署方式、工作负载、地址引用完整；原有未补录实例可原样保留，通过 `unchanged` 身份引用绕过新增完整性要求，改动实例时补齐。

UUID 用 Django default；新 code 在服务器按类型前缀+UUID生成并进行唯一校验，既有 id/code 原样保留。临时 form_key/import_alias 只解析本次请求内引用，不入库、不作为观测身份。旧环境允许原环境内编辑，不迁移或强制改名为四个新选项。

删除已保存实例、组或切换模式均采用 `enabled=false` 退休。不物理删除，不修改/删除其 RuntimeMember、EngineBinding、PollState、TelemetrySnapshot 或外部来源映射；保留旧服务、组、集群、环境关系。存在任意历史成员/绑定的实例修改角色、组、集群时采用退休旧实例并新建替代实例；地址/配置字段编辑可保持身份。不得把旧 Endpoint 移到另一个集群导致其 RuntimeMember.clean 失败。新替代实例不会自动接管旧观测绑定。

必须同步修正 `PDGroup.clean`、`Endpoint.clean` 的退休合同：disabled PDGroup 可保留旧模式；disabled Endpoint 可保留旧 role/group 模式，但仍验证同环境、group.service 一致、RuntimeMember.cluster 与 Endpoint.cluster 一致。active PDGroup/Endpoint 继续严格验证当前模式，active Endpoint 不引用 disabled group。不全局跳过 disabled 对象的 full_clean。现有 `catalog.save` 在父修改后校验全部历史孩子，因此仅停用孩子不够；上述有限豁免是模式切换的必要前提。其他 FK/跨环境/身份规则保持。

服务自身停用若提供该动作，必须在同一事务退休活跃组/实例，保留业务关联与所有观测，不提供物理删除。退休对象在编辑读取和完整导出中显示只读历史，不随保存丢弃。当前拓扑与总览只使用原有 active 条件，不将配置 Node 注入实际运行映射。

## 原子写与并发

新增 `control/service_entry.py` 负责整项读取/校验/事务；HTTP 包装单独 `service_entry_views.py`。不要让前端循环调用现有逐资源 save；也不要将逐资源 save 的 parent 校验夹在模式切换中间。

读取编辑数据在单个 GET 的现有 repeatable-read/atomic 边界内返回服务、全部活跃与退休组/实例、现有业务关联、必要选项及各对象 version，附 `metadata_revision`。预期版本来自该快照，不能在保存前再读当前版本替换草稿版本。选项分页读取应通过同一快照校验 revision；不完整/过期选项不用于可编辑提交。

写事务首先以 `Revision.metadata=expected_metadata_revision` 条件 UPDATE 取得写入顺序并递增 metadata/view（失败回滚），再锁定/校验 service 与涉及对象 versions、实际成员集合和所有关联。全局 revision 捕捉旧 CRUD 新增子项、删除关系、同名选项变化等服务 version 没覆盖的修改；代价是无关目录修改也可能提示重新读取，当前规模接受。缺失 revision/expected_versions 为400；变化为409，返回对象类型/id/预期/当前版本和 revision，不自动覆盖。

对象更新采用 version 条件 UPDATE（事务内）；已变更对象 version递增一次，主 service每次整项编辑递增一次，新增对象版本1。关系变更递增对应 Business.version，保留其其他服务绑定；仅改变本服务所选业务关联。团队重新选择只改变关联：不重写现有 Business.team/owner、不牵连其 Key；同页新业务保存 owner/critical/watch_order 并全验证。已存在但停用的原关联可保留，只读提示；新增不得选择停用资源。KeyModelGrant 和其他服务绑定完全不参与替换。

事务顺序：预校验全部字段/引用→获得 revision写序→核对全部身份/版本/集合→建立同页新父资源→退休变更组/实例→更新服务模式/模型与新组/实例→增量业务关系→验证最终全部相关父子对象→匿名审计→返回完整已保存快照。所有影响在同一 `transaction.atomic`；任一字段/唯一性/关联/并发错误回滚全部（含revision与审计）。API审计不保存地址或外部Key原文。SQLite BUSY/LOCKED转换成可重读的结构化冲突/繁忙错误，绝不返回成功或自动重试未确认的创建。

## API

新增路由置于通用 `catalog/<collection>` 路由前，复用现有 envelope、错误码、CSRF与匿名direct合同；无新增账号/权限框架。

| 方法/路径（`/api/v1/service-entry` 前缀） | 合同 |
| --- | --- |
| GET `/services?environment_code=&cursor=&limit=` | limit≤100，已录入服务目录、分页游标，按环境过滤 |
| GET `/options?environment_code=` | 同环境父资源选项；分页或显式截断错误，revision返回 |
| GET `/services/<uuid>` | 单事务完整编辑快照；versions包括全部组/实例、被引用父对象与关系业务；历史只读数据 |
| POST `/services` | 创建整项，expected_metadata_revision、新service及refs、groups/endpoints；201完整快照 |
| PUT `/services/<uuid>` | 整项编辑，expected_metadata_revision + expected_versions；200保存快照 |
| GET `/templates/services.csv` | 全服务批量模板/示例下载，与监控模板分开 |
| POST `/imports/validate` | UTF-8 CSV字符串，解析/引用/业务/模式校验，返回规范计划、逐行错误、revision、摘要 |
| POST `/imports/apply` | 提交同一CSV、validate时revision与内容SHA256；重新解析/验证，在一个事务保存全批；任一失败全回滚 |
| GET `/services/<uuid>/export` | 完整JSON只读导出；全部配置、id/code/version、关系、退休与真实观测字段不遗漏；不含凭证 |

请求结构固定白名单：`service:{name,environment_code,deployment_mode,model_ref}`，`team_ref`、`business_refs:[ref,...]`、`remove_business_ids:[]`；ref恰好选择 `{id}` 或 `{create:{form_key,name,...}}`。business_refs允许同环境多业务，各业务所属团队必须符合该ref对应团队；旧跨团队额外业务依赖仍可原样保留，不能强制单团队重写。remove_business_ids只允许明确从读取快照中选定解绑的业务，不将遗漏关系解释为删除。groups使用 `{id,unchanged:true}` 保留原组，或 `{id?,form_key?,name,endpoints:[...]}`；endpoint为 `{id?,form_key?,name,role,cluster_ref,namespace,workload_kind,workload_ref,address_ref,configured_nodes}` 或 `{id,unchanged:true}`。COMBINED endpoints放在顶层，SPLIT_PD endpoints放各组。新对象不允许客户端id/code；existing id必须来自快照且属于本service。删除已有对象通过显式 `retire_ids`，不把遗漏集合解释为删除；服务器要求每个原活跃对象恰好保留、修改或退休一次，防止UI隐藏多个group时丢项。历史项由服务器保存，客户端不能编辑或复活。

`expected_versions` 键格式为复数 collection（如 `services:uuid`、`endpoints:uuid`），version必须为正整数；必要键集合由快照合同确定，缺项报错。允许合并同环境options父资源版本map；其他服务/组/实例的额外键拒绝，不能接受客户端未知对象。业务选择变更明确提交旧/新业务，保留该service额外业务关联；只对当前表单原选业务的关系增量调整。若旧service有多个业务，UI显示并维护多选列表，不能任意挑一个后清空其他。与额外业务关联、Key授权有关的对象只校验读取版本，不替换整个关系集合。

## CSV 合同

采用一行一实例、同 `environment_code + service_alias` 为一整项服务，重复服务/父信息必须完全相同；SPLIT_PD同 `group_alias` 聚合同组。COMBINED不允许group列，至少一行；P/D每组明确P/D行及可选Router。此次批量创建，不按名称覆盖已保存服务；已有整项编辑走目录与版本接口。

严格列：`environment_code,service_alias,service_name,deployment_mode,team_id,team_name,team_alias,business_id,business_name,business_alias,business_owner,business_critical,business_watch_order,model_id,model_name,model_alias,cluster_id,cluster_name,cluster_alias,cluster_region,group_alias,group_name,endpoint_alias,endpoint_name,role,namespace,workload_kind,workload_ref,address_ref,configured_nodes`。配置 Node 用JSON字符串数组，标准CSV quoting。template下载提供列说明及唯一显式示例；示例不生成UUID、不偷偷预填生产数据。

父资源解析每种只允许一条引用路径：ID来自已有目录；未提供ID/alias时以同环境精确唯一name匹配，0个报未找到、多个报歧义；alias表示同批新建，name及必填属性须一致。新建父资源不得与同环境已有同名对象冲突，提示改用ID/唯一名称。shared alias全文件按类型+环境唯一；service_alias、group_alias、endpoint_alias分别限定环境、服务、组/服务作用域；同alias重复实例拒绝，同group重复配置不一致拒绝。跨环境同文本alias是不同引用，绝不fallback跨环境匹配。名称用NFC+首尾空白标准化、大小写保持，禁止模糊/前缀匹配。

alias语法 `[A-Za-z][A-Za-z0-9_-]{0,63}`，拒绝UUID以及保留词 `id,uuid,code,latest,null,none,auto,system`（忽略大小写）；不会同时将alias当名称或id解析。已有关联的 `_id` 可以填系统UUID，新对象UUID/code输入和任意采样字段（含隐藏未知列）拒绝。全新后端使用标准库csv严格解析，不复制原型parser/UUID cache/localStorage；重复validate没有数据库写入/UUID分配，apply重新解析后才生成实体身份。

边界：CSV≤2MiB，最多1000实例行、100服务、每服务≤100实例、≤20组、每实例≤32配置Node，同页新父对象总计≤300；JSON请求≤2MiB，超限明确拒绝不截断。错误含行/列/对象/错误码；validate发现问题不返回可apply计划。apply摘要变化或revision变化409，保留文本与行修正草稿，重新validate后才能应用。界面按服务/组显示预览，并允许修正单行字段后重新validate；修正不继承旧token/hash。

导出分两个用途：整项只读JSON完整包含真实历史身份；配置CSV仅含可重新创建配置及明确的现有目录引用，文件/按钮标明「配置复制模板，不含观测，不用于覆盖已有服务」。不可将只读完整导出直接当可写CSV，避免人工UID入口。配置复制CSV的固定列仅支持恰好一个启用业务关联；无业务或多个业务时返回 `EXPORT_REQUIRES_SINGLE_BUSINESS`，引导完整JSON查看并整项编辑，不静默丢弃关联。

## 生命周期与发布

### 用户追加的显示范围

同一交付恢复正式02中央P/D登记关联的连线动画，以原`02-PD运行诊断.html`为视觉参考。线条只展示已登记的P/D关系，不能暗示真实KV传输、吞吐或实时监控；未接入KV指标仍为`—`。动效必须支持暂停、关闭/reduced-motion和静态关系可读性，不增加持续卡片扫光或粒子。

恢复Gateway总览真正的图形关联区：使用现有Demo拓扑模块与正式后端topology真实关系，提供对象选择器；目录非空时默认选择启用服务，若无服务则启用模型，之后可选其他合法起点。侧栏资源映射和`?view=mapping`直达也采用同一默认规则，空目录才显示录入提示。原overview只剩chain类型卡和完整映射表，且focusId默认空导致非空目录仍显示选择提示；必须修复该入口状态。服务目录和整项编辑提供「查看此服务关系图」，传明确service focus。恢复图形区沿用原拓扑视觉，不重构既有完整信息表格，不接入推导健康。

五屏portal嵌入时隐藏iframe页面内部重复`.app-bar`（品牌、页签、按钮），保留外层portal导航及02页面标题。独立打开保留内部app-bar。通过明确embed参数/上下文标记限定样式；不能全局删除header，也不能让隐藏后的标题/暂停控制无可用路径。视觉代理与录入代理分文件；app.js/index.html如涉及Gateway入口由协调者合并，不能同时修改。

正式入口维持controller `confirmLeave/destroy`；新草稿、编辑、CSV修正均纳入dirty检测。新建父资源、模式切换、删组/实例/Node、切环境都检测未保存输入；模式分支切换可保存内存草稿但只有当前活跃分支提交，已存历史采用显式退休。请求seq/epoch阻止旧响应落到新页面，destroy清理监听；保存时禁止重复点击、导航/刷新不销毁正在提交的controller。保存成功直接采用服务器返回快照和版本，再刷新目录；刷新失败显示「保存成功，目录刷新失败」，禁重发创建，允许核对已返回UUID。网络响应丢失显示「结果未知」，不自动重发；按目录核对再明确新建。

相关新CSS仅作用 `.service-entry`；index中的相关CSS/JS同步`v=service-entry-v1`，旧映射资源版本/样式无需改动。预览使用全新/tmp数据库和未占用端口，不写原backend SQLite、8767/8768或原型。保留匿名direct/CSRF、env完整性与upstream来源状态。

新增0006迁移必须写升级说明与执行验证；当前v0.4.0待发布、镜像标识保持v0.4，不发布新版本。升级沿用已确认停所有写者→旧版本镜像核验备份→唯一新迁移Job→核验schema→退出全部维护进程→匹配API/Web恢复。`deploy/README.md` NAS备份Python片段逐字保护，不修改其校验或备份行为。现场NAS/巡检/K8s仍未验收，不将本地检查称为生产验证。

## 用户追加视觉修订与实际接口勘误

用户随后要求移除02页面重复标题/巡播/登记组数整行及底部来源状态栏，扩大中央动效并增加分支。当前02嵌入模式隐藏该整行，独立模式保留紧凑页面标题；中央宽320px、6条固定阶段关系示意曲线，不表示具体实例配对或实际KV路由。实例来源与采样窗口保留；阶段汇总、GPU、KV缺失文案逐项明确，不生成汇总数值。其他页面嵌入app-bar隐藏规则保留。

Gateway顶部明确标注目录可用环境；服务表单标注服务所属环境。旧演示local保持原值、显示本地演示，不自动改成DEV。新服务保存后同源目录与屏幕环境及metadata revision应一致。主Key新建和helper新建内部code均服务器自动生成，既有identity保留。当前用户要求把原定medium任务全部改Sol6.1 high执行，预算与候选编号不变。
