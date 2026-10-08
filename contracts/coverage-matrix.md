# Source and capability coverage

Baseline: `underthedeepsea/iaas-inspection-platform` commit `c62c55cccd72009dbc79e8a52fc848cf3cb93f56`. API source `apps/inference_performance/api.py::serialize_profile` and metrics source `schemas.py::METRIC_FIELDS/parse_sample` were read from that fixed commit on 2026-09-26. This is source compatibility evidence, not a recorded production response. `fixtures/synthetic/` is synthetic only; no recorded fixtures exist.

| Upstream path | Control metric | Unit | State |
|---|---|---|---|
| current_metrics.ttft.{avg,p90,p95,p99}_ms | ttft_{stat}_ms | ms | source-supported, real chain unverified |
| current_metrics.tpot.{avg,p90,p95,p99}_ms | tpot_{stat}_ms | ms/token | source-supported, real chain unverified |
| current_metrics.e2e.{avg,p90,p95,p99}_ms | e2e_{stat}_ms | ms | source-supported, real chain unverified |
| current_metrics.ttft.e2e_ratio | ttft_e2e_ratio | ratio | source-supported |
| current_metrics.traffic.qps / qpm | request_rate / request_rate_per_minute | requests/s / requests/min | source-supported |
| current_metrics.throughput.generation_tps / prompt_tps | generated_tokens_per_second / input_tokens_per_second | tokens/s | source-supported |
| current_metrics.cache.kv_cache_hit_rate | kv_cache_hit_ratio | ratio | source-supported |
| current_metrics.requests.running / waiting | running / waiting | requests | source-supported |
| status / evaluation_status | upstream_status / upstream_evaluation_status | categorical | copied; no new thresholds |
| engine, window, freshness, plugin, quality | identity/time/quality | original semantics | source-supported |
| provenance.source/sample_id/ingested_at | origin proof | n/a | absent from baseline; read extension required |
| GPU/NIC/node risk, P/D stages, business SLI | nullable unsupported metrics | n/a | future collection, not available |

No sums, means, maxima, synthesized business SLI or cross-Endpoint latency calculation are implemented. Additional monitor calculations require the user's decision. Catalog counts and coverage counts describe configuration/quality only. Source-window age determines stale state; served_at is never sample time. The baseline plugin is inference-performance 1.0.0; unknown versions remain UNVERIFIED. Administrator origin_verified alone is insufficient: the source allowlist, provenance, supported plugin and non-DEMO origin must also hold.

Blockers for M0/M5: actual URL/environment/read-only identity, trusted ingestion provenance, real sample and full business→service→Endpoint→cluster/PD→engine binding chain. No upstream write endpoint is called. The upstream service requires its own enforced GET-only authorization; a locally emitted bearer header does not prove that enforcement.

Hardware extension source: `AI-inspect` commit `b28a8090d4538593e2ad41d8ecfeda0fa2af3739`, `apps/hardware_health`. Source-code compatibility only; no real response or provenance proof. `GET /api/v1/hardware-health/profiles` provides up to200 latest devices per environment/resource_type; GPU_POOL is single GPU. Only 01 CPU/GPU utilization, GPU temperature and approved GPU/host memory utilization formulas are connected. Values require VALID quality and unexpired window/point times. Hardware always UNVERIFIED/UNKNOWN health; no source collection agent exists in that module. Xid/ECC/03 fault rows, filesystem/disk, GPU power/clocks, NIC, cluster aggregation remain unconnected. 02 E2E P99/TTFT P95/TTFT e2e ratio/TPOT P95 now occupy the four approved bottom slots; no additive latency or cross-Endpoint computation. Details: `docs/approved-metrics-integration.md`.
