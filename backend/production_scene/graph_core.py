"""Configured edges, including the business→service relationship even without keys.
Input is already scoped by the existing topology API. This does not discover resources.
"""
from copy import deepcopy
from .catalog_core import business_contains_endpoint

def augment_topology(graph,catalog,focus_type='',focus_id=''):
    graph=deepcopy(graph);nodes={n['id']:n for n in graph.get('nodes',[])}
    edges=list(graph.get('edges',[]))
    def add(source,target,kind,**extra):
        if source in nodes and target in nodes and not any(e['source']==source and e['target']==target and e['type']==kind for e in edges):
            edges.append({'source':source,'target':target,'type':kind,'evidence_kind':'CONFIGURED',**extra})
    for g in catalog.get('pd-groups',[]):
        key='pd_group:'+g['id']
        if key not in nodes:continue
        nodes[key].update({k:g.get(k,'') for k in ['namespace','namespaces','deployment_scope_ids','cluster_id','service_id','placement_state']})
        add('service:'+g['service_id'],key,'contains_pd_group')
    for ep in catalog.get('endpoints',[]):
        key='endpoint:'+ep['id']
        if key not in nodes:continue
        nodes[key].update({k:ep.get(k,'') for k in ['namespace','role','pd_group_id','deployment_scope_id','cluster_id','workload_ref']})
        if ep.get('pd_group_id'):add('pd_group:'+ep['pd_group_id'],key,'contains_endpoint')
    for b in catalog.get('businesses',[]):
        for sid in b.get('service_ids',[]):add('business:'+b['id'],'service:'+sid,'depends_on')
        for gid in b.get('pd_group_ids',[]):add('business:'+b['id'],'pd_group:'+gid,'deployed_on')
    # Scope deployment details using registered group membership, never shared-model proximity.
    allowed_groups=None;allowed_businesses=None;focused_business=None
    if focus_type=='business':
        business=next((b for b in catalog.get('businesses',[]) if b['id']==focus_id),None)
        if business and business.get('pd_group_ids'):
            allowed_groups=set(business['pd_group_ids']);allowed_businesses={focus_id};focused_business=business
    elif focus_type=='pd_group':
        if any(g['id']==focus_id for g in catalog.get('pd-groups',[])):allowed_groups={focus_id}
    elif focus_type=='endpoint':
        ep=next((e for e in catalog.get('endpoints',[]) if e['id']==focus_id),None)
        if ep and ep.get('pd_group_id'):allowed_groups={ep['pd_group_id']}
    if allowed_groups is not None:
        allowed_eps={e['id'] for e in catalog.get('endpoints',[]) if e.get('pd_group_id') in allowed_groups}
        if focused_business is not None:allowed_eps&={e['id'] for e in catalog.get('endpoints',[]) if business_contains_endpoint(focused_business,e)}
        if focus_type=='endpoint':allowed_eps&={focus_id}
        if allowed_businesses is None:
            allowed_businesses={b['id'] for b in catalog.get('businesses',[]) if any(e['id'] in allowed_eps and business_contains_endpoint(b,e) for e in catalog.get('endpoints',[]))}
        allowed_teams={b['team_id'] for b in catalog.get('businesses',[]) if b['id'] in allowed_businesses}
        allowed_members={e['source'] for e in edges if e['type']=='backs_endpoint' and e['target'] in {'endpoint:'+i for i in allowed_eps}}
        allowed_nodes={e['target'] for e in edges if e['type']=='scheduled_on' and e['source'] in allowed_members}
        def keep(key,n):
            ident=key.split(':',1)[1]
            if n['type']=='pd_group':return ident in allowed_groups
            if n['type']=='endpoint':return ident in allowed_eps
            if n['type']=='business':return ident in allowed_businesses
            if n['type']=='team':return ident in allowed_teams
            if n['type'] in ('pod','runtime_member'):return key in allowed_members
            if n['type']=='node':return key in allowed_nodes
            return True
        nodes={k:v for k,v in nodes.items() if keep(k,v)}
    for g in catalog.get('pd-groups',[]):
        node=nodes.get('pd_group:'+g['id'])
        if node is not None:
            visible_eps=[ep for ep in catalog.get('endpoints',[]) if ep.get('pd_group_id')==g['id'] and 'endpoint:'+ep['id'] in nodes]
            shown=list(dict.fromkeys(ep['namespace'] for ep in visible_eps if ep.get('namespace')))
            node['visible_namespaces']=shown
            node['namespace']=' / '.join(shown or g.get('namespaces',[]))
    edges=[e for e in edges if e['source'] in nodes and e['target'] in nodes]
    return {**graph,'nodes':list(nodes.values()),'edges':edges,'relation_scope':'CONFIGURED','business_service_direct':True}

def catalog_graph(catalog,focus_type='service',focus_id=''):
    """Offline screenshot fixture from the same catalog FKs, not inferred proximity."""
    types={'teams':'team','businesses':'business','models':'model','services':'service','pd-groups':'pd_group','endpoints':'endpoint','clusters':'cluster'}
    nodes=[{**row,'id':typ+':'+row['id'],'type':typ} for col,typ in types.items() for row in catalog.get(col,[]) if row.get('enabled') is not False]
    edges=[]
    for b in catalog.get('businesses',[]):edges.append({'source':'team:'+b['team_id'],'target':'business:'+b['id'],'type':'owns'})
    for s in catalog.get('services',[]):edges.append({'source':'model:'+s['model_id'],'target':'service:'+s['id'],'type':'serves'})
    for ep in catalog.get('endpoints',[]):
        edges.append({'source':'service:'+ep['service_id'],'target':'endpoint:'+ep['id'],'type':'serves'})
        edges.append({'source':'endpoint:'+ep['id'],'target':'cluster:'+ep['cluster_id'],'type':'runs_in'})
    return augment_topology({'nodes':nodes,'edges':edges,'truncated':False},catalog,focus_type,focus_id)
