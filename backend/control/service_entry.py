"""Whole-service configuration. Runtime observations are never written here."""
import copy,re,uuid
from django.db import transaction,OperationalError
from django.db.models import F
from django.core.exceptions import ValidationError
from . import models as m
from .catalog import APIError,serialize,COLLECTIONS
from .access import audit

PARENTS={'teams':m.Team,'businesses':m.Business,'models':m.Model,'clusters':m.KubernetesCluster}
MAX_OPTIONS=10000
NEW_ENVS={'PRD','DR','STG','DEV'}

def reject(code,message,**details):
    raise APIError(code,message,400,details)

def fields(value,allowed,required=()):
    if not isinstance(value,dict):reject('INVALID_ARGUMENT','必须为对象')
    unknown=set(value)-set(allowed)
    if unknown:reject('UNKNOWN_FIELDS','不允许的字段',fields=sorted(unknown))
    missing=set(required)-set(value)
    if missing:reject('MISSING_FIELDS','缺少字段',fields=sorted(missing))

def uid(value):
    try:return str(uuid.UUID(str(value)))
    except (ValueError,TypeError,AttributeError):reject('INVALID_ID','无效目录身份')

def text(value,label,limit=240,required=True):
    if not isinstance(value,str) or len(value)>limit or (required and not value.strip()) or any(ord(c)<32 for c in value):reject('INVALID_FIELD',label+'无效',field=label)
    return value.strip()

def revision():
    r=m.Revision.objects.filter(pk=1).first()
    return r.metadata if r else 0

def version_map(objects):
    result={}
    for obj in objects:
        kind=next(k for k,v in COLLECTIONS.items() if isinstance(obj,v))
        result[kind+':'+str(obj.pk)]=obj.version
    return result

def options(env):
    result={};objects=[]
    for kind,model in PARENTS.items():
        rows=list(model.objects.filter(environment_code=env).order_by('name','id')[:MAX_OPTIONS+1])
        if len(rows)>MAX_OPTIONS:reject('OPTIONS_LIMIT','当前环境目录超过可编辑上限，请缩小目录')
        result[kind]=[serialize(x) for x in rows];objects+=rows
    return {'environment_code':env,'options':result,'expected_versions':version_map(objects),'metadata_revision':revision()}

def get_service(pk):
    try:return m.InferenceService.objects.get(pk=uid(pk))
    except m.InferenceService.DoesNotExist:raise APIError('NOT_FOUND','服务不存在',404)

def snapshot(service):
    groups=list(m.PDGroup.objects.filter(service=service));endpoints=list(m.Endpoint.objects.filter(service=service))
    relations=list(m.BusinessServiceBinding.objects.filter(service=service).select_related('business'))
    opt=options(service.environment_code)
    objects=[service,*groups,*endpoints,*[x.business for x in relations]]
    versions={**opt['expected_versions'],**version_map(objects)}
    return {'service':serialize(service),'groups':[serialize(x) for x in groups],'endpoints':[serialize(x) for x in endpoints],
        'businesses':[dict(serialize(x.business),binding_enabled=x.enabled) for x in relations],
        'runtime_members':[serialize(x) for x in m.RuntimeMember.objects.filter(endpoint__service=service)],
        'engine_bindings':[serialize(x) for x in m.EngineBinding.objects.filter(endpoint__service=service)],
        'expected_versions':versions,'metadata_revision':revision(),'options':opt['options']}

def acquire(expected):
    if type(expected) is not int or expected<0:reject('VERSION_REQUIRED','expected_metadata_revision 必须为非负整数')
    updated=m.Revision.objects.filter(pk=1,metadata=expected).update(metadata=F('metadata')+1,view=F('view')+1)
    if not updated and not m.Revision.objects.filter(pk=1).exists():
        m.Revision.objects.create(pk=1)
        updated=m.Revision.objects.filter(pk=1,metadata=expected).update(metadata=F('metadata')+1,view=F('view')+1)
    if updated!=1:
        raise APIError('VERSION_CONFLICT','目录已更新，请重新读取；当前草稿保留',409,{'expected_metadata_revision':expected,'current_metadata_revision':revision()})

def check_versions(payload,env,required):
    versions=payload.get('expected_versions')
    if not isinstance(versions,dict):reject('VERSION_REQUIRED','expected_versions 必填')
    missing=set(required)-set(versions)
    if missing:reject('VERSION_REQUIRED','缺少读取版本',objects=sorted(missing))
    conflicts=[]
    for key,value in versions.items():
        if not isinstance(key,str) or ':' not in key or type(value) is not int or value<1:reject('INVALID_VERSION','对象版本无效')
        kind,pk=key.split(':',1)
        if kind not in {*PARENTS,'services','pd-groups','endpoints'}:reject('INVALID_VERSION','不允许的版本对象')
        if kind not in PARENTS and key not in required:reject('INVALID_VERSION','版本对象不属于当前服务快照',object=key)
        model=COLLECTIONS[kind]
        obj=model.objects.filter(pk=uid(pk),environment_code=env).first()
        if not obj:reject('INVALID_VERSION','版本对象不存在或环境不符',object=key)
        if obj.version!=value:conflicts.append({'object':key,'expected_version':value,'current_version':obj.version})
    if conflicts:raise APIError('VERSION_CONFLICT','对象已更新，当前草稿保留',409,{'objects':conflicts})

def new_entity(entity_model,name,env,**attrs):
    obj=entity_model(name=name,environment_code=env,**attrs)
    obj.code=entity_model._meta.model_name+'-'+str(obj.pk)
    return obj

def persist(obj,attrs=None,new=False):
    if attrs:
        for key,value in attrs.items():setattr(obj,key,value)
    obj.full_clean()
    if new:obj.save(force_insert=True)
    else:
        old=obj.version;obj.version+=1
        values={f.attname:getattr(obj,f.attname) for f in obj._meta.fields if not f.primary_key}
        if type(obj).objects.filter(pk=obj.pk,version=old).update(**values)!=1:raise APIError('VERSION_CONFLICT','对象已更新',409)
    return obj

class Writer:
    def __init__(self,payload,service=None):
        self.payload=payload;self.service=service;self.created={};self.touched=[]
        fields(payload,{'expected_metadata_revision','expected_versions','service','team_ref','business_refs','remove_business_ids','groups','endpoints','retire_ids'}, {'service','expected_metadata_revision','expected_versions'})
        info=payload['service'];fields(info,{'name','environment_code','deployment_mode','model_ref'},{'name','environment_code','deployment_mode','model_ref'})
        self.env=text(info['environment_code'],'environment_code',80)
        if service and service.environment_code!=self.env:reject('IMMUTABLE_ENVIRONMENT','已有服务不能迁移环境')
        if not service and self.env not in NEW_ENVS:reject('INVALID_ENVIRONMENT','新服务环境必须为 PRD/DR/STG/DEV')
        if info['deployment_mode'] not in {'COMBINED','SPLIT_PD'}:reject('INVALID_MODE','部署模式无效')
        text(info['name'],'name')
        for key in ('business_refs','remove_business_ids','groups','endpoints'):
            val=payload.get(key,[])
            if not isinstance(val,list) or len(val)>100:reject('LIMIT_EXCEEDED',key+'必须为最多100项数组')
        if len(payload.get('groups',[]))>20:reject('LIMIT_EXCEEDED','最多20个P/D组')
        self.oldgroups={str(x.pk):x for x in m.PDGroup.objects.filter(service=service)} if service else {}
        self.oldeps={str(x.pk):x for x in m.Endpoint.objects.filter(service=service)} if service else {}
        self.oldbusinesses=list(m.BusinessServiceBinding.objects.filter(service=service).select_related('business')) if service else []
        self.required=version_map([*self.oldgroups.values(),*self.oldeps.values(),*[x.business for x in self.oldbusinesses],*[x.business.team for x in self.oldbusinesses],*[x.cluster for x in self.oldeps.values()],*([service,service.model] if service else [])])
        self.seen_groups=set();self.seen_eps=set();self.retired_eps=set();self.retired_groups=set()
        self.count=0;self.formkeys=set()
        self.scan_refs(payload)
    def scan_refs(self,value):
        if isinstance(value,dict):
            for key,v in value.items():
                if key.endswith('_ref') and key in {'team_ref','model_ref','cluster_ref'}:self.scan_ref(v,{'team_ref':'teams','model_ref':'models','cluster_ref':'clusters'}[key])
                elif key=='business_refs':
                    for item in v:self.scan_ref(item,'businesses')
                else:self.scan_refs(v)
        elif isinstance(value,list):
            for v in value:self.scan_refs(v)
    def scan_ref(self,ref,kind):
        fields(ref,{'id','create'})
        if len(ref)!=1:reject('INVALID_REFERENCE','引用必须选择已有ID或同页新建')
        if 'id' in ref:
            pk=uid(ref['id']);self.required[kind+':'+pk]=None
    def ref(self,kind,value,team=None):
        self.scan_ref(value,kind);model=PARENTS[kind]
        if 'id' in value:
            obj=model.objects.filter(pk=uid(value['id']),environment_code=self.env).first()
            if not obj:reject('CROSS_ENVIRONMENT','引用不存在或环境不一致',kind=kind)
            if not obj.enabled:
                existing={str(self.service.model_id)} if self.service and kind=='models' else set()
                if kind=='businesses':existing|={str(x.business_id) for x in self.oldbusinesses if x.enabled}
                if kind=='clusters':existing|={str(x.cluster_id) for x in self.oldeps.values()}
                if kind=='teams':existing|={str(x.business.team_id) for x in self.oldbusinesses}
                if str(obj.pk) not in existing:reject('DISABLED_REFERENCE','不能新引用停用资源')
            return obj
        spec=value['create'];allowed={'form_key','name'}|({'owner','critical','watch_order'} if kind=='businesses' else {'region'} if kind=='clusters' else set())
        fields(spec,allowed,{'form_key','name'}|({'owner'} if kind=='businesses' else set()))
        formkey=text(spec['form_key'],'form_key',64)
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}',formkey) or formkey.lower() in {'id','uuid','code','latest','null','none','auto','system'}:reject('INVALID_ALIAS','新建标识无效或为保留词')
        try:uuid.UUID(formkey)
        except ValueError:pass
        else:reject('INVALID_ALIAS','新建标识不能为UUID')
        name=text(spec['name'],'name');cachekey=(self.env,kind,formkey)
        definition=copy.deepcopy(spec)
        if team:definition['team_id']=str(team.pk)
        if cachekey in self.created:
            obj,prior=self.created[cachekey]
            if definition!=prior:reject('ALIAS_CONFLICT','同一新建标识的配置不一致')
            return obj
        if len(self.created)>=300:reject('LIMIT_EXCEEDED','新父对象最多300项')
        if model.objects.filter(environment_code=self.env,name=name).exists():reject('NAME_EXISTS','同环境已有同名资源，请选择已有ID')
        attrs={}
        if kind=='businesses':
            if not team:reject('MISSING_TEAM','新建业务必须选择团队')
            critical=spec.get('critical',False);order=spec.get('watch_order')
            if type(critical) is not bool or (order is not None and (type(order) is not int or order<1)):reject('INVALID_FIELD','关键业务排序无效')
            attrs=dict(team=team,owner=text(spec['owner'],'owner',160),critical=critical,watch_order=order)
        if kind=='clusters':attrs['region']=text(spec.get('region',''),'region',100,False)
        obj=persist(new_entity(model,name,self.env,**attrs),new=True)
        self.created[cachekey]=(obj,definition);return obj
    def retire(self):
        spec=self.payload.get('retire_ids',{'groups':[],'endpoints':[]})
        fields(spec,{'groups','endpoints'})
        for kind,old,seen in (('groups',self.oldgroups,self.retired_groups),('endpoints',self.oldeps,self.retired_eps)):
            vals=spec.get(kind,[])
            if not isinstance(vals,list) or len(vals)>100:reject('INVALID_RETIRE','退休集合无效')
            for value in vals:
                pk=uid(value)
                if pk in seen or pk not in old or not old[pk].enabled:reject('INVALID_RETIRE','退休对象重复或不属于当前活跃服务')
                seen.add(pk)
        for pk in self.retired_groups:
            self.retired_eps.update(str(e.pk) for e in self.oldeps.values() if str(e.pd_group_id)==pk and e.enabled)
        for pk in self.retired_eps:persist(self.oldeps[pk],{'enabled':False})
        for pk in self.retired_groups:persist(self.oldgroups[pk],{'enabled':False})
    def form_key(self,item,kind):
        if 'form_key' not in item:return
        value=text(item['form_key'],'form_key',64)
        try:uuid.UUID(value)
        except ValueError:pass
        else:reject('INVALID_ALIAS','新建标识不能为UUID')
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}',value) or value.lower() in {'id','uuid','code','latest','null','none','auto','system'}:reject('INVALID_ALIAS','新建标识无效')
        key=(kind,value)
        if key in self.formkeys:reject('DUPLICATE_ALIAS','重复新建实例或分组标识')
        self.formkeys.add(key)
    def endpoint(self,item,group=None):
        fields(item,{'id','form_key','unchanged','name','role','cluster_ref','namespace','workload_kind','workload_ref','address_ref','configured_nodes'})
        self.form_key(item,'endpoints')
        old=None
        if 'id' in item:
            pk=uid(item['id']);old=self.oldeps.get(pk)
            if not old or not old.enabled or pk in self.seen_eps or pk in self.retired_eps:reject('INVALID_ENDPOINT','实例重复或不属于当前活跃服务')
            self.seen_eps.add(pk)
        self.count+=1
        if self.count>100:reject('LIMIT_EXCEEDED','每服务最多100实例')
        if item.get('unchanged') is True:
            if not old or set(item)!={'id','unchanged'} or str(old.pd_group_id or '')!=str(group.pk if group else ''):reject('INVALID_UNCHANGED','原样实例必须保持分组')
            return old
        if 'unchanged' in item:reject('INVALID_UNCHANGED','unchanged只能为true')
        for key in ('name','role','cluster_ref','namespace','workload_kind','workload_ref','address_ref','configured_nodes'):
            if key not in item:reject('MISSING_FIELDS','实例配置必须完整',field=key)
        role=item['role']
        if (group and role not in {'PREFILL','DECODE','ROUTER'}) or (not group and role!='COMBINED'):reject('INVALID_ROLE','实例角色与部署模式不一致')
        namespace=text(item['namespace'],'namespace',120)
        if len(namespace)>63 or not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]*[a-z0-9])?',namespace):reject('INVALID_NAMESPACE','Namespace必须为K8s命名空间名称')
        workload=text(item['workload_ref'],'workload_ref',160)
        if item['workload_kind'] not in {'LWS','Deployment'}:reject('INVALID_WORKLOAD','部署方式必须为LWS或Deployment')
        nodes=item['configured_nodes']
        if not isinstance(nodes,list) or len(nodes)>32:reject('INVALID_NODES','配置Node最多32项')
        nodes=[text(x,'configured_nodes',160) for x in nodes]
        if len(set(nodes))!=len(nodes):reject('DUPLICATE_NODE','配置Node不能重复')
        cluster=self.ref('clusters',item['cluster_ref'])
        if not cluster.enabled and (not old or old.cluster_id!=cluster.pk):reject('DISABLED_REFERENCE','不能新建部署到停用集群')
        attrs=dict(name=text(item['name'],'name'),role=role,cluster=cluster,pd_group=group,namespace=namespace,workload_kind=item['workload_kind'],workload_ref=workload,address_ref=text(item['address_ref'],'address_ref',160),configured_nodes=nodes)
        if old and (old.cluster_id!=cluster.pk or old.pd_group_id!=(group.pk if group else None) or old.role!=role):
            if m.RuntimeMember.objects.filter(endpoint=old).exists() or m.EngineBinding.objects.filter(endpoint=old).exists():
                persist(old,{'enabled':False});self.retired_eps.add(str(old.pk));old=None
        if old:return persist(old,attrs)
        obj=persist(new_entity(m.Endpoint,attrs.pop('name'),self.env,service=self.service,**attrs),new=True)
        return obj
    def apply(self):
        info=self.payload['service'];team=self.ref('teams',self.payload['team_ref']) if self.payload.get('team_ref') else None
        model=self.ref('models',info['model_ref'])
        businesses=[self.ref('businesses',ref,team) for ref in self.payload.get('business_refs',[])]
        if len({x.pk for x in businesses})!=len(businesses):reject('DUPLICATE','重复业务引用')
        for b in businesses:
            if team and b.team_id!=team.pk and not any(x.business_id==b.pk for x in self.oldbusinesses):reject('WRONG_TEAM','所选业务不属于所选团队')
        self.retire()
        attrs={'name':text(info['name'],'name'),'model':model,'deployment_mode':info['deployment_mode']}
        if self.service:
            # Children are validated only after the complete transition has been assembled.
            old=self.service.version;self.service.version+=1
            for key,value in attrs.items():setattr(self.service,key,value)
            self.service.full_clean()
            if m.InferenceService.objects.filter(pk=self.service.pk,version=old).update(name=self.service.name,model_id=model.pk,deployment_mode=self.service.deployment_mode,version=self.service.version)!=1:raise APIError('VERSION_CONFLICT','服务已更新',409)
        else:self.service=persist(new_entity(m.InferenceService,attrs.pop('name'),self.env,**attrs),new=True)
        groups=self.payload.get('groups',[]);eps=self.payload.get('endpoints',[])
        if self.service.deployment_mode=='COMBINED':
            if groups or not eps:reject('INVALID_DEPLOYMENT','合并服务必须至少一个实例且无P/D组')
            for item in eps:self.endpoint(item)
        else:
            if eps or not groups:reject('INVALID_DEPLOYMENT','P/D服务必须至少一个P/D组')
            for item in groups:
                fields(item,{'id','form_key','name','endpoints','unchanged'})
                self.form_key(item,'groups')
                group=None
                if 'id' in item:
                    pk=uid(item['id']);group=self.oldgroups.get(pk)
                    if not group or not group.enabled or pk in self.retired_groups or pk in self.seen_groups:reject('INVALID_GROUP','分组重复或不属于当前活跃服务')
                    self.seen_groups.add(pk)
                if item.get('unchanged') is True:
                    if not group or set(item)!={'id','unchanged'}:reject('INVALID_UNCHANGED','原样分组必须为已有分组')
                    children=[e for e in self.oldeps.values() if e.pd_group_id==group.pk and e.enabled]
                    if any(str(e.pk) in self.retired_eps for e in children):reject('INVALID_UNCHANGED','原样组不能同时退休子实例')
                    self.seen_eps.update(str(e.pk) for e in children);self.count+=len(children)
                    if self.count>100:reject('LIMIT_EXCEEDED','每服务最多100实例')
                    continue
                if 'unchanged' in item:reject('INVALID_UNCHANGED','unchanged只能为true')
                fields(item,{'id','form_key','name','endpoints'},{'name','endpoints'})
                name=text(item['name'],'name');items=item['endpoints']
                if not isinstance(items,list) or not items or len(items)>100:reject('INVALID_GROUP','分组实例必须为非空有界数组')
                group=persist(group,{'name':name}) if group else persist(new_entity(m.PDGroup,name,self.env,service=self.service),new=True)
                roles=[self.endpoint(e,group).role for e in items]
                if not {'PREFILL','DECODE'}<=set(roles):reject('INCOMPLETE_PD','每个P/D组至少一个P和一个D')
        activegroups={pk for pk,g in self.oldgroups.items() if g.enabled or pk in self.retired_groups}
        activeeps={pk for pk,e in self.oldeps.items() if e.enabled or pk in self.retired_eps}
        if activegroups!=(self.seen_groups|self.retired_groups) or activeeps!=(self.seen_eps|self.retired_eps):reject('INCOMPLETE_DISPOSITION','原活跃分组和实例必须明确保留或退休')
        removes=self.payload.get('remove_business_ids',[])
        if len({uid(x) for x in removes})!=len(removes):reject('DUPLICATE','重复解绑业务')
        oldbindings={str(x.business_id):x for x in self.oldbusinesses}
        if any(uid(x) not in oldbindings for x in removes):reject('INVALID_RELATION','只能显式解绑已读业务关系')
        if {uid(x) for x in removes}&{str(b.pk) for b in businesses}:reject('INVALID_RELATION','业务不能同时绑定和解绑')
        changed=set()
        for value in removes:
            binding=oldbindings[uid(value)]
            if binding.enabled:binding.enabled=False;binding.save(update_fields=['enabled']);changed.add(binding.business_id)
        for b in businesses:
            binding,created=m.BusinessServiceBinding.objects.get_or_create(business=b,service=self.service)
            if not created and not binding.enabled:binding.enabled=True;binding.save(update_fields=['enabled'])
            if created or not oldbindings.get(str(b.pk),None) or not oldbindings[str(b.pk)].enabled:changed.add(b.pk)
        for pk in changed:
            # Increment once for relation change. Fresh parent version is known inside this transaction.
            m.Business.objects.filter(pk=pk).update(version=F('version')+1)
        self.service.refresh_from_db();self.service.full_clean()
        for obj in [*m.PDGroup.objects.filter(service=self.service),*m.Endpoint.objects.filter(service=self.service)]:obj.full_clean()
        for member in m.RuntimeMember.objects.filter(endpoint__service=self.service):member.full_clean()
        audit('anonymous','service_entry_update' if self.oldgroups or self.oldeps else 'service_entry_save',self.service,{'service_id':str(self.service.pk),'retired_group_ids':sorted(self.retired_groups),'retired_endpoint_ids':sorted(self.retired_eps)})
        return self.service

def write(payload,pk=None):
    try:
        with transaction.atomic():
            acquire(payload.get('expected_metadata_revision') if isinstance(payload,dict) else None)
            service=get_service(pk) if pk else None
            writer=Writer(payload,service)
            check_versions(payload,writer.env,writer.required)
            return snapshot(writer.apply())
    except OperationalError as exc:
        if any(x in str(exc).lower() for x in ('locked','busy','serialize','deadlock')):raise APIError('VERSION_CONFLICT','目录正被修改，请重新读取后保存',409,{'retryable':True}) from exc
        raise
