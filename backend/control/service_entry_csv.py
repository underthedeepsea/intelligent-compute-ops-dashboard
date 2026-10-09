"""Strict service configuration CSV; validation allocates no entity identities."""
import csv,io,json,hashlib,re,unicodedata,copy,uuid
from django.db import transaction,OperationalError
from . import models as m
from .catalog import APIError,serialize
from .service_entry import PARENTS,Writer,check_versions,acquire,snapshot,options,reject,NEW_ENVS

COLUMNS='environment_code,service_alias,service_name,deployment_mode,team_id,team_name,team_alias,business_id,business_name,business_alias,business_owner,business_critical,business_watch_order,model_id,model_name,model_alias,cluster_id,cluster_name,cluster_alias,cluster_region,group_alias,group_name,endpoint_alias,endpoint_name,role,namespace,workload_kind,workload_ref,address_ref,configured_nodes'.split(',')
RESERVED={'id','uuid','code','latest','null','none','auto','system'}
MAX_BYTES=2*1024*1024

def norm(value):return unicodedata.normalize('NFC',value.strip())

def alias(value):
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}',value) or value.lower() in RESERVED:reject('INVALID_ALIAS','标识无效或为保留词')
    try:uuid.UUID(value)
    except ValueError:pass
    else:reject('INVALID_ALIAS','导入标识不能为UUID')
    return value

def parse(source):
    if not isinstance(source,str):reject('INVALID_CSV','csv必须为UTF-8文本')
    try:size=len(source.encode('utf-8'))
    except UnicodeError:reject('INVALID_CSV','CSV必须为有效UTF-8')
    if size>MAX_BYTES:reject('LIMIT_EXCEEDED','CSV最多2MiB')
    if '\x00' in source:reject('INVALID_CSV','CSV含非法字符')
    try:
        reader=csv.reader(io.StringIO(source.lstrip('\ufeff'),newline=''),strict=True)
        raw=list(reader)
    except csv.Error as exc:reject('INVALID_CSV','CSV结构无效：'+str(exc))
    if not raw:reject('INVALID_CSV','CSV缺少表头')
    if raw[0]!=COLUMNS:reject('INVALID_COLUMNS','表头必须与整项服务模板完全一致',columns=COLUMNS)
    if not raw[1:]:reject('EMPTY_CSV','没有实例数据')
    if len(raw)>1001:reject('LIMIT_EXCEEDED','每批最多1000实例行')
    for row in raw[1:]:
        if len(row)!=len(COLUMNS):reject('INVALID_CSV','每行列数必须与表头一致')
    return raw[1:]

def encode(rows):
    stream=io.StringIO(newline='');writer=csv.writer(stream,lineterminator='\r\n');writer.writerow(COLUMNS);writer.writerows(rows);return stream.getvalue()

def template():
    row={x:'' for x in COLUMNS}
    row.update(environment_code='DEV',service_alias='example_service',service_name='示例服务（请替换）',deployment_mode='COMBINED',team_alias='example_team',team_name='示例团队（请替换）',business_alias='example_business',business_name='示例业务（请替换）',business_owner='负责人（请替换）',business_critical='false',model_alias='example_model',model_name='示例模型（请替换）',cluster_alias='example_cluster',cluster_name='示例集群（请替换）',endpoint_alias='example_endpoint',endpoint_name='示例实例（请替换）',role='COMBINED',namespace='inference',workload_kind='Deployment',workload_ref='replace-workload',address_ref='http://replace-service:8000',configured_nodes='["replace-node"]')
    return encode([[row[x] for x in COLUMNS]])

def compile_csv(source):
    cells=parse(source);errors=[];bundles={};parent_defs={};parent_lines={};ep_aliases=set();option_cache={};ep_lines={}
    def issue(row,column,exc):errors.append({'row':row,'column':column,'code':exc.code,'message':exc.message})
    def parent(row,kind,env):
        prefix={'teams':'team','businesses':'business','models':'model','clusters':'cluster'}[kind]
        identity,name,a=(row[prefix+'_'+suffix] for suffix in ('id','name','alias'))
        if identity and a:reject('INVALID_REFERENCE','已有ID与新建alias不能同时填写')
        if identity:
            from .service_entry import uid
            obj=PARENTS[kind].objects.filter(pk=uid(identity),environment_code=env,enabled=True).first()
            if not obj:reject('CROSS_ENVIRONMENT','目录ID不存在、已停用或环境不符')
            if name and norm(obj.name)!=name:reject('REFERENCE_MISMATCH','ID和名称不匹配')
            return {'id':str(obj.pk)}
        if not name:reject('MISSING_FIELDS','资源名称必填')
        if not a:
            matches=[obj for obj in PARENTS[kind].objects.filter(environment_code=env,enabled=True) if norm(obj.name)==name]
            if len(matches)!=1:reject('AMBIGUOUS_NAME' if matches else 'NAME_NOT_FOUND','名称必须在同环境唯一存在；新资源请填写alias')
            return {'id':str(matches[0].pk)}
        alias(a)
        if any(norm(obj.name)==name for obj in PARENTS[kind].objects.filter(environment_code=env)):reject('NAME_EXISTS','同环境已有同名资源，请使用ID或唯一名称')
        spec={'form_key':a,'name':name}
        if kind=='businesses':
            critical=row['business_critical'] or 'false'
            if critical not in {'true','false'}:reject('INVALID_FIELD','business_critical只接受true/false')
            order=row['business_watch_order'];order=int(order) if order.isdigit() and int(order)>0 else None if not order else -1
            if order==-1 or (critical=='true' and not order):reject('INVALID_FIELD','关键业务需要正整数watch_order')
            if not row['business_owner']:reject('MISSING_FIELDS','新建业务负责人必填')
            spec.update(owner=row['business_owner'],critical=critical=='true',watch_order=order)
        if kind=='clusters':spec['region']=row['cluster_region']
        key=(env,kind,a)
        definition={**spec}
        if kind=='businesses':definition['team_ref']={x:row[x] for x in ('team_id','team_name','team_alias')}
        if key in parent_defs and parent_defs[key]!=definition:reject('ALIAS_CONFLICT','同批资源alias的字段不一致')
        # Distinct aliases cannot quietly create same-name entities.
        if any(k[0]==env and k[1]==kind and k!=key and d['name']==name for k,d in parent_defs.items()):reject('NAME_EXISTS','同批同名资源必须使用相同alias')
        parent_defs[key]=definition;parent_lines[key]=lineno
        return {'create':spec}
    for lineno,raw in enumerate(cells,2):
        row={k:norm(v) for k,v in zip(COLUMNS,raw)}
        column='environment_code'
        try:
            env=row['environment_code']
            if env not in NEW_ENVS:reject('INVALID_ENVIRONMENT','新服务环境必须为PRD/DR/STG/DEV')
            column='service_alias';a=alias(row['service_alias'])
            column='service_name'
            if not row['service_name']:reject('MISSING_FIELDS','service_name必填')
            column='deployment_mode'
            if row['deployment_mode'] not in {'COMBINED','SPLIT_PD'}:reject('INVALID_MODE','部署模式无效')
            if env not in option_cache:option_cache[env]=options(env)
            refs={}
            for kind in PARENTS:
                prefix={'teams':'team','businesses':'business','models':'model','clusters':'cluster'}[kind]
                column=prefix+('_id' if row[prefix+'_id'] else '_alias' if row[prefix+'_alias'] else '_name')
                refs[kind]=parent(row,kind,env)
            column='business_id'
            if 'id' in refs['businesses'] and 'id' in refs['teams'] and m.Business.objects.get(pk=refs['businesses']['id']).team_id!=uuid.UUID(refs['teams']['id']):reject('WRONG_TEAM','业务不属于所选团队')
            if 'id' in refs['businesses'] and 'create' in refs['teams']:reject('WRONG_TEAM','已有业务不能归属本批新团队')
            key=(env,a)
            meta={k:row[k] for k in COLUMNS[:16]}
            if key not in bundles:
                if len(bundles)>=100:reject('LIMIT_EXCEEDED','最多100个服务')
                bundles[key]={'meta':meta,'payload':{'expected_metadata_revision':option_cache[env]['metadata_revision'],'expected_versions':option_cache[env]['expected_versions'],'service':{'name':row['service_name'],'environment_code':env,'deployment_mode':row['deployment_mode'],'model_ref':refs['models']},'team_ref':refs['teams'],'business_refs':[refs['businesses']],'groups':[],'endpoints':[],'retire_ids':{'groups':[],'endpoints':[]}},'groups':{},'rows':[]}
            bundle=bundles[key]
            column='service_alias'
            if meta!=bundle['meta']:reject('INCONSISTENT_SERVICE','同一服务alias的服务和父资源字段必须一致')
            column='endpoint_alias';ep_a=alias(row['endpoint_alias']);ep_key=(env,a,ep_a)
            if ep_key in ep_aliases:reject('DUPLICATE_ENDPOINT','同一服务中实例alias重复')
            ep_aliases.add(ep_key)
            column='configured_nodes'
            try:nodes=json.loads(row['configured_nodes'] or '[]')
            except ValueError:reject('INVALID_NODES','configured_nodes必须为JSON字符串数组')
            ep={'form_key':ep_a,'name':row['endpoint_name'],'role':row['role'],'cluster_ref':refs['clusters'],'namespace':row['namespace'],'workload_kind':row['workload_kind'],'workload_ref':row['workload_ref'],'address_ref':row['address_ref'],'configured_nodes':nodes}
            ep_lines[id(ep)]=lineno
            if row['deployment_mode']=='COMBINED':
                column='group_alias'
                if row['group_alias'] or row['group_name']:reject('INVALID_GROUP','合并服务不能填写P/D组')
                bundle['payload']['endpoints'].append(ep)
            else:
                column='group_alias'
                ga=alias(row['group_alias'])
                if ga not in bundle['groups']:
                    group={'form_key':ga,'name':row['group_name'],'endpoints':[]};bundle['groups'][ga]=group;bundle['payload']['groups'].append(group)
                group=bundle['groups'][ga]
                column='group_name'
                if group['name']!=row['group_name']:reject('ALIAS_CONFLICT','同组alias名称不一致')
                group['endpoints'].append(ep)
            bundle['rows'].append(lineno)
        except APIError as exc:issue(lineno,exc.details.get('field',column),exc)
    if len(parent_defs)>300:errors.append({'row':1,'column':'','code':'LIMIT_EXCEEDED','message':'新父资源最多300项'})
    # Pure validation mirrors field semantics without instantiating UUID-backed models.
    from .service_entry import text
    for bundle in bundles.values():
        p=bundle['payload'];eps=p['endpoints']+[ep for g in p['groups'] for ep in g['endpoints']]
        firstline=bundle['rows'][0] if bundle['rows'] else 2
        try:
            if not eps or len(eps)>100 or len(p['groups'])>20:reject('LIMIT_EXCEEDED','每服务最多100实例、20组且不能为空')
            text(p['service']['name'],'service_name')
        except APIError as exc:issue(firstline,exc.details.get('field',''),exc)
        for g in p['groups']:
            try:
                text(g['name'],'group_name')
                if not {'PREFILL','DECODE'}<={x['role'] for x in g['endpoints']}:reject('INCOMPLETE_PD','每个P/D组至少一个P和D')
            except APIError as exc:issue(ep_lines[id(g['endpoints'][0])] if g['endpoints'] else firstline,'group_alias',exc)
        for ep in eps:
            column=''
            try:
                for field,limit in [('name',240),('namespace',120),('workload_ref',160),('address_ref',160)]:
                    column='endpoint_name' if field=='name' else field;text(ep[field],column,limit)
                column='namespace'
                if len(ep['namespace'])>63 or not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]*[a-z0-9])?',ep['namespace']):reject('INVALID_NAMESPACE','Namespace格式无效')
                column='workload_kind'
                if ep['workload_kind'] not in {'LWS','Deployment'}:reject('INVALID_WORKLOAD','部署方式无效')
                column='role'
                if ep['role'] not in ({'COMBINED'} if p['service']['deployment_mode']=='COMBINED' else {'PREFILL','DECODE','ROUTER'}):reject('INVALID_ROLE','实例角色无效')
                column='configured_nodes';nodes=ep['configured_nodes']
                if not isinstance(nodes,list) or len(nodes)>32:reject('INVALID_NODES','配置Node最多32项')
                clean=[text(n,'configured_nodes',160) for n in nodes]
                if len(set(clean))!=len(clean):reject('DUPLICATE_NODE','配置Node不能重复')
            except APIError as exc:issue(ep_lines[id(ep)],column,exc)
    watch_orders={}
    for key,definition in parent_defs.items():
        try:
            text(definition['name'],'name')
            if 'owner' in definition:text(definition['owner'],'business_owner',160)
            if 'region' in definition:text(definition['region'],'cluster_region',100,False)
            if definition.get('critical'):
                order=definition['watch_order']
                if m.Business.objects.filter(enabled=True,critical=True,watch_order=order).exists() or order in watch_orders:reject('WATCH_ORDER_CONFLICT','关键业务展示排序已使用')
                watch_orders[order]=key
        except APIError as exc:issue(parent_lines[key],exc.details.get('field',''),exc)
    return {'valid':not errors,'errors':errors,'sha256':hashlib.sha256(source.encode('utf-8')).hexdigest(),'metadata_revision':option_cache[next(iter(option_cache))]['metadata_revision'] if option_cache else options('DEV')['metadata_revision'],
        'columns':COLUMNS,'rows':cells,'services':[{'alias':k[1],'name':v['payload']['service']['name'],'environment_code':k[0],'deployment_mode':v['payload']['service']['deployment_mode'],'groups':len(v['payload']['groups']),'endpoints':len(v['rows'])} for k,v in bundles.items()],
        'service_count':len(bundles),'endpoint_count':len(cells),'_bundles':[v['payload'] for v in bundles.values()]}

def validate(source):
    try:
        result=compile_csv(source);result.pop('_bundles');return result
    except APIError as exc:
        return {'valid':False,'errors':[{'row':1,'column':'','code':exc.code,'message':exc.message}], 'columns':COLUMNS,'rows':[], 'services':[],'service_count':0,'endpoint_count':0,'metadata_revision':options('DEV')['metadata_revision'],'sha256':hashlib.sha256(source.encode('utf-8')).hexdigest() if isinstance(source,str) and not any(0xD800<=ord(c)<=0xDFFF for c in source) else None}

def apply(payload):
    from .service_entry import fields
    fields(payload,{'csv','sha256','expected_metadata_revision'},{'csv','sha256','expected_metadata_revision'})
    source=payload['csv']
    if not isinstance(source,str) or hashlib.sha256(source.encode('utf-8')).hexdigest()!=payload['sha256']:raise APIError('VERSION_CONFLICT','CSV已变化，请重新校验',409)
    try:
        with transaction.atomic():
            acquire(payload['expected_metadata_revision'])
            result=compile_csv(source)
            if not result['valid']:raise APIError('INVALID_CSV','批次校验失败，未保存',400,{'errors':result['errors']})
            created={};saved=[];writers=[]
            for p in result['_bundles']:
                writer=Writer(p);writer.created=created;check_versions(p,writer.env,writer.required);writers.append(writer)
            for writer in writers:saved.append(writer.apply())
            return {'items':[snapshot(s) for s in saved],'service_count':len(saved),'endpoint_count':result['endpoint_count']}
    except OperationalError as exc:
        if any(x in str(exc).lower() for x in ('locked','busy','serialize','deadlock')):raise APIError('VERSION_CONFLICT','目录正被修改，请重新校验',409,{'retryable':True}) from exc
        raise

def export_csv(service):
    rows=[];bindings=list(m.BusinessServiceBinding.objects.filter(service=service,enabled=True).select_related('business__team'))
    if len(bindings)!=1:raise APIError('EXPORT_REQUIRES_SINGLE_BUSINESS','配置复制CSV需要且仅支持一个业务关联；请使用完整只读JSON查看全部关联，并从整项服务目录编辑',400,{'business_count':len(bindings),'alternative':'complete-json-and-whole-service-edit'})
    business=bindings[0].business if len(bindings)==1 else None
    for ep in m.Endpoint.objects.filter(service=service,enabled=True).select_related('cluster','pd_group'):
        row={x:'' for x in COLUMNS};row.update(environment_code=service.environment_code,service_alias='copy_service',service_name=service.name,deployment_mode=service.deployment_mode,model_id=str(service.model_id),endpoint_alias='ep_'+str(ep.pk).replace('-',''),endpoint_name=ep.name,cluster_id=str(ep.cluster_id),role=ep.role,namespace=ep.namespace,workload_kind=ep.workload_kind,workload_ref=ep.workload_ref,address_ref=ep.address_ref,configured_nodes=json.dumps(ep.configured_nodes,ensure_ascii=False))
        if business:row.update(team_id=str(business.team_id),business_id=str(business.pk))
        if ep.pd_group_id:row.update(group_alias='group_'+str(ep.pd_group_id).replace('-',''),group_name=ep.pd_group.name)
        rows.append([row[x] for x in COLUMNS])
    return encode(rows)
