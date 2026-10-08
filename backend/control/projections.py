from . import models as m
from .access import scoped,environments
from .telemetry import metric,state,METRICS
CAPABILITIES={x:{'state':'UNSUPPORTED','reason':'巡检来源与能力尚未验证'} for x in ('infrastructure','business_sli','pd_stages')}
CAPABILITIES['endpoint_performance']={'state':'UNVERIFIED','reason':'真实只读接入尚未验收'}
def qs(model,user):return scoped(model.objects.filter(enabled=True),user)
def counts(user):return {name:qs(model,user).count() for name,model in [('teams',m.Team),('businesses',m.Business),('models',m.Model),('clusters',m.KubernetesCluster),('services',m.InferenceService),('pd_groups',m.PDGroup),('endpoints',m.Endpoint)]}
def endpoint_view(e):
    from .monitoring import csv_endpoint
    if e.cluster.monitoring_source=="CSV":return csv_endpoint(e)
    bindings=list(m.EngineBinding.objects.filter(endpoint=e,enabled=True,provider__enabled=True).select_related('provider').order_by('code'))
    # More than one binding cannot be silently merged or arbitrarily selected.
    binding=bindings[0] if len(bindings)==1 else None
    snapshot=m.TelemetrySnapshot.objects.filter(binding=binding,binding_version=binding.binding_version).order_by('-source_end').first() if binding else None
    payload=snapshot.payload if snapshot else None
    # Legacy payloads without configuration generation cannot certify current trust.
    if payload and payload['observation'].get('provider_version')!=binding.provider.version:payload=None
    s=state(payload) if binding else 'UNMAPPED'
    metrics=payload['metrics'] if payload else {k:metric(None,v[2],'MISSING') for k,v in METRICS.items()}
    observation={**payload['observation'],'source_type':'INSPECTION'} if payload else None
    if observation:
        poll=m.PollState.objects.filter(binding=binding).first()
        observation['transport_status']=poll.error or 'OK' if poll else 'UNKNOWN'
        if poll and poll.error in {'IDENTITY_MISMATCH','INVALID_WINDOW','CLOCK_SKEW','CONTRACT_INCOMPATIBLE','INVALID_METRIC','MISSING_METRIC','INVALID_PERCENTILES','INVALID_FRESHNESS','INVALID_QUALITY','INVALID_JSON','SNAPSHOT_MUTATED','INVALID_SNAPSHOT_ID','NORMALIZED_TOO_LARGE'}:s='INVALID'
        observation['data_state']=s
    return {'id':str(e.pk),'name':e.name,'environment_code':e.environment_code,'service_id':str(e.service_id),'cluster_id':str(e.cluster_id),'pd_group_id':str(e.pd_group_id) if e.pd_group_id else None,'role':e.role,'source_type':'INSPECTION','data_state':s,'status':observation['upstream_status'] if s=='FRESH' else 'UNKNOWN','metrics':metrics,'observation':observation}
def screen(kind,user):
    endpoints=[endpoint_view(x) for x in qs(m.Endpoint,user).filter(cluster__enabled=True).select_related('cluster')]
    coverage={'configured':len(endpoints),'bound':sum(x['data_state']!='UNMAPPED' for x in endpoints),'verified':sum(bool(x['observation'] and x['observation']['origin']=='VERIFIED') for x in endpoints),'fresh':sum(x['data_state']=='FRESH' for x in endpoints)}
    ends=[x['observation']['source_window']['end'] for x in endpoints if x['observation']]
    result={'kind':kind,'capabilities':CAPABILITIES,'coverage':coverage,'data_state':'INVALID' if any(x['data_state']=='INVALID' for x in endpoints) else 'FRESH' if endpoints and coverage['fresh']==len(endpoints) else 'STALE' if any(x['data_state']=='STALE' for x in endpoints) else 'UNVERIFIED' if ends else 'MISSING','items':[],'summary':{},'source_window':{'start':None,'end':min(ends) if ends else None}}
    from .monitoring import csv_hardware
    sources={x.monitoring_source for x in qs(m.KubernetesCluster,user)}
    result['source_type']='MIXED' if len(sources)>1 else next(iter(sources),'INSPECTION')
    if result['source_type']=='CSV' and ends:result['data_state']='CSV_SNAPSHOT'
    if kind=='overview':
        from .hardware import hardware_view
        result.update(items=endpoints,summary=counts(user),hardware=[hardware_view(x) for x in qs(m.HardwareBinding,user).filter(provider__enabled=True,cluster__enabled=True,cluster__monitoring_source='INSPECTION').select_related('provider','cluster')]+[h for c in qs(m.KubernetesCluster,user).filter(monitoring_source='CSV') for h in csv_hardware(c)])
    elif kind=='pd-groups':
        result['items']=[{'id':str(p.pk),'name':p.name,'environment_code':p.environment_code,'service_id':str(p.service_id),'endpoints':[e for e in endpoints if e['pd_group_id']==str(p.pk)],'metrics':{k:metric() for k in ('prefill_latency_ms','decode_latency_ms','kv_transfer_bytes')}} for p in qs(m.PDGroup,user)]
    elif kind=='infrastructure':result['summary']={'clusters':qs(m.KubernetesCluster,user).count(),'telemetry_state':'UNSUPPORTED'}
    elif kind=='services':
        for s in qs(m.InferenceService,user).select_related('model'):
            es=[e for e in endpoints if e['service_id']==str(s.pk)];bs=qs(m.Business,user).filter(businessservicebinding__service=s,businessservicebinding__enabled=True)
            result['items'].append({'id':str(s.pk),'name':s.name,'environment_code':s.environment_code,'model_id':str(s.model_id),'model_name':s.model.name,'endpoints':es,'configured_businesses':[{'id':str(b.pk),'name':b.name} for b in bs]})
    elif kind=='critical-apps':
        for b in qs(m.Business,user).filter(critical=True).order_by('watch_order'):
            services=list(qs(m.InferenceService,user).filter(businessservicebinding__business=b,businessservicebinding__enabled=True));ids=[str(x.pk) for x in services]
            dependencies=[{'id':str(service.pk),'name':service.name,'endpoints':[e for e in endpoints if e['service_id']==str(service.pk)]} for service in services]
            result['items'].append({'id':str(b.pk),'name':b.name,'owner':b.owner,'watch_order':b.watch_order,'environment_code':b.environment_code,'service_ids':ids,'business_observed_status':'UNKNOWN','dependency_services':dependencies,'metrics':{k:metric() for k in ('availability','latencyP99','requestRate','errorRate','burn')},'series':[]})
    for item in result.get('hardware',[]):
        if item.get('observation'):ends.append(item['observation']['source_window']['end'])
    if result['source_type']=='CSV' and ends:result['data_state']='CSV_SNAPSHOT'
    result['source_window']['end']=min(ends) if ends else None
    return result
