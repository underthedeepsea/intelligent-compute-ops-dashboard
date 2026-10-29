/* Presentation-only smoothing of ALREADY REDACTED ranks, not measured values.
   Gaussian low-pass within each contiguous visible run, then bounded cubic
   interpolation. Source tracks, timestamps and rule states are never mutated.
   This is a smoothed relative trend, NOT an exact plot of every sample. */
(function(root){'use strict';
function slopes(points){
 const n=points.length;if(n<2)return n?[0]:[];
 const h=[],d=[];for(let i=0;i<n-1;i++){h.push(points[i+1].x-points[i].x);d.push((points[i+1].y-points[i].y)/h[i]);}
 if(n===2)return [d[0],d[0]];
 const m=Array(n).fill(0);
 for(let i=1;i<n-1;i++){
  if(d[i-1]*d[i]<=0)continue;
  const w1=2*h[i]+h[i-1],w2=h[i]+2*h[i-1];m[i]=(w1+w2)/(w1/d[i-1]+w2/d[i]);
 }
 const end=(h0,h1,d0,d1)=>{let v=((2*h0+h1)*d0-h0*d1)/(h0+h1);if(Math.sign(v)!==Math.sign(d0))v=0;else if(Math.sign(d0)!==Math.sign(d1)&&Math.abs(v)>3*Math.abs(d0))v=3*d0;return v;};
 m[0]=end(h[0],h[1],d[0],d[1]);m[n-1]=end(h[n-2],h[n-3],d[n-2],d[n-3]);return m;
}
function smoothRanks(values){
 if(!Array.isArray(values)||values.some(v=>!Number.isFinite(v)||v<0||v>8))throw new Error('Invalid public rank');
 const n=values.length;if(n<3)return values.slice();
 // Fixed visual bandwidth. It is not a health threshold or data-driven state.
 // Reflection avoids endpoint spikes; samples beyond the visible history are NEVER read.
 const sigma=Math.max(1.35,Math.min(8,n*.045)),radius=Math.ceil(sigma*4);
 const weights=Array.from({length:2*radius+1},(_,i)=>Math.exp(-.5*((i-radius)/sigma)**2));
 const total=weights.reduce((a,b)=>a+b,0);
 const reflect=i=>{while(i<0||i>=n)i=i<0?-i-1:2*n-i-1;return i;};
 const lo=Math.min(...values),hi=Math.max(...values);
 return values.map((_,i)=>Math.max(lo,Math.min(hi,weights.reduce((sum,w,j)=>sum+w*values[reflect(i+j-radius)],0)/total)));
}
function segments(shape,states,width=600,height=100,pad=8){
 if(typeof shape!=='string'||typeof states!=='string'||shape.length!==states.length||/[^abcdefghi-]/.test(shape)||/[^GWRUO]/.test(states))throw new Error('Invalid safe shape');
 if(![width,height,pad].every(Number.isFinite)||pad<0||width<=2*pad||height<=2*pad)throw new Error('Invalid viewport');
 const pieces=[];let run=[],latest=null;
 const flush=()=>{
  if(!run.length)return;
  const ranks=smoothRanks(run.map(i=>shape.charCodeAt(i)-97));
  const points=run.map((index,j)=>({x:pad+index*(width-2*pad)/Math.max(1,shape.length-1),y:height-pad-ranks[j]/8*(height-2*pad),state:states[index],index}));
  if(run.at(-1)===shape.length-1)latest=points.at(-1);
  const m=slopes(points);
  for(let i=0;i<points.length-1;i++){const a=points[i],b=points[i+1],h=b.x-a.x;pieces.push({state:b.state,start:a,end:b,c1:{x:a.x+h/3,y:a.y+h*m[i]/3},c2:{x:b.x-h/3,y:b.y-h*m[i+1]/3}});}
  run=[];
 };
 for(let i=0;i<shape.length;i++){if(shape[i]==='-')flush();else run.push(i);}flush();
 return {pieces,latest};
}
function paths(pieces){
 const f=n=>Number(n.toFixed(3)),text=p=>`${f(p.x)} ${f(p.y)}`;
 const out=[];
 for(const s of pieces){let prev=out.at(-1);const command=`C${text(s.c1)} ${text(s.c2)} ${text(s.end)}`;
  if(prev&&prev.state===s.state&&prev.lastIndex===s.start.index){prev.d+=command;prev.lastIndex=s.end.index;}
  else out.push({state:s.state,d:`M${text(s.start)}${command}`,lastIndex:s.end.index});
 }return out;
}
const api=Object.freeze({slopes,smoothRanks,segments,paths});if(typeof module!=='undefined')module.exports=api;else root.MaskedCurves=api;
})(typeof window==='undefined'?globalThis:window);
