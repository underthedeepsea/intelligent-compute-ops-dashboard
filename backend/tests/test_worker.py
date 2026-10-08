import httpx
from django.test import override_settings
from control.inspection import InspectionReader,ReadError
from control.worker import acquire,round_poll
from control.models import WorkerLease,PollState
from .test_telemetry import TelemetryTests,fixture
class WorkerTests(TelemetryTests):
    @override_settings(PROVIDER_URLS=['https://inspection.test'])
    def test_get_only_and_redirect_rejection(self):
        calls=[]
        def handler(request):
            calls.append(request);return httpx.Response(200,json=fixture(self.binding))
        r=InspectionReader(self.binding.provider,httpx.MockTransport(handler));r.fetch_profile(self.binding);r.close()
        self.assertEqual(calls[0].method,'GET');self.assertEqual(calls[0].url.params['model_name'],'model');self.assertNotIn('/latest/',calls[0].url.path)
        r=InspectionReader(self.binding.provider,httpx.MockTransport(lambda _:httpx.Response(302,headers={'Location':'https://evil.test'})))
        with self.assertRaisesMessage(ReadError,''):r.fetch_profile(self.binding)
        r.close()
    def test_single_owner_worker_success_backoff(self):
        self.assertTrue(acquire('one'));self.assertFalse(acquire('two'))
        binding=self.binding
        class Reader:
            def __init__(self,p):pass
            def fetch_profile(self,b):
                from control.telemetry import normalize
                return normalize(fixture(binding),b)
            def close(self):pass
        self.assertEqual(round_poll('two',Reader)['polled'],0)
        result=round_poll('one',Reader);self.assertEqual(result['polled'],1);self.assertIsNotNone(PollState.objects.get().last_success_at)
    def test_persistent_rate_quota(self):
        from control.worker import reserve_request
        self.assertTrue(acquire('rate'))
        WorkerLease.objects.filter(pk=1).update(request_count=240,rate_window=__import__('django.utils.timezone',fromlist=['now']).now())
        self.assertFalse(reserve_request('rate'))
    def test_failure_backoff_preserves_history_and_invalidates_current(self):
        from control.telemetry import normalize,publish,InvalidProfile
        from control.projections import endpoint_view
        from django.utils import timezone
        raw=fixture(self.binding);raw['provenance']={'source':'trusted','sample_id':'s1','ingested_at':timezone.now().isoformat()};publish(self.binding,normalize(raw,self.binding))
        class Reader:
            def __init__(self,p):pass
            def fetch_profile(self,b):raise InvalidProfile('INVALID_METRIC')
            def close(self):pass
        self.assertEqual(round_poll('error',Reader)['polled'],1)
        poll=PollState.objects.get();self.assertEqual(poll.failures,1);self.assertEqual(poll.error,'INVALID_METRIC');self.assertGreater(poll.next_due,timezone.now())
        view=endpoint_view(self.binding.endpoint);self.assertEqual(view['data_state'],'INVALID');self.assertEqual(view['status'],'UNKNOWN');self.assertIsNotNone(view['observation'])
