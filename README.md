# 智算运维大屏

**Intelligent Compute Ops Dashboard**：面向智算集群的五屏观测界面、AI Gateway 资源控制台和独立录入流程原型。

静态 HTML / CSS / JavaScript 前端，Django 后端；本地使用 SQLite，部署配置提供 PostgreSQL 与 Nginx。无需前端构建步骤。

![01 全局运维总览](docs/screenshots/overview.png)

*截图为离线演示目录，过期指标保持空值；中心连线表示登记部署关系。*

## 主要界面

| 页面 | 用途 |
| --- | --- |
| 01 全局运维总览 | 单设备原始指标；按实际目录关系显示集群 → 服务 → Endpoint，支持分页和详情下钻 |
| 02 P/D 运行诊断 | 多集群、多 P/D 的 Endpoint 性能与负载查看 |
| 03 基础设施异常定位 | 基础设施异常资源定位；未接入时保留状态说明与留白 |
| 04 推理服务异常定位 | 按 Endpoint 原始状态查看服务与配置业务依赖 |
| 05 关键应用守望 | 关键业务与服务目录关系 |
| AI Gateway Console | 团队、业务、模型、服务、授权引用与运行成员目录 |

目录关系不代表真实调用、运行健康或网络流量。未接入、未知与过期状态单独显示，不用零值替代缺失数据。没有真实采集器时，离线样本明确标记为演示、未验证或过期。

## 本地启动

需要 Python 3.10+；Node.js 用于前端单元测试。

```bash
git clone https://github.com/underthedeepsea/intelligent-compute-ops-dashboard.git
cd intelligent-compute-ops-dashboard
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock
export CONTROL_LOCAL=1
export CONTROL_PASSWORDLESS_LOCAL=1
export CONTROL_PASSWORDLESS_USERNAME=local-preview
export CONTROL_PASSWORDLESS_ENVIRONMENT=local
python backend/manage.py migrate --noinput
python backend/manage.py bootstrap_local_access
python backend/manage.py runserver 127.0.0.1:8767 --noreload
```

- 五屏入口：<http://127.0.0.1:8767/screen/>
- 控制台：<http://127.0.0.1:8767/gateway/>

初始数据库为空。可在另一个已启用同一虚拟环境的终端执行以下命令，生成明确标记的离线演示数据：

```bash
python demo/local_preview/seed.py
```

此脚本只用于本机演示数据库，生成前自动备份；详见 [演示数据说明](demo/local_preview/README.md)。它不连接实际巡检平台，不代表真实监控。

本机免密访问仅供 loopback 开发预览，专用账号不是超级用户。禁止将该模式经隧道或公网代理公开。生产部署使用独立会话、数据库及真实权限配置，参见 [部署说明](deploy/README.md)。

## 独立录入原型（实验功能）

```bash
python3 -m http.server 8789 --bind 127.0.0.1 --directory prototypes/gateway-entry-flow
```

访问 <http://127.0.0.1:8789/?mode=wizard>。支持整项服务录入、P/D 与 Router、K8s 命名空间、LWS/Deployment、多个配置 Node、自动生成记录 UUID。数据仅保存在该浏览器，不与正式后端或五屏自动同步；Pod 和采集 UID 不接受人工填入。

**已知未解决事项**：批量导入的显式名称引用可能与导入别名冲突；同页重复载入完整示例可能复用已保存 UUID。暂不将该原型的批量导入用于重要数据。这两项不属于本轮01拓扑调整。

## 测试

```bash
node --test frontend/screen/tests/*.test.cjs frontend/gateway/tests/*.test.cjs
node --test prototypes/gateway-entry-flow/directory-core.test.cjs
CONTROL_LOCAL=1 python backend/manage.py test tests --verbosity 1
```

测试包含合成数据与隔离数据库，不构成生产采集验证。历史本机浏览器验收脚本、会话记录、数据库及凭据不随源码发布。

## 项目结构

```text
backend/                 Django API、目录、权限、观测投影与测试
frontend/screen/         五屏与门户
frontend/gateway/        AI Gateway 控制台
prototypes/gateway-entry-flow/  浏览器本地录入原型
demo/local_preview/      离线演示数据生成器
contracts/               接口与来源契约
templates/               CSV 模板
deploy/                  Docker Compose / Nginx 部署配置
docs/                    目录录入、监控与上线检查说明
```

项目尚未宣称完成真实巡检平台接入或生产上线；请按来源契约和部署检查项验证自己的环境。
