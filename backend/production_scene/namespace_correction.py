"""Explicit, transaction-bound correction. Refuse unmanaged runtime references."""
import json
from pathlib import Path
from control import models as m
from control.catalog import serialize, APIError
from . import models as s
from .catalog_legacy_v4 import digest, NORMALIZATION_VERSION
from .catalog_legacy_v3 import compile_catalog as compile_v3
from .namespace_core import namespace_plan
from .data_files import read_data,data_root


def correct_namespaces(source, compiled):
    from .importer_legacy_v4 import require, record_core, install_relations, verify_import
    from .importer_legacy_v3 import verify_import as verify_v3
    folder = data_root()
    old_packet = json.loads((folder/'legacy/production-catalog-v3.json').read_text())
    new_packet = json.loads((folder/'legacy/production-catalog-v4.json').read_text())
    require(source.source_hash == digest(old_packet) and source.payload == old_packet,
            source.pk, 'UNRECOGNIZED_NAMESPACE_SOURCE')
    require(compiled['source_hash'] == digest(new_packet), source.pk, 'UNRECOGNIZED_NAMESPACE_TARGET')
    require(source.normalization_version == 3, source.pk, 'NORMALIZATION_CONFLICT')
    old = compile_v3(old_packet)
    verify_v3(source, old)
    plan = namespace_plan(old, compiled)
    require(not s.NamespaceCorrection.objects.filter(source=source).exists(), source.pk)
    retired = set(plan['retired_endpoint_ids'])
    # No guessing how to merge active runtime identities, credentials or telemetry.
    for model in (m.EngineBinding, m.RuntimeMember):
        require(not model.objects.filter(endpoint_id__in=retired).exists(), model._meta.label, 'RUNTIME_REBIND_REQUIRED')
    require(not m.ImportRecord.objects.filter(entity_id__in=retired).exists(), 'ImportRecord', 'UNMANAGED_ENDPOINT_REFERENCE')
    for snapshot in m.ClusterCsvSnapshot.objects.filter(cluster_id__in=[c['id'] for c in old['catalog']['clusters']]):
        require(not any(i in json.dumps(snapshot.endpoint_payload) for i in retired), 'CSV快照', 'RUNTIME_REBIND_REQUIRED')
    # Additive future tables must not create unreviewed references to retired entries.
    for rel in m.Endpoint._meta.related_objects:
        if rel.related_model in {m.EngineBinding, m.RuntimeMember, s.EndpointPodBinding}: continue
        require(not rel.related_model.objects.filter(**{rel.field.attname+'__in':retired}).exists(),
                rel.related_model._meta.label, 'UNMANAGED_ENDPOINT_REFERENCE')
    drop_pods = {x for x,y in plan['maps']['pods'].items() if x!=y}
    drop_scopes = {x for x,y in plan['maps']['deployment-scopes'].items() if x!=y}
    for model, ids, allowed in [(s.PodRegistration,drop_pods,{s.EndpointPodBinding}),
                                (s.DeploymentScope,drop_scopes,{s.BusinessDeploymentBinding})]:
        for rel in model._meta.related_objects:
            qs = rel.related_model.objects.filter(**{rel.field.attname+'__in':ids})
            if rel.related_model not in allowed:
                require(not qs.exists(), rel.related_model._meta.label, 'UNMANAGED_NAMESPACE_REFERENCE')
            else:
                require(not qs.exclude(source=source).exists(), rel.related_model._meta.label, 'UNMANAGED_NAMESPACE_REFERENCE')
    expected_links = {r['id'] for r in old['catalog']['endpoint-pod-bindings']}
    require({str(i) for i in s.EndpointPodBinding.objects.filter(endpoint_id__in=retired).values_list('id',flat=True)} <= expected_links,
            '额外Pod引用', 'UNMANAGED_ENDPOINT_REFERENCE')
    old_policy=json.loads((folder/'legacy/escape-policy-v3.json').read_text())
    new_policy=json.loads((folder/'legacy/escape-policy-v4.json').read_text())
    saved_plans=list(s.EscapePlan.objects.filter(source=source))
    for policy in saved_plans:
        require(policy.payload in [old_policy,new_policy] and policy.content_sha256==digest(policy.payload),
                policy.plan_id,'ESCAPE_PLAN_CONFLICT')
    # Record immutable before-images before any catalogue write.
    before = {'source_hash':source.source_hash,'payload':source.payload,'counts':source.counts,
              'normalization_version':source.normalization_version,'created_records':source.created_records,
              'escape_plans':[serialize(x) for x in saved_plans],
              'endpoints':[serialize(x) for x in m.Endpoint.objects.filter(pk__in=retired)],
              'scopes':[serialize(x) for x in s.DeploymentScope.objects.filter(source=source)],
              'pods':[serialize(x) for x in s.PodRegistration.objects.filter(source=source)],
              'pod_bindings':[serialize(x) for x in s.EndpointPodBinding.objects.filter(source=source)],
              'business_scopes':[serialize(x) for x in s.BusinessDeploymentBinding.objects.filter(source=source)]}
    for ep in m.Endpoint.objects.filter(pk__in=retired):
        ep.enabled = False; ep.version += 1
        ep.save(update_fields=['enabled','version'])
    s.EndpointPodBinding.objects.filter(source=source,endpoint_id__in=retired).delete()
    require(not s.EndpointPodBinding.objects.filter(pod_id__in=drop_pods).exists(), 'Pod仍有额外引用')
    s.PodRegistration.objects.filter(source=source,id__in=drop_pods).delete()
    s.BusinessDeploymentBinding.objects.filter(source=source,deployment_scope_id__in=drop_scopes).delete()
    s.DeploymentScope.objects.filter(source=source,id__in=drop_scopes).delete()
    install_relations(source, compiled)
    for policy in saved_plans:policy.delete()
    s.EscapePlan.objects.create(plan_id=new_policy['plan_id'],source=source,content_sha256=digest(new_policy),payload=new_policy)
    source.payload = new_packet; source.source_hash = compiled['source_hash']
    source.counts = compiled['counts']; source.normalization_version = NORMALIZATION_VERSION
    source.created_records = record_core(compiled)
    source.save(update_fields=['payload','source_hash','counts','normalization_version','created_records'])
    payload = {'before':before, **plan}
    s.NamespaceCorrection.objects.create(source=source,from_version=3,to_version=NORMALIZATION_VERSION,
                                         payload=payload,content_sha256=digest(payload))
    verify_import(source, compiled)
    return plan
