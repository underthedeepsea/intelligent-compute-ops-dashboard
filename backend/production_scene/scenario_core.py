"""Eight-hour synthetic source, persisted separately from production telemetry.
Rules here apply only to this scenario. They are NOT inspection thresholds.
"""
from __future__ import annotations
import math
import json
from pathlib import Path
from .recovery_core import compile_plan,attach_plans
from .hardware_core import host_context
from .scene_rules import evaluate_window
from datetime import datetime, timedelta, timezone
from .catalog_core import compile_catalog, identity, digest, business_contains_endpoint

EP_METRICS={f'{family}_{stat}_ms':('ms/token' if family=='tpot' else 'ms') for family in ['ttft','tpot','e2e'] for stat in ['avg','p90','p95','p99']}
EP_METRICS.update({'ttft_e2e_ratio':'ratio','request_rate':'requests/s','request_rate_per_minute':'requests/min','generated_tokens_per_second':'tokens/s','input_tokens_per_second':'tokens/s','kv_cache_hit_ratio':'ratio','running':'requests','waiting':'requests'})
HOST_METRICS={'cpu_busy_ratio':'ratio','memory_usage_ratio':'ratio','filesystem_usage_ratio':'ratio'}
RULES={
 'EP_QUEUE':{'key':'waiting','warning':16,'critical':32,'label':'排队请求持续增加','kind':'ENDPOINT'},
 'EP_TTFT':{'key':'ttft_p95_ms','warning':700,'critical':1200,'label':'首 Token 延迟升高','kind':'ENDPOINT'},
 'EP_TPOT':{'key':'tpot_p95_ms','warning':65,'critical':100,'label':'逐 Token 延迟升高','kind':'ENDPOINT'},
 'EP_E2E':{'key':'e2e_p99_ms','warning':12000,'critical':18000,'label':'端到端尾延迟升高','kind':'ENDPOINT'},
 'HOST_CPU':{'key':'cpu_busy_ratio','warning':.88,'critical':.95,'label':'主机 CPU 持续繁忙','kind':'HOST'},
 'HOST_MEM':{'key':'memory_usage_ratio','warning':.90,'critical':.96,'label':'主机内存压力','kind':'HOST'},
 'HOST_FS':{'key':'filesystem_usage_ratio','warning':.90,'critical':.97,'label':'文件系统空间压力','kind':'HOST'}
}
for k,r in RULES.items():r.update(id='SCENE.'+k,version='1.1',comparison='>=',confirm_windows=2,recover_windows=3,origin='SYNTHETIC')

def iso(t):return t.isoformat(timespec='seconds')


def frame(dataset, step):
    if type(step) is not int or not 0<=step<dataset['steps']:raise ValueError('step 超出 0–959')
    start=datetime.fromisoformat(dataset['start'])+timedelta(seconds=step*dataset['step_seconds']);end=start+timedelta(seconds=dataset['step_seconds'])
    sample=dataset['samples'][step];cat=dataset['catalog'];eps=[];hardware=[]
    def decorate(item,row,keys,scope):
        point_start=datetime.fromisoformat(dataset['start'])+timedelta(seconds=row.get('at',step)*dataset['step_seconds']);point_end=point_start+timedelta(seconds=dataset['step_seconds'])
        observation={'origin':'SYNTHETIC','source_type':'SCENARIO','data_state':row['q'],'freshness':'FRESH','transport_status':'OK' if row['q']=='REPLAY' else 'SOURCE_ERROR','max_age_seconds':60,'source_window':{'start':iso(point_start),'end':iso(point_end)},'identity':{'scope':scope,'entity_id':item['id']},'provider_snapshot_id':f'szg-8h/{row.get("at",step)}/{item["id"]}'}
        metrics={k:{'value':v,'unit':unit,'state':'AVAILABLE','scope':scope,'collected_at':iso(point_end)} for (k,unit),v in zip(keys.items(),row['v'])}
        findings=[]
        for hit in row['hits']:
            rule=dataset['rules'][hit['rule']]
            findings.append({**rule,**hit,'rule_id':rule['id'],'observed_value':hit['value'],'threshold':rule['critical'] if hit['level']=='CRITICAL' else rule['warning'],'first_seen':iso(datetime.fromisoformat(dataset['start'])+timedelta(seconds=hit['first_step']*30)),'source_window':observation['source_window'],'revalidation_state':'RECOVERING' if hit['clear'] else 'ACTIVE'})
        return {**item,**host_context(item,cat),'pending_confirmation':row.get('pending_confirmation',False),'status':row['s'],'data_state':row['q'],'metrics':metrics,'observation':observation,'findings':findings}
    for item,row in zip(cat['endpoints'],sample['e']):eps.append(decorate(item,row,dataset['endpoint_metrics'],'ENDPOINT'))
    for node,row in zip(dataset['nodes'],sample['h']):
        item={'id':dataset['host_ids'][node],'name':node,'host_id':node,'resource_type':'HOST','node_name':node,'cluster_id':cat['clusters'][0]['id'],'environment_code':cat['clusters'][0]['environment_code']}
        hardware.append(decorate(item,row,dataset['host_metrics'],'DEVICE'))
    services=[{**s,'model_name':next(m['name'] for m in cat['models'] if m['id']==s['model_id']),'endpoints':[e for e in eps if e['service_id']==s['id']]} for s in cat['services']]
    apps=[]
    for b in cat['businesses']:
        deps=[{**s,'endpoints':[e for e in s['endpoints'] if business_contains_endpoint(b,e)]} for s in services if s['id'] in b['service_ids']]
        targets=set(b.get('recovery',{}).get('target_group_ids',[]))
        recovery_deps=[{**s,'endpoints':[e for e in s['endpoints'] if e['pd_group_id'] in targets]} for s in services if any(e['pd_group_id'] in targets for e in s['endpoints'])]
        apps.append({**b,'business_observed_status':'UNKNOWN','dependency_services':deps,'recovery_dependencies':recovery_deps,'metrics':{},'series':[]})
    coverage={'configured':len(eps),'bound':len(eps),'verified':0,'fresh':0,'replay_valid':sum(e['data_state']=='REPLAY' for e in eps)}
    base={'source_type':'SCENARIO','data_state':'REPLAY','source_window':{'start':iso(start),'end':iso(end)},'coverage':coverage,'summary':{k:dataset['counts'][k] for k in ['clusters','services','endpoints','businesses']},'managed_gpu_hosts':len(cat.get('gpu-hosts',[])),'scene':{'id':'szg-8h','step':step,'origin':'SYNTHETIC'},'hardware':hardware}
    return {'catalog':cat,'now':int(end.timestamp()*1000)+1000,'projections':{kind:{'schema_version':'1.0','view_revision':step+1,'data':{**base,'kind':kind,'items':items}} for kind,items in [('overview',eps),('services',services),('critical-apps',apps)]}}
