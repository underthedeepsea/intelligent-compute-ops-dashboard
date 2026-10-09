# 发布与回滚检查单

当前仅准备本地实现与验证。未获真实巡检地址、身份和凭证，M0/M5 真实验收未通过；此清单不代表批准上线，未勾选项不得以页面可打开替代。

## 当前部署合同

当前版本按 [HTTP部署说明](../deploy/README.md#纯-httppod-直连无-ingress) 部署：HTTP Web Pod IP:8080，同源API，NAS PV/PVC中的SQLite，单副本、单写者、串行备份/迁移；无需Ingress或本项目账号体系。应用仍需随机Django应用密钥、Host和HTTP origin，保留CSRF、版本与关联校验。巡检尚未接通时通过手动CSV快照演示，默认不启动取数worker。

从旧版升级先停止所有写者，使用旧版本镜像验证并备份数据库，唯一迁移Job完成并退出后恢复匹配的API/Web。不得删库解决身份提示，不执行已退休的bootstrap_access。实际操作与生产清单以当前deploy/README.md和docs/deployment-production-checklist.md为准。

下面保留最初巡检集成的历史检查与证据。其PostgreSQL、HTTPS、角色和账号步骤属于旧设计，当前部署不再采用；来源验证、脱敏、原始指标及真实联调缺口仍适用。

## 历史发布前门禁

- [ ] 冻结发布源码、依赖锁、数据库迁移、API schema 和静态资源版本；保存执行命令、退出码及证据路径。
- [ ] 使用独立 PostgreSQL database/owner；禁止共享巡检表、跨库查询或导入巡检 ORM。SQLite 仅用于显式隔离本地开发。
- [ ] 配置 HTTPS 同源入口、真实会话密钥、允许的 Host 和受控静态目录；确认浏览器只访问统一后端，不持有巡检 token。
- [ ] 核验 `catalog_admin`、`operator`、`screen_viewer`、`auditor` 的服务端权限和环境范围；普通用户不能修改 Provider、Secret 引用与权限。电视不暴露 Key、地址及敏感审计内容。
- [ ] 真实巡检入口有已验证的只读身份：仅授权必要 GET；拒绝上报、触发巡检、AI 对话和风险处置。客户端方法限制不能代替上游身份权限。
- [ ] 核对真实部署版本、完整复合身份、采集来源、source allowlist、窗口与脱敏 recorded 响应；通过真实验收后才开启来源确认。
- [ ] 确认正式路由不能访问 `/demo/`、旧演示接口或 demo JS；生产导入演示数据被拒绝，故障时不回退演示值。
- [ ] 核验大屏监控值直接对应巡检支持字段、单位、统计口径和样本窗口；未经用户确认，不做跨 Endpoint 汇总、平均、最大值或业务指标推算。需综合计算时先取得用户决策。目录/绑定覆盖计数应明确标为元数据或接入覆盖，不能冒充监控值。
- [ ] 完成目录冲突/越权、绑定变更清空、断流过期、来源拒绝、五屏空态/恢复、暂停/静态可读性、容量及回滚证据；明确仍未支持的指标。

## 发布顺序

1. 备份统一后端主数据，记录可恢复时间点和数据库迁移状态。巡检平台保持独立发布。
2. 先发布向后兼容迁移与 API，再启动独立取数 worker，最后发布匹配契约的前端。API 进程不得自行启动轮询线程。
3. 显式执行并检查数据库迁移，再校验 `/healthz` 和 `/readyz`；当前 `/readyz` 仅验证数据库连接，不验证迁移就绪。上游不可达应反映在集成状态，而不是伪造健康或使本地目录不可用。
4. 从一个业务、服务、PD 和已验证绑定开始灰度，比对目录、原始数值、source window、脱敏、上下游关系与下钻身份。
5. 仅在真实链路、权限、故障和容量门禁都有证据后扩大范围；没有采集的能力继续显示未接入。

实际命令见 [项目 README](../README.md) 与 [部署说明](../deploy/README.md)。本地使用 `CONTROL_LOCAL=1 .venv/bin/python backend/manage.py`；已落地命令为 `migrate`、`bootstrap_access`、`import_gateway_catalog`、`poll_inspection`（可加 `--once`）和 `test tests --verbosity 1`。生产 Compose 使用独立 PostgreSQL，先迁移与收集静态资源，再启动 API、单例 worker、Web，并置于 HTTPS 入口后。设计文档中的命令轮廓不作为已实现能力的证明。

当前[第三轮定向复查](../evidence/review-3.md) 为 LOCAL_TARGETED_PASS，B1/B2 在本地审查范围内闭合：独立后端 3 项、前端 8 项及浏览器 4 项检查通过，88 个冻结文件哈希一致。独立 Final Audit 正在进行，本地定向通过不表示生产验收通过。首轮 8 项阻塞与第二轮 `CHANGES REQUIRED` 均保留，见 [首轮审查](../evidence/review-1.md)、[第二轮复查](../evidence/review-2.md)。用户追加授权的修复证据为 [第三候选后端验证](../evidence/backend-repair3-verification.md)（实际 Reader + worker 等 26 项定向测试通过）和 [第三候选前端报告](../evidence/frontend-candidate3-report.md)（04 单 Endpoint 完整帧、12 秒轮播、精确选择暂停且继续老化；4 项浏览器检查、8 项相关单测通过，合成数据）。

第二候选 SQLite 40 个方法中 38 通过、2 项 PostgreSQL 专用跳过；PostgreSQL 40 项通过且 runner/清理退出 0，仍仅作为 [第二候选历史验证](../evidence/backend-repair2-verification.md)。第三候选后端没有数据库/事务变更，因此未重复 PostgreSQL，不能将历史结果标为本轮重跑。真实 M0/M5、24 小时稳定运行、100 绑定容量压测、完整 Compose build/up/TLS 及生产回滚演练保持未验收。

目录导入尚不支持原 JS grants 和 business bindings，必须另行维护并核对这些关系；目录记录导入成功不能代表完整旧关系图迁移完成。当前监控投影保留各 Endpoint 原始状态，不计算服务/业务综合严重度、替代实例数量或推算影响标记。

## 立即阻断或回滚的条件

出现 demo 冒充真实、错误实体映射/重复统计、上游写权限可达、电视或跨环境数据泄漏时立即停止扩大范围并回滚。绑定变更沿用旧遥测、过期值保持健康、数据库迁移异常或契约不兼容同样阻断发布。

先停止取数 worker，保留日志和失败证据，再恢复匹配的上一正式 API 与前端。保持数据库向后兼容，不自动覆盖发布后新增的目录修改。必须恢复备份时进入维护窗口并明确可丢失的变更范围；没有上一正式版本时进入维护或只读目录模式，不启动静态演示替代生产。

回滚后再次确认目录可读、权限有效、旧遥测未被标新鲜、正式入口仍拒绝 demo；记录失败原因、实际版本、恢复点及后续修复项。关闭统一后端 provider/worker 不得修改巡检平台数据或调度。
