import csv,io,json,uuid
from datetime import timedelta
from django.test import TransactionTestCase,override_settings
from django.contrib.auth.models import User,Group
from django.utils import timezone
from control import models as m
from control.monitoring import COLUMNS,import_csv,switch_source,inspection_allowed
from control.projections import endpoint_view,screen
from control.telemetry import same_generation,metric,state,publish,InvalidProfile
from control.catalog import APIError,save

class MonitoringTests(TransactionTestCase):
    def setUp(self):
        self.user='anonymous'
    def csv(self,kind,rows):
        out=io.StringIO();w=csv.DictWriter(out,fieldnames=COLUMNS[kind]);w.writeheader();w.writerows(rows);return out.getvalue()
    def config(self,**fields):
        return dict(environment_code='prod',cluster_code='cluster',cluster_name='Cluster',model_code='model',model_name='Model',service_code='service',service_name='Service',deployment_mode='SPLIT_PD',pd_group_code='pd',pd_group_name='PD',endpoint_code='endpoint',endpoint_name='Endpoint',role='PREFILL',**fields)
    def create(self):
        data={'kind':'cluster-config','csv':self.csv('cluster-config',[self.config()])};p=import_csv(self.user,data);self.assertEqual(m.KubernetesCluster.objects.count(),0)
        result=import_csv(self.user,{**data,**{k:p[k] for k in ('expected_version','normalized_hash')}},True);return m.KubernetesCluster.objects.get(pk=result['cluster']['id'])
    def to_csv(self,c):
        switch_source(self.user,c.pk,{'expected_version':c.version,'source':'CSV'});c.refresh_from_db()
    def request_import(self,c,rows,kind='endpoint-metrics'):
        data={'kind':kind,'cluster_id':str(c.pk),'csv':self.csv(kind,rows)};p=import_csv(self.user,data);return data|{k:p[k] for k in ('expected_version','normalized_hash')}
    def test_config_dryrun_atomic_idempotent_and_scope(self):
        c=self.create();self.assertEqual(m.Endpoint.objects.count(),1)
        data={'kind':'cluster-config','csv':self.csv('cluster-config',[self.config()])};p=import_csv(self.user,data);self.assertFalse(import_csv(self.user,data|{k:p[k] for k in ('expected_version','normalized_hash')},True)['changed'])
        count=m.AuditEvent.objects.count();rev=m.Revision.objects.get().view
        bad=self.config();bad['endpoint_code']='new';bad['role']='INVALID'
        with self.assertRaises(APIError):import_csv(self.user,{'kind':'cluster-config','csv':self.csv('cluster-config',[self.config(),bad])},True)
        self.assertEqual(m.AuditEvent.objects.count(),count);self.assertEqual(m.Revision.objects.get().view,rev);self.assertEqual(m.Endpoint.objects.count(),1)
        bad=self.config();bad['environment_code']='other'
        with self.assertRaises(APIError):import_csv(self.user,{'kind':'cluster-config','csv':self.csv('cluster-config',[bad])})
    def test_csv_old_sample_retained_zero_missing_and_no_inspection_fallback(self):
        c=self.create();self.to_csv(c)
        p=self.request_import(c,[{'endpoint_code':'endpoint','sampled_at':'2020-01-01T00:00:00Z','running':'0','request_rate':'1.5'}]);import_csv(self.user,p,True)
        e=m.Endpoint.objects.get();v=endpoint_view(e);self.assertEqual(v['data_state'],'CSV_SNAPSHOT');self.assertEqual(v['status'],'UNKNOWN');self.assertEqual(v['metrics']['running']['value'],0);self.assertIsNone(v['metrics']['waiting']['value']);self.assertFalse(import_csv(self.user,p,True)['changed'])
        result=screen('overview',self.user);self.assertEqual(result['source_type'],'CSV');self.assertEqual(result['data_state'],'CSV_SNAPSHOT')
        c.refresh_from_db();switch_source(self.user,c.pk,{'expected_version':c.version,'source':'INSPECTION'});e.refresh_from_db();self.assertEqual(endpoint_view(e)['data_state'],'UNMAPPED')
        c.refresh_from_db();self.to_csv(c);e.refresh_from_db();self.assertEqual(endpoint_view(e)['data_state'],'CSV_SNAPSHOT')
        stale={'observation':{'source_window':{'end':'2020-01-01T00:00:00Z'},'freshness':'FRESH','origin':'VERIFIED'}};self.assertEqual(state(stale),'STALE')
    def test_preview_apply_conflict_and_bad_rows_keep_previous(self):
        c=self.create();self.to_csv(c);data=self.request_import(c,[{'endpoint_code':'endpoint','sampled_at':'2020-01-01T00:00:00Z','running':'2'}]);c.version+=1;c.save()
        with self.assertRaises(APIError) as err:import_csv(self.user,data,True)
        self.assertEqual(err.exception.code,'VERSION_CONFLICT');self.assertFalse(m.ClusterCsvSnapshot.objects.get(cluster=c).endpoint_payload)
        for extra in ({'running':'NaN'},{'running':'1.5'},{'kv_cache_hit_ratio':'2'},{'sampled_at':'2030-01-01T00:00:00Z'},{'endpoint_code':'other'}):
            with self.assertRaises(APIError):self.request_import(c,[{'endpoint_code':'endpoint','sampled_at':'2020-01-01T00:00:00Z','running':'1'}|extra])
    @override_settings(PROVIDER_URLS=['https://inspection.test'])
    def test_switch_invalidates_late_success_error_aba_and_catalog_bypass(self):
        c=self.create();e=m.Endpoint.objects.get();p=m.ProviderInstance.objects.create(code='p',name='P',environment_code='prod',base_url_ref='https://inspection.test')
        b=m.EngineBinding.objects.create(code='b',name='B',environment_code='prod',provider=p,environment_id=uuid.uuid4(),engine_id='x',engine_type='vllm',model_name='Model',endpoint=e,scope='ENDPOINT');old=m.EngineBinding.objects.select_related('provider').get(pk=b.pk)
        self.to_csv(c);current=m.EngineBinding.objects.select_related('provider').get(pk=b.pk);self.assertFalse(same_generation(current,old));self.assertFalse(inspection_allowed(current))
        with self.assertRaisesMessage(InvalidProfile,'BINDING_CHANGED'):publish(old,{})
        switch_source(self.user,c.pk,{'expected_version':c.version,'source':'INSPECTION'});current=m.EngineBinding.objects.select_related('provider').get(pk=b.pk);self.assertFalse(same_generation(current,old));self.assertTrue(inspection_allowed(current))
        with self.assertRaises(APIError):save(m.KubernetesCluster,self.user,{'expected_version':1,'monitoring_source':'CSV'},c.pk)
        captured=current;save(m.Endpoint,self.user,{'expected_version':e.version,'enabled':False,'confirm_disable':True},e.pk);current=m.EngineBinding.objects.select_related('provider').get(pk=b.pk);self.assertFalse(same_generation(current,captured));self.assertEqual(screen('overview',self.user)['items'],[])
    def test_hardware_family_retention_and_null_legacy_exclusion(self):
        c=self.create();self.to_csv(c)
        data=self.request_import(c,[{'resource_code':'host','resource_name':'Host','resource_type':'HOST','host_id':'host','sampled_at':'2020-01-01T00:00:00Z','cpu_busy_ratio':'.2','memory_available_bytes':'20','memory_total_bytes':'100'}],'hardware-metrics');import_csv(self.user,data,True)
        c.refresh_from_db();import_csv(self.user,self.request_import(c,[{'endpoint_code':'endpoint','sampled_at':'2021-01-01T00:00:00Z','running':'1'}]),True)
        r=screen('overview',self.user);self.assertEqual(len(r['hardware']),1);self.assertEqual(r['hardware'][0]['metrics']['memory_usage_ratio']['value'],.8);self.assertTrue(r['hardware'][0]['observation']['sampled_at'].startswith('2020'))
        for extra in ({'gpu_uuid':'unexpected'},{'memory_available_bytes':'200'},{'utilization_ratio':'.5'}):
            with self.assertRaises(APIError):self.request_import(c,[{'resource_code':'host','resource_name':'Host','resource_type':'HOST','host_id':'host','sampled_at':'2020-01-01T00:00:00Z','cpu_busy_ratio':'.2','memory_total_bytes':'100'}|extra],'hardware-metrics')
    def test_roles_templates_and_api(self):
        c=self.create()
        self.assertEqual(self.client.get('/api/v1/monitoring/clusters').status_code,200)
        for kind in COLUMNS:
            response=self.client.get('/api/v1/monitoring/templates/'+kind+'.csv');self.assertEqual(response.status_code,200);self.assertEqual(next(csv.reader(io.StringIO(response.content.decode('utf-8-sig')))),COLUMNS[kind])
        self.assertEqual(self.client.get('/api/v1/monitoring/clusters').status_code,200)
        self.assertEqual(self.client.post('/api/v1/monitoring/imports/validate',data='{}',content_type='application/json').status_code,400)
        self.assertEqual(self.client.patch('/api/v1/monitoring/clusters/'+str(c.pk)+'/source',data=json.dumps({'expected_version':c.version,'source':'CSV'}),content_type='application/json').status_code,200)

    @override_settings(PROVIDER_URLS=['https://inspection.test'])
    def test_worker_late_error_and_unassigned_hardware(self):
        from control.worker import round_poll
        from control.inspection import ReadError
        c=self.create();e=m.Endpoint.objects.get();provider=m.ProviderInstance.objects.create(code='provider',name='Provider',environment_code='prod',base_url_ref='https://inspection.test')
        binding=m.EngineBinding.objects.create(code='binding',name='Binding',environment_code='prod',provider=provider,environment_id=uuid.uuid4(),engine_id='engine',engine_type='vllm',model_name='Model',endpoint=e,scope='ENDPOINT')
        user=self.user
        class Reader:
            def __init__(self,p):pass
            def close(self):pass
            def fetch_profile(self,b):
                switch_source(user,c.pk,{'expected_version':c.version,'source':'CSV'})
                raise ReadError('IDENTITY_MISMATCH',True)
        round_poll(reader_factory=Reader)
        poll=m.PollState.objects.get(binding=binding);self.assertEqual(poll.error,'');self.assertFalse(poll.paused);self.assertEqual(poll.failures,0)
        m.HardwareBinding.objects.create(code='legacy',name='Legacy',environment_code='prod',provider=provider,environment_id=uuid.uuid4(),resource_type='HOST',asset_id=uuid.uuid4(),host_id='host')
        self.assertEqual(screen('overview',self.user)['hardware'],[])
