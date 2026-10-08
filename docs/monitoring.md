# 按集群配置监控来源

Gateway 的「监控接入」由目录管理员配置，operator 可查看。每个集群独立选择「巡检」或「CSV」，所以多个集群可同时使用不同来源。CSV 是人工导入的持久快照，显示原始采样时间，直到下一次同类导入；它不代表当前健康状态。巡检仍按原来的有效期和来源可信度显示。

## CSV 使用步骤

1. 打开 Gateway 监控接入，下载「集群配置」模板。UTF-8 编码，可带 BOM；用支持 CSV 的表格编辑器打开。模板第二行是示例：替换或删除后填写自己的数据，保留表头。
2. 每个文件配置一个集群，一行一个 Endpoint。重复填写一致的集群、模型、服务和 PD 定义；模板可增行。`environment_code` 填管理员已授权的环境。只配置空集群时保留前四列，后续列留空。
3. 上传集群配置，校验并查看预览，再应用。已有配置按编码补充或更新；文件中省略的对象不会被删除。共享模型、服务、PD 的名称及归属必须与已有配置一致，不能借集群导入改名或移动其他集群的 Endpoint。
4. 在目标集群把来源切为 CSV。分别下载 Endpoint 指标和硬件指标模板，填写已有 Endpoint 编码或设备身份、采样时间、数值，然后各自校验并应用。
5. 打开大屏。标记「CSV 快照」与采样时间的值长期保留；Endpoint 与硬件分别保留各自最后一次导入时间。新导入替换所选集群的同类快照，不影响另一类。文件没提供的指标显示缺失，不自动补零；Endpoint 文件未包含的 Endpoint 不回退到巡检数据。

切换回巡检会隐藏 CSV 快照，等本次来源下的新巡检结果；以后切回 CSV 可继续看到上次保存的快照。重新上传同一规范化文件是幂等操作。预览之后配置被其他人改动时，需要重新校验。

## 字段与单位

- `sampled_at` 必须是带时区的 ISO 时间，例如 `2026-09-01T08:00:00Z`（UTC）。同一文件所有行相同。旧时间允许，最多允许比服务端当前时间快 30 秒。`imported_at` 是系统记录的导入时间，不取代采样时间。
- `ttft_*_ms`、`e2e_*_ms`：毫秒；`tpot_*_ms`：毫秒/token。`p90 <= p95 <= p99`。
- `request_rate`：请求/秒；`request_rate_per_minute`：请求/分钟。`generated_tokens_per_second`、`input_tokens_per_second`：token/秒。各指标独立输入，不根据其他列推算。
- `ttft_e2e_ratio`、`kv_cache_hit_ratio`、`utilization_ratio`、`cpu_busy_ratio`：0–1 比例，例如 72% 填 `0.72`，不能填 `72`。
- `running`、`waiting`：非负整数；其他填入的数值必须是有限非负数。空白表示 MISSING；`0` 是有效实测数值。至少填写一个指标。
- `temperature_celsius`：摄氏度；所有 `*_bytes`：字节。内存总量必须大于零，已用/可用量不得超过总量。仅派生 GPU 已用/总量和主机 `1 - 可用/总量`，不生成其他综合指标或健康结论。
- GPU 行 `resource_type=GPU_POOL`，必须填 `gpu_uuid`、`host_id`；使用 GPU 利用率、温度、已用及总内存列。主机行 `resource_type=HOST`，`gpu_uuid` 留空，使用 CPU、可用及总内存列。非适用列留空。
- 配置中的 `runtime_code` 及 pod/node 字段可选。填写成员时需要 runtime_code 与 namespace；observed_at 如填写也须带时区。没有提供的 Pod/Node 身份不会自动生成。
- COMBINED 服务使用 COMBINED Endpoint，PD 列留空；SPLIT_PD 服务填写 PD，角色为 ROUTER/PREFILL/DECODE。

CSV 列名须与模板一致，最多 1 MiB、1000 数据行。禁止公式、重复列名、重复对象及跨环境引用。导入失败不保存任何行。

## 巡检接入

先由服务端运维配置 HTTPS Provider 白名单和服务器环境变量凭据，并通过现有 Provider 目录配置来源。监控页只选择已有 Provider，不接收任意 URL 或原始密钥。每个 Endpoint 使用明确的 environment_id、engine_id、engine_type、model_name 映射；硬件使用所选集群、环境 UUID、asset_id、host_id、GPU UUID 的显式单设备映射。保存映射会废弃旧版本观察。

当前参考巡检接口缺少完整 provenance 证明，可能展示 UNVERIFIED；选择「巡检」不会把数据自动提升为可信或正常。未分配集群的旧硬件映射不会混入任何受管理集群；请在监控页建立明确集群映射。离线演示仅把自身演示硬件绑定到对应演示集群，不访问生产巡检。
