import json
from django.test import TransactionTestCase,Client
from django.contrib.auth.models import User,Group
from control import models as m
class CatalogTests(TransactionTestCase):
    def setUp(self):
        self.user='anonymous'
    def post(self,path,data):return self.client.post('/api/v1/'+path,data=json.dumps(data),content_type='application/json')
    def entity(self,collection,code,**fields):
        response=self.post('catalog/'+collection,dict(code=code,name=code,environment_code='prod',**fields));self.assertEqual(response.status_code,201,response.content);return response.json()['data']
    def test_crud_scope_conflict_and_audit(self):
        t=self.entity('teams','t')
        response=self.client.patch('/api/v1/catalog/teams/'+t['id'],json.dumps({'expected_version':1,'name':'renamed'}),content_type='application/json');self.assertEqual(response.status_code,200)
        self.assertEqual(self.client.patch('/api/v1/catalog/teams/'+t['id'],json.dumps({'expected_version':1,'name':'stale'}),content_type='application/json').status_code,409)
        self.assertEqual(self.post('catalog/teams',{'code':'x','name':'x','environment_code':'other'}).status_code,201)
        self.assertEqual(m.AuditEvent.objects.count(),3);self.assertEqual(m.Revision.objects.get().metadata,3)
    def test_relations_and_constraint(self):
        t=self.entity('teams','t');b=self.entity('businesses','b',team_id=t['id'],owner='Ops');model=self.entity('models','m')
        k=self.post('gateway/keys',dict(code='k',name='key',environment_code='prod',team_id=t['id'],business_id=b['id'],external_key_ref='ref-001',masked_label='***001')).json()['data']
        response=self.client.put('/api/v1/gateway/keys/'+k['id']+'/model-grants',json.dumps({'expected_version':1,'model_ids':[model['id']]}),content_type='application/json');self.assertEqual(response.status_code,200);self.assertFalse(response.json()['data']['applied_to_data_plane'])
        self.assertEqual(self.client.put('/api/v1/gateway/keys/'+k['id']+'/model-grants',json.dumps({'expected_version':1,'model_ids':[]}),content_type='application/json').status_code,409)
        self.assertEqual(self.client.patch('/api/v1/catalog/teams/'+t['id'],json.dumps({'expected_version':1,'enabled':False}),content_type='application/json').status_code,409)
    def test_pd_and_parent_validation(self):
        model=self.entity('models','m');s=self.entity('services','s',model_id=model['id'],deployment_mode='SPLIT_PD');p=self.entity('pd-groups','p',service_id=s['id']);c=self.entity('clusters','c')
        self.entity('endpoints','e',service_id=s['id'],pd_group_id=p['id'],cluster_id=c['id'],role='PREFILL')
        response=self.client.patch('/api/v1/catalog/services/'+s['id'],json.dumps({'expected_version':1,'deployment_mode':'COMBINED'}),content_type='application/json');self.assertEqual(response.status_code,400);self.assertEqual(m.InferenceService.objects.get().deployment_mode,'SPLIT_PD')
    def test_unknown_fields_pagination(self):
        for i in range(3):self.entity('teams',f't{i}')
        first=self.client.get('/api/v1/catalog/teams?limit=2').json()['data'];self.assertEqual(len(first['items']),2)
        second=self.client.get('/api/v1/catalog/teams',{'limit':2,'cursor':first['next_cursor']}).json()['data'];self.assertEqual(len(second['items']),1)
        self.assertEqual(self.post('catalog/models',dict(code='x',name='x',environment_code='prod',health='NORMAL')).status_code,400)
    def test_server_generated_code_and_client_identity_rejection(self):
        import uuid
        team=self.post('catalog/teams',dict(name='automatic',environment_code='DEV')).json()['data']
        self.assertEqual(team['code'],'team-'+team['id']);uuid.UUID(team['id'])
        key=self.post('gateway/keys',dict(name='key',environment_code='DEV',team_id=team['id'],external_key_ref='external-key',masked_label='***key'))
        self.assertEqual(key.status_code,201,key.content);self.assertEqual(key.json()['data']['code'],'apikeyref-'+key.json()['data']['id'])
        denied=self.post('catalog/teams',dict(name='forged',environment_code='DEV',id=str(uuid.uuid4())))
        self.assertEqual(denied.status_code,400);self.assertEqual(denied.json()['error']['code'],'UNKNOWN_FIELDS')
        edited=self.client.patch('/api/v1/catalog/teams/'+team['id'],json.dumps({'expected_version':1,'name':'renamed'}),content_type='application/json')
        self.assertEqual(edited.status_code,200);self.assertEqual(edited.json()['data']['code'],team['code'])
    def test_postgres_concurrent_writes_one_wins(self):
        from django.db import connection,close_old_connections
        if connection.vendor!='postgresql':self.skipTest('PostgreSQL row-lock test')
        from concurrent.futures import ThreadPoolExecutor
        from control.catalog import save,APIError
        t=self.entity('teams','concurrent')
        def change(name):
            close_old_connections()
            try:
                try:save(m.Team,self.user,{'expected_version':1,'name':name},t['id']);return 'OK'
                except APIError as e:return e.code
            finally:connection.close()
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(change,['one','two']))
        self.assertCountEqual(results,['OK','VERSION_CONFLICT']);self.assertEqual(m.Team.objects.get(pk=t['id']).version,2)
    def test_runtime_members_replace_audits_timestamps(self):
        model=self.entity('models','rm');service=self.entity('services','rs',model_id=model['id'],deployment_mode='COMBINED');cluster=self.entity('clusters','rc');endpoint=self.entity('endpoints','re',service_id=service['id'],cluster_id=cluster['id'],role='COMBINED')
        payload={'expected_version':1,'items':[{'code':'pod','name':'Pod','namespace':'default','pod_uid':'uid1','observed_at':'2026-09-26T00:00:00Z'}]}
        response=self.client.put('/api/v1/catalog/endpoints/'+endpoint['id']+'/runtime-members',json.dumps(payload),content_type='application/json');self.assertEqual(response.status_code,200,response.content);self.assertEqual(len(response.json()['data']['items']),1);self.assertEqual(response.json()['data']['version'],2)
