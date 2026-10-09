import json
from django.http import HttpResponse
from django.core import signing
from django.db.models import Q
from django.core.exceptions import RequestDataTooBig
from . import models as m
from .catalog import APIError,serialize
from .views import boundary,envelope,body,method
from . import service_entry as entry
from . import service_entry_csv as batch


def payload(request):
    try:
        if len(request.body)>batch.MAX_BYTES:raise APIError('LIMIT_EXCEEDED','请求最多2MiB',413)
        return body(request)
    except RequestDataTooBig:raise APIError('LIMIT_EXCEEDED','请求最多2MiB',413)

@boundary
def services(request,pk=None):
    method(request,{'GET','PUT'} if pk else {'GET','POST'})
    if request.method in {'POST','PUT'}:return envelope(entry.write(payload(request),pk),200 if pk else 201)
    if pk:return envelope(entry.snapshot(entry.get_service(pk)))
    env=request.GET.get('environment_code');limit=int(request.GET.get('limit','100'))
    if not 1<=limit<=100:raise APIError('INVALID_LIMIT','limit应为1–100')
    q=m.InferenceService.objects.all().order_by('code','id')
    if env:q=q.filter(environment_code=env)
    cursor=request.GET.get('cursor')
    if cursor:
        try:
            c=signing.loads(cursor,salt='service-entry-cursor')
            if c['env']!=env:raise ValueError()
            q=q.filter(Q(code__gt=c['code'])|Q(code=c['code'],id__gt=c['id']))
        except (signing.BadSignature,ValueError,KeyError):raise APIError('INVALID_CURSOR','游标无效')
    rows=list(q[:limit+1]);next_cursor=None
    if len(rows)>limit:
        last=rows[limit-1];next_cursor=signing.dumps({'env':env,'code':last.code,'id':str(last.pk)},salt='service-entry-cursor')
    return envelope({'items':[serialize(x) for x in rows[:limit]],'next_cursor':next_cursor})

@boundary
def options(request):
    method(request,{'GET'});env=entry.text(request.GET.get('environment_code',''),'environment_code',80)
    return envelope(entry.options(env))

@boundary
def imports(request,action):
    method(request,{'POST'});data=payload(request)
    if action=='validate':
        entry.fields(data,{'csv'},{'csv'});return envelope(batch.validate(data['csv']))
    if action=='apply':return envelope(batch.apply(data),201)
    raise APIError('NOT_FOUND','批量操作不存在',404)

@boundary
def template(request):
    method(request,{'GET'});response=HttpResponse('\ufeff'+batch.template(),content_type='text/csv; charset=utf-8')
    response['Content-Disposition']='attachment; filename="service-entry-template.csv"';return response

@boundary
def export(request,pk):
    method(request,{'GET'});service=entry.get_service(pk)
    if request.GET.get('format')=='csv':
        response=HttpResponse('\ufeff'+batch.export_csv(service),content_type='text/csv; charset=utf-8')
        response['Content-Disposition']='attachment; filename="service-configuration-copy-no-observations.csv"'
        response['X-Export-Scope']='configuration-copy-not-observations'
        return response
    if request.GET.get('format') not in {None,'json'}:raise APIError('INVALID_FORMAT','仅支持json/csv')
    data=entry.snapshot(service)
    # All persisted source snapshots remain read-only; never offered as writable imports.
    relations=list(m.BusinessServiceBinding.objects.filter(service=service).select_related('business'))
    data['business_bindings']=[serialize(x) for x in relations]
    data['telemetry_snapshots']=[serialize(x) for x in m.TelemetrySnapshot.objects.filter(binding__endpoint__service=service)]
    data['poll_states']=[serialize(x) for x in m.PollState.objects.filter(binding__endpoint__service=service)]
    data['key_model_grants']=[serialize(x) for x in m.KeyModelGrant.objects.filter(model=service.model)]
    data['parents']={
        'teams':[serialize(x) for x in m.Team.objects.filter(pk__in={r.business.team_id for r in relations})],
        'models':[serialize(service.model)],
        'clusters':[serialize(x) for x in m.KubernetesCluster.objects.filter(endpoint__service=service).distinct()],
        'providers':[serialize(x) for x in m.ProviderInstance.objects.filter(enginebinding__endpoint__service=service).distinct()],
    }
    data.pop('options',None)
    response=HttpResponse(json.dumps(data,ensure_ascii=False,default=str),content_type='application/json; charset=utf-8')
    response['Content-Disposition']='attachment; filename="service-complete-readonly.json"';return response
