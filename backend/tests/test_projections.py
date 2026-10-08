from django.contrib.auth.models import User
from control import models as m
from control.projections import screen
from control.topology import topology
from .test_telemetry import TelemetryTests
class ProjectionTests(TelemetryTests):
    def test_no_synthetic_business_or_infra_health(self):
        user=User.objects.create_superuser('root','root@example.test','password')
        t=m.Team.objects.create(code='t',name='t',environment_code='prod');b=m.Business.objects.create(code='business',name='business',environment_code='prod',team=t,owner='ops',critical=True,watch_order=1)
        data=screen('critical-apps',user);self.assertEqual(data['items'][0]['business_observed_status'],'UNKNOWN');self.assertIsNone(data['items'][0]['metrics']['availability']['value'])
        infra=screen('infrastructure',user);self.assertEqual(infra['items'],[]);self.assertEqual(infra['summary']['telemetry_state'],'UNSUPPORTED')
    def test_topology_model_actual_edges(self):
        user=User.objects.create_superuser('root','root@example.test','password');s=self.binding.endpoint.service
        data=topology(user,'model',str(s.model_id));types={e['type'] for e in data['edges']};self.assertIn('serves',types);self.assertIn('runs_in',types)
        self.assertFalse(data['truncated'])
