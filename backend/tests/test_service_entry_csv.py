import copy,json,csv,io,uuid
from django.test import TransactionTestCase
from control import models as m
from control import service_entry as e,service_entry_csv as c
from control.catalog import APIError

class ServiceEntryCsvTests(TransactionTestCase):
    def setUp(self):m.Revision.objects.create(pk=1)
    def row(self,**changes):
        raw=c.parse(c.template())[0];row=dict(zip(c.COLUMNS,raw));row.update(changes);return [row[x] for x in c.COLUMNS]
    def apply(self,source):
        result=c.validate(source);self.assertTrue(result['valid'],result)
        return c.apply({'csv':source,'sha256':result['sha256'],'expected_metadata_revision':result['metadata_revision']})
    def test_validate_no_writes_and_batch_shared_parent_persistence(self):
        source=c.encode([self.row(),self.row(service_alias='second',service_name='Second service',endpoint_alias='second_ep')])
        before=[model.objects.count() for model in (m.Team,m.Business,m.Model,m.KubernetesCluster,m.InferenceService,m.Endpoint,m.AuditEvent)]
        for _ in range(2):result=c.validate(source);self.assertTrue(result['valid'],result);self.assertEqual(len(result['rows']),2)
        self.assertEqual(before,[model.objects.count() for model in (m.Team,m.Business,m.Model,m.KubernetesCluster,m.InferenceService,m.Endpoint,m.AuditEvent)])
        saved=self.apply(source);self.assertEqual(saved['service_count'],2);self.assertEqual(m.Team.objects.count(),1);self.assertEqual(m.Business.objects.count(),1);self.assertEqual(m.Endpoint.objects.count(),2);self.assertEqual(e.revision(),1)
    def test_pd_multiple_groups_different_cluster_alias(self):
        rows=[]
        for group in ('a','b'):
            for role in ('PREFILL','DECODE','ROUTER'):
                rows.append(self.row(deployment_mode='SPLIT_PD',group_alias=group,group_name=group,endpoint_alias=group+role,role=role,cluster_alias='cluster_'+group,cluster_name='Cluster '+group))
        source=c.encode(rows);result=self.apply(source);self.assertEqual(len(result['items'][0]['groups']),2);self.assertEqual(m.KubernetesCluster.objects.count(),2)
    def test_parse_quotes_bom_unicode_and_cells_returned_on_invalid_semantics(self):
        source='\ufeff'+c.encode([self.row(service_name='模型,测试',configured_nodes='["one","two"]')]);self.assertTrue(c.validate(source)['valid'])
        source=c.encode([self.row(namespace='BAD')]);result=c.validate(source);self.assertFalse(result['valid']);self.assertEqual(result['columns'],c.COLUMNS);self.assertEqual(len(result['rows']),1);self.assertEqual(result['errors'][0]['row'],2)
    def test_alias_reserved_duplicate_cross_environment_and_inconsistent_fields(self):
        for value in ('auto','null','latest',str(uuid.uuid4())):
            result=c.validate(c.encode([self.row(model_alias=value)]));self.assertFalse(result['valid']);self.assertEqual(result['errors'][0]['column'],'model_alias')
        self.assertFalse(c.validate(c.encode([self.row(),self.row()]))['valid'])
        self.assertFalse(c.validate(c.encode([self.row(),self.row(endpoint_alias='another',service_name='different')]))['valid'])
        self.assertFalse(c.validate(c.encode([self.row(environment_code='other')]))['valid'])
    def test_existing_id_unique_name_and_ambiguous_name(self):
        model=m.Model.objects.create(code='m',name='model',environment_code='DEV');row=self.row(model_id=str(model.pk),model_name='model',model_alias='')
        self.assertTrue(c.validate(c.encode([row]))['valid']);row=self.row(model_id='',model_name='model',model_alias='');self.assertTrue(c.validate(c.encode([row]))['valid'])
        m.Model.objects.create(code='m2',name='model',environment_code='DEV');self.assertFalse(c.validate(c.encode([row]))['valid'])
        model.environment_code='PRD';model.save();row=self.row(model_id=str(model.pk),model_name='model',model_alias='');self.assertFalse(c.validate(c.encode([row]))['valid'])
    def test_hash_revision_conflicts_no_partial_batch(self):
        source=c.encode([self.row()]);r=c.validate(source)
        with self.assertRaises(APIError):c.apply({'csv':source+'\n','sha256':r['sha256'],'expected_metadata_revision':r['metadata_revision']})
        m.Revision.objects.filter(pk=1).update(metadata=1)
        with self.assertRaises(APIError):c.apply({'csv':source,'sha256':r['sha256'],'expected_metadata_revision':r['metadata_revision']})
        self.assertEqual(m.InferenceService.objects.count(),0)
    def test_last_service_unique_constraint_rolls_back_whole_batch(self):
        # Critical watch_order is globally unique; each new business requests the same slot.
        source=c.encode([self.row(business_critical='true',business_watch_order='1'),self.row(service_alias='second',service_name='Second',business_alias='other_business',business_name='Other business',business_critical='true',business_watch_order='1',endpoint_alias='second_ep')])
        from django.core.exceptions import ValidationError
        r=c.validate(source)
        with self.assertRaises((APIError,ValidationError)):c.apply({'csv':source,'sha256':r['sha256'],'expected_metadata_revision':r['metadata_revision']})
        self.assertEqual(m.Team.objects.count(),0);self.assertEqual(m.InferenceService.objects.count(),0);self.assertEqual(m.AuditEvent.objects.count(),0);self.assertEqual(e.revision(),0)
    def test_failure_after_last_service_persistence_rolls_back_every_write(self):
        from unittest.mock import patch
        source=c.encode([self.row(),self.row(service_alias='second',service_name='Second',endpoint_alias='second_ep')]);r=c.validate(source);self.assertTrue(r['valid'],r)
        original=e.audit;calls=[]
        def fail_second(*args,**kwargs):
            original(*args,**kwargs);calls.append(m.InferenceService.objects.count())
            if len(calls)==2:raise APIError('INJECTED_FAILURE','final service audit rejected')
        with patch('control.service_entry.audit',side_effect=fail_second):
            with self.assertRaises(APIError):c.apply({'csv':source,'sha256':r['sha256'],'expected_metadata_revision':r['metadata_revision']})
        self.assertEqual(calls,[1,2]);self.assertEqual(e.revision(),0)
        for model in (m.Team,m.Business,m.Model,m.KubernetesCluster,m.InferenceService,m.Endpoint,m.BusinessServiceBinding,m.AuditEvent):self.assertEqual(model.objects.count(),0,model.__name__)
    def test_configuration_copy_round_trip_with_pd_nodes(self):
        rows=[self.row(deployment_mode='SPLIT_PD',group_alias='pd',group_name='PD group',endpoint_alias=role,role=role,configured_nodes='["node-a","node-b"]') for role in ('PREFILL','DECODE','ROUTER')]
        saved=self.apply(c.encode(rows));service=m.InferenceService.objects.get(pk=saved['items'][0]['service']['id']);source=c.export_csv(service)
        copied=self.apply(source)['items'][0];self.assertNotEqual(copied['service']['id'],str(service.pk));self.assertEqual(len(copied['groups']),1)
        self.assertEqual({x['role'] for x in copied['endpoints']},{'PREFILL','DECODE','ROUTER'});self.assertTrue(all(x['configured_nodes']==['node-a','node-b'] for x in copied['endpoints']))
    def test_configuration_copy_rejects_non_single_business_without_losing_relations(self):
        saved=self.apply(c.template())['items'][0];service=m.InferenceService.objects.get(pk=saved['service']['id']);team=m.Team.objects.first()
        extra=m.Business.objects.create(code='extra',name='extra',environment_code='DEV',team=team,owner='Ops');m.BusinessServiceBinding.objects.create(business=extra,service=service)
        response=self.client.get('/api/v1/service-entry/services/'+str(service.pk)+'/export?format=csv');self.assertEqual(response.status_code,400);self.assertEqual(response.json()['error']['code'],'EXPORT_REQUIRES_SINGLE_BUSINESS')
        complete=self.client.get('/api/v1/service-entry/services/'+str(service.pk)+'/export').json();self.assertEqual(len(complete['business_bindings']),2)
        m.BusinessServiceBinding.objects.filter(service=service).update(enabled=False)
        self.assertEqual(self.client.get('/api/v1/service-entry/services/'+str(service.pk)+'/export?format=csv').status_code,400)
    def test_unknown_headers_raw_sampling_and_limits(self):
        source=c.template().replace('configured_nodes','node_uid',1);self.assertFalse(c.validate(source)['valid'])
        self.assertFalse(c.validate('x'* (2*1024*1024+1))['valid'])
        self.assertFalse(c.validate(c.encode([self.row()]*1001))['valid'])
    def test_service_group_endpoint_node_and_parent_limits(self):
        sources=[
            c.encode([self.row(service_alias='service_'+str(i),service_name='Service '+str(i),endpoint_alias='ep_'+str(i)) for i in range(101)]),
            c.encode([self.row(endpoint_alias='ep_'+str(i)) for i in range(101)]),
            c.encode([self.row(deployment_mode='SPLIT_PD',group_alias='group_'+str(i),group_name='Group '+str(i),endpoint_alias=role+str(i),role=role) for i in range(21) for role in ('PREFILL','DECODE')]),
            c.encode([self.row(configured_nodes=json.dumps(['node'+str(i) for i in range(33)]))]),
            c.encode([self.row(service_alias='service_'+str(i),service_name='Service '+str(i),endpoint_alias='ep_'+str(i),team_alias='team_'+str(i),team_name='Team '+str(i),business_alias='business_'+str(i),business_name='Business '+str(i),model_alias='model_'+str(i),model_name='Model '+str(i),cluster_alias='cluster_'+str(i),cluster_name='Cluster '+str(i)) for i in range(76)]),
        ]
        for source in sources:
            result=c.validate(source);self.assertFalse(result['valid']);self.assertTrue(any(x['code'] in {'LIMIT_EXCEEDED','INVALID_NODES'} for x in result['errors']),result)
        self.assertEqual(m.InferenceService.objects.count(),0);self.assertEqual(e.revision(),0)
    def test_invalid_utf8_header_duplicates_and_csv_structure(self):
        for source in (c.template().replace('model_alias','model_name',1),c.template()+'"unterminated',c.template()+'\x00',c.template()+'\ud800'):
            self.assertFalse(c.validate(source)['valid'])
    def test_http_template_apply_export(self):
        template=self.client.get('/api/v1/service-entry/templates/services.csv');self.assertEqual(template.status_code,200)
        source=template.content.decode('utf-8');r=self.client.post('/api/v1/service-entry/imports/validate',json.dumps({'csv':source}),content_type='application/json');self.assertEqual(r.status_code,200)
        data=r.json()['data'];self.assertTrue(data['valid'],data)
        response=self.client.post('/api/v1/service-entry/imports/apply',json.dumps({'csv':source,'sha256':data['sha256'],'expected_metadata_revision':data['metadata_revision']}),content_type='application/json');self.assertEqual(response.status_code,201,response.content)
        pk=response.json()['data']['items'][0]['service']['id'];export=self.client.get('/api/v1/service-entry/services/'+pk+'/export?format=csv');self.assertEqual(export.status_code,200);self.assertEqual(export['X-Export-Scope'],'configuration-copy-not-observations');self.assertNotIn('pod_uid',export.content.decode())
