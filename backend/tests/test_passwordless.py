import json
from io import StringIO
from django.test import TestCase, Client, override_settings
from django.contrib.auth.models import User, Group
from django.core.management import call_command, CommandError
from control.models import AccessScope, Team, AuditEvent
from control.local_access import MARKER

@override_settings(LOCAL=True, PASSWORDLESS_LOCAL=True, PASSWORDLESS_USERNAME='local-preview', PASSWORDLESS_ENVIRONMENT='local', ALLOWED_HOSTS=['localhost','127.0.0.1','[::1]','evil.test'])
class PasswordlessTests(TestCase):
    def setUp(self):
        call_command('bootstrap_local_access', stdout=StringIO())
        self.user=User.objects.get(username='local-preview')
        self.client=Client(enforce_csrf_checks=True, HTTP_HOST='127.0.0.1', REMOTE_ADDR='127.0.0.1')
    def token(self, client=None):
        return (client or self.client).get('/api/v1/session').json()['data']['csrf_token']
    def enter(self, client=None, **extra):
        client=client or self.client
        return client.post('/api/v1/session/local', '{}', content_type='application/json', HTTP_X_CSRFTOKEN=self.token(client), **extra)
    def test_read_only_bootstrap_and_scoped_session(self):
        r=self.client.get('/api/v1/session');self.assertFalse(r.json()['data']['authenticated']);self.assertTrue(r.json()['data']['local_passwordless_available'])
        self.assertEqual(r['Cache-Control'],'no-store')
        self.assertEqual(self.client.get('/api/v1/catalog/teams').status_code,401)
        self.assertNotIn('_auth_user_id',self.client.session)
        self.assertEqual(self.client.get('/api/v1/session/local').status_code,405)
        r=self.enter();self.assertEqual(r.status_code,200);self.assertEqual(r.json()['data']['roles'],['catalog_admin']);self.assertEqual(r.json()['data']['environments'],['local'])
        self.assertFalse(self.user.is_superuser);self.assertFalse(self.user.has_usable_password())
        self.assertEqual(AuditEvent.objects.filter(action='local_session_start').count(),1)
        self.enter();self.assertEqual(AuditEvent.objects.filter(action='local_session_start').count(),1)
        self.assertEqual(self.client.get('/admin/').status_code,200)
        self.assertEqual(self.client.get('/admin/auth/user/').status_code,403)
        for name in ['overview','pd-groups','infrastructure','services','critical-apps','bootstrap']:
            self.assertEqual(self.client.get('/api/v1/screens/'+name).status_code,200)
    def test_csrf_and_client_identity_rejected(self):
        self.token()
        self.assertEqual(self.client.post('/api/v1/session/local','{}',content_type='application/json').status_code,403)
        self.assertEqual(self.client.post('/api/v1/session/local','{}',content_type='application/json',HTTP_X_CSRFTOKEN='bad').status_code,403)
        r=self.client.post('/api/v1/session/local',json.dumps({'username':'admin'}),content_type='application/json',HTTP_X_CSRFTOKEN=self.token());self.assertEqual(r.status_code,400)
        self.assertEqual(self.enter(HTTP_ORIGIN='https://evil.test').status_code,403)
        self.assertNotIn('_auth_user_id',self.client.session)
    def test_remote_host_and_proxy_boundaries(self):
        for extra in [{'REMOTE_ADDR':'192.0.2.1'},{'HTTP_HOST':'evil.test'},{'HTTP_FORWARDED':'for=127.0.0.1'},{'HTTP_X_FORWARDED_FOR':'127.0.0.1'},{'HTTP_X_FORWARDED_PROTO':'https'},{'HTTP_X_REAL_IP':'127.0.0.1'},{'HTTP_X_AUTH_REQUEST_USER':'admin'},{'HTTP_REMOTE_USER':'admin'}]:
            with self.subTest(extra=extra):self.assertEqual(self.enter(**extra).status_code,403)
        self.assertNotIn('_auth_user_id',self.client.session)
        for host,addr in [('localhost','127.0.0.1'),('[::1]','::1')]:
            client=Client(enforce_csrf_checks=True,HTTP_HOST=host,REMOTE_ADDR=addr)
            self.assertEqual(self.enter(client).status_code,200)
    def test_either_switch_disabled(self):
        for options in [{'LOCAL':False},{'PASSWORDLESS_LOCAL':False}]:
            with self.subTest(options=options),override_settings(**options):
                self.assertFalse(self.client.get('/api/v1/session').json()['data']['local_passwordless_available'])
                self.assertEqual(self.enter().status_code,403)
                with self.assertRaises(CommandError):call_command('bootstrap_local_access',stdout=StringIO())
    def test_existing_session_not_elevated(self):
        user=User.objects.create_user('tv');user.groups.add(Group.objects.create(name='screen_viewer'));AccessScope.objects.create(user=user,environment_code='other')
        self.client.force_login(user)
        r=self.enter();self.assertEqual(r.json()['data']['username'],'tv');self.assertEqual(r.json()['data']['roles'],['screen_viewer']);self.assertEqual(r.json()['data']['environments'],['other'])
        self.assertEqual(self.client.get('/api/v1/catalog/teams').status_code,403)
        self.assertEqual(AuditEvent.objects.filter(action='local_session_start').count(),0)
    def test_scope_write_and_admin_boundaries(self):
        self.enter();token=self.token();outside=Team.objects.create(code='outside',name='Other',environment_code='other')
        self.assertEqual(self.client.get('/api/v1/catalog/teams').json()['data']['items'],[])
        self.assertEqual(self.client.get('/api/v1/catalog/teams/'+str(outside.pk)).status_code,404)
        def create(env,csrf=True):
            return self.client.post('/api/v1/catalog/teams',json.dumps({'code':'test','name':'Allowed','environment_code':env}),content_type='application/json',**({'HTTP_X_CSRFTOKEN':token} if csrf else {}))
        self.assertEqual(create('local',False).status_code,403)
        self.assertEqual(create('other').status_code,403)
        self.assertEqual(create('local').status_code,201)
        self.assertTrue(AuditEvent.objects.filter(actor='local-preview',environment_code='local',action='create').exists())
        self.assertNotContains(self.client.get('/admin/control/team/'),'Other')
        self.assertEqual(self.client.get('/admin/control/team/'+str(outside.pk)+'/change/').status_code,302)
        self.assertEqual(self.client.get('/admin/control/accessscope/').status_code,403)
    def test_provision_idempotent_no_existing_user_elevation(self):
        call_command('bootstrap_local_access',stdout=StringIO());self.assertEqual(User.objects.count(),1)
        self.assertEqual(AuditEvent.objects.filter(action='create_local_identity').count(),1)
        outsider=User.objects.create_user('existing',password='original')
        with override_settings(PASSWORDLESS_USERNAME='existing'):
            with self.assertRaises(CommandError):call_command('bootstrap_local_access',stdout=StringIO())
        outsider.refresh_from_db();self.assertFalse(outsider.is_staff);self.assertFalse(outsider.groups.exists());self.assertFalse(AccessScope.objects.filter(user=outsider).exists());self.assertTrue(outsider.check_password('original'))
    def test_missing_and_changed_identity_fail_closed(self):
        for field,value in [('is_active',False),('is_superuser',True),('is_staff',False)]:
            original=getattr(self.user,field);setattr(self.user,field,value);self.user.save()
            self.assertEqual(self.enter().status_code,403)
            with self.assertRaises(CommandError):call_command('bootstrap_local_access',stdout=StringIO())
            setattr(self.user,field,original);self.user.save()
        AccessScope.objects.create(user=self.user,environment_code='other');self.assertEqual(self.enter().status_code,403)
        AccessScope.objects.filter(user=self.user,environment_code='other').delete()
        self.user.groups.remove(Group.objects.get(name=MARKER));self.assertEqual(self.enter().status_code,403)
        self.user.delete();self.assertEqual(self.enter().status_code,403)

    def test_issued_session_direct_access_rejects_all_identity_drift(self):
        from django.contrib.auth.models import Permission
        from control.local_access import SESSION_MARKER
        perm=Permission.objects.get(content_type__app_label='auth',codename='change_user')
        def scalar(user,field,value):
            setattr(user,field,value);user.save(update_fields=[field])
        mutations={
            'scope':lambda u:AccessScope.objects.create(user=u,environment_code='other'),
            'superuser':lambda u:scalar(u,'is_superuser',True),
            'username':lambda u:scalar(u,'username',u.username+'-renamed'),
            'staff':lambda u:scalar(u,'is_staff',False),
            'inactive':lambda u:scalar(u,'is_active',False),
            'marker':lambda u:u.groups.remove(Group.objects.get(name=MARKER)),
            'role':lambda u:u.groups.remove(Group.objects.get(name='catalog_admin')),
            'direct_permission':lambda u:u.user_permissions.add(perm),
            'role_permission':lambda u:Group.objects.get(name='catalog_admin').permissions.add(perm),
            'marker_permission':lambda u:Group.objects.get(name=MARKER).permissions.add(perm),
        }
        for path in ['/api/v1/catalog/teams','/admin/auth/user/','/api/v1/session/local']:
            for name,mutate in mutations.items():
                with self.subTest(path=path,drift=name),override_settings(PASSWORDLESS_USERNAME='drift-'+name):
                    old=User.objects.filter(username='drift-'+name).first()
                    if old:old.delete()
                    call_command('bootstrap_local_access',stdout=StringIO())
                    user=User.objects.get(username='drift-'+name)
                    client=Client(enforce_csrf_checks=True,HTTP_HOST='127.0.0.1',REMOTE_ADDR='127.0.0.1')
                    token=self.enter(client).json()['data']['csrf_token']
                    self.assertIn(SESSION_MARKER,client.session)
                    mutate(user)
                    try:
                        if path.endswith('/local'):
                            response=client.post(path,'{}',content_type='application/json',HTTP_X_CSRFTOKEN=token)
                        else:response=client.get(path)
                        self.assertEqual(response.status_code,403)
                        self.assertEqual(response.json()['error']['code'],'LOCAL_SESSION_INVALID')
                        self.assertNotIn('_auth_user_id',client.session)
                        self.assertNotIn(SESSION_MARKER,client.session)
                        self.assertEqual(client.get('/api/v1/catalog/teams').status_code,401)
                    finally:
                        for group in Group.objects.filter(name__in=['catalog_admin',MARKER]):group.permissions.clear()
                        user.delete()

    def test_issued_session_rejects_configuration_and_request_drift(self):
        from control.local_access import SESSION_MARKER
        options=[{'PASSWORDLESS_LOCAL':False},{'LOCAL':False},{'PASSWORDLESS_USERNAME':'another'},{'PASSWORDLESS_ENVIRONMENT':'other'}]
        for options in options:
            for path in ['/api/v1/catalog/teams','/admin/']:
                client=Client(enforce_csrf_checks=True,HTTP_HOST='127.0.0.1',REMOTE_ADDR='127.0.0.1')
                self.assertEqual(self.enter(client).status_code,200)
                with self.subTest(options=options,path=path),override_settings(**options):
                    self.assertEqual(client.get(path).status_code,403)
                    self.assertNotIn(SESSION_MARKER,client.session)
        for extra in [{'REMOTE_ADDR':'192.0.2.1'},{'HTTP_HOST':'evil.test'},{'HTTP_X_FORWARDED_FOR':'127.0.0.1'}]:
            client=Client(enforce_csrf_checks=True,HTTP_HOST='127.0.0.1',REMOTE_ADDR='127.0.0.1')
            self.assertEqual(self.enter(client).status_code,200)
            self.assertEqual(client.get('/admin/',**extra).status_code,403)
            self.assertNotIn('_auth_user_id',client.session)

    def test_preexisting_group_permissions_refuse_bootstrap_and_login_without_changes(self):
        from django.contrib.auth.models import Permission
        perm=Permission.objects.get(content_type__app_label='auth',codename='change_user')
        for name in ['catalog_admin',MARKER]:
            with self.subTest(group=name):
                group=Group.objects.get(name=name);group.permissions.add(perm)
                try:
                    with override_settings(PASSWORDLESS_USERNAME='not-created'):
                        with self.assertRaises(CommandError):call_command('bootstrap_local_access',stdout=StringIO())
                        self.assertFalse(User.objects.filter(username='not-created').exists())
                    old_password=self.user.password
                    with self.assertRaises(CommandError):call_command('bootstrap_local_access',stdout=StringIO())
                    self.assertEqual(self.enter().status_code,403)
                    self.user.refresh_from_db();self.assertEqual(self.user.password,old_password)
                    self.assertTrue(group.permissions.filter(pk=perm.pk).exists())
                finally:group.permissions.remove(perm)

    def test_reinitialize_revokes_unmarked_legacy_session_preserves_ordinary_users(self):
        from control.local_access import SESSION_MARKER
        legacy=Client(HTTP_HOST='127.0.0.1',REMOTE_ADDR='127.0.0.1');legacy.force_login(self.user)
        self.assertNotIn(SESSION_MARKER,legacy.session)
        self.assertEqual(legacy.get('/api/v1/catalog/teams').status_code,200)
        ordinary=User.objects.create_superuser('ordinary-admin',password='test-original')
        regular=Client(HTTP_HOST='127.0.0.1',REMOTE_ADDR='127.0.0.1');regular.force_login(ordinary)
        self.assertEqual(self.enter().status_code,200)
        call_command('bootstrap_local_access',stdout=StringIO())
        self.assertEqual(legacy.get('/api/v1/catalog/teams').status_code,401)
        self.assertEqual(self.client.get('/api/v1/catalog/teams').status_code,403)
        self.assertEqual(regular.get('/admin/auth/user/').status_code,200)
        with override_settings(PASSWORDLESS_LOCAL=False,PASSWORDLESS_ENVIRONMENT='changed'):
            self.assertEqual(regular.get('/admin/auth/user/').status_code,200)
        ordinary.refresh_from_db();self.assertTrue(ordinary.check_password('test-original'))
        self.assertEqual(self.enter().status_code,200)
