# 本地演示包应用方法

GitHub 当前源码不包含新版资源清单、指标回放、逃生预案、旧版种子/静态样本、原型样本和演示截图。测试中的小型合成夹具用于验证代码，不会自动安装进应用。初始数据库为空，普通入口读取实际登记目录与 API；缺少演示包不会自动补数据。

## 1. 启动源码

按 README 创建虚拟环境、安装 `requirements.lock`。在项目根目录执行命令。生产目录使用你自己的数据库；演示请使用独立 SQLite。包路径和数据目录均为本机绝对路径，不从 GitHub 下载样本。

```bash
export CONTROL_LOCAL=1
export SQLITE_PATH=/absolute/path/local-preview.sqlite3
export PRODUCTION_SCENE_DATA_DIR=/absolute/path/local-demo-data
python backend/manage.py migrate --noinput

# 仅校验 ZIP 全清单 SHA256、资源目录/预案匹配及全部 960 个窗口
python backend/manage.py install_demo_bundle /absolute/path/compute-dashboard-szg8h-v5-local-data.zip
# 明确安装到外部数据目录；不写数据库、不执行包内脚本
python backend/manage.py install_demo_bundle /absolute/path/compute-dashboard-szg8h-v5-local-data.zip --apply
```

安装器默认只检查；重复安装相同内容不重复写入。遇到不同的已有文件、路径穿越、符号链接、清单/哈希不一致或超限包会拒绝。更新不同版本请使用新的数据目录，验收后修改环境变量，不覆盖原包。可用 `--data-dir` 指定安装目录，但后续命令和 API 进程仍须设置相同的 `PRODUCTION_SCENE_DATA_DIR`。

## 2. 显式登记目录并启动回放

已有数据库先停止 API 及其他写者、备份数据库，再串行迁移与导入。新建演示数据库也按以下顺序执行：

```bash
python backend/manage.py prepare_szg_scene
python backend/manage.py prepare_szg_scene --apply
python backend/manage.py check_scene_install
export PRODUCTION_SCENE_REPLAY_ENABLED=1
python backend/manage.py runserver 127.0.0.1:8769 --noreload
```

`prepare_szg_scene` 默认事务回滚，`--apply` 才登记目录/预案；不写生产遥测、不切流量。旧版四组目录先纠正成三个逻辑组，旧版→v5 再将两个重复入口停用并保留 Endpoint 身份和原始观测；重复 Pod/部署范围登记先归档前像再收敛。卡型默认未确认，不把回放 H200/MX550 当成真实资产。遇到真实运行绑定、未知引用、手改预案或目录漂移时停止，不能强制替换。

v5 验收以 `check_scene_install` 和你的本地包清单为准。当前迁移包含 0001–0005：旧迁移保持兼容，新迁移只建表；目录、主机卡型、修订审计和预案由显式导入处理。原始表格中的歧义应在本地核对，不把演示状态当成生产资产确认。

回放：<http://127.0.0.1:8769/screen/?replay=szg-8h&screen=02>；控制台：<http://127.0.0.1:8769/gateway/>。普通 `/screen/` 不切到合成指标。关闭回放将 `PRODUCTION_SCENE_REPLAY_ENABLED=0` 后重启 API；不会删除已登记目录。

容器部署时将已安装的数据目录作为只读卷挂载进 API，设置对应的 `PRODUCTION_SCENE_DATA_DIR` 和回放开关。代码镜像排除本地样本；无需把数据放进镜像或上传 GitHub。

## 3. 旧版样本与离线资料（可选）

包中 `legacy/` 保存旧版种子、静态五屏数据和原型样本；`audit/` 保存原始数据映射、覆盖报告、快照及离线 HTML。安装命令只将这些文件保存到外部数据目录，不执行它们。

```bash
# 仅检查；再显式恢复到项目内被 Git 忽略的四个历史路径
python backend/manage.py restore_legacy_demo
python backend/manage.py restore_legacy_demo --apply
# 独立浏览器原型读取恢复的 JSON；不写正式数据库
python3 -m http.server 8789 --bind 127.0.0.1 --directory prototypes/gateway-entry-flow
```

访问 <http://127.0.0.1:8789/?mode=wizard>。未恢复样本时原型打开空目录，样本按钮禁用，仍可手工录入。

旧 `frontend/screen/demo-data.js` 仅为历史兼容保留，当前新版入口不加载它。旧 `demo/local_preview/seed.py` 会改写数据库，因此不会由任何导入命令自动运行。若要重现旧演示，应在独立项目副本/空库中按其 README 运行；不要在现有 SZG 数据库运行历史种子。

## 4. 检查

```bash
# 不装包也能执行通用测试；依赖外部样本的测试会明确显示 skipped
python backend/manage.py test tests production_scene --verbosity 1
node --test frontend/screen/tests/*.test.cjs frontend/gateway/tests/*.test.cjs
node --test prototypes/gateway-entry-flow/directory-core.test.cjs

# 数据验收必须装包，并强制缺少夹具时报错；原有断言全部保留
export PRODUCTION_SCENE_TEST_DATA_REQUIRED=1
python backend/manage.py test tests production_scene --verbosity 1
node --test prototypes/gateway-entry-flow/directory-core.test.cjs
```

Django 测试使用隔离测试数据库。公开历史和旧 Tag 已经按所有者授权清理，原历史备份仅本地保留。整个包是演示材料，不是生产采集验收。

## 5. 在部署环境中应用

仅重现演示效果需要同版本前后端、数据库迁移、可读取的外部包目录和显式回放开关，不需要额外采集器、消息队列或巡检服务。演示包不会接入真实监控，也不会执行预案切流。

1. 确认 API/Web 均来自 v0.7.0，停止 API 及其他数据库写者，备份数据库和当前外部数据目录。
2. 将本地 ZIP 私下传到维护环境，安装依赖并串行迁移；对新目录执行上面的 ZIP 校验、`--apply` 安装和目录预检。
3. 预检通过后执行 `prepare_szg_scene --apply`、`check_scene_install`。未知真实引用或目录漂移必须先处理；不要强制覆盖。
4. 将已安装目录作为只读卷挂载 API，设置相同 `PRODUCTION_SCENE_DATA_DIR`；需要演示回放才设置 `PRODUCTION_SCENE_REPLAY_ENABLED=1`。启动 API/Web 并使用显式回放 URL 检查。
5. 退出演示时关闭回放并重启 API；恢复普通入口。真实生产监控另需实际数据源、绑定、来源验证和访问控制，不由这个包提供。

原有本机路径、真实名称和详细映射保存在独立的本地生产导入指南中，不发布到此仓库。
