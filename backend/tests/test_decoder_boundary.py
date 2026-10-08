"""B1/R3: exercise actual HTTP decoding and per-binding worker isolation."""
from datetime import timedelta
from unittest.mock import patch
import httpx
from django.test import TestCase,override_settings
from django.utils import timezone
from control import models as m
from control.inspection import InspectionReader,ReadError
from control.worker import round_poll
from . import test_telemetry as samples

@override_settings(PROVIDER_URLS=['https://inspection.test'])
class DecoderBoundaryTests(TestCase):
    def setUp(self):
        samples.TelemetryTests.setUp(self)
    def test_deep_json_poison_first_good_second_uses_real_reader_and_worker(self):
        bad=self.binding
        good=m.EngineBinding.objects.create(code='good',name='Good',environment_code='prod',provider=bad.provider,endpoint=bad.endpoint,environment_id=bad.environment_id,engine_id='good-engine',engine_type='vllm',model_name='model',scope='ENDPOINT')
        inputs={
            'array_1500':b'['*1500+b'0'+b']'*1500,
            'object_1500':b'{"x":'*1500+b'0'+b'}'*1500,
        }
        self.assertEqual(len(inputs['array_1500']),3001)
        for name,poison in inputs.items():
            with self.subTest(name=name):
                self.assertLess(len(poison),262144)
                m.PollState.objects.update_or_create(binding=bad,defaults={'last_attempt_at':timezone.now()-timedelta(seconds=2),'last_success_at':None,'next_due':None,'error':'','failures':0,'paused':False})
                m.PollState.objects.update_or_create(binding=good,defaults={'last_attempt_at':timezone.now()-timedelta(seconds=1),'last_success_at':None,'next_due':None,'error':'','failures':0,'paused':False})
                requests=[]
                def handler(request):
                    requests.append((request.method,request.url.path))
                    if request.url.path.endswith('/'+bad.engine_id+'/profile'):
                        return httpx.Response(200,content=poison,headers={'Content-Type':'application/json'})
                    self.assertTrue(request.url.path.endswith('/good-engine/profile'))
                    raw=samples.fixture(good);raw['snapshot_id']='good-'+name
                    return httpx.Response(200,json=raw)
                def reader(provider):return InspectionReader(provider,httpx.MockTransport(handler))
                result=round_poll('decoder-boundary',reader)
                self.assertEqual(result['polled'],2)
                self.assertEqual(requests,[('GET','/api/v1/inference-performance/engines/'+bad.engine_id+'/profile'),('GET','/api/v1/inference-performance/engines/good-engine/profile')])
                failed=m.PollState.objects.get(binding=bad)
                self.assertEqual(failed.error,'INVALID_JSON');self.assertEqual(failed.failures,1);self.assertFalse(failed.paused)
                self.assertIsNone(failed.last_success_at);self.assertGreater(failed.next_due,timezone.now())
                succeeded=m.PollState.objects.get(binding=good)
                self.assertEqual(succeeded.error,'');self.assertEqual(succeeded.failures,0);self.assertIsNotNone(succeeded.last_success_at)
                self.assertFalse(m.TelemetrySnapshot.objects.filter(binding=bad).exists())
                self.assertTrue(m.TelemetrySnapshot.objects.filter(binding=good,provider_snapshot_id='good-'+name).exists())
    def test_existing_decoder_failures_still_classified(self):
        for body in (b'\xff',b'{broken',b'{"value":NaN}'):
            with self.subTest(body=body):
                reader=InspectionReader(self.binding.provider,httpx.MockTransport(lambda _:httpx.Response(200,content=body)))
                with self.assertRaises(ReadError) as caught:reader.fetch_profile(self.binding)
                self.assertEqual(caught.exception.code,'INVALID_JSON')
                reader.close()
    def test_unrelated_programming_exception_is_not_swallowed(self):
        reader=InspectionReader(self.binding.provider,httpx.MockTransport(lambda _:httpx.Response(200,content=b'{}')))
        with patch('json.loads',side_effect=RuntimeError('intentional programming failure')):
            with self.assertRaisesRegex(RuntimeError,'intentional programming failure'):reader.fetch_profile(self.binding)
        reader.close()
