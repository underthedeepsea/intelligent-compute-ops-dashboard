from urllib.parse import quote

from . import models as m
from .access import scoped
from .catalog import APIError
TYPES={'team':m.Team,'business':m.Business,'model':m.Model,'key':m.ApiKeyRef,'service':m.InferenceService,'endpoint':m.Endpoint,'pd_group':m.PDGroup,'cluster':m.KubernetesCluster,'pod':m.RuntimeMember}
def topology(user,focus_type,focus_id):
    if focus_type not in {*TYPES, 'node'}:raise APIError('INVALID_FOCUS','不支持的节点类型')
    nodes={};edges=[]
    for kind,model in TYPES.items():
        for x in scoped(model.objects.filter(enabled=True),user):
            key=f'{kind}:{x.pk}';nodes[key]={'id':key,'type':kind,'name':x.name,'environment_code':x.environment_code,'origin':x.origin,'evidence_kind':x.origin}
    def edge(a,b,kind):
        if a in nodes and b in nodes:edges.append({'source':a,'target':b,'type':kind})
    for b in scoped(m.Business.objects.filter(enabled=True),user):edge(f'team:{b.team_id}',f'business:{b.pk}','owns')
    for k in scoped(m.ApiKeyRef.objects.filter(enabled=True),user):
        edge(f'team:{k.team_id}',f'key:{k.pk}','owns')
        if k.business_id:edge(f'business:{k.business_id}',f'key:{k.pk}','owns')
    for g in m.KeyModelGrant.objects.filter(enabled=True):edge(f'key:{g.key_id}',f'model:{g.model_id}','authorizes')
    for g in m.BusinessServiceBinding.objects.filter(enabled=True):edge(f'business:{g.business_id}',f'service:{g.service_id}','depends_on')
    for s in scoped(m.InferenceService.objects.filter(enabled=True),user):edge(f'model:{s.model_id}',f'service:{s.pk}','serves')
    for e in scoped(m.Endpoint.objects.filter(enabled=True),user):
        edge(f'service:{e.service_id}',f'endpoint:{e.pk}','serves');edge(f'endpoint:{e.pk}',f'cluster:{e.cluster_id}','runs_in')
        if e.pd_group_id:edge(f'endpoint:{e.pk}',f'pd_group:{e.pd_group_id}','member_of_pd')
    for p in scoped(m.RuntimeMember.objects.filter(enabled=True),user):
        edge(f'pod:{p.pk}',f'endpoint:{p.endpoint_id}','backs_endpoint')
        if p.pod_uid and p.node_uid and p.observed_at and p.origin in ('CONFIGURED','DEMO') and f'cluster:{p.cluster_id}' in nodes and f'endpoint:{p.endpoint_id}' in nodes:
            node_token=('DEMO:' if p.origin=='DEMO' else '')+quote(p.node_uid, safe='')
            nid=f'node:{p.cluster_id}:{node_token}';nodes[nid]={'id':nid,'type':'node','name':p.node_name,'environment_code':p.environment_code,'origin':p.origin,'evidence_kind':p.origin}
            edge(f'pod:{p.pk}',nid,'scheduled_on');edge(nid,f'cluster:{p.cluster_id}','runs_in')
    focus=f'{focus_type}:{focus_id}'
    if focus not in nodes:raise APIError('NOT_FOUND','对象不存在',404)
    # Directional ancestry and descendants separately: no sibling expansion through shared team/cluster.
    selected={focus}
    for direction in ('up','down'):
        frontier={focus}
        # A node points to its cluster, while pods point to their endpoint. Seed
        # only the endpoints actually backed by this node before walking their
        # ancestors; never reverse-walk from the shared cluster.
        if focus_type in ('node', 'pod') and direction == 'up':
            pods=({e['source'] for e in edges if e['type']=='scheduled_on' and e['target']==focus} if focus_type == 'node' else {focus})
            frontier|={e['target'] for e in edges if e['type']=='backs_endpoint' and e['source'] in pods}
        seen=set(frontier)
        while frontier:
            next_set=set()
            for e in edges:
                a,b=(e['target'],e['source']) if direction=='up' else (e['source'],e['target'])
                if a in frontier and b not in seen:next_set.add(b)
            seen|=next_set;frontier=next_set
        selected|=seen
    # Incoming membership is a deployment relation, not a graph-wide reverse walk.
    members={e['source'] for e in edges if e['type']=='backs_endpoint' and e['target'] in selected}
    if focus_type == 'node':
        members&={e['source'] for e in edges if e['type']=='scheduled_on' and e['target']==focus}
        selected-={key for key in selected if key.startswith('pod:') and key not in members}
    selected|=members
    selected|={e['target'] for e in edges if e['type']=='scheduled_on' and e['source'] in members}
    # Include configured business dependants of selected services.
    business_ids={e['source'] for e in edges if e['type']=='depends_on' and e['target'] in selected}
    selected|=business_ids
    selected|={e['source'] for e in edges if e['type']=='owns' and e['target'] in business_ids}
    chosen=sorted(selected)[:500];links=[e for e in edges if e['source'] in chosen and e['target'] in chosen]
    return {'nodes':[nodes[x] for x in chosen],'edges':links[:1000],'truncated':len(selected)>500 or len(links)>1000,'limit':{'nodes':500,'edges':1000}}
