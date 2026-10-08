import json,tempfile
from django.test import TestCase,override_settings
from django.contrib.auth.models import User
from django.core.management import call_command,CommandError
from control.models import Team,ImportRecord
class ImportTests(TestCase):
    @override_settings(ALLOW_DEMO_IMPORT=True)
    def test_dry_run_idempotence_demo_gate(self):
        User.objects.create_superuser('root','root@example.test','password')
        data={'source_namespace':'synthetic','source_kind':'DEMO','records':[{'collection':'teams','legacy_id':'t','fields':{'code':'t','name':'t','environment_code':'test'}}]}
        with tempfile.NamedTemporaryFile(mode='w+',suffix='.json') as f:
            json.dump(data,f);f.flush()
            with self.assertRaises(CommandError):call_command('import_gateway_catalog',file=f.name,actor='root')
            call_command('import_gateway_catalog',file=f.name,actor='root',allow_demo=True,dry_run=True);self.assertEqual(Team.objects.count(),0)
            call_command('import_gateway_catalog',file=f.name,actor='root',allow_demo=True);call_command('import_gateway_catalog',file=f.name,actor='root',allow_demo=True)
        self.assertEqual(Team.objects.count(),1);self.assertEqual(Team.objects.get().origin,'DEMO');self.assertEqual(ImportRecord.objects.count(),1)
