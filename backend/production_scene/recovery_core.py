"""Pure, read-only recovery-plan semantics; never an execution or capacity claim."""
from copy import deepcopy
from .catalog_core import digest, text

def compile_plan(packet, catalog):
    required={'schema_version','plan_id','catalog_bundle_id','mode','source','source_group_ids','target_group_ids','target_scope_state','readiness','automatic_switch','notes'}
    if not isinstance(packet,dict) or set(packet)!=required:
        raise ValueError('逃生预案字段不完整或包含未知字段')
    if type(packet['schema_version']) is not int or packet['schema_version']!=1:
        raise ValueError('逃生预案版本不支持')
    for k in ['plan_id','catalog_bundle_id']:text(packet[k],k,80)
    text(packet['notes'],'notes',1000,True)
    for k,value in [('mode','ACTIVE_ACTIVE'),('source','USER_DECLARED'),('target_scope_state','CANDIDATES_PENDING_CONFIRMATION'),('readiness','UNVERIFIED')]:
        if packet[k]!=value:raise ValueError('当前预案不支持该状态: '+k)
    if packet['automatic_switch'] is not False:raise ValueError('本入口禁止开启自动切换')
    groups={g['id']:g for g in catalog.get('pd-groups',[]) if g.get('enabled') is not False}
    for key in ['source_group_ids','target_group_ids']:
        ids=packet[key]
        if not isinstance(ids,list) or not 1<=len(ids)<=100 or any(not isinstance(i,str) or i not in groups for i in ids) or len(set(ids))!=len(ids):
            raise ValueError('预案关联组不存在、重复或为空: '+key)
    if set(packet['source_group_ids'])&set(packet['target_group_ids']):raise ValueError('逃生目标不可指向自身')
    scopes={(groups[i]['environment_code'],groups[i]['service_id']) for i in packet['source_group_ids']+packet['target_group_ids']}
    if len(scopes)!=1:raise ValueError('逃生预案不可跨环境或跨服务隐式关联')
    if any(not groups[i]['name'].endswith('-fallback') for i in packet['target_group_ids']):raise ValueError('当前预案仅允许明确命名的 fallback 候选组')
    out=deepcopy(packet);out['content_sha256']=digest(packet)
    out['service_id']=next(iter(scopes))[1];out['environment_code']=next(iter(scopes))[0]
    return out

def business_recovery(business, plans):
    groups=set(business.get('pd_group_ids',[]))
    eligible=[p for p in plans if groups.intersection(p['source_group_ids'])]
    targets=sorted({i for p in eligible for i in p['target_group_ids'] if i not in groups})
    is_receiver=any(groups.intersection(p['target_group_ids']) for p in plans)
    return {'configured':bool(targets),'role':'PROTECTED' if targets else 'FALLBACK_POOL' if is_receiver else 'UNCONFIGURED','plan_ids':[p['plan_id'] for p in eligible], 'target_group_ids':targets,'readiness':'UNVERIFIED','automatic_switch':False,'target_scope_state':'CANDIDATES_PENDING_CONFIRMATION'}

def attach_plans(catalog, plans):
    """Mutates the transport copy, never the directory model or source packet."""
    catalog['escape-plans']=plans
    for b in catalog.get('businesses',[]):b['recovery']=business_recovery(b,plans)
    return catalog
