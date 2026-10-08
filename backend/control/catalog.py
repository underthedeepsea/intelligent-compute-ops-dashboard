from datetime import date,datetime
from django.core.exceptions import ValidationError
from django.db import transaction
from . import models as m
from .access import scoped,bump,audit,environments

COLLECTIONS={'teams':m.Team,'businesses':m.Business,'models':m.Model,'clusters':m.KubernetesCluster,'services':m.InferenceService,'pd-groups':m.PDGroup,'endpoints':m.Endpoint,'runtime-members':m.RuntimeMember,'keys':m.ApiKeyRef,'providers':m.ProviderInstance,'engine-bindings':m.EngineBinding,'hardware-bindings':m.HardwareBinding}
class APIError(Exception):
    def __init__(self,code,message,status=400,details=None): self.code,self.message,self.status,self.details=code,message,status,details or {}
def serialize(obj):
    result={}
    for f in obj._meta.fields:
        if f.name in {'credential_ref','base_url_ref'}: continue
        v=getattr(obj,f.attname)
        if isinstance(v,(datetime,date)):v=v.isoformat()
        result[f.attname]=str(v) if f.get_internal_type()=='UUIDField' or f.is_relation and v is not None else v
    if isinstance(obj,m.ApiKeyRef): result['applied_to_data_plane']=False
    return result

def find(model,user,pk,lock=False):
    q=scoped(model.objects.all(),user)
    if lock:q=q.select_for_update()
    try:return q.get(pk=pk)
    except (model.DoesNotExist,ValueError,ValidationError):raise APIError('NOT_FOUND','对象不存在',404)
def version(obj,payload):
    if type(payload.get('expected_version')) is not int: raise APIError('VERSION_REQUIRED','expected_version 必填')
    if obj.version!=payload['expected_version']:raise APIError('VERSION_CONFLICT','对象已更新，请重新读取',409,{'current_version':obj.version})

def save(model,user,payload,pk=None,origin=None):
    with transaction.atomic():
        m.Revision.objects.select_for_update().get_or_create(pk=1)
        obj=find(model,user,pk,True) if pk else model()
        if pk:version(obj,payload)
        before=serialize(obj) if pk else {}
        allowed={f.attname:f for f in model._meta.fields if f.editable and not f.primary_key}
        unknown=set(payload)-set(allowed)-({'expected_version','confirm_disable'} if pk else set())
        if unknown:raise APIError('UNKNOWN_FIELDS','不允许的字段',details={'fields':sorted(unknown)})
        for key,value in payload.items():
            if key not in allowed:continue
            f=allowed[key]
            if f.is_relation and value is not None:
                related=find(f.remote_field.model,user,value)
                setattr(obj,f.name,related)
            else:setattr(obj,key,value)
        if not user.is_superuser and obj.environment_code not in environments(user):raise APIError('FORBIDDEN','无此环境权限',403)
        if pk and obj.environment_code!=before['environment_code']:raise APIError('IMMUTABLE_ENVIRONMENT','已有对象不能移动环境')
        if pk and before['enabled'] and not obj.enabled:
            refs=[]
            for rel in obj._meta.related_objects:
                q=getattr(obj,rel.get_accessor_name()).all() if not rel.one_to_one else None
                if q is not None and q.exists():refs.append(rel.related_model.__name__)
            if refs and payload.get('confirm_disable') is not True:raise APIError('REFERENCED_ENTITY','停用前请确认关联影响',409,{'references':refs})
        if pk:
            obj.version+=1
            if isinstance(obj,(m.EngineBinding,m.HardwareBinding)):obj.binding_version+=1
        if origin:obj.origin=origin
        obj.full_clean();obj.save()
        # A parent edit must not invalidate existing children.
        for rel in obj._meta.related_objects:
            if rel.related_model in COLLECTIONS.values() and not rel.one_to_one:
                for child in getattr(obj,rel.get_accessor_name()).all():child.full_clean()
        if isinstance(obj,m.ProviderInstance) and pk:
            # Provider identity/trust is part of every dependent observation generation.
            for binding in m.EngineBinding.objects.select_for_update().filter(provider=obj):
                binding.binding_version+=1;binding.version+=1
                binding.save(update_fields=['binding_version','version'])
                m.PollState.objects.filter(binding=binding).update(paused=False,next_due=None,error='',failures=0,last_attempt_at=None,last_success_at=None)
            for binding in m.HardwareBinding.objects.select_for_update().filter(provider=obj):
                binding.binding_version+=1;binding.version+=1
                binding.save(update_fields=['binding_version','version'])
                m.HardwareObservation.objects.filter(binding=binding).update(payload={},paused=False,next_due=None,error='',failures=0,last_attempt_at=None,last_success_at=None)
        if isinstance(obj,m.HardwareBinding):
            m.HardwareObservation.objects.filter(binding=obj).update(payload={},paused=False,next_due=None,error='',failures=0,last_attempt_at=None,last_success_at=None)
        if isinstance(obj,m.EngineBinding):
            m.PollState.objects.filter(binding=obj).update(paused=False,next_due=None,error='',failures=0,last_attempt_at=None,last_success_at=None)
        if pk and isinstance(obj,(m.Endpoint,m.KubernetesCluster)):
            from .monitoring import invalidate_bindings
            invalidate_bindings(cluster=obj if isinstance(obj,m.KubernetesCluster) else None,endpoint=obj if isinstance(obj,m.Endpoint) else None)
        after=serialize(obj)
        changes={k:{'old':before.get(k),'new':v} for k,v in after.items() if before.get(k)!=v and k not in {'external_key_ref','address_ref'}}
        audit(user,'update' if pk else 'create',obj,changes);bump('metadata')
        return obj

def replace_relations(user,obj,payload,kind):
    with transaction.atomic():
        m.Revision.objects.select_for_update().get_or_create(pk=1)
        obj=find(type(obj),user,obj.pk,True);version(obj,payload)
        if kind=='grants':target,relation,parent,field,ids=m.Model,m.KeyModelGrant,'key','model','model_ids'
        else:target,relation,parent,field,ids=m.InferenceService,m.BusinessServiceBinding,'business','service','service_ids'
        if set(payload)!={'expected_version',ids} or not isinstance(payload[ids],list) or len(payload[ids])>100:raise APIError('INVALID_RELATIONS','关系集合格式无效')
        targets=[find(target,user,x) for x in payload[ids]]
        if len({str(x.pk) for x in targets})!=len(targets):raise APIError('DUPLICATE','重复关系')
        if any(x.environment_code!=obj.environment_code for x in targets):raise APIError('CROSS_ENVIRONMENT','关系环境必须一致')
        old=list(relation.objects.filter(**{parent:obj,'enabled':True}).values_list(field+'_id',flat=True))
        relation.objects.filter(**{parent:obj}).update(enabled=False)
        for x in targets:relation.objects.update_or_create(**{parent:obj,field:x},defaults={'enabled':True})
        obj.version+=1;obj.save(update_fields=['version']);bump('metadata')
        audit(user,'replace_'+kind,obj,{'old':[str(x) for x in old],'new':[str(x.pk) for x in targets],'version':obj.version})
        return obj
