# 本地离线演示数据

从项目根目录执行：

```sh
.venv/bin/python demo/local_preview/seed.py
```

脚本只写本项目既有 `backend/local.sqlite3` 的 `local` 环境；不启动、停止或连接服务。写前用 SQLite backup 生成独立临时目录中的 `before-demo.sqlite3`，输出备份路径及插入统计。实体 code 使用 `local-preview-demo-v1` 命名空间，名称含 `【演示】`，origin 为 `DEMO`。重复运行保留既有数据，不重复建目录或快照，也不删除任何数据。既有用户名、用户组、环境权限均不修改。

数据包含 3 个团队、关键业务、模型、服务、集群、P/D 组和脱敏 Key 引用，18 个 P/D Endpoint（客服 1P1D、知识 2P2D、代码 5P7D）；业务与服务、Key 与模型关系均已配置。样本仅覆盖现有巡检合同支持的 Endpoint 指标：TTFT、TPOT、E2E、请求量、生成及输入 tokens/s、缓存命中率和 running/waiting。所有数值均为人工构造的演示快照，经现有 normalize 校验；来源显示 UNVERIFIED，服务/业务健康保持 UNKNOWN。不会推算跨 Endpoint 总量、P/D 阶段指标、硬件健康或业务 SLI。

Provider 使用保留的 `.invalid` 地址，无凭据；全部演示 PollState 暂停。脚本内的 Provider 校验白名单只存在于该进程，未修改服务配置，且不发出网络请求。现有发布函数包含全局旧样本清理，所以这里校验后只追加命名空间内的样本，不调用全局清理。

五分钟后快照自然显示 STALE，数值仍可查看。如需重新展示未过期的离线样本，执行：

```sh
.venv/bin/python demo/local_preview/seed.py --refresh
```

这会备份后追加 18 份新时间窗的 UNVERIFIED 合成快照，保留已有样本；没有自动实时更新。03 只有登记集群数量，硬件指标未接入；04 不将演示样本列为已验证活动故障，可从服务目录查看详情；05 仅展示关键业务目录和配置依赖。

2026-09-26 扩展：先应用0004迁移。seed增加同命名空间的一个GPU和一个HOST绑定、两个暂停轮询的HardwareObservation缓存，填充01已批准五槽，名称含【演示】且DEMO/UNVERIFIED明确可见；不会生成硬件健康或03故障。`--refresh`仍追加18份Endpoint样本，同时替换这两个专属的最新硬件缓存（硬件无历史表），写前仍备份SQLite。硬件五槽过期后显示STALE与空值。02替换指标直接取已有Endpoint样本。没有真实采集器或自动续新。

01候选3将可见来源标记译为“演示 · 未验证”；title继续保留DEMO / UNVERIFIED、完整设备名与采样时间。过期状态仍显示STALE。


2026-09-27 拓扑扩展：保留原有六个 Endpoint 与 Binding 的 code/ID，补充另外十二个，并为十八个 Endpoint 各登记一个 `origin=DEMO` 的 RuntimeMember。Pod、节点 UID、命名空间与 `observed_at` 都是本次离线构造的证据，不代表 Kubernetes 实际发现或请求观测；不复用硬件样本来推断调度关系。已有实体不覆盖，新增对象、快照与关系仍在同一命名空间；不删除历史。若本命名空间已有用户修改导致预期 P/D 数量不符，事务回滚而不改删用户记录。

拓扑 API 合同：`focus_type` 支持 `node`、`pod` 及既有类型。`pod` ID 为 `pod:<RuntimeMember UUID>`；配置节点 ID 为 `node:<cluster UUID>:<URL编码 node_uid>`，DEMO 节点 ID 为 `node:<cluster UUID>:DEMO:<URL编码 node_uid>`，避免合成与配置身份合并。`focus_id` 是返回 ID 去掉第一个类型前缀的剩余原串，作为查询参数整体编码一次，调用方无需解析复合内容。节点仅从作用域内、启用且包含 Pod UID、节点 UID、时间戳的 CONFIGURED/DEMO RuntimeMember 产生，并要求其集群及 Endpoint 同样可见。

每个拓扑节点增加 `origin` 与 `evidence_kind`，值来自所属实体；虚拟节点继承 RuntimeMember 来源。边仍为原来的 `source/target/type`，`authorizes` 是调用授权，`depends_on` 是配置依赖，`backs_endpoint`/`scheduled_on`/`runs_in` 是登记部署关系，均不证明真实调用。集群可反查其部署模型及授权团队；节点只通过自身 Pod 的 Endpoint 定向反查，不从共享集群扩张其他模型。API 未新增表、迁移或真实采集。
