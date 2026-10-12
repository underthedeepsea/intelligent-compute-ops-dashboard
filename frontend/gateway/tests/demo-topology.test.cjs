const {test}=require('node:test'),assert=require('node:assert/strict'),D=require('../demo-topology.js');
function fixture(){const ids=['team:t','business:b','key:k','model:m','service:s','endpoint:e','pod:p','node:c:DEMO:node%2F1','cluster:c','pd_group:d'];return {nodes:ids.map(id=>({id,type:id.split(':')[0],name:id})),edges:[['team:t','business:b','owns'],['team:t','key:k','owns'],['business:b','key:k','owns'],['key:k','model:m','authorizes'],['model:m','service:s','serves'],['business:b','service:s','depends_on'],['service:s','endpoint:e','serves'],['endpoint:e','cluster:c','runs_in'],['endpoint:e','pd_group:d','member_of_pd'],['pod:p','endpoint:e','backs_endpoint'],['pod:p','node:c:DEMO:node%2F1','scheduled_on'],['node:c:DEMO:node%2F1','cluster:c','runs_in']].map(([source,target,type])=>({source,target,type}))};}
test('eight populated columns retain canonical service/PD/Pod objects and all edge evidence; graph immutable',()=>{
 const g=fixture(),before=JSON.stringify(g),v=D.project(g);
 assert.deepEqual(v.types,[['team'],['business'],['key','model'],['service'],['pd_group'],['endpoint'],['cluster'],['pod','node']]);
 assert.equal(new Set(v.nodes.map(n=>n.id)).size,g.nodes.length);assert.deepEqual(v.hidden,[]);
 const covered=new Set([...v.primary,...v.secondary].flatMap(e=>e.evidence));assert.equal(covered.size,g.edges.length);
 assert.equal(JSON.stringify(g),before);
});
test('business depends directly on visible service without Key; no invented collapsed model route',()=>{
 const g=fixture(),v=D.project(g);
 assert.deepEqual(v.primary.find(e=>e.type==='depends_on').evidence,[5]);
 assert.ok(v.primary.some(e=>e.source==='model:m'&&e.target==='service:s'));
 assert.ok(v.primary.some(e=>e.source==='service:s'&&e.target==='endpoint:e'));
 assert.ok(v.primary.some(e=>e.source==='node:c:DEMO:node%2F1'&&e.target==='cluster:c'));
 assert.equal(v.primary.some(e=>e.collapsedPath),false);
 g.nodes=g.nodes.filter(n=>n.type!=='key');g.edges=g.edges.filter(e=>e.source!=='key:k'&&e.target!=='key:k');
 const direct=D.project(g).primary.find(e=>e.type==='depends_on');assert.equal(direct.source,'business:b');assert.equal(direct.target,'service:s');
 g.edges=g.edges.filter(e=>e.type!=='depends_on');assert.equal(D.project(g).primary.some(e=>e.type==='depends_on'),false);
});
test('all registered endpoints and their evidenced nodes survive names/roles without representative folding',()=>{
 const g=fixture();for(let i=2;i<=4;i++){g.nodes.push({id:'endpoint:e'+i,type:'endpoint',name:'untrusted name P D '+i},{id:'pod:p'+i,type:'pod',name:'p'+i},{id:'node:n'+i,type:'node',name:'n'+i});g.edges.push({source:'service:s',target:'endpoint:e'+i,type:'serves'},{source:'endpoint:e'+i,target:'cluster:c',type:'runs_in'},{source:'pod:p'+i,target:'endpoint:e'+i,type:'backs_endpoint'},{source:'pod:p'+i,target:'node:n'+i,type:'scheduled_on'},{source:'node:n'+i,target:'cluster:c',type:'runs_in'});}
 const before=JSON.stringify(g),v=D.project(g);
 assert.deepEqual(v.nodes.filter(n=>n.type==='endpoint').map(n=>n.id),['endpoint:e','endpoint:e2','endpoint:e3','endpoint:e4']);
 assert.deepEqual(v.nodes.filter(n=>n.type==='node').map(n=>n.id),['node:c:DEMO:node%2F1','node:n2','node:n3','node:n4']);
 for(const edge of v.primary)assert.deepEqual(g.edges[edge.evidence[0]],{source:edge.source,target:edge.target,type:edge.type});
 assert.equal(JSON.stringify(g),before);
});
test('dynamic measured columns preserve direct skip-column routes and real endpoint geometry',()=>{
 const g=fixture(),v=D.project(g),sizes=Object.fromEntries(g.nodes.map((n,i)=>[n.id,{height:80+i*13}])),l=D.layout(v,sizes,1350);
 assert.equal(l.columnX.length,8);assert.equal(l.rects.size,g.nodes.length);assert.equal(l.routes.length,v.primary.length);
 for(const edge of l.routes){const a=l.rects.get(edge.source),b=l.rects.get(edge.target);assert.equal(edge.points[0][1],a.y+a.height/2);assert.equal(edge.points[3][1],b.y+b.height/2);assert.deepEqual(edge.evidence,v.primary.find(p=>p.index===edge.index).evidence);}
 const direct=l.routes.find(e=>e.type==='depends_on');assert.equal(direct.source,'business:b');assert.equal(direct.target,'service:s');assert.ok(l.rects.get(direct.target).x-l.rects.get(direct.source).x>l.columnX[1]-l.columnX[0]);
 for(const [id,r] of l.rects){assert.equal(r.height,sizes[id].height);assert.ok(r.x>=0&&r.y>=0&&r.x+r.width<=l.width&&r.y+r.height<=l.height);}
 assert.equal(D.layout(D.project({nodes:[],edges:[]})).types.length,0);
});
module.exports={fixture};
