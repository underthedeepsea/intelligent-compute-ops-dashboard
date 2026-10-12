"""Run in the target repo: python backend/manage.py test production_scene --verbosity 2.
These integration tests require the original control app and Django dependencies.
"""
import copy,json,os
from unittest import skipUnless
from .data_files import data_root
from pathlib import Path
from unittest.mock import patch
from django.test import TestCase,Client,override_settings
from control import models as m
from control.catalog import APIError
from .models import DeploymentScope,BusinessDeploymentBinding,CatalogCorrection,CatalogImport,DeploymentIdentity,BusinessPDGroupBinding,PodRegistration,EndpointPodBinding
from .importer import import_catalog,current_revision,verify_import
from .catalog_core import compile_catalog
FIXTURE=data_root()/'production-catalog.json'
if os.environ.get('PRODUCTION_SCENE_TEST_DATA_REQUIRED')=='1' and not FIXTURE.is_file():
 raise RuntimeError('Required local demo fixture missing; install_demo_bundle first')
PACKET=json.loads(FIXTURE.read_text()) if FIXTURE.is_file() else None

@skipUnless(PACKET is not None,'Optional local demo bundle not installed')
class CatalogIntegrationTests(TestCase):
 def apply_catalog(self):return import_catalog(PACKET,apply=True,expected_revision=current_revision())
 def test_dry_run_rolls_back_everything(self):
  result=import_catalog(PACKET)
  self.assertFalse(result['applied']);self.assertEqual(m.Team.objects.count(),0);self.assertEqual(CatalogImport.objects.count(),0)
 def test_exact_gateway_counts_and_pod_bindings(self):
  self.apply_catalog()
  for model,count in [(m.Team,6),(m.Business,6),(m.Model,1),(m.KubernetesCluster,1),(m.InferenceService,1),(m.PDGroup,3),(m.Endpoint,8),(PodRegistration,22),(EndpointPodBinding,24),(BusinessPDGroupBinding,9),(DeploymentScope,4)]:self.assertEqual(model.objects.count(),count,model.__name__)
 def test_retry_is_idempotent(self):
  self.apply_catalog();rev=current_revision();r=self.apply_catalog()
  self.assertTrue(r['already_imported']);self.assertEqual(current_revision(),rev);self.assertEqual(m.Endpoint.objects.count(),8)
 def test_revision_required_and_checked(self):
  for version in [None,True,-1]:
   with self.assertRaises(APIError):import_catalog(PACKET,apply=True,expected_revision=version)
  self.assertEqual(m.Team.objects.count(),0)
 def test_returned_revision_matches_database(self):
  r=self.apply_catalog();self.assertEqual(r['metadata_revision'],current_revision());self.assertGreater(current_revision(),0)
 def test_preserves_existing_business_order(self):
  team=m.Team.objects.create(code='existing-team',name='已有团队',environment_code='PRD')
  business=m.Business.objects.create(code='existing-b',name='已有业务',team=team,owner='已有负责人',critical=True,watch_order=90,environment_code='PRD')
  self.apply_catalog();business.refresh_from_db();self.assertEqual(business.watch_order,90)
  self.assertEqual(m.Business.objects.filter(watch_order__gt=90).count(),6)
 def test_no_operational_telemetry_identity_or_keys(self):
  self.apply_catalog()
  for model in [m.RuntimeMember,m.ApiKeyRef,m.ProviderInstance,m.EngineBinding,m.HardwareBinding,m.TelemetrySnapshot,m.HardwareObservation]:self.assertEqual(model.objects.count(),0,model.__name__)
 def test_same_name_unknown_identity_rejected(self):
  m.Team.objects.create(code='preexisting',name=PACKET['rows'][0]['team'],environment_code='PRD')
  with self.assertRaises(APIError):self.apply_catalog()
  self.assertEqual(CatalogImport.objects.count(),0);self.assertEqual(m.Team.objects.count(),1)
 def test_same_name_group_without_scope_is_rejected(self):
  catalog=compile_catalog(PACKET)['catalog']
  model=m.Model.objects.create(**{k:catalog['models'][0][k] for k in ['id','code','name','environment_code','enabled','origin']})
  service=m.InferenceService.objects.create(model=model,**{k:catalog['services'][0][k] for k in ['id','code','name','environment_code','enabled','origin','deployment_mode']})
  group=next(g for g in catalog['pd-groups'] if g['name']=='pd-server-dsv4flash-fallback')
  m.PDGroup.objects.create(code='existing-unscoped-group',name=group['name'],environment_code=group['environment_code'],service=service)
  with self.assertRaises(APIError) as error:self.apply_catalog()
  self.assertEqual(error.exception.code,'EXISTING_NATURAL_IDENTITY')
  self.assertEqual(CatalogImport.objects.count(),0);self.assertEqual(m.PDGroup.objects.count(),1);self.assertEqual(DeploymentIdentity.objects.count(),0)
 def test_base_edit_prevents_immutable_retry(self):
  self.apply_catalog();m.Team.objects.filter(name=PACKET['rows'][0]['team']).update(name='已手动修改')
  with self.assertRaises(APIError):self.apply_catalog()
 def test_extra_relation_edit_prevents_replay(self):
  self.apply_catalog();link=EndpointPodBinding.objects.first();link.delete()
  with self.assertRaises(APIError):verify_import(CatalogImport.objects.get())
 def test_source_is_immutable(self):
  self.apply_catalog();p=copy.deepcopy(PACKET);p['source']['comment']='changed'
  with self.assertRaises(APIError):import_catalog(p,apply=True,expected_revision=current_revision())
 def test_transaction_failure_leaves_no_partial_catalog(self):
  with patch('production_scene.importer.audit',side_effect=RuntimeError('injected audit failure')):
   with self.assertRaises(RuntimeError):self.apply_catalog()
  self.assertEqual(m.Team.objects.count(),0);self.assertEqual(PodRegistration.objects.count(),0);self.assertEqual(current_revision(),0)
 def test_csrf_and_explicit_confirmation(self):
  c=Client(enforce_csrf_checks=True)
  self.assertEqual(c.post('/api/v1/production-scene/imports/apply',data=json.dumps({'packet':PACKET,'expected_revision':0,'confirm':True}),content_type='application/json').status_code,403)
  response=c.get('/api/v1/production-scene/source');self.assertEqual(response.status_code,200)
  token=response.json()['data']['csrf_token']
  response=c.post('/api/v1/production-scene/imports/apply',data=json.dumps({'packet':PACKET,'expected_revision':0}),content_type='application/json',HTTP_X_CSRFTOKEN=token)
  self.assertEqual(response.status_code,400);self.assertEqual(m.Team.objects.count(),0)
  response=c.post('/api/v1/production-scene/imports/apply',data=json.dumps({'packet':PACKET,'expected_revision':0,'confirm':True}),content_type='application/json',HTTP_X_CSRFTOKEN=token)
  self.assertEqual(response.status_code,200);self.assertEqual(m.Team.objects.count(),6)
 @override_settings(PRODUCTION_SCENE_REPLAY_ENABLED=False)
 def test_replay_disabled_by_default(self):
  self.assertEqual(self.client.get('/api/v1/production-scene/replay/dataset').status_code,404)
 @override_settings(PRODUCTION_SCENE_REPLAY_ENABLED=True)
 def test_replay_requires_import(self):
  self.assertEqual(self.client.get('/api/v1/production-scene/replay/dataset').status_code,409)
 @override_settings(PRODUCTION_SCENE_REPLAY_ENABLED=True)
 def test_replay_read_isolated_and_revision_unchanged(self):
  self.apply_catalog();revision=current_revision()
  response=self.client.get('/api/v1/production-scene/replay/frame?step=390');self.assertEqual(response.status_code,200)
  data=response.json();self.assertEqual(data['projections']['overview']['data']['source_type'],'SCENARIO')
  self.assertEqual(current_revision(),revision);self.assertEqual(m.TelemetrySnapshot.objects.count(),0)
 @override_settings(PRODUCTION_SCENE_REPLAY_ENABLED=True)
 def test_replay_detects_catalog_drift(self):
  self.apply_catalog();BusinessPDGroupBinding.objects.all().first().delete()
  self.assertEqual(self.client.get('/api/v1/production-scene/replay/dataset').status_code,409)
 def test_actual_catalog_has_group_specific_scopes(self):
  self.apply_catalog();c=self.client.get('/api/v1/production-scene/catalog').json()['data']['catalog']
  self.assertEqual(len(c['pods']),22);self.assertEqual(len(c['business-pd-bindings']),9)
  live=self.client.get('/api/v1/production-scene/live/critical-apps').json()['data']
  counts={b['name']:sum(len(s['endpoints']) for s in b['dependency_services']) for b in live['items']}
  self.assertEqual(counts['sample-business-03'],2);self.assertEqual(counts['sample-business-01'],4)

@skipUnless(PACKET is not None,'Optional local demo bundle not installed')
class RecoveryTopologyIntegrationTests(TestCase):
 """Additive v2 upgrade invariants; these require real Django test databases."""
 def apply_catalog(self):return import_catalog(PACKET,apply=True,expected_revision=current_revision())
 def test_first_import_registers_one_explicit_plan(self):
  from .models import EscapePlan
  self.apply_catalog();self.assertEqual(EscapePlan.objects.count(),1)
  self.assertFalse(EscapePlan.objects.get().payload['automatic_switch'])
 def test_plan_retry_does_not_bump_or_duplicate(self):
  from .models import EscapePlan
  self.apply_catalog();rev=current_revision();result=self.apply_catalog()
  self.assertEqual(EscapePlan.objects.count(),1);self.assertEqual(rev,current_revision());self.assertFalse(result['escape_plan_added'])
 def test_old_bundle_preview_does_not_write_plan(self):
  from .models import EscapePlan
  self.apply_catalog();EscapePlan.objects.all().delete();rev=current_revision();r=import_catalog(PACKET)
  self.assertTrue(r['escape_plan_pending']);self.assertFalse(r['escape_plan_added']);self.assertEqual(EscapePlan.objects.count(),0);self.assertEqual(rev,current_revision())
 def test_old_bundle_apply_adds_plan_only(self):
  from .models import EscapePlan
  self.apply_catalog();EscapePlan.objects.all().delete();rev=current_revision();r=self.apply_catalog()
  self.assertTrue(r['escape_plan_added']);self.assertGreater(current_revision(),rev)
  self.assertEqual((m.Business.objects.count(),m.PDGroup.objects.count(),m.Endpoint.objects.count(),PodRegistration.objects.count()),(6,3,8,22))
 def test_policy_conflict_preserves_existing_bytes(self):
  from .models import EscapePlan
  self.apply_catalog();row=EscapePlan.objects.get();old=copy.deepcopy(row.payload);old['notes']='edited plan';row.payload=old;row.save()
  with self.assertRaises(APIError):self.apply_catalog()
  row.refresh_from_db();self.assertEqual(row.payload,old)
 def test_get_catalog_never_creates_missing_policy(self):
  from .models import EscapePlan
  self.apply_catalog();EscapePlan.objects.all().delete();r=self.client.get('/api/v1/production-scene/catalog')
  self.assertEqual(r.status_code,200);self.assertEqual(r.json()['data']['catalog']['escape-plans'],[]);self.assertEqual(EscapePlan.objects.count(),0)
 @override_settings(PRODUCTION_SCENE_REPLAY_ENABLED=True)
 def test_both_replay_routes_require_matching_plan(self):
  from .models import EscapePlan
  self.apply_catalog();EscapePlan.objects.all().delete()
  for path in ('dataset','frame?step=390'):
   r=self.client.get('/api/v1/production-scene/replay/'+path);self.assertEqual(r.status_code,409);self.assertEqual(r.json()['error']['code'],'ESCAPE_PLAN_REQUIRED')
 def test_gateway_six_direct_service_dependencies(self):
  self.apply_catalog();service=m.InferenceService.objects.get()
  r=self.client.get('/api/v1/production-scene/topology',{'focus_type':'service','focus_id':str(service.pk)})
  self.assertEqual(r.status_code,200);graph=r.json()['data']
  self.assertEqual(len([e for e in graph['edges'] if e['type']=='depends_on']),6)
  self.assertEqual(len([n for n in graph['nodes'] if n['type']=='service']),1)
 def test_business_focus_restricts_scoped_group(self):
  self.apply_catalog();b=m.Business.objects.get(name='sample-business-03')
  r=self.client.get('/api/v1/production-scene/topology',{'focus_type':'business','focus_id':str(b.pk)})
  gs=[n for n in r.json()['data']['nodes'] if n['type']=='pd_group']
  self.assertEqual(len(gs),1);self.assertEqual(gs[0]['namespace'],'pd-server-dsv5flash-fallback')
 def test_three_protected_and_three_receiving_businesses(self):
  self.apply_catalog();cat=self.client.get('/api/v1/production-scene/catalog').json()['data']['catalog']
  self.assertEqual(sum(b['recovery']['role']=='PROTECTED' for b in cat['businesses']),3)
  self.assertEqual(sum(b['recovery']['role']=='FALLBACK_POOL' for b in cat['businesses']),3)
 def test_recovery_targets_not_added_to_primary_live_metrics(self):
  self.apply_catalog();apps=self.client.get('/api/v1/production-scene/live/critical-apps').json()['data']['items']
  b=next(b for b in apps if b['name']=='sample-business-01')
  self.assertEqual(sum(len(s['endpoints']) for s in b['dependency_services']),4)
  self.assertEqual(sum(len(s['endpoints']) for s in b['recovery_dependencies']),4)
  self.assertEqual(b['business_observed_status'],'UNKNOWN')
 def test_failed_policy_apply_is_transactional(self):
  from .models import EscapePlan
  self.apply_catalog();EscapePlan.objects.all().delete();rev=current_revision()
  with patch('production_scene.importer.audit',side_effect=RuntimeError('failure')):
   with self.assertRaises(RuntimeError):self.apply_catalog()
  self.assertEqual(EscapePlan.objects.count(),0);self.assertEqual(current_revision(),rev)

@skipUnless(PACKET is not None,'Optional local demo bundle not installed')
class NamedGroupCorrectionTests(TestCase):
 """Real database migration-path tests. Do not substitute mocks for these on release."""
 def seed_legacy(self, with_plan=True):
  from .catalog_legacy_v2 import compile_catalog as old_compile
  from .catalog_core import digest
  from .importer import FIELDS,COMMON,record_core,POD_FIELDS,SCOPE_FIELDS
  from .models import EscapePlan
  old=old_compile(PACKET);cat=old['catalog']
  src=CatalogImport.objects.create(bundle_id=old['bundle_id'],source_hash=old['source_hash'],payload=PACKET,counts=old['counts'])
  for collection,(model,extra) in FIELDS.items():
   for row in cat[collection]:model.objects.create(**{k:row[k] for k in COMMON+extra})
  for row in cat['pd-groups']:DeploymentIdentity.objects.create(pd_group_id=row['id'],source=src,**{k:row[k] for k in SCOPE_FIELDS})
  for row in cat['business-pd-bindings']:
   BusinessPDGroupBinding.objects.create(id=row['id'],business_id=row['business_id'],pd_group_id=row['pd_group_id'],source=src)
   m.BusinessServiceBinding.objects.get_or_create(business_id=row['business_id'],service_id=row['service_id'])
  for row in cat['pods']:PodRegistration.objects.create(id=row['id'],source=src,**{k:row[k] for k in POD_FIELDS})
  for row in cat['endpoint-pod-bindings']:EndpointPodBinding.objects.create(id=row['id'],endpoint_id=row['endpoint_id'],pod_id=row['pod_id'],source=src)
  src.created_records=record_core(old);src.save(update_fields=['created_records'])
  if with_plan:
   policy=json.loads((data_root()/'legacy/escape-policy-v2.json').read_text())
   EscapePlan.objects.create(plan_id=policy['plan_id'],source=src,payload=policy,content_sha256=digest(policy))
  return src,old
 def correct(self):return import_catalog(PACKET,apply=True,expected_revision=current_revision())
 def test_confirmed_legacy_four_groups_become_three(self):
  src,old=self.seed_legacy();r=self.correct();src.refresh_from_db()
  self.assertEqual((m.PDGroup.objects.count(),DeploymentScope.objects.count(),src.normalization_version),(3,4,3))
  self.assertEqual(r['identity_correction']['before_groups'],4);self.assertEqual(r['identity_correction']['after_groups'],3)
  self.assertFalse(m.PDGroup.objects.filter(id__in=[g['id'] for g in old['catalog']['pd-groups']]).exists());verify_import(src)
 def test_preview_does_not_change_legacy_objects(self):
  src,old=self.seed_legacy();before=list(m.Endpoint.objects.values('id','pd_group_id','version'));rev=current_revision()
  r=import_catalog(PACKET);self.assertTrue(r['identity_correction_pending']);src.refresh_from_db()
  self.assertEqual(src.normalization_version,1);self.assertEqual(m.PDGroup.objects.count(),4)
  self.assertEqual(list(m.Endpoint.objects.values('id','pd_group_id','version')),before);self.assertEqual(DeploymentScope.objects.count(),0)
  self.assertEqual(CatalogCorrection.objects.count(),0);self.assertEqual(current_revision(),rev)
 def test_physical_ids_and_memberships_preserved(self):
  src,old=self.seed_legacy();before={model.__name__:list(model.objects.values_list('pk',flat=True)) for model in [m.Endpoint,PodRegistration,EndpointPodBinding]}
  self.correct()
  for model in [m.Endpoint,PodRegistration,EndpointPodBinding]:self.assertCountEqual(list(model.objects.values_list('pk',flat=True)),before[model.__name__])
 def test_archive_contains_full_before_images_and_digest(self):
  from .catalog_core import digest
  src,old=self.seed_legacy();self.correct();a=CatalogCorrection.objects.get()
  self.assertEqual(a.content_sha256,digest(a.payload));self.assertEqual(len(a.payload['before']['groups']),4)
  self.assertEqual(len(a.payload['before']['endpoints']),8);self.assertEqual(a.payload['before']['source_payload'],PACKET)
 def test_repeated_correction_idempotent(self):
  self.seed_legacy();self.correct();rev=current_revision();r=self.correct()
  self.assertFalse(r['applied']);self.assertIsNone(r['identity_correction']);self.assertEqual(current_revision(),rev)
  self.assertEqual(CatalogCorrection.objects.count(),1);self.assertEqual(m.PDGroup.objects.count(),3)
 def test_legacy_without_escape_plan_also_supported(self):
  from .models import EscapePlan
  self.seed_legacy(with_plan=False);self.correct();self.assertEqual(EscapePlan.objects.count(),1)
  self.assertEqual(len(EscapePlan.objects.get().payload['target_group_ids']),1)
 def test_real_engine_bindings_and_telemetry_not_deleted_or_changed(self):
  import uuid
  from django.utils import timezone
  self.seed_legacy();ep=m.Endpoint.objects.first()
  provider=m.ProviderInstance.objects.create(code='external-provider',name='外部来源',environment_code='PRD',base_url_ref='https://provider.invalid')
  binding=m.EngineBinding.objects.create(code='existing-binding',name='已有绑定',environment_code='PRD',provider=provider,environment_id=uuid.uuid4(),engine_id='existing',engine_type='sglang',model_name='sample-model-01',endpoint=ep,scope='ENDPOINT')
  snapshot=m.TelemetrySnapshot.objects.create(binding=binding,binding_version=1,provider_snapshot_id='existing-source',source_end=timezone.now(),payload={'keep':'exactly'},content_hash='a'*64,json_bytes=18)
  before_binding=list(m.EngineBinding.objects.values());before_snapshot=list(m.TelemetrySnapshot.objects.values());self.correct()
  self.assertEqual(list(m.EngineBinding.objects.values()),before_binding);self.assertEqual(list(m.TelemetrySnapshot.objects.values()),before_snapshot)
 def test_modified_endpoint_aborts_without_partial_correction(self):
  self.seed_legacy();m.Endpoint.objects.filter(pk=m.Endpoint.objects.first().pk).update(workload_ref='user-changed')
  with self.assertRaises(APIError):self.correct()
  self.assertEqual(m.PDGroup.objects.count(),4);self.assertEqual(CatalogCorrection.objects.count(),0)
 def test_generic_legacy_import_reference_blocks_deletion(self):
  import uuid
  self.seed_legacy();m.ImportRecord.objects.create(namespace='other-import',legacy_id='existing',entity_id=m.PDGroup.objects.first().id,source_hash='a'*64)
  with self.assertRaises(APIError):self.correct()
  self.assertEqual(m.PDGroup.objects.count(),4);self.assertEqual(DeploymentScope.objects.count(),0)
 def test_unknown_extra_endpoint_reference_blocks_correction(self):
  self.seed_legacy();e=m.Endpoint.objects.first()
  m.Endpoint.objects.create(code='other-disabled-ep',name='外部停用引用',environment_code=e.environment_code,service=e.service,cluster=e.cluster,pd_group=e.pd_group,role=e.role,enabled=False)
  with self.assertRaises(APIError):self.correct()
  self.assertEqual(m.PDGroup.objects.count(),4);self.assertEqual(m.Endpoint.objects.count(),9)
 def test_foreign_same_name_group_not_merged(self):
  self.seed_legacy();g=m.PDGroup.objects.first();m.PDGroup.objects.create(code='foreign-pd',name=g.name,service=g.service,environment_code=g.environment_code)
  with self.assertRaises(APIError):self.correct()
  self.assertEqual(m.PDGroup.objects.count(),5)
 def test_corrected_namespaces_do_not_expand_business_data(self):
  self.seed_legacy();self.correct();c=self.client.get('/api/v1/production-scene/catalog').json()['data']['catalog']
  fallback=[g for g in c['pd-groups'] if g['name']=='pd-server-dsv4flash-fallback'];self.assertEqual(len(fallback),1);self.assertEqual(len(fallback[0]['namespaces']),2)
  self.assertEqual(len(c['business-deployment-bindings']),9)
  apps=self.client.get('/api/v1/production-scene/live/critical-apps').json()['data']['items']
  expected={'sample-business-01':4,'sample-business-02':4,'sample-business-06':4,'sample-business-05':2,'sample-business-03':2,'sample-team-02':2}
  for app in apps:self.assertEqual(sum(len(s['endpoints']) for s in app['dependency_services']),expected[app['name']])
 def test_audit_failure_rolls_back_full_correction(self):
  src,old=self.seed_legacy();groups=list(m.PDGroup.objects.values());eps=list(m.Endpoint.objects.values());rev=current_revision()
  with patch('production_scene.importer.audit',side_effect=RuntimeError('injected failure')):
   with self.assertRaises(RuntimeError):self.correct()
  src.refresh_from_db();self.assertEqual(src.normalization_version,1);self.assertEqual(list(m.PDGroup.objects.values()),groups)
  self.assertEqual(list(m.Endpoint.objects.values()),eps);self.assertEqual(CatalogCorrection.objects.count(),0);self.assertEqual(current_revision(),rev)
 @override_settings(PRODUCTION_SCENE_REPLAY_ENABLED=True)
 def test_old_normalization_replay_requires_confirmation(self):
  self.seed_legacy();response=self.client.get('/api/v1/production-scene/replay/dataset')
  self.assertEqual(response.status_code,409);self.assertEqual(response.json()['error']['code'],'PD_GROUP_CORRECTION_REQUIRED')
 @override_settings(PRODUCTION_SCENE_REPLAY_ENABLED=True)
 def test_after_correction_default_frame_has_all_data(self):
  self.seed_legacy();self.correct();response=self.client.get('/api/v1/production-scene/replay/frame?step=390')
  self.assertEqual(response.status_code,200);data=response.json()['projections']
  self.assertEqual(len(data['overview']['data']['items']),8);self.assertEqual(len(data['critical-apps']['data']['items']),6)
  self.assertTrue(all(len(e['metrics'])==20 for e in data['overview']['data']['items']))
