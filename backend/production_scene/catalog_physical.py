"""Pure, deterministic screenshot-catalog compiler. No database or network access.
Blank runtime identity is not forward-filled. Namespace is part of deployment identity.
"""
from __future__ import annotations
import hashlib
import json
import re
import uuid
from copy import deepcopy

NS = uuid.UUID('985a5f86-0167-4bd7-a2d6-cb1c57e58121')
MAX_ROWS = 2000

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)

def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()

def identity(kind, *parts):
    return str(uuid.uuid5(NS, canonical([kind, *parts])))

def text(value, label, maximum=240, empty=False):
    if not isinstance(value, str) or value != value.strip() or (not value and not empty) or len(value)>maximum or any(ord(c)<32 for c in value):
        raise ValueError(f'{label}: 必须为首尾无空格的有效文本（最长 {maximum}）')
    return value

def compile_catalog(packet):
    if not isinstance(packet,dict) or (type(packet.get('schema_version')) is not int or packet.get('schema_version')!=1):
        raise ValueError('目录 schema_version 必须为整数 1')
    allowed={'schema_version','bundle_id','environment_code','source','rows'}
    if set(packet)-allowed: raise ValueError('目录包含未知顶层字段')
    bid=text(packet.get('bundle_id'),'bundle_id',80)
    if not re.fullmatch(r'[a-z0-9][a-z0-9._-]{0,79}',bid): raise ValueError('bundle_id 只能使用小写英文、数字、点、短横线、下划线')
    env=text(packet.get('environment_code'),'environment_code',80)
    if not isinstance(packet.get('source'),dict): raise ValueError('source 必须是对象')
    rows=packet.get('rows')
    if not isinstance(rows,list) or not 1<=len(rows)<=MAX_ROWS: raise ValueError('目录行数必须在 1–2000 之间')
    stores={key:{} for key in ['teams','businesses','models','clusters','services','pd-groups','endpoints','pods','business-pd-bindings','endpoint-pod-bindings']}
    issues=[]; source_rows=[]
    def put(kind,parts,**fields):
        ident=identity(kind,env,*parts)
        item={'id':ident,'code':'szg-'+kind[:8]+'-'+ident[:18], 'environment_code':env,'enabled':True,'origin':'REGISTERED',**fields}
        previous=stores[kind].get(ident)
        if previous and kind == 'pods':
            # One registered Pod may be referenced by both logical stages. Preserve
            # per-stage workload on Endpoint, never invent another Pod or node.
            check = [k for k in item if k not in {'workload_ref','workload_refs'}]
            if any(previous.get(k) != item.get(k) for k in check):
                raise ValueError('pods: 同一Pod身份的节点或其他字段冲突')
            refs = sorted(set(previous.get('workload_refs',[previous['workload_ref']]) + [item['workload_ref']]))
            item['workload_refs'] = refs
            item['workload_ref'] = refs[0]
            previous = None
        if previous and previous!=item: raise ValueError(f'{kind}: 同一身份字段冲突 {fields.get("name",ident)}')
        stores[kind][ident]=item
        return ident
    required={'critical','region','service_name','deployment_mode','model','cluster','namespace','team','business','pd_group','prefill','decode'}
    for i,raw in enumerate(rows,1):
        if not isinstance(raw,dict) or set(raw)!=required: raise ValueError(f'第 {i} 行字段必须完整且不能含未知字段')
        r=deepcopy(raw)
        for key in ['region','service_name','model','cluster','namespace','team','business','pd_group']:
            text(r[key],f'第 {i} 行 {key}',120 if key=='namespace' else 240)
        if type(r['critical']) is not bool or r['deployment_mode']!='SPLIT_PD': raise ValueError(f'第 {i} 行重要业务/部署模式无效')
        tid=put('teams',[r['team']],name=r['team'])
        busid=put('businesses',[r['team'],r['business']],name=r['business'],team_id=tid,critical=r['critical'],owner='待登记')
        mid=put('models',[r['model']],name=r['model'])
        cid=put('clusters',[r['cluster']],name=r['cluster'],region=r['region'])
        sid=put('services',[r['service_name'],mid],name=r['service_name'],model_id=mid,deployment_mode=r['deployment_mode'])
        gid=put('pd-groups',[sid,cid,r['namespace'],r['pd_group']],name=r['pd_group'],service_id=sid,cluster_id=cid,namespace=r['namespace'])
        put('business-pd-bindings',[busid,gid],business_id=busid,pd_group_id=gid,service_id=sid)
        row={'row':i,**r,'business_id':busid,'pd_group_id':gid}
        for key,role in [('prefill','PREFILL'),('decode','DECODE')]:
            part=r[key]
            if not isinstance(part,dict) or set(part)!={'workload_kind','workload','pod','node'}: raise ValueError(f'第 {i} 行 {key} 结构错误')
            if part['workload_kind'] not in {'LWS','Deployment'}: raise ValueError('工作负载类型必须为 LWS / Deployment')
            text(part['workload'],f'第 {i} 行 workload',160)
            for f in ['pod','node']: text(part[f],f'第 {i} 行 {f}',160,True)
            eid=identity('endpoints',env,gid,role,part['workload'])
            endpoint=stores['endpoints'].get(eid)
            if endpoint is None:
                eid=put('endpoints',[gid,role,part['workload']],name=part['workload']+' · '+('P' if role=='PREFILL' else 'D'),service_id=sid,cluster_id=cid,pd_group_id=gid,role=role,namespace=r['namespace'],workload_kind=part['workload_kind'],workload_ref=part['workload'],address_ref='',configured_nodes=[])
                endpoint=stores['endpoints'][eid]
            elif endpoint['workload_kind']!=part['workload_kind']: raise ValueError('同一工作负载类型冲突')
            if part['node'] and part['node'] not in endpoint['configured_nodes']: endpoint['configured_nodes'].append(part['node'])
            if part['pod']:
                pid=put('pods',[cid,r['namespace'],part['pod']],name=part['pod'],pod_name=part['pod'],cluster_id=cid,namespace=r['namespace'],workload_ref=part['workload'],node_name=part['node'],pod_uid=None,node_uid=None,observed_at=None,identity_state='REGISTERED_ONLY')
                put('endpoint-pod-bindings',[eid,pid],endpoint_id=eid,pod_id=pid)
            else:
                issues.append({'code':'POD_NOT_LISTED','row':i,'severity':'INFO','message':f'第 {i} 行 {role} Pod 未填写，保留为空；不补造副本。'})
            row[key+'_endpoint_id']=eid
        source_rows.append(row)
    for ep in stores['endpoints'].values(): ep['configured_nodes'].sort()
    for g in stores['pd-groups'].values():
        eps=[x for x in stores['endpoints'].values() if x['pd_group_id']==g['id']]
        sets={role:{b['pod_id'] for b in stores['endpoint-pod-bindings'].values() if b['endpoint_id'] in {x['id'] for x in eps if x['role']==role}} for role in ['PREFILL','DECODE']}
        same=sets['PREFILL'] & sets['DECODE']
        g['placement_state']='COLOCATED_REPORTED' if same else 'SEPARATE_REPORTED'
        g['placement_note']='P/D 指向同一 Pod；物理分离待确认' if same else 'P/D 为不同登记 Pod；非运行验证'
        if same: issues.append({'code':'SHARED_PD_POD','group_id':g['id'],'severity':'REVIEW','message':g['name']+' 的 P/D 同 Pod、同节点；保留原部署模式，禁止当作已验证物理分离。'})
        if 'dsv5flash' in g['namespace'] and 'dsv4flash' in g['name']:
            issues.append({'code':'NAMESPACE_LABEL_MISMATCH','group_id':g['id'],'severity':'REVIEW','message':'namespace 为 '+g['namespace']+'，组名为 '+g['name']+'；按截图分别保留，未自动改写。'})
    catalog={key:list(val.values()) for key,val in stores.items()}
    for n,b in enumerate(catalog['businesses'],1):
        b['watch_order']=n if b['critical'] else None
        b['service_ids']=sorted({x['service_id'] for x in catalog['business-pd-bindings'] if x['business_id']==b['id']})
        b['pd_group_ids']=[x['pd_group_id'] for x in catalog['business-pd-bindings'] if x['business_id']==b['id']]
    for ep in catalog['endpoints']:
        ep['pod_ids']=[b['pod_id'] for b in catalog['endpoint-pod-bindings'] if b['endpoint_id']==ep['id']]
    for s in catalog['services']:
        s['configured_businesses']=[{'id':b['id'],'name':b['name'],'pd_group_ids':b['pd_group_ids']} for b in catalog['businesses'] if s['id'] in b['service_ids']]
    nodes=sorted({p['node_name'] for p in catalog['pods'] if p['node_name']})
    counts={key:len(value) for key,value in catalog.items()}
    counts.update(workloads=len({(x['cluster_id'],x['namespace'],x['workload_kind'],x['workload_ref']) for x in catalog['endpoints']}),source_rows=len(rows),nodes=len(nodes),named_pd_groups=len({x['name'] for x in catalog['pd-groups']}),namespaces=len({x['namespace'] for x in catalog['pd-groups']}))
    return {'schema_version':1,'bundle_id':bid,'environment_code':env,'source_hash':digest(packet),'catalog':catalog,'source_rows':source_rows,'issues':issues,'counts':counts,'nodes':nodes}
