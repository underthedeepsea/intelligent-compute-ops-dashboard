# Docker 镜像与 Kubernetes NAS 部署

部署设计与边界见 [设计](../docs/docker-nas-design.md) 与 [实施计划](../docs/docker-nas-implementation.md)。Kubernetes 默认 **NAS PV/PVC + SQLite**，不启用本地模式；Compose 保留 PostgreSQL 方案。用户指定的纯HTTP入口使用下节HTTP配置；原base保留HTTPS默认。没有真实集群、NAS 或巡检联调验收。本配置不能作为生产就绪证明。

## 纯 HTTP：Pod 直连，无 Ingress

用户环境为 Linux AMD64 K8s，Web Pod IP 可被浏览器/电视访问。使用 **`deploy/k8s/http`**，不要直接把原 HTTPS base 作为 HTTP方案。应用入口为 `http://Web-Pod-IP:8080`；Web转发API的8000，保留集群内 `api` Service 和DNS。无需Ingress、TLS Secret、证书或443/8443应用端口。

此路线是v0.2.0之后新增的配置，清单使用 **0.3.0**，必须从包含HTTP改动的源码构建相应镜像，不能使用旧0.2.0 API镜像。用户已取消镜像上传，本次不提供公开可拉取的镜像地址。

```sh
/path/to/ai-ops-control-plane/deploy/build.sh \
  --registry registry.example.internal/control --version 0.3.0 --platform linux/amd64
```

把部署材料复制到部署专用目录，替换NAS地址/目录、应用与迁移清单的仓库/tag或digest；私有仓库另配置imagePullSecrets。将base/configmap.yaml的`ALLOWED_HOSTS`替换为实际Web Pod IP（或域名），共享http/config/configmap-patch.yaml的CSRF origin改为 `http://实际地址:8080`，不要使用通配符。Pod IP重建后变化时同步配置与访问地址。

`CONTROL_TRANSPORT=http` 使Session/CSRF Cookie适用于HTTP，后端忽略外来 `X-Forwarded-Proto`；HTTP Nginx按自身连接协议覆盖该头。密码、角色/环境权限和CSRF均保留，LOCAL/DEBUG/免密不得开启。独立Nginx ConfigMap会自动生成版本哈希并挂载至Web；其原生HTTP探针和静态资源仍使用8080。

按以下顺序操作，完整的Job失败处理、管理员授权、备份恢复与NAS验收仍遵守本文对应章节：

```sh
# 先离线渲染，确认配置/仓库/版本/NAS占位符全部替换。
kubectl kustomize deploy/k8s/http > /tmp/control-http.yaml
kubectl kustomize deploy/k8s/http/migrate > /tmp/control-http-migrate.yaml
# 先安装命名空间、HTTP配置、Nginx配置和PV/PVC；此profile不含Deployment。
kubectl apply -k deploy/k8s/http/prerequisites
kubectl apply -f /secure/path/control-secret.yaml
kubectl -n ai-ops wait pvc/control-data --for=jsonpath='{.status.phase}'=Bound --timeout=120s
# 确保所有API和维护写者均已退出，再执行唯一迁移Job。
kubectl apply -k deploy/k8s/http/migrate
kubectl -n ai-ops wait job/control-migrate --for=condition=complete --timeout=600s
kubectl -n ai-ops logs job/control-migrate
# 确认全部迁移容器退出后串行初始化管理员，再启动应用。
# 管理员Job的API镜像必须也替换为同一0.3.0版本；不得沿用示例中的0.2.0。
kubectl apply -k deploy/k8s/http
kubectl -n ai-ops rollout status deployment/control-api --timeout=180s
kubectl -n ai-ops rollout status deployment/control-web --timeout=180s
kubectl -n ai-ops get pods -l app=control-web -o wide
```

不要在应用启动前 `apply -k http`：它包含Deployment，会提前启动API。准备资源使用HTTP prerequisites profile，**不能直接应用原base/configmap.yaml**，否则会丢失HTTP模式与HTTP origin。管理员步骤见“清单与首次安装顺序”第4步，仍使用仓库外Secret与私有Job，完成且容器退出后才运行上面的启动命令。维护时停止所有API并按Job状态处理，升级恢复使用 `apply -k http` 而不是base。

仅对需要访问的客户端开放Web8080；限制API8000和NAS访问。现场准备项见 [生产清单](../docs/deployment-production-checklist.md)。AMD64构建、镜像分发和真实NAS/K8s联调仍需现场完成。

## 构建两个独立镜像

安装 Docker Engine 与 buildx，在任意工作目录调用脚本。发布前显式选择仓库、不可复用的版本、目标平台；K8s 的 API、Web、迁移和管理员 Job 必须使用同一发布版本。

```sh
/path/to/ai-ops-control-plane/deploy/build.sh \
  --registry registry.example.internal/control --version 0.2.0 --platform linux/amd64
# 多平台发布需事先 docker login；脚本不读取或保存凭证。
/path/to/ai-ops-control-plane/deploy/build.sh \
  --registry registry.example.internal/control --version 0.2.0 \
  --platform linux/amd64,linux/arm64 --push
```

无 `--push` 时仅加载一个平台到本机；多平台必须 push。脚本拒绝 `latest`。重复覆盖既有版本会失去不可变性，仓库应开启 tag 不可变策略，正式发布可将镜像替换为 digest。基础镜像使用固定版本标签，但标签仍可能变动；严格复现时由发布者锁定经验证的基础镜像 digest。

`--target api` 是后端/维护/可选 worker 镜像，包含 CSV 模板；`--target web` 包含静态前端与构建阶段 `collectstatic` 产物，不依赖宿主目录或共享 static 卷。Dockerfile 旁的 `.dockerignore` 只允许必要源码/资产，排除演示目录、测试、数据库、常见密钥文件与 `.codex`。不要把实际秘密写入源码文件。构建阶段没有生产凭证，运行时 Secret 必须外部提供。

API 默认一个 Gunicorn sync worker、一个线程；Web 监听 8080。两者 UID/GID 为 10001，运行根文件系统可以只读，`/tmp` 必须可写。CSV 本身上限 1 MiB，Nginx 请求体上限 2 MiB（JSON 包装占用额外空间）。入口、WAF 或代理也须允许 2 MiB。`/api/`、`/admin/`、`/healthz`、`/readyz` 转发 API；`/static/` 由 Web 提供；`/web-healthz` 是 Web 自身探针。

## NAS 与 SQLite 的硬性运行约束

- NAS 上使用专用导出目录。NAS 管理员预建目录，授予 **UID/GID 10001** 创建、读写、重命名及删除文件的权限；例如属主 `10001:10001`、目录模式 `0770`。必须验证节点上的数值身份与 NFS 导出授权一致。不要用 `0777` 代替权限设计。
- 挂载整个 `/data`，保存 SQLite 与同目录回滚日志，禁止只用 `subPath` 挂数据库文件。`20Gi` 是 PV/PVC 声明，不会自动创建 NAS 配额；配额与容量告警由 NAS 设置。
- `ReadWriteMany` 不代表允许应用并发写。默认只有一个 API Pod、一个 sync worker/线程，`Recreate` 更新；无 HPA、无默认巡检 worker。禁止增加副本、用多个发布实例共享此目录或并行维护任务。
- 迁移、创建/更改管理员、角色授权、导入管理命令、备份恢复都须先停止 API，等待所有 API 和维护 Pod 退出，再运行唯一维护 Job。禁止在运行中的 API 上 `kubectl exec ... manage.py` 写库。正常浏览器管理/CSV 导入由唯一 API 进程处理。
- `CONTROL_LOCAL` 与 `CONTROL_PASSWORDLESS_LOCAL` 均不得开启。`DATABASE_ENGINE=sqlite` 单独选择数据库；DEBUG 仍为 false；默认HTTPS使用Secure Cookie，显式HTTP模式按上节配置。两种模式均须配置SECRET、Host与匹配协议/端口的CSRF origin。未指定引擎的历史非 LOCAL 配置仍默认 PostgreSQL。
- Django 连接设置 `timeout=30`、`journal_mode=DELETE`、`synchronous=FULL`；不使用 WAL。若旧库处于 WAL 状态，转换前必须在维护窗口安全 checkpoint/关闭所有连接并备份，禁止直接删除 WAL/SHM。

[NFS 场景下 SQLite 官方警示](https://sqlite.org/useovernet.html)指出，网络文件系统的锁和同步行为可能导致损坏；[WAL 官方说明](https://sqlite.org/wal.html)说明 WAL 不适用于网络文件系统。DELETE/FULL、单进程和 30 秒等待都不能修复失效的 NFS 锁或保证 NAS 耐久性。[Django 5.2 文档](https://docs.djangoproject.com/en/5.2/ref/databases/#setting-pragma-options)支持连接初始化 PRAGMA。目标 NAS 不通过验收时暂停上线；用户若另行选择 PostgreSQL，再切换可选路线。

## 清单与首次安装顺序

以下base安装命令描述原HTTPS路线；用户选定的HTTP路线使用上节HTTP清单及初始化顺序。所有命令是部署者执行的示例，本次没有执行 K8s 写操作。先备份清单到部署专用目录，在副本中替换：NAS server/export、仓库/tag 或 digest、域名、命名空间（若调整需同步 PV claimRef、全部示例）、Ingress class、TLS Secret。镜像私有仓库另配 `imagePullSecrets`。所有 `REPLACE_*`/`example.invalid` 必须消除。

`base` 包含 Namespace、ConfigMap、PV/PVC、API/Web Deployment/Service；**不包含 Secret、TLS Ingress 或维护 Job**。`migrate` 只包含一次迁移 Job，引用提前创建的 ConfigMap、Secret、PVC。分别离线预览：

```sh
kubectl kustomize deploy/k8s/base > /tmp/control-base.yaml
kubectl kustomize deploy/k8s/migrate > /tmp/control-migrate.yaml
```

1. NAS 端完成专用目录和权限验收；每个可能调度节点必须安装/支持 NFS 挂载客户端，能访问 NAS。`root_squash` 下不依赖 root initContainer chown；本清单没有这种绕过步骤。
2. 只创建基础存储/配置，不提前启动 API：

```sh
kubectl apply -f deploy/k8s/base/namespace.yaml
kubectl apply -f deploy/k8s/base/configmap.yaml
kubectl apply -f deploy/k8s/base/storage.yaml
# 将 secret.example.yaml 复制到仓库外、填写随机秘密，限制文件权限后应用。
kubectl apply -f /secure/path/control-secret.yaml
kubectl -n ai-ops wait pvc/control-data --for=jsonpath='{.status.phase}'=Bound --timeout=120s
```

3. 首次安装也核对没有其他实例/Job 挂载同一 NAS；升级需先按下节停服务。保证唯一写者，再执行迁移：

```sh
kubectl apply -k deploy/k8s/migrate
kubectl -n ai-ops wait job/control-migrate --for=condition=complete --timeout=600s
kubectl -n ai-ops logs job/control-migrate
```

Job 执行 `migrate --noinput` 后 `bootstrap_access` 创建角色组（现有命令名，不是另一个 bootstrap_roles 命令）。`wait` 超时不代表 Job 已失败或进程已退出；保持 API=0，按下方状态表读取实际状态后处理。Job 的 template 不可变，修改镜像/命令再 apply 不会重新执行旧 Job。迁移与管理员初始化 Job 都遵循相同恢复步骤：

| Job / Pod 状态 | 允许的处理 | API 与重建限制 |
| --- | --- | --- |
| Complete，且该 Job 所有 Pod 的全部容器已 terminated，旧节点无存活写者 | 保存结果；需要下一次运行时，仅删除该已终止 Job 对象，再串行创建唯一新 Job | 维护期间保持 API=0；不删除 PV/PVC |
| Failed，且该 Job 所有 Pod 的全部容器已 terminated，旧节点无存活写者 | 保存失败状态、日志和错误证据；核对部分迁移/管理员创建状态，修复原因后，仅删除该已终止 Failed Job 对象，再串行创建唯一新 Job | 保持 API=0；不得盲目重复非幂等命令，不删除 PV/PVC |
| Active，或任意相关 Pod 为 Running/Pending/Terminating，或无法证明旧节点进程已退出 | 继续等待并调查；失联节点须先隔离并确认没有存活写者。Job condition 或 Pod 对象被删除不能代替进程退出证明 | 禁止删除后立即重建、禁止启动另一维护 Job、禁止恢复 API |

失败恢复的执行顺序如下（`control-migrate` 可替换为 `control-create-admin`）：

```sh
kubectl -n ai-ops scale deployment/control-api --replicas=0
kubectl -n ai-ops wait --for=delete pod -l app=control-api --timeout=180s
kubectl -n ai-ops get job control-migrate -o yaml
kubectl -n ai-ops get pods -l job-name=control-migrate -o yaml
kubectl -n ai-ops logs job/control-migrate --all-containers=true
kubectl -n ai-ops get pods -l app=control-maintenance -o wide
```

首次安装尚无 Deployment 时，不创建 API，并核实没有其他 API 实例。将上述状态、每个失败 Pod 的日志和错误原因保存到受控证据目录；多 Pod 时按各 Pod 分别取日志，注意脱敏。确认所有 API、该 Job 的所有容器及其他维护进程均已退出。若出现 Active/Terminating 或失联节点，继续等待/隔离，不能跳到重建步骤。

确认不存在写者后，使用同版本镜像的**唯一仅查询状态的核对 Job**检查 `django_migrations` 与实际 schema（例如 `manage.py showmigrations --plan` 加必要表结构核对），并检查目标管理员是否已创建、角色/环境授权是否已写入；该核对 Job 也必须退出后才能执行下一任务。迁移可能只完成部分步骤，不把失败等同全部回滚；先查清状态、修复权限/Secret/迁移等根因，再决定继续迁移或按已验证备份恢复。管理员已存在时移除重试命令中的 `createsuperuser`，只补齐缺失授权；不要盲目重复创建或覆盖密码。

证据已保存、状态核对完成、全部进程已退出且失联节点已隔离后，才可执行 `kubectl -n ai-ops delete job control-migrate`（管理员任务使用其 Job 名），仅删除已终止的 Complete/Failed **Job 对象**。确认其清理结束，更新私有清单，再 `apply -k deploy/k8s/migrate` 或 apply 唯一管理员 Job；等待成功且 Pod 退出后才继续后续步骤。失败再次保持 API=0，重新调查，不并行重试。始终不删除 PVC/PV，不使用 `kubectl delete -k base` 清理。

4. 仍保持 API 未启动，使用 `examples/admin-job.example.yaml` 的私有副本进行首次管理员初始化。单独建立仓库外 Secret `control-admin-bootstrap`，含 `DJANGO_SUPERUSER_USERNAME`、`DJANGO_SUPERUSER_EMAIL`、`DJANGO_SUPERUSER_PASSWORD`；使用密码管理流程供给，不把密码放在命令行/代码。替换 Job 镜像与 `CONTROL_ADMIN_ENVIRONMENT` 为真实环境代码，apply 后 wait/log。它依次创建管理员并赋予 catalog_admin 和明确环境范围；不可对已存在管理员盲目重复 createsuperuser。后续授权维护时复制为新的 Job 名，改为只执行 `bootstrap_access --username ... --role ... --environment ...`，仍在维护窗口串行执行。初始化完成确认 Pod 退出，删除临时引导 Secret 与完成的管理员 Job；失败时先按上方 Failed Job 恢复步骤检查用户/授权状态，保持 API=0，不能直接重复 apply 或启动第二个 Job。

```sh
kubectl apply -f /secure/path/control-admin-secret.yaml
kubectl apply -f /secure/path/control-admin-job.yaml
kubectl -n ai-ops wait job/control-create-admin --for=condition=complete --timeout=300s
kubectl -n ai-ops logs job/control-create-admin
# 确认完成并终止后清理一次性引导资源；此处不删除任何数据库存储。
kubectl -n ai-ops delete job control-create-admin
kubectl -n ai-ops delete secret control-admin-bootstrap
```
5. 所有维护 Pod 已退出后才启动应用，再配置 TLS 入口：

```sh
kubectl apply -k deploy/k8s/base
kubectl -n ai-ops rollout status deployment/control-api --timeout=180s
kubectl -n ai-ops rollout status deployment/control-web --timeout=180s
kubectl apply -f /secure/path/control-ingress.yaml
```

入口需安装实际 Ingress controller、创建正确证书 Secret `control-tls`，强制 HTTP 跳 HTTPS，并**覆盖/清理客户端 X-Forwarded-Proto** 为实际外部协议。示例是通用 Ingress，没有假定控制器注解；按所选控制器设置 TLS 跳转、2 MiB 请求体和信任代理范围。服务只使用 ClusterIP；限制网络访问，确保客户端不能绕过可信入口直连 Web/API 来伪造代理头。`ALLOWED_HOSTS`、`CSRF_TRUSTED_ORIGINS` 和 Ingress host 同步，浏览器全程 HTTPS 同源；HTTP 不会正常携带 Secure 登录 Cookie。

初期数据通过控制台手动 CSV 导入，不启动巡检 worker，也不写入演示数据。巡检集成需另外取得来源、只读凭证与明确授权。

## 升级与维护窗口

先保留上一版本 API/Web digest、清单、Secret 管理引用与数据库备份。新镜像构建并验证成功后，同步修改 base、migrate、维护 Job 的 API 版本；Web 与 API 保持同一发布。

```sh
kubectl -n ai-ops scale deployment/control-api --replicas=0
kubectl -n ai-ops wait --for=delete pod -l app=control-api --timeout=180s
kubectl -n ai-ops get pods -l app=control-maintenance
# 确认维护 Pod 全部已终止，NAS没有别的写者；备份后再运行单次新版本迁移。
```

停止自动发布/GitOps 的副本回调，避免服务被提前恢复。仅 scale=0 而 Pod 尚在 Terminating 不够；若节点不可达，Pod 删除不证明进程停止，必须隔离/确认旧节点没有存活写者，再迁移或新调度。`Recreate` 限制常规更新但不能代替节点故障时的写者隔离。

成功备份后，按上方状态表处理旧迁移 Job：Complete 可在确认进程退出后清理；Failed 须先保存证据、检查部分迁移状态并修复原因，确认所有进程退出/旧节点隔离后才清理重建；Active/Terminating 继续等待与调查，不并行重建。仅删除已终止的 Job 对象，不删除 PV/PVC，API 始终保持 0，再运行本版本唯一迁移 Job；必要管理员/授权变更也使用单独 Job 串行完成。全部维护结束再 `apply -k base` 恢复一副本。维护期间 Web 可继续展示静态文件，但 API 请求失败；预先安排停机提示，不把这一阶段作为监控数据更新。

## 备份、恢复与回滚

停止 API/所有维护进程后才备份。可使用 NAS 管理端一致性快照及异地备份，或唯一维护 Job 调用 SQLite backup API 写入独立备份目录。不要在运行期间直接 `cp control.sqlite3`，不要删除回滚日志来解除锁。非正常终止后必须保留数据库及日志，由唯一维护进程完成 SQLite 恢复，再做完整性检查/备份。

例如将维护 Job 的命令改为以下 Python 脚本（使用**待备份数据库当前对应的旧版本镜像**，先备份再升级；`DJANGO_SETTINGS_MODULE=config.settings` 与部署环境变量保持一致，/data可写，目标专用备份目录由管理员建立）。源不存在、源为空库或 schema/已安装迁移不匹配时停止，不创建源或目标。若源处于部分迁移状态，先调查并选择对应版本/恢复方案，不降低校验来强行继续。目标创建后任何失败均视为失败备份，保留证据并隔离该文件，不用于恢复；修复后使用新的唯一备份名称：

```python
import sqlite3
from contextlib import closing
from pathlib import Path
import django
from django.conf import settings
from django.apps import apps
from django.db.migrations.loader import MigrationLoader

django.setup()
if settings.LOCAL or settings.DATABASES['default']['ENGINE'] != 'django.db.backends.sqlite3':
    raise RuntimeError('备份仅用于生产配置的 SQLite 维护窗口')
source_path = Path('/data/control.sqlite3')
if source_path.resolve() != Path(settings.DATABASES['default']['NAME']).resolve():
    raise RuntimeError('源路径与当前部署 SQLITE_PATH 不一致，停止维护')
backup = Path('/data/backups/control-before-upgrade.sqlite3')
if backup.exists():
    raise RuntimeError('禁止覆盖已有备份；使用本次唯一备份名称')

# 使用待备份库对应的旧版本镜像，读取该版本的迁移文件；不连接 Django 数据库。
expected_migrations = set(MigrationLoader(None).graph.nodes)
expected_tables = {'django_migrations': {'app', 'name', 'applied'}}
for model in apps.get_models(include_auto_created=True):
    if model._meta.managed and not model._meta.proxy:
        expected_tables[model._meta.db_table] = {
            field.column for field in model._meta.local_fields
        }

def verify_database(connection):
    if connection.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
        raise RuntimeError('数据库完整性检查失败，停止维护')
    tables = {row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    if not set(expected_tables) <= tables:
        raise RuntimeError('缺少预期应用表，拒绝空库/错误源')
    for table, expected_columns in expected_tables.items():
        quoted_table = '"' + table.replace('"', '""') + '"'
        columns = {row[1] for row in connection.execute(
            'PRAGMA table_info(' + quoted_table + ')'
        )}
        if not expected_columns <= columns:
            raise RuntimeError('应用表字段与备份版本不一致，停止维护')
    applied = set(connection.execute('SELECT app, name FROM django_migrations'))
    if applied != expected_migrations:
        raise RuntimeError('已安装迁移与备份镜像版本不一致，停止维护')

# mode=rw 拒绝创建缺失源，仍允许唯一维护进程进行正常回滚日志恢复。
with closing(sqlite3.connect(source_path.resolve().as_uri() + '?mode=rw',
                            uri=True, timeout=30)) as source:
    verify_database(source)  # 全部源校验通过前，不创建目标备份。
    with backup.open('xb'):
        pass  # 排他创建，避免覆盖刚出现的同名文件或符号链接。
    with closing(sqlite3.connect(backup.resolve().as_uri() + '?mode=rw',
                                uri=True, timeout=30)) as target:
        source.backup(target)
        verify_database(target)
print('备份成功：源与目标应用 schema、迁移和完整性均通过校验')
```

备份保存到同一 NAS 仅方便操作，不能代替异地备份。保留备份校验、权限、时间、镜像/Schema 版本，并在离线副本上验证恢复。恢复时保持所有写者退出，先保全当前完整数据目录，再将验证过的备份恢复到专用 NAS 路径（UID/GID 10001）；不混用旧 WAL/SHM/journal 与新库。通过唯一维护 Job 检查 integrity/schema，恢复对应版本镜像后再启动。

回滚代码前确认旧代码兼容新 Schema；不兼容时恢复升级前数据库备份与匹配的 API/Web 版本。不要盲目反向迁移，不把恢复演示数据库称为生产恢复验证。PV `Retain` 使删除 PVC 后 NAS 数据不会被自动回收；PVC/PV 与目录恢复需管理员明确操作，[PV 官方文档](https://kubernetes.io/docs/concepts/storage/persistent-volumes/)说明绑定和回收语义。日常 Job 重跑、升级和回滚均不删除 PVC/PV。

## 目标 NAS 验收（外部环境待完成）

在专用测试导出/测试库验证，绝不对正式库做故障注入：

- 各节点 UID/GID 10001 创建/读写/rename/delete、目录日志空间、PV/PVC Bound、权限及 root_squash；实际配额与备份空间。
- 实际 SQLite 连接确认 DELETE、FULL、busy_timeout=30000；测试写入、同步确认后的重新挂载读取与 integrity_check。
- NAS/NFS 厂商支持的文件锁、fsync/稳定存储语义；网络中断、客户端异常退出、NAS重启后回滚日志恢复和完整性。检查出现 I/O error/locked 时不会额外启动写者。
- 节点失联时的旧写者隔离、重调度、备份恢复演练；单进程吞吐与人工CSV导入负载满足目标。
- 所选协议的登录与Cookie、Host/CSRF、未经授权访问、CSV模板/静态管理资源、2 MiB代理、只读根文件系统与Secret运维；HTTP路线不要求TLS验收。

RWX/Retain/PRAGMA 配置正确并不等于上述外部验收通过；不能保证任意 NFS 实现可靠锁定。

## 可选 PostgreSQL Compose

从 `deploy` 目录复制 `.env.example` 到仓库外或被忽略的 `.env`，填写真实值和镜像版本。此路线显式 `DATABASE_ENGINE=postgresql`，与默认 K8s NAS 路线分开选择，不启用 LOCAL。Web 镜像封装资产，**没有宿主 frontend 挂载或 collectstatic 运行步骤**。

```sh
cd /path/to/ai-ops-control-plane/deploy
docker compose --env-file .env build
docker compose --env-file .env up -d db
docker compose --env-file .env run --rm api python manage.py migrate --noinput
docker compose --env-file .env run --rm api python manage.py createsuperuser
docker compose --env-file .env run --rm api python manage.py bootstrap_access \
  --username YOUR_ADMIN --role catalog_admin --environment YOUR_ENVIRONMENT
docker compose --env-file .env up -d api web
```

前端仅绑定 localhost:8088，须配可信 TLS 反向代理并覆盖协议头；HTTP 直连不支持正式安全登录。若用已发布镜像可将 build 替换为 pull。轮询 worker 复用 API target，放在 `inspection` profile，默认不开启；获得真实巡检授权后才可 `docker compose --profile inspection up -d worker`，一份worker、PostgreSQL，不与 NAS SQLite 并行。备份 PostgreSQL 使用受控 pg_dump 流程；代码/schema回滚仍需匹配版本和验证。

若另选 PostgreSQL 的 Kubernetes 部署，由运维提供独立 PostgreSQL 服务/Secret，把 `DATABASE_ENGINE` 改为 `postgresql`、设置 PGHOST/PGDATABASE/PGUSER/PGPASSWORD；明确移除 SQLite NAS 挂载并重新审查维护与备份流程。本次不附复杂 overlay，也不自动把用户指定 NAS SQLite 改成 PostgreSQL。
