const {test}=require('node:test');
const assert=require('node:assert/strict');
const C=require('./directory-core.js');
test('完整示例的跨文件关联可以一起通过校验',()=>{
  const sample=C.examples(),batch=C.empty();
  for(const type of C.order)if(sample[type].length)batch[type]=C.decode(type,C.encode(type,sample[type],{localized:true}));
  const result=C.validateBatch(C.seed(),batch,{manual:true,imports:true});
  assert.equal(result.valid,true,JSON.stringify(result.results.filter(row=>row.issues.length)));
  assert.equal(result.additions,23);
});
test('CSV 支持 BOM、CRLF、带逗号/换行和转义引号的字段',()=>{
  const text='\uFEFFcode,name,environment\r\nteam-1,"研发,平台\n第二行 ""引号""",demo-local';
  const rows=C.decode('teams',text);
  assert.equal(rows[0].name,'研发,平台\n第二行 "引号"');assert.equal(rows[0]._line,2);
});
test('CSV 表头/行结构错误不静默丢列',()=>{
  assert.throws(()=>C.decode('teams','code,name,environment,unknown\na,A,demo-local,x'),/无法识别/);
  assert.throws(()=>C.decode('teams','code,name,environment\na,A,demo-local,x'),/第 2 行/);
  assert.throws(()=>C.decode('teams','code,name,environment\na,"A,demo-local'),/未闭合/);
  assert.throws(()=>C.decode('teams','code,稳定代码,name,environment\na,a,A,demo-local'),/重复字段/);
});
test('已存在和批次内重复代码均阻止整批通过，原目录保持不变',()=>{
  const db=C.seed(),before=JSON.stringify(db),batch=C.empty();
  batch.teams=[{code:'dev',name:'覆盖',environment:'demo-local'},{code:'new',name:'新增',environment:'demo-local'},{code:'new',name:'重复',environment:'demo-local'}];
  const result=C.validateBatch(db,batch);assert.equal(result.valid,false);assert.equal(JSON.stringify(db),before);
  assert.match(result.results[0].issues[0].message,/不会覆盖/);assert.match(result.results[2].issues[0].message,/重复记录/);
});
test('错误的资源引用和 P/D 归属不能通过',()=>{
  const batch=C.empty();batch.endpoints=[{code:'bad-ep',name:'错误实例',environment:'demo-local',service_code:'help-service',cluster_code:'missing',pd_group_code:'code-pd',role:'DECODE',address_ref:'demo-only:bad'}];
  const issues=C.validateBatch(C.seed(),batch).results[0].issues;
  assert.ok(issues.some(issue=>issue.message.includes('不存在')));assert.ok(issues.some(issue=>issue.message.includes('合并服务')));assert.ok(issues.some(issue=>issue.message.includes('同一服务')));
});
test('历史采集身份完整性校验仍要求真实 UID 与明确时区',()=>{
  const batch=C.empty();batch.runtimes=[{code:'partial-pod',name:'部分身份',environment:'demo-local',endpoint_code:'demo-coding-p',namespace:'demo',pod_name:'demo-pod',node_name:'demo-node',observed_at:'2026-10-03T10:00:00'}];
  const issues=C.validateBatch(C.seed(),batch).results[0].issues;
  assert.ok(issues.some(issue=>issue.field==='node_uid'));assert.ok(issues.some(issue=>issue.field==='pod_uid'));assert.ok(issues.some(issue=>issue.message.includes('时区')));
});
test('Key 团队归属和脱敏标签错误会被标出',()=>{
  const batch=C.empty();batch.keys=[{code:'bad-key',name:'错误 Key',environment:'demo-local',team_code:'dev',business_code:'help',external_key_ref:'demo-only:ref',masked_label:'not-masked',desired_status:'ACTIVE'}];
  const issues=C.validateBatch(C.seed(),batch).results[0].issues;
  assert.ok(issues.some(issue=>issue.field==='business_code'));assert.ok(issues.some(issue=>issue.field==='masked_label'));
});
test('没有业务依赖或模型授权时，映射保留待补录信息',()=>{
  const db=C.seed();db.dependencies=[];const first=C.mappings(db)[0];
  assert.equal(first.dependency,'待补录');assert.equal(first.authorization,'已配置');assert.equal(first.effective_status,'NOT_CONNECTED');
  db.dependencies=[{business_code:'coding',service_code:'code-service'}];db.grants=[];
  const mapping=C.mappings(db).find(row=>row.service==='代码辅助推理');assert.equal(mapping.dependency,'已配置');assert.equal(mapping.authorization,'待补录');
});
test('逐步录入重复保存只复用完全相同的记录，不覆盖改名记录',()=>{
  const db=C.seed(),batch=C.empty();batch.teams=[{...db.teams[0]}];
  assert.equal(C.validateBatch(db,batch,{reuseIdentical:true}).valid,true);
  batch.teams[0].name='改名';assert.equal(C.validateBatch(db,batch,{reuseIdentical:true}).valid,false);
});
test('编辑资源更新映射，保留稳定身份且不就地改写原目录',()=>{
  const db=C.seed(),row=db.endpoints[0],before=JSON.stringify(db);
  const result=C.prepareUpdate(db,'endpoints',row.code,{address_ref:'demo-only:edited'},row);
  assert.equal(result.ok,true,result.message);assert.equal(JSON.stringify(db),before);
  assert.ok(C.mappings(result.candidate).some(item=>item.address==='demo-only:edited'));
  assert.equal(result.row.code,row.code);assert.equal(result.row._version,1);
});
test('修改父资源不能使已有部署或团队引用失效',()=>{
  const db=C.seed(),service=db.services.find(row=>row.deployment_mode==='SPLIT_PD');
  const result=C.prepareUpdate(db,'services',service.code,{deployment_mode:'COMBINED'},service);
  assert.equal(result.ok,false);assert.match(result.message,/合并服务/);
  const business=db.businesses.find(row=>row.code==='coding');
  assert.equal(C.prepareUpdate(db,'businesses',business.code,{team_code:'support'},business).ok,false);
});
test('编辑拒绝稳定代码变更、陈旧快照和重复关系',()=>{
  const db=C.seed(),row=db.teams[0];
  assert.equal(C.prepareUpdate(db,'teams',row.code,{code:'other'},row).ok,false);
  const old={...row};row.name='其他页面修改';
  assert.equal(C.prepareUpdate(db,'teams',row.code,{name:'覆盖'},old).ok,false);
  const relation=db.dependencies[0],other=db.dependencies[1];
  assert.equal(C.prepareUpdate(db,'dependencies',C.identity('dependencies',relation),other,relation).ok,false);
});
test('新导入记录可省略 ID 并生成稳定 UUID，保留旧表头兼容',()=>{
  const text='显示名称,环境\n新增环境团队,PRD';
  const row=C.decode('teams',text)[0];assert.match(row.code,/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);assert.equal(C.decode('teams',text)[0].code,row.code);
  const legacy=C.decode('teams','稳定代码,显示名称,环境\nlegacy,旧数据,demo-local')[0];assert.equal(legacy._import_key,'legacy');assert.ok(C.isUuid(legacy.code));
});
test('支持四种环境与 LWS/Deployment，保留环境一致性校验',()=>{
  for(const env of C.environments){const batch=C.empty();batch.teams=[{code:C.newId(),name:'团队',environment:env}];assert.equal(C.validateBatch(C.empty(),batch).valid,true);}
  const db=C.seed(),batch=C.empty();batch.runtimes=[{...db.runtimes[0],code:C.newId(),workload_kind:'LWS'}];assert.equal(C.validateBatch(db,batch).valid,true);
  batch.runtimes[0].workload_kind='Deployment';assert.equal(C.validateBatch(db,batch).valid,true);
  batch.runtimes[0].environment='PRD';assert.equal(C.validateBatch(db,batch).valid,false);
  batch.runtimes[0].environment='DEV';batch.runtimes[0].workload_kind='Invalid';assert.equal(C.validateBatch(db,batch).valid,false);
});
test('整项服务修改原子保存并保留其他服务、授权和多运行成员',()=>{
  const db=C.seed(),before=JSON.stringify(db),batch=C.empty(),sid='code-service';
  batch.services=[{...db.services[0],name:'改名服务'}];batch.pdgroups=db.pdgroups.filter(row=>row.service_code===sid);batch.endpoints=db.endpoints.filter(row=>row.service_code===sid);
  batch.endpoints=batch.endpoints.map(row=>({...row,namespace:'inference',workload_kind:'LWS',workload_ref:'inference-p',configured_nodes:['node-1','node-2']}));batch.dependencies=[db.dependencies[0]];
  const result=C.prepareServiceUpdate(db,sid,batch,JSON.parse(before),'coding');assert.equal(result.ok,true,result.message);assert.equal(JSON.stringify(db),before);assert.equal(result.candidate.services.find(row=>row.code===sid).name,'改名服务');assert.deepEqual(result.candidate.grants,db.grants);assert.equal(result.candidate.runtimes.length,db.runtimes.length);
  batch.endpoints=[{...batch.endpoints[0],cluster_code:'missing'}];assert.equal(C.prepareServiceUpdate(db,sid,batch,JSON.parse(before),'coding').ok,false);assert.equal(JSON.stringify(db),before);
});
test('整项修改允许合并服务带 Router；拒绝陈旧整项目录快照',()=>{
  const db=C.seed(),expected=structuredClone(db),batch=C.empty(),sid='code-service';
  batch.services=[{...db.services[0],deployment_mode:'COMBINED'}];batch.endpoints=db.endpoints.filter(row=>row.service_code===sid).map((row,i)=>({...row,role:i?'ROUTER':'COMBINED',pd_group_code:''}));batch.dependencies=[db.dependencies[0]];
  assert.equal(C.prepareServiceUpdate(db,sid,batch,expected,'coding').ok,true);
  db.teams[0].name='其他页面修改';assert.equal(C.prepareServiceUpdate(db,sid,batch,expected,'coding').ok,false);
});
test('实例地址接受 HTTP/HTTPS URL，拒绝含密码或不明格式',()=>{
  assert.equal(C.isAddress('http://prefill.inference.svc:8000'),true);assert.equal(C.isAddress('https://10.0.1.20:8443'),true);assert.equal(C.isAddress('10.0.1.20'),false);assert.equal(C.isAddress('https://user:secret@example.invalid'),false);
});

function serviceBatch(db,sid='code-service'){
  const batch=C.empty();batch.services=db.services.filter(row=>row.code===sid);batch.pdgroups=db.pdgroups.filter(row=>row.service_code===sid);batch.endpoints=db.endpoints.filter(row=>row.service_code===sid);batch.dependencies=db.dependencies.filter(row=>row.service_code===sid);return structuredClone(batch);
}
test('配置 Node 单独保存，多节点不制造 Pod，校验重复和空名称',()=>{
  const db=C.seed(),batch=serviceBatch(db);batch.endpoints[0].configured_nodes=['worker-a','worker-b'];batch.endpoints[0].namespace='inference';batch.endpoints[0].workload_kind='Deployment';
  const result=C.prepareServiceUpdate(db,'code-service',batch,structuredClone(db),'coding');assert.equal(result.ok,true,result.message);assert.deepEqual(result.candidate.runtimes,db.runtimes);assert.deepEqual(result.candidate.endpoints.find(row=>row.code===batch.endpoints[0].code).configured_nodes,['worker-a','worker-b']);
  const ep=C.mappings(result.candidate).find(row=>row.endpoint_code===batch.endpoints[0].code);assert.deepEqual(ep.configured_nodes,['worker-a','worker-b']);assert.equal(ep.observed_node,'');
  batch.endpoints[0].configured_nodes=['worker-a',' worker-a '];assert.equal(C.prepareServiceUpdate(db,'code-service',batch,structuredClone(db),'coding').ok,false);
  batch.endpoints[0].configured_nodes=[''];assert.equal(C.prepareServiceUpdate(db,'code-service',batch,structuredClone(db),'coding').ok,false);
});
test('服务保存深等保留全部真实旧观测和元数据，不只保留数量',()=>{
  const db=C.seed(),ep=db.endpoints[0];Object.assign(db.runtimes[0],{pod_uid:'real-pod-uid',node_uid:'real-node-uid',node_name:'observed-worker',observed_at:'2026-10-08T10:00:00+08:00',_source:'真实历史采集',_custom:'保留'});
  db.runtimes.push({...db.runtimes[0],code:'second-real-pod',pod_name:'second-pod',pod_uid:'second-uid',observed_at:'2026-10-08T11:00:00+08:00'});
  const before=structuredClone(db),batch=serviceBatch(db);batch.services[0].name='配置改名';batch.endpoints[0].configured_nodes=['configured-worker'];
  const result=C.prepareServiceUpdate(db,'code-service',batch,before,'coding');assert.equal(result.ok,true,result.message);assert.deepEqual(result.candidate.runtimes,before.runtimes);assert.deepEqual(result.candidate.grants,before.grants);assert.deepEqual(db,before);
  const mapping=C.mappings(result.candidate).find(row=>row.runtime_code===before.runtimes[0].code);assert.equal(mapping.observed_node,'observed-worker');assert.deepEqual(mapping.configured_nodes,['configured-worker']);
});
test('移除实例保留历史采集与退休引用，无历史的配置不退休',()=>{
  const db=C.seed(),before=structuredClone(db),batch=serviceBatch(db);batch.endpoints=[batch.endpoints[1]];
  const result=C.prepareServiceUpdate(db,'code-service',batch,before,'coding');assert.equal(result.ok,true,result.message);assert.deepEqual(result.candidate.runtimes,before.runtimes);assert.equal(result.candidate.retired_endpoints.length,1);assert.equal(result.candidate.retired_endpoints[0].code,before.endpoints[0].code);assert.ok(C.validateBatch(C.empty(),result.candidate).valid);assert.ok(!C.mappings(result.candidate).some(row=>row.endpoint_code===before.endpoints[0].code));
  const back=serviceBatch(result.candidate);back.endpoints.unshift({...before.endpoints[0],configured_nodes:['worker-back']});const restored=C.prepareServiceUpdate(result.candidate,'code-service',back,structuredClone(result.candidate),'coding');assert.equal(restored.ok,true,restored.message);assert.equal(restored.candidate.retired_endpoints.length,0);assert.deepEqual(restored.candidate.runtimes,before.runtimes);
  db.runtimes=db.runtimes.filter(row=>row.endpoint_code!==before.endpoints[0].code);assert.equal(C.prepareServiceUpdate(db,'code-service',batch,structuredClone(db),'coding').candidate.retired_endpoints.length,0);
});
test('模式切换保留旧 P/D 和全部 runtime，历史组独立于当前配置',()=>{
  const db=C.seed(),batch=serviceBatch(db);batch.services[0].deployment_mode='COMBINED';batch.pdgroups=[];batch.endpoints=[{...db.endpoints[0],code:C.newId(),name:'合并新配置',role:'COMBINED',pd_group_code:'',configured_nodes:['worker-c']}];
  const result=C.prepareServiceUpdate(db,'code-service',batch,structuredClone(db),'coding');assert.equal(result.ok,true,result.message);assert.deepEqual(result.candidate.runtimes,db.runtimes);assert.equal(result.candidate.retired_endpoints.length,2);assert.equal(result.candidate.retired_pdgroups.length,1);assert.ok(C.mappings(result.candidate).filter(row=>row.service_code==='code-service').every(row=>row.pod==='未采集'));assert.ok(C.validateBatch(C.empty(),result.candidate).valid);
});
test('保存层拒绝隐藏采样载荷和 runtime 修改',()=>{
  const db=C.seed(),batch=serviceBatch(db);batch.runtimes=[{...db.runtimes[0]}];assert.equal(C.prepareServiceUpdate(db,'code-service',batch,structuredClone(db),'coding').ok,false);
  batch.runtimes=[];batch.endpoints[0].pod_uid='forged';assert.equal(C.prepareServiceUpdate(db,'code-service',batch,structuredClone(db),'coding').ok,false);
  assert.equal(C.prepareUpdate(db,'runtimes',db.runtimes[0].code,{pod_uid:'forged'},db.runtimes[0]).ok,false);
  assert.equal(C.prepareUpdate(db,'endpoints',db.endpoints[0].code,{node_uid:'forged'},db.endpoints[0]).ok,false);
  const manual=C.empty();manual.runtimes=[db.runtimes[0]];assert.equal(C.validateBatch(db,manual,{manual:true}).valid,false);
});
test('CSV 模板不提供系统 ID/采样输入，UUID 与采样非空明确拒绝',()=>{
  assert.ok(!C.importOrder.includes('runtimes'));assert.ok(C.encode('endpoints',[],{forImport:true}).startsWith('import_key,name,environment'));assert.ok(!C.encode('endpoints',[],{forImport:true}).includes('pod_uid'));
  assert.throws(()=>C.decode('teams','code,name,environment\n'+C.newId()+',团队,DEV'),/UUID/);
  assert.throws(()=>C.decode('runtimes','code,name\npod,x'),/只读/);
  assert.throws(()=>C.decode('endpoints','name,environment,service_code,cluster_code,role,address_ref,pod_name\nx,DEV,s,c,COMBINED,http://example.invalid,pod-a'),/采集端/);
  assert.equal(C.decode('endpoints','name,environment,service_code,cluster_code,role,address_ref,pod_uid\nx,DEV,s,c,COMBINED,http://example.invalid,')[0].pod_uid,undefined);
});
test('CSV 名称引用、导入别名、Node 数组往返与歧义拒绝',()=>{
  const db=C.seed(),batch=C.empty();batch.endpoints=C.decode('endpoints','import_key,name,environment,service_code,cluster_code,role,address_ref,configured_nodes\nep-a,新配置,DEV,name:客服问答推理,name:华东智算集群,COMBINED,http://example.invalid,"[""worker-01"",""worker-02""]"');
  let check=C.validateBatch(db,batch,{manual:true,imports:true});assert.equal(check.valid,true,JSON.stringify(check.results));assert.equal(check.results[0].row.service_code,'help-service');assert.deepEqual(check.results[0].row.configured_nodes,['worker-01','worker-02']);
  const encoded=C.encode('endpoints',batch.endpoints,{forImport:true});assert.deepEqual(C.decode('endpoints',encoded)[0].configured_nodes,['worker-01','worker-02']);
  db.clusters.push({...db.clusters[1],code:'duplicate-name'});check=C.validateBatch(db,batch,{manual:true,imports:true});assert.equal(check.valid,false);assert.match(check.results[0].issues.map(issue=>issue.message).join(','),/不唯一/);
});
test('历史导出保留真实 UID 和系统 ID，配置与观测字段分离',()=>{
  const db=C.seed();Object.assign(db.runtimes[0],{pod_uid:'actual-uid',node_uid:'actual-node',node_name:'actual-node-name',observed_at:'2026-10-08T10:00:00Z'});db.endpoints[0].configured_nodes=['configured-node'];
  const csv=C.encode('runtimes',[db.runtimes[0]]);assert.ok(csv.includes('actual-uid'));assert.ok(csv.includes(db.runtimes[0].code));const mappings=C.mappings(db);assert.equal(mappings[0].observed_node,'actual-node-name');assert.deepEqual(mappings[0].configured_nodes,['configured-node']);assert.equal(mappings[0].effective_status,'NOT_CONNECTED');assert.ok(!C.inputFields('runtimes').length);
});

const fs=require('node:fs'),vm=require('node:vm');
function demoContext(stored={}){
  const storage=new Map(Object.entries(stored)),elements=new Map(),listeners={};
  const element=()=>({hidden:false,innerHTML:'',textContent:'',value:'',dataset:{},classList:{toggle(){},add(){},remove(){}},setAttribute(){},removeAttribute(){},focus(){},scrollIntoView(){},closest(){return null;},querySelector(){return element();},showModal(){this.open=true;},close(){this.open=false;}});
  const query=selector=>{if(selector==='[aria-invalid="true"]')return null;if(!elements.has(selector))elements.set(selector,element());return elements.get(selector);};
  const context={GatewayDirectoryCore:C,GatewayRecordEditor:{canLeave:()=>true},document:{querySelector:query,querySelectorAll:()=>[],body:element(),addEventListener(type,listener){(listeners['document:'+type]||=[]).push(listener);}},localStorage:{getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value)},URL,URLSearchParams,crypto:globalThis.crypto,structuredClone,Date,console,location:{href:'http://127.0.0.1:8790/?mode=directory',search:'?mode=directory'},history:{replaceState(){}},CustomEvent:class{constructor(type){this.type=type;}},confirm:()=>true,setTimeout(){},scrollTo(){},addEventListener(type,listener){(listeners[type]||=[]).push(listener);},dispatchEvent(event){for(const listener of listeners[event.type]||[])listener(event);}};
  context.window=context;vm.createContext(context);return {context,storage,elements,listeners};
}
test('真实脚本链路：旧草稿保存只提交配置，新建与通用编辑保留退休集合和旧 runtime',()=>{
  const original=C.seed(),removed=serviceBatch(original);removed.endpoints=[removed.endpoints[1]];const retired=C.prepareServiceUpdate(original,'code-service',removed,structuredClone(original),'coding').candidate;
  const draft={step:0,completed:false,data:{environment:'DEV',serviceMode:'new',serviceName:'兼容旧草稿服务',deployment:'COMBINED',routerEnabled:false,teamMode:'existing',teamId:'dev',businessMode:'existing',businessId:'coding',modelMode:'existing',modelId:'coder',keyMode:'later',endpoints:[{code:C.newId(),role:'COMBINED',name:'配置实例',cluster:'southwest',address:'http://example.invalid:8000'}],runtimes:[{namespace:'inference',workload:'workload-a',workloadKind:'Deployment',podName:'stale-pod',podUid:'stale-uid',nodeName:'stale-node',nodeUid:'stale-node-uid',observedAt:'2026-10-08T10:00:00Z',configuredNodes:['configured-1','configured-2']}]} };
  const demo=demoContext({'gateway.entry-flow.directory.v1':JSON.stringify({schema:1,revision:7,revisions:[],db:retired}),'gateway.entry-flow.prototype.v1':JSON.stringify({schema:1,state:draft})});
  vm.runInContext(fs.readFileSync(require.resolve('./directory.js'),'utf8'),demo.context);vm.runInContext(fs.readFileSync(require.resolve('./app.js'),'utf8'),demo.context);
  const rendered=demo.elements.get('#form-content').innerHTML;assert.ok(rendered.includes('配置 Node / 部署范围'));assert.ok(!/data-field="[^"]*(podName|podUid|nodeUid|observedAt)"/.test(rendered));
  demo.elements.get('#flow-form').onsubmit({preventDefault(){}});
  const saved=JSON.parse(demo.storage.get('gateway.entry-flow.directory.v1'));assert.equal(saved.revision,8);assert.deepEqual(saved.db.runtimes,retired.runtimes);assert.deepEqual(saved.db.retired_endpoints,retired.retired_endpoints);assert.deepEqual(saved.db.retired_pdgroups,retired.retired_pdgroups);
  const ep=saved.db.endpoints.find(row=>row.name==='配置实例');assert.ok(ep);assert.deepEqual(ep.configured_nodes,['configured-1','configured-2']);assert.equal(ep.pod_name,undefined);
  const savedDraft=JSON.parse(demo.storage.get('gateway.entry-flow.prototype.v1'));assert.equal(savedDraft.state.data.runtimes[0].podUid,undefined);assert.equal(savedDraft.state.data.runtimes[0].nodeName,undefined);
  const row=saved.db.teams[0],update=C.prepareUpdate(saved.db,'teams',row.code,{name:'新团队名称'},row);assert.equal(update.ok,true,update.message);assert.deepEqual(update.candidate.retired_endpoints,retired.retired_endpoints);assert.deepEqual(update.candidate.runtimes,retired.runtimes);
});
test('真实 CSV UI 管线：修正不接收隐藏 UUID，重复编译与整批保存身份稳定',()=>{
  const demo=demoContext();demo.context.FormData=class{constructor(form){this.values=form.values;}[Symbol.iterator](){return Object.entries(this.values)[Symbol.iterator]();}};
  vm.runInContext(fs.readFileSync(require.resolve('./directory.js'),'utf8'),demo.context);
  const click=(id,dataset={})=>{const button={id,dataset,hasAttribute:()=>false};for(const listener of demo.listeners['document:click'])listener({target:{closest:()=>button}});};
  demo.context.GatewayEntryDirectory.open('batch');click('batch-example');click('validate-batch');click('',{batchType:'teams'});click('',{editBatch:'0'});
  const dialog=demo.elements.get('#record-dialog').innerHTML;assert.ok(!dialog.includes('name="code"'));assert.ok(dialog.includes('name="import_key"'));
  for(const listener of demo.listeners['document:submit'])listener({preventDefault(){},target:{id:'detail-form',values:{import_key:'batch-1-a-team',name:'修正后团队',environment:'demo-local',code:'forged-system-code'}}});
  click('validate-batch');const ids=[...demo.elements.get('#manager').innerHTML.matchAll(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/g)].map(match=>match[0]);assert.ok(ids.length>0);
  click('validate-batch');click('commit-batch');const saved=JSON.parse(demo.storage.get('gateway.entry-flow.directory.v1'));assert.ok(saved);const teams=saved.db.teams.filter(row=>row._source==='批量 CSV');assert.equal(teams.length,2);assert.ok(teams.some(row=>row.name==='修正后团队'));assert.ok(teams.every(row=>C.isUuid(row.code)&&ids.includes(row.code)));assert.ok(!JSON.stringify(saved.db).includes('forged-system-code'));assert.equal(saved.db.runtimes.length,C.seed().runtimes.length);assert.ok(saved.db.endpoints.filter(row=>row._source==='批量 CSV').every(row=>row.configured_nodes.length===2));
});
test('外部 Key 字符串引用完整保留，不能随机生成替代凭据',()=>{
  const db=C.seed(),batch=C.empty(),external='external-credential-'+C.newId();batch.keys=C.decode('keys',`import_key,name,environment,team_code,business_code,external_key_ref,masked_label,desired_status\nkey-a,已有外部引用,DEV,name:研发效能团队,name:代码研发助手,${external},demo-••••-actual,ACTIVE`);
  const check=C.validateBatch(db,batch,{manual:true,imports:true});assert.equal(check.valid,true,JSON.stringify(check.results));assert.equal(check.results[0].row.external_key_ref,external);assert.ok(C.isUuid(check.results[0].row.code));assert.notEqual(check.results[0].row.code,external);
});
