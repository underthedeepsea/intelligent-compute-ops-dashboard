"""Read-only single-device hardware adapter for AI-inspect b28a8090.

The upstream GET omits environment and provenance attestations. Bindings constrain
request scope and device identity; observations remain UNVERIFIED, even on a
verified inference provider. No raw evaluation or arbitrary upstream fields leak.
"""
import json
from datetime import timedelta
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from . import models as m
from .access import bump
from .telemetry import InvalidProfile,finite_number,typed_text,metric,state,same_generation

FIELDS={'GPU_POOL':('gpu',{'utilization_ratio':'ratio','temperature_celsius':'°C','memory_used_bytes':'bytes','memory_total_bytes':'bytes'}),
        'HOST':('host',{'cpu_busy_ratio':'ratio','memory_available_bytes':'bytes','memory_total_bytes':'bytes'})}

def timestamp(value):
    try: result=parse_datetime(value) if isinstance(value,str) else None
    except (ValueError,TypeError,OverflowError): result=None
    if not result or timezone.is_naive(result): raise InvalidProfile('INVALID_WINDOW')
    return result

def normalize_hardware(raw,binding,now=None):
    now=now or timezone.now()
    if not isinstance(raw,dict): raise InvalidProfile('CONTRACT_INCOMPATIBLE')
    identity=raw.get('identity')
    if (raw.get('asset_id')!=str(binding.asset_id) or raw.get('host_id')!=binding.host_id
        or not isinstance(identity,dict)
        or (binding.resource_type=='GPU_POOL' and identity.get('gpu_uuid')!=binding.gpu_uuid)
        or (binding.resource_type=='HOST' and identity)):
        raise InvalidProfile('IDENTITY_MISMATCH')
    # Validate an environment assertion if a later compatible source supplies it.
    if 'environment_id' in raw and raw['environment_id']!=str(binding.environment_id): raise InvalidProfile('IDENTITY_MISMATCH')
    start,end=timestamp(raw.get('window_start')),timestamp(raw.get('window_end'))
    if start>=end or (end-start).total_seconds()>3600: raise InvalidProfile('INVALID_WINDOW')
    if end>now+timedelta(seconds=30): raise InvalidProfile('CLOCK_SKEW')
    if raw.get('freshness') not in ('FRESH','STALE'): raise InvalidProfile('INVALID_FRESHNESS')
    if raw.get('status') not in ('NORMAL','WARNING','CRITICAL','UNKNOWN'): raise InvalidProfile('CONTRACT_INCOMPATIBLE')
    if not typed_text(raw.get('snapshot_id')): raise InvalidProfile('INVALID_SNAPSHOT_ID')
    family,fields=FIELDS[binding.resource_type]
    components=raw.get('metrics')
    component=components.get(family) if isinstance(components,dict) else None
    values=component.get('values') if isinstance(component,dict) else None
    if not isinstance(values,dict): raise InvalidProfile('INVALID_METRIC')
    metrics={}
    for key,unit in fields.items():
        point=values.get(key)
        if not isinstance(point,dict) or point.get('quality') not in ('VALID','MISSING','UNSUPPORTED','RESET'): raise InvalidProfile('INVALID_QUALITY')
        collected=timestamp(point.get('collected_at'))
        if not start<=collected<=end+timedelta(minutes=5) or collected>now+timedelta(seconds=30): raise InvalidProfile('INVALID_WINDOW')
        quality=point['quality'];value=point.get('value')
        if quality=='VALID':
            if not finite_number(value) or value<0 or unit=='ratio' and value>1: raise InvalidProfile('INVALID_METRIC')
        elif value is not None: raise InvalidProfile('INVALID_METRIC')
        metrics[key]={**metric(value,unit,'AVAILABLE' if quality=='VALID' else quality,'DEVICE'),'quality':quality,'collected_at':collected.isoformat()}
    used='memory_used_bytes' if family=='gpu' else 'memory_available_bytes'
    a,b=metrics[used],metrics['memory_total_bytes']
    derived=metric(None,'ratio','MISSING','DEVICE')
    if a['state']==b['state']=='AVAILABLE':
        if b['value']<=0 or a['value']>b['value']: raise InvalidProfile('INVALID_METRIC')
        # Pair timestamps are retained; the derived value ages from the older input.
        value=a['value']/b['value']
        derived={**metric(value if family=='gpu' else 1-value,'ratio','AVAILABLE','DEVICE'),'quality':'VALID','collected_at':min(a['collected_at'],b['collected_at'],key=timestamp)}
    metrics['memory_usage_ratio']=derived
    payload={'metrics':metrics,'observation':{'binding_id':str(binding.pk),'binding_version':binding.binding_version,
        'provider_id':str(binding.provider_id),'provider_version':binding.provider.version,
        'identity':{'environment_id':str(binding.environment_id),'asset_id':str(binding.asset_id),'host_id':binding.host_id,'gpu_uuid':binding.gpu_uuid,'resource_type':binding.resource_type,'scope':'DEVICE'},
        'provider_snapshot_id':raw['snapshot_id'],'source_window':{'start':start.isoformat(),'end':end.isoformat()},
        'origin':'UNVERIFIED','demo':binding.origin=='DEMO','freshness':raw['freshness'],'max_age_seconds':300,
        'fetched_at':now.isoformat(),'upstream_status':raw['status'],'transport_status':'OK'}}
    if len(json.dumps(payload).encode())>65536: raise InvalidProfile('NORMALIZED_TOO_LARGE')
    return payload

def immutable(payload):
    o=payload['observation']
    return {'metrics':payload['metrics'],'identity':o['identity'],'window':o['source_window'],'snapshot':o['provider_snapshot_id']}

def publish_hardware(binding,payload,owner=None):
    with transaction.atomic():
        m.Revision.objects.select_for_update().get_or_create(pk=1)
        if owner and not m.WorkerLease.objects.filter(pk=1,owner=owner,expires_at__gt=timezone.now()).exists(): raise InvalidProfile('LEASE_LOST')
        current=m.HardwareBinding.objects.select_for_update().select_related('provider').get(pk=binding.pk)
        o=payload['observation']
        if not same_generation(current,binding) or o['binding_version']!=binding.binding_version or o['provider_version']!=binding.provider.version: raise InvalidProfile('BINDING_CHANGED')
        row,_=m.HardwareObservation.objects.select_for_update().get_or_create(binding=binding)
        previous=row.payload
        if previous and previous['observation']['binding_version']==binding.binding_version and previous['observation']['provider_version']==binding.provider.version:
            old=previous['observation']
            if old['provider_snapshot_id']==o['provider_snapshot_id'] and immutable(previous)!=immutable(payload): raise InvalidProfile('SNAPSHOT_MUTATED')
            if timestamp(o['source_window']['end'])<timestamp(old['source_window']['end']): raise InvalidProfile('OUT_OF_ORDER')
            if old['source_window']==o['source_window'] and old['provider_snapshot_id']!=o['provider_snapshot_id']: raise InvalidProfile('SNAPSHOT_MUTATED')
        row.payload=payload;row.save(update_fields=['payload']);bump('telemetry')

def hardware_view(binding):
    row=m.HardwareObservation.objects.filter(binding=binding).first()
    payload=row.payload if row else None
    if payload and (payload['observation']['binding_version']!=binding.binding_version or payload['observation']['provider_version']!=binding.provider.version): payload=None
    result={'id':str(binding.pk),'name':binding.name,'environment_code':binding.environment_code,'resource_type':binding.resource_type,
            'asset_id':str(binding.asset_id),'host_id':binding.host_id,'gpu_uuid':binding.gpu_uuid,'cluster_id':str(binding.cluster_id) if binding.cluster_id else None,'source_type':'INSPECTION','metrics':{},'observation':None,'data_state':'MISSING','status':'UNKNOWN'}
    if payload:
        result.update(metrics=payload['metrics'],observation={**payload['observation'],'source_type':'INSPECTION','transport_status':row.error or 'OK'},data_state=state(payload))
        if row.error and row.error!='DEMO_OFFLINE': result['data_state']='SOURCE_ERROR'
        # This contract cannot attest origin: never promote upstream health.
        result['observation']['data_state']=result['data_state']
    return result

def poll_hardware(owner,reader_factory,start,count,limit=80,deadline=16):
    import time
    from .worker import acquire,reserve_request
    from .inspection import ReadError
    from .monitoring import inspection_allowed
    for binding in m.HardwareBinding.objects.filter(enabled=True,provider__enabled=True).filter(Q(cluster__isnull=True)|Q(cluster__enabled=True,cluster__monitoring_source="INSPECTION")): m.HardwareObservation.objects.get_or_create(binding=binding)
    rows=m.HardwareObservation.objects.filter(paused=False,binding__enabled=True,binding__provider__enabled=True).filter(Q(binding__cluster__isnull=True)|Q(binding__cluster__enabled=True,binding__cluster__monitoring_source="INSPECTION")).filter(Q(next_due__isnull=True)|Q(next_due__lte=timezone.now())).order_by('last_attempt_at','binding_id')
    for bid in list(rows.values_list('binding_id',flat=True)[:max(0,limit-count)]):
        if time.monotonic()-start>=deadline or count>=limit or not acquire(owner) or not reserve_request(owner): break
        with transaction.atomic():
            m.Revision.objects.select_for_update().get_or_create(pk=1)
            binding=m.HardwareBinding.objects.select_for_update().select_related('provider').get(pk=bid)
            row=m.HardwareObservation.objects.select_for_update().get(binding=binding)
            if not inspection_allowed(binding) or not binding.enabled or not binding.provider.enabled or row.paused: continue
            row.last_attempt_at=timezone.now();row.save(update_fields=['last_attempt_at'])
        error=None;reader=None
        try:
            reader=reader_factory(binding.provider)
            publish_hardware(binding,reader.fetch_hardware_profile(binding),owner)
        except (ReadError,InvalidProfile) as exc: error=exc
        finally:
            if reader: reader.close()
        count+=1
        with transaction.atomic():
            m.Revision.objects.select_for_update().get_or_create(pk=1)
            if not m.WorkerLease.objects.filter(pk=1,owner=owner,expires_at__gt=timezone.now()).exists(): break
            current=m.HardwareBinding.objects.select_for_update().select_related('provider').get(pk=bid)
            if not same_generation(current,binding): continue
            row=m.HardwareObservation.objects.select_for_update().get(binding=binding)
            before=(row.error,row.paused)
            if error:
                row.failures+=1;row.error=error.code if isinstance(error,ReadError) else str(error);row.paused=getattr(error,'pause',False)
                delay=max(min(120,30*2**min(row.failures-1,3)),getattr(error,'retry_after',0))
            else: row.last_success_at=timezone.now();row.failures=0;row.error='';delay=30
            row.next_due=timezone.now()+timedelta(seconds=delay);row.save()
            if before!=(row.error,row.paused): bump('telemetry')
    return count
