"""Explicit scene endpoints; /screens/* and telemetry writes remain untouched."""
import json
from functools import lru_cache
from pathlib import Path
from django.conf import settings
from django.http import JsonResponse
from django.middleware.csrf import get_token
from control import models as m
from control.catalog import serialize,APIError
from control.projections import screen
from control.views import boundary,method,body,envelope
from .models import NodeHardware,CatalogImport,DeploymentIdentity,BusinessPDGroupBinding,PodRegistration,EndpointPodBinding,DeploymentScope,BusinessDeploymentBinding
from .catalog_core import digest,compile_catalog,business_contains_endpoint,NORMALIZATION_VERSION
from .importer import import_catalog,current_revision,verify_import
from .scenario_core import frame
from .recovery import available_plans
from .recovery_core import attach_plans
from .graph_core import augment_topology
from .hardware_core import catalog_hosts,host_context

from .data_files import data_root,read_data

def no_store(response):
    response['Cache-Control']='no-store'
    response['X-Content-Type-Options']='nosniff'
    return response

def gate():
    if not getattr(settings,'PRODUCTION_SCENE_REPLAY_ENABLED',False):
        raise APIError('REPLAY_DISABLED','场景回放未开启',404)

def load_dataset():
    file=data_root()/'szg-8h.json'
    try:stamp=file.stat().st_mtime_ns
    except OSError:read_data('szg-8h.json');raise
    return _load_dataset(str(file),stamp)

@lru_cache(maxsize=1)
def _load_dataset(file,stamp):
    # No request-controlled path, URL, or pickle; validate every shipped window once.
    from .coverage_core import check_dataset
    try:
        data=json.loads(Path(file).read_text(encoding='utf-8'))
        check_dataset(data)
    except (OSError,ValueError,TypeError,KeyError) as exc:
        raise APIError('DATASET_INVALID','8小时场景文件校验失败：'+str(exc),503) from exc
    return data

def catalog_data():
    collections={'teams':m.Team,'businesses':m.Business,'models':m.Model,'clusters':m.KubernetesCluster,'services':m.InferenceService,'pd-groups':m.PDGroup,'endpoints':m.Endpoint}
    # Bounded endpoint prevents silent truncation. Existing paginated APIs remain available.
    output={}
    for key,model in collections.items():
        rows=list(model.objects.filter(enabled=True)[:5001])
        if len(rows)>5000:raise APIError('CATALOG_TOO_LARGE','目录超出此入口的5000对象上限，请使用原分页 API',413)
        output[key]=[serialize(x) for x in rows]
    scopes=[{'id':str(x.pk),'pd_group_id':str(x.pd_group_id),'cluster_id':str(x.cluster_id),
             'namespace':x.namespace,'placement_state':x.placement_state,'placement_note':x.placement_note}
            for x in DeploymentScope.objects.filter(pd_group__enabled=True,cluster__enabled=True).order_by('namespace','id')]
    output['deployment-scopes']=scopes
    for g in output['pd-groups']:
        parts=[x for x in scopes if x['pd_group_id']==g['id']]
        namespaces=list(dict.fromkeys(x['namespace'] for x in parts))
        clusters=list(dict.fromkeys(x['cluster_id'] for x in parts))
        states={x['placement_state'] for x in parts}
        g.update(identity_kind='NAMED_PD_GROUP',deployment_scope_ids=[x['id'] for x in parts],
                 namespaces=namespaces,namespace=namespaces[0] if len(namespaces)==1 else '',
                 cluster_ids=clusters,cluster_id=clusters[0] if len(clusters)==1 else None,
                 placement_state=next(iter(states)) if len(states)==1 else 'MIXED_REPORTED',
                 placement_note='；'.join(dict.fromkeys(x['placement_note'] for x in parts)))
    links=[{'id':str(x.pk),'business_id':str(x.business_id),'pd_group_id':str(x.pd_group_id)}
           for x in BusinessPDGroupBinding.objects.filter(enabled=True,business__enabled=True,
                pd_group__enabled=True,pd_group__service__enabled=True)]
    scope_links=[{'id':str(x.pk),'business_id':str(x.business_id),
                  'deployment_scope_id':str(x.deployment_scope_id),
                  'pd_group_id':str(x.deployment_scope.pd_group_id)}
                 for x in BusinessDeploymentBinding.objects.filter(enabled=True,business__enabled=True,
                    deployment_scope__pd_group__enabled=True).select_related('deployment_scope')]
    output['business-pd-bindings']=links
    output['business-deployment-bindings']=scope_links
    for b in output['businesses']:
        b['pd_group_ids']=[x['pd_group_id'] for x in links if x['business_id']==b['id']]
        b['deployment_scope_ids']=[x['deployment_scope_id'] for x in scope_links if x['business_id']==b['id']]
        b['group_scope_declared']=bool(b['pd_group_ids'])
        # An imported, declared scope that becomes empty must fail closed, not widen to a whole group.
        b['deployment_scope_declared']=bool(b['deployment_scope_ids']) or BusinessPDGroupBinding.objects.filter(business_id=b['id']).exists()
        b['service_ids']=[str(x) for x in m.BusinessServiceBinding.objects.filter(business_id=b['id'],
            enabled=True,service__enabled=True).values_list('service_id',flat=True)]
    pods=[{'id':str(x.pk),'pod_name':x.pod_name,'name':x.pod_name,'cluster_id':str(x.cluster_id),'namespace':x.namespace,'workload_ref':x.workload_ref,'node_name':x.node_name,'identity_state':x.identity_state,'observed_at':None,'pod_uid':None,'node_uid':None} for x in PodRegistration.objects.filter(cluster__enabled=True,enabled=True)]
    elinks=[{'id':str(x.pk),'endpoint_id':str(x.endpoint_id),'pod_id':str(x.pod_id)} for x in EndpointPodBinding.objects.filter(endpoint__enabled=True,endpoint__cluster__enabled=True,pod__enabled=True)]
    output.update(pods=pods,**{'endpoint-pod-bindings':elinks})
    for ep in output['endpoints']:
        ep['pod_ids']=[x['pod_id'] for x in elinks if x['endpoint_id']==ep['id']]
        matches=[x for x in scopes if x['pd_group_id']==ep['pd_group_id'] and x['cluster_id']==ep['cluster_id'] and x['namespace']==ep['namespace']]
        ep['deployment_scope_id']=matches[0]['id'] if len(matches)==1 else None
    for s in output['services']:
        s['configured_businesses']=[{'id':b['id'],'name':b['name'],'pd_group_ids':b['pd_group_ids'],'deployment_scope_ids':b['deployment_scope_ids']} for b in output['businesses'] if s['id'] in b['service_ids']]
    output['business-service-bindings']=[{'business_id':b['id'],'service_id':sid,'evidence_kind':'CONFIGURED'} for b in output['businesses'] for sid in b['service_ids']]
    output['gpu-hosts']=catalog_hosts(output)
    hardware={str(x.pk):x for x in NodeHardware.objects.filter(cluster__enabled=True)}
    for h in output['gpu-hosts']:
        item=hardware.get(h['id'])
        if item:
            h.update(is_gpu_host=item.is_gpu_host,gpu_model=item.gpu_model,
                     gpu_model_source=item.gpu_model_source,version=item.version)
        else:
            h.update(is_gpu_host=False,inventory_source='UNCONFIRMED',version=0)
    return attach_plans(output,available_plans(output))

@boundary
def catalog(request):
    method(request,{'GET'})
    from .catalog_legacy_v3 import compile_catalog as old_compile
    from .catalog_legacy_v4 import compile_catalog as compile_v4
    all_issues=[issue for source in CatalogImport.objects.all() for issue in (compile_catalog if source.normalization_version==5 else compile_v4 if source.normalization_version==4 else old_compile)(source.payload)['issues']]
    response=envelope({'catalog':catalog_data(),'issues':all_issues,'imports':[{'bundle_id':x.bundle_id,'source_hash':x.source_hash,'counts':x.counts,'normalization_version':x.normalization_version} for x in CatalogImport.objects.all()], 'metadata_revision':current_revision(),'csrf_token':get_token(request),'replay_enabled':bool(getattr(settings,'PRODUCTION_SCENE_REPLAY_ENABLED',False))})
    return no_store(response)

@boundary
def source_packet(request):
    method(request,{'GET'})
    return no_store(envelope({'packet':read_data('production-catalog.json'),'metadata_revision':current_revision(),'csrf_token':get_token(request)}))

@boundary
def imports(request,action):
    method(request,{'POST'})
    payload=body(request)
    if set(payload)-{'packet','expected_revision','confirm'}:raise APIError('UNKNOWN_FIELDS','未知导入参数')
    if action not in {'validate','apply'}:raise APIError('NOT_FOUND','导入动作不存在',404)
    if action=='apply' and payload.get('confirm') is not True:raise APIError('CONFIRM_REQUIRED','请明确确认导入')
    try:result=import_catalog(payload.get('packet'),apply=action=='apply',expected_revision=payload.get('expected_revision'))
    except ValueError as exc:raise APIError('INVALID_CATALOG',str(exc))
    return no_store(envelope(result))

def verified_replay():
    """Both read routes share the same immutable catalog and recovery-plan gates."""
    gate();d=load_dataset()
    source=CatalogImport.objects.filter(pk=d['bundle_id']).first()
    if not source:raise APIError('CATALOG_IMPORT_REQUIRED','请先在 Gateway 导入对应生产目录，再开启场景回放',409)
    verify_import(source)
    if source.source_hash!=d['catalog_source_hash']:raise APIError('CATALOG_SOURCE_MISMATCH','目录来源与当前回放不一致，请核对清单',409)
    expected={p['plan_id']:p['content_sha256'] for p in d.get('catalog',{}).get('escape-plans',[])}
    current={p['plan_id']:p['content_sha256'] for p in catalog_data().get('escape-plans',[])}
    if any(current.get(k)!=v for k,v in expected.items()):
        raise APIError('ESCAPE_PLAN_REQUIRED','请在 Gateway 重新确认同一清单，以登记本次双活预案',409)
    return d

@boundary
def dataset(request):
    method(request,{'GET'});d=verified_replay()
    return no_store(JsonResponse(d,json_dumps_params={'ensure_ascii':False,'separators':(',',':')}))

@boundary
def replay_frame(request):
    method(request,{'GET'});d=verified_replay()
    try:value=frame(d,int(request.GET.get('step','390')))
    except ValueError as exc:raise APIError('INVALID_STEP',str(exc))
    return no_store(JsonResponse(value,json_dumps_params={'ensure_ascii':False}))

@boundary
def live(request,kind):
    method(request,{'GET'})
    if kind not in {'overview','services','critical-apps'}:raise APIError('NOT_FOUND','投影不存在',404)
    data=screen(kind,'anonymous');cat=catalog_data()
    ep_lookup={x['id']:x for x in cat['endpoints']}
    def enrich(ep):
        registered=ep_lookup.get(ep['id'],{})
        for k in ['namespace','workload_kind','workload_ref','configured_nodes','pod_ids','deployment_scope_id']:ep[k]=registered.get(k,[] if k in {'configured_nodes','pod_ids'} else '')
        ep.update(host_context({**ep,**registered},cat))
    if kind=='overview':
        data['summary']['managed_gpu_hosts']=sum(h['is_gpu_host'] for h in cat['gpu-hosts'])
        for hardware in data.get('hardware',[]):hardware.update(host_context(hardware,cat))
        for ep in data['items']:enrich(ep)
    elif kind=='services':
        for service in data['items']:
            for ep in service['endpoints']:enrich(ep)
    elif kind=='critical-apps':
        lookup={b['id']:b for b in cat['businesses']}
        for business in data['items']:
            meta=lookup.get(business['id'],{});group_ids=set(meta.get('pd_group_ids',[]))
            business['recovery']=meta.get('recovery',{})
            business['team_id']=meta.get('team_id')
            business['pd_group_ids']=list(group_ids)
            business['deployment_scope_ids']=meta.get('deployment_scope_ids',[])
            business['deployment_scope_declared']=meta.get('deployment_scope_declared',False)
            business['dependency_scope']='DEPLOYMENT_SCOPE' if business['deployment_scope_declared'] else 'PD_GROUP' if group_ids else 'SERVICE'
            for dependency in business['dependency_services']:
                for ep in dependency['endpoints']:enrich(ep)
                if group_ids or business['deployment_scope_declared']:
                    dependency['endpoints']=[ep for ep in dependency['endpoints'] if business_contains_endpoint(meta,ep)]
    if kind=='critical-apps':
        # Fetch candidate targets only once, and never add them to normal dependency metrics.
        service_projection=screen('services','anonymous') if any(b.get('recovery',{}).get('target_group_ids') for b in data['items']) else {'items':[]}
        for business in data['items']:
            targets=set(business.get('recovery',{}).get('target_group_ids',[]))
            business['recovery_dependencies']=[{**service,'endpoints':[ep for ep in service['endpoints'] if ep.get('pd_group_id') in targets]} for service in service_projection['items'] if any(ep.get('pd_group_id') in targets for ep in service['endpoints'])]
    # Hardware evidence is NOT manufactured here. Abnormal-only rendering uses trustworthy upstream states.
    return no_store(envelope(data))

@boundary
def topology(request):
    method(request,{'GET'})
    from control.topology import topology as original_topology
    kind=request.GET.get('focus_type','service');ident=request.GET.get('focus_id','')
    # Original API owns focus validation and existing scope. Only augment within it.
    graph=original_topology('anonymous',kind,ident)
    return no_store(envelope(augment_topology(graph,catalog_data(),kind,ident)))


@boundary
def hardware_inventory(request):
    method(request, {'GET','POST'})
    if request.method=='GET':
        return no_store(envelope({'items':catalog_data()['gpu-hosts'],'metadata_revision':current_revision(),'csrf_token':get_token(request)}))
    payload=body(request)
    allowed={'id','expected_revision','expected_version','gpu_model','is_gpu_host','confirm'}
    if set(payload)!=allowed or payload.get('confirm') is not True:
        raise APIError('INVALID_HARDWARE_INPUT','需要明确确认卡型登记和完整版本字段')
    if not isinstance(payload['gpu_model'],str) or len(payload['gpu_model'])>80 or any(ord(c)<32 for c in payload['gpu_model']):
        raise APIError('INVALID_HARDWARE_INPUT','卡型必须为最长80字符的普通文本')
    if type(payload['is_gpu_host']) is not bool or type(payload['expected_version']) is not int or type(payload['expected_revision']) is not int:
        raise APIError('INVALID_HARDWARE_INPUT','无效的主机类型或版本')
    revision,_=m.Revision.objects.select_for_update().get_or_create(pk=1)
    if revision.metadata != payload['expected_revision']:
        raise APIError('VERSION_CONFLICT','目录版本已变化，请刷新后重试',409)
    obj=NodeHardware.objects.select_for_update().filter(pk=payload['id']).first()
    if not obj:raise APIError('NOT_FOUND','请先导入本版GPU主机目录',404)
    if obj.version!=payload['expected_version']:raise APIError('VERSION_CONFLICT','主机卡型已变化，请刷新',409)
    from control.access import bump,audit
    obj.gpu_model=payload['gpu_model'].strip();obj.gpu_model_source='USER_DECLARED' if obj.gpu_model else 'UNCONFIRMED'
    obj.is_gpu_host=payload['is_gpu_host'];obj.version+=1
    obj.full_clean();obj.save()
    bump('metadata');audit('anonymous','gpu_host_metadata_updated',obj,{'gpu_model':obj.gpu_model,'is_gpu_host':obj.is_gpu_host,'no_telemetry_changes':True})
    return no_store(envelope({'id':str(obj.pk),'version':obj.version,'metadata_revision':current_revision()}))
