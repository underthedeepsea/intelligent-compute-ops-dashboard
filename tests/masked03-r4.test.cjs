const test=require('node:test'),a=require('node:assert/strict'),fs=require('node:fs');const C=require('../frontend/screen-masked/assets/masked-core.js'),R=require('../frontend/screen-masked/assets/masked03-r4.js'),D=require('../frontend/screen-masked/assets/masked-diagnostics.js');const data=JSON.parse(fs.readFileSync(__dirname+'/../frontend/screen-masked/data/view.json')),m=new C.Model(data);test('h VM uses same plan and exact metric states across all windows',()=>{for(let step=0;step<m.d.frames;step++){const p=D.plan(m,'h',step),v=R.fromPlan(m,step,p);a.deepEqual(v.ids,p.ids);for(const k of v.metrics)a.equal(k.state,m.d.tracks[p.id].metrics[k.code].state[step]);}});test('role requires matching host/group endpoint evidence',()=>{const p=D.plan(m,'h',390),v=R.fromPlan(m,390,p);a.ok(['P','D','P/D','OTHER'].includes(v.roleEvidence.role));const fake={...p,row:{...p.row,role:'OTHER'}};a.equal(R.fromPlan(m,390,fake).roleEvidence.role,'OTHER');const missing={...m,cat:{...m.cat,endpoints:[]}};a.equal(R.fromPlan(missing,390,p).roleEvidence.role,'OTHER')});test('offline/normal plan has no row promoted',()=>{a.equal(D.plan(m,'h',0).ids.length,0);a.equal(D.plan(m,'h',390,'','',true).ids.length,0)});
test('every rendered memory and storage animation resolves to a loaded keyframe',()=>{
 const p=D.plan(m,'h',390),ctx={model:m,step:390,chart:()=>'<figure></figure>',badge:s=>s,stateBadge:s=>s,color:s=>s,name:(col,id)=>m.map[col].get(id)?.name||'',cycling:false,icon:()=>''};
 const html=R.render(p,ctx,D.render(p,ctx));
 const refs=[...html.matchAll(/animation-name:([\w-]+)/g)].map(x=>x[1]);
 const css=fs.readFileSync(__dirname+'/../frontend/screen-masked/assets/masked03-r4.css','utf8');
 const definitions=new Set([...css.matchAll(/@keyframes\s+([\w-]+)/g)].map(x=>x[1]));
 a.ok(refs.length>0,'the approved memory/storage animations must remain present');
 const missing=[...new Set(refs.filter(x=>!definitions.has(x)))];
 a.deepEqual(missing,[],'rendered SVG animation references must match stylesheet keyframes');
});
