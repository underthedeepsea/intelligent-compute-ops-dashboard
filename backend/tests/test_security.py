import json
from django.test import TransactionTestCase,Client
from django.contrib.auth.models import User,Group
from control.models import AccessScope,Team
class SecurityTests(TransactionTestCase):
    def test_session_csrf_and_tv_boundaries(self):
        user=User.objects.create_user('tv',password='secure-test-pass');user.groups.add(Group.objects.create(name='screen_viewer'));AccessScope.objects.create(user=user,environment_code='prod')
        client=Client(enforce_csrf_checks=True)
        self.assertEqual(client.get('/api/v1/screens/bootstrap').status_code,401)
        self.assertEqual(client.post('/api/v1/session/login',json.dumps({'username':'tv','password':'secure-test-pass'}),content_type='application/json').status_code,403)
        token=client.get('/api/v1/session').json()['data']['csrf_token']
        self.assertEqual(client.post('/api/v1/session/login',json.dumps({'username':'tv','password':'secure-test-pass'}),content_type='application/json',HTTP_X_CSRFTOKEN=token).status_code,200)
        for path in ['catalog/teams','gateway/keys','topology','audit-events','integrations/status']:
            self.assertEqual(client.get('/api/v1/'+path).status_code,403,path)
        for name in ['overview','pd-groups','infrastructure','services','critical-apps','bootstrap']:
            r=client.get('/api/v1/screens/'+name);self.assertEqual(r.status_code,200);self.assertNotIn('credential_ref',r.content.decode());self.assertNotIn('address_ref',r.content.decode())
    def test_scope_details_and_admin(self):
        u=User.objects.create_user('op');u.groups.add(Group.objects.create(name='operator'));AccessScope.objects.create(user=u,environment_code='prod');self.client.force_login(u)
        t=Team.objects.create(code='secret',name='secret',environment_code='other')
        self.assertEqual(self.client.get('/api/v1/catalog/teams/'+str(t.pk)).status_code,404)
        self.assertEqual(self.client.get('/api/v1/catalog/teams').json()['data']['items'],[])
        self.assertEqual(self.client.post('/api/v1/catalog/teams',{},content_type='application/json').status_code,403)
