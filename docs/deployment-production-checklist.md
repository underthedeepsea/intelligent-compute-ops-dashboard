# 生产部署准备清单：x86 K8s、Pod 外部可达、NAS SQLite

更新日期：2026-10-09。基线为已发布 v0.2.0；新增 HTTP 配置需使用本工作区重新构建的 0.3.0 镜像。

本清单按用户明确要求采用纯 HTTP、Web Pod 外部直连、不使用 Ingress。用户已取消镜像上传；当前没有公开可拉取的项目镜像。已发布版本标签不修改。

## 当前完成程度

已有：Web/API Dockerfile 与构建脚本、K8s Deployment/Service、NAS PV/PVC、应用配置和 Secret 示例、迁移及管理员 Job、升级与备份恢复说明。

HTTP 入口使用独立 `deploy/k8s/http` 配置，不需要证书、TLS Secret 或 HTTPS 入口。现场仍需完成 Linux AMD64 镜像构建验证、外部访问限制和 Pod 地址变动处理，以及真实 K8s、NAS 与恢复验收。请按 [HTTP部署说明](../deploy/README.md#纯-httppod-直连无-ingress)执行，而不是直接使用原HTTPS base。

## 1. 需要交付的应用镜像

| 项目 | 要求 | 当前状态 |
| --- | --- | --- |
| `control-web` | Linux AMD64；包含 Nginx、前端页面、JS/CSS 和 Django 管理静态文件 | 构建方案已有；AMD64 成品待构建验证 |
| `control-api` | Linux AMD64；包含 Python、Django、Gunicorn、业务代码、依赖及 CSV 模板 | 构建方案已有；AMD64 成品待构建验证 |
| 镜像仓库或离线分发 | 提供实际地址、同版本标签和 digest；私有仓库提供拉取 Secret | 现场提供；不上传 GitHub |

运行时使用两个完整应用镜像。通用 Nginx/Python 基础镜像本身不能代替应用镜像。迁移、管理员初始化与备份维护复用 API 镜像，不增加第三个应用镜像。SQLite 已由 Python 提供，不部署数据库容器；此默认路线不需要 PostgreSQL、MySQL、Redis 或巡检 worker。

构建机需访问基础镜像及 Python 包源，或准备对应的离线缓存；部署节点只需获取构建好的应用镜像，容器启动时不执行 pip 安装。已有构建命令见 [部署说明](../deploy/README.md)。

## 2. 现场必须提供的配置和基础设施

| 所需项 | 提供内容 | 责任方 / 现状 |
| --- | --- | --- |
| K8s 环境 | Linux AMD64 节点、目标集群与命名空间、部署权限、集群 DNS、准入策略及资源额度 | 集群管理员；命名空间默认 `ai-ops` |
| 应用资源 | 一个 Web Pod、一个 API Pod；API 固定单副本、一个 sync worker/线程、Recreate，无 HPA | 清单已有；吞吐需现场验证 |
| NAS | NFS 服务地址、专用 export 路径、协议版本、节点访问授权、实际容量及配额 | NAS 管理员提供；PV/PVC 模板已有 |
| NAS 权限 | UID/GID `10001:10001` 可在专用目录创建、读写、重命名和删除文件；所有可能调度节点支持 NFS 挂载 | NAS/节点管理员验收；不依赖 root initContainer 改权限 |
| 数据卷 | 挂载整个 `/data`，数据库为 `/data/control.sqlite3`；保留同目录回滚日志；PV `Retain` | 清单默认声明 20Gi，NAS 实际配额需另配 |
| 访问地址 | 推荐内网域名；定义 Web Pod 重建后如何更新域名解析或现有负载均衡后端 | 网络管理员；不要求安装 Ingress |
| 应用 Secret | 持久保存的随机 `DJANGO_SECRET_KEY`；不能随 Pod 重建随机更换 | 运维提供，写入 `control-secrets`，不进源码和镜像 |
| ConfigMap | `DATABASE_ENGINE=sqlite`、`SQLITE_PATH`、真实 `ALLOWED_HOSTS`、`CONTROL_TRANSPORT=http`、含 HTTP 协议和端口的 `CSRF_TRUSTED_ORIGINS` | 模板已有，需替换现场值；禁止启用 LOCAL 或免密 |
| 初始管理员 | 用户名、邮箱、密码、角色及实际环境授权范围 | 通过临时引导 Secret 和唯一管理员 Job 初始化；完成后清理引导 Secret |
| 网络访问控制 | 外部用户仅访问 Web；API 8000 限制为 Web 与必要探针；NAS 仅向授权节点开放 | 集群/网络管理员；当前未提供适配现场 CNI 的策略 |
| 数据内容 | 推理服务/集群/授权等业务配置，以及需要展示的人工导入数据 | 业务人员录入；全新生产库不自动写入演示数据 |
| 备份与运维 | 备份目标、周期、保留期限、恢复责任人、维护窗口、失联节点旧写者隔离流程 | 运维提供；已有维护说明，仍需恢复演练 |

当前应用资源声明：API 请求 100m CPU / 128Mi，限制 1 CPU / 256Mi；Web 请求 50m / 32Mi，限制 500m / 128Mi。这是清单起始值，不是生产容量测试结论；节点、DNS、NAS及系统组件资源另计。维护 Job 串行运行，并预留其资源。

## 3. HTTP入口及端口

```text
浏览器/电视 → http://Web-Pod-IP:8080 → Nginx → api:8000 → NAS上的SQLite
```

可直接使用 Web Pod IP，也可配置内网域名。保留 API Service 与集群 DNS。Pod 重建后可能更换地址，需更新访问地址或域名解析。

| 通信路径 | 端口 | 范围 |
| --- | --- | --- |
| 浏览器/电视、K8s探针 → Web Pod | TCP 8080 | 页面、同源API入口和Web探针 |
| Web Pod、必要探针 → API Service/Pod | TCP 8000 | 外部用户只使用Web入口，限制直接API访问 |
| K8s节点 → NAS | NFSv4通常TCP 2049 | 实际以NAS协议为准；NFSv3还需rpcbind/mountd等端口 |
| Pod → 集群DNS | UDP/TCP 53 | 集群已有服务，用于解析API Service |
| 节点/构建机 → 镜像仓库 | 以仓库配置为准 | 此处仓库协议与应用HTTP入口无关 |
| SQLite | 无端口 | 文件存储 |

HTTP配置令Session/CSRF Cookie可在HTTP发送，仍保留密码、权限、Host和CSRF检查；不启用LOCAL、免密或DEBUG。Nginx覆盖外来转发协议头，后端HTTP模式不信任该头。

```text
CONTROL_TRANSPORT=http
ALLOWED_HOSTS=实际Web-Pod-IP,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=http://实际Web-Pod-IP:8080
DATABASE_ENGINE=sqlite
SQLITE_PATH=/data/control.sqlite3
```

域名访问时将Host和Origin替换为实际域名；Host不填协议/端口，Origin必须包含协议和实际非默认端口，不使用通配符。

## 4. 安装和验收顺序

1. 完成 AMD64 应用镜像、HTTP清单、仓库与现场配置；消除全部占位符。
2. 创建命名空间、应用 Secret/ConfigMap、PV/PVC；验证 NAS 权限和 PVC Bound。
3. 保持 API 未启动，确认 NAS 没有其他写者；唯一迁移 Job 执行迁移和角色初始化，等待所有容器退出。
4. 唯一管理员 Job 初始化用户和环境授权，确认退出后清理临时引导资源。
5. 启动单副本 API 与 Web，验证 HTTP、浏览器登录/CSRF、静态文件、健康探针和导入。
6. 导入实际展示数据，在测试库验证 NAS 锁、同步、网络/节点故障恢复与备份恢复；记录验收后再正式上线。

维护与失败 Job 恢复仍按 [部署说明](../deploy/README.md) 执行，不并行启动写者，不删除 PV/PVC。默认巡检不对接真实系统，手动导入模板在 `templates/cluster-config.csv`、`templates/endpoint-metrics.csv`、`templates/hardware-metrics.csv`。

## 参考与限制

- [Django Cookie配置](https://docs.djangoproject.com/en/5.2/ref/settings/#session-cookie-secure)：HTTP路线明确配置Cookie传输；CSRF校验保留。
- [Kubernetes Pod](https://kubernetes.io/docs/concepts/workloads/pods/)：Pod 生命周期；重建后不能假定地址不变。
- [Linux NFS 文档](https://man7.org/linux/man-pages/man5/nfs.5.html)：NFS 版本和端口差异。
- [SQLite 网络文件系统说明](https://sqlite.org/useovernet.html)：NAS 上的文件锁与同步可靠性须实际验证。单副本和 DELETE/FULL 不能消除 NAS 实现风险。

当前尚未完成上述现场验收，不能称为生产就绪。此清单已明确待提供项和实施差距；不表示AMD64成品、现场部署或镜像上传已完成；本地验证结果见HTTP部署记录。
