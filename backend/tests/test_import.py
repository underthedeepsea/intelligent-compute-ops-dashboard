import json,tempfile
from django.test import TestCase,override_settings
from django.contrib.auth.models import User
from django.core.management import call_command,CommandError
from control.models import Team,ImportRecord,AuditEvent
class ImportTests(TestCase):
    @override_settings(ALLOW_DEMO_IMPORT=True)
    def test_dry_run_idempotence_demo_gate(self):
        data={'source_namespace':'synthetic','source_kind':'DEMO','records':[{'collection':'teams','legacy_id':'t','fields':{'code':'t','name':'t','environment_code':'test'}}]}
        with tempfile.NamedTemporaryFile(mode='w+',suffix='.json') as f:
            json.dump(data,f);f.flush()
            with self.assertRaises(CommandError):call_command('import_gateway_catalog',file=f.name)
            call_command('import_gateway_catalog',file=f.name,allow_demo=True,dry_run=True);self.assertEqual(Team.objects.count(),0)
            call_command('import_gateway_catalog',file=f.name,allow_demo=True);call_command('import_gateway_catalog',file=f.name,allow_demo=True)
        self.assertEqual(Team.objects.count(),1);self.assertEqual(Team.objects.get().origin,'DEMO');self.assertEqual(ImportRecord.objects.count(),1)

    def test_default_source_and_explicit_source_without_users(self):
        data={'source_namespace':'reviewed','source_kind':'REVIEWED','records':[{'collection':'teams','legacy_id':'one','fields':{'code':'one','name':'One','environment_code':'PRD'}}]}
        with tempfile.NamedTemporaryFile(mode='w+',suffix='.json') as f:
            json.dump(data,f);f.flush()
            call_command('import_gateway_catalog',file=f.name)
            self.assertEqual(AuditEvent.objects.get().actor,'cli-import')
            for actor in ['', ' '*2, 'x'*151]:
                with self.assertRaises(CommandError): call_command('import_gateway_catalog',file=f.name,actor=actor)
            data['source_namespace']='explicit';data['records'][0]['fields']['code']='two'
            f.seek(0);json.dump(data,f);f.truncate();f.flush()
            call_command('import_gateway_catalog',file=f.name,actor='现场离线导入')
            self.assertTrue(AuditEvent.objects.filter(actor='现场离线导入').exists())
        self.assertEqual(User.objects.count(),0)
