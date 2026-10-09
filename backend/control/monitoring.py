"""Cluster-scoped configuration and explicitly non-live CSV observations."""
import csv,io,json,hashlib,math
from datetime import timedelta
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from . import models as m
from .access import scoped,environments,bump,audit
from .catalog import APIError,find,serialize,version
from .telemetry import METRICS,metric

CONFIG_COLUMNS='environment_code,cluster_code,cluster_name,region,model_code,model_name,service_code,service_name,deployment_mode,pd_group_code,pd_group_name,endpoint_code,endpoint_name,role,runtime_code,pod_uid,pod_name,namespace,workload_ref,node_uid,node_name,observed_at'.split(',')
ENDPOINT_COLUMNS=['endpoint_code','sampled_at',*METRICS]
HARDWARE_COLUMNS='resource_code,resource_name,resource_type,host_id,gpu_uuid,sampled_at,utilization_ratio,temperature_celsius,memory_used_bytes,memory_total_bytes,cpu_busy_ratio,memory_available_bytes'.split(',')
COLUMNS={'cluster-config':CONFIG_COLUMNS,'endpoint-metrics':ENDPOINT_COLUMNS,'hardware-metrics':HARDWARE_COLUMNS}
MAX_BYTES=1048576

def invalidate_bindings(cluster=None,endpoint=None):
    engines=m.EngineBinding.objects.filter(endpoint=endpoint) if endpoint else m.EngineBinding.objects.filter(endpoint__cluster=cluster)
    hardware=m.HardwareBinding.objects.filter(cluster=cluster) if cluster else m.HardwareBinding.objects.none()
    for b in engines.select_for_update():
        b.binding_version+=1;b.version+=1;b.save(update_fields=['binding_version','version'])
        m.PollState.objects.filter(binding=b).update(last_attempt_at=None,last_success_at=None,next_due=None,error='',failures=0,paused=False)
    for b in hardware.select_for_update():
        b.binding_version+=1;b.version+=1;b.save(update_fields=['binding_version','version'])
        m.HardwareObservation.objects.filter(binding=b).update(payload={},last_attempt_at=None,last_success_at=None,next_due=None,error='',failures=0,paused=False)

def inspection_allowed(binding):
    if isinstance(binding,m.EngineBinding):
        return m.Endpoint.objects.filter(pk=binding.endpoint_id,enabled=True,cluster__enabled=True,cluster__monitoring_source='INSPECTION').exists()
    return not binding.cluster_id or m.KubernetesCluster.objects.filter(pk=binding.cluster_id,enabled=True,monitoring_source='INSPECTION').exists()

def switch_source(user,pk,data):
    if set(data)!={'expected_version','source'} or data['source'] not in ('INSPECTION','CSV'):raise APIError('INVALID_SOURCE','请选择巡检或 CSV 来源')
    with transaction.atomic():
        m.Revision.objects.select_for_update().get_or_create(pk=1)
        c=find(m.KubernetesCluster,user,pk,True);version(c,data)
        if not c.enabled:raise APIError('DISABLED_CLUSTER','集群已停用')
        if c.monitoring_source!=data['source']:
            old=c.monitoring_source;c.monitoring_source=data['source'];c.source_generation+=1;c.version+=1;c.save(update_fields=['monitoring_source','source_generation','version'])
            invalidate_bindings(cluster=c);bump('metadata');bump('telemetry')
            audit(user,'monitoring_source',c,{'old':old,'new':c.monitoring_source,'source_generation':c.source_generation})
        return cluster_summary(c)

def cluster_summary(c):
    row=m.ClusterCsvSnapshot.objects.filter(cluster=c).first()
    endpoints=[]
    for e in m.Endpoint.objects.filter(cluster=c,enabled=True).select_related('service__model','pd_group'):
        bindings=[serialize(b) for b in m.EngineBinding.objects.filter(endpoint=e,enabled=True)]
        endpoints.append({**serialize(e),'service_code':e.service.code,'service_name':e.service.name,'model_code':e.service.model.code,'model_name':e.service.model.name,'deployment_mode':e.service.deployment_mode,'pd_group_code':e.pd_group.code if e.pd_group else None,'pd_group_name':e.pd_group.name if e.pd_group else None,'engine_bindings':bindings,'engine_binding':bindings[0] if len(bindings)==1 else None})
    snapshot=None
    if row and (row.endpoint_hash or row.hardware_hash):
        snapshot={'id':str(c.pk),'endpoint_count':len(row.endpoint_payload),'hardware_count':len(row.hardware_payload),'sampled_at':row.endpoint_sampled_at or row.hardware_sampled_at,'imported_at':row.endpoint_imported_at or row.hardware_imported_at,'endpoint_sampled_at':row.endpoint_sampled_at,'endpoint_imported_at':row.endpoint_imported_at,'hardware_sampled_at':row.hardware_sampled_at,'hardware_imported_at':row.hardware_imported_at}
    return {**serialize(c),'snapshot':snapshot,'endpoints':endpoints,'hardware':[serialize(b) for b in m.HardwareBinding.objects.filter(cluster=c,enabled=True)]}

def parse_csv(kind,text):
    if kind not in COLUMNS:raise APIError('INVALID_KIND','不支持的 CSV 模板')
    if not isinstance(text,str):raise APIError('INVALID_CSV','CSV 必须为 UTF-8 文本')
    try:encoded=text.encode('utf-8')
    except UnicodeError:raise APIError('INVALID_CSV','CSV 包含无效 Unicode 字符')
    if len(encoded)>MAX_BYTES:raise APIError('CSV_TOO_LARGE','CSV 最大 1 MiB')
    if any(ord(x)<32 and x not in '\r\n\t' for x in text):raise APIError('INVALID_CSV','CSV 包含控制字符')
    try:
        reader=csv.reader(io.StringIO(text.lstrip('\ufeff')),strict=True)
        header=next(reader)
        if len(set(header))!=len(header) or set(header)!=set(COLUMNS[kind]):raise APIError('CSV_HEADERS','CSV 列名必须与模板完全一致')
        rows=[]
        for line,values in enumerate(reader,2):
            if not values or all(not x.strip() for x in values):continue
            if len(values)!=len(header):raise APIError('CSV_ROW','CSV 列数错误',details={'rows':[{'row':line,'field':'','message':'列数错误'}]})
            if len(rows)>=1000:raise APIError('CSV_TOO_MANY_ROWS','CSV 最多 1000 行')
            row={k:v.strip() for k,v in zip(header,values)}
            if any(len(v)>1000 or v.startswith(('=','+','-','@')) or '\t' in v for v in row.values()):raise APIError('CSV_VALUE','单元格过长或包含公式/制表符',details={'rows':[{'row':line,'field':'','message':'无效单元格'}]})
            rows.append((line,row))
    except (csv.Error,StopIteration):raise APIError('INVALID_CSV','CSV 格式无效')
    if not rows:raise APIError('CSV_EMPTY','CSV 至少需要一行数据')
    return rows

def invalid(line,field,message):raise APIError('CSV_VALIDATION','CSV 数据校验失败',details={'rows':[{'row':line,'field':field,'message':message}]})
def timestamp(value,line,field='sampled_at'):
    try:dt=parse_datetime(value)
    except (ValueError,TypeError,OverflowError):dt=None
    if not dt or timezone.is_naive(dt) or dt>timezone.now()+timedelta(seconds=30):invalid(line,field,'必须是带时区且不超过当前时间 30 秒的 ISO 时间')
    return dt.isoformat()
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def config_plan(user,rows,cluster):
    first=rows[0][1];env=first['environment_code'];code=first['cluster_code']
    if not code or not first['cluster_name']:invalid(rows[0][0],'cluster_code','集群编码和名称必填')
    if cluster and (cluster.code!=code or cluster.environment_code!=env):raise APIError('WRONG_CLUSTER','CSV 与目标集群不一致')
    cache={};operations=[];definitions={};seen=set()
    def entity(model,code,fields,line,shared=False):
        key=(model,code)
        if not code or len(code)>120 or code.startswith('-'):invalid(line,'code','编码必填，最长 120 字符')
        canonical={k:str(v.pk) if isinstance(v,m.Entity) else v for k,v in fields.items()}
        if key in definitions:
            if definitions[key]!=canonical:invalid(line,'code','重复定义不一致')
            return cache[key]
        obj=model.objects.filter(code=code).first()
        if obj and obj.environment_code!=env:invalid(line,'code','编码不可用或不属于此环境')
        if obj and not obj.enabled:invalid(line,'code','编码对应对象已停用')
        if obj and shared and any(getattr(obj,k+'_id')!=v.pk if isinstance(v,m.Entity) else getattr(obj,k)!=v for k,v in fields.items()):invalid(line,'code','共享模型、服务或 PD 的定义与现有配置冲突')
        if obj and model==m.Endpoint and obj.cluster_id!=cluster_obj.pk:invalid(line,'endpoint_code','Endpoint 已属于其他集群')
        if obj and model==m.RuntimeMember and obj.endpoint_id!=fields['endpoint'].pk:invalid(line,'runtime_code','成员已属于其他 Endpoint')
        old=serialize(obj) if obj else None
        obj=obj or model(code=code,environment_code=env)
        changed=old is None or any(getattr(obj,k+'_id')!=v.pk if isinstance(v,m.Entity) else getattr(obj,k)!=v for k,v in fields.items())
        for k,v in fields.items():setattr(obj,k,v)
        # FK existence is validated by the planned typed graph; new parents are not saved in preview.
        obj.full_clean(exclude=[f.name for f in obj._meta.fields if f.is_relation])
        definitions[key]=canonical;cache[key]=obj
        if changed:operations.append((obj,old))
        return obj
    cluster_obj=entity(m.KubernetesCluster,code,{'name':first['cluster_name'],'region':first['region']},rows[0][0])
    if cluster and cluster_obj.pk!=cluster.pk:raise APIError('WRONG_CLUSTER','目标集群不一致')
    for line,r in rows:
        if any(r[k]!=first[k] for k in ('environment_code','cluster_code','cluster_name','region')):invalid(line,'cluster_code','每个文件只能定义一个一致的集群')
        if not r['endpoint_code']:
            if any(r[k] for k in CONFIG_COLUMNS[4:]):invalid(line,'endpoint_code','Endpoint 编码缺失')
            continue
        if r['endpoint_code'] in seen:invalid(line,'endpoint_code','重复 Endpoint')
        seen.add(r['endpoint_code'])
        if r['deployment_mode'] not in ('COMBINED','SPLIT_PD'):invalid(line,'deployment_mode','只支持 COMBINED 或 SPLIT_PD')
        if not r['model_name'] or not r['service_name'] or not r['endpoint_name']:invalid(line,'name','模型、服务、Endpoint 名称必填')
        model=entity(m.Model,r['model_code'],{'name':r['model_name']},line,True)
        service=entity(m.InferenceService,r['service_code'],{'name':r['service_name'],'model':model,'deployment_mode':r['deployment_mode']},line,True)
        pd=None
        if r['deployment_mode']=='SPLIT_PD':
            if r['role'] not in ('ROUTER','PREFILL','DECODE') or not r['pd_group_name']:invalid(line,'role','SPLIT_PD 需要 PD 名称及 ROUTER/PREFILL/DECODE 角色')
            pd=entity(m.PDGroup,r['pd_group_code'],{'name':r['pd_group_name'],'service':service},line,True)
        elif r['role']!='COMBINED' or r['pd_group_code'] or r['pd_group_name']:invalid(line,'role','COMBINED 不可设置 PD 或阶段角色')
        endpoint=entity(m.Endpoint,r['endpoint_code'],{'name':r['endpoint_name'],'cluster':cluster_obj,'service':service,'pd_group':pd,'role':r['role']},line)
        if r['runtime_code']:
            observed=timestamp(r['observed_at'],line,'observed_at') if r['observed_at'] else None
            if not r['namespace']:invalid(line,'namespace','配置成员时 namespace 必填')
            entity(m.RuntimeMember,r['runtime_code'],{'name':r['pod_name'] or r['runtime_code'],'endpoint':endpoint,'cluster':cluster_obj,'namespace':r['namespace'],'workload_ref':r['workload_ref'],'pod_uid':r['pod_uid'] or None,'pod_name':r['pod_name'],'node_uid':r['node_uid'] or None,'node_name':r['node_name'],'observed_at':parse_datetime(observed) if observed else None},line)
        elif any(r[k] for k in CONFIG_COLUMNS[15:]):invalid(line,'runtime_code','填写成员信息需要 runtime_code')
    return cluster_obj,operations

def metric_plan(kind,rows,cluster):
    if cluster.monitoring_source!='CSV':raise APIError('SOURCE_CONFLICT','请先将此集群切换为 CSV 来源',409)
    payload=[];seen=set();sampled=None
    from .hardware import FIELDS
    for line,r in rows:
        at=timestamp(r['sampled_at'],line)
        if sampled and parse_datetime(at)!=parse_datetime(sampled):invalid(line,'sampled_at','同一文件所有行采样时间必须一致')
        sampled=at
        if kind=='endpoint-metrics':
            endpoint=m.Endpoint.objects.filter(code=r['endpoint_code'],cluster=cluster,enabled=True).first()
            if not endpoint:invalid(line,'endpoint_code','Endpoint 不在当前集群或已停用')
            identity=str(endpoint.pk);item={'id':identity,'endpoint_code':endpoint.code};fields={k:v[2] for k,v in METRICS.items()}
        else:
            if r['resource_type'] not in FIELDS:invalid(line,'resource_type','只支持 GPU_POOL 或 HOST')
            if not r['resource_code'] or not r['resource_name'] or not r['host_id']:invalid(line,'resource_code','资源编码、名称、host_id 必填')
            if len(r['resource_code'])>120 or len(r['resource_name'])>240 or len(r['host_id'])>192 or len(r['gpu_uuid'])>192:invalid(line,'resource_code','资源字段过长')
            if (r['resource_type']=='GPU_POOL')!=bool(r['gpu_uuid']):invalid(line,'gpu_uuid','GPU 必须填写 UUID；主机必须留空')
            identity=r['resource_code'];item={k:r[k] for k in ('resource_code','resource_name','resource_type','host_id','gpu_uuid')}
            fields=FIELDS[r['resource_type']][1]
            if any(r[k] for k in HARDWARE_COLUMNS[6:] if k not in fields):invalid(line,'resource_type','包含不适用于此资源类型的指标')
            device=(r['resource_type'],r['host_id'],r['gpu_uuid'])
            if device in seen:invalid(line,'resource_code','重复设备身份')
            seen.add(device)
        if identity in seen:invalid(line,'code','重复对象')
        seen.add(identity);metrics={}
        for key,unit in fields.items():
            value=None
            if r[key]:
                try:value=float(r[key])
                except (ValueError,OverflowError):invalid(line,key,'需要数值')
                if not math.isfinite(value) or value<0 or (unit=='ratio' and value>1) or (key in ('running','waiting') and not value.is_integer()):invalid(line,key,'指标超出允许范围')
            metrics[key]=metric(value,unit,'AVAILABLE' if value is not None else 'MISSING','ENDPOINT' if kind=='endpoint-metrics' else 'DEVICE')
            if kind=='hardware-metrics':metrics[key].update(collected_at=at,quality='VALID' if value is not None else 'MISSING')
        if not any(p['value'] is not None for p in metrics.values()):invalid(line,'metrics','至少填写一项指标')
        if kind=='endpoint-metrics':
            for group in ('ttft','tpot','e2e'):
                vals=[metrics[f'{group}_{p}_ms']['value'] for p in ('p90','p95','p99')];vals=[v for v in vals if v is not None]
                if vals!=sorted(vals):invalid(line,group,'分位数必须递增')
        else:
            key='memory_used_bytes' if r['resource_type']=='GPU_POOL' else 'memory_available_bytes'
            a,b=metrics[key]['value'],metrics['memory_total_bytes']['value'];value=None
            if b is not None and b<=0:invalid(line,'memory_total_bytes','内存总量必须大于零')
            if a is not None and b is not None:
                if a>b:invalid(line,key,'不可超过内存总量')
                value=a/b if r['resource_type']=='GPU_POOL' else 1-a/b
            metrics['memory_usage_ratio']={**metric(value,'ratio','AVAILABLE' if value is not None else 'MISSING','DEVICE'),'collected_at':at,'quality':'VALID' if value is not None else 'MISSING'}
        item['metrics']=metrics;payload.append(item)
    return payload,sampled

def prepare(user,data):
    if set(data)-{'kind','cluster_id','csv','expected_version','normalized_hash'}:raise APIError('UNKNOWN_FIELDS','不允许的字段')
    kind=data.get('kind');rows=parse_csv(kind,data.get('csv'))
    c=find(m.KubernetesCluster,user,data['cluster_id']) if data.get('cluster_id') else None
    if c and not c.enabled:raise APIError('DISABLED_CLUSTER','集群已停用')
    if kind=='cluster-config':
        c,plan=config_plan(user,rows,c);sampled=None
        canonical={'kind':kind,'environment':c.environment_code,'cluster':c.code,'rows':[r for _,r in rows]}
    else:
        if not c:raise APIError('CLUSTER_REQUIRED','请先选择集群')
        plan,sampled=metric_plan(kind,rows,c);canonical={'kind':kind,'cluster_id':str(c.pk),'sampled_at':sampled,'rows':sorted(plan,key=lambda x:x.get('id',x.get('resource_code','')))}
    return kind,rows,c,plan,sampled,digest(canonical)

def import_csv(user,data,apply=False):
    with transaction.atomic():
        if apply:m.Revision.objects.select_for_update().get_or_create(pk=1)
        kind,rows,c,plan,sampled,hash_value=prepare(user,data)
        exists=m.KubernetesCluster.objects.filter(pk=c.pk).exists()
        if apply and exists:c=m.KubernetesCluster.objects.select_for_update().get(pk=c.pk)
        response={'valid':True,'row_count':len(rows),'summary':{'cluster_code':c.code,'cluster_name':c.name,'kind':kind,'sampled_at':sampled},'expected_version':c.version if exists else None,'normalized_hash':hash_value}
        if not apply:return response
        if data.get('normalized_hash')!=hash_value:raise APIError('PREVIEW_CHANGED','预览内容已改变，请重新校验',409)
        snapshot=m.ClusterCsvSnapshot.objects.filter(cluster=c).first() if exists else None
        family='endpoint' if kind=='endpoint-metrics' else 'hardware'
        same=(not plan if kind=='cluster-config' else snapshot and getattr(snapshot,family+'_hash')==hash_value)
        if same:return {'changed':False,'row_count':len(rows),'cluster':cluster_summary(c)}
        if exists:version(c,data)
        elif data.get('expected_version') is not None:raise APIError('VERSION_CONFLICT','新建集群版本应为空',409)
        if kind=='cluster-config':
            for obj,before in plan:
                # Previously planned FK objects now exist in operation order.
                obj.full_clean()
                if before:obj.version+=1
                obj.save()
                audit(user,'csv_config_update' if before else 'csv_config_create',obj,{'hash':hash_value,'kind':kind})
                if before and isinstance(obj,m.Endpoint):invalidate_bindings(endpoint=obj)
            c=m.KubernetesCluster.objects.get(pk=c.pk)
            if exists and not any(isinstance(o,m.KubernetesCluster) for o,_ in plan):c.version+=1;c.save(update_fields=['version'])
            snapshot,_=m.ClusterCsvSnapshot.objects.get_or_create(cluster=c);snapshot.config_hash=hash_value;snapshot.save(update_fields=['config_hash']);bump('metadata')
        else:
            snapshot=snapshot or m.ClusterCsvSnapshot(cluster=c)
            setattr(snapshot,family+'_payload',plan);setattr(snapshot,family+'_hash',hash_value);setattr(snapshot,family+'_sampled_at',parse_datetime(sampled));setattr(snapshot,family+'_imported_at',timezone.now())
            if len(json.dumps([snapshot.endpoint_payload,snapshot.hardware_payload]).encode())>2097152:raise APIError('CSV_TOO_LARGE','规范化快照超过 2 MiB')
            snapshot.save();c.version+=1;c.save(update_fields=['version']);bump('telemetry')
        audit(user,'csv_import',c,{'kind':kind,'hash':hash_value,'row_count':len(rows),'version':c.version})
        return {'changed':True,'row_count':len(rows),'cluster':cluster_summary(c)}

def csv_observation(c,row,family):
    sampled=getattr(row,family+'_sampled_at').isoformat();imported=getattr(row,family+'_imported_at').isoformat()
    return {'source_type':'CSV','data_state':'CSV_SNAPSHOT','sampled_at':sampled,'imported_at':imported,'source_window':{'start':sampled,'end':sampled},'origin':'CSV','source_generation':c.source_generation,'snapshot_id':getattr(row,family+'_hash'),'upstream_status':'UNKNOWN','transport_status':'NOT_APPLICABLE'}

def csv_endpoint(e):
    row=m.ClusterCsvSnapshot.objects.filter(cluster=e.cluster).first();item=next((x for x in row.endpoint_payload if x['id']==str(e.pk)),None) if row else None
    return {'id':str(e.pk),'name':e.name,'environment_code':e.environment_code,'service_id':str(e.service_id),'cluster_id':str(e.cluster_id),'pd_group_id':str(e.pd_group_id) if e.pd_group_id else None,'role':e.role,'source_type':'CSV','data_state':'CSV_SNAPSHOT' if item else 'MISSING','status':'UNKNOWN','metrics':item['metrics'] if item else {k:metric(None,v[2],'MISSING') for k,v in METRICS.items()},'observation':csv_observation(e.cluster,row,'endpoint') if item else None}

def csv_hardware(c):
    row=m.ClusterCsvSnapshot.objects.filter(cluster=c).first()
    if not row or not row.hardware_hash:return []
    return [{'id':f'csv:{c.pk}:{x["resource_code"]}','cluster_id':str(c.pk),'name':x['resource_name'],'environment_code':c.environment_code,'resource_type':x['resource_type'],'asset_id':x['resource_code'],'host_id':x['host_id'],'gpu_uuid':x['gpu_uuid'],'metrics':x['metrics'],'source_type':'CSV','observation':csv_observation(c,row,'hardware'),'data_state':'CSV_SNAPSHOT','status':'UNKNOWN'} for x in row.hardware_payload]
