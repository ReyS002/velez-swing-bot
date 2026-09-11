/* Room instruments consume existing snapshots. They never submit orders or fetch broker data. */
const CITIES = [
  ["New York", "America/New_York"], ["London", "Europe/London"],
  ["Tokyo", "Asia/Tokyo"], ["Dubai", "Asia/Dubai"],
];
const LAYOUTS = {
  media: {clock:null,accent:null,window:null},
  pacific:{clock:null,accent:null,window:"polygon(30% 18%,100% 0,100% 62%,31% 53%)"},
  tokyo:{clock:null,accent:null,window:"polygon(27% 20%,100% 0,100% 56%,27% 49%)"},
  manhattan:{clock:null,accent:null,window:"polygon(35% 16%,100% 0,100% 63%,35% 53%)"},
  dubai:{clock:null,accent:null,window:"polygon(35% 18%,100% 0,100% 62%,35% 53%)"},
};
const ACCENTS = {
  media:[0,70,345,490,"Brass architectural miniature"],
  pacific:[370,255,470,300,"Koa keepsake box and lava stone"],
  manhattan:[1360,150,370,400,"Exchange bell"],
  dubai:[1770,65,400,490,"Brass astrolabe"],
};
function readSetting(key,fallback){try{return localStorage.getItem(key)??fallback;}catch{return fallback;}}
function saveSetting(key,value){try{localStorage.setItem(key,value);}catch{/* storage may be unavailable */}}
export function mountRoomEnhancements({roomRect,roomSnapshot,open,assetsReady}) {
  if(document.querySelector("#desk-enhancements"))return;
  const root=document.createElement("div");root.id="desk-enhancements";root.className="desk-enhancements";
  root.innerHTML=`<div class="desk-weather" aria-hidden="true"><div class="desk-clouds"></div><svg class="desk-aircraft" viewBox="0 0 100 30"><defs><linearGradient id="aircraft-metal" x2="0" y2="1"><stop stop-color="#e0e6e9"/><stop offset=".45" stop-color="#aab7bf"/><stop offset="1" stop-color="#43505a"/></linearGradient></defs><path fill="url(#aircraft-metal)" d="M3 18L12 17 6 3 12 4 25 16 65 15 80 14Q92 14 98 19Q100 22 87 23L28 23 17 25 8 24Z"/><path fill="#647580" d="M41 19L26 29 36 29 63 20ZM39 16L31 8 38 8 59 17Z"/><path fill="#283c49" d="M82 16L88 17 91 19H82Z"/><path stroke="#344754" stroke-width="1.4" stroke-dasharray="2 2" d="M30 18H76"/><ellipse cx="48" cy="24" rx="6" ry="2" fill="#64717a"/><circle cx="47" cy="21" r=".7" fill="#edcebb"/></svg><div class="desk-rain"></div><div class="desk-rain-beads"></div><div class="desk-city-glints"></div></div>
    <div class="desk-projection" aria-hidden="true"></div><div class="desk-shelf-light" aria-hidden="true"></div>
    <div class="desk-instrument desk-session-clock" role="group" aria-label="World clocks; select a city for market sessions">${CITIES.map(([name],i)=>`<button type="button" data-city="${i}" aria-label="${name} time and market sessions"><span class="clock-face"><i class="clock-hour"></i><i class="clock-minute"></i><b></b></span><span class="clock-city">${name}</span></button>`).join("")}</div>
    <div class="desk-regional-accent" role="img"></div>`;
  document.body.append(root);
  const q=s=>root.querySelector(s);
  let motion=readSetting("sovereign-ambience","on"), rain=readSetting("sovereign-rain","off");
  // A fresh arrangement per page load; the saved Off setting always wins.
  const beads=q(".desk-rain-beads");
  for(let i=0;i<44;i++){const bead=document.createElement("i");const size=1.5+Math.random()*3.5;bead.style.cssText=`left:${30+Math.random()*69}%;top:${9+Math.random()*46}%;width:${size}px;height:${size*(1.1+Math.random()*.5)}px;--bead-delay:${-Math.random()*34}s;--bead-duration:${24+Math.random()*28}s`;beads.append(bead);}
  const reduced=matchMedia("(prefers-reduced-motion: reduce)");
  let timer=null;
  function canMove(){return !reduced.matches&&!document.hidden&&document.body.dataset.objectMotion!=="off";}
  function place(el,box){const r=roomRect();Object.assign(el.style,{left:r.left+box[0]*r.width/100+"px",top:r.top+box[1]*r.height/100+"px",width:box[2]*r.width/100+"px",height:box[3]*r.height/100+"px"});}
  function layout(){
    const scene=roomSnapshot(), p=LAYOUTS[scene.id],r=roomRect();
    root.dataset.ready=String(assetsReady?.()!==false);
    root.dataset.room=scene.id;root.dataset.theme=scene.theme;
    const clock=q(".desk-session-clock");clock.hidden=!p.clock;if(p.clock)place(clock,p.clock);
    const accent=q(".desk-regional-accent");
    accent.hidden=!p.accent;
    if(p.accent){
      place(accent,p.accent);
      const [x,y,w,h,label]=ACCENTS[scene.id];
      accent.innerHTML=`<svg viewBox="${x} ${y} ${w} ${h}" aria-hidden="true"><image width="2172" height="724" href="/dashboard/assets/sovereign/regional-accents-v1.png"/></svg>`;
      accent.setAttribute("aria-label",label);
    }else{accent.replaceChildren();accent.removeAttribute("aria-label");}
    Object.assign(q(".desk-weather").style,{left:r.left+"px",top:r.top+"px",width:r.width+"px",height:r.height+"px",clipPath:p.window||"inset(100%)"});
    Object.assign(q(".desk-projection").style,{left:"36vw",top:innerHeight-85+"px",width:"28vw",height:"28px"});
    root.style.setProperty("--instrument-scale",String(r.width/1672));
    q(".desk-shelf-light").classList.remove("lit");
  }
  function setMotion(){root.dataset.ambience=motion;root.dataset.rain=rain;root.dataset.paused=String(!canMove());clearInterval(timer);timer=null;if(!document.hidden){tick();timer=setInterval(tick,30000);}}
  function tick(){
    const now=new Date();
    CITIES.forEach(([name,zone],i)=>{const parts=new Intl.DateTimeFormat("en-GB",{timeZone:zone,hour:"2-digit",minute:"2-digit",hourCycle:"h23"}).formatToParts(now);const h=Number(parts.find(p=>p.type==="hour").value),m=Number(parts.find(p=>p.type==="minute").value);const b=q(`[data-city="${i}"]`);b.querySelector(".clock-hour").style.transform=`rotate(${h%12*30+m/2}deg)`;b.querySelector(".clock-minute").style.transform=`rotate(${m*6}deg)`;b.title=`${name} · ${String(h).padStart(2,"0")}:${String(m).padStart(2,"0")} local time. Open sessions and calendar.`;b.setAttribute("aria-label",b.title);});
  }
  q(".desk-session-clock").addEventListener("click",e=>{const b=e.target.closest("[data-city]");if(b){document.body.dataset.sessionCity=b.dataset.city;open("clock",b);}});
  function shelf(e){const target=e.target.closest?.('[data-object-id="vault"],[data-object-id="bookshelf"],.desk-regional-accent');if(!target||!canMove())return;const r=target.getBoundingClientRect(),light=q(".desk-shelf-light");Object.assign(light.style,{left:r.left-12+"px",top:r.top-8+"px",width:r.width+24+"px",height:r.height+16+"px"});light.classList.add("lit");}
  document.addEventListener("pointerover",shelf);document.addEventListener("focusin",shelf);
  for(const event of ["pointerout","focusout"])document.addEventListener(event,()=>q(".desk-shelf-light").classList.remove("lit"));
  const grid=document.querySelector(".sovereign-tools-grid");
  for(const [key,label] of [["ambience","Outdoor ambience"],["rain","Window rain"]]){const b=document.createElement("button");b.type="button";b.id=`desk-${key}-toggle`;const refresh=()=>{const on=(key==="ambience"?motion:rain)==="on";b.textContent=`${label}: ${on?"On":"Off"}`;b.setAttribute("aria-pressed",String(on));};b.addEventListener("click",()=>{if(key==="ambience"){motion=motion==="on"?"off":"on";saveSetting("sovereign-ambience",motion);}else{rain=rain==="on"?"off":"on";saveSetting("sovereign-rain",rain);}refresh();setMotion();});refresh();grid?.append(b);}
  document.addEventListener("desk:layout",layout);document.addEventListener("desk:roomchange",layout);
  document.addEventListener("desk:motionchange",setMotion);document.addEventListener("visibilitychange",()=>{setMotion();});reduced.addEventListener("change",setMotion);
  layout();setMotion();
  return {layout};
}
