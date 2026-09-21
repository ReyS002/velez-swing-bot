// Cape Canaveral ambience: local presentation only; no mission or trading API.
const KEY = 'sovereign-cape-launch';
export const LAUNCH_DURATION = 64;
export function nextLaunchDelay(random = Math.random) { return 600000 + Math.min(1, Math.max(0, random())) * 300000; }
export function launchFrame(seconds) {
  const t = Math.max(0, seconds);
  if (t < 3) return { phase: 'ignition', rise: 0, flame: t / 3, smoke: 1, rocket: true };
  if (t < 24) { const a = t - 3; return { phase: 'ascent', rise: 1.15 * a * a, flame: 1, smoke: 1, rocket: true }; }
  if (t < LAUNCH_DURATION) return { phase: 'clearing', rise: t < 60 ? 520 : 0, flame: 0, smoke: Math.pow(1 - (t - 24) / 40, 1.4), rocket: t >= 60, rocketOpacity: Math.max(0, (t - 60) / 4) };
  return { phase: 'idle', rise: 0, flame: 0, smoke: 0, rocket: true };
}

export function mountCapeLaunch({ roomRect, roomSnapshot }) {
  if (document.getElementById('cape-launch-canvas')) return;
  const canvas = document.createElement('canvas');
  canvas.id = 'cape-launch-canvas'; canvas.setAttribute('aria-hidden', 'true');
  document.body.append(canvas);
  const ctx = canvas.getContext('2d'); if (!ctx) return;
  const vehicle = new Image();vehicle.src='/dashboard/assets/sovereign/cape-rocket.png';vehicle.onload=()=>draw();
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  let enabled = false; try { enabled = localStorage.getItem(KEY) === 'on'; } catch {}
  let remaining = nextLaunchDelay(), elapsed = null, raf = 0, idleTimer = 0, previous = 0, disposed = false;
  let activeSignature = '', visible = false;
  const grid = document.querySelector('.sovereign-tools-grid');
  const controls = document.createElement('section'); controls.className = 'cape-launch-controls';
  controls.innerHTML = '<div><strong>Cape Canaveral launches</strong><span>Optional ambient effect · every 10–15 minutes</span></div><button id="cape-launch-toggle" type="button" role="switch" aria-checked="false">Launch animation: Off</button><button id="cape-launch-preview" type="button">Preview launch</button><small id="cape-launch-status" role="status"></small>';
  grid?.append(controls);
  const toggle = controls.querySelector('#cape-launch-toggle'), preview = controls.querySelector('#cape-launch-preview'), status = controls.querySelector('#cape-launch-status');
  // One deterministic billowing smoke field, shaded as lit water vapor rather
  // than screen-space circles. Drawn only during a launch, then dispersed.
  let seed = 872341;
  const random = () => { seed = (1664525 * seed + 1013904223) >>> 0; return seed / 4294967296; };
  const particles = Array.from({ length: 150 }, (_, i) => ({
    birth: (i / 150) * 19, drift: 2 + random() * 7, lift: 1 + random() * 2.6,
    radius: 3 + random() * 8, spread: (random() - .28) * 2, phase: random() * 6.28,
    shade: Math.floor(178 + random() * 55), alpha: .18 + random() * .27,
  }));
  // Pre-render textured lobes once. Their soft shadows and small internal lobes
  // remain visible at the launch site's distant scale without per-frame filters.
  const puffs = Array.from({ length: 5 }, (_, index) => {
    const puff = document.createElement('canvas'); puff.width = puff.height = 128;
    const c = puff.getContext('2d');
    for (let i = 0; i < 28; i++) {
      const x = 64 + (random() - .5) * 53, y = 64 + (random() - .5) * 48, r = 12 + random() * 29;
      const gradient = c.createRadialGradient(x - r * .28, y - r * .35, 0, x, y, r);
      const level = 204 + index * 5;
      gradient.addColorStop(0, `rgba(${level + 20},${level + 17},${level + 13},.48)`);
      gradient.addColorStop(.54, `rgba(${level},${level},${level + 4},.32)`);
      gradient.addColorStop(1, 'rgba(140,155,174,0)');
      c.fillStyle = gradient; c.fillRect(x-r, y-r, r*2, r*2);
    }
    return puff;
  });
  function canAnimate() {
    return roomSnapshot().id === 'cape' && !document.hidden && !reduced.matches && document.body.dataset.objectMotion !== 'off'
      && !document.body.classList.contains('pro-console-open') && !document.body.classList.contains('sovereign-chart-expanded')
      && document.body.dataset.roomAsset === `cape-${roomSnapshot().theme}-clean.png`;
  }
  function updateControls() {
    toggle.setAttribute('aria-checked', String(enabled)); toggle.textContent = `Launch animation: ${enabled ? 'On' : 'Off'}`;
    preview.disabled = !canAnimate() || elapsed !== null;
    status.textContent = reduced.matches ? 'Paused for reduced motion.' : document.body.dataset.objectMotion === 'off' ? 'Enable Object motion to preview launches.' : roomSnapshot().id !== 'cape' ? 'Select Cape Canaveral to preview a launch.' : elapsed !== null ? 'Launch in progress · smoke will clear naturally.' : enabled ? 'Next launch after 10–15 minutes of visible room time.' : 'Automatic launches off. Preview once whenever you like.';
  }
  function begin() {
    if (!canAnimate() || elapsed !== null) return false;
    elapsed = 0; remaining = nextLaunchDelay(); updateControls(); sync(); return true;
  }
  toggle.addEventListener('click', () => {
    enabled = !enabled; try { localStorage.setItem(KEY, enabled ? 'on' : 'off'); } catch {}
    remaining = nextLaunchDelay(); if (!enabled) elapsed = null;
    updateControls(); sync();
  });
  preview.addEventListener('click', () => {
    if (!begin()) return;
    document.getElementById('sovereign-tools').hidden = true;
    document.querySelector('[data-desk-action="tools"]')?.setAttribute('aria-expanded', 'false');
    document.querySelector('[data-desk-action="tools"]')?.focus({preventScroll:true});
  });
  function layout() {
    const r = roomRect(); Object.assign(canvas.style, { left: r.left+'px', top:r.top+'px', width:r.width+'px', height:r.height+'px' });
    const ratio = Math.min(devicePixelRatio || 1, 2);
    if (canvas.width !== Math.round(1672*ratio)) { canvas.width = Math.round(1672*ratio); canvas.height = Math.round(941*ratio); }
    ctx.setTransform(ratio,0,0,ratio,0,0);
  }
  function windowClip() {
    // Actual glass panes: frame bars stay in front of the rocket and plume.
    ctx.beginPath(); ctx.moveTo(824,112); ctx.lineTo(1225,96); ctx.lineTo(1225,489); ctx.lineTo(978,479); ctx.lineTo(978,375); ctx.lineTo(824,375); ctx.closePath();
    ctx.moveTo(1243,93);ctx.lineTo(1494,69);ctx.lineTo(1494,533);ctx.lineTo(1243,510);ctx.closePath(); ctx.clip();
  }
  function rocket(x,y,alpha=1) {
    ctx.save();ctx.translate(x,y);ctx.globalAlpha=alpha;
    if(vehicle.complete&&vehicle.naturalWidth){ctx.globalAlpha=alpha*.88;ctx.drawImage(vehicle,399,18,139,1600,-2.6,-56,5.2,56);ctx.restore();return;}
    const metal=ctx.createLinearGradient(-3,0,3,0);metal.addColorStop(0,'#a3acb7');metal.addColorStop(.33,'#f7f2e4');metal.addColorStop(.68,'#fffdf3');metal.addColorStop(1,'#687887');
    ctx.fillStyle=metal;ctx.beginPath();ctx.moveTo(-2.6,0);ctx.lineTo(-2.6,-42);ctx.quadraticCurveTo(-3.8,-49,0,-56);ctx.quadraticCurveTo(3.8,-49,2.6,-42);ctx.lineTo(2.6,0);ctx.closePath();ctx.fill();
    ctx.fillStyle='#17242f';ctx.fillRect(-2.6,-34,5.2,6);ctx.fillRect(-2.1,-2,4.2,2.5);
    ctx.strokeStyle='rgba(120,137,151,.65)';ctx.lineWidth=.4;ctx.beginPath();ctx.moveTo(-2.6,-43);ctx.lineTo(2.6,-43);ctx.moveTo(-2.6,-18);ctx.lineTo(2.6,-18);ctx.stroke();
    ctx.restore();
  }
  function flame(x,y,t,amount) {
    ctx.save();ctx.globalCompositeOperation='screen';
    const pulse=.94+.06*Math.sin(t*83),length=(16+Math.min(t,12)*2.3)*amount*pulse;
    const glow=ctx.createRadialGradient(x,y+3,0,x,y+3,21*amount+1);
    glow.addColorStop(0,'rgba(255,218,127,.7)');glow.addColorStop(.25,'rgba(255,124,35,.18)');glow.addColorStop(1,'rgba(255,90,20,0)');ctx.fillStyle=glow;ctx.fillRect(x-25,y-23,50,60);
    const exhaust=ctx.createLinearGradient(x,y,x,y+length);exhaust.addColorStop(0,'#fffff4');exhaust.addColorStop(.18,'#fffacc');exhaust.addColorStop(.6,'#ffc76c');exhaust.addColorStop(1,'rgba(255,136,45,0)');
    ctx.fillStyle=exhaust;ctx.beginPath();ctx.moveTo(x-2,y);ctx.bezierCurveTo(x-4,y+length*.3,x-1.5,y+length*.8,x+Math.sin(t*37),y+length);ctx.bezierCurveTo(x+2,y+length*.7,x+4,y+length*.3,x+2,y);ctx.fill();ctx.restore();
  }
  function draw() {
    ctx.clearRect(0,0,1672,941);
    if(roomSnapshot().id!=='cape')return;
    ctx.save();windowClip();const t=elapsed??0,frame=elapsed===null?launchFrame(64):launchFrame(t),night=roomSnapshot().theme==='night';
    const x=1096+Math.max(0,frame.rise-120)*.033, y=333-frame.rise;
    if(elapsed!==null){
      for(let i=0;i<particles.length;i++){
        const p=particles[i],age=t-p.birth;if(age<0)continue;
        const r=p.radius+Math.min(age,35)*.78,px=1096+age*p.drift*p.spread,py=334-Math.min(age*p.lift,48)+Math.sin(p.phase+age*.13)*3;
        ctx.globalAlpha=p.alpha*frame.smoke*(night?.95:.8)*Math.min(age/1.8,1);
        ctx.drawImage(puffs[i%5],px-r*1.3,py-r,r*2.6,r*2);
      }
      ctx.globalAlpha=1;
      if(frame.phase==='ascent'){
        for(let i=0;i<42;i++){
          const trailAge=i*.23,pt=Math.max(3,t-trailAge),historic=launchFrame(pt),ty=333-historic.rise;
          const r=2.5+i*.29,tx=1096+Math.max(0,historic.rise-120)*.033+Math.sin(i*1.9+t)*i*.035;
          if(ty<y+10)continue;
          ctx.globalAlpha=.43*(1-i/46);ctx.drawImage(puffs[i%5],tx-r,ty-r,r*2,r*3);
        }
      }
      ctx.globalAlpha=1;if(frame.flame>0)flame(x,y,t,frame.flame);
    }
    if(frame.rocket)rocket(x,y,frame.rocketOpacity??1);
    ctx.restore();canvas.dataset.phase=frame.phase;canvas.dataset.elapsed=(elapsed??0).toFixed(2);
  }
  function tick(now) {
    raf=0;idleTimer=0;if(disposed||!canAnimate())return;
    const dt=Math.min(Math.max((now-previous)/1000,0),elapsed===null?1.2:.1);previous=now;
    if(elapsed!==null){elapsed+=dt;if(elapsed>=LAUNCH_DURATION){elapsed=null;remaining=nextLaunchDelay();updateControls();}}
    else if(enabled){remaining-=dt*1000;if(remaining<=0){elapsed=0;remaining=nextLaunchDelay();updateControls();}}
    if(elapsed!==null){draw();raf=requestAnimationFrame(tick);}
    else {if(canvas.dataset.phase!=='idle')draw();if(enabled)idleTimer=setTimeout(()=>tick(performance.now()),1000);}
  }
  function sync() {
    layout();const next=roomSnapshot();
    const signature=[next.id,next.theme,canAnimate(),enabled,elapsed!==null].join('|');
    if(signature!==activeSignature){
      if(raf)cancelAnimationFrame(raf);raf=0;clearTimeout(idleTimer);idleTimer=0;
      if(next.id!=='cape'){elapsed=null;remaining=nextLaunchDelay();}
      activeSignature=signature;
      if(!disposed&&canAnimate()&&(enabled||elapsed!==null)){previous=performance.now();if(elapsed!==null)raf=requestAnimationFrame(tick);else idleTimer=setTimeout(()=>tick(performance.now()),1000);}
    }
    visible=next.id==='cape';canvas.hidden=!visible;draw();updateControls();
  }
  for(const type of ['desk:layout','desk:roomchange','desk:motionchange','visibilitychange'])document.addEventListener(type,sync);
  window.addEventListener('resize',sync);reduced.addEventListener('change',sync);
  new MutationObserver(sync).observe(document.body,{attributes:true,attributeFilter:['class','data-room-asset']});
  // Read-only diagnostics for runtime verification. Timings are not adjustable via UI.
  window.__capeLaunch={snapshot:()=>({enabled,phase:canvas.dataset.phase,elapsed,remaining,active:Boolean(raf||idleTimer),room:roomSnapshot().id}),preview:begin};
  window.addEventListener('pagehide',()=>{disposed=true;if(raf)cancelAnimationFrame(raf);clearTimeout(idleTimer);raf=0;idleTimer=0;});
  window.addEventListener('pageshow',()=>{disposed=false;activeSignature='';sync();});
  sync();
}
