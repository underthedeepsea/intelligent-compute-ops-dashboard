# Frontend API v1.0 — frozen local implementation contract

All paths below start `/api/v1`, no trailing slash. Same-origin CSRF cookies; GET `/session` sets CSRF cookie and returns `data.csrf_token`. All POST/PATCH/PUT require `X-CSRFToken`. All APIs use anonymous direct access across registered environments. JSON errors: `{error:{code,message,request_id,details}}` (400/401/403/404/409). Success envelope `{schema_version:"1.0",view_revision,metadata_revision,telemetry_revision,served_at,data}`. Revisions are integers; reject older view_revision. `served_at` is response time, never sample time.

GET `/session` returns `{access_mode:"direct",can_write:true,environments:[],csrf_token,data_mode:"live"}` with Cache-Control: no-store. It is access metadata, with no user, authenticated flag or roles. The frontend calls `ensureAccess()`. All registered environments are directly readable and writable; CSRF and entity environment consistency remain. Login/logout/local and public admin routes do not exist. HTTP audit actor is anonymous. Current contract: [direct access](../docs/direct-access-design.md).

GET `/catalog/{teams,businesses,models,clusters,services,pd-groups,endpoints,runtime-members}` and `/gateway/keys`: `data:{items:[],next_cursor:null}`. Optional environment_code, limit (1..100), cursor. Collection POST creates entity, details GET/PATCH; PATCH requires expected_version. No DELETE, use enabled=false. Entity common fields `{id,code,name,environment_code,enabled,version,origin}`; origin CONFIGURED/DEMO. Additional fields:

POST 可省略 code，由服务器以类型前缀和自动 UUID 生成；显式旧 code 请求继续兼容。客户端 id 始终拒绝，PATCH 省略 code 保持原值。正式页面不要求人工录入 UUID/code。

- businesses: team_id, owner, critical, watch_order
- models/teams: common only
- clusters: region
- services: model_id, deployment_mode COMBINED/SPLIT_PD
- pd-groups: service_id
- endpoints: service_id, cluster_id, pd_group_id nullable, role ROUTER/PREFILL/DECODE/COMBINED, address_ref
- keys: external_key_ref, masked_label, team_id, business_id nullable, desired_status ACTIVE/SUSPENDED, effective_status NOT_CONNECTED, applied_to_data_plane false
- runtime-members: endpoint_id, cluster_id, namespace, workload_ref, pod_uid/pod_name/node_uid/node_name, observed_at

GET/PUT `/gateway/keys/{id}/model-grants`; GET data `{version,items:[{model_id,enabled:true}],applied_to_data_plane:false}`; PUT `{expected_version,model_ids:[]}` replaces enabled set and increments Key version. GET/PUT `/catalog/businesses/{id}/service-bindings`; same form with service_ids and items service_id. Unknown or forbidden fields rejected. Foreign IDs must be same environment and visible. Version conflict 409 details.current_version. Referenced entity disable requires `confirm_disable:true` (otherwise 409 details references).

Integrations `/integrations/providers` and `/integrations/engine-bindings` share collection/detail verbs and are directly accessible. GET `/integrations/status`: `{providers:[],bindings:[],capabilities,coverage}`. Operational fields are not arbitrary writable health fields.

GET `/topology?focus_type=model&focus_id=UUID` (also business,service,endpoint,key,team,pd_group,cluster). Data `{nodes:[{id,type,name,environment_code}],edges:[{source,target,type}],truncated,limit:{nodes:500,edges:1000}}`; node ids are typed strings `model:UUID`. Edge semantics owns,authorizes,depends_on,serves,member_of_pd,backs_endpoint,runs_in,scheduled_on. Model focus includes upstream business/team/key and downstream actual deployment relations. Runtime members without verified UID do not create confirmed scheduled_on edges.

GET `/screens/bootstrap`: `{data_mode:"live",capabilities,refresh_seconds:10,rotation_seconds:30,environments:[],counts:{teams,businesses,models,clusters,services,pd_groups,endpoints},screens:[{id,title,path}]}`.

Every screen response data contains `{kind,capabilities,coverage:{configured, bound,verified,fresh},data_state,items:[],summary:{},source_window:{start:null,end:null}}`. data_state MISSING/UNMAPPED/UNVERIFIED/FRESH/STALE; capability values `{state:"UNSUPPORTED"|"UNVERIFIED",reason}`. No samples means unknown, never healthy.

- `/screens/overview`: summary catalog counts; items endpoint views below.
- `/screens/pd-groups`: items `{id,name,environment_code,service_id,endpoints:[endpointView],metrics:{prefill_latency_ms,decode_latency_ms,kv_transfer_bytes}}` (unsupported metrics).
- `/screens/infrastructure`: summary `{clusters:integer,telemetry_state:"UNSUPPORTED"}`; items `[]` means unsupported coverage, not zero faults. No node inventory/GPU counts in screen output.
- `/screens/services`: items `{id,name,environment_code,model_id,model_name,endpoints:[endpointView],configured_businesses:[{id,name}]}`. Normal rows are valid; frontend may choose summary/whitespace.
- `/screens/critical-apps`: items `{id,name,owner,watch_order,environment_code,service_ids:[],business_observed_status:"UNKNOWN",dependency_services:[{id,name,endpoints:[endpointView]}],metrics:{availability,latencyP99,requestRate,errorRate,burn},series:[]}`. Business metrics always unsupported pending real business SLI.

endpointView `{id,name,environment_code,service_id,cluster_id,pd_group_id,role,data_state,status:"UNKNOWN"|upstreamStatus,metrics,observation}`. Metric is `{value:number|null,unit,state:"AVAILABLE"|"UNSUPPORTED"|"MISSING",scope:"ENDPOINT"|"POD"}`. Known names ttft_avg_ms/ttft_p90_ms/ttft_p95_ms/ttft_p99_ms, tpot_*, e2e_*, request_rate,request_rate_per_minute,generated_tokens_per_second,input_tokens_per_second,kv_cache_hit_ratio,running,waiting,ttft_e2e_ratio. observation `{binding_id,binding_version,provider_snapshot_id,source_window:{start,end},fetched_at,origin,freshness,max_age_seconds,upstream_status,upstream_evaluation_status,transport_status,provider_id,provider_version,identity}` or null. UI must reevaluate source end age (300s cap), never substitute served_at. Non FRESH status becomes UNKNOWN while raw upstream historical status may remain in observation. No global quantile or cross-endpoint rate sums.

GET `/telemetry/endpoints/{id}/history`: data `{items:[{source_window,metrics}],coverage:"PARTIAL",retention_hours:6,max_points:120}`. GET `/audit-events` directly accessible across environments. `/healthz`,`/readyz` public minimal service checks.

Runtime maintenance: GET/PUT `/catalog/endpoints/{id}/runtime-members`. GET `{version,items:[runtimeMember]}`. PUT `{expected_version,items:[...]}` replaces active members, disables omitted members, and increments Endpoint version. New items carry writable RuntimeMember fields; existing items add id and expected_version. Endpoint/cluster/environment are forced from parent. Maximum 100; all changes/audit are atomic.

Candidate 2 clarification: no service status/active_anomaly and no business potential_impact/healthy_alternative_endpoints are returned. These unapproved cross-Endpoint conclusions are removed, not replaced by another aggregation. configured_businesses and dependency_services are configuration relationships only. Every dependency Endpoint includes its own observation; use min(observation.max_age_seconds,300) for expiry, with source_window.end, independent of served_at. observation.freshness preserves upstream FRESH/STALE, observation.data_state carries local validity. transport_status is OK/UNKNOWN or a bounded internal error code; inspector transport and browser→API transport must be displayed independently. Non-OK transport means last-known values, not a newly confirmed healthy state. Provider edits atomically advance dependent binding versions and old-generation observations disappear immediately.

Approved metrics extension (2026-09-26): `/catalog/hardware-bindings` is directly accessible, with Entity fields plus provider_id, environment_id UUID, resource_type GPU_POOL/HOST, asset_id UUID, host_id, gpu_uuid (required only for GPU_POOL), and read-only binding_version. Same environment, revision, CSRF and audit rules apply. No hardware telemetry writes are exposed to the browser. `/screens/overview` adds `hardware:[{id,name,environment_code,resource_type,asset_id,host_id,gpu_uuid,status:"UNKNOWN",data_state,metrics,observation}]`, scoped to enabled bindings and providers. The existing overview coverage and top-level data_state still describe Endpoint observations; hardware has its own per-device state. Each metric has DEVICE scope and raw unit, quality and collected_at when available; memory_usage_ratio is the approved same-device capacity formula. Only VALID points can be AVAILABLE. observation contains binding/provider generations, explicit device identity, source_window, fixed 300s max age, origin UNVERIFIED, demo boolean, original upstream_status, freshness and transport_status. Current upstream GET lacks origin/environment attestation; no hardware value or Provider setting certifies healthy status. Errors hide current hardware values, retained caches are not current conclusions. The screen checks both source-window and point age. Infrastructure fault output remains unchanged/unsupported. See `docs/approved-metrics-integration.md` for exact source and bounded cache/worker behavior.

## service-entry-v1：整项服务登记

正式Gateway入口使用 `/api/v1/service-entry`，复用匿名direct、同源CSRF、原有envelope和error格式；不写RuntimeMember/采样身份，也不签发Key。请求/响应精确样例见 `.codex/cost-aware/gateway-service-entry-integration-v1/evidence/api-shapes.md`；设计见 `docs/service-entry-integration-design.md`。

- `GET /services?environment_code=&limit=100&cursor=`：service原对象分页目录；`GET /options?environment_code=`：父目录四集合、其版本和metadata_revision。各集合最多10000，超限报错，不静默截断。
- `GET /services/<id>`：单快照包含service、全部groups/endpoints、businesses(binding_enabled)、runtime_members/engine_bindings只读历史、options、expected_versions、metadata_revision。
- `POST /services` / `PUT /services/<id>`：一次服务端原子事务。`expected_metadata_revision`来自读取快照；`expected_versions`键为plural collection加冒号UUID，如`services:uuid`、`pd-groups:uuid`。必须涵盖所有既有组/实例、关系业务及其团队、历史实例集群、原模型和所选existing父资源；允许合并options父资源版本map，额外合法同环境父资源也核对版本；其他服务/组/实例不属于当前快照，拒绝。缺失/未知键拒绝；冲突409保留草稿，不自动覆盖。
- service含name/environment_code/deployment_mode/model_ref；顶层team_ref、business_refs数组、显式remove_business_ids；COMBINED顶层endpoints，SPLIT_PD各groups含endpoints。refs恰好为`{id}`或`{create:{form_key,name,...}}`，所有新id/code在服务端生成。业务create含owner/critical/watch_order，集群create可含region。
- 旧group/endpoint可`{id,unchanged:true}`；`retire_ids:{groups:[],endpoints:[]}`显式退休，退组自动退其活跃实例。其他活跃对象必须明确保留或修改；历史身份不删。旧跨环境关联拒绝，service不迁移环境；新环境限PRD/DR/STG/DEV。历史实例改cluster/group/role时退休旧身份并新建替代，旧members/bindings保持。
- 新Endpoint填写name/role/cluster_ref/namespace/workload_kind/workload_ref/address_ref/configured_nodes；Node≤32个字符串仅配置，不生成人工Pod/NodeUID或健康。
- `GET /templates/services.csv`：独立服务登记模板。`POST /imports/validate {csv}` 返回valid/errors/sha256/metadata_revision/services统计/columns/rows；rows为按columns顺序的字符串数组，结构可解析但语义无效仍返回，error.row对应原始数据行号(从2起)。无写/无实体UUID分配。
- `POST /imports/apply {csv,sha256,expected_metadata_revision}`：摘要/revision核对，重新解析，整批atomic。仅创建，不按名称覆盖。CSV≤2MiB/1000实例行/100服务，每服务≤100实例/20组，同批新父≤300。若任何字段错误全批回滚。
- CSV每行一实例，service_alias聚合服务/group_alias聚合组；父资源引用由existing ID、同环境唯一name、同批新alias三种明确方式解析。alias禁止UUID和id/uuid/code/latest/null/none/auto/system。未知列/人工采样列拒绝；configured_nodes为JSON字符串数组；可在UI修改服务器解析的单元格后重新validate，不复用旧摘要。
- `GET /services/<id>/export`：完整只读JSON，含配置/退休/业务关系（含关系id）/RuntimeMember真实身份/EngineBinding/源快照/PollState/模型Key授权关系；parents含相关团队、模型、历史/当前集群、脱敏Provider，保留其配置身份，不含服务端凭证或无关目录。`?format=csv`为显式标注的active配置复制文件，不含观测、不覆盖既有服务；只支持一个业务关联，无业务或多业务时返回400 `EXPORT_REQUIRES_SINGLE_BUSINESS`，应使用完整JSON查看并从整项服务目录编辑，避免静默丢关联。

所有mutation至多2MiB，请求超限413。保存成功直接返回完整快照；客户端后续目录刷新失败不重发创建，网络结果未知需核对目录。未接入监控的配置状态不标为健康/VERIFIED，来源合同保持。
