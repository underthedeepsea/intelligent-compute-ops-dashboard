(function(root){
'use strict';
const MAX_KEYS=120, MAX_ROWS=1000, CONCURRENCY=5;
async function load({keys,request,isCurrent=()=>true}){
 const selected=keys.slice(0,MAX_KEYS),snapshots=new Array(selected.length);
 let next=0;
 async function worker(){
  while(next<selected.length){
   const index=next++;
   if(!isCurrent())return;
   // A detail/grants pair must describe one version, even during concurrent edits.
   snapshots[index]=await root.KeySnapshot.readKeySnapshot({request,id:selected[index].id,isCurrent});
   if(!isCurrent())return;
  }
 }
 await Promise.all(Array.from({length:Math.min(CONCURRENCY,selected.length)},worker));
 if(!isCurrent())return null;
 return {snapshots:snapshots.filter(Boolean),truncated:keys.length>MAX_KEYS,totalKeys:keys.length};
}
function buildRows(catalog,snapshots,maxRows=MAX_ROWS){
 const byId=(name,id)=>catalog[name].find(x=>x.id===id);
 const rows=[],seen=new Set();let truncated=false;
 function add(key,team,model,service,endpoint,member,note){
  const id=[key.id,model?.id||'',service?.id||'',endpoint?.id||'',member?.id||''].join(':');
  if(seen.has(id)||truncated)return;seen.add(id);if(rows.length>=maxRows){truncated=true;return;}
  const cluster=endpoint&&byId('clusters',endpoint.cluster_id);
  rows.push({id,key,team,model,service,endpoint,member,cluster,note});
 }
 for(const snapshot of snapshots){
  if(truncated)break;
  const key=snapshot.key,team=byId('teams',key.team_id);
  const grants=snapshot.grants.filter(g=>g.enabled);
  if(!grants.length){add(key,team,null,null,null,null,'未配置模型授权');continue;}
  for(const grant of grants){
   if(truncated)break;
   const model=byId('models',grant.model_id);
   if(!model){add(key,team,{id:grant.model_id,name:'目录不可见',enabled:false},null,null,null,'授权模型未出现在当前目录');continue;}
   if(model.environment_code!==key.environment_code){add(key,team,model,null,null,null,'授权模型环境不一致');continue;}
   const services=catalog.services.filter(s=>s.model_id===model.id&&s.environment_code===key.environment_code);
   if(!services.length){add(key,team,model,null,null,null,'未登记服务');continue;}
   for(const service of services){
    if(truncated)break;
    const endpoints=catalog.endpoints.filter(ep=>ep.service_id===service.id&&ep.environment_code===key.environment_code);
    if(!endpoints.length){add(key,team,model,service,null,null,'未登记 Endpoint');continue;}
    for(const endpoint of endpoints){
     if(truncated)break;
     const registered=catalog['runtime-members'].filter(m=>m.endpoint_id===endpoint.id&&m.cluster_id===endpoint.cluster_id&&m.environment_code===key.environment_code);
     const members=registered.filter(m=>m.enabled);
     if(!members.length){add(key,team,model,service,endpoint,null,registered.length?'运行成员已登记但停用':'未登记运行成员');continue;}
     for(const member of members){if(truncated)break;add(key,team,model,service,endpoint,member,'');}
    }
   }
  }
 }
 return {rows,truncated};
}
const api={load,buildRows,MAX_KEYS,MAX_ROWS,CONCURRENCY};if(typeof module!=='undefined')module.exports=api;root.GatewayOverviewMapping=api;
})(typeof window!=='undefined'?window:globalThis);
