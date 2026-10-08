(function(root){
'use strict';
/** A form and its grants must come from one observed Key version. Never promote fields. */
async function readKeySnapshot({request,id,isCurrent=()=>true,maxAttempts=3}){
 const base='/api/v1/gateway/keys/'+encodeURIComponent(id);
 for(let attempt=0;attempt<maxAttempts;attempt++){
  if(!isCurrent())return null;
  const [detail,grants]=await Promise.all([request(base),request(base+'/model-grants')]);
  if(!isCurrent())return null;
  const version=detail.data?.version;
  if(!Number.isSafeInteger(version)||version<1||!Number.isSafeInteger(grants.data?.version)||!Array.isArray(grants.data?.items))throw new Error('Key 读取响应不符合契约');
  if(version===grants.data.version)return {key:detail.data,grants:grants.data.items};
 }
 const error=new Error('Key 正被其他用户更新，无法取得一致版本。请刷新后重试。');
 error.status=409;error.payload={error:{code:'INCOHERENT_KEY_READ'}};throw error;
}
const api={readKeySnapshot};if(typeof module!=='undefined')module.exports=api;root.KeySnapshot=api;
})(typeof window!=='undefined'?window:globalThis);
