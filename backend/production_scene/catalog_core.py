"""Pure, deterministic screenshot-catalog compiler. No database or network access.
Blank runtime identity is not forward-filled. Namespace is part of deployment identity, NOT logical PD Group identity.
"""
from __future__ import annotations
import hashlib
import json
import re
import uuid
from copy import deepcopy

NS = uuid.UUID('985a5f86-0167-4bd7-a2d6-cb1c57e58121')
MAX_ROWS = 2000

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)

def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()

def identity(kind, *parts):
    return str(uuid.uuid5(NS, canonical([kind, *parts])))

def text(value, label, maximum=240, empty=False):
    if not isinstance(value, str) or value != value.strip() or (not value and not empty) or len(value)>maximum or any(ord(c)<32 for c in value):
        raise ValueError(f'{label}: 必须为首尾无空格的有效文本（最长 {maximum}）')
    return value

NORMALIZATION_VERSION = 5


def compile_catalog(packet):
    """Compile user-declared PD names into logical groups, retaining physical scope.

    The frozen v2 compiler is used only to preserve physical Endpoint/Pod IDs and
    original row validation. Logical identity is (environment, service, PD name).
    Two namespaces can belong to ONE PD group; they never share metrics or Pod IDs.
    """
    from .catalog_physical import compile_catalog as physical_compile
    if isinstance(packet, dict) and any(r.get('namespace')=='pd-server-dsv5flash-fallback' for r in packet.get('rows',[]) if isinstance(r,dict)):
        raise ValueError('namespace已由用户确认统一为pd-server-dsv4flash-fallback，请加载本版清单。')
    raw_packet = deepcopy(packet)
    clean_packet = deepcopy(packet)
    for r in clean_packet.get('rows', []):
        for stage in ('prefill','decode'):
            part = r.get(stage, {})
            if 'gpu_model' in part:
                text(part['gpu_model'], 'gpu_model', 80, True)
                part.pop('gpu_model')
    old = physical_compile(clean_packet)
    old['source_hash'] = digest(raw_packet)
    out = deepcopy(old)
    cat = out['catalog']
    env = out['environment_code']
    groups = {}
    aliases = {}
    scopes = []
    old_groups = old['catalog']['pd-groups']
    for g in old_groups:
        gid = identity('pd-group-logical', env, g['service_id'], g['name'])
        aliases[g['id']] = gid
        if gid not in groups:
            groups[gid] = {
                'id': gid, 'code': 'szg-pdgroup-' + gid[:18],
                'name': g['name'], 'environment_code': env,
                'enabled': True, 'origin': 'REGISTERED',
                'service_id': g['service_id'], 'identity_kind': 'NAMED_PD_GROUP',
                'deployment_scope_ids': [], 'namespaces': [], 'cluster_ids': [],
                'legacy_group_ids': [],
            }
        row = groups[gid]
        row['deployment_scope_ids'].append(g['id'])
        row['legacy_group_ids'].append(g['id'])
        if g['namespace'] not in row['namespaces']: row['namespaces'].append(g['namespace'])
        if g['cluster_id'] not in row['cluster_ids']: row['cluster_ids'].append(g['cluster_id'])
        scopes.append({**g, 'code': 'szg-scope-' + g['id'][:18],
                       'pd_group_id': gid, 'identity_kind': 'DEPLOYMENT_SCOPE'})
    for g in groups.values():
        parts = [s for s in scopes if s['pd_group_id'] == g['id']]
        states = {s['placement_state'] for s in parts}
        g.update(namespace=g['namespaces'][0] if len(g['namespaces']) == 1 else '',
                 cluster_id=g['cluster_ids'][0] if len(g['cluster_ids']) == 1 else None,
                 placement_state=next(iter(states)) if len(states) == 1 else 'MIXED_REPORTED',
                 placement_note='；'.join(dict.fromkeys(s['placement_note'] for s in parts)))
    cat['pd-groups'] = list(groups.values())
    cat['deployment-scopes'] = scopes
    cat['business-deployment-bindings'] = []
    group_links = {}
    for link in old['catalog']['business-pd-bindings']:
        gid = aliases[link['pd_group_id']]
        ident = identity('business-pd-bindings', env, link['business_id'], gid)
        group_links[ident] = {**link, 'id': ident,
            'code': 'szg-business-' + ident[:18], 'pd_group_id': gid}
        scope_id = link['pd_group_id']
        did = identity('business-deployment-bindings', env, link['business_id'], scope_id)
        cat['business-deployment-bindings'].append({**link, 'id': did,
            'code': 'szg-bizscope-' + did[:18], 'deployment_scope_id': scope_id,
            'pd_group_id': gid})
    cat['business-pd-bindings'] = list(group_links.values())
    for ep in cat['endpoints']:
        ep['deployment_scope_id'] = ep['pd_group_id']
        ep['pd_group_id'] = aliases[ep['pd_group_id']]
    for b in cat['businesses']:
        b['pd_group_ids'] = list(dict.fromkeys(aliases[i] for i in b['pd_group_ids']))
        b['deployment_scope_ids'] = [l['deployment_scope_id'] for l in cat['business-deployment-bindings']
                                     if l['business_id'] == b['id']]
        b['group_scope_declared'] = True
        b['deployment_scope_declared'] = True
    by_business = {b['id']: b for b in cat['businesses']}
    for s in cat['services']:
        for b in s['configured_businesses']:
            original = by_business[b['id']]
            b['pd_group_ids'] = original['pd_group_ids']
            b['deployment_scope_ids'] = original['deployment_scope_ids']
    for r in out['source_rows']:
        r['deployment_scope_id'] = r['pd_group_id']
        r['pd_group_id'] = aliases[r['pd_group_id']]
    for issue in out['issues']:
        if issue.get('group_id') in aliases:
            issue['deployment_scope_id'] = issue['group_id']
            issue['group_id'] = aliases[issue['group_id']]
    out['counts'].update({key: len(cat[key]) for key in
        ['pd-groups', 'deployment-scopes', 'business-pd-bindings', 'business-deployment-bindings']})
    out['counts']['named_pd_groups'] = len(groups)
    out['normalization_version'] = NORMALIZATION_VERSION
    out['legacy_group_map'] = aliases
    from .hardware_core import catalog_hosts
    cat['gpu-hosts'] = catalog_hosts(cat)
    source_cards = {}
    for r in raw_packet['rows']:
        for stage in ('prefill','decode'):
            p = r[stage]
            if p['node'] and p.get('gpu_model'):
                key = (r['cluster'],p['node'])
                if key in source_cards and source_cards[key] != p['gpu_model']:
                    raise ValueError('同一主机卡型冲突: '+p['node'])
                source_cards[key] = p['gpu_model']
    clusters = {c['id']: c['name'] for c in cat['clusters']}
    for h in cat['gpu-hosts']:
        model = source_cards.get((clusters[h['cluster_id']],h['node_name']))
        if model: h.update(gpu_model=model, gpu_model_source='USER_SCREENSHOT')
    out['issues'].extend(deepcopy(raw_packet.get('source',{}).get('cell_conflicts',[])))
    out['counts']['managed_gpu_hosts'] = len(cat['gpu-hosts'])
    return out


def business_contains_endpoint(business, endpoint):
    """Scope filters refine logical membership, never create another PD Group."""
    if endpoint.get('pd_group_id') not in business.get('pd_group_ids', []):
        return False
    if business.get('deployment_scope_declared'):
        return endpoint.get('deployment_scope_id') in business.get('deployment_scope_ids', [])
    return True
