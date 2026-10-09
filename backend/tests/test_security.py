import json
from django.test import TransactionTestCase, Client
from django.contrib.auth.models import User, Group
from control.models import AccessScope, Team, AuditEvent
class SecurityTests(TransactionTestCase):
    def test_direct_csrf_and_projection_boundaries(self):
        self.assertEqual(User.objects.count(),0)
        c=Client(enforce_csrf_checks=True)
        for path in ['catalog/teams','gateway/keys','audit-events','integrations/status','screens/bootstrap']:
            self.assertEqual(c.get('/api/v1/'+path).status_code,200,path)
        access=c.get('/api/v1/session').json()['data']
        self.assertEqual(access['access_mode'],'direct'); self.assertTrue(access['can_write'])
        self.assertTrue({'PRD','DR','STG','DEV'}<=set(access['environments']))
        for field in ['authenticated','username','roles','local_passwordless_available']: self.assertNotIn(field,access)
        data=json.dumps({'code':'t','name':'t','environment_code':'custom'})
        self.assertEqual(c.post('/api/v1/catalog/teams',data,content_type='application/json').status_code,403)
        token=access['csrf_token']
        self.assertEqual(c.post('/api/v1/catalog/teams',data,content_type='application/json',HTTP_X_CSRFTOKEN=token,HTTP_ORIGIN='http://attacker.invalid').status_code,403)
        self.assertEqual(c.post('/api/v1/catalog/teams',data,content_type='application/json',HTTP_X_CSRFTOKEN=token).status_code,201)
        self.assertEqual(AuditEvent.objects.get().actor,'anonymous')
        for action in ['login','logout','local']:
            self.assertEqual(c.post('/api/v1/session/'+action,'{}',content_type='application/json',HTTP_X_CSRFTOKEN=token).status_code,404)
        for path in ['/admin/','/admin/login/']: self.assertEqual(c.get(path).status_code,404)
        for name in ['overview','pd-groups','infrastructure','services','critical-apps','bootstrap']:
            response=c.get('/api/v1/screens/'+name); self.assertEqual(response.status_code,200)
            for field in ['credential_ref','address_ref']: self.assertNotIn(field,response.content.decode())
        self.assertEqual(User.objects.count(),0); self.assertEqual(Group.objects.count(),0); self.assertEqual(AccessScope.objects.count(),0)
    def test_all_registered_environments_even_disabled_and_old_cookie(self):
        t=Team.objects.create(code='t',name='t',environment_code='other',enabled=False)
        self.client.cookies['sessionid']='obsolete-cookie'
        self.assertEqual(self.client.get('/api/v1/catalog/teams/'+str(t.pk)).status_code,200)
        self.assertIn('other',self.client.get('/api/v1/session').json()['data']['environments'])
        self.assertNotIn('sessionid',self.client.get('/api/v1/session').cookies)

    def test_legacy_identity_records_do_not_limit_access(self):
        u=User.objects.create_user('legacy');g=Group.objects.create(name='screen_viewer');u.groups.add(g)
        AccessScope.objects.create(user=u,environment_code='local')
        Team.objects.create(code='prod',name='Prod',environment_code='PRD')
        Team.objects.create(code='dr',name='DR',environment_code='DR',enabled=False)
        self.client.force_login(u)
        self.assertEqual(len(self.client.get('/api/v1/catalog/teams').json()['data']['items']),2)
        response=self.client.post('/api/v1/catalog/teams',json.dumps({'code':'new','name':'New','environment_code':'OTHER'}),content_type='application/json')
        self.assertEqual(response.status_code,201)
        self.assertEqual(AuditEvent.objects.get().actor,'anonymous')
        self.assertEqual(User.objects.get().username,'legacy');self.assertEqual(AccessScope.objects.get().environment_code,'local')
    def test_admin_migration_graph_retained_without_auth_middleware(self):
        from django.conf import settings
        from django.db.migrations.loader import MigrationLoader
        from django.contrib.admin.apps import AdminConfig
        from config.legacy_admin import LegacyAdminConfig
        self.assertEqual(AdminConfig.name,LegacyAdminConfig.name)
        self.assertIn(('admin','0001_initial'),MigrationLoader(None).graph.nodes)
        for name in ['SessionMiddleware','AuthenticationMiddleware','LocalSessionGuard']:
            self.assertFalse(any(name in item for item in settings.MIDDLEWARE))
