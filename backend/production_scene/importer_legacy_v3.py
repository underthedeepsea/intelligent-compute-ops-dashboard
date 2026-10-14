from .data_files import data_root,read_data
"""Atomic Gateway catalog import and explicitly confirmed PD-name correction.

Only records owned by a verified, unchanged earlier bundle are reparented.
Endpoint IDs, Pod IDs, provider bindings and all telemetry rows are untouched.
"""
import json
from pathlib import Path
from django.db import transaction
from control import models as m
from control.access import bump, audit
from control.catalog import APIError, serialize
from .models import (CatalogImport, DeploymentIdentity, BusinessPDGroupBinding,
                     PodRegistration, EndpointPodBinding, DeploymentScope,
                     BusinessDeploymentBinding, CatalogCorrection, EscapePlan)
from .catalog_legacy_v3 import compile_catalog, digest, NORMALIZATION_VERSION
from .catalog_legacy_v2 import compile_catalog as compile_legacy
def install_plan(source, compiled, apply=False):
    from .recovery_core import compile_plan
    packet=json.loads((data_root()/'legacy/escape-policy-v3.json').read_text())
    plan=compile_plan(packet,compiled['catalog'])
    old=EscapePlan.objects.filter(pk=plan['plan_id']).first()
    if old:
        if old.payload!=packet or old.content_sha256!=digest(packet) or old.source_id!=source.pk:
            raise APIError('ESCAPE_PLAN_CONFLICT','旧预案存在未知改动',409)
        return False
    if apply:EscapePlan.objects.create(plan_id=packet['plan_id'],source=source,payload=packet,content_sha256=digest(packet))
    return True

COMMON = ['id','code','name','environment_code','enabled','origin']
FIELDS = {
    'teams': (m.Team, []),
    'businesses': (m.Business, ['team_id','owner','critical','watch_order']),
    'models': (m.Model, []), 'clusters': (m.KubernetesCluster, ['region']),
    'services': (m.InferenceService, ['model_id','deployment_mode']),
    'pd-groups': (m.PDGroup, ['service_id']),
    'endpoints': (m.Endpoint, ['service_id','cluster_id','pd_group_id','role','namespace',
                              'workload_kind','workload_ref','address_ref','configured_nodes']),
}
SCOPE_FIELDS = ['cluster_id','namespace','placement_state','placement_note']
POD_FIELDS = ['cluster_id','namespace','pod_name','workload_ref','node_name','identity_state']


def current_revision():
    row = m.Revision.objects.filter(pk=1).first()
    return row.metadata if row else 0


def stored_fields(obj, fields):
    result = {}
    for key in fields:
        value = getattr(obj, key)
        result[key] = str(value) if key.endswith('_id') or key == 'id' else value
    return result


def require(condition, object_id, code='CATALOG_DRIFT'):
    if not condition:
        raise APIError(code, '目录已变化或存在冲突，请先核对；未覆盖：' + str(object_id), 409)


def record_core(compiled):
    records = []
    for collection, (model, extra) in FIELDS.items():
        for item in compiled['catalog'][collection]:
            obj = model.objects.get(pk=item['id'])
            records.append({'collection': collection, 'id': str(obj.pk),
                            'fields': stored_fields(obj, COMMON + extra)})
    return records


def install_relations(source, compiled):
    """Caller holds revision lock. Conflict checks prohibit implicit overwrite."""
    cat = compiled['catalog']
    for scope in cat['deployment-scopes']:
        fields = {k: scope[k] for k in ['pd_group_id'] + SCOPE_FIELDS}
        obj, new = DeploymentScope.objects.get_or_create(
            id=scope['id'], defaults={**fields, 'source': source})
        require(obj.source_id == source.pk and stored_fields(obj, fields) == fields, scope['id'])
    for link in cat['business-pd-bindings']:
        fields = {k: link[k] for k in ['business_id','pd_group_id']}
        obj, new = BusinessPDGroupBinding.objects.get_or_create(
            id=link['id'], defaults={**fields, 'source': source})
        require(obj.source_id == source.pk and obj.enabled and stored_fields(obj, fields) == fields, link['id'])
        core, new = m.BusinessServiceBinding.objects.get_or_create(
            business_id=link['business_id'], service_id=link['service_id'], defaults={'enabled': True})
        require(core.enabled, link['business_id'])
    for link in cat['business-deployment-bindings']:
        fields = {k: link[k] for k in ['business_id','deployment_scope_id']}
        obj, new = BusinessDeploymentBinding.objects.get_or_create(
            id=link['id'], defaults={**fields, 'source': source})
        require(obj.source_id == source.pk and obj.enabled and stored_fields(obj, fields) == fields, link['id'])
    for pod in cat['pods']:
        fields = {k: pod[k] for k in POD_FIELDS}
        obj, new = PodRegistration.objects.get_or_create(
            id=pod['id'], defaults={**fields, 'source': source})
        require(obj.source_id == source.pk and stored_fields(obj, fields) == fields, pod['id'])
    for link in cat['endpoint-pod-bindings']:
        fields = {k: link[k] for k in ['endpoint_id','pod_id']}
        obj, new = EndpointPodBinding.objects.get_or_create(
            id=link['id'], defaults={**fields, 'source': source})
        require(obj.source_id == source.pk and stored_fields(obj, fields) == fields, link['id'])


def verify_import(source, compiled=None, *, legacy=False):
    """Fail closed for stale normalization, missing rows, or changed scope relations."""
    if not legacy and source.normalization_version != NORMALIZATION_VERSION:
        raise APIError('PD_GROUP_CORRECTION_REQUIRED',
                       '请重新加载清单并确认导入，将旧的四组目录修正为三个 PD Group', 409)
    compiled = compiled or compile_catalog(source.payload)
    cat = compiled['catalog']
    require(source.source_hash == digest(source.payload) == compiled['source_hash'], source.pk)
    require(source.counts == compiled['counts'], source.pk)
    expected = {(collection, row['id']) for collection in FIELDS for row in cat[collection]}
    recorded = {(r['collection'], r['id']) for r in source.created_records}
    require(expected == recorded and len(recorded) == len(source.created_records), source.pk)
    for rec in source.created_records:
        obj = FIELDS[rec['collection']][0].objects.filter(pk=rec['id']).first()
        require(obj is not None and stored_fields(obj, rec['fields']) == rec['fields'], rec['id'])
    for group in cat['pd-groups']:
        if legacy:
            require(DeploymentIdentity.objects.filter(pd_group_id=group['id'], source=source,
                    **{k: group[k] for k in SCOPE_FIELDS}).exists(), group['id'])
        expected_eps = {e['id'] for e in cat['endpoints'] if e['pd_group_id'] == group['id']}
        actual_eps = {str(i) for i in m.Endpoint.objects.filter(pd_group_id=group['id'], enabled=True).values_list('id', flat=True)}
        require(actual_eps == expected_eps, group['id'])
    if not legacy:
        for scope in cat['deployment-scopes']:
            require(DeploymentScope.objects.filter(id=scope['id'], source=source,
                **{k: scope[k] for k in ['pd_group_id'] + SCOPE_FIELDS}).exists(), scope['id'])
        require(set(DeploymentScope.objects.filter(source=source).values_list('id', flat=True)) ==
                {__import__('uuid').UUID(x['id']) for x in cat['deployment-scopes']}, source.pk)
        for link in cat['business-deployment-bindings']:
            require(BusinessDeploymentBinding.objects.filter(id=link['id'], source=source, enabled=True,
                business_id=link['business_id'], deployment_scope_id=link['deployment_scope_id']).exists(), link['id'])
    for link in cat['business-pd-bindings']:
        require(BusinessPDGroupBinding.objects.filter(id=link['id'], business_id=link['business_id'],
                pd_group_id=link['pd_group_id'], enabled=True, source=source).exists(), link['id'])
        require(m.BusinessServiceBinding.objects.filter(business_id=link['business_id'],
                service_id=link['service_id'], enabled=True).exists(), link['business_id'])
    for business in cat['businesses']:
        actual = {str(i) for i in BusinessPDGroupBinding.objects.filter(
            business_id=business['id'], enabled=True).values_list('pd_group_id', flat=True)}
        require(actual == set(business['pd_group_ids']), business['id'])
        services = {str(i) for i in m.BusinessServiceBinding.objects.filter(
            business_id=business['id'], enabled=True).values_list('service_id', flat=True)}
        require(services == set(business['service_ids']), business['id'])
        if not legacy:
            scopes = {str(i) for i in BusinessDeploymentBinding.objects.filter(
                business_id=business['id'], enabled=True).values_list('deployment_scope_id', flat=True)}
            require(scopes == set(business['deployment_scope_ids']), business['id'])
    for pod in cat['pods']:
        require(PodRegistration.objects.filter(id=pod['id'], source=source,
                **{k: pod[k] for k in POD_FIELDS}).exists(), pod['id'])
    for link in cat['endpoint-pod-bindings']:
        require(EndpointPodBinding.objects.filter(id=link['id'], endpoint_id=link['endpoint_id'],
                pod_id=link['pod_id'], source=source).exists(), link['id'])
    for ep in cat['endpoints']:
        actual = {str(i) for i in EndpointPodBinding.objects.filter(endpoint_id=ep['id']).values_list('pod_id', flat=True)}
        require(actual == set(ep['pod_ids']), ep['id'])


def correct_legacy(source, compiled):
    """Execute INSIDE caller's transaction, including during rollback-only preview.

    Moves catalog FKs, never physical Endpoint IDs. Replaced group rows are archived
    with full before-images. Unknown dependants abort BEFORE any destructive change.
    """
    legacy = compile_legacy(source.payload)
    verify_import(source, legacy, legacy=True)
    require(not CatalogCorrection.objects.filter(source=source).exists(), source.pk)
    old_ids = {g['id'] for g in legacy['catalog']['pd-groups']}
    new_ids = {g['id'] for g in compiled['catalog']['pd-groups']}
    old_ep_ids = {e['id'] for e in legacy['catalog']['endpoints']}
    require(old_ep_ids == {e['id'] for e in compiled['catalog']['endpoints']}, 'Endpoint IDs')
    require(not m.PDGroup.objects.filter(pk__in=new_ids).exists(), '目标 PD Group ID')
    # Do not absorb unrelated same-name groups merely because names happen to match.
    for g in compiled['catalog']['pd-groups']:
        require(not m.PDGroup.objects.filter(name=g['name'], environment_code=g['environment_code'],
                service_id=g['service_id']).exclude(pk__in=old_ids).exists(), g['name'])
    known_models = {m.Endpoint, DeploymentIdentity, BusinessPDGroupBinding}
    for rel in m.PDGroup._meta.related_objects:
        query = rel.related_model.objects.filter(**{rel.field.attname + '__in': old_ids})
        if rel.related_model not in known_models:
            require(not query.exists(), rel.related_model._meta.label, 'UNMANAGED_PD_REFERENCE')
    require(not m.ImportRecord.objects.filter(entity_id__in=old_ids).exists(), 'ImportRecord', 'UNMANAGED_PD_REFERENCE')
    # Also reject disabled or foreign-owned dependants; they must not be discarded.
    require({str(i) for i in m.Endpoint.objects.filter(pd_group_id__in=old_ids).values_list('id', flat=True)} == old_ep_ids, '额外 Endpoint 引用')
    require(not DeploymentIdentity.objects.filter(pd_group_id__in=old_ids).exclude(source=source).exists(), '部署来源')
    require(not BusinessPDGroupBinding.objects.filter(pd_group_id__in=old_ids).exclude(source=source).exists(), '业务组来源')
    legacy_links = {r['id'] for r in legacy['catalog']['business-pd-bindings']}
    require({str(i) for i in BusinessPDGroupBinding.objects.filter(pd_group_id__in=old_ids).values_list('id', flat=True)} == legacy_links, '额外业务组引用')
    require(not DeploymentScope.objects.filter(source=source).exists(), '已存在部分新部署范围')
    old_policy = read_data('legacy/escape-policy-v2.json')
    saved_plans = list(EscapePlan.objects.filter(source=source))
    for plan in saved_plans:
        require(plan.payload == old_policy and plan.content_sha256 == digest(old_policy), plan.plan_id, 'ESCAPE_PLAN_CONFLICT')
    # A plan from another source must not silently retain a removed group reference.
    for plan in EscapePlan.objects.exclude(source=source):
        refs = set(plan.payload.get('source_group_ids', [])) | set(plan.payload.get('target_group_ids', []))
        require(not refs.intersection(old_ids), plan.plan_id, 'UNMANAGED_PD_REFERENCE')
    before = {
        'source_hash': source.source_hash, 'source_payload': source.payload,
        'counts': source.counts, 'created_records': source.created_records,
        'normalization_version': source.normalization_version,
        'groups': [serialize(x) for x in m.PDGroup.objects.filter(pk__in=old_ids)],
        'endpoints': [serialize(x) for x in m.Endpoint.objects.filter(pk__in=old_ep_ids)],
        'deployment_identities': [serialize(x) for x in DeploymentIdentity.objects.filter(source=source)],
        'business_group_bindings': [serialize(x) for x in BusinessPDGroupBinding.objects.filter(source=source)],
        'escape_plans': [serialize(x) for x in saved_plans],
    }
    for g in compiled['catalog']['pd-groups']:
        obj = m.PDGroup(**{k: g[k] for k in COMMON + ['service_id']})
        obj.full_clean(); obj.save()
    for ep in compiled['catalog']['endpoints']:
        obj = m.Endpoint.objects.get(pk=ep['id'])
        obj.pd_group_id = ep['pd_group_id']; obj.version += 1
        obj.full_clean(); obj.save(update_fields=['pd_group_id','version'])
    BusinessPDGroupBinding.objects.filter(source=source, pd_group_id__in=old_ids).delete()
    DeploymentIdentity.objects.filter(source=source, pd_group_id__in=old_ids).delete()
    # PROTECT remains a final backstop after explicit unmanaged-reference checks.
    m.PDGroup.objects.filter(pk__in=old_ids).delete()
    install_relations(source, compiled)
    for plan in saved_plans: plan.delete()
    install_plan(source, compiled, apply=True)
    from_version = source.normalization_version
    source.counts = compiled['counts']; source.created_records = record_core(compiled)
    source.normalization_version = NORMALIZATION_VERSION
    source.save(update_fields=['counts','created_records','normalization_version'])
    payload = {'reason': 'USER_CONFIRMED_PD_GROUP_NAME_IDENTITY', 'before': before,
               'group_id_map': compiled['legacy_group_map'],
               'preserved_endpoint_ids': sorted(old_ep_ids), 'after_counts': compiled['counts']}
    CatalogCorrection.objects.create(source=source, from_version=from_version,
        to_version=NORMALIZATION_VERSION, payload=payload, content_sha256=digest(payload))
    verify_import(source, compiled)
    return {'before_groups': len(old_ids), 'after_groups': len(new_ids),
            'preserved_endpoints': len(old_ep_ids), 'deployment_scopes': len(compiled['catalog']['deployment-scopes'])}


def import_catalog(packet, *, apply=False, expected_revision=None, actor='anonymous'):
    compiled = compile_catalog(packet)
    with transaction.atomic():
        rev, _ = m.Revision.objects.select_for_update().get_or_create(pk=1)
        if apply and (type(expected_revision) is not int or expected_revision != rev.metadata):
            raise APIError('VERSION_CONFLICT', '目录已变化，请重新校验后再导入', 409, {'current_revision': rev.metadata})
        source = CatalogImport.objects.select_for_update().filter(pk=compiled['bundle_id']).first()
        correction = None; plan_added = False; already = bool(source)
        if source:
            if source.source_hash != compiled['source_hash']:
                raise APIError('BUNDLE_IMMUTABLE', '同一个 bundle_id 不能替换不同内容；请核对目录差异', 409)
            if source.normalization_version < NORMALIZATION_VERSION:
                correction = correct_legacy(source, compiled)
            else:
                verify_import(source, compiled)
                plan_added = install_plan(source, compiled, apply=apply)
        else:
            source = CatalogImport.objects.create(bundle_id=compiled['bundle_id'],
                source_hash=compiled['source_hash'], payload=packet, counts=compiled['counts'],
                normalization_version=NORMALIZATION_VERSION)
            orders = m.Business.objects.filter(enabled=True, critical=True).values_list('watch_order', flat=True)
            next_order = max([n for n in orders if n is not None] + [0]) + 1
            for collection, (model, extra) in FIELDS.items():
                for item in compiled['catalog'][collection]:
                    fields = {k: item[k] for k in COMMON + extra}
                    obj = model.objects.filter(pk=item['id']).first()
                    if obj:
                        actual = stored_fields(obj, fields)
                        require(all(actual[k] == value for k, value in fields.items() if k != 'watch_order'), item['id'], 'CATALOG_CONFLICT')
                    else:
                        natural = {'name': item['name'], 'environment_code': item['environment_code']}
                        if collection == 'pd-groups': natural['service_id'] = item['service_id']
                        if collection == 'endpoints': natural.update({k:item[k] for k in ['service_id','pd_group_id','cluster_id','role','namespace','workload_ref']})
                        require(not model.objects.filter(**natural).exists(), item['name'], 'EXISTING_NATURAL_IDENTITY')
                        if collection == 'businesses' and fields['critical']:
                            fields['watch_order'] = next_order; next_order += 1
                        obj = model(**fields); obj.full_clean(); obj.save()
            install_relations(source, compiled)
            source.created_records = record_core(compiled); source.save(update_fields=['created_records'])
            verify_import(source, compiled)
            plan_added = install_plan(source, compiled, apply=apply)
        changed = not already or bool(correction) or plan_added
        if apply and changed:
            bump('metadata')
            audit(actor, 'pd_group_identity_corrected' if correction else 'production_catalog_import',
                  m.InferenceService.objects.get(pk=compiled['catalog']['services'][0]['id']),
                  {'bundle_id': source.pk, 'source_hash': source.source_hash, 'counts': compiled['counts'],
                   'identity_correction': correction, 'automatic_switch': False})
        revision = current_revision() if apply else rev.metadata
        if not apply: transaction.set_rollback(True)
        return {**compiled, 'already_imported': already, 'applied': bool(apply and changed),
                'identity_correction': correction, 'identity_correction_pending': bool(correction and not apply),
                'escape_plan_added': bool(apply and plan_added), 'escape_plan_pending': bool(plan_added and not apply),
                'metadata_revision': revision}
