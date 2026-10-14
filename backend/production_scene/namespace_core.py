"""Pure consolidation plan for the specifically confirmed v5→v4 namespace typo."""
from .catalog_core import digest


def namespace_plan(before, after):
    a, b = before['catalog'], after['catalog']
    if {(g['id'],g['name']) for g in a['pd-groups']} != {(g['id'],g['name']) for g in b['pd-groups']}:
        raise ValueError('namespace纠正不得改变逻辑PD组身份')
    if {x['id'] for x in a['businesses']} != {x['id'] for x in b['businesses']}:
        raise ValueError('namespace纠正不得改变业务身份')
    mappings = {}
    def ns(value): return value.replace('pd-server-dsv5flash-fallback', 'pd-server-dsv4flash-fallback')
    fields = {'deployment-scopes': ['pd_group_id','cluster_id','namespace'],
              'endpoints': ['pd_group_id','cluster_id','namespace','role','workload_ref'],
              'pods': ['cluster_id','namespace','pod_name']}
    for kind, keys in fields.items():
        dest = {tuple(x.get(k) for k in keys): x for x in b[kind]}
        mapping = {}
        for x in a[kind]:
            key = tuple(ns(x.get(k,'')) if k=='namespace' else x.get(k) for k in keys)
            y = dest.get(key)
            if y is None: raise ValueError('缺少明确的namespace目标: '+x['id'])
            if kind=='endpoints' and set(x['configured_nodes']) != set(y['configured_nodes']):
                raise ValueError('同名工作负载节点列表冲突')
            if kind=='pods' and x['node_name'] != y['node_name']:
                raise ValueError('同名Pod节点冲突')
            mapping[x['id']] = y['id']
        mappings[kind] = mapping
    retired = [x for x,y in mappings['endpoints'].items() if x!=y]
    return {'reason':'USER_CONFIRMED_ALL_NAMESPACES_V4', 'maps':mappings,
            'retired_endpoint_ids':retired, 'preserved_endpoint_ids':[x for x,y in mappings['endpoints'].items() if x==y],
            'before_counts':before['counts'],'after_counts':after['counts'],
            'telemetry_changes':False}
