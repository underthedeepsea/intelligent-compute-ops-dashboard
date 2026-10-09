# Docker 与 NAS 部署设计 v1

本需求独立于历史产品/界面 episode。Kubernetes 默认使用 NAS 上的 SQLite，保留 PostgreSQL 为可选路线。没有连接真实集群或巡检，也不改变现有 UI、演示数据库。

API 与 Web 由同一允许清单上下文构建为两个镜像；API 带管理代码与 CSV 模板，Web 带前端及构建时 collectstatic 产物。镜像不可变，非 root，运行根文件系统只读，临时文件进入 /tmp。TLS 在可信入口终止，Web 保留入口协议，仅无入口协议时使用本地实际协议；入口必须覆盖来自客户端的转发头。

数据库选择与 CONTROL_LOCAL 解耦。未指定引擎的历史行为保持：LOCAL 使用 SQLite，其他环境 PostgreSQL。显式 sqlite 使用 DELETE 回滚日志、FULL 同步、30 秒锁等待。生产 SQLite 不启用 DEBUG、演示导入或免密。

NAS PV 使用 NFS、RWX、Retain、空 StorageClass、显式 PVC 绑定，挂载完整 /data。RWX 仅描述存储能力，不许可应用多写者。默认 API 一副本、一个 sync worker/线程、Recreate；不启用巡检 worker、不允许 HPA。迁移、管理员创建、授权、备份恢复均在 API 完全退出后的维护窗口串行运行。Pod 的 UID/GID 为 10001，由 NAS 管理员预建可写目录；root_squash 下禁止依赖 root initContainer chown。

NFS 锁与持久性取决于 NAS、客户端、网络和故障恢复行为；单写者与 DELETE/FULL 是约束而非可靠性保证。上线前必须在目标 NAS 做验收。本方案不声称生产就绪。

参考：[Django 5.2 SQLite OPTIONS](https://docs.djangoproject.com/en/5.2/ref/databases/#setting-pragma-options)、[SQLite WAL](https://sqlite.org/wal.html)、[网络文件系统警示](https://sqlite.org/useovernet.html)、[Kubernetes PV](https://kubernetes.io/docs/concepts/storage/persistent-volumes/)。WAL 不适用于网络文件系统；网络锁失效仍可能造成数据损坏。
