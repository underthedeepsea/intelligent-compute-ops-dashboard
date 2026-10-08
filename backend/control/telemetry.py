import hashlib,json,math
from datetime import timedelta
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.db import transaction
from django.db.models import Sum
from .models import TelemetrySnapshot,EngineBinding,WorkerLease
from .access import bump

class InvalidProfile(Exception):pass
METRICS={f'{g}_{s}_ms':(g,s+'_ms','ms' if g!='tpot' else 'ms/token') for g in ('ttft','tpot','e2e') for s in ('avg','p90','p95','p99')}
METRICS.update({'ttft_e2e_ratio':('ttft','e2e_ratio','ratio'),'request_rate':('traffic','qps','requests/s'),'request_rate_per_minute':('traffic','qpm','requests/min'),'generated_tokens_per_second':('throughput','generation_tps','tokens/s'),'input_tokens_per_second':('throughput','prompt_tps','tokens/s'),'kv_cache_hit_ratio':('cache','kv_cache_hit_rate','ratio'),'running':('requests','running','requests'),'waiting':('requests','waiting','requests')})
def metric(value=None,unit='',state='UNSUPPORTED',scope='ENDPOINT'):return {'value':value,'unit':unit,'state':state,'scope':scope}
def finite_number(value):
    if type(value) not in (int,float):return False
    try:return math.isfinite(value)
    except (OverflowError,ValueError):return False

def typed_text(value,maximum=240):
    return isinstance(value,str) and 0<len(value)<=maximum

def normalize(raw,binding,now=None):
    now=now or timezone.now()
    if not isinstance(raw,dict):raise InvalidProfile('CONTRACT_INCOMPATIBLE')
    engine=raw.get('engine')
    if not isinstance(engine,dict):raise InvalidProfile('CONTRACT_INCOMPATIBLE')
    for key in ('engine_id','engine_type','model_name'):
        if not typed_text(engine.get(key)) or engine[key]!=getattr(binding,key):raise InvalidProfile('IDENTITY_MISMATCH')
    environment=raw.get('environment_id',str(binding.environment_id))
    if not isinstance(environment,str) or environment!=str(binding.environment_id):raise InvalidProfile('IDENTITY_MISMATCH')
    window=raw.get('source_window',raw.get('window'))
    if not isinstance(window,dict) or not all(isinstance(window.get(k),str) for k in ('start','end')):raise InvalidProfile('INVALID_WINDOW')
    try:start,end=parse_datetime(window['start']),parse_datetime(window['end'])
    except (TypeError,ValueError,OverflowError):raise InvalidProfile('INVALID_WINDOW')
    if not start or not end or timezone.is_naive(start) or timezone.is_naive(end) or start>=end:raise InvalidProfile('INVALID_WINDOW')
    if end>now+timedelta(seconds=30):raise InvalidProfile('CLOCK_SKEW')
    current=raw.get('current_metrics')
    if not isinstance(current,dict):raise InvalidProfile('CONTRACT_INCOMPATIBLE')
    metrics={}
    for name,(group,key,unit) in METRICS.items():
        values=current.get(group)
        if not isinstance(values,dict):raise InvalidProfile('INVALID_METRIC')
        value=values.get(key)
        if value is None:raise InvalidProfile('MISSING_METRIC')
        if not finite_number(value) or value<0 or unit=='ratio' and value>1:raise InvalidProfile('INVALID_METRIC')
        metrics[name]=metric(value,unit,'AVAILABLE',binding.scope)
    for group in ('ttft','tpot','e2e'):
        values=[metrics[f'{group}_{p}_ms']['value'] for p in ('p90','p95','p99')]
        if values!=sorted(values):raise InvalidProfile('INVALID_PERCENTILES')
    plugin=raw.get('plugin',{});provenance=raw.get('provenance',{});quality=raw.get('quality',{})
    if not all(isinstance(v,dict) for v in (plugin,provenance,quality)):raise InvalidProfile('CONTRACT_INCOMPATIBLE')
    for obj,fields in ((plugin,('id','version')),(provenance,('source','sample_id','ingested_at')),(quality,('state',))):
        for key in fields:
            if key in obj and not typed_text(obj[key]):raise InvalidProfile('CONTRACT_INCOMPATIBLE')
    if 'pending_confirmation' in quality and type(quality['pending_confirmation']) is not bool:raise InvalidProfile('INVALID_QUALITY')
    status=raw.get('status','UNKNOWN');evaluation=raw.get('evaluation_status','UNKNOWN')
    allowed={'NORMAL','WARNING','CRITICAL','UNKNOWN','OK','PASS','FAIL','ERROR'}
    if not isinstance(status,str) or not isinstance(evaluation,str) or status not in allowed or evaluation not in allowed:raise InvalidProfile('CONTRACT_INCOMPATIBLE')
    supported=plugin.get('id')=='inference-performance' and plugin.get('version')=='1.0.0' and plugin.get('version') in binding.provider.plugin_versions
    try:provenance_time=parse_datetime(provenance.get('ingested_at',''))
    except (TypeError,ValueError,OverflowError):provenance_time=None
    verified=bool(provenance_time and not timezone.is_naive(provenance_time)) and binding.origin!='DEMO' and binding.provider.origin_verified and provenance.get('source') in binding.provider.source_allowlist and bool(provenance.get('sample_id')) and supported
    freshness=raw.get('freshness')
    if not isinstance(freshness,dict) or not isinstance(freshness.get('state'),str) or freshness['state'] not in {'FRESH','STALE'}:raise InvalidProfile('INVALID_FRESHNESS')
    max_age=freshness.get('max_age_seconds',300)
    if not finite_number(max_age) or max_age<=0:raise InvalidProfile('INVALID_FRESHNESS')
    snapshot_id=raw.get('snapshot_id')
    if not typed_text(snapshot_id):raise InvalidProfile('INVALID_SNAPSHOT_ID')
    result={'metrics':metrics,'observation':{'binding_id':str(binding.pk),'binding_version':binding.binding_version,'provider_id':str(binding.provider_id),'provider_version':binding.provider.version,'identity':{'environment_id':str(binding.environment_id),**{k:engine[k] for k in ('engine_id','engine_type','model_name')},'scope':binding.scope},'provider_snapshot_id':snapshot_id,'source_window':{'start':start.isoformat(),'end':end.isoformat()},'fetched_at':now.isoformat(),'origin':'VERIFIED' if verified else 'UNVERIFIED','freshness':freshness['state'],'max_age_seconds':min(300,max_age),'upstream_status':status,'upstream_evaluation_status':evaluation,'transport_status':'OK'},'evidence':{'plugin':{k:plugin[k] for k in ('id','version') if k in plugin},'quality':{k:quality[k] for k in ('state','pending_confirmation') if k in quality},'provenance':{k:provenance[k] for k in ('source','sample_id','ingested_at') if k in provenance}}}
    if len(json.dumps(result).encode())>65536:raise InvalidProfile('NORMALIZED_TOO_LARGE')
    return result

def same_generation(current,captured):
    from .monitoring import inspection_allowed
    return (inspection_allowed(current) and current.enabled and current.provider.enabled and
            current.binding_version==captured.binding_version and
            current.provider_id==captured.provider_id and
            current.provider.version==captured.provider.version)

def immutable_sample(payload):
    o=payload['observation']
    return {'metrics':payload['metrics'],'identity':{k:o.get(k) for k in ('binding_id','binding_version','provider_id','provider_version','identity','provider_snapshot_id','source_window')},'provenance':payload.get('evidence',{}).get('provenance',{})}

def meaningful_payload(payload):
    value=dict(payload);value['observation']={k:v for k,v in payload['observation'].items() if k!='fetched_at'}
    return value

def state(payload,now=None):
    if not payload:return 'MISSING'
    o=payload['observation'];end=parse_datetime(o['source_window']['end']);now=now or timezone.now()
    if end>now+timedelta(seconds=30):return 'INVALID'
    if o['freshness']=='STALE' or (now-end).total_seconds()>o.get('max_age_seconds',300):return 'STALE'
    if o['origin']!='VERIFIED':return 'UNVERIFIED'
    return 'FRESH'

def publish(binding,payload,owner=None,budget=209715200):
    with transaction.atomic():
        # Global revision row serializes cache budget checks and all publications.
        from .models import Revision
        Revision.objects.select_for_update().get_or_create(pk=1)
        if owner and not WorkerLease.objects.filter(pk=1,owner=owner,expires_at__gt=timezone.now()).exists():raise InvalidProfile('LEASE_LOST')
        current=EngineBinding.objects.select_for_update().select_related('provider').get(pk=binding.pk)
        if not same_generation(current,binding):raise InvalidProfile('BINDING_CHANGED')
        if payload['observation'].get('provider_version')!=binding.provider.version or payload['observation'].get('binding_version')!=binding.binding_version:raise InvalidProfile('BINDING_CHANGED')
        o=payload['observation'];sid=o['provider_snapshot_id'];data=json.dumps(payload,sort_keys=True).encode();digest=hashlib.sha256(data).hexdigest()
        existing=TelemetrySnapshot.objects.filter(binding=binding,binding_version=binding.binding_version,provider_snapshot_id=sid).first()
        if existing:
            if immutable_sample(existing.payload)!=immutable_sample(payload):raise InvalidProfile('SNAPSHOT_MUTATED')
            changed=meaningful_payload(existing.payload)!=meaningful_payload(payload)
            total=TelemetrySnapshot.objects.aggregate(total=Sum('json_bytes'))['total'] or 0
            if total-existing.json_bytes+len(data)>budget:raise InvalidProfile('CAPACITY_EXCEEDED')
            existing.payload=payload;existing.json_bytes=len(data);existing.content_hash=digest
            existing.save(update_fields=['payload','json_bytes','content_hash'])
            if changed:bump('telemetry')
            return changed
        cutoff=timezone.now()-timedelta(hours=6)
        for bid,version in TelemetrySnapshot.objects.values_list('binding_id','binding_version').distinct():
            q=TelemetrySnapshot.objects.filter(binding_id=bid,binding_version=version).order_by('-source_end','-ingested_at')
            if not EngineBinding.objects.filter(pk=bid,binding_version=version,enabled=True).exists():
                q.filter(source_end__lt=cutoff).delete()
            latest=q.first()
            if latest:
                q.exclude(pk=latest.pk).filter(source_end__lt=cutoff).delete()
                keep=list(q.values_list('pk',flat=True)[:119])
                q.exclude(pk__in=keep).delete()
        total=TelemetrySnapshot.objects.aggregate(total=Sum('json_bytes'))['total'] or 0
        if total+len(data)>budget:raise InvalidProfile('CAPACITY_EXCEEDED')
        TelemetrySnapshot.objects.create(binding=binding,binding_version=binding.binding_version,provider_snapshot_id=sid,source_end=parse_datetime(o['source_window']['end']),payload=payload,content_hash=digest,json_bytes=len(data))
        bump('telemetry');return True
