const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const e=value=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
function render(start='2026-09-26T17:11:03.454664+00:00',end='2026-09-26T17:12:03.454664+00:00'){
 const window={};vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../restored02.js'),'utf8'),{window});
 const x={id:'ep',name:'长名称 " <Endpoint>',role:'PREFILL',metrics:{request_rate:{state:'AVAILABLE',value:987654321.2,unit:'requests/s'},tpot_p95_ms:{state:'AVAILABLE',value:49.3,unit:'ms/token'}},observation:{source_window:{start,end},identity:{model_name:'长模型名'}}};
 const data={items:[{id:'g',name:'g',endpoints:[x]}]};
 const c={state:{},e,m:(n,d)=>Number(n).toFixed(d),catalog:{},endpointState:()=> 'UNKNOWN',ageState:()=> 'STALE',stateLabel:x=>x,source:()=>`<div class="live-source">来源 UNVERIFIED · 来源已过期 · 巡检链路 DEMO_OFFLINE<br>来源窗口 ${e(start)} ～ ${e(end)} · 原始 Endpoint 口径</div>`};
 return window.ScreenRenderers['02'].render(data,c);
}
test('TV window uses explicit UTC+8, keeps full timestamps and truthful source status',()=>{const html=render();assert.match(html,/采样窗口 09-27 01:11–01:12（UTC\+8）/);assert.match(html,/title="2026-09-26T17:11:03.454664\+00:00 ～ 2026-09-26T17:12:03.454664\+00:00"/);assert.match(html,/UNVERIFIED · 来源已过期 · 巡检链路 DEMO_OFFLINE/);assert.match(html,/原始 Endpoint 口径/);assert.doesNotMatch(html,/实时/);});
test('cross-day source windows retain both dates; invalid dates retain raw provenance',()=>{assert.match(render('2026-09-26T15:59:00Z','2026-09-26T16:01:00Z'),/09-26 23:59–09-27 00:01/);assert.match(render('bad-window','bad-end'),/来源窗口 bad-window ～ bad-end/);});
test('compact values retain full numeric meaning and long identities remain escaped',()=>{const html=render();assert.match(html,/987.7M<small title="987654321.2 requests\/s">req\/s/);assert.match(html,/TPOT P95<\/span><b>49.3<small>ms\/token/);assert.match(html,/title="长名称 &quot; &lt;Endpoint>"/);assert.doesNotMatch(html,/<Endpoint>/);});
