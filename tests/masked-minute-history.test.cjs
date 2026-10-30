const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const base=path.join(__dirname,'../frontend/screen-masked');
const js=fs.readFileSync(path.join(base,'assets/masked-gauges.js'),'utf8');
// Exercise the actual pure history functions without booting the browser-only renderer.
const functions=js.slice(js.indexOf('function historyWindow('),js.indexOf('function instrument('));
const {historyWindow,historyStrip}=new Function('esc','full',functions+';return {historyWindow,historyStrip};')(s=>String(s),s=>s);
const fixture=(state,interval=30000,step=state.length-1)=>({x:{id:'test-host',code:'CPU'},ctx:{step,model:{d:{interval_ms:interval,tracks:{'test-host':{metrics:{CPU:{state}}}}}}}});
const run=f=>historyWindow(f.x,f.ctx);
test('native minute points preserve every source state and a twenty-minute window has21 positions',()=>{
 const states='GGGWWRRRGGUUGGGWWWGGGWRGG',f=fixture(states,60000),h=run(f);
 assert.equal(h.cadence,60000);assert.equal(h.minutes,20);assert.equal(h.points.length,21);
 assert.equal(h.points.map(p=>p.state).join(''),states.slice(-21));
 assert(h.points.every(p=>p.first===p.last));
});
test('sub-minute data keeps confirmed risk and marks uncertainty without turning it into a visual gap',()=>{
 const f=fixture('GGUWWR'),h=run(f);
 assert.equal(h.points.map(p=>p.state).join(''),'GWR');
 assert.deepEqual(h.points.map(p=>p.pending),[false,true,false]);
 assert.equal(h.sourceSequence,'GGUWWR');assert.equal(f.ctx.model.d.interval_ms,30000);
 const html=historyStrip(f.x,f.ctx,false);
 assert(html.includes('data-point-count="3"'));assert(html.includes('1分钟/点'));
 assert(html.includes('data-pending-point-count="1"'));assert(!html.includes('g12-pending'));assert(!html.includes('菱形'));assert(!html.includes('data-state="U"'));
});
test('unknown never becomes healthy; abnormal and unknown remain separately represented',()=>{
 for(const [input,state,pending] of [['GU','U',true],['UU','U',true],['RU','R',true],['WU','W',true],['G?','U',true],['OO','O',false]]){
  const p=run(fixture(input)).points[0];assert.equal(p.state,state,input);assert.equal(p.pending,pending,input);
 }
});
test('current minute is partial and cannot read a future warning to hide current unknown',()=>{
 const f=fixture('GGUW',30000,2);assert.equal(run(f).points.at(-1).state,'U');
 f.ctx.step=3;assert.equal(run(f).points.at(-1).state,'W');assert(run(f).points.at(-1).pending);
});
test('window edges exclude older samples at both half-minute alignments and cover the source exactly once',()=>{
 for(const step of [390,391]){
  const f=fixture('G'.repeat(500),30000,step),h=run(f);
  assert.equal(h.first,step-40);assert.equal(h.minutes,20);assert.equal(h.points.length,21);
  assert.deepEqual(h.points.flatMap(p=>Array.from({length:p.last-p.first+1},(_,i)=>p.first+i)),Array.from({length:41},(_,i)=>step-40+i));
 }
});
test('short history shows its actual span; slower sources are not upsampled into invented points',()=>{
 const start=run(fixture('GG',30000,0));assert.equal(start.minutes,0);assert.equal(start.points.length,1);
 const short=fixture('GG',30000);assert(historyStrip(short.x,short.ctx,false).includes('观察窗0.5分钟'));
 const slow=run(fixture('G'.repeat(20),120000));assert.equal(slow.cadence,120000);assert.equal(slow.points.length,11);assert.equal(slow.minutes,20);
});
test('missing, offline, invalid interval and out-of-range sources do not render a false history',()=>{
 for(const f of [fixture('',30000,0),fixture('GG',0),fixture('GG',NaN),fixture('GG',30000,5)])assert.equal(run(f),null);
 const f=fixture('GG');assert(!historyStrip(f.x,f.ctx,true).includes('g7-history-track'));
 delete f.ctx.model.d.tracks['test-host'];assert.equal(run(f),null);
});
test('actual masked transitions keep the unknown evidence and original JSON unchanged',()=>{
 const raw=fs.readFileSync(path.join(base,'data/view.json'),'utf8'),d=JSON.parse(raw);
 for(const [id,start] of [['h7fd856d5d0aea59b16ea5f14',384],['hfc04f9f844573548a688c115',360]]){
  const x={id,code:'CPU'},ctx={step:390,model:{d}},h=historyWindow(x,ctx),point=h.points.find(p=>p.first===start);
  assert.equal(point.state,'W');assert(point.pending);assert.deepEqual(point.states,['U','W']);
  assert.equal(h.points.length,21);assert.equal(h.sourceSequence,d.tracks[id].metrics.CPU.state.slice(350,391));
 }
 assert.equal(JSON.stringify(d),JSON.stringify(JSON.parse(raw)));
});
test('requested display notes are removed while missing-data information and global replay mode remain',()=>{
 assert(!js.includes('状态轨迹来自回放'));assert(!js.includes('未提供原始读数'));
 const inference=fs.readFileSync(path.join(base,'assets/masked-inference.js'),'utf8');
 assert(!inference.includes('不展示原始读数'));assert(inference.includes('KV链路状态待确认'));
 assert((fs.readFileSync(path.join(base,'assets/masked-app.js'),'utf8')+fs.readFileSync(path.join(base,'index.html'),'utf8')).includes('场景回放'));
});
