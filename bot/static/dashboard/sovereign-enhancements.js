/* Room instruments consume existing snapshots. They never submit orders or fetch broker data. */
const CITIES = [
  ["New York", "America/New_York"], ["London", "Europe/London"],
  ["Tokyo", "Asia/Tokyo"], ["Dubai", "Asia/Dubai"],
];
const LAYOUTS = {
  media: {clock:[85.8,37.3,5.5,3.1],accent:[12.1,19.3,3,7.5],window:null},
  pacific:{clock:[19,6.5,5.5,2.8],accent:[18.6,19.5,5.5,8],window:"polygon(30% 18%,100% 0,100% 62%,31% 53%)"},
  tokyo:{clock:[19.55,28.1,5.3,6.5],accent:null,window:"polygon(27% 20%,100% 0,100% 56%,27% 49%)"},
  manhattan:{clock:[19.55,7.5,5,6.5],accent:[19.1,27,5.5,7.5],window:"polygon(35% 16%,100% 0,100% 63%,35% 53%)"},
  dubai:{clock:[20,38.6,5.4,6.5],accent:[19.5,9,5.5,8],window:"polygon(35% 18%,100% 0,100% 62%,35% 53%)"},
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
  root.innerHTML=`<div class="desk-weather" aria-hidden="true"><div class="desk-clouds"></div><svg class="desk-aircraft" viewBox="0 0 24 14"><path fill="currentColor" d="M23 7L13 5 7 0H5L8 5 3 6 0 3V5L2 7 0 9V11L3 8 8 9 5 14H7L13 9Z"/></svg><div class="desk-rain"></div><div class="desk-city-glints"></div></div>
    <div class="desk-projection" aria-hidden="true"></div><div class="desk-shelf-light" aria-hidden="true"></div>
    <div class="desk-instrument desk-session-clock" role="group" aria-label="World clocks; select a city for market sessions">${CITIES.map(([name],i)=>`<button type="button" data-city="${i}" aria-label="${name} time and market sessions"><span class="clock-face"><i class="clock-hour"></i><i class="clock-minute"></i><b></b></span><span class="clock-city">${name}</span></button>`).join("")}</div>
    <div class="desk-regional-accent" role="img"></div>`;
  document.body.append(root);
  const q=s=>root.querySelector(s);
  let motion=readSetting("sovereign-ambience","on"), rain=readSetting("sovereign-rain","off");
  const reduced=matchMedia("(prefers-reduced-motion: reduce)");
  let timer=null;
  function canMove(){return !reduced.matches&&!document.hidden&&document.body.dataset.objectMotion!=="off";}
  function place(el,box){const r=roomRect();Object.assign(el.style,{left:r.left+box[0]*r.width/100+"px",top:r.top+box[1]*r.height/100+"px",width:box[2]*r.width/100+"px",height:box[3]*r.height/100+"px"});}
  function layout(){
    const scene=roomSnapshot(), p=LAYOUTS[scene.id],r=roomRect();
    root.dataset.ready=String(assetsReady?.()!==false);
    root.dataset.room=scene.id;root.dataset.theme=scene.theme;
    place(q(".desk-session-clock"),p.clock);
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
