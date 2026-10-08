/* Layout uses measured rectangles. Routes only use empty column gutters and the
 * header corridor; display aggregation never creates a new domain relationship. */
(function(root){'use strict';
const order=['cluster','node','deployment_summary','pod','runtime_member','endpoint','pd_group','service','model','key','business','team'];
function project(graph,expanded=new Set()){
 const folded=['pod','runtime_member','endpoint'].filter(t=>!expanded.has(t));
 const groups=folded.map(type=>({id:'summary:'+type,type:type==='endpoint'?'endpoint':'deployment_summary',name:(type==='endpoint'?'Endpoint':'Pod')+' 部署汇总',members:graph.nodes.filter(n=>n.type===type),summaryType:type})).filter(g=>g.members.length);
 const mapping=new Map(groups.flatMap(g=>g.members.map(n=>[n.id,g.id])));
 const nodes=graph.nodes.filter(n=>!mapping.has(n.id)).concat(groups),edges=[];
 for(const edge of graph.edges){const source=mapping.get(edge.source)||edge.source,target=mapping.get(edge.target)||edge.target;if(source===target)continue;let item=edges.find(e=>e.source===source&&e.target===target);if(!item){item={source,target,originals:[]};edges.push(item);}item.originals.push(edge);}
 return {nodes,edges};
}
function layout(nodes,sizes={}){
 const types=[...new Set(nodes.map(n=>n.type))].sort((a,b)=>(order.indexOf(a)<0?99:order.indexOf(a))-(order.indexOf(b)<0?99:order.indexOf(b))),rects=new Map();let x=30,height=560;
 types.forEach(type=>{const members=nodes.filter(n=>n.type===type),width=Math.max(174,...members.map(n=>sizes[n.id]?.width||174));let y=140;for(const n of members){const h=sizes[n.id]?.height||100;rects.set(n.id,{x,y,width,height:h,type});y+=h+30;}height=Math.max(height,y+30);x+=width+76;});
 return {rects,types,width:Math.max(820,x),height};
}
function route(edge,rects,index=0){
 const a=rects.get(edge.source),b=rects.get(edge.target);if(!a||!b)return null;
 const forward=b.x>a.x,same=b.x===a.x,ax=forward||same?a.x+a.width:a.x,bx=forward?b.x:b.x+b.width;
 const ay=a.y+a.height/2,by=b.y+b.height/2,ag=ax+(forward||same?20:-20),bg=bx+(forward?-20:20),lane=48+(index%12)*6;
 const adjacent=!same&&![...rects.values()].some(r=>r.x>Math.min(a.x,b.x)&&r.x<Math.max(a.x,b.x));
 const middle=(ax+bx)/2;
 const points=adjacent?[[ax,ay],[middle,ay],[middle,by],[bx,by]]:[[ax,ay],[ag,ay],[ag,lane],[bg,lane],[bg,by],[bx,by]];
 return {...edge,points,d:points.map((p,i)=>(i?'L':'M')+p.join(' ')).join(' ')};
}
function collisions(routed,rects){const hits=[];for(const [id,r] of rects){if(id===routed.source||id===routed.target)continue;for(let i=1;i<routed.points.length;i++){const [a,b]=[routed.points[i-1],routed.points[i]];if(a[0]===b[0]?a[0]>r.x&&a[0]<r.x+r.width&&Math.max(a[1],b[1])>r.y&&Math.min(a[1],b[1])<r.y+r.height:a[1]>r.y&&a[1]<r.y+r.height&&Math.max(a[0],b[0])>r.x&&Math.min(a[0],b[0])<r.x+r.width){hits.push(id);break;}}}return hits;}
const api={order,project,layout,route,collisions};if(typeof module!=='undefined')module.exports=api;else root.GatewayGraph=api;
})(typeof window==='undefined'?globalThis:window);
