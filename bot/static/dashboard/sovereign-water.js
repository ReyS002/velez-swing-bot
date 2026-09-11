// Window-only weather: independent particles and slow ocean reflections.
// No network requests beyond the existing room plate; no trading state.
export function mountWater(root, roomSnapshot) {
  const weather=root.querySelector('.desk-weather');
  const canvas=document.createElement('canvas');canvas.className='desk-water';canvas.setAttribute('aria-hidden','true');weather.append(canvas);
  const ctx=canvas.getContext('2d');if(!ctx)return;
  const reduced=matchMedia('(prefers-reduced-motion: reduce)');
  const random=(a,b)=>a+Math.random()*(b-a);
  const streaks=Array.from({length:135},()=>({x:random(0,1672),y:random(-941,941),speed:random(160,480),length:random(3,13),alpha:random(.035,.13)}));
  const beads=Array.from({length:72},()=>({x:random(470,1640),y:random(110,520),r:random(1.4,3.8),speed:0,wait:random(0,16),trail:0}));
  const plate=new Image();let filename='',raf=0,last=0,elapsed=0,signature='';
  // Move the photographed water rather than drawing a few glints over a still sea.
  // The feathered ocean mask excludes the coast, palms and window mullions.
  const sea=document.createElement('canvas'),mask=document.createElement('canvas');
  sea.width=mask.width=1672;sea.height=mask.height=941;
  const seaCtx=sea.getContext('2d'),maskCtx=mask.getContext('2d');
  const shoreline=[[1292,306],[1510,306],[1510,462],[1455,471],[1340,455],[1293,443],[1257,439],[1170,420],[1100,402],[1065,391],[1150,382],[1258,365],[1258,324]];
  if(maskCtx){maskCtx.filter='blur(4px)';maskCtx.fillStyle='#fff';maskCtx.beginPath();shoreline.forEach(([x,y],i)=>i?maskCtx.lineTo(x,y):maskCtx.moveTo(x,y));maskCtx.closePath();maskCtx.fill();maskCtx.filter='none';maskCtx.clearRect(1265,0,24,941);}
  function resetBead(b){b.x=random(470,1640);b.y=random(100,190);b.r=random(1.4,3);b.wait=random(3,16);b.speed=0;b.trail=0;}
  function drop(b,dt){
    b.wait-=dt;b.r=Math.min(4.7,b.r+dt*.028);
    if(b.wait<0){b.speed=Math.min(38,b.speed+dt*5);b.y+=b.speed*dt;b.x+=Math.sin(b.y*.038)*dt*.6;b.trail=Math.min(23,b.trail+dt*4);}
    if(b.y>560)resetBead(b);
    if(b.trail){ctx.strokeStyle='rgba(204,221,231,.085)';ctx.lineWidth=.65;ctx.beginPath();ctx.moveTo(b.x,b.y-b.trail);ctx.lineTo(b.x,b.y);ctx.stroke();}
    ctx.save();ctx.beginPath();ctx.ellipse(b.x,b.y,b.r,b.r*(b.speed?1.45:1.14),0,0,Math.PI*2);ctx.clip();
    if(plate.complete&&plate.naturalWidth){ctx.globalAlpha=.55;ctx.drawImage(plate,(b.x-2*b.r)*plate.naturalWidth/1672,(b.y-2*b.r)*plate.naturalHeight/941,4*b.r*plate.naturalWidth/1672,4*b.r*plate.naturalHeight/941,b.x-b.r,b.y-1.5*b.r,2*b.r,3*b.r);ctx.globalAlpha=1;}
    const g=ctx.createRadialGradient(b.x-b.r*.4,b.y-b.r*.65,.1,b.x,b.y,b.r*1.5);g.addColorStop(0,'rgba(247,253,255,.65)');g.addColorStop(.24,'rgba(216,235,247,.13)');g.addColorStop(.65,'rgba(7,25,38,.10)');g.addColorStop(1,'rgba(201,227,243,.42)');ctx.fillStyle=g;ctx.fillRect(b.x-b.r,b.y-b.r*1.5,b.r*2,b.r*3);ctx.restore();
  }
  function ocean(t,night){
    if(seaCtx&&plate.complete&&plate.naturalWidth){
      seaCtx.clearRect(0,0,1672,941);
      const sx=plate.naturalWidth/1672,sy=plate.naturalHeight/941;
      // Waves travel shoreward, with increasing displacement toward the foreground.
      for(let y=300;y<485;y+=2){
        const depth=Math.max(0,(y-300)/185);
        const phase=y*.21-t*2.4;
        const dx=(Math.sin(phase)*2.8+Math.sin(y*.075+t*1.35)*1.3)*depth;
        const dy=(Math.sin(phase*.74)*2.1+Math.sin(y*.13-t*1.8)*1.2)*depth;
        seaCtx.drawImage(plate,(1040+dx)*sx,(y+dy)*sy,490*sx,2*sy,1040,y,490,2);
      }
      seaCtx.globalCompositeOperation='destination-in';seaCtx.drawImage(mask,0,0);seaCtx.globalCompositeOperation='source-over';
      ctx.drawImage(sea,0,0);
    }
    ctx.save();ctx.beginPath();[[1275,325],[1480,324],[1480,435],[1400,425],[1325,386],[1275,369]].forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.closePath();ctx.clip();
    // Small, broken specular crests follow the perspective of the distant water.
    for(let i=0;i<46;i++){const y=330+(i*17.13)%100,x=1275+(i*67.7)%210;const phase=t*.7+i*1.91;const a=(.5+.5*Math.sin(phase))*(night?.13:.2);ctx.strokeStyle=`rgba(${night?'255,201,146':'220,246,252'},${a})`;ctx.lineWidth=.45+(y-330)/180;ctx.beginPath();ctx.ellipse(x+Math.sin(phase*.3)*2,y+Math.sin(phase)*.65,3+(y-325)*.1,.35,0,Math.PI*.1,Math.PI*.8);ctx.stroke();}
    const x=1320+(t*.33)%115,y=350+Math.sin(t*.55)*.25;
    ctx.save();ctx.translate(x,y);ctx.rotate(Math.sin(t*.7)*.018);ctx.globalAlpha=night?.65:.8;
    ctx.fillStyle=night?'#d2baa0':'#e9e9dc';ctx.beginPath();ctx.moveTo(0,-10);ctx.lineTo(-.5,-1);ctx.lineTo(-4.5,-1.5);ctx.closePath();ctx.fill();ctx.fillStyle=night?'#ad9880':'#c7d1cd';ctx.beginPath();ctx.moveTo(1,-8);ctx.lineTo(5,-1);ctx.lineTo(1,-1);ctx.closePath();ctx.fill();ctx.strokeStyle='#655c50';ctx.lineWidth=.45;ctx.beginPath();ctx.moveTo(0,-11);ctx.lineTo(0,1);ctx.stroke();ctx.fillStyle='#383e3e';ctx.beginPath();ctx.moveTo(-5,0);ctx.lineTo(6,0);ctx.lineTo(3,2);ctx.lineTo(-3,2);ctx.closePath();ctx.fill();ctx.restore();ctx.restore();
  }
  function draw(now){raf=0;if(now-last<32){raf=requestAnimationFrame(draw);return;}const dt=Math.min((now-last)/1000||0,.05);last=now;elapsed+=dt;ctx.clearRect(0,0,1672,941);
    if(roomSnapshot().id==='pacific')ocean(elapsed,root.dataset.theme==='night');
    if(root.dataset.rain==='on'){
      for(const p of streaks){p.y+=p.speed*dt;p.x-=p.speed*.055*dt;if(p.y>941){p.y=random(-150,-10);p.x=random(0,1672);}ctx.strokeStyle=`rgba(210,229,241,${p.alpha})`;ctx.lineWidth=.45;ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineTo(p.x+p.length*.055,p.y-p.length);ctx.stroke();}
      for(const b of beads)drop(b,dt);
    }
    raf=requestAnimationFrame(draw);
  }
  function sync(){
    // Body classes are touched by the chart loop even when their values are unchanged.
    // Never reset the animation clock for an unrelated or identical mutation.
    const identity=[document.hidden,reduced.matches,innerWidth>760,root.dataset.ambience,root.dataset.paused,root.dataset.ready,root.dataset.room,root.dataset.theme,root.dataset.rain,document.body.classList.contains('pro-console-open'),document.body.classList.contains('sovereign-chart-expanded'),document.body.dataset.roomAsset,Math.min(devicePixelRatio||1,2)].join('|');
    if(identity===signature)return;signature=identity;
    if(raf)cancelAnimationFrame(raf);raf=0;
    const file=document.body.dataset.roomAsset;if(file&&file!==filename&&file!=='unavailable'){filename=file;plate.src='/dashboard/assets/sovereign/'+file;}
    const ratio=Math.min(devicePixelRatio||1,2),w=Math.round(1672*ratio),h=Math.round(941*ratio);
    if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;ctx.setTransform(ratio,0,0,ratio,0,0);}
    const active=!document.hidden&&!reduced.matches&&innerWidth>760&&root.dataset.ambience==='on'&&root.dataset.paused!=='true'&&root.dataset.ready==='true'&&!document.body.classList.contains('pro-console-open')&&!document.body.classList.contains('sovereign-chart-expanded');
    if(active&&(root.dataset.rain==='on'||roomSnapshot().id==='pacific')){last=performance.now();raf=requestAnimationFrame(draw);}else ctx.clearRect(0,0,1672,941);
  }
  new MutationObserver(sync).observe(root,{attributes:true,attributeFilter:['data-paused','data-rain','data-ambience','data-ready','data-room','data-theme']});
  new MutationObserver(sync).observe(document.body,{attributes:true,attributeFilter:['class']});
  document.addEventListener('visibilitychange',sync);window.addEventListener('resize',sync);reduced.addEventListener('change',sync);sync();
}
