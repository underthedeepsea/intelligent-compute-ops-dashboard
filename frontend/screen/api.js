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
async function ensureSession(){
 let session=(await request('/api/v1/session')).data;
 setCSRF(session.csrf_token);
 if(!session.authenticated && session.local_passwordless_available){
  session=(await request('/api/v1/session/local',{method:'POST',body:{}})).data;
  setCSRF(session.csrf_token);
 }
 if(!session.authenticated){const error=new Error('尚未获得访问身份，请联系管理员配置访问入口。');error.status=401;throw error;}
 return session;
}
const api={escape,metric,request,setCSRF,ensureSession};
if(typeof module!=='undefined')module.exports=api;
root.ControlAPI=api;
})(typeof window!=='undefined'?window:globalThis);
