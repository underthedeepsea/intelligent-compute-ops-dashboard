"""Exhaustive, dependency-free dataset coverage validation; no network or writes."""
from collections import Counter
from datetime import datetime
import math
from .catalog_core import digest, business_contains_endpoint
from .scenario_core import frame, EP_METRICS, HOST_METRICS

EXPECTED_NAMES = {'pd-server-dsv4flash-01','pd-server-dsv4flash-02','pd-server-dsv4flash-fallback'}

def check_dataset(data):
    def require(condition, message):
        if not condition: raise ValueError(message)
    copy = dict(data); signature = copy.pop('content_sha256', None)
    require(digest(copy) == signature, '数据文件 SHA-256 不匹配')
    require(data.get('normalization_version') == 3, '目录不是 v3 三组身份')
    require(data.get('origin') == 'SYNTHETIC', '回放来源必须与生产来源隔离')
    require(data.get('steps') == 960 and data.get('step_seconds') == 30, '必须为 960 个 30 秒窗口')
    require(len(data.get('samples', [])) == 960, '采样窗口缺失')
    start, end = datetime.fromisoformat(data['start']), datetime.fromisoformat(data['end'])
    require(start.tzinfo is not None and end.tzinfo is not None and (end-start).total_seconds() == 28800, '8 小时范围无效')
    cat = data['catalog']; groups = cat['pd-groups']; eps = cat['endpoints']; scopes = cat['deployment-scopes']
    require(len(groups) == 3 and {g['name'] for g in groups} == EXPECTED_NAMES, '必须是三个明确命名的 PD Group')
    for key, rows in cat.items():
        if key == 'escape-plans': continue
        require(len({x['id'] for x in rows}) == len(rows), '重复对象 ID：' + key)
    require(len(scopes) == 4 and len(eps) == 8 and len(cat['pods']) == 22 and len(data['nodes']) == 12, '部署、入口、Pod 或节点缺失')
    require(len(cat['businesses']) == 6 and len(cat['business-pd-bindings']) == 9, '业务或组关联缺失')
    scope_map = {d['id']:d for d in scopes}; ids = {g['id'] for g in groups}
    for ep in eps:
        scope = scope_map.get(ep.get('deployment_scope_id'))
        require(scope and ep['pd_group_id'] in ids and scope['pd_group_id'] == ep['pd_group_id'], '入口组/部署引用失效')
        require(ep['namespace'] == scope['namespace'] and ep['cluster_id'] == scope['cluster_id'], '入口跨 namespace 或集群')
        require(ep['pod_ids'], '入口没有 Pod 登记')
    require(data['endpoint_metrics'] == EP_METRICS and data['host_metrics'] == HOST_METRICS, '指标键或单位与合同不一致')
    status_counts = Counter(); quality_counts = Counter(); rows_per_group = {}
    for group in groups:
        indexes = [i for i,ep in enumerate(eps) if ep['pd_group_id'] == group['id']]
        require(indexes and any(eps[i]['role']=='PREFILL' for i in indexes) and any(eps[i]['role']=='DECODE' for i in indexes), '组没有完整 P/D 数据')
        rows_per_group[group['id']] = indexes
    group_states = {g['id']:Counter() for g in groups}
    for step, sample in enumerate(data['samples']):
        require(len(sample.get('e', [])) == 8 and len(sample.get('h', [])) == 12, f'窗口 {step} 的对象数不完整')
        for kind, keys in [('e', EP_METRICS), ('h', HOST_METRICS)]:
            for index, row in enumerate(sample[kind]):
                require(len(row.get('v', [])) == len(keys), f'{step}/{kind}/{index} 指标不完整')
                require(all(type(v) in (int,float) and math.isfinite(v) and v>=0 for v in row['v']), f'{step}/{kind}/{index} 有空、布尔、非有限或负值')
                values = dict(zip(keys, row['v']))
                require(all(values[k] <= 1 for k,unit in keys.items() if unit=='ratio'), '比例越界')
                if kind == 'e':
                    status_counts[row['s']] += 1; quality_counts[row['q']] += 1
                    for family in ['ttft','tpot','e2e']:
                        require(values[f'{family}_p90_ms'] <= values[f'{family}_p95_ms'] <= values[f'{family}_p99_ms'], '分位数顺序无效')
                    if row['q'] != 'REPLAY':
                        require(row['s']=='UNKNOWN' and not row['hits'] and row['at']<step, '失联窗口被当成当前有效值')
                        require(row['v'] == data['samples'][row['at']]['e'][index]['v'], '失联时篡改历史数值')
        for gid,indexes in rows_per_group.items():
            states = [sample['e'][i]['s'] for i in indexes]
            status = 'CRITICAL' if 'CRITICAL' in states else 'WARNING' if 'WARNING' in states else 'UNKNOWN' if 'UNKNOWN' in states else 'NORMAL'
            group_states[gid][status] += 1
    default = frame(data, data['default_step'])['projections']; current_eps = default['overview']['data']['items']
    apps = []
    for business in cat['businesses']:
        rows = [ep for ep in eps if business_contains_endpoint(business,ep)]
        require(rows and {ep['role'] for ep in rows} == {'PREFILL','DECODE'}, '业务缺少 P/D 观测：'+business['name'])
        require(len(rows) == (4 if len(business['pd_group_ids'])==2 else 2), '业务部署范围被意外扩大')
        apps.append({'name':business['name'],'pd_group_ids':business['pd_group_ids'],
                     'deployment_scope_ids':business['deployment_scope_ids'],'endpoints':len(rows),
                     'windows':960,'source_numeric_values':len(rows)*960*20})
    group_report = []
    for group in groups:
        indexes = rows_per_group[group['id']]; states = [current_eps[i]['status'] for i in indexes]
        state = 'CRITICAL' if 'CRITICAL' in states else 'WARNING' if 'WARNING' in states else 'NORMAL'
        group_report.append({'id':group['id'],'name':group['name'],'namespaces':group['namespaces'],
            'deployment_scopes':len(group['deployment_scope_ids']),'endpoints':len(indexes),
            'prefill_endpoints':sum(eps[i]['role']=='PREFILL' for i in indexes),
            'decode_endpoints':sum(eps[i]['role']=='DECODE' for i in indexes),
            'windows':960,'metrics_per_endpoint':20,'numeric_values':len(indexes)*960*20,
            'window_states':dict(group_states[group['id']]),'default_state':state})
    faults = lambda rows: sum(x['status'] in {'WARNING','CRITICAL','FAIL','ERROR'} for x in rows)
    return {'result':'PASS','normalization_version':3,'dataset_sha256':signature,
            'start':data['start'],'end':data['end'],'steps':960,'step_seconds':30,
            'logical_pd_groups':3,'deployment_scopes':4,'endpoint_snapshots':7680,
            'host_snapshots':11520,'endpoint_numeric_values':153600,'host_numeric_values':34560,
            'endpoint_quality_counts':dict(quality_counts),'endpoint_status_counts':dict(status_counts),
            'groups':group_report,'businesses':apps,
            'default_window':{'step':data['default_step'],'window':default['overview']['data']['source_window'],
                'screen03_abnormal_objects':faults(default['overview']['data']['hardware']),
                'screen04_abnormal_objects':faults(current_eps),'screen05_businesses':len(apps)},
            'limits':{'not_a_production_telemetry_verification':True,
                'outage_uses_last_known_values_with_original_time':True,
                'normal_windows_intentionally_empty_on_03_04':True}}
