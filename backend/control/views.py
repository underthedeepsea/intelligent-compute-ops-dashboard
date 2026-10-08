import json,uuid
from functools import wraps
from django.http import JsonResponse
from django.contrib.auth import authenticate,login,logout
from django.middleware.csrf import get_token
from django.db import transaction,IntegrityError,connection
from django.core.exceptions import ValidationError
from django.core import signing
from django.db.models import Q
from django.utils import timezone
from . import models as m
from .access import roles,environments,scoped,repeatable_read
from .local_access import local_request_allowed,configured_identity,SESSION_MARKER,session_identity
from .catalog import APIError,COLLECTIONS,serialize,find,save,replace_relations
from .projections import screen,counts,CAPABILITIES
from .topology import topology

def error(code,message,status=400,details=None):return JsonResponse({'error':{'code':code,'message':message,'request_id':str(uuid.uuid4()),'details':details or {}}},status=status)
def csrf_failure(request,reason=''):return error('CSRF_FAILED','CSRF 校验失败',403)
def envelope(data,status=200):
    r=m.Revision.objects.filter(pk=1).first()
    return JsonResponse({'schema_version':'1.0','view_revision':r.view if r else 0,'metadata_revision':r.metadata if r else 0,'telemetry_revision':r.telemetry if r else 0,'served_at':timezone.now().isoformat(),'data':data},status=status)
def body(request):
    try:
        d=json.loads(request.body or b'{}',parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
        if not isinstance(d,dict):raise ValueError()
        return d
    except (ValueError,UnicodeDecodeError):raise APIError('INVALID_JSON','请求必须为 JSON 对象')
def boundary(fn):
    @wraps(fn)
    def wrapped(request,*args,**kwargs):
        try:
            with transaction.atomic():
                if request.method=='GET':repeatable_read()
                return fn(request,*args,**kwargs)
        except APIError as e:return error(e.code,e.message,e.status,e.details)
        except ValidationError as e:return error('VALIDATION_ERROR','数据校验失败',400,{'fields':e.message_dict if hasattr(e,'message_dict') else e.messages})
        except IntegrityError:return error('CONFLICT','唯一约束或关联冲突',409)
        except (ValueError,TypeError):return error('INVALID_ARGUMENT','参数格式无效')
    return wrapped

def require(request,allowed):
    if not request.user.is_authenticated:raise APIError('UNAUTHENTICATED','请先登录',401)
    if not roles(request.user)&set(allowed):raise APIError('FORBIDDEN','无此操作权限',403)
def method(request,allowed):
    if request.method not in allowed:raise APIError('METHOD_NOT_ALLOWED','不支持此方法',405)
def session_data(request):return {'authenticated':request.user.is_authenticated,'username':request.user.get_username() if request.user.is_authenticated else None,'roles':sorted(roles(request.user)) if request.user.is_authenticated else [],'environments':environments(request.user) if request.user.is_authenticated else [],'csrf_token':get_token(request),'data_mode':'live','local_passwordless_available':local_request_allowed(request)}
@boundary
def session(request,action=None):
    if action=='local':
        method(request,{'POST'})
        if body(request):raise APIError('INVALID_ARGUMENT','免密入口不接受身份参数')
        if not local_request_allowed(request):raise APIError('LOCAL_ACCESS_DISABLED','此入口未启用本地免密访问',403)
        if not request.user.is_authenticated:
            user=configured_identity()
            login(request,user,backend='django.contrib.auth.backends.ModelBackend')
            request.session[SESSION_MARKER]=session_identity(user)
            m.AuditEvent.objects.create(actor=user.username,action='local_session_start',entity_id=str(user.pk),environment_code=environments(user)[0],changes={'mode':'local_passwordless'})
    elif action=='login':
        method(request,{'POST'});data=body(request)
        if set(data)!={'username','password'} or not all(isinstance(v,str) for v in data.values()):raise APIError('INVALID_LOGIN','登录参数无效')
        user=authenticate(request,username=data['username'],password=data['password'])
        if not user:raise APIError('INVALID_CREDENTIALS','用户名或密码错误',401)
        login(request,user)
    elif action=='logout':method(request,{'POST'});logout(request)
    elif action is None:method(request,{'GET'})
    else:raise APIError('NOT_FOUND','会话入口不存在',404)
    response=envelope(session_data(request))
    response['Cache-Control']='no-store'
    return response
@boundary
def catalog(request,collection,pk=None):
    model=COLLECTIONS.get(collection)
    if not model:raise APIError('NOT_FOUND','目录不存在',404)
    restricted=collection in {'providers','engine-bindings','hardware-bindings'}
    require(request,{'catalog_admin'} if restricted or request.method!='GET' else {'catalog_admin','operator'})
    method(request,{'GET','PATCH'} if pk else {'GET','POST'})
    if request.method in {'POST','PATCH'}:return envelope(serialize(save(model,request.user,body(request),pk)),201 if not pk else 200)
    if pk:return envelope(serialize(find(model,request.user,pk)))
    q=scoped(model.objects.all(),request.user).order_by('code','id');env=request.GET.get('environment_code')
    if env:q=q.filter(environment_code=env)
    limit=int(request.GET.get('limit','100'))
    if not 1<=limit<=100:raise APIError('INVALID_LIMIT','limit 应为 1–100')
    cursor=request.GET.get('cursor')
    if cursor:
        try:c=signing.loads(cursor,salt='catalog-cursor');code,uid=c['code'],c['id']
        except (signing.BadSignature,KeyError):raise APIError('INVALID_CURSOR','游标无效')
        if c['collection']!=collection or c.get('environment')!=env:raise APIError('INVALID_CURSOR','游标范围不一致')
        q=q.filter(Q(code__gt=code)|Q(code=code,id__gt=uid))
    rows=list(q[:limit+1]);next_cursor=None
    if len(rows)>limit:
        last=rows[limit-1];next_cursor=signing.dumps({'code':last.code,'id':str(last.pk),'collection':collection,'environment':env},salt='catalog-cursor')
    return envelope({'items':[serialize(x) for x in rows[:limit]],'next_cursor':next_cursor})
@boundary
def relations(request,pk,kind):
    require(request,{'catalog_admin'} if request.method!='GET' else {'catalog_admin','operator'});method(request,{'GET','PUT'})
    obj=find(m.ApiKeyRef if kind=='grants' else m.Business,request.user,pk)
    if request.method=='PUT':obj=replace_relations(request.user,obj,body(request),kind)
    if kind=='grants':items=[{'model_id':str(x.model_id),'enabled':x.enabled} for x in m.KeyModelGrant.objects.filter(key=obj,enabled=True)]
    else:items=[{'service_id':str(x.service_id),'enabled':x.enabled} for x in m.BusinessServiceBinding.objects.filter(business=obj,enabled=True)]
    return envelope({'version':obj.version,'items':items,'applied_to_data_plane':False})
@boundary
def topology_view(request):
    require(request,{'catalog_admin','operator'});method(request,{'GET'})
    return envelope(topology(request.user,request.GET.get('focus_type'),request.GET.get('focus_id')))
@boundary
def screens(request,kind):
    require(request,{'catalog_admin','operator','screen_viewer'});method(request,{'GET'})
    names=[('overview','智算总览'),('pd-groups','PD 运行诊断'),('infrastructure','基础设施异常'),('services','推理服务异常'),('critical-apps','关键应用守望')]
    if kind=='bootstrap':return envelope({'data_mode':'live','capabilities':CAPABILITIES,'refresh_seconds':10,'rotation_seconds':30,'environments':environments(request.user),'counts':counts(request.user),'screens':[{'id':str(i+1).zfill(2),'title':title,'path':'/api/v1/screens/'+name} for i,(name,title) in enumerate(names)]})
    if kind not in dict(names):raise APIError('NOT_FOUND','屏幕不存在',404)
    return envelope(screen(kind,request.user))
@boundary
def status(request):
    require(request,{'catalog_admin','operator'});method(request,{'GET'})
    bindings=[]
    for b in scoped(m.EngineBinding.objects.all(),request.user):
        p=m.PollState.objects.filter(binding=b).first()
        bindings.append({'id':str(b.pk),'name':b.name,'binding_version':b.binding_version,'last_attempt_at':p.last_attempt_at if p else None,'last_success_at':p.last_success_at if p else None,'error':p.error if p else 'NOT_POLLED','paused':p.paused if p else False})
    return envelope({'providers':[{'id':str(p.pk),'name':p.name,'origin_verified':p.origin_verified} for p in scoped(m.ProviderInstance.objects.all(),request.user)],'bindings':bindings,'capabilities':CAPABILITIES,'coverage':screen('overview',request.user)['coverage']})
@boundary
def history(request,pk):
    require(request,{'catalog_admin','operator'});method(request,{'GET'});e=find(m.Endpoint,request.user,pk)
    if not e.enabled or not e.cluster.enabled:return envelope({'items':[],'coverage':'MISSING','retention_hours':6,'max_points':120})
    if e.cluster.monitoring_source=='CSV':
        from .monitoring import csv_endpoint
        item=csv_endpoint(e);observation=item['observation']
        return envelope({'items':[{'source_window':observation['source_window'],'metrics':item['metrics'],'source_type':'CSV','data_state':'CSV_SNAPSHOT'}] if observation else [],'coverage':'CSV_SNAPSHOT','source_type':'CSV','retention_hours':None,'max_points':1})
    from datetime import timedelta
    rows=m.TelemetrySnapshot.objects.filter(binding__endpoint=e,binding__enabled=True,source_end__gte=timezone.now()-timedelta(hours=6)).order_by('-source_end')
    items=[]
    for x in rows.select_related('binding')[:120]:
        if x.binding_version==x.binding.binding_version:items.append({'source_window':x.payload['observation']['source_window'],'metrics':x.payload['metrics']})
    return envelope({'items':items,'coverage':'PARTIAL','retention_hours':6,'max_points':120})
@boundary
def audit_events(request):
    require(request,{'catalog_admin','auditor'});method(request,{'GET'})
    return envelope({'items':list(scoped(m.AuditEvent.objects.all(),request.user).order_by('-id').values('id','occurred_at','actor','action','entity_id','environment_code','changes')[:100]),'next_cursor':None})
def health(request,ready=False):
    if request.method!='GET':return error('METHOD_NOT_ALLOWED','不支持此方法',405)
    if ready:
        try:
            with connection.cursor() as c:c.execute('SELECT 1')
        except Exception:return JsonResponse({'status':'unavailable'},status=503)
    return JsonResponse({'status':'ok'})

@boundary
def runtime_members(request,pk):
    require(request,{'catalog_admin'} if request.method!='GET' else {'catalog_admin','operator'});method(request,{'GET','PUT'})
    endpoint=find(m.Endpoint,request.user,pk)
    if request.method=='PUT':
        from .catalog import version
        from .access import bump,audit
        data=body(request)
        if set(data)!={'expected_version','items'} or not isinstance(data['items'],list) or len(data['items'])>100:raise APIError('INVALID_MEMBERS','items 必须为最多100项数组')
        m.Revision.objects.select_for_update().get_or_create(pk=1)
        endpoint=find(m.Endpoint,request.user,pk,True);version(endpoint,data)
        seen=set()
        for item in data['items']:
            if not isinstance(item,dict):raise APIError('INVALID_MEMBERS','成员必须为对象')
            fields=dict(item);member_id=fields.pop('id',None)
            if member_id:
                member=find(m.RuntimeMember,request.user,member_id)
                if member.endpoint_id!=endpoint.pk:raise APIError('WRONG_ENDPOINT','成员不属于此 Endpoint')
            if member_id in seen:raise APIError('DUPLICATE','重复成员')
            if member_id:seen.add(member_id)
            fields.update(endpoint_id=str(endpoint.pk),cluster_id=str(endpoint.cluster_id),environment_code=endpoint.environment_code)
            member=save(m.RuntimeMember,request.user,fields,member_id)
            seen.add(str(member.pk))
        existing=m.RuntimeMember.objects.filter(endpoint=endpoint,enabled=True).exclude(pk__in=seen)
        for member in existing:save(m.RuntimeMember,request.user,{'expected_version':member.version,'enabled':False,'confirm_disable':True},member.pk)
        endpoint.version+=1;endpoint.save(update_fields=['version']);bump('metadata');audit(request.user,'replace_members',endpoint,{'member_ids':sorted(seen),'version':endpoint.version})
    return envelope({'version':endpoint.version,'items':[serialize(x) for x in m.RuntimeMember.objects.filter(endpoint=endpoint,enabled=True)]})
