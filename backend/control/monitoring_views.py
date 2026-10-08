from pathlib import Path
from django.http import HttpResponse
from . import models as m
from .access import scoped
from .catalog import APIError,serialize
from .views import boundary,require,method,body,envelope
from .monitoring import cluster_summary,switch_source,import_csv,COLUMNS

@boundary
def clusters(request):
    require(request,{'catalog_admin','operator'});method(request,{'GET'})
    return envelope({'items':[cluster_summary(c) for c in scoped(m.KubernetesCluster.objects.filter(enabled=True),request.user)]})

@boundary
def options(request):
    require(request,{'catalog_admin'});method(request,{'GET'})
    return envelope({name:[serialize(x) for x in scoped(model.objects.filter(enabled=True),request.user)] for name,model in [('providers',m.ProviderInstance),('models',m.Model),('services',m.InferenceService),('pd_groups',m.PDGroup)]})

@boundary
def source(request,pk):
    require(request,{'catalog_admin'});method(request,{'PATCH'})
    return envelope(switch_source(request.user,pk,body(request)))

@boundary
def imports(request,action):
    require(request,{'catalog_admin'});method(request,{'POST'})
    if action not in ('validate','apply'):raise APIError('NOT_FOUND','导入入口不存在',404)
    return envelope(import_csv(request.user,body(request),apply=action=='apply'))

@boundary
def template(request,kind):
    require(request,{'catalog_admin','operator'});method(request,{'GET'})
    if kind not in COLUMNS:raise APIError('NOT_FOUND','模板不存在',404)
    content=(Path(__file__).resolve().parents[2]/'templates'/f'{kind}.csv').read_bytes()
    response=HttpResponse(content,content_type='text/csv; charset=utf-8')
    response['Content-Disposition']=f'attachment; filename="{kind}.csv"'
    response['Cache-Control']='no-store'
    return response
