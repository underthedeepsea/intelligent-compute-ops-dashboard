const assert=require('node:assert/strict'),test=require('node:test'),S=require('../service-entry.js');
const snap={service:{id:'s',name:'old',environment_code:'legacy',model_id:'m',deployment_mode:'SPLIT_PD'},groups:[{id:'g1',name:'One',enabled:true},{id:'g2',name:'Two',enabled:true}],endpoints:[{id:'p',enabled:true,pd_group_id:'g1',name:'P',role:'PREFILL',cluster_id:'c',configured_nodes:[]},{id:'d',enabled:true,pd_group_id:'g2',name:'D',role:'DECODE',cluster_id:'c',configured_nodes:[]}],businesses:[{id:'b1',team_id:'t',binding_enabled:true},{id:'b2',team_id:'other',binding_enabled:true}],expected_versions:{'services:s':2},metadata_revision:9};
test('hydrate preserves multi groups, businesses, old environment and missing legacy config',()=>{const d=S.hydrate(snap),b=S.bundle(d,snap,snap);assert.equal(d.environment_code,'legacy');assert.equal(b.groups.length,2);assert.deepEqual(b.groups[0].endpoints,[{id:'p',unchanged:true}]);assert.deepEqual(b.business_refs,[{id:'b1'},{id:'b2'}]);assert.deepEqual(b.expected_versions,snap.expected_versions);assert.equal(b.expected_metadata_revision,9);});
test('mode switch retires old groups and explicit business removal',()=>{const d=S.hydrate(snap);d.deployment_mode='COMBINED';d.businesses.splice(0,1);const b=S.bundle(d,snap,snap);assert.deepEqual(b.retire_ids,{groups:['g1','g2'],endpoints:[]});assert.deepEqual(b.remove_business_ids,['b1']);});
test('new parents and endpoints have form keys but no artificial identity or observation',()=>{const d=S.fresh();d.model.create=true;d.model.name='M';d.team.create=true;d.team.name='T';d.businesses[0].create=true;d.businesses[0].name='B';d.businesses[0].owner='Owner';d.endpoints[0].cluster.create=true;const b=S.bundle(d,null,{metadata_revision:1,expected_versions:{}});assert.ok(b.service.model_ref.create.form_key);assert.ok(b.endpoints[0].form_key);assert.equal(b.endpoints[0].id,undefined);assert.equal(b.endpoints[0].pod_uid,undefined);assert.equal(b.endpoints[0].code,undefined);});
test('server-parsed cells serialize commas quotes and multiline values with standard quoting',()=>{assert.equal(S.csvText(['a','b'],[['a,b','a"b\nc']]),'"a","b"\r\n"a,b","a""b\nc"');});

const copy=x=>JSON.parse(JSON.stringify(x));
test('R1 active bindings retain disabled business entities while inactive bindings stay historical',()=>{
 const s=copy(snap);s.businesses=[{id:'historical',team_id:'old',enabled:false,binding_enabled:false},{id:'active',team_id:'t',enabled:true,binding_enabled:true},{id:'disabled-active',team_id:'other',enabled:false,binding_enabled:true}];
 const original=JSON.stringify(s),d=S.hydrate(s),body=S.bundle(d,s,s);assert.deepEqual(d.businesses.map(b=>b.id),['active','disabled-active']);assert.equal(d.team.id,'t');assert.deepEqual(body.business_refs,[{id:'active'},{id:'disabled-active'}]);assert.deepEqual(body.remove_business_ids,[]);assert.deepEqual(body.expected_versions,s.expected_versions);assert.equal(JSON.stringify(s),original);
 d.businesses.splice(0,1);assert.deepEqual(S.bundle(d,s,s).remove_business_ids,['active']);
});
test('R1 detached binding remains detached on next name-only save with history versions retained',()=>{
 const s=copy(snap);s.businesses=[{id:'b',team_id:'t',binding_enabled:false,enabled:true}];s.expected_versions['businesses:b']=3;const d=S.hydrate(s);d.name='renamed';const body=S.bundle(d,s,s);assert.deepEqual(body.business_refs,[]);assert.deepEqual(body.remove_business_ids,[]);assert.equal(body.expected_versions['businesses:b'],3);
});
test('R2 zero-business new and edit bodies omit an empty team reference',()=>{
 const s=copy(snap);s.businesses=[];const d=S.hydrate(s);d.name='zero renamed';assert.equal(Object.hasOwn(S.bundle(d,s,s),'team_ref'),false);
 const fresh=S.fresh();fresh.businesses=[];assert.equal(Object.hasOwn(S.bundle(fresh,null,{metadata_revision:1}),'team_ref'),false);
});
test('R2 selected or explicitly created teams remain in payloads when adding business',()=>{
 const d=S.fresh();d.businesses[0].create=true;d.businesses[0].name='B';d.businesses[0].owner='Owner';d.team.id='t';assert.deepEqual(S.bundle(d,null,{}).team_ref,{id:'t'});d.team.create=true;d.team.name='new team';assert.equal(S.bundle(d,null,{}).team_ref.create.name,'new team');
});

const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};
const flush=()=>new Promise(setImmediate),row=(id,env)=>({id,name:id,environment_code:env,deployment_mode:'COMBINED',enabled:true});
const pageData=(items,next_cursor=null)=>({data:{items,next_cursor}});
async function listFixture(){
 const listeners=new Map(),pending=[];
 const host={innerHTML:'',querySelector:()=>null,addEventListener:(n,f)=>listeners.set(n,f),removeEventListener:(n,f)=>{if(listeners.get(n)===f)listeners.delete(n);}};
 const api={request:(url)=>{if(url.includes('/options'))return Promise.resolve({data:{metadata_revision:1,expected_versions:{},options:{}}});if(/\/services\/[^?]+$/.test(url))return Promise.resolve({data:{service:{id:'edit',name:'edit',environment_code:'PRD',deployment_mode:'COMBINED',model_id:'m'},groups:[],endpoints:[],businesses:[],options:{},expected_versions:{},metadata_revision:1}});const p=deferred();pending.push({url,...p});return p.promise;}};
 const controller=S.mount(host,{api,escape:String,session:{can_write:true}});await flush();
 const click=dataset=>listeners.get('click')({target:{closest:()=>({dataset,hasAttribute:n=>n==='data-se-new'&&dataset.seNew!==undefined})}});
 const change=env=>listeners.get('change')({target:{value:env,dataset:{},hasAttribute:n=>n==='data-se-directory-env'}});
 const opening=click({seTab:'directory'});await flush();pending[0].resolve(pageData([row('original','STG')]));await opening;
 return {host,pending,controller,click,change};
}
test('R3 newest environment wins reversed responses and stale success cannot change notice',async()=>{
 const f=await listFixture(),dev=f.change('DEV');await flush();const prd=f.change('PRD');await flush();f.pending[2].resolve(pageData([row('PRD-winner','PRD')]));await prd;const current=f.host.innerHTML;f.pending[1].resolve(pageData([row('DEV-stale','DEV')]));await dev;assert.equal(f.host.innerHTML,current);assert.ok(current.includes('PRD-winner'));assert.ok(!current.includes('DEV-stale'));f.controller.destroy();
});
test('R3 pagination captures one environment and stops old pages after a new environment',async()=>{
 const f=await listFixture(),dev=f.change('DEV');await flush();f.pending[1].resolve(pageData([row('DEV-first','DEV')],'next'));await flush();assert.ok(f.pending[2].url.includes('environment_code=DEV')&&f.pending[2].url.includes('cursor=next'));const prd=f.change('PRD');await flush();f.pending[3].resolve(pageData([row('PRD-page','PRD')]));await prd;f.pending[2].resolve(pageData([row('DEV-next','DEV')],'third'));await flush();assert.equal(f.pending.length,4);await dev;assert.ok(f.host.innerHTML.includes('PRD-page'));assert.ok(!f.host.innerHTML.includes('DEV-first'));f.controller.destroy();
});
test('R3 current directory failures are handled, clear wrong-environment rows and recover',async()=>{
 const f=await listFixture(),dev=f.change('DEV');await flush();f.pending[1].reject(Error('current directory failure'));await assert.doesNotReject(dev);assert.ok(f.host.innerHTML.includes('current directory failure'));assert.ok(!f.host.innerHTML.includes('original'));const prd=f.change('PRD');await flush();f.pending[2].resolve(pageData([row('recovered','PRD')]));await prd;assert.ok(f.host.innerHTML.includes('recovered'));assert.ok(!f.host.innerHTML.includes('current directory failure'));f.controller.destroy();
});
test('R3 stale failures cannot escape or replace current directory state',async()=>{
 const f=await listFixture(),dev=f.change('DEV');await flush();const prd=f.change('PRD');await flush();f.pending[2].resolve(pageData([row('current','PRD')]));await prd;const html=f.host.innerHTML;f.pending[1].reject(Error('stale failure'));await assert.doesNotReject(dev);assert.equal(f.host.innerHTML,html);f.controller.destroy();
});
test('R3 leaving directory for tab, edit or new invalidates pending list completion',async()=>{
 for(const action of [{seTab:'batch'},{seEdit:'edit'},{seNew:''}]){const f=await listFixture(),pending=f.change('DEV');await flush();await f.click(action);const html=f.host.innerHTML;f.pending[1].resolve(pageData([row('late directory','DEV')]));await pending;assert.equal(f.host.innerHTML,html);f.controller.destroy();}
});
test('R3 destroy invalidates pending success and failure without late rendering',async()=>{
 for(const reject of [false,true]){const f=await listFixture(),pending=f.change('DEV');await flush();const html=f.host.innerHTML;f.controller.destroy();if(reject)f.pending[1].reject(Error('destroyed failure'));else f.pending[1].resolve(pageData([row('destroyed','DEV')]));await assert.doesNotReject(pending);assert.equal(f.host.innerHTML,html);}
});
test('R3 current multi-page load keeps all rows and one fixed environment',async()=>{
 const f=await listFixture(),dev=f.change('DEV');await flush();f.pending[1].resolve(pageData([row('page-one','DEV')],'next'));await flush();f.pending[2].resolve(pageData([row('page-two','DEV')]));await dev;assert.ok(f.host.innerHTML.includes('page-one')&&f.host.innerHTML.includes('page-two'));assert.ok(f.pending.slice(1).every(p=>p.url.includes('environment_code=DEV')));f.controller.destroy();
});
test('R3 pending directory errors cannot replace tab, edit or new notices',async()=>{
 for(const action of [{seTab:'batch'},{seEdit:'edit'},{seNew:''}]){const f=await listFixture(),pending=f.change('DEV');await flush();await f.click(action);const html=f.host.innerHTML;f.pending[1].reject(Error('old view failure'));await assert.doesNotReject(pending);assert.equal(f.host.innerHTML,html);f.controller.destroy();}
});
