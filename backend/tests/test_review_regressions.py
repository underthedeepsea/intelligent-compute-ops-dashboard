"""Candidate 2 regressions for review R1–R5/R7/R8. Synthetic data only."""
import copy
from datetime import timedelta
from unittest.mock import patch
import httpx
from django.test import TestCase,TransactionTestCase,override_settings
from django.contrib.auth.models import User
from django.utils import timezone
from control import models as m
from control.catalog import save
from control.telemetry import normalize,publish,InvalidProfile
from control.inspection import InspectionReader,ReadError
from control.worker import round_poll
from control.projections import endpoint_view,screen
from control.topology import topology
from .test_telemetry import TelemetryTests,fixture

@override_settings(PROVIDER_URLS=['https://inspection.test','https://other.test'])
class ReviewRegressionTests(TestCase):
    def setUp(self):
        TelemetryTests.setUp(self)
        self.user='anonymous'
    def captured(self):return m.EngineBinding.objects.select_related('provider','endpoint').get(pk=self.binding.pk)
    def profile(self,binding=None):
        raw=fixture(binding or self.binding)
        raw['provenance']={'source':'trusted','sample_id':'sample-1','ingested_at':'2026-09-26T00:00:00Z'}
        return raw
    def edit_provider(self,fields):
        provider=m.ProviderInstance.objects.get(pk=self.binding.provider_id)
        return save(m.ProviderInstance,self.user,{'expected_version':provider.version,**fields},provider.pk)
    def test_r1_provider_mutations_invalidate_old_cache_and_inflight(self):
        for change in [{'origin_verified':False},{'source_allowlist':[]},{'plugin_versions':[]},{'base_url_ref':'https://other.test'},{'enabled':False,'confirm_disable':True}]:
            with self.subTest(change=change):
                self.edit_provider({'origin_verified':True,'source_allowlist':['trusted'],'plugin_versions':['1.0.0'],'base_url_ref':'https://inspection.test','enabled':True})
                old=self.captured();payload=normalize(self.profile(old),old);publish(old,payload)
                previous=old.binding_version
                self.edit_provider(change)
                current=self.captured();self.assertEqual(current.binding_version,previous+1)
                view=endpoint_view(current.endpoint)
                self.assertNotEqual(view['data_state'],'FRESH');self.assertEqual(view['status'],'UNKNOWN');self.assertIsNone(view['observation'])
                with self.assertRaisesMessage(InvalidProfile,'BINDING_CHANGED'):publish(old,payload)
    def test_r2_obsolete_success_and_failures_cannot_touch_new_generation(self):
        for target in ('binding','provider'):
            for outcome in ('success','transient','permanent'):
                with self.subTest(target=target,outcome=outcome):
                    current=self.captured();m.PollState.objects.update_or_create(binding=current,defaults={'paused':False,'next_due':None,'error':'','failures':0,'last_success_at':None})
                    outer=self
                    class Reader:
                        def __init__(self,p):pass
                        def fetch_profile(self,b):
                            raw=outer.profile(b)
                            if target=='binding':save(m.EngineBinding,outer.user,{'expected_version':b.version,'engine_id':b.engine_id+'x'},b.pk)
                            else:outer.edit_provider({'name':'provider-'+outcome})
                            if outcome=='permanent':raise ReadError('HTTP_401',True)
                            if outcome=='transient':raise ReadError('TRANSPORT_ERROR')
                            return normalize(raw,b)
                        def close(self):pass
                    round_poll('r2',Reader)
                    p=m.PollState.objects.get(binding=current)
                    self.assertFalse(p.paused);self.assertEqual(p.error,'');self.assertEqual(p.failures,0);self.assertIsNone(p.next_due);self.assertIsNone(p.last_success_at);self.assertIsNone(p.last_attempt_at)
    def test_r3_malformed_consumed_types_are_contract_errors(self):
        mutations=[('engine',None),('engine',[]),('engine','bad'),('status',[]),('status',{}),('evaluation_status',[]),('window',[]),('window',{'start':{},'end':[]}),('plugin',[]),('quality',None),('provenance',[]),('freshness',None),('snapshot_id',{})]
        for key,value in mutations:
            with self.subTest(key=key,value=value):
                raw=self.profile();raw[key]=value
                with self.assertRaises(InvalidProfile):normalize(raw,self.binding)
        for path,value in [(('freshness','state'),[]),(('freshness','max_age_seconds'),10**400),(('quality','pending_confirmation'),'false'),(('plugin','version'),[]),(('provenance','source'),{}),(('current_metrics','traffic','qps'),10**400)]:
            raw=self.profile();d=raw
            for k in path[:-1]:d=d[k]
            d[path[-1]]=value
            with self.assertRaises(InvalidProfile):normalize(raw,self.binding)
    def test_r3_poison_source_does_not_stop_later_binding(self):
        bad=self.binding
        good=m.EngineBinding.objects.create(code='good',name='good',environment_code='prod',provider=bad.provider,endpoint=bad.endpoint,environment_id=bad.environment_id,engine_id='good-engine',engine_type='vllm',model_name='model',scope='ENDPOINT')
        # Force deterministic poison first, good second in the fair due ordering.
        m.PollState.objects.create(binding=bad,last_attempt_at=timezone.now()-timedelta(seconds=2))
        m.PollState.objects.create(binding=good,last_attempt_at=timezone.now()-timedelta(seconds=1))
        outer=self
        class Reader:
            def __init__(self,p):pass
            def fetch_profile(self,b):
                raw=outer.profile(b)
                if b.pk==bad.pk:raw['engine']=None
                return normalize(raw,b)
            def close(self):pass
        result=round_poll('r3',Reader)
        self.assertEqual(result['polled'],2);self.assertEqual(m.PollState.objects.get(binding=bad).error,'CONTRACT_INCOMPATIBLE');self.assertIsNotNone(m.PollState.objects.get(binding=good).last_success_at)
        self.assertGreater(m.PollState.objects.get(binding=bad).next_due,timezone.now())
    def test_r3_invalid_provider_configuration_is_bounded(self):
        m.ProviderInstance.objects.filter(pk=self.binding.provider_id).update(plugin_versions={})
        result=round_poll('r3-config')
        self.assertEqual(result['polled'],1);poll=m.PollState.objects.get();self.assertTrue(poll.paused);self.assertEqual(poll.error,'PROVIDER_CONFIG_INVALID')
    def test_r4_same_sample_mutable_read_state_and_immutable_measurements(self):
        binding=self.captured();raw=self.profile(binding);now=timezone.now();payload=normalize(raw,binding,now)
        publish(binding,payload);rev=m.Revision.objects.get().telemetry
        unchanged=normalize(raw,binding,now+timedelta(seconds=1));self.assertFalse(publish(binding,unchanged));self.assertEqual(m.Revision.objects.get().telemetry,rev)
        raw['freshness']['state']='STALE';raw['status']='UNKNOWN'
        stale=normalize(raw,binding,now+timedelta(seconds=301));self.assertTrue(publish(binding,stale));self.assertEqual(m.Revision.objects.get().telemetry,rev+1);self.assertEqual(m.TelemetrySnapshot.objects.count(),1)
        self.assertEqual(endpoint_view(binding.endpoint)['data_state'],'STALE')
        raw['evaluation_status']='WARNING';revised=normalize(raw,binding,now+timedelta(seconds=302));self.assertTrue(publish(binding,revised));self.assertEqual(m.TelemetrySnapshot.objects.count(),1)
        for change in ('metric','window'):
            altered=copy.deepcopy(raw)
            if change=='metric':altered['current_metrics']['traffic']['qps']=999
            else:altered['window']['start']=(now-timedelta(seconds=120)).isoformat()
            with self.assertRaisesMessage(InvalidProfile,'SNAPSHOT_MUTATED'):publish(binding,normalize(altered,binding,now+timedelta(seconds=303)))
    def test_r4_repeated_success_only_advances_transport_timestamps(self):
        raw=self.profile();outer=self
        class Reader:
            def __init__(self,p):pass
            def fetch_profile(self,b):return normalize(raw,b)
            def close(self):pass
        round_poll('r4',Reader);rev=m.Revision.objects.get().telemetry
        m.PollState.objects.filter(binding=self.binding).update(next_due=None)
        round_poll('r4',Reader);self.assertEqual(m.Revision.objects.get().telemetry,rev);self.assertEqual(m.TelemetrySnapshot.objects.count(),1)
    def test_r5_members_actual_nodes_without_shared_siblings(self):
        e=self.binding.endpoint;s=e.service;cluster=e.cluster
        own=m.RuntimeMember.objects.create(code='own-pod',name='Own Pod',environment_code='prod',endpoint=e,cluster=cluster,namespace='n',pod_uid='pod1',node_uid='node1',node_name='Node 1',observed_at=timezone.now())
        other_model=m.Model.objects.create(code='other-model',name='Other',environment_code='prod')
        sibling=m.InferenceService.objects.create(code='sibling',name='Sibling',environment_code='prod',model=other_model,deployment_mode='COMBINED')
        other=m.Endpoint.objects.create(code='other-endpoint',name='Other endpoint',environment_code='prod',service=sibling,cluster=cluster,role='COMBINED')
        other_pod=m.RuntimeMember.objects.create(code='other-pod',name='Other pod',environment_code='prod',endpoint=other,cluster=cluster,namespace='n',pod_uid='pod2',node_uid='node2',node_name='Node 2',observed_at=timezone.now())
        for focus,pk in [('model',s.model_id),('service',s.pk)]:
            data=topology(self.user,focus,str(pk));ids={n['id'] for n in data['nodes']}
            self.assertIn('pod:'+str(own.pk),ids);self.assertIn(f'node:{cluster.pk}:node1',ids)
            self.assertNotIn('pod:'+str(other_pod.pk),ids);self.assertNotIn(f'node:{cluster.pk}:node2',ids);self.assertNotIn('service:'+str(sibling.pk),ids)
            self.assertIn({'source':'pod:'+str(own.pk),'target':f'node:{cluster.pk}:node1','type':'scheduled_on'},data['edges'])
            self.assertFalse(data['truncated'])
    def test_r7_r8_raw_endpoint_dependency_contract_no_composite_status(self):
        team=m.Team.objects.create(code='team',name='Team',environment_code='prod')
        business=m.Business.objects.create(code='business',name='Business',environment_code='prod',team=team,owner='Ops',critical=True,watch_order=1)
        m.BusinessServiceBinding.objects.create(business=business,service=self.binding.endpoint.service)
        raw=self.profile();raw['status']='WARNING';raw['freshness']['max_age_seconds']=30
        publish(self.binding,normalize(raw,self.binding));m.PollState.objects.create(binding=self.binding,error='TRANSPORT_ERROR')
        service=screen('services',self.user)['items'][0];app=screen('critical-apps',self.user)['items'][0]
        for field in ('status','active_anomaly','potential_businesses'):self.assertNotIn(field,service)
        for field in ('potential_impact','healthy_alternative_endpoints'):self.assertNotIn(field,app)
        self.assertEqual(service['configured_businesses'],[{'id':str(business.pk),'name':business.name}])
        obs=app['dependency_services'][0]['endpoints'][0]['observation']
        self.assertEqual(obs['max_age_seconds'],30);self.assertEqual(obs['transport_status'],'TRANSPORT_ERROR');self.assertEqual(obs['upstream_status'],'WARNING');self.assertIn('source_window',obs)


@override_settings(PROVIDER_URLS=['https://inspection.test'])
class GenerationConcurrencyTests(TransactionTestCase):
    def test_postgres_provider_edit_fences_inflight_publication_and_completion(self):
        from django.db import connection,close_old_connections
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event
        if connection.vendor!='postgresql':self.skipTest('PostgreSQL concurrent generation fence')
        TelemetryTests.setUp(self)
        user='anonymous'
        started=Event();resume=Event()
        class Reader:
            def __init__(self,p):pass
            def fetch_profile(self,b):
                payload=normalize(fixture(b),b)
                started.set()
                if not resume.wait(5):raise RuntimeError('test interleave timeout')
                return payload
            def close(self):pass
        def poll():
            close_old_connections()
            try:return round_poll('concurrent-generation',Reader)
            finally:connection.close()
        with ThreadPoolExecutor(max_workers=1) as pool:
            result=pool.submit(poll)
            try:
                self.assertTrue(started.wait(5))
                provider=m.ProviderInstance.objects.get(pk=self.binding.provider_id)
                save(m.ProviderInstance,user,{'expected_version':provider.version,'origin_verified':False},provider.pk)
            finally:resume.set()
            result.result(timeout=8)
        pollstate=m.PollState.objects.get(binding=self.binding)
        self.assertFalse(pollstate.paused);self.assertEqual(pollstate.error,'');self.assertIsNone(pollstate.next_due);self.assertIsNone(pollstate.last_success_at)
        self.assertEqual(m.TelemetrySnapshot.objects.count(),0)
        self.binding.refresh_from_db();self.assertEqual(self.binding.binding_version,2)
