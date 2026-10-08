import copy,uuid
from datetime import timedelta
from django.test import TestCase,override_settings
from django.utils import timezone
from control import models as m
from control.telemetry import normalize,state,publish,InvalidProfile

def fixture(binding):
    now=timezone.now()
    return {'snapshot_id':'synthetic-1','engine':{'engine_id':binding.engine_id,'engine_type':binding.engine_type,'model_name':binding.model_name},'window':{'start':(now-timedelta(seconds=60)).isoformat(),'end':now.isoformat()},'status':'NORMAL','evaluation_status':'NORMAL','plugin':{'id':'inference-performance','version':'1.0.0'},'quality':{'state':'READY'},'freshness':{'state':'FRESH','max_age_seconds':300},'current_metrics':{'ttft':{'avg_ms':1,'p90_ms':2,'p95_ms':3,'p99_ms':4,'e2e_ratio':.2},'tpot':{'avg_ms':1,'p90_ms':2,'p95_ms':3,'p99_ms':4},'e2e':{'avg_ms':1,'p90_ms':2,'p95_ms':3,'p99_ms':4},'traffic':{'qps':1,'qpm':60},'throughput':{'generation_tps':10,'prompt_tps':20},'cache':{'kv_cache_hit_rate':.5},'requests':{'running':1,'waiting':0}}}
class TelemetryTests(TestCase):
    def setUp(self):
        common={'environment_code':'prod'};model=m.Model.objects.create(code='m',name='m',**common);service=m.InferenceService.objects.create(code='s',name='s',model=model,deployment_mode='COMBINED',**common);cluster=m.KubernetesCluster.objects.create(code='c',name='c',**common);endpoint=m.Endpoint.objects.create(code='e',name='e',service=service,cluster=cluster,role='COMBINED',**common);provider=m.ProviderInstance.objects.create(code='p',name='p',base_url_ref='https://inspection.test',plugin_versions=['1.0.0'],source_allowlist=['trusted'],origin_verified=True,**common);self.binding=m.EngineBinding.objects.create(code='b',name='b',provider=provider,endpoint=endpoint,environment_id=uuid.uuid4(),engine_id='engine-1',engine_type='vllm',model_name='model',scope='ENDPOINT',**common)
    def test_verified_requires_provenance_freshness(self):
        raw=fixture(self.binding);payload=normalize(raw,self.binding);self.assertEqual(state(payload),'UNVERIFIED')
        raw['provenance']={'source':'trusted','sample_id':'s1','ingested_at':timezone.now().isoformat()};payload=normalize(raw,self.binding);self.assertEqual(state(payload),'FRESH');self.assertEqual(state(payload,timezone.now()+timedelta(seconds=301)),'STALE')
        raw['window']['end']=(timezone.now()+timedelta(seconds=31)).isoformat()
        with self.assertRaisesMessage(InvalidProfile,'CLOCK_SKEW'):normalize(raw,self.binding)
    def test_invalid_values_identity_missing_group(self):
        for mutate in [lambda r:r['engine'].update(model_name='other'),lambda r:r['current_metrics']['ttft'].update(p99_ms=0),lambda r:r['current_metrics']['cache'].update(kv_cache_hit_rate=2),lambda r:r['current_metrics'].pop('traffic'),lambda r:r['current_metrics']['traffic'].update(qps=float('nan'))]:
            raw=fixture(self.binding);mutate(raw)
            with self.assertRaises(InvalidProfile):normalize(raw,self.binding)
    def test_dedupe_capacity_binding_change(self):
        payload=normalize(fixture(self.binding),self.binding);self.assertTrue(publish(self.binding,payload));self.assertFalse(publish(self.binding,payload));self.assertEqual(m.TelemetrySnapshot.objects.count(),1)
        payload=copy.deepcopy(payload);payload['observation']['provider_snapshot_id']='new'
        with self.assertRaisesMessage(InvalidProfile,'CAPACITY_EXCEEDED'):publish(self.binding,payload,budget=1)
        m.EngineBinding.objects.filter(pk=self.binding.pk).update(binding_version=2)
        with self.assertRaisesMessage(InvalidProfile,'BINDING_CHANGED'):publish(self.binding,payload)
    def test_history_is_bounded(self):
        payload=normalize(fixture(self.binding),self.binding)
        for i in range(122):
            p=copy.deepcopy(payload);p['observation']['provider_snapshot_id']=str(i);publish(self.binding,p)
        self.assertEqual(m.TelemetrySnapshot.objects.count(),120)
    def test_unknown_plugin_and_demo_never_verified(self):
        raw=fixture(self.binding);raw['provenance']={'source':'trusted','sample_id':'s1','ingested_at':timezone.now().isoformat()};raw['plugin']['version']='99'
        self.assertEqual(state(normalize(raw,self.binding)),'UNVERIFIED')
        raw['plugin']['version']='1.0.0';self.binding.origin='DEMO'
        self.assertEqual(state(normalize(raw,self.binding)),'UNVERIFIED')
