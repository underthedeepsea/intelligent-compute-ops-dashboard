"""Plan the explicit A:R screenshot revision, independent of ORM."""

def revision_plan(before, after):
    a,b=before['catalog'],after['catalog']
    for kind in ('teams','businesses','models','clusters','services'):
        if {x['id'] for x in a[kind]} != {x['id'] for x in b[kind]}:
            raise ValueError('目录修订不可改变核心归属身份: '+kind)
    changes={}
    for kind in ('pd-groups','deployment-scopes','endpoints','pods','endpoint-pod-bindings','gpu-hosts'):
        old={x['id']:x for x in a[kind]}; new={x['id']:x for x in b[kind]}
        changes[kind]={'added':sorted(new.keys()-old.keys()),'retired':sorted(old.keys()-new.keys())}
        if kind in ('pd-groups','deployment-scopes','endpoints') and changes[kind]['retired']:
            raise ValueError('这次修订只能新增组/入口，不可移除已有身份')
    # No metrics can be reparented silently. Pod label correction is a separate audit.
    new_ep={e['id']:e for e in b['endpoints']}
    for ep in a['endpoints']:
        peer=new_ep[ep['id']]
        for k in ('pd_group_id','cluster_id','namespace','role','workload_ref','configured_nodes'):
            if ep[k]!=peer[k]: raise ValueError('旧入口身份/节点发生漂移: '+ep['id'])
    changed_pod_eps=[e['id'] for e in a['endpoints'] if set(e['pod_ids'])!=set(new_ep[e['id']]['pod_ids'])]
    return {'reason':'USER_SCREENSHOTS_20261013_COLUMNS_A_R','before_counts':before['counts'],
            'after_counts':after['counts'],'changes':changes,'pod_alias_changed_endpoints':changed_pod_eps,
            'preserved_endpoint_ids':sorted(e['id'] for e in a['endpoints']),
            'telemetry_changed':False,'automatic_switch':False}
