from .data_files import data_root,read_data
"""Atomic, explicit v4 -> v5 catalog amendment. Caller owns the revision lock.
No provider/telemetry changes. Before images are retained and unknown edits reject.
"""
import json
from pathlib import Path
from control import models as m
from control.catalog import serialize
from . import models as s
from .catalog_core import digest, NORMALIZATION_VERSION
from .catalog_legacy_v4 import compile_catalog as compile_v4
from .catalog_revision_core import revision_plan


def apply_revision(source, compiled, packet):
    from .importer import require, COMMON, FIELDS, stored_fields, install_relations, record_core, verify_import
    from .importer_legacy_v4 import verify_import as verify_v4
    folder=data_root()
    prior=json.loads((folder/'legacy/production-catalog-v4.json').read_text())
    target=json.loads((folder/'production-catalog.json').read_text())
    require(source.normalization_version==4 and source.payload==prior and source.source_hash==digest(prior),
            source.pk,'UNRECOGNIZED_CATALOG_REVISION_SOURCE')
    require(packet==target and compiled['source_hash']==digest(target),source.pk,'UNRECOGNIZED_CATALOG_REVISION_TARGET')
    old=compile_v4(prior); verify_v4(source,old)
    plan=revision_plan(old,compiled)
    require(not s.CatalogRevisionAudit.objects.filter(source=source,to_version=5).exists(),source.pk)
    changed=plan['pod_alias_changed_endpoints']
    # The table corrects the 02 Pod spelling. Do not reinterpret an attached live member.
    require(not m.RuntimeMember.objects.filter(endpoint_id__in=changed).exists(), 'RuntimeMember','RUNTIME_REBIND_REQUIRED')
    require(not m.EngineBinding.objects.filter(endpoint_id__in=changed,runtime_member__isnull=False).exists(),
            'EngineBinding POD scope','RUNTIME_REBIND_REQUIRED')
    retired_pods=set(plan['changes']['pods']['retired'])
    for rel in s.PodRegistration._meta.related_objects:
        query=rel.related_model.objects.filter(**{rel.field.attname+'__in':retired_pods})
        if rel.related_model==s.EndpointPodBinding:
            require(not query.exclude(source=source).exists(),rel.related_model._meta.label,'UNMANAGED_POD_REFERENCE')
        else:require(not query.exists(),rel.related_model._meta.label,'UNMANAGED_POD_REFERENCE')
    previous_policy=json.loads((folder/'legacy/escape-policy-v4.json').read_text())
    policy=json.loads((folder/'escape-policy.json').read_text())
    saved=list(s.EscapePlan.objects.filter(source=source))
    for p in saved:require(p.payload==previous_policy and p.content_sha256==digest(previous_policy),p.pk,'ESCAPE_PLAN_CONFLICT')
    existing_hw={str(h.pk):h for h in s.NodeHardware.objects.filter(source=source)}
    for h in compiled['catalog']['gpu-hosts']:
        item=existing_hw.get(h['id'])
        if item:
            # User-confirmed equivalences only. MX550 is not silently treated as C550.
            equivalent={'NVIDIA-H200':{'H200','NVIDIA-H200'},'METAX-C550':{'C550','METAX-C550'}}.get(h['gpu_model'],{h['gpu_model']})
            require(item.is_gpu_host and (not item.gpu_model or item.gpu_model in equivalent),h['node_name'],'HARDWARE_METADATA_CONFLICT')
    before={'source':serialize(source),'node_hardware':[serialize(x) for x in existing_hw.values()],
            'pods':[serialize(x) for x in s.PodRegistration.objects.filter(source=source)],
            'pod_bindings':[serialize(x) for x in s.EndpointPodBinding.objects.filter(source=source)],
            'escape_plans':[serialize(x) for x in saved]}
    for collection,(model,extra) in FIELDS.items():
        old_ids={x['id'] for x in old['catalog'][collection]}
        for item in compiled['catalog'][collection]:
            if item['id'] in old_ids:continue
            fields={k:item[k] for k in COMMON+extra}
            require(not model.objects.filter(pk=item['id']).exists(),item['id'],'CATALOG_CONFLICT')
            natural={'name':item['name'],'environment_code':item['environment_code']}
            if collection=='pd-groups':natural['service_id']=item['service_id']
            if collection=='endpoints':natural.update({k:item[k] for k in ('service_id','pd_group_id','cluster_id','role','namespace','workload_ref')})
            require(not model.objects.filter(**natural).exists(),item['name'],'EXISTING_NATURAL_IDENTITY')
            obj=model(**fields);obj.full_clean();obj.save()
    stale_links=set(plan['changes']['endpoint-pod-bindings']['retired'])
    s.EndpointPodBinding.objects.filter(source=source,pk__in=stale_links).delete()
    s.PodRegistration.objects.filter(source=source,pk__in=retired_pods).update(enabled=False)
    install_relations(source,compiled)
    for h in compiled['catalog']['gpu-hosts']:
        obj=s.NodeHardware.objects.select_for_update().get(pk=h['id'])
        if obj.gpu_model!=h['gpu_model'] or obj.gpu_model_source!='USER_SCREENSHOT':
            obj.gpu_model=h['gpu_model'];obj.gpu_model_source='USER_SCREENSHOT';obj.version+=1
            obj.full_clean();obj.save(update_fields=['gpu_model','gpu_model_source','version'])
    from .recovery import install_plan
    for p in saved:p.delete()
    install_plan(source,compiled,apply=True)
    source.payload=packet;source.source_hash=compiled['source_hash'];source.counts=compiled['counts']
    source.normalization_version=NORMALIZATION_VERSION;source.created_records=record_core(compiled)
    source.save(update_fields=['payload','source_hash','counts','normalization_version','created_records'])
    image={'before':before,'plan':plan,'after_source_hash':source.source_hash}
    s.CatalogRevisionAudit.objects.create(source=source,from_version=4,to_version=5,payload=image,content_sha256=digest(image))
    verify_import(source,compiled)
    return plan
