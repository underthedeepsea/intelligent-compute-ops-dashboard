(() => {
  'use strict';
  const C=GatewayDirectoryCore,KEY='gateway.entry-flow.directory.v1';
  const $=selector=>document.querySelector(selector);
  const esc=value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  let revisions=[],db=C.seed(),revision=0,mode='wizard',batchType='endpoints',listType='endpoints',listView='mapping',query='',sourceFilter='all',page=1,overviewTeam='',overviewCluster='',overviewIntent='';
  let csvTexts={},preview=null,fileErrors=[],flash='',detail=null,storageWarning='',previewPage=1;
  const pageSize=15;
  let entryMethod='wizard',editTarget=null,editReturn=null;
  function load(){try{storageWarning='';const stored=JSON.parse(localStorage.getItem(KEY)||'null');if(stored){if(stored.schema!==1||!C.order.every(type=>Array.isArray(stored.db?.[type])))throw Error('格式不兼容');db=C.cloneDb(stored.db);revision=stored.revision||0;revisions=stored.revisions||[];}}catch{storageWarning='浏览器目录无法读取，当前暂用合成示例；保存前请导出需要保留的数据。';}}
  load();
  function catalog(){const result={};for(const type of ['teams','businesses','models','services','clusters','keys'])result[type]=db[type].map(row=>({id:row.code,name:row.name,environment:C.environmentCode(row.environment),team:row.team_code,business:row.business_code,model:row.model_code,deployment:row.deployment_mode,masked:row.masked_label}));return result;}
  function persist(batch,source,reuseIdentical=false){
    load();if(storageWarning)return {ok:false,message:storageWarning};
    const check=C.validateBatch(db,batch,{reuseIdentical,manual:true,imports:source==='批量 CSV'});
    if(!check.valid)return {ok:false,message:check.results.flatMap(row=>row.issues.map(issue=>`${C.schemas[row.type].label} · ${row.id}：${issue.message}`)).slice(0,4).join('；')||'本批次没有可保存的记录。',check};
    const next=C.cloneDb(db);
    const time=new Date().toLocaleString('zh-CN');
    for(const row of check.results)if(!row.reused)next[row.type].push({...row.row,_source:source,_recorded_at:time});
    try{localStorage.setItem(KEY,JSON.stringify({schema:1,revision:revision+1,revisions,db:next}));}catch{return {ok:false,message:'浏览器无法保存目录。本批次未提交，输入仍保留，请导出后再尝试。'};}
    db=next;revision++;window.dispatchEvent(new CustomEvent('demo-directory-change'));
    return {ok:true,added:check.additions,reused:check.reused};
  }
  function wizardBatch(result){
    const batch=C.empty(),env=result.environment;
    batch.clusters=(result.new_clusters||[]).map(row=>({...row,environment:env}));
    for(const [kind,type] of [['team','teams'],['business','businesses'],['model','models'],['service','services']])if(result[kind].mode==='new'){
      const row={code:result[kind].reference,name:result[kind].name,environment:env};
      if(kind==='business')Object.assign(row,{team_code:result.team.reference,owner:result.business.owner});
      if(kind==='service')Object.assign(row,{model_code:result.model.reference,deployment_mode:result.service.deployment});
      batch[type].push(row);
    }
    for(const group of result.pd_groups||(result.pd_group?[result.pd_group]:[]))batch.pdgroups.push({...group,environment:env,service_code:result.service.reference});
    result.endpoints.forEach(row=>{
      batch.endpoints.push({code:row.code,name:row.name,environment:env,service_code:result.service.reference,cluster_code:row.cluster.id,pd_group_code:result.service.deployment==='SPLIT_PD'?(row.pd_group_code||result.pd_group?.code||''):'',role:row.role,address_ref:row.address_ref,namespace:row.namespace,workload_kind:row.workload_kind,workload_ref:row.workload_ref,configured_nodes:row.configured_nodes});
      if(C.forbiddenInput('endpoints',row))batch.runtimes.push({}); // Core rejects legacy/manual sampling payloads.
    });
    if(result.key?.code)batch.keys.push({code:result.key.code,name:result.key.name,environment:env,team_code:result.team.reference,business_code:result.business.reference,external_key_ref:result.key.reference,masked_label:result.key.masked_label,desired_status:result.key.desired_status});
    batch.dependencies.push({business_code:result.business.reference,service_code:result.service.reference});
    if(result.key&&result.configured_relationships.key_model_authorization)batch.grants.push({key_code:result.key.code||result.key.reference,model_code:result.model.reference});
    return batch;
  }
  function commitWizard(result){return persist(wizardBatch(result),'直接录入',true);}
  function commitService(result,edit){
    load();if(storageWarning)return {ok:false,message:storageWarning};
    const prepared=C.prepareServiceUpdate(db,edit.serviceId,wizardBatch(result),edit.expected,edit.previousBusiness);if(!prepared.ok)return prepared;
    const nextHistory=[...revisions,{revision,savedAt:new Date().toISOString(),db}];
    try{localStorage.setItem(KEY,JSON.stringify({schema:1,revision:revision+1,revisions:nextHistory,db:prepared.candidate}));}catch{return {ok:false,message:'保存失败，输入已保留，目录未改变。'};}
    revisions=nextHistory;db=prepared.candidate;revision++;window.dispatchEvent(new CustomEvent('demo-directory-change'));return {ok:true};
  }
  function serviceContext(serviceId){return {serviceId,expected:JSON.parse(JSON.stringify(db)),previousBusiness:db.dependencies.find(row=>row.service_code===serviceId)?.business_code||''};}

  window.GatewayEntryDirectory={catalog,commitWizard,commitService,serviceContext,edit:openEdit,open:(next='directory')=>{if(next==='directory')listView='mapping';setMode(next);},prepareLeave:()=>true};
  function options(value,importing=false){return (importing?C.importOrder:C.order).map(type=>`<option value="${type}" ${type===value?'selected':''}>${C.schemas[type].label}</option>`).join('');}
  function message(text,error=false){flash=text;const target=$('#manager-message');if(target){target.textContent=text;target.hidden=!text;target.classList.toggle('failure',error);}}
  function setMode(next){
    if(!['wizard','batch','directory','edit'].includes(next))return false;
    if(mode==='edit'&&next!=='edit'&&!GatewayRecordEditor.canLeave())return false;
    if(mode==='wizard'&&next!=='wizard')GatewayEntryDirectory.prepareLeave();
    if(next!==mode&&/暂存|移出/.test(flash))flash='';
    if(next==='batch'&&mode==='directory'&&listView==='resources')batchType=C.importOrder.includes(listType)?listType:'endpoints';
    mode=next;
    const entering=next==='wizard'||next==='batch';if(entering)entryMethod=next;
    $('#entry-header').hidden=!entering;$('#entry-session-tools').hidden=next!=='wizard';
    document.querySelectorAll('[data-entry-method]').forEach(button=>{const selected=button.dataset.entryMethod===next;button.setAttribute('aria-selected',String(selected));button.classList.toggle('selected',selected);});
    $('#manager').classList.toggle('original-directory',next==='directory');$('#wizard').hidden=next!=='wizard';$('#manager').hidden=!['batch','directory'].includes(next);$('#record-editor').hidden=next!=='edit';
    if(next==='batch'){$('#manager').setAttribute('role','tabpanel');$('#manager').setAttribute('aria-labelledby','tab-batch');}else{$('#manager').removeAttribute('role');$('#manager').removeAttribute('aria-labelledby');}
    updateConsole();
    const url=new URL(location.href);url.searchParams.set('mode',next);url.searchParams.delete('type');url.searchParams.delete('view');url.searchParams.delete('record');url.searchParams.delete('service');
    if(next==='directory'&&listView==='resources'){url.searchParams.set('view','resources');url.searchParams.set('type',listType);}
    if(next==='edit'&&editTarget){url.searchParams.set('type',editTarget.type);url.searchParams.set('record',editTarget.id);}history.replaceState(null,'',url);
    if(next==='edit')$('#editor-title')?.focus({preventScroll:true});
    else if(next!=='wizard'){render();$('#manager-title').focus({preventScroll:true});}
    else window.dispatchEvent(new CustomEvent('demo-directory-change'));
    window.scrollTo({top:0,left:0,behavior:'instant'});return true;
  }
  function updateConsole(){
    const view=mode==='directory'?(listView==='mapping'?'overview':listType==='keys'?'keys':'resources'):mode==='edit'?(editTarget?.type==='keys'?'keys':'resources'):'entry';
    document.querySelectorAll('.console-nav-item').forEach(button=>{const active=(button.dataset.consoleView||(button.hasAttribute('data-entry-open')?'entry':''))===view;button.classList.toggle('selected',active);if(active)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');});
    $('#console-location').textContent=mode==='edit'?'资源与关系目录 / 编辑'+C.schemas[editTarget.type].label:mode==='wizard'?'资源录入 / 直接录入':mode==='batch'?'资源录入 / 批量导入':{overview:'网关总览',resources:'资源与关系目录',keys:'API Key 目录'}[view];
    document.body.dataset.consoleMode=mode;
  }
  function openEdit(type,id){
    if(!C.schemas[type])return;
    if(type==='runtimes'){const runtime=db.runtimes.find(row=>row.code===id);if(runtime)openDetail(type,runtime);return;}
    if(['services','endpoints'].includes(type)){const serviceId=type==='services'?id:db.endpoints.find(row=>row.code===id)?.service_code;if(!serviceId)return;if(!setMode('wizard'))return;if(GatewayEntryDirectory.editService)GatewayEntryDirectory.editService(serviceContext(serviceId));else GatewayEntryDirectory.pendingServiceId=serviceId;return;}
    if(mode==='edit'&&!GatewayRecordEditor.canLeave())return;
    const row=db[type].find(item=>C.identity(type,item)===id);if(!row)return;
    editReturn={listType,listView,query,sourceFilter,page,overviewTeam,overviewCluster,overviewIntent};
    if(mode!=='directory')editReturn={...editReturn,listType:type,listView:'resources',query:'',sourceFilter:'all',page:1};
    editTarget={type,id,saved:false};
    if($('#record-dialog').open)$('#record-dialog').close();
    GatewayRecordEditor.show({type,row,db,onSave:saveEdit,onCancel:returnFromEdit});setMode('edit');
  }
  function saveEdit(changes,expected,expectedService){
    load();if(storageWarning)return {ok:false,message:storageWarning};
    const result=C.prepareUpdate(db,editTarget.type,editTarget.id,changes,expected,expectedService);if(!result.ok)return result;
    result.row._updated_at=new Date().toLocaleString('zh-CN');
    try{localStorage.setItem(KEY,JSON.stringify({schema:1,revision:revision+1,revisions,db:result.candidate}));}catch{return {ok:false,message:'浏览器无法保存，本次修改尚未提交，输入已保留。'};}
    db=result.candidate;revision++;editTarget.id=C.identity(editTarget.type,result.row);editTarget.saved=true;
    const url=new URL(location.href);url.searchParams.set('record',editTarget.id);history.replaceState(null,'',url);
    window.dispatchEvent(new CustomEvent('demo-directory-change'));return result;
  }
  function returnFromEdit(){
    if(editTarget.saved){listType=editTarget.type;listView='resources';query=editTarget.id;sourceFilter='all';page=1;flash='修改已保存，已定位到这条记录。';}
    else ({listType,listView,query,sourceFilter,page,overviewTeam,overviewCluster,overviewIntent}=editReturn);
    setMode('directory');
  }
  function openResource(type){listView='resources';listType=type;query='';sourceFilter='all';page=1;setMode('directory');}
  function overviewSummary(){
    const metrics=[['teams','团队','已登记团队'],['keys','API Key','外部引用 · 配置意图'],['models','模型','已登记模型'],['endpoints','Endpoint','已登记服务实例'],['runtimes','运行成员',`${db.clusters.length} 个集群 · 登记信息`]];
    return `<section class="console-metrics" aria-label="目录资源统计">${metrics.map(([type,label,caption],index)=>`<button type="button" class="console-metric ${index===0?'accent':''}" data-open-resource="${type}"><small>${label}</small><strong>${db[type].length}</strong><span>${caption}</span></button>`).join('')}</section><section class="panel console-chain-panel"><div class="panel-head"><div><h2>统一主数据链路</h2><p>查看已登记资源及配置关系，选择对象进入对应目录。</p></div><button type="button" class="button small" data-entry-open>录入资源 ↗</button></div><div class="console-chain">${[['teams','Team'],['businesses','Business'],['keys','API Key'],['models','Model'],['services','Service'],['pdgroups','P/D Group'],['clusters','Cluster']].map(([type,en],index)=>`<button type="button" class="console-chain-card" data-open-resource="${type}"><span>${String(index+1).padStart(2,'0')} · ${en}</span><b>${C.schemas[type].label}</b><em>${db[type].length} 个已登记</em></button>`).join('')}</div></section>`;
  }
  function render(){
    if(mode==='wizard'||mode==='edit')return;
    updateConsole();
    const isBatch=mode==='batch';
    $('#manager').innerHTML=`<div class="manager-heading"><div><h1 tabindex="-1" id="manager-title">${isBatch?'批量导入':listView==='mapping'?'AI 网关资源关系总览':listType==='keys'?'API Key 目录':'资源与关系目录'}</h1><p class="muted">${isBatch?'使用表格准备多条资源和关系，先校验，再保存整个批次。':listView==='mapping'?'团队、业务、授权模型与实际登记的部署关系':'查看、修改已保存资源及其关联信息。'}</p></div><div class="manager-actions">${!isBatch?`<button class="button" type="button" data-list-view="${listView==='mapping'?'resources':'mapping'}">${listView==='mapping'?'资源完整字段':'返回网关总览'}</button>`:''}${!isBatch?'<button class="button primary" type="button" data-new-entry>＋ 录入资源</button>':''}<button class="button" type="button" ${isBatch?'data-entry-records':'data-mode="batch"'}>${isBatch?'查看已录入记录':'批量导入'}</button></div></div><div id="manager-message" role="status" class="notice ${storageWarning?'failure':''}" ${flash||storageWarning?'':'hidden'}>${esc(flash||storageWarning)}</div>${isBatch?batchView():directoryView()}`;
  }
  function batchView(){
    const staged=C.order.filter(type=>csvTexts[type]?.trim());
    return `<div class="import-path"><span>1 准备 CSV</span><b>→</b><span>2 校验与修正</span><b>→</b><span>3 保存本批次</span><b>→</b><button type="button" data-entry-records>录入目录</button></div><section class="section batch-setup"><div class="batch-toolbar"><div class="field"><label for="batch-type">当前资源类型</label><select id="batch-type">${options(batchType,true)}</select></div><div class="batch-tools"><button class="button small" id="download-template" type="button">下载当前类型模板</button><button class="button small" id="choose-files" type="button">选择 CSV 文件</button><button class="button small" id="batch-example" type="button">载入完整批量示例</button><input id="csv-files" type="file" accept=".csv,text/csv" multiple hidden></div></div><p class="hint">记录 UUID 由系统生成。跨文件用导入标识（如 team-a）关联；已有资源填写 name:资源名称，须在类型和环境内唯一。只新增，不覆盖已有记录。Pod 与采集 UID 不接受人工导入。</p><details class="format-help"><summary>文件命名、字段要求与导入顺序</summary><p>单个 CSV 使用上方选中的类型；一次选择多个文件时，文件名用 <code>teams.csv</code>、<code>businesses.csv</code> 等类型名。下载模板时已使用对应名称。</p><p>可以同时导入全部类型，校验会检查同一批次内的关联。环境填写 <code>PRD / DR / STG / DEV</code>。旧模板和 demo-local 历史数据继续兼容。旧表头继续识别；旧采集列仅空值兼容。配置 Node 列填写 JSON 字符串数组，例如 ["worker-01","worker-02"]。</p><div class="schema-reference">${[{key:'import_key',label:'导入标识'},...C.inputFields(batchType)].map(field=>`<span><code>${field.key}</code> · ${field.label}${field.required?' <b>必填</b>':' <small>可选</small>'}</span>`).join('')}</div></details><div class="staged-types" aria-label="本批次文件">${staged.map(type=>`<button type="button" data-batch-type="${type}" class="${type===batchType?'selected':''}">${C.schemas[type].label} <small>已暂存</small></button>`).join('')||'<small>尚未暂存文件，可先载入完整示例体验。</small>'}</div><label class="csv-label" for="csv-text">${C.schemas[batchType].label} CSV · 可直接粘贴并修改</label><textarea id="csv-text" spellcheck="false" placeholder="先下载模板填写，或载入完整示例">${esc(csvTexts[batchType]||'')}</textarea><div class="batch-bottom"><span class="hint">文件在本页暂存，点击校验前不保存到目录。</span><div><button class="text-button" type="button" id="clear-current" ${csvTexts[batchType]?'':'disabled'}>移出当前文件</button><button class="button primary" id="validate-batch" type="button">校验整个批次</button></div></div></section><div id="batch-preview">${previewHTML()}</div>`;
  }
  function previewHTML(){
    if(!preview&&!fileErrors.length)return '';
    if(fileErrors.length)return `<section class="section"><h2>文件需要修正</h2><ul class="import-errors">${fileErrors.map(error=>`<li>${esc(error)}</li>`).join('')}</ul><p class="hint">当前暂存内容仍保留，修正 CSV 后重新校验。</p></section>`;
    const failed=preview.results.filter(row=>row.issues.length),validCount=preview.results.length-failed.length;
    const matching=preview.results.filter(row=>row.type===batchType);previewPage=Math.min(previewPage,Math.max(1,Math.ceil(matching.length/pageSize)));
    const display=matching.slice((previewPage-1)*pageSize,previewPage*pageSize);
    return `<section class="section"><div class="section-heading"><div><h2 id="validation-title" tabindex="-1">提交前校验</h2><small>${preview.results.length} 条记录 · ${validCount} 条通过 · ${failed.length} 条需要修正</small></div><span class="validation-badge ${failed.length?'invalid':'valid'}">${failed.length?'整批尚未提交':'整批可保存'}</span></div><div class="validation-types">${C.order.filter(type=>preview.results.some(row=>row.type===type)).map(type=>{const rows=preview.results.filter(row=>row.type===type),fail=rows.filter(row=>row.issues.length).length;return `<button type="button" data-batch-type="${type}" class="${type===batchType?'selected':''}">${C.schemas[type].label} ${rows.length}${fail?` <b>${fail} 条错误</b>`:''}</button>`;}).join('')}</div><div class="table-wrap"><table class="directory-table"><thead><tr><th>CSV 行</th><th>代码 / 关系</th><th>名称</th><th>校验结果</th><th></th></tr></thead><tbody>${display.map(row=>`<tr><td>${row.line}</td><td class="mono">${esc(row.id)}</td><td>${esc(row.row.name||'配置关系')}</td><td>${row.issues.length?`<span class="error-text">${row.issues.map(issue=>esc(issue.message)).join('<br>')}</span>`:'<span class="valid-text">通过</span>'}</td><td><button type="button" class="text-button" data-edit-batch="${row.index}">查看 / 修正</button></td></tr>`).join('')||'<tr><td colspan="5" class="empty">当前类型没有待导入记录，选择上方已暂存类型查看。</td></tr>'}</tbody></table></div><div class="pagination"><span>当前类型第 ${previewPage} / ${Math.max(1,Math.ceil(matching.length/pageSize))} 页</span><div><button type="button" class="button small" id="preview-prev" ${previewPage===1?'disabled':''}>上一页</button><button type="button" class="button small" id="preview-next" ${previewPage*pageSize>=matching.length?'disabled':''}>下一页</button></div></div><div class="batch-bottom"><p class="hint">${failed.length?'修正全部错误后才能保存。不会只导入部分行。':'资源和关系一起保存到此浏览器的演示目录。'}</p><button class="button primary" id="commit-batch" type="button" ${preview.valid?'':'disabled'}>保存整个批次 · ${preview.results.length} 条</button></div></section>`;
  }
  function focusPreview(){const heading=$('#batch-preview h2');if(heading){heading.tabIndex=-1;heading.focus({preventScroll:true});heading.scrollIntoView({block:'start',behavior:'instant'});}}
  function compile(){
    fileErrors=[];const batch=C.empty();
    for(const type of C.order)if(csvTexts[type]?.trim()){try{batch[type]=C.decode(type,csvTexts[type]);if(!batch[type].length)fileErrors.push(C.schemas[type].label+'：CSV 只有表头，没有数据行。');}catch(error){fileErrors.push(C.schemas[type].label+'：'+error.message);}}
    preview=fileErrors.length?null:C.validateBatch(db,batch,{manual:true,imports:true});
    if(!fileErrors.length&&!preview.results.length)fileErrors.push('请先选择 CSV 文件、粘贴内容或载入完整示例。');
    return batch;
  }
  function filteredResources(){
    const all=db[listType],q=query.trim().toLowerCase();return all.filter(row=>(sourceFilter==='all'||row._source===sourceFilter)&&(!q||Object.values(row).some(value=>String(value).toLowerCase().includes(q))));
  }
  function filteredMappings(){const q=query.trim().toLowerCase();return C.mappings(db).filter(row=>(!overviewTeam||row.team_code===overviewTeam)&&(!overviewCluster||row.cluster_code===overviewCluster)&&(!overviewIntent||row.desired_status===overviewIntent)&&(!q||Object.values(row).some(value=>String(value).toLowerCase().includes(q))));}
  function tableHTML(){
    const mappingRows=listView==='mapping'?C.mappings(db):[];const all=listView==='mapping'?filteredMappings():filteredResources();page=Math.min(page,Math.max(1,Math.ceil(all.length/pageSize)));const visible=all.slice((page-1)*pageSize,page*pageSize);
    let columns,rows;
    if(listView==='mapping'){
      columns=['团队','API Key','模型','服务地址引用','模型 Pod','集群','节点','配置意图','映射'];
      rows=visible.map(row=>`<tr><td><div class="overview-team"><span class="avatar">${esc(row.team[0])}</span><span><b>${esc(row.team)}</b><small>${esc(row.team_code||row.environment)}</small></span></div></td><td>${row.key_code?`<button type="button" class="key-badge" data-overview-key="${esc(row.key_code)}">${esc(row.key)} ↗</button>`:`<span class="overview-missing">${esc(row.key)}</span>`}<small class="overview-secondary">${esc(row.key_name||'Key 待补录')}</small><small class="overview-secondary">${esc(row.key_code)}</small></td><td><span class="tag model">${esc(row.model)}</span></td><td><span class="tag ip">${esc(row.address)}</span><small class="overview-secondary">${esc(row.service)} · ${esc(row.role)}</small></td><td class="pod">${esc(row.pod)}<small class="overview-secondary">${esc(row.namespace||'Namespace 未登记')}</small></td><td><span class="tag cluster">${esc(row.cluster)}</span></td><td><span class="overview-secondary configured-node-text">配置 Node：${esc(C.displayValue(row.configured_nodes)||'未登记')}</span>${row.observed_node?`<span class="tag node">观测 Node：${esc(row.observed_node)}</span>`:'<span class="overview-missing">观测 Node 未采集</span>'}</td><td>${row.desired_status?`<span class="tag ${row.desired_status==='ACTIVE'?'good':row.desired_status==='SUSPENDED'?'warn':'bad'}">${esc(row.desired_status)}</span>`:'<span class="overview-missing">未配置</span>'}<small class="overview-secondary">执行端 ${esc(row.effective_status)}</small>${row.dependency==='待补录'?'<small class="overview-secondary">业务依赖待补录</small>':''}</td><td><button type="button" class="overview-map-link" data-overview-row="${mappingRows.findIndex(item=>item.key_code===row.key_code&&item.business_code===row.business_code&&item.service_code===row.service_code&&item.endpoint_code===row.endpoint_code&&item.runtime_code===row.runtime_code)}">查看 ↗</button></td></tr>`).join('');
    }else{
      columns=['代码 / 关系','名称','归属 / 关联','录入来源','操作'];
      const refFields=C.schemas[listType].fields.filter(field=>field.ref);
      rows=visible.map(row=>`<tr><td class="mono">${esc(C.identity(listType,row))}<small>${esc(row.environment||'两端同环境')}</small></td><td>${esc(row.name||'配置关系')}</td><td>${refFields.length?refFields.map(field=>{const ref=db[field.ref].find(record=>record.code===row[field.key]);return `<span>${esc(field.label.replace('代码',''))}：${esc(ref?.name||row[field.key]||(listType==='endpoints'&&field.key==='pd_group_code'&&row.role==='COMBINED'?'不适用（合并部署）':'待补录'))}</span>`;}).join(''):listType==='clusters'?esc(row.region||'区域待补录'):'—'}</td><td>${esc(row._source||'浏览器录入')}<small>${esc(row._updated_at?'修改于 '+row._updated_at:row._recorded_at||'演示初始目录')}</small></td><td><button class="text-button" type="button" data-view-record="${esc(C.identity(listType,row))}">查看</button><button class="text-button" type="button" data-edit-record="${esc(C.identity(listType,row))}" data-edit-type="${listType}">${listType==='runtimes'?'查看历史':'编辑'}</button></td></tr>`).join('');
    }
    const pages=Math.max(1,Math.ceil(all.length/pageSize));
    const pagination=`<div class="pagination"><span>第 ${page} / ${pages} 页</span><div><button type="button" class="button small" id="list-prev" ${page===1?'disabled':''}>上一页</button><button type="button" class="button small" id="list-next" ${page*pageSize>=all.length?'disabled':''}>下一页</button></div></div>`;
    if(listView==='mapping')return `<div class="overview-table-scroll"><table class="overview-table"><thead><tr>${columns.map(column=>`<th>${column}</th>`).join('')}</tr></thead><tbody>${rows||'<tr><td colspan="9" class="empty">没有匹配的映射记录。</td></tr>'}</tbody></table></div><div class="panel-foot"><span>配置 Node 表示部署范围；Pod / 观测 Node 按历史来源展示，均不表示已验证健康。</span><span>当前显示 ${visible.length} / ${all.length} 条映射</span></div>${pages>1?pagination:''}`;
    return `<div class="list-count">资源记录 · 匹配 ${all.length} 条</div><div class="table-wrap"><table class="directory-table catalog-table"><thead><tr>${columns.map(column=>`<th>${column}</th>`).join('')}</tr></thead><tbody>${rows||'<tr><td colspan="5" class="empty">没有匹配记录。</td></tr>'}</tbody></table></div>${pagination}`;
  }
  function directoryView(){
    const sources=[...new Set(db[listType].map(row=>row._source||'浏览器录入'))];
    const selectOptions=(type,value)=>db[type].map(row=>`<option value="${esc(row.code)}" ${value===row.code?'selected':''}>${esc(row.name)}</option>`).join('');
    const footer=`<div class="directory-export"><button class="button small" id="export-filtered" type="button">导出当前结果</button><button class="button small" id="export-directory" type="button">导出全部目录 JSON</button><span>本地交互 Demo · 数据仅保存在此浏览器</span></div>`;
    if(listView==='mapping')return `${overviewSummary()}<section class="panel overview-map"><div class="panel-head"><div><h2>授权与运行实例映射</h2><p>每行对应一条 Key × 模型 × Endpoint × 运行成员关系；缺少部署时保留配置行。</p></div><span class="pill neutral">只读总览 · 非运行健康状态</span></div><div class="toolbar overview-toolbar"><input id="directory-search" class="search" type="search" aria-label="搜索录入目录" placeholder="搜索团队 / Key / 模型 / 地址引用 / Pod / 集群 / 节点" value="${esc(query)}"><select id="overview-team" aria-label="筛选团队"><option value="">全部团队</option>${selectOptions('teams',overviewTeam)}</select><select id="overview-cluster" aria-label="筛选集群"><option value="">全部集群</option>${selectOptions('clusters',overviewCluster)}</select><select id="overview-intent" aria-label="筛选配置意图"><option value="">全部意图</option>${['ACTIVE','SUSPENDED','DISABLED'].map(status=>`<option ${overviewIntent===status?'selected':''}>${status}</option>`).join('')}</select></div><div id="directory-table-container">${tableHTML()}</div></section>${footer}`;
    return `<section class="panel resource-directory"><div class="panel-head"><div><h2>资源与关系完整字段</h2><p>已保存 ${C.order.reduce((n,type)=>n+db[type].length,0)} 条资源与关系；选择类型后可查看每条记录的全部字段。</p></div><span class="pill neutral">支持查看与修改</span></div><div class="toolbar"><input id="directory-search" class="search" type="search" aria-label="搜索录入目录" placeholder="搜索名称、代码、关联或字段内容" value="${esc(query)}"><select id="directory-type" aria-label="资源类型">${options(listType)}</select><select id="source-filter" aria-label="筛选录入来源"><option value="all">全部来源</option>${sources.map(source=>`<option ${sourceFilter===source?'selected':''}>${esc(source)}</option>`).join('')}</select></div><div id="directory-table-container">${tableHTML()}</div></section>${footer}`;
  }
  function openMappingDetail(row){
    detail=null;
    const pairs=[['teams',row.team_code],['businesses',row.business_code],['keys',row.key_code],['models',row.model_code],['services',row.service_code],['pdgroups',row.pd_group_code],['endpoints',row.endpoint_code],['runtimes',row.runtime_code],['clusters',row.cluster_code]];
    $('#record-dialog').innerHTML=`<header><div><small>授权与运行实例映射 · 完整字段</small><h2>${esc(row.service)}</h2></div><button type="button" id="close-detail" class="button small">关闭</button></header><p class="hint">业务依赖：${esc(row.dependency)} · Key 模型授权：${esc(row.authorization)} · 执行端未连接</p>${pairs.filter(([type])=>type!=='runtimes').map(([type,code])=>{const record=[...db[type],...(type==='endpoints'?db.retired_endpoints||[]:type==='pdgroups'?db.retired_pdgroups||[]:[])].find(item=>item.code===code);return `<section class="mapping-detail-group"><div class="mapping-detail-heading"><h3>${C.schemas[type].label}</h3>${record?`<button type="button" class="text-button" data-edit-record="${esc(C.identity(type,record))}" data-edit-type="${type}">编辑</button>`:''}</div>${record?`<div class="detail-fields">${C.schemas[type].fields.map(field=>`<div><label>${field.label}<small>${field.key}</small></label><p class="${record[field.key]?'':'empty-value'}">${esc(C.displayValue(record[field.key])||'未填写')}</p></div>`).join('')}</div>`:`<p class="empty-value">${type==='pdgroups'&&db.services.find(item=>item.code===row.service_code)?.deployment_mode==='COMBINED'?'不适用（合并部署）':'未登记'}</p>`}</section>`;}).join('')}<section class="mapping-detail-group"><h3>全部 Pod / Node 历史记录</h3>${db.runtimes.filter(item=>item.endpoint_code===row.endpoint_code).map(item=>`<div class="detail-fields">${C.schemas.runtimes.fields.map(field=>`<div><label>${esc(field.label)}</label><p>${esc(C.displayValue(item[field.key])||'未填写')}</p></div>`).join('')}<div><label>来源</label><p>${esc(item._source||'历史登记')}</p></div></div>`).join('')||'<p class="empty-value">未采集</p>'}</section>`;
    $('#record-dialog').showModal();
  }
  function download(name,text,mime='text/csv;charset=utf-8'){const blob=new Blob([mime.startsWith('text/csv')?'\uFEFF'+text:text],{type:mime}),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  function batchReferenceInput(field,row){
    const available=db[field.ref].filter(item=>!row.environment||C.environmentCode(item.environment)===C.environmentCode(row.environment)).map(item=>({value:'name:'+item.name,label:item.name}));
    if(csvTexts[field.ref])try{for(const item of C.decode(field.ref,csvTexts[field.ref]))if(item._import_key)available.push({value:item._import_key,label:item.name+' · 本批次'});}catch{}
    const value=row[field.key]||'';if(value&&!available.some(item=>item.value===value))available.unshift({value,label:value});
    return `<select id="detail-${field.key}" name="${field.key}"><option value="">请选择</option>${available.map(item=>`<option value="${esc(item.value)}" ${value===item.value?'selected':''}>${esc(item.label)}</option>`).join('')}</select>`;
  }
  function openDetail(type,row,index=null){
    if(index!==null){const original=C.decode(type,csvTexts[type])[index];row={...original};}detail={type,row:{...row},index};const editable=index!==null,fields=editable?[{key:'import_key',label:'导入标识'},...C.schemas[type].fields]:C.schemas[type].fields;
    $('#record-dialog').innerHTML=`<form id="detail-form" novalidate><header><div><small>${C.schemas[type].label} · ${editable?'批次修正':'完整字段'}</small><h2>${esc(row.name||C.identity(type,row))}</h2></div><button type="button" id="close-detail" class="button small">关闭</button></header>${editable?'<p class="hint">只修改暂存内容，修正后会重新校验整个批次。</p>':''}<div class="detail-fields">${fields.map(field=>`<div><label for="detail-${field.key}">${field.label}${field.required?'<span class="required">必填</span>':''}<small>${field.key}</small></label>${editable&&field.ref?batchReferenceInput(field,row):editable&&field.key!=='code'?`<input id="detail-${field.key}" name="${field.key}" value="${esc(field.array?JSON.stringify(row[field.key]||[]):field.key==='import_key'?row._import_key:row[field.key])}" ${field.required?'required':''}>`:`<p class="${row[field.key]?'':'empty-value'}">${esc(C.displayValue(row[field.key])||'未填写')}</p>`}</div>`).join('')}${!editable&&type==='runtimes'?`<div><label>实例历史配置</label><p>${esc((db.endpoints.find(ep=>ep.code===row.endpoint_code)||(db.retired_endpoints||[]).find(ep=>ep.code===row.endpoint_code))?.name||row.endpoint_code)}</p></div>`:''}${!editable?`<div><label>录入来源</label><p>${esc(row._source||'浏览器录入')}</p></div><div><label>录入时间</label><p>${esc(row._recorded_at||'初始合成示例')}</p></div>`:''}</div>${type==='runtimes'?'<div class="note">历史采集字段只读，保留原始身份和来源；配置 Node 在所属服务中维护。</div>':''}${type==='keys'?'<div class="note">仅外部引用与配置意图；执行端未连接。</div>':''}${editable?'<footer><button class="button primary" type="submit">保留修正并重新校验</button></footer>':type==='runtimes'?'':`<footer><button class="button primary" type="button" data-edit-record="${esc(C.identity(type,row))}" data-edit-type="${type}">${type==='runtimes'?'查看历史记录':'编辑记录'}</button></footer>`}</form>`;
    $('#record-dialog').showModal();
  }
  document.addEventListener('click',event=>{
    const button=event.target.closest('button');if(!button)return;
    if(button.hasAttribute('data-entry-open')){setMode(entryMethod);return;}
    if(button.hasAttribute('data-entry-method')){setMode(button.dataset.entryMethod);return;}
    if(button.hasAttribute('data-entry-records')){openResource(listType);return;}
    if(button.hasAttribute('data-new-entry')){if(setMode('wizard'))GatewayEntryDirectory.startNew?.();return;}
    if(button.dataset.editRecord!==undefined){openEdit(button.dataset.editType,button.dataset.editRecord);return;}
    if(button.dataset.consoleView){if(button.dataset.consoleView==='overview'){listView='mapping';query='';page=1;setMode('directory');}else openResource(button.dataset.consoleView==='keys'?'keys':'teams');return;}
    if(button.dataset.openResource){openResource(button.dataset.openResource);return;}
    if(button.id==='refresh-directory'){load();preview=null;window.dispatchEvent(new CustomEvent('demo-directory-change'));if(mode==='edit'){return;}if(mode!=='wizard'){render();message('目录已刷新，显示此浏览器最新保存的数据。');}return;}
    if(button.dataset.mode){if(button.dataset.mode==='directory'){listView='mapping';query='';page=1;}setMode(button.dataset.mode);return;}
    if(button.dataset.batchType){batchType=button.dataset.batchType;previewPage=1;render();return;}
    if(button.dataset.listType){listType=button.dataset.listType;sourceFilter='all';page=1;render();return;}
    if(button.dataset.listView){listView=button.dataset.listView;query='';sourceFilter='all';page=1;setMode('directory');return;}
    if(button.dataset.overviewKey){const row=db.keys.find(item=>item.code===button.dataset.overviewKey);if(row)openDetail('keys',row);return;}
    if(button.dataset.overviewRow!==undefined){const row=C.mappings(db)[Number(button.dataset.overviewRow)];if(row)openMappingDetail(row);return;}
    if(button.dataset.viewRecord){const row=db[listType].find(item=>C.identity(listType,item)===button.dataset.viewRecord);if(row)openDetail(listType,row);return;}
    if(button.dataset.editBatch!==undefined){const result=preview.results.find(row=>row.type===batchType&&row.index===Number(button.dataset.editBatch));if(result)openDetail(batchType,{...result.row,_import_key:result.importKey},result.index);return;}
    if(button.id==='download-template')download(batchType+'.csv',C.encode(batchType,[],{localized:true,forImport:true}));
    if(button.id==='choose-files')$('#csv-files').click();
    if(button.id==='batch-example'){
      if(Object.values(csvTexts).some(text=>text.trim())&&!confirm('用完整示例替换当前暂存批次？已保存目录不会改变。'))return;
      let number=1;while(db.teams.some(row=>row.code===`batch-${number}-a-team`))number++;
      const sample=C.examples('batch-'+number);csvTexts=Object.fromEntries(C.importOrder.filter(type=>sample[type].length).map(type=>[type,C.encode(type,sample[type],{localized:true,forImport:true})]));preview=null;fileErrors=[];flash='已载入两套完整服务关系示例，使用本批次的独立代码。点击校验后，可一起保存全部资源与关系。';render();
    }
    if(button.id==='clear-current'){delete csvTexts[batchType];preview=null;fileErrors=[];flash='当前文件已移出暂存批次。';render();}
    if(button.id==='validate-batch'){previewPage=1;load();compile();flash='';render();focusPreview();}
    if(button.id==='commit-batch'){
      const batch=compile();if(fileErrors.length||!preview?.valid){render();return;}
      const result=persist(batch,'批量 CSV');if(!result.ok){preview=result.check||preview;render();message(result.message,true);return;}
      csvTexts={};preview=null;fileErrors=[];flash=`已将 ${result.added} 条资源与关系保存到浏览器演示目录。`;listType='endpoints';listView='mapping';query='';sourceFilter='all';overviewTeam='';overviewCluster='';overviewIntent='';page=1;setMode('directory');
    }
    if(button.id==='preview-prev'){previewPage--;$('#batch-preview').innerHTML=previewHTML();}
    if(button.id==='preview-next'){previewPage++;$('#batch-preview').innerHTML=previewHTML();}
    if(button.id==='close-detail')$('#record-dialog').close();
    if(button.id==='list-prev'){page--;$('#directory-table-container').innerHTML=tableHTML();}
    if(button.id==='list-next'){page++;$('#directory-table-container').innerHTML=tableHTML();}
    if(button.id==='export-directory')download('gateway-demo-directory.json',JSON.stringify({kind:'synthetic-demo-directory',saved_to:'browser-only',db},null,2),'application/json');
    if(button.id==='export-filtered'){
      if(listView==='resources')download(listType+'-filtered.csv',C.encode(listType,filteredResources()));
      else download('gateway-demo-mappings.json',JSON.stringify(filteredMappings(),null,2),'application/json');
    }
  });
  document.addEventListener('input',event=>{
    if(event.target.id==='csv-text'){csvTexts[batchType]=event.target.value;preview=null;fileErrors=[];$('#batch-preview').innerHTML='';}
    if(event.target.id==='directory-search'){query=event.target.value;page=1;$('#directory-table-container').innerHTML=tableHTML();}
  });
  document.addEventListener('change',async event=>{
    if(event.target.id==='batch-type'){batchType=event.target.value;previewPage=1;render();}
    if(event.target.id==='directory-type'){listType=event.target.value;sourceFilter='all';page=1;setMode('directory');}
    if(['overview-team','overview-cluster','overview-intent'].includes(event.target.id)){if(event.target.id==='overview-team')overviewTeam=event.target.value;if(event.target.id==='overview-cluster')overviewCluster=event.target.value;if(event.target.id==='overview-intent')overviewIntent=event.target.value;page=1;$('#directory-table-container').innerHTML=tableHTML();}
    if(event.target.id==='source-filter'){sourceFilter=event.target.value;page=1;$('#directory-table-container').innerHTML=tableHTML();}
    if(event.target.id==='csv-files'){
      const files=[...event.target.files];if(!files.length)return;const currentType=batchType,loaded={},errors=[];
      await Promise.all(files.map(async file=>{const stem=file.name.replace(/\.csv$/i,'');const identified=C.order.find(key=>key===stem||C.schemas[key].label===stem);const type=identified||(files.length===1?currentType:null);if(!type){errors.push(file.name+'：多文件导入请按模板名称命名。');return;}if(file.size>2*1024*1024){errors.push(file.name+'：超过 2 MB。');return;}if(loaded[type]!==undefined){errors.push(file.name+'：同一类型只能选择一个文件。');return;}loaded[type]=null;try{loaded[type]=await file.text();}catch{errors.push(file.name+'：读取失败。');}}));
      if(!errors.length){Object.assign(csvTexts,loaded);batchType=Object.keys(loaded)[0]||batchType;previewPage=1;preview=null;fileErrors=[];flash=`已暂存 ${files.length} 个 CSV。点击“校验整个批次”查看结果。`;}else{fileErrors=errors;preview=null;flash='文件未载入，原暂存内容保留。';}render();
    }
  });
  document.addEventListener('submit',event=>{if(event.target.id!=='detail-form'||detail?.index===null)return;event.preventDefault();const rows=C.decode(detail.type,csvTexts[detail.type]);const values=Object.fromEntries(new FormData(event.target));rows[detail.index]={...rows[detail.index],...Object.fromEntries(C.inputFields(detail.type).map(field=>[field.key,values[field.key]??rows[detail.index][field.key]])),_import_key:values.import_key||''};csvTexts[detail.type]=C.encode(detail.type,rows,{localized:true,forImport:true});$('#record-dialog').close();compile();render();focusPreview();});
  window.addEventListener('storage',event=>{if(event.key!==KEY)return;load();preview=null;flash='浏览器目录已更新，待导入批次需要重新校验。';if(mode!=='wizard'&&mode!=='edit')render();window.dispatchEvent(new CustomEvent('demo-directory-change'));});
  window.addEventListener('beforeunload',event=>{if(Object.values(csvTexts).some(text=>text.trim())){event.preventDefault();event.returnValue='';}});
  const initialParams=new URLSearchParams(location.search);if(initialParams.get('mode')==='wizard'&&initialParams.get('service'))GatewayEntryDirectory.pendingServiceId=initialParams.get('service');if(initialParams.get('view')==='resources'){listView='resources';listType=C.order.includes(initialParams.get('type'))?initialParams.get('type'):'teams';}
  if(initialParams.get('mode')==='edit'){const type=initialParams.get('type'),id=initialParams.get('record');if(C.schemas[type]&&db[type].some(row=>C.identity(type,row)===id))openEdit(type,id);else{flash='没有找到这条记录，请从目录重新选择。';setMode('directory');}}else setMode(initialParams.get('mode')||'directory');
})();
