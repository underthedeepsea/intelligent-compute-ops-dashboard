/* Shared same-origin API transport. No credentials or provider URLs are stored here. */
(function(root){
'use strict';
const escape = value => String(value ?? '').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const metric = (value,digits=0) => typeof value==='number' && Number.isFinite(value) ? value.toLocaleString('zh-CN',{maximumFractionDigits:digits}) : '—';
let csrf='';
async function request(path, options={}) {
 if (!path.startsWith('/api/v1/')) throw new Error('只允许同源统一 API');
 const headers={'Accept':'application/json',...options.headers};
 if(options.body!==undefined){ headers['Content-Type']='application/json'; headers['X-CSRFToken']=csrf; }
 const response=await fetch(path,{credentials:'same-origin',cache:'no-store',...options,headers,body:options.body===undefined?undefined:JSON.stringify(options.body)});
 let result; try{result=await response.json();}catch{throw new Error('服务器未返回 JSON');}
 if(!response.ok){const error=new Error(result.error?.message || result.detail || `请求失败 (${response.status})`);error.status=response.status;error.payload=result;throw error;}
 if(result.schema_version!==1 && result.schema_version!=='1' && result.schema_version!=='1.0') throw new Error('不兼容的 API schema');
 return result;
}
function setCSRF(token){csrf=token || '';}
async function ensureAccess(){
 const access=(await request('/api/v1/session')).data;
 setCSRF(access.csrf_token);
 if(access.access_mode!=='direct'||access.can_write!==true) throw new Error('接口访问元数据无效，请检查服务接口。');
 return access;
}
const api={escape,metric,request,setCSRF,ensureAccess};
if(typeof module!=='undefined')module.exports=api;
root.ControlAPI=api;
})(typeof window!=='undefined'?window:globalThis);
