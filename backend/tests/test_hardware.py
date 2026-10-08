import copy,uuid
from datetime import timedelta
import httpx
from django.test import TestCase,override_settings
from django.utils import timezone
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from control import models as m
from control.catalog import save,APIError
from control.hardware import normalize_hardware,publish_hardware,hardware_view
from control.inspection import InspectionReader,ReadError
from control.telemetry import InvalidProfile
from control.projections import screen
from control.worker import round_poll,acquire
from .test_telemetry import TelemetryTests

def fixture(b,now=None):
    now=now or timezone.now()
    numbers={'utilization_ratio':.72,'temperature_celsius':64,'memory_used_bytes':48,'memory_total_bytes':80} if b.resource_type=='GPU_POOL' else {'cpu_busy_ratio':.43,'memory_available_bytes':96,'memory_total_bytes':256}
    return {'snapshot_id':'hardware-1','asset_id':str(b.asset_id),'host_id':b.host_id,'identity':{'gpu_uuid':b.gpu_uuid,'model':'Test'} if b.gpu_uuid else {},'window_start':(now-timedelta(seconds=60)).isoformat(),'window_end':now.isoformat(),'status':'NORMAL','freshness':'FRESH','metrics':{'gpu' if b.gpu_uuid else 'host':{'identity':{},'values':{k:{'value':v,'quality':'VALID','collected_at':now.isoformat()} for k,v in numbers.items()}}}}

@override_settings(PROVIDER_URLS=['https://inspection.test'])
class HardwareTests(TestCase):
    def setUp(self):
        TelemetryTests.setUp(self)
        self.engine=self.binding
        self.binding=m.HardwareBinding.objects.create(code='hw',name='GPU 01',environment_code='prod',cluster=self.engine.endpoint.cluster,provider=self.engine.provider,environment_id=self.engine.environment_id,resource_type='GPU_POOL',asset_id=uuid.uuid4(),host_id='host1',gpu_uuid='GPU1')
        self.user=User.objects.create_user('viewer')
        m.AccessScope.objects.create(user=self.user,environment_code='prod')
        self.admin=User.objects.create_superuser('root','root@test','pw')
    def test_values_formulas_never_verified(self):
        p=normalize_hardware(fixture(self.binding),self.binding)
        self.assertEqual(p['metrics']['memory_usage_ratio']['value'],.6)
        self.assertEqual(p['observation']['origin'],'UNVERIFIED')
        publish_hardware(self.binding,p)
        v=hardware_view(self.binding);self.assertEqual(v['status'],'UNKNOWN');self.assertEqual(v['data_state'],'UNVERIFIED')
        self.binding.resource_type='HOST';self.binding.gpu_uuid=''
        self.assertEqual(normalize_hardware(fixture(self.binding),self.binding)['metrics']['memory_usage_ratio']['value'],.625)
    def test_quality_invalid_capacities_clock_identity(self):
        for quality in ('RESET','MISSING','UNSUPPORTED'):
            raw=fixture(self.binding);raw['metrics']['gpu']['values']['memory_used_bytes'].update(quality=quality,value=None)
            p=normalize_hardware(raw,self.binding);self.assertIsNone(p['metrics']['memory_usage_ratio']['value'])
        mutations=[lambda r:r.update(asset_id=str(uuid.uuid4())),lambda r:r.update(host_id='other'),lambda r:r['identity'].update(gpu_uuid='other'),lambda r:r.update(environment_id=str(uuid.uuid4())),lambda r:r.update(window_end=(timezone.now()+timedelta(seconds=60)).isoformat()),lambda r:r['metrics']['gpu']['values']['memory_total_bytes'].update(value=0),lambda r:r['metrics']['gpu']['values']['memory_used_bytes'].update(value=81),lambda r:r['metrics']['gpu']['values']['utilization_ratio'].update(value=float('nan')),lambda r:r['metrics']['gpu']['values']['temperature_celsius'].update(quality='RESET')]
        for mutate in mutations:
            raw=fixture(self.binding);mutate(raw)
            with self.assertRaises(InvalidProfile): normalize_hardware(raw,self.binding)
    def test_stale_scope_disabled_provider(self):
        raw=fixture(self.binding,timezone.now()-timedelta(seconds=301));publish_hardware(self.binding,normalize_hardware(raw,self.binding))
        self.assertEqual(hardware_view(self.binding)['data_state'],'STALE')
        self.assertEqual(len(screen('overview',self.user)['hardware']),1)
        m.AccessScope.objects.filter(user=self.user).update(environment_code='elsewhere')
        self.assertEqual(screen('overview',self.user)['hardware'],[])
        self.binding.provider.enabled=False;self.binding.provider.save()
        self.assertEqual(screen('overview',self.admin)['hardware'],[])
    def test_binding_and_provider_update_invalidate_inflight(self):
        p=normalize_hardware(fixture(self.binding),self.binding);publish_hardware(self.binding,p)
        save(m.HardwareBinding,self.admin,{'expected_version':1,'host_id':'new-host'},self.binding.pk)
        with self.assertRaisesMessage(InvalidProfile,'BINDING_CHANGED'): publish_hardware(self.binding,p)
        current=m.HardwareBinding.objects.select_related('provider').get(pk=self.binding.pk)
        self.assertEqual(hardware_view(current)['data_state'],'MISSING')
        p=normalize_hardware(fixture(current),current);publish_hardware(current,p)
        save(m.ProviderInstance,self.admin,{'expected_version':1,'origin_verified':False},current.provider_id)
        with self.assertRaisesMessage(InvalidProfile,'BINDING_CHANGED'): publish_hardware(current,p)
        current.refresh_from_db();self.assertEqual(hardware_view(current)['data_state'],'MISSING')
    def test_cross_environment_catalog_and_generation(self):
        other=m.ProviderInstance.objects.create(code='other',name='other',environment_code='other',base_url_ref='https://inspection.test')
        with self.assertRaises(ValidationError): save(m.HardwareBinding,self.admin,{'expected_version':1,'provider_id':str(other.pk)},self.binding.pk)
        with self.assertRaises(APIError): save(m.HardwareBinding,self.user,{'expected_version':1,'provider_id':str(other.pk)},self.binding.pk)
    def test_mutated_duplicate_old_window_and_lease(self):
        p=normalize_hardware(fixture(self.binding),self.binding);publish_hardware(self.binding,p)
        changed=copy.deepcopy(p);changed['metrics']['utilization_ratio']['value']=.1
        with self.assertRaisesMessage(InvalidProfile,'SNAPSHOT_MUTATED'):publish_hardware(self.binding,changed)
        old=fixture(self.binding,timezone.now()-timedelta(seconds=60));old['snapshot_id']='older'
        with self.assertRaisesMessage(InvalidProfile,'OUT_OF_ORDER'):publish_hardware(self.binding,normalize_hardware(old,self.binding))
        with self.assertRaisesMessage(InvalidProfile,'LEASE_LOST'):publish_hardware(self.binding,p,'not-owner')
    def test_reader_only_scoped_get_missing_duplicate_and_limit(self):
        calls=[]
        def handler(request):calls.append(request);return httpx.Response(200,json={'profiles':[fixture(self.binding)],'limit':200})
        reader=InspectionReader(self.binding.provider,httpx.MockTransport(handler));reader.fetch_hardware_profile(self.binding)
        self.assertEqual(calls[0].method,'GET');self.assertEqual(calls[0].url.path,'/api/v1/hardware-health/profiles')
        self.assertEqual(calls[0].url.params['environment_id'],str(self.binding.environment_id));self.assertEqual(calls[0].url.params['resource_type'],'GPU_POOL')
        for profiles,code in [([],'ASSET_NOT_RETURNED'),([fixture(self.binding)]*2,'IDENTITY_MISMATCH'),([{}]*201,'CONTRACT_INCOMPATIBLE')]:
            reader=InspectionReader(self.binding.provider,httpx.MockTransport(lambda _,p=profiles:httpx.Response(200,json={'profiles':p})))
            with self.assertRaises(ReadError) as ctx:reader.fetch_hardware_profile(self.binding)
            self.assertEqual(ctx.exception.code,code)
    def test_worker_shared_lease_errors_and_generation(self):
        m.EngineBinding.objects.filter(pk=self.engine.pk).update(enabled=False)
        class Reader:
            def __init__(self,p):pass
            def fetch_hardware_profile(self,b):return normalize_hardware(fixture(b),b)
            def close(self):pass
        self.assertTrue(acquire('owner'));self.assertEqual(round_poll('other',Reader)['polled'],0)
        self.assertEqual(round_poll('owner',Reader)['polled'],1)
        row=m.HardwareObservation.objects.get();self.assertIsNotNone(row.last_success_at)
        m.HardwareObservation.objects.update(next_due=None)
        class Broken(Reader):
            def fetch_hardware_profile(self,b):raise ReadError('ASSET_NOT_RETURNED')
        round_poll('owner',Broken);row.refresh_from_db()
        self.assertEqual(row.failures,1);self.assertEqual(hardware_view(self.binding)['data_state'],'SOURCE_ERROR')
        self.assertTrue(row.payload)

@override_settings(PROVIDER_URLS=['https://inspection.test'])
class HardwareBudgetTests(TestCase):
    def setUp(self):
        TelemetryTests.setUp(self)
        template=self.binding
        for i in range(89):
            m.EngineBinding.objects.create(code=f'budget-engine-{i}',name='engine',environment_code='prod',provider=template.provider,environment_id=template.environment_id,engine_id=f'budget-engine-{i}',engine_type='vllm',model_name='model',scope='ENDPOINT',endpoint=template.endpoint)
        self.calls={'hardware':0,'inference':0}
        calls=self.calls
        class Reader:
            def __init__(self,p):pass
            def fetch_profile(self,b):calls['inference']+=1;raise ReadError('TEST_SOURCE_UNAVAILABLE')
            def fetch_hardware_profile(self,b):calls['hardware']+=1;raise ReadError('TEST_SOURCE_UNAVAILABLE')
            def close(self):pass
        self.reader=Reader
    def hardware(self,count,**poll):
        for i in range(count):
            b=m.HardwareBinding.objects.create(code=f'budget-hw-{i}',name='GPU',environment_code='prod',provider=self.binding.provider,environment_id=self.binding.environment_id,resource_type='GPU_POOL',asset_id=uuid.uuid4(),host_id='host',gpu_uuid=f'gpu-{i}')
            m.HardwareObservation.objects.create(binding=b,**poll)
    def check_budget(self,hardware,inference):
        from unittest.mock import patch
        # Fixed monotonic time isolates request-count behavior from test-host speed.
        with patch('control.worker.time.monotonic',return_value=100):
            result=round_poll('budget-owner',self.reader)
        self.assertEqual(self.calls,{'hardware':hardware,'inference':inference})
        self.assertEqual(result['polled'],hardware+inference)
        self.assertLessEqual(result['polled'],80)
        self.assertLessEqual(m.WorkerLease.objects.get().request_count,240)
    def test_no_hardware_preserves_eighty(self):self.check_budget(0,80)
    def test_paused_hardware_does_not_reserve_inference_slots(self):
        self.hardware(1,paused=True);self.check_budget(0,80)
    def test_not_due_hardware_does_not_reserve_inference_slots(self):
        self.hardware(1,next_due=timezone.now()+timedelta(minutes=1));self.check_budget(0,80)
    def test_actual_hardware_consumes_only_actual_slots(self):
        self.hardware(3);self.check_budget(3,77)
    def test_forty_hardware_leaves_forty_and_total_eighty(self):
        self.hardware(45);self.check_budget(40,40)
    def test_shared_rate_budget_is_not_bypassed(self):
        self.hardware(3);acquire('budget-owner')
        m.WorkerLease.objects.update(rate_window=timezone.now(),request_count=235)
        self.check_budget(3,2)
