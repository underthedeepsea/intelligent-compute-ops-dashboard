# Docker 与 NAS 部署实施计划 v1

1. 冻结基线与独立预算：两批候选、两批集中审查；Sol61 medium 设计实现，父协调者做独立审查与实际构建。
2. 增加数据库引擎选择与定点测试：生产安全默认、非法引擎拒绝、临时库真实 PRAGMA 验证；不读取原有 SQLite。
3. 构建 API/Web target、允许清单、任意工作目录可用的 build/push 脚本；Compose 使用封装前端镜像，PostgreSQL 路线保留。
4. 提供独立基础/迁移 Kustomization、NAS PV/PVC、安全上下文、探针、资源、TLS 与 Secret 示例；所有占位符须由部署者替换。
5. 文档完整描述首次安装、停机升级、单次维护 Job、备份恢复与 NAS 验收；迁移不放入应用入口，不自动运行。
6. 验证限定为 Python 定点测试、shell 语法、离线 Kustomize/schema、真实 Docker 构建与隔离容器检查。环境不可用记录限制，不连真实 K8s。集中 review 后必要修复计入第二候选。
