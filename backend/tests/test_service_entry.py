import json,copy,uuid,threading
from concurrent.futures import ThreadPoolExecutor
from django.test import TransactionTestCase,Client
from django.db import connection,close_old_connections
from django.utils import timezone
from control import models as m
from control.catalog import serialize,save,APIError
from control import service_entry as e

class ServiceEntryTests(TransactionTestCase):
    def setUp(self):
        self.team=self.entity(m.Team,'team');self.business=self.entity(m.Business,'business',team=self.team,owner='Ops')
        self.model=self.entity(m.Model,'model');self.cluster=self.entity(m.KubernetesCluster,'cluster')
        m.Revision.objects.create(pk=1)
    def entity(self,entity_model,name,**attrs):
        obj=entity_model(code=name+'-'+uuid.uuid4().hex,name=name,environment_code='DEV',**attrs);obj.full_clean();obj.save();return obj
    def endpoint(self,role='COMBINED',**changes):
        p=dict(name='instance',role=role,cluster_ref={'id':str(self.cluster.pk)},namespace='inference',workload_kind='Deployment',workload_ref='llm',address_ref='http://llm:8000',configured_nodes=['node-a','node-b']);p.update(changes);return p
    def payload(self,snap=None):
        data=dict(expected_metadata_revision=e.revision(),expected_versions=e.options('DEV')['expected_versions'],service=dict(name='service',environment_code='DEV',deployment_mode='COMBINED',model_ref={'id':str(self.model.pk)}),team_ref={'id':str(self.team.pk)},business_refs=[{'id':str(self.business.pk)}],remove_business_ids=[],groups=[],endpoints=[self.endpoint()],retire_ids={'groups':[],'endpoints':[]})
        if snap:
            data['expected_metadata_revision']=snap['metadata_revision'];data['expected_versions']=snap['expected_versions'];data['service']['deployment_mode']=snap['service']['deployment_mode']
            data['endpoints']=[{'id':x['id'],'unchanged':True} for x in snap['endpoints'] if x['enabled'] and x['pd_group_id'] is None]
            data['groups']=[{'id':x['id'],'unchanged':True} for x in snap['groups'] if x['enabled']]
        return data
    def request(self,method,path,payload=None,client=None):
        client=client or self.client
        return getattr(client,method)('/api/v1/service-entry/'+path,data=json.dumps(payload),content_type='application/json') if payload is not None else getattr(client,method)('/api/v1/service-entry/'+path)
    def test_create_and_actual_persistence_no_observations(self):
        response=self.request('post','services',self.payload());self.assertEqual(response.status_code,201,response.content)
        data=response.json()['data'];service=m.InferenceService.objects.get(pk=data['service']['id']);ep=m.Endpoint.objects.get(service=service)
        self.assertTrue(service.code.startswith('inferenceservice-'));uuid.UUID(data['service']['id'])
        self.assertEqual(ep.configured_nodes,['node-a','node-b']);self.assertEqual(m.RuntimeMember.objects.count(),0)
        self.assertEqual(m.AuditEvent.objects.get().actor,'anonymous');self.assertEqual(e.revision(),1)
        reread=self.request('get','services/'+str(service.pk)).json()['data'];self.assertEqual(reread['endpoints'][0]['namespace'],'inference')
    def test_saved_environment_matches_gateway_and_same_origin_screen_sources(self):
        p=self.payload();p['service']['environment_code']='PRD';p['expected_versions']={};p['team_ref']={'create':{'form_key':'prd_team','name':'PRD team'}};p['business_refs']=[{'create':{'form_key':'prd_business','name':'PRD business','owner':'Ops'}}]
        p['service']['model_ref']={'create':{'form_key':'prd_model','name':'PRD model'}};p['endpoints'][0]['cluster_ref']={'create':{'form_key':'prd_cluster','name':'PRD cluster'}}
        saved=self.request('post','services',p).json();pk=saved['data']['service']['id'];revision=saved['metadata_revision']
        gateway=self.request('get','services?environment_code=PRD').json();self.assertEqual(gateway['data']['items'][0]['id'],pk);self.assertEqual(gateway['metadata_revision'],revision)
        bootstrap=self.client.get('/api/v1/screens/bootstrap').json();session=self.client.get('/api/v1/session').json();self.assertEqual(bootstrap['data']['environments'],session['data']['environments']);self.assertIn('PRD',bootstrap['data']['environments'])
        screens=self.client.get('/api/v1/screens/services').json();screen_service=next(x for x in screens['data']['items'] if x['id']==pk)
        self.assertEqual(screen_service['environment_code'],'PRD');self.assertEqual(screens['metadata_revision'],revision);self.assertEqual(bootstrap['metadata_revision'],revision)
        overview=self.client.get('/api/v1/screens/overview').json();screen_endpoint=next(x for x in overview['data']['items'] if x['service_id']==pk)
        self.assertEqual(screen_endpoint['environment_code'],'PRD');self.assertEqual(screen_endpoint['data_state'],'UNMAPPED');self.assertEqual(screen_endpoint['status'],'UNKNOWN')
        self.assertEqual(m.RuntimeMember.objects.count(),0)
    def test_same_page_new_parents_and_business_required_owner(self):
        p=self.payload();p['team_ref']={'create':{'form_key':'new_team','name':'New team'}};p['business_refs']=[{'create':{'form_key':'new_business','name':'New business','owner':'Owner'}}]
        p['service']['model_ref']={'create':{'form_key':'new_model','name':'New model'}};p['endpoints'][0]['cluster_ref']={'create':{'form_key':'new_cluster','name':'New cluster','region':'A'}}
        snap=e.write(p);self.assertEqual(snap['service']['version'],1);self.assertEqual(m.Business.objects.get(name='New business').team.name,'New team')
        self.assertEqual(m.Endpoint.objects.get(service_id=snap['service']['id']).cluster.region,'A')
    def split(self):
        p=self.payload();p['service']['deployment_mode']='SPLIT_PD';p['endpoints']=[]
        p['groups']=[dict(name='group-'+str(i),endpoints=[self.endpoint('PREFILL'),self.endpoint('DECODE'),self.endpoint('ROUTER')]) for i in range(2)]
        return e.write(p)
    def test_multiple_pd_identity_and_unchanged_edit(self):
        snap=self.split();p=self.payload(snap);p['service']['name']='edited';result=e.write(p,snap['service']['id'])
        self.assertEqual({x['id'] for x in snap['groups']},{x['id'] for x in result['groups']});self.assertEqual(len(result['endpoints']),6)
    def history(self,snap):
        chosen=next((x for x in snap['endpoints'] if x['role']=='PREFILL'),snap['endpoints'][0])
        endpoint=m.Endpoint.objects.get(pk=chosen['id'])
        member=self.entity(m.RuntimeMember,'pod',endpoint=endpoint,cluster=endpoint.cluster,namespace='observed',pod_uid='actual-pod-uid',pod_name='actual-pod',node_uid='actual-node-uid',node_name='observed-node',observed_at=timezone.now())
        provider=m.ProviderInstance.objects.create(code='provider',name='provider',environment_code='DEV',base_url_ref='https://example.invalid')
        binding=m.EngineBinding.objects.create(code='binding',name='binding',environment_code='DEV',provider=provider,environment_id=uuid.uuid4(),engine_id='engine',engine_type='vllm',model_name='model',endpoint=endpoint,runtime_member=member,scope='POD')
        m.PollState.objects.create(binding=binding,error='retained')
        m.TelemetrySnapshot.objects.create(binding=binding,binding_version=binding.binding_version,provider_snapshot_id='historical-source',source_end=timezone.now(),payload={'preserved':'source'},content_hash='a'*64,json_bytes=22)
        return endpoint,member,binding
    def test_mode_transition_retains_every_observed_field_and_binding(self):
        snap=self.split();ep,member,binding=self.history(snap);before=[serialize(x) for x in (member,binding)];source_before=serialize(m.TelemetrySnapshot.objects.get());poll_before=serialize(m.PollState.objects.get())
        snap=e.snapshot(m.InferenceService.objects.get(pk=snap['service']['id']));p=self.payload(snap);p['service']['deployment_mode']='COMBINED';p['groups']=[];p['endpoints']=[self.endpoint()];p['retire_ids']['groups']=[g['id'] for g in snap['groups']]
        result=e.write(p,snap['service']['id']);ep.refresh_from_db();self.assertFalse(ep.enabled)
        member.refresh_from_db();binding.refresh_from_db();self.assertEqual(before,[serialize(x) for x in (member,binding)]);self.assertEqual(m.PollState.objects.get().error,'retained')
        self.assertEqual(source_before,serialize(m.TelemetrySnapshot.objects.get()));self.assertEqual(poll_before,serialize(m.PollState.objects.get()))
        self.assertEqual(sum(x['enabled'] for x in result['endpoints']),1)
        service=m.InferenceService.objects.get(pk=snap['service']['id']);save(m.InferenceService,'anonymous',{'expected_version':service.version,'name':'later'},service.pk)
    def test_cluster_change_retires_historical_identity_not_reparent_member(self):
        snap=e.write(self.payload());ep,member,binding=self.history(snap);c=self.entity(m.KubernetesCluster,'othercluster')
        snap=e.snapshot(ep.service);p=self.payload(snap);p['endpoints']=[self.endpoint(id=str(ep.pk),cluster_ref={'id':str(c.pk)})]
        result=e.write(p,ep.service_id);ep.refresh_from_db();member.refresh_from_db();self.assertFalse(ep.enabled);self.assertEqual(member.cluster_id,self.cluster.pk)
        active=[x for x in result['endpoints'] if x['enabled']];self.assertNotEqual(active[0]['id'],str(ep.pk));self.assertEqual(active[0]['cluster_id'],str(c.pk))
    def replace_history(self,move_group):
        snap=self.split();ep,member,binding=self.history(snap);before=[serialize(x) for x in (member,binding)];snap=e.snapshot(ep.service);p=self.payload(snap)
        original_group=str(ep.pd_group_id);target=next(x['id'] for x in snap['groups'] if x['id']!=original_group) if move_group else original_group
        p['groups']=[{'id':g['id'],'name':g['name'],'endpoints':[{'id':x['id'],'unchanged':True} for x in snap['endpoints'] if x['pd_group_id']==g['id'] and x['id']!=str(ep.pk)]} for g in snap['groups']]
        next(g for g in p['groups'] if g['id']==original_group)['endpoints'].append(self.endpoint('PREFILL'))
        next(g for g in p['groups'] if g['id']==target)['endpoints'].append(self.endpoint('PREFILL' if move_group else 'ROUTER',id=str(ep.pk)))
        result=e.write(p,ep.service_id);ep.refresh_from_db();member.refresh_from_db();binding.refresh_from_db()
        self.assertFalse(ep.enabled);self.assertEqual(before,[serialize(x) for x in (member,binding)])
        self.assertEqual(sum(x['enabled'] for x in result['endpoints']),7);self.assertEqual(member.endpoint_id,ep.pk)
    def test_role_change_replaces_historical_identity(self):self.replace_history(False)
    def test_group_change_replaces_historical_identity(self):self.replace_history(True)
    def test_rollback_including_new_parent_revision_and_audit(self):
        p=self.payload();p['team_ref']={'create':{'form_key':'fresh','name':'fresh'}};p['business_refs']=[];p['endpoints'].append(self.endpoint(namespace='INVALID'))
        before=(m.Team.objects.count(),m.Endpoint.objects.count(),m.AuditEvent.objects.count(),e.revision())
        with self.assertRaises(APIError):e.write(p)
        self.assertEqual(before,(m.Team.objects.count(),m.Endpoint.objects.count(),m.AuditEvent.objects.count(),e.revision()))
    def test_unknown_uid_fields_uuid_and_cross_environment(self):
        for key in ('pod_name','pod_uid','node_uid','observed_at','code'):
            p=self.payload();p['endpoints'][0][key]='forbidden';self.assertEqual(self.request('post','services',p).status_code,400)
        p=self.payload();p['endpoints'][0]['id']=str(uuid.uuid4());self.assertEqual(self.request('post','services',p).status_code,400)
        other=self.entity(m.Model,'other');other.environment_code='PRD';other.save()
        p=self.payload();p['service']['model_ref']={'id':str(other.pk)};p['expected_versions']['models:'+str(other.pk)]=other.version
        self.assertEqual(self.request('post','services',p).status_code,400);self.assertEqual(e.revision(),0)
    def test_business_extra_relations_key_grants_preserved(self):
        snap=e.write(self.payload());extra=self.entity(m.Business,'extra',team=self.team,owner='extra');service=m.InferenceService.objects.get(pk=snap['service']['id'])
        m.BusinessServiceBinding.objects.create(business=extra,service=service)
        key=self.entity(m.ApiKeyRef,'key',external_key_ref='external-001',masked_label='***001',team=self.team,business=extra);m.KeyModelGrant.objects.create(key=key,model=self.model)
        before=serialize(key);snap=e.snapshot(service);p=self.payload(snap);e.write(p,service.pk)
        self.assertTrue(m.BusinessServiceBinding.objects.get(business=extra,service=service).enabled);self.assertEqual(m.KeyModelGrant.objects.count(),1);key.refresh_from_db();self.assertEqual(before,serialize(key))
    def test_missing_disposition_and_missing_versions_rejected(self):
        snap=self.split();p=self.payload(snap);p['groups'].pop()
        with self.assertRaises(APIError) as exc:e.write(p,snap['service']['id'])
        self.assertEqual(exc.exception.code,'INCOMPLETE_DISPOSITION')
        p=self.payload(snap);p['expected_versions']={};self.assertEqual(self.request('put','services/'+snap['service']['id'],p).status_code,400)
    def test_stale_revision_old_crud_and_relationship_conflict(self):
        snap=e.write(self.payload());p=self.payload(snap);ep=m.Endpoint.objects.get(pk=snap['endpoints'][0]['id'])
        save(m.Endpoint,'anonymous',{'expected_version':ep.version,'name':'changed'},ep.pk)
        result=self.request('put','services/'+snap['service']['id'],p);self.assertEqual(result.status_code,409);self.assertEqual(result.json()['error']['code'],'VERSION_CONFLICT')
    def test_object_versions_conflict_even_if_revision_is_current(self):
        snap=e.write(self.payload());p=self.payload(snap);m.Endpoint.objects.filter(pk=snap['endpoints'][0]['id']).update(version=2)
        result=self.request('put','services/'+snap['service']['id'],p);self.assertEqual(result.status_code,409);self.assertTrue(result.json()['error']['details']['objects'])
    def test_legacy_configuration_kept_unchanged(self):
        service=self.entity(m.InferenceService,'legacy',model=self.model,deployment_mode='COMBINED');ep=self.entity(m.Endpoint,'legacyep',service=service,cluster=self.cluster,role='COMBINED')
        snap=e.snapshot(service);result=e.write(self.payload(snap),service.pk);self.assertEqual(result['endpoints'][0]['namespace'],'')
    def test_unchanged_without_existing_identity_is_structured_error(self):
        p=self.payload();p['endpoints']=[{'unchanged':True}]
        response=self.request('post','services',p);self.assertEqual(response.status_code,400)
        self.assertEqual(response.json()['error']['code'],'INVALID_UNCHANGED');self.assertEqual(m.InferenceService.objects.count(),0);self.assertEqual(e.revision(),0)
    def test_unrelated_child_version_rejected_and_referenced_versions_required(self):
        snap=e.write(self.payload());other=e.write(self.payload());snap=e.snapshot(m.InferenceService.objects.get(pk=snap['service']['id']))
        p=self.payload(snap);p['expected_versions']['services:'+other['service']['id']]=other['service']['version']
        response=self.request('put','services/'+snap['service']['id'],p);self.assertEqual(response.status_code,400);self.assertEqual(response.json()['error']['code'],'INVALID_VERSION')
        p=self.payload(snap);p['expected_versions'].pop('clusters:'+str(self.cluster.pk))
        self.assertEqual(self.request('put','services/'+snap['service']['id'],p).json()['error']['code'],'VERSION_REQUIRED')
    def test_disabled_business_retained_but_not_reactivated(self):
        snap=e.write(self.payload());service=m.InferenceService.objects.get(pk=snap['service']['id']);self.business.enabled=False;self.business.save()
        snap=e.snapshot(service);self.assertEqual(self.request('put','services/'+str(service.pk),self.payload(snap)).status_code,200)
        binding=m.BusinessServiceBinding.objects.get(service=service,business=self.business);binding.enabled=False;binding.save()
        service.refresh_from_db();snap=e.snapshot(service);p=self.payload(snap)
        response=self.request('put','services/'+str(service.pk),p);self.assertEqual(response.status_code,400);binding.refresh_from_db();self.assertFalse(binding.enabled)
    def test_export_complete_observed_history(self):
        snap=e.write(self.payload());ep,member,binding=self.history(snap);result=self.request('get','services/'+str(ep.service_id)+'/export')
        self.assertEqual(result.status_code,200);data=result.json();self.assertEqual(data['runtime_members'][0]['pod_uid'],'actual-pod-uid');self.assertEqual(data['engine_bindings'][0]['id'],str(binding.pk));self.assertIn('configured_nodes',data['endpoints'][0]);self.assertNotIn('credential_ref',result.content.decode())
        self.assertEqual(data['parents']['models'][0]['id'],str(self.model.pk));self.assertEqual(data['parents']['clusters'][0]['id'],str(self.cluster.pk))
        self.assertEqual(data['parents']['teams'][0]['id'],str(self.team.pk));self.assertEqual(data['parents']['providers'][0]['id'],str(binding.provider_id))
        self.assertIn('id',data['business_bindings'][0]);self.assertNotIn('base_url_ref',result.content.decode())
    def test_anonymous_csrf_and_options_pagination(self):
        client=Client(enforce_csrf_checks=True);r=self.request('post','services',self.payload(),client);self.assertEqual(r.status_code,403)
        session=client.get('/api/v1/session').json()['data'];r=client.post('/api/v1/service-entry/services',data=json.dumps(self.payload()),content_type='application/json',HTTP_X_CSRFTOKEN=session['csrf_token']);self.assertEqual(r.status_code,201)
        self.assertEqual(session['access_mode'],'direct');self.assertEqual(self.request('get','options?environment_code=DEV').status_code,200)
        self.assertEqual(self.request('get','services?limit=1').json()['data']['items'][0]['name'],'service')
    def test_two_real_sqlite_connections_one_winner(self):
        if connection.vendor!='sqlite':self.skipTest('SQLite-specific concurrency')
        snap=e.write(self.payload());p=self.payload(snap);gate=threading.Barrier(2)
        def change(name):
            close_old_connections();payload=copy.deepcopy(p);payload['service']['name']=name
            try:
                gate.wait(timeout=10)
                try:e.write(payload,snap['service']['id']);return 'OK'
                except APIError as exc:return exc.code
            finally:connection.close()
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(change,['first','second']))
        self.assertCountEqual(results,['OK','VERSION_CONFLICT']);self.assertEqual(m.InferenceService.objects.get().version,2)
