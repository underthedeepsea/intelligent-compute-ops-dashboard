# v0.4.0 直接访问设计

用户明确取消本项目账号密码体系，后期接入其他生产系统；当前不设计鉴权。Gateway、观测中心和五屏直接打开，生产 HTTP 与本地预览使用同一访问合同。

所有目录、关系、拓扑、监控和审计 API 匿名直接读写全部已登记环境。GET `/api/v1/session` 是兼容路径上的访问元数据：`access_mode:"direct"`、`can_write:true`、`csrf_token`、`environments`、`data_mode`，无 fake user、authenticated、roles 或 username。环境候选包含全部实体的环境代码（含停用记录）以及 PRD、DR、STG、DEV；候选不是授权白名单。旧 session cookie 不影响访问。

移除 Session、Authentication、LocalSessionGuard 中间件以及 login/logout/local 与公开 admin 路由。历史 auth/contenttypes/sessions/admin 表及迁移保留，LegacyAdminConfig 仅保留迁移图，不加载管理站或注册要求身份中间件的管理站检查；不删除旧身份或历史审计。旧 bootstrap 命令明确报退休错误，不新建身份。

CSRF 同源请求校验、Host 检查、expected_version、事务、关联关系、不可改变已有实体环境、跨环境关系一致性、generation 失效、脱敏投影仍执行。HTTP审计 actor 为 `anonymous`；CLI `--actor` 是可选自由操作来源，默认 `cli-import`，非个人身份或权限凭据。其值须为非空且不超过150字符。导入尺寸、幂等、dry-run及DEMO双开关仍保留。

默认部署为 HTTP Web Pod IP:8080、单副本 API、NAS SQLite DELETE/FULL，迁移 Job 只 migrate，无账户初始化、TLS/Ingress前提。所有推荐镜像为0.4.0；AMD64现场构建、NAS/网络/恢复验收仍需现场完成。本次不上传镜像或自动构建。

历史 `docs/design.md`、`docs/implementation.md` 的登录、role、scope、admin条款由本合同取代，原文及历史 evidence 保持。数据是演示或CSV快照；轮播不是实时监控。
