import time,uuid
from datetime import timedelta
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from .models import WorkerLease,PollState,EngineBinding,Revision
from .inspection import InspectionReader,ReadError
from .telemetry import publish,InvalidProfile,same_generation
from .access import bump

def acquire(owner):
    with transaction.atomic():
        lease,_=WorkerLease.objects.select_for_update().get_or_create(pk=1,defaults={'owner':owner,'expires_at':timezone.now()})
        if lease.owner!=owner and lease.expires_at>timezone.now():return False
        lease.owner=owner;lease.expires_at=timezone.now()+timedelta(seconds=45);lease.save();return True

def reserve_request(owner):
    with transaction.atomic():
        lease=WorkerLease.objects.select_for_update().get(pk=1)
        now=timezone.now()
        if lease.owner!=owner or lease.expires_at<=now:return False
        if not lease.rate_window or (now-lease.rate_window).total_seconds()>=60:
            lease.rate_window=now;lease.request_count=0
        if lease.request_count>=240:return False
        lease.request_count+=1;lease.save(update_fields=['rate_window','request_count']);return True

def round_poll(owner=None,reader_factory=InspectionReader):
    owner=owner or str(uuid.uuid4())
    if not acquire(owner):return {'lease':False,'polled':0}
    from .monitoring import inspection_allowed
    start=time.monotonic();count=0
    from .hardware import poll_hardware
    count=poll_hardware(owner,reader_factory,start,count,limit=40,deadline=8)
    for binding in EngineBinding.objects.filter(enabled=True,provider__enabled=True,endpoint__enabled=True,endpoint__cluster__enabled=True,endpoint__cluster__monitoring_source="INSPECTION").order_by('code'):
        PollState.objects.get_or_create(binding=binding)
    due=PollState.objects.filter(paused=False,binding__enabled=True,binding__provider__enabled=True,binding__endpoint__enabled=True,binding__endpoint__cluster__enabled=True,binding__endpoint__cluster__monitoring_source="INSPECTION").filter(Q(next_due__isnull=True)|Q(next_due__lte=timezone.now())).order_by('last_attempt_at','binding_id')
    inference_limit=max(0,80-count)
    ids=list(due.values_list('binding_id',flat=True)[:inference_limit])
    for bid in ids:
        if time.monotonic()-start>=16 or count>=80:break
        if not acquire(owner) or not reserve_request(owner):break
        with transaction.atomic():
            Revision.objects.select_for_update().get_or_create(pk=1)
            binding=EngineBinding.objects.select_for_update(of=('self',)).select_related('provider','endpoint','runtime_member').get(pk=bid)
            poll=PollState.objects.select_for_update().get(binding=binding)
            if not inspection_allowed(binding) or not binding.enabled or not binding.provider.enabled or poll.paused:continue
            poll.last_attempt_at=timezone.now();poll.save(update_fields=['last_attempt_at'])
        reader=None;error=None
        try:
            reader=reader_factory(binding.provider);payload=reader.fetch_profile(binding);publish(binding,payload,owner)
        except (ReadError,InvalidProfile) as exc:error=exc
        finally:
            if reader:reader.close()
        with transaction.atomic():
            Revision.objects.select_for_update().get_or_create(pk=1)
            if not WorkerLease.objects.filter(pk=1,owner=owner,expires_at__gt=timezone.now()).exists():break
            current=EngineBinding.objects.select_for_update().select_related('provider').get(pk=bid)
            if not same_generation(current,binding):
                count+=1
                continue
            poll=PollState.objects.select_for_update().get(binding=binding)
            before=(poll.error,poll.paused,bool(poll.last_success_at))
            if error:
                poll.failures+=1;poll.error=error.code if isinstance(error,ReadError) else str(error)
                poll.paused=getattr(error,'pause',False)
                delay=max(min(120,30*2**min(poll.failures-1,3)),getattr(error,'retry_after',0))
            else:
                poll.last_success_at=timezone.now();poll.failures=0;poll.error='';delay=30
            poll.next_due=timezone.now()+timedelta(seconds=delay);poll.save()
            if before!=(poll.error,poll.paused,bool(poll.last_success_at)):bump('telemetry')
        count+=1
    # Sequential GETs provide concurrency=1, below max=4. Round <=80 reads / >=20s gives <=240/min.
    return {'lease':True,'polled':count,'backlog':due.count()}
