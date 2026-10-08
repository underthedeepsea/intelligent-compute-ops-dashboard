#!/usr/bin/env python3
"""Append a namespaced, synthetic local preview dataset; never contacts a provider.

Run from the project root: .venv/bin/python demo/local_preview/seed.py
Re-running preserves existing catalog and inference samples. --refresh appends eighteen
inference samples and replaces two namespaced latest-only hardware demo caches.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import uuid
from collections import Counter
from datetime import timedelta

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / 'backend/local.sqlite3'
NAMESPACE = 'local-preview-demo-v1'
PROVIDER_URL = 'https://local-preview-demo.invalid'
ENVIRONMENT_ID = uuid.uuid5(uuid.NAMESPACE_URL, NAMESPACE)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--refresh', action='store_true')
args = parser.parse_args()
if not DB.is_file():
    raise SystemExit('Expected the existing backend/local.sqlite3; initialize local preview first.')
# Scope this standalone process to the one authorized local database. No runtime
# server settings, access users, credentials, or allowlists are changed.
os.environ['CONTROL_LOCAL'] = '1'
os.environ['SQLITE_PATH'] = str(DB)
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
sys.path.insert(0, str(ROOT / 'backend'))
import django
django.setup()
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from control import models as m
from control.access import bump
from control.telemetry import normalize, state
from control.projections import screen
from django.contrib.auth.models import User

if not settings.LOCAL or Path(settings.DATABASES['default']['NAME']).resolve() != DB.resolve():
    raise SystemExit('This script only supports this project local SQLite database.')
viewer = User.objects.get(username='local-preview', is_superuser=False)
if not m.AccessScope.objects.filter(user=viewer, environment_code='local').exists():
    raise SystemExit('Expected existing local-preview/local scope; no permissions will be changed.')
backup_dir = Path(tempfile.mkdtemp(prefix='ai-ops-local-preview-'))
backup = backup_dir / 'before-demo.sqlite3'
with sqlite3.connect(DB) as source, sqlite3.connect(backup) as target:
    source.backup(target)
created = Counter()
now = timezone.now()
run_id = now.strftime('%Y%m%dT%H%M%S%fZ')


def entity(entity_class, suffix, name, **fields):
    code = f'{NAMESPACE}-{suffix}'
    existing = entity_class.objects.filter(code=code).first()
    if existing:
        if existing.origin != 'DEMO' or existing.environment_code != 'local':
            raise ValueError(f'Namespace collision for {code}; refusing to modify it.')
        return existing
    obj = entity_class(code=code, name=f'【演示】{name}', environment_code='local', origin='DEMO', **fields)
    obj.full_clean()
    obj.save()
    created[entity_class.__name__] += 1
    return obj


def relation(relation_class, **fields):
    obj, added = relation_class.objects.get_or_create(**fields)
    if added:
        obj.full_clean()
        created[relation_class.__name__] += 1
    return obj


with transaction.atomic():
    m.Revision.objects.select_for_update().get_or_create(pk=1)
    # A reserved .invalid address and paused PollState prevent network work. The
    # temporary validation allowlist exists only in this seed process.
    allowed_before = settings.PROVIDER_URLS
    settings.PROVIDER_URLS = [*allowed_before, PROVIDER_URL]
    try:
        provider = entity(m.ProviderInstance, 'provider', '离线合成巡检样本',
                          base_url_ref=PROVIDER_URL, origin_verified=False,
                          plugin_versions=['1.0.0'], source_allowlist=[], capabilities={})
    finally:
        settings.PROVIDER_URLS = allowed_before
    if provider.origin_verified or provider.base_url_ref != PROVIDER_URL or provider.source_allowlist:
        raise ValueError('Demo provider was modified to verified; refusing to use it.')
    # Endpoint values are individually authored, not inferred from other endpoints
    # or used to manufacture service/business/infrastructure health.
    scenarios = [
        ('support', '智能客服团队', '客户服务助手', '客服运维（演示）', 'Qwen3-32B', '客服问答推理', '华东智算集群', '华东', '客服 P/D 组', [(186, 37, 42.6, 1720, 8450, .84, 86, 7), (248, 43, 38.2, 1510, 7260, .78, 104, 16)]),
        ('knowledge', '企业知识团队', '企业知识检索', '知识平台（演示）', 'DeepSeek-R1-32B', '知识推理服务', '华北智算集群', '华北', '知识 P/D 组', [(325, 51, 21.4, 980, 5200, .71, 67, 12), (412, 63, 18.7, 860, 4610, .65, 92, 24)]),
        ('coding', '研发效能团队', '代码研发助手', '研发平台（演示）', 'Qwen3-Coder-30B', '代码辅助推理', '西南智算集群', '西南', '代码 P/D 组', [(143, 28, 31.8, 1340, 6900, .91, 58, 3), (198, 34, 27.6, 1180, 6180, .87, 73, 9)]),
    ]
    used_orders = set(m.Business.objects.filter(enabled=True, critical=True).values_list('watch_order', flat=True))
    for index, (slug, team_name, business_name, owner, model_name, service_name, cluster_name, region, pd_name, samples) in enumerate(scenarios):
        team = entity(m.Team, f'team-{slug}', team_name)
        order = 1
        while order in used_orders:
            order += 1
        business = entity(m.Business, f'business-{slug}', business_name,
                          team=team, owner=owner, critical=True, watch_order=order)
        used_orders.add(business.watch_order)
        model = entity(m.Model, f'model-{slug}', model_name)
        service = entity(m.InferenceService, f'service-{slug}', service_name, model=model, deployment_mode='SPLIT_PD')
        cluster = entity(m.KubernetesCluster, f'cluster-{slug}', cluster_name, region=region)
        pd = entity(m.PDGroup, f'pd-{slug}', pd_name, service=service)
        relation(m.BusinessServiceBinding, business=business, service=service, evidence_kind='DEMO')
        key = entity(m.ApiKeyRef, f'key-{slug}', f'{business_name}调用引用', team=team, business=business,
                     external_key_ref=f'{NAMESPACE}-external-{slug}', masked_label=f'demo-••••-{index+1:04d}')
        relation(m.KeyModelGrant, key=key, model=model)
        counts = {'support': (1, 1), 'knowledge': (2, 2), 'coding': (5, 7)}[slug]
        replicas = [(role, values, ordinal) for role, values, count in zip(('PREFILL', 'DECODE'), samples, counts) for ordinal in range(1, count+1)]
        for role, values, ordinal in replicas:
            short_role = 'P' if role == 'PREFILL' else 'D'
            member_suffix = short_role.lower() + (str(ordinal) if ordinal > 1 else '')
            member_label = short_role + (str(ordinal) if ordinal > 1 else '')
            endpoint = entity(m.Endpoint, f'endpoint-{slug}-{member_suffix}', f'{service_name} · {member_label}',
                              service=service, cluster=cluster, pd_group=pd, role=role,
                              address_ref=f'demo-only:{slug}:{member_suffix}')
            entity(m.RuntimeMember, f'runtime-{slug}-{member_suffix}', f'{service_name} · {member_label} 合成 Pod',
                   endpoint=endpoint, cluster=cluster, namespace=NAMESPACE,
                   workload_ref=f'demo-only:{slug}:{member_suffix}',
                   pod_uid=f'demo-{slug}-{member_suffix}', pod_name=f'demo-{slug}-{member_suffix}',
                   node_uid=f'demo-{slug}-node-{member_suffix}', node_name=f'【演示】{region}节点 {member_label}',
                   observed_at=now)
            binding = entity(m.EngineBinding, f'binding-{slug}-{member_suffix}', f'{service_name} {member_label}离线映射',
                             provider=provider, environment_id=ENVIRONMENT_ID,
                             engine_id=f'demo-{slug}-{member_suffix}', engine_type='vllm',
                             model_name=model_name, endpoint=endpoint, scope='ENDPOINT')
            poll, added = m.PollState.objects.get_or_create(binding=binding, defaults={'paused': True, 'error': 'DEMO_OFFLINE'})
            if added:
                created['PollState'] += 1
            if not poll.paused:
                raise ValueError('Demo polling was unpaused; refusing to change existing configuration.')
            if m.TelemetrySnapshot.objects.filter(binding=binding, binding_version=binding.binding_version).exists() and not args.refresh:
                continue
            ttft, tpot, qps, output_tps, input_tps, cache, running, waiting = values
            e2e = ttft + 3000
            def percentiles(avg):
                return {'avg_ms': avg, 'p90_ms': round(avg*1.25, 2), 'p95_ms': round(avg*1.45, 2), 'p99_ms': round(avg*1.8, 2)}
            sid = f'{NAMESPACE}:{run_id}:{slug}:{member_label}'
            raw = {'snapshot_id': sid,
                   'engine': {'engine_id': binding.engine_id, 'engine_type': binding.engine_type, 'model_name': binding.model_name},
                   'source_window': {'start': (now-timedelta(seconds=60)).isoformat(), 'end': now.isoformat()},
                   'status': 'UNKNOWN', 'evaluation_status': 'UNKNOWN',
                   'plugin': {'id': 'inference-performance', 'version': '1.0.0'},
                   'quality': {'state': 'DEMO', 'pending_confirmation': True},
                   'provenance': {'source': 'DEMO_SYNTHETIC_OFFLINE', 'sample_id': sid, 'ingested_at': now.isoformat()},
                   'freshness': {'state': 'FRESH', 'max_age_seconds': 300},
                   'current_metrics': {'ttft': {**percentiles(ttft), 'e2e_ratio': round(ttft/e2e, 4)},
                       'tpot': percentiles(tpot), 'e2e': percentiles(e2e),
                       'traffic': {'qps': qps, 'qpm': round(qps*60, 2)},
                       'throughput': {'generation_tps': output_tps, 'prompt_tps': input_tps},
                       'cache': {'kv_cache_hit_rate': cache}, 'requests': {'running': running, 'waiting': waiting}}}
            payload = normalize(raw, binding, now=now)
            assert payload['observation']['origin'] == 'UNVERIFIED'
            assert state(payload, now=now) == 'UNVERIFIED'
            encoded = json.dumps(payload, sort_keys=True).encode()
            # Deliberately avoid publish(), whose retention cleanup may remove
            # unrelated historical snapshots. These rows are append-only.
            snapshot = m.TelemetrySnapshot(binding=binding, binding_version=binding.binding_version,
                         provider_snapshot_id=sid, source_end=parse_datetime(payload['observation']['source_window']['end']),
                         payload=payload, content_hash=hashlib.sha256(encoded).hexdigest(), json_bytes=len(encoded))
            snapshot.full_clean()
            snapshot.save()
            created['TelemetrySnapshot'] += 1
    # Two explicitly synthetic single devices populate only the five approved slots.
    from control.hardware import normalize_hardware
    hardware_cluster = m.KubernetesCluster.objects.get(code=f'{NAMESPACE}-cluster-support', origin='DEMO', environment_code='local')
    for suffix, resource, gpu, numbers in [
        ('gpu', 'GPU_POOL', 'DEMO-GPU-01', {'utilization_ratio':.72,'temperature_celsius':64,'memory_used_bytes':48*1024**3,'memory_total_bytes':80*1024**3}),
        ('host', 'HOST', '', {'cpu_busy_ratio':.43,'memory_available_bytes':96*1024**3,'memory_total_bytes':256*1024**3}),
    ]:
        binding = entity(m.HardwareBinding, 'hardware-'+suffix, 'GPU 01' if gpu else '主机 01',
                         provider=provider, cluster=hardware_cluster, environment_id=ENVIRONMENT_ID, resource_type=resource,
                         asset_id=uuid.uuid5(ENVIRONMENT_ID, suffix), host_id='DEMO-HOST-01', gpu_uuid=gpu)
        if binding.cluster_id is None:
            binding.cluster = hardware_cluster
            binding.full_clean();binding.save(update_fields=['cluster'])
        elif binding.cluster_id != hardware_cluster.pk:
            raise ValueError('Demo hardware cluster was modified; refusing to reassign it.')
        row, added = m.HardwareObservation.objects.get_or_create(binding=binding, defaults={'paused':True,'error':'DEMO_OFFLINE'})
        if not row.paused: raise ValueError('Demo hardware polling was unpaused; refusing to modify it.')
        if row.payload and not args.refresh: continue
        raw = {'snapshot_id':f'{NAMESPACE}:{run_id}:{suffix}', 'asset_id':str(binding.asset_id),
               'host_id':binding.host_id, 'identity':{'gpu_uuid':gpu,'model':'DEMO GPU'} if gpu else {},
               'window_start':(now-timedelta(seconds=60)).isoformat(), 'window_end':now.isoformat(),
               'freshness':'FRESH', 'status':'UNKNOWN',
               'metrics':{'gpu' if gpu else 'host':{'identity':{},'values':{key:{'value':value,'quality':'VALID','collected_at':now.isoformat()} for key,value in numbers.items()}}}}
        row.payload=normalize_hardware(raw,binding,now=now)
        assert row.payload['observation']['origin']=='UNVERIFIED'
        row.save(update_fields=['payload'])
        created['HardwareObservation']+=1
    if created:
        if any(key != 'TelemetrySnapshot' for key in created):
            bump('metadata')
        if created['TelemetrySnapshot'] or created['HardwareObservation']:
            bump('telemetry')
        m.AuditEvent.objects.create(actor='local-demo-seed', action='seed_demo', entity_id=NAMESPACE,
                                   environment_code='local', changes={'created':dict(created),'synthetic':True})
    checks = {}
    for kind in ('overview', 'pd-groups', 'infrastructure', 'services', 'critical-apps'):
        view = screen(kind, viewer)
        checks[kind] = {'items':len(view['items']), 'coverage':view['coverage'], 'data_state':view['data_state'], 'summary':view['summary']}
    demo_endpoints = [e for e in screen('overview', viewer)['items'] if e['name'].startswith('【演示】')]
    seeded_ids = set(str(pk) for pk in m.Endpoint.objects.filter(code__startswith=NAMESPACE+'-endpoint-').values_list('pk', flat=True))
    demo_endpoints = [e for e in demo_endpoints if e['id'] in seeded_ids]
    assert len(demo_endpoints) == 18
    for slug, expected in [('support', (1, 1)), ('knowledge', (2, 2)), ('coding', (5, 7))]:
        endpoints = m.Endpoint.objects.filter(pd_group__code=f'{NAMESPACE}-pd-{slug}', enabled=True)
        assert tuple(endpoints.filter(role=role).count() for role in ('PREFILL', 'DECODE')) == expected
    assert all(e['observation']['origin']=='UNVERIFIED' and e['status']=='UNKNOWN' for e in demo_endpoints)
    assert all(e['data_state'] in ('UNVERIFIED','STALE') for e in demo_endpoints)
    assert all(e['metrics']['ttft_avg_ms']['value'] is not None for e in demo_endpoints)
    assert not User.objects.get(pk=viewer.pk).is_superuser
print(json.dumps({'namespace':NAMESPACE, 'backup':str(backup), 'created':dict(created), 'checks':checks,
                  'endpoint_ids':{e['name']:e['id'] for e in demo_endpoints}}, ensure_ascii=False, indent=2))
