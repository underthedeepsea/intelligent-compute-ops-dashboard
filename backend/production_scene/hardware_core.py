"""Host inventory and card model metadata are user-declared, not automatic discovery."""
from .catalog_legacy_v2 import identity


def catalog_hosts(catalog):
    hosts = {}
    for ep in catalog.get('endpoints', []):
        if ep.get('enabled') is False:
            continue
        for name in ep.get('configured_nodes', []):
            key = (ep['environment_code'], ep['cluster_id'], name)
            item = hosts.setdefault(key, {
                'id': identity('managed-gpu-host', *key), 'name': name, 'node_name': name,
                'environment_code': key[0], 'cluster_id': key[1], 'enabled': True,
                'is_gpu_host': True, 'inventory_source': 'USER_DECLARED_PD_HOST',
                'gpu_model': '', 'gpu_model_source': 'UNCONFIRMED',
                'roles': [], 'endpoint_ids': [], 'pd_group_ids': [],
            })
            for field, value in [('roles', ep['role']), ('endpoint_ids', ep['id']), ('pd_group_ids', ep['pd_group_id'])]:
                if value not in item[field]:
                    item[field].append(value)
    return sorted(hosts.values(), key=lambda h: (h['environment_code'], h['cluster_id'], h['node_name']))



def host_context(entity, catalog):
    is_host = entity.get('resource_type') in {'HOST', 'GPU_POOL'}
    names = ([entity.get('node_name') or entity.get('host_id')] if is_host else entity.get('configured_nodes', []))
    names = set(n for n in names if n)
    rows = [h for h in catalog.get('gpu-hosts', []) if h['node_name'] in names
            and h['cluster_id'] == entity.get('cluster_id')
            and h.get('environment_code') == entity.get('environment_code')]
    roles = sorted({r for h in rows for r in h.get('roles', [])}) if is_host else [entity.get('role', 'UNKNOWN')]
    return {'host_roles': roles, 'gpu_models': sorted({h['gpu_model'] for h in rows if h.get('gpu_model')}),
            'gpu_model_sources': sorted({h.get('gpu_model_source', 'UNCONFIRMED') for h in rows}),
            'managed_host_ids': [h['id'] for h in rows], 'configured_host_count': len(rows)}
