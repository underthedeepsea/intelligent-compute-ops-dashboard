(function(root){
  'use strict';
  const F=(key,label,required=false,extra={})=>({key,label,required,...extra});
  const base=[F('code','稳定代码',true),F('name','显示名称',true),F('environment','环境',true)];
  const schemas={
    teams:{label:'团队',fields:[...base]},
    businesses:{label:'业务',fields:[...base,F('team_code','所属团队代码',true,{ref:'teams'}),F('owner','负责人',true)]},
    models:{label:'模型',fields:[...base]},
    clusters:{label:'集群',fields:[...base,F('region','区域')]},
    services:{label:'推理服务',fields:[...base,F('model_code','模型代码',true,{ref:'models'}),F('deployment_mode','部署模式',true,{values:['SPLIT_PD','COMBINED']})]},
    pdgroups:{label:'P/D 组',fields:[...base,F('service_code','服务代码',true,{ref:'services'})]},
    endpoints:{label:'Endpoint',fields:[...base,F('service_code','服务代码',true,{ref:'services'}),F('cluster_code','集群代码',true,{ref:'clusters'}),F('pd_group_code','P/D 组代码',false,{ref:'pdgroups'}),F('role','角色',true,{values:['PREFILL','DECODE','ROUTER','COMBINED']}),F('address_ref','地址引用',true),F('namespace','Namespace'),F('workload_kind','部署方式',false,{values:['LWS','Deployment']}),F('workload_ref','工作负载名称'),F('configured_nodes','配置 Node / 部署范围',false,{array:true})]},
    runtimes:{label:'Pod / Node 历史记录',fields:[...base,F('endpoint_code','Endpoint 代码',true,{ref:'endpoints'}),F('namespace','Pod 命名空间',true),F('pod_name','Pod 名称',true),F('workload_ref','工作负载名称'),F('workload_kind','部署方式',false,{values:['LWS','Deployment']}),F('pod_uid','Pod UID'),F('node_name','Node 名称'),F('node_uid','Node UID'),F('observed_at','实际观测时间')]},
    keys:{label:'Key 引用',fields:[...base,F('team_code','团队代码',true,{ref:'teams'}),F('business_code','业务代码',false,{ref:'businesses'}),F('external_key_ref','外部引用 ID',true),F('masked_label','脱敏标签',true),F('desired_status','配置意图',true,{values:['ACTIVE','SUSPENDED']})]},
    dependencies:{label:'业务服务依赖',fields:[F('business_code','业务代码',true,{ref:'businesses'}),F('service_code','服务代码',true,{ref:'services'})]},
    grants:{label:'Key 模型授权',fields:[F('key_code','Key 代码',true,{ref:'keys'}),F('model_code','模型代码',true,{ref:'models'})]}
  };
  const environments=['PRD','DR','STG','DEV'];
  const environmentCode=value=>value==='demo-local'?'DEV':value;
  const newId=()=>globalThis.crypto.randomUUID();
  const isAddress=value=>{try{const url=new URL(value);return ['http:','https:'].includes(url.protocol)&&!!url.hostname&&!url.username&&!url.password;}catch{return false;}};
  const labels={code:'记录 ID',service_code:'所属推理服务',cluster_code:'部署集群',pd_group_code:'部署分组',role:'实例职责',address_ref:'实例访问地址',model_code:'使用模型',endpoint_code:'所属实例',team_code:'所属团队',business_code:'所属业务',key_code:'Key 引用'};
  for(const [type,schema] of Object.entries(schemas))schema.fields=schema.fields.map(field=>({...field,aliases:field.key==='workload_ref'?[field.label,'工作负载引用']:[field.label],label:field.key==='name'?(type==='services'?'推理服务名':type==='endpoints'?'实例名称':field.label):(labels[field.key]||field.label)}));
  const generatedImportIds=new Map();
  const order=Object.keys(schemas);
  const empty=()=>Object.fromEntries(order.map(type=>[type,[]]));
  const identity=(type,row)=>row.code||[row.business_code||row.key_code,row.service_code||row.model_code].join(' → ');
  const isUuid=value=>/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(String(value));
  const importOrder=order.filter(type=>type!=='runtimes');
  const inputFields=type=>schemas[type].fields.filter(field=>field.key!=='code'&&type!=='runtimes');
  const displayValue=value=>Array.isArray(value)?value.join('、'):String(value??'');
  const cloneDb=db=>({...structuredClone(db),retired_endpoints:structuredClone(db.retired_endpoints||[]),retired_pdgroups:structuredClone(db.retired_pdgroups||[])});
  function nodeList(value){if(Array.isArray(value))return value.map(item=>String(item).trim());if(!value)return [];try{const parsed=JSON.parse(value);return Array.isArray(parsed)?parsed.map(item=>String(item).trim()):[String(value).trim()];}catch{return [String(value).trim()];}}
  function normalize(type,row){return Object.fromEntries(schemas[type].fields.map(field=>[field.key,field.array?nodeList(row[field.key]):String(row[field.key]??'').trim()]));}
  function forbiddenInput(type,row){return type==='runtimes'||['pod_name','pod_uid','node_name','node_uid','observed_at','podName','podUid','nodeName','nodeUid','observedAt','runtime_member'].some(key=>row[key]!==undefined&&row[key]!==''&&row[key]!==null);}
  function resolveImports(db,batch){
    const result=empty(),errors=[];
    for(const type of order)result[type]=(batch[type]||[]).map(row=>({...row}));
    for(const type of order)for(const row of result[type])for(const field of schemas[type].fields.filter(item=>item.ref)){
      const value=row[field.key];if(!value)continue;
      const imported=result[field.ref].filter(item=>item._import_key===value);
      const existing=db[field.ref].filter(item=>item.code===value||('name:'+item.name===value||item.name===value)&&(!row.environment||environmentCode(item.environment)===environmentCode(row.environment)));
      const matches=imported.length?imported:existing;
      if(matches.length!==1)errors.push({type,row,field:field.key,message:field.label+'引用'+(matches.length?'不唯一':'不存在')+'：'+value});
      else row[field.key]=matches[0].code;
    }
    return {batch:result,errors};
  }
  function seed(){
    const db=empty(),env='demo-local';
    db.teams=[{code:'dev',name:'研发效能团队',environment:env},{code:'support',name:'智能客服团队',environment:env}];
    db.businesses=[{code:'coding',name:'代码研发助手',environment:env,team_code:'dev',owner:'研发平台（示例）'},{code:'help',name:'客户服务助手',environment:env,team_code:'support',owner:'客服平台（示例）'}];
    db.models=[{code:'coder',name:'Qwen3-Coder-30B',environment:env},{code:'qwen',name:'Qwen3-32B',environment:env}];
    db.clusters=[{code:'southwest',name:'西南智算集群',environment:env,region:'西南'},{code:'east',name:'华东智算集群',environment:env,region:'华东'}];
    db.services=[{code:'code-service',name:'代码辅助推理',environment:env,model_code:'coder',deployment_mode:'SPLIT_PD'},{code:'help-service',name:'客服问答推理',environment:env,model_code:'qwen',deployment_mode:'COMBINED'}];
    db.pdgroups=[{code:'code-pd',name:'代码推理 P/D 组',environment:env,service_code:'code-service'}];
    db.endpoints=[{code:'demo-coding-p',name:'代码推理 · P',service_code:'code-service',cluster_code:'southwest',pd_group_code:'code-pd',role:'PREFILL',address_ref:'demo-only:coding:p',environment:env},{code:'demo-coding-d',name:'代码推理 · D',service_code:'code-service',cluster_code:'southwest',pd_group_code:'code-pd',role:'DECODE',address_ref:'demo-only:coding:d',environment:env},{code:'demo-help-c',name:'客服推理 · 合并',service_code:'help-service',cluster_code:'east',role:'COMBINED',address_ref:'demo-only:help:c',environment:env}];
    db.runtimes=db.endpoints.map(row=>({code:row.code+'-pod',name:row.name+' Pod',environment:env,endpoint_code:row.code,namespace:'demo-inference',pod_name:row.code+'-0',workload_ref:'statefulset/'+row.code}));
    db.keys=[{code:'coding-ref',name:'研发助手调用引用',environment:env,team_code:'dev',business_code:'coding',external_key_ref:'demo-only:external:0003',masked_label:'demo-••••-0003',desired_status:'ACTIVE'},{code:'support-ref',name:'客服调用引用',environment:env,team_code:'support',business_code:'help',external_key_ref:'demo-only:external:0001',masked_label:'demo-••••-0001',desired_status:'ACTIVE'}];
    db.dependencies=[{business_code:'coding',service_code:'code-service'},{business_code:'help',service_code:'help-service'}];
    db.grants=[{key_code:'coding-ref',model_code:'coder'},{key_code:'support-ref',model_code:'qwen'}];
    return Object.fromEntries(order.map(type=>[type,db[type].map(row=>({...normalize(type,row),_source:'合成示例'}))]));
  }
  function examples(batchPrefix='batch'){
    const db=empty(),env='demo-local';
    ['a','b'].forEach((suffix,index)=>{
      const prefix=batchPrefix+'-'+suffix,label=index===0?'研发知识检索':'工单问答助手';
      db.teams.push({code:prefix+'-team',name:label+'团队',environment:env});
      db.businesses.push({code:prefix+'-business',name:label,environment:env,team_code:prefix+'-team',owner:'示例负责人'});
      db.models.push({code:prefix+'-model',name:index===0?'示例知识模型':'示例问答模型',environment:env});
      db.services.push({code:prefix+'-service',name:label+'推理',environment:env,model_code:prefix+'-model',deployment_mode:'SPLIT_PD'});
      db.pdgroups.push({code:prefix+'-pd',name:label+' P/D 组',environment:env,service_code:prefix+'-service'});
      ['p','d1','d2'].forEach((role,i)=>{
        const code=prefix+'-'+role;
        db.endpoints.push({code,name:label+' · '+role.toUpperCase(),environment:env,service_code:prefix+'-service',cluster_code:index===0?'southwest':'east',pd_group_code:prefix+'-pd',role:i===0?'PREFILL':'DECODE',address_ref:'demo-only:'+prefix+':'+role,namespace:'demo-inference',workload_kind:'LWS',workload_ref:code,configured_nodes:['demo-node-'+suffix+'-1','demo-node-'+suffix+'-2']});
      });
      db.keys.push({code:prefix+'-key',name:label+'调用引用',environment:env,team_code:prefix+'-team',business_code:prefix+'-business',external_key_ref:'demo-only:'+prefix+':external',masked_label:'demo-••••-batch-'+suffix,desired_status:'ACTIVE'});
      db.dependencies.push({business_code:prefix+'-business',service_code:prefix+'-service'});
      db.grants.push({key_code:prefix+'-key',model_code:prefix+'-model'});
    });
    db.clusters=[{code:batchPrefix+'-cluster',name:'新增演示集群',environment:env,region:'演示区域'}];
    return db;
  }
  function parseCSV(text){
    if(text.length>2*1024*1024)throw Error('CSV 超过 2 MB，请拆分为较小批次。');
    text=text.replace(/^\uFEFF/,'');const rows=[];let row=[],cell='',quoted=false,afterQuote=false,line=1,rowLine=1;
    const pushCell=()=>{row.push(cell);cell='';afterQuote=false;};
    const pushRow=()=>{pushCell();if(row.some(v=>v.trim()))rows.push({cells:row,line:rowLine});row=[];rowLine=line+1;};
    for(let i=0;i<text.length;i++){
      const char=text[i];
      if(quoted){if(char==='"'){if(text[i+1]==='"'){cell+='"';i++;}else{quoted=false;afterQuote=true;}}else{cell+=char;if(char==='\n')line++;}continue;}
      if(afterQuote&&char!==','&&char!=='\n'&&char!=='\r')throw Error(`第 ${line} 行：引号结束后应为逗号或换行。`);
      if(char==='"'){if(cell)throw Error(`第 ${line} 行：引号应放在字段开头。`);quoted=true;}
      else if(char===',')pushCell();
      else if(char==='\n'){pushRow();line++;}
      else if(char==='\r'){if(text[i+1]==='\n')i++;pushRow();line++;}
      else cell+=char;
    }
    if(quoted)throw Error('CSV 的双引号未闭合。');if(cell||row.length||afterQuote)pushRow();
    if(!rows.length)throw Error('请粘贴或选择含表头的 CSV。');if(rows.length>5001)throw Error('每个文件最多 5000 条数据，请拆分批次。');return rows;
  }
  function decode(type,text){
    if(type==='runtimes')throw Error('Pod / Node 历史记录只读，不接受人工导入。请登记实例配置。');
    const raw=parseCSV(text),schema=schemas[type];
    const names=raw[0].cells.map(value=>value.trim());
    const keys=names.map(name=>name==='import_key'||name==='导入标识'?'import_key':schema.fields.find(field=>field.key===name||field.label===name||field.aliases?.includes(name))?.key||(['pod_name','pod_uid','node_name','node_uid','observed_at'].includes(name)?name:null));
    const unknown=names.filter((_,i)=>!keys[i]);if(unknown.length)throw Error('无法识别表头：'+unknown.join('、')+'。请使用本类型的模板。');
    if(new Set(keys).size!==keys.length)throw Error('表头中存在重复字段。');
    const missing=schema.fields.filter(field=>field.required&&field.key!=='code'&&!keys.includes(field.key));if(missing.length)throw Error('缺少必填列：'+missing.map(field=>field.label).join('、'));
    const cacheKey=type+'\0'+text;if(!generatedImportIds.has(cacheKey)){if(generatedImportIds.size>=32)generatedImportIds.delete(generatedImportIds.keys().next().value);generatedImportIds.set(cacheKey,new Map());}const ids=generatedImportIds.get(cacheKey);
    return raw.slice(1).map(item=>{
      if(item.cells.length!==keys.length)throw Error(`第 ${item.line} 行有 ${item.cells.length} 列，表头为 ${keys.length} 列。`);
      const input=Object.fromEntries(keys.map((key,i)=>[key,item.cells[i].trim()]));
      if(forbiddenInput(type,input))throw Error(`第 ${item.line} 行：Pod 名、UID、观测 Node 和采样时间由采集端维护，不能人工录入。`);
      if(isUuid(input.code)||isUuid(input.import_key)||schema.fields.some(field=>field.ref&&isUuid(input[field.key])))throw Error(`第 ${item.line} 行：系统 UUID 不能人工输入，请使用导入标识或资源名称引用。`);
      if(!ids.has(item.line))ids.set(item.line,newId());
      const row=normalize(type,{...input,code:ids.get(item.line)});
      if(keys.includes('configured_nodes')&&input.configured_nodes){let nodes;try{nodes=JSON.parse(input.configured_nodes);}catch{}if(!Array.isArray(nodes)||nodes.some(node=>typeof node!=='string'))throw Error(`第 ${item.line} 行：配置 Node 请填写 JSON 字符串数组。`);}
      return {...row,_import_key:input.import_key||input.code||'',_line:item.line};
    });
  }
  function encode(type,rows,{localized=false,forImport=false}={}){
    const quote=value=>{let text=Array.isArray(value)?JSON.stringify(value):String(value??'');if(/^[=+@\t\r]/.test(text))text="'"+text;return /[,"\r\n]/.test(text)?'"'+text.replaceAll('"','""')+'"':text;};
    const fields=forImport?[F('import_key','导入标识'),...inputFields(type)]:schemas[type].fields;
    const keys=fields.map(field=>field.key);
    return [(localized?fields.map(field=>field.label):keys).join(','),...rows.map(row=>keys.map(key=>quote(key==='import_key'?row._import_key!==undefined?row._import_key:row.code:row[key])).join(','))].join('\r\n');
  }
  function validateBatch(db,batch,{reuseIdentical=false,manual=false,imports=false}={}){
    let importErrors=[];if(imports){const resolved=resolveImports(db,batch);batch=resolved.batch;importErrors=resolved.errors;}
    const candidate=cloneDb(db);if(!manual){candidate.retired_endpoints=structuredClone(batch.retired_endpoints||candidate.retired_endpoints);candidate.retired_pdgroups=structuredClone(batch.retired_pdgroups||candidate.retired_pdgroups);}const results=[];
    for(const type of order){const seen=new Set();(batch[type]||[]).forEach((input,index)=>{
      const row=normalize(type,input),id=identity(type,row),issues=[];let reused=false;
      if(type==='endpoints'&&input.configured_nodes!==undefined&&input.configured_nodes!==''){let nodes=input.configured_nodes;if(typeof nodes==='string')try{nodes=JSON.parse(nodes);}catch{}if(!Array.isArray(nodes)||nodes.some(node=>typeof node!=='string'))issues.push({field:'configured_nodes',message:'配置 Node 必须是名称字符串数组'});}
      if(manual&&forbiddenInput(type,input))issues.push({field:'code',message:'采集记录与身份不能通过配置录入修改'});
      if(input._import_key&&(batch[type]||[]).filter(other=>other._import_key===input._import_key).length>1)issues.push({field:'import_key',message:'导入标识重复：'+input._import_key});
      for(const error of importErrors)if(error.type===type&&error.row===input)issues.push({field:error.field,message:error.message});
      for(const field of schemas[type].fields){if(field.required&&!row[field.key])issues.push({field:field.key,message:field.label+'必填'});if(field.values&&row[field.key]&&!field.values.includes(row[field.key]))issues.push({field:field.key,message:field.label+'应为 '+field.values.join(' / ')});}
      if(row.code&&!/^[a-zA-Z0-9_-]+$/.test(row.code))issues.push({field:'code',message:'稳定代码只能使用字母、数字、短横线和下划线'});
      if(row.environment&&!environments.includes(environmentCode(row.environment)))issues.push({field:'environment',message:'环境请选择 PRD / DR / STG / DEV'});
      if(seen.has(id))issues.push({field:'code',message:'同一批次出现重复记录：'+id});seen.add(id);
      const existing=db[type].find(item=>identity(type,item)===id);
      if(existing){reused=reuseIdentical&&schemas[type].fields.every(field=>JSON.stringify(existing[field.key]??(field.array?[]:''))===JSON.stringify(row[field.key]));if(!reused)issues.push({field:'code',message:'目录已有此代码或关系，本批次不会覆盖：'+id});}
      if(!existing)candidate[type].push(row);
      results.push({type,index,line:input._line||index+2,row,id,issues,reused,importKey:input._import_key});
    });}
    for(const result of results){const {type,row,issues}=result,add=(field,message)=>issues.push({field,message});
      const refs=[];for(const field of schemas[type].fields){if(!field.ref||!row[field.key])continue;const parent=[...candidate[field.ref],...(type==='runtimes'&&field.ref==='endpoints'?candidate.retired_endpoints:[])].find(item=>item.code===row[field.key]);if(!parent)add(field.key,field.label+'不存在：'+row[field.key]);else{refs.push(parent);if(row.environment&&environmentCode(parent.environment)!==environmentCode(row.environment))add(field.key,'关联资源必须处于同一环境');}}
      if(!row.environment&&new Set(refs.map(ref=>environmentCode(ref.environment))).size>1)add('environment','关系两端必须处于同一环境');
      if(type==='pdgroups'){const service=candidate.services.find(s=>s.code===row.service_code);if(service&&service.deployment_mode!=='SPLIT_PD')add('service_code','P/D 组只能归属 P/D 分离服务');}
      if(type==='endpoints'){
        if(row.configured_nodes.some(node=>!node))add('configured_nodes','配置 Node 名称不能为空');
        if(new Set(row.configured_nodes).size!==row.configured_nodes.length)add('configured_nodes','同一实例的配置 Node 不能重复');
        if(row.address_ref&&!row.address_ref.startsWith('demo-only:')&&!isAddress(row.address_ref))add('address_ref','实例访问地址请填写 http:// 或 https:// 开头的主机/IP 与端口，不能包含账号密码');
        const service=candidate.services.find(s=>s.code===row.service_code),group=candidate.pdgroups.find(g=>g.code===row.pd_group_code);
        if(service?.deployment_mode==='COMBINED'&&(!['COMBINED','ROUTER'].includes(row.role)||row.pd_group_code))add('role','合并服务只允许 COMBINED / ROUTER 且不关联 P/D 组');
        if(service?.deployment_mode==='SPLIT_PD'&&(row.role==='COMBINED'||!row.pd_group_code))add('pd_group_code','分离服务需要 P/D 组，角色不能是 COMBINED');
        if(group&&group.service_code!==row.service_code)add('pd_group_code','P/D 组必须属于同一服务');
      }
      if(type==='runtimes'){
        if(row.node_name||row.node_uid){for(const field of ['node_name','node_uid','pod_uid','observed_at'])if(!row[field])add(field,'Node 身份需要 Node 名称、Node UID、Pod UID、观测时间成组填写');}
        if(row.observed_at&&(!/^\d{4}-\d\d-\d\dT\d\d:\d\d(?::\d\d(?:\.\d+)?)?(?:Z|[+-]\d\d:\d\d)$/.test(row.observed_at)||!Number.isFinite(Date.parse(row.observed_at))))add('observed_at','观测时间需要有效 ISO 8601 时间及明确时区');
      }
      if(type==='keys'){
        const business=candidate.businesses.find(b=>b.code===row.business_code);
        if(business&&business.team_code!==row.team_code)add('business_code','业务必须属于当前团队');
        if(row.masked_label&&!/[•*]/.test(row.masked_label))add('masked_label','脱敏标签必须包含 • 或 *，不要输入原始密钥');
      }
    }
    const additions=results.filter(result=>!result.reused).length;
    return {results,valid:results.length>0&&results.every(result=>!result.issues.length),additions,reused:results.length-additions,candidate};
  }
  function prepareUpdate(db,type,id,changes,expected,expectedService){
    const fail=message=>({ok:false,message});
    if(!schemas[type])return fail('无法识别资源类型。');
    const index=db[type].findIndex(row=>identity(type,row)===id),current=db[type][index];
    if(!current)return fail('此记录已不存在，请返回目录刷新。');
    if(JSON.stringify(current)!==JSON.stringify(expected))return fail('此记录已在其他页面更新。请重新打开编辑页后再修改，当前输入尚未保存。');
    if(type==='runtimes')return fail('Pod / Node 历史记录只读，请编辑所属服务的部署配置。');
    if(forbiddenInput(type,changes))return fail('Pod 名与采集身份不能通过配置编辑修改。');
    const replacement={...current,...normalize(type,{...current,...changes})};
    if(current.code!==replacement.code)return fail('记录 ID 不可修改。');
    const candidate=cloneDb(db);
    candidate[type][index]=replacement;
    let service;
    if(type==='endpoints'&&changes.service_name!==undefined){
      const target=candidate.services.find(row=>row.code===current.service_code);
      const original=db.services.find(row=>row.code===current.service_code);
      if(!target||JSON.stringify(original)!==JSON.stringify(expectedService))return fail('所属推理服务已在其他页面修改，请重新打开编辑页。');
      target.name=String(changes.service_name).trim();
      if(target.name!==original.name){target._version=(Number(original._version)||0)+1;target._updated_at=new Date().toLocaleString('zh-CN');}
      service=target;
    }
    // Check the entire resulting graph, including records which reference this one.
    const check=validateBatch(empty(),candidate);
    const problems=check.results.filter(row=>row.issues.length);
    if(problems.length)return {ok:false,message:problems.flatMap(row=>row.issues.map(issue=>`${schemas[row.type].label} · ${row.id}：${issue.message}`)).join('；'),issues:problems};
    replacement._version=(Number(current._version)||0)+1;
    return {ok:true,candidate,row:replacement,service};
  }
  function prepareServiceUpdate(db,serviceId,batch,expected,previousBusiness){
    if(JSON.stringify(db)!==JSON.stringify(expected))return {ok:false,message:'目录已在其他页面变化，请保存草稿后重新打开服务编辑页。'};
    if(!db.services.some(row=>row.code===serviceId))return {ok:false,message:'此推理服务已不存在。'};
    const oldEndpoints=new Set(db.endpoints.filter(row=>row.service_code===serviceId).map(row=>row.code));
    const nextEndpoints=new Set(batch.endpoints.map(row=>row.code));
    if((batch.runtimes||[]).length||order.some(type=>(batch[type]||[]).some(row=>forbiddenInput(type,row))))return {ok:false,message:'配置保存不能提交 Pod 或采集身份。'};
    const base=cloneDb(db);
    const retired=base.retired_endpoints;
    for(const ep of db.endpoints.filter(row=>oldEndpoints.has(row.code)&&!nextEndpoints.has(row.code)))if(db.runtimes.some(row=>row.endpoint_code===ep.code)&&!retired.some(row=>row.code===ep.code))retired.push(structuredClone(ep));
    base.retired_endpoints=retired.filter(row=>!nextEndpoints.has(row.code));
    const nextGroups=new Set(batch.pdgroups.map(row=>row.code));
    for(const group of db.pdgroups.filter(row=>row.service_code===serviceId&&!nextGroups.has(row.code)))if(base.retired_endpoints.some(ep=>ep.pd_group_code===group.code)&&!base.retired_pdgroups.some(row=>row.code===group.code))base.retired_pdgroups.push(structuredClone(group));
    base.retired_pdgroups=base.retired_pdgroups.filter(row=>!nextGroups.has(row.code));
    for(const type of order)base[type]=db[type].filter(row=>{
      if(type==='services')return row.code!==serviceId;
      if(type==='pdgroups'||type==='endpoints')return row.service_code!==serviceId;
      if(type==='dependencies')return !(row.service_code===serviceId&&row.business_code===previousBusiness);
      return true;
    }).map(row=>structuredClone(row));
    const check=validateBatch(base,batch,{reuseIdentical:true});
    if(!check.valid)return {ok:false,message:check.results.flatMap(row=>row.issues.map(issue=>schemas[row.type].label+'：'+issue.message)).join('；')};
    const candidate=cloneDb(base);
    for(const entry of check.results)if(!entry.reused){const prior=db[entry.type].find(row=>identity(entry.type,row)===entry.id);candidate[entry.type].push({...prior,...entry.row,_source:prior?prior._source:'直接录入',_version:(Number(prior?._version)||0)+1,_updated_at:new Date().toLocaleString('zh-CN')});}
    const graph=validateBatch(empty(),candidate);if(!graph.valid)return {ok:false,message:graph.results.flatMap(row=>row.issues.map(issue=>schemas[row.type].label+'：'+issue.message)).join('；')};
    return {ok:true,candidate};
  }
  function mappings(db){
    const rows=[];
    // Traverse configured business dependencies and Key model grants independently.
    for(const service of db.services){
      const model=db.models.find(item=>item.code===service.model_code);
      const dependencies=db.dependencies.filter(item=>item.service_code===service.code);
      const authorizedKeys=db.keys.filter(key=>db.grants.some(grant=>grant.key_code===key.code&&grant.model_code===service.model_code));
      const contexts=authorizedKeys.map(key=>({key,business:db.businesses.find(b=>b.code===key.business_code),team:db.teams.find(t=>t.code===key.team_code),dependency:dependencies.some(dep=>dep.business_code===key.business_code)}));
      for(const dep of dependencies)if(!contexts.some(context=>context.business?.code===dep.business_code)){
        const business=db.businesses.find(b=>b.code===dep.business_code);
        contexts.push({key:null,business,team:db.teams.find(t=>t.code===business?.team_code),dependency:true});
      }
      if(!contexts.length)contexts.push({key:null,business:null,team:null,dependency:false});
      for(const context of contexts){const {business,team}=context;
        const keys=context.key?[context.key]:[];
        const endpoints=db.endpoints.filter(ep=>ep.service_code===service.code);
        for(const key of keys.length?keys:[null])for(const ep of endpoints.length?endpoints:[null]){
          const runtimeRows=ep?db.runtimes.filter(row=>row.endpoint_code===ep.code):[];
          for(const runtime of runtimeRows.length?runtimeRows:[null]){
            const cluster=ep&&db.clusters.find(item=>item.code===ep.cluster_code);
            rows.push({team:team?.name||'归属待补录',business:business?.name||'依赖待补录',key:key?.masked_label||'授权待补录',key_code:key?.code||'',key_name:key?.name||'',desired_status:key?.desired_status||'',team_code:team?.code||'',business_code:business?.code||'',model_code:model?.code||'',cluster_code:cluster?.code||'',runtime_code:runtime?.code||'',namespace:ep?.namespace||runtime?.namespace||'',configured_nodes:ep?.configured_nodes||[],observed_node:runtime?.node_name||'',observed_at:runtime?.observed_at||'',observation_source:runtime?._source||'',pd_group_code:ep?.pd_group_code||'',service_code:service.code,endpoint_code:ep?.code||'',model:model?.name||'模型待补录',service:service.name,endpoint:ep?.name||'实例待补录',address:ep?.address_ref||'—',role:ep?.role||'—',pod:runtime?.pod_name||'未采集',cluster:cluster?.name||'—',node:runtime?.node_name||'',environment:service.environment,dependency:context.dependency?'已配置':'待补录',authorization:key?'已配置':'待补录',effective_status:'NOT_CONNECTED'});
          }
        }
      }
    }
    return rows;
  }
  const api={isUuid,inputFields,importOrder,displayValue,cloneDb,nodeList,forbiddenInput,resolveImports,newId,environments,environmentCode,isAddress,schemas,order,empty,identity,normalize,seed,examples,parseCSV,decode,encode,validateBatch,prepareUpdate,prepareServiceUpdate,mappings};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.GatewayDirectoryCore=api;
})(typeof window!=='undefined'?window:globalThis);
