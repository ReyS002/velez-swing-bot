/* Room instruments consume existing snapshots. They never submit orders or fetch broker data. */
const CITIES = [
  ["New York", "America/New_York"], ["London", "Europe/London"],
  ["Tokyo", "Asia/Tokyo"], ["Dubai", "Asia/Dubai"],
];
const LAYOUTS = {
  media: {dial:[59,81,6,4.8],clock:[44,69.5,12,4.3],tray:[84,78,8,5.5],accent:[12.1,19.3,3,7.5],window:null},
  pacific:{dial:[59,80,6,4.8],clock:[46,64,12,4.5],tray:[84,78,8,5.5],accent:[18.6,19.5,5.5,8],window:"polygon(30% 18%,100% 0,100% 62%,31% 53%)"},
  tokyo:{dial:[57,80,6,4.8],clock:[43,63,12,4.5],tray:[84,76,8,5.5],accent:[19.1,21,5.5,6],window:"polygon(27% 20%,100% 0,100% 56%,27% 49%)"},
  manhattan:{dial:[59,80,6,4.8],clock:[45,63,12,4.5],tray:[84,77,8,5.5],accent:[19.1,27,5.5,7.5],window:"polygon(35% 16%,100% 0,100% 63%,35% 53%)"},
  dubai:{dial:[60,80,6,4.8],clock:[46,64,12,4.5],tray:[84,77,8,5.5],accent:[19.5,9,5.5,8],window:"polygon(35% 18%,100% 0,100% 62%,35% 53%)"},
};
const ACCENTS = {
  media:[0,70,345,490,"Brass architectural miniature"],
  pacific:[370,255,470,300,"Koa keepsake box and lava stone"],
  tokyo:[880,215,420,320,"Mount Fuji glass paperweight"],
  manhattan:[1360,150,370,400,"Exchange bell"],
  dubai:[1770,65,400,490,"Brass astrolabe"],
};
const number = v => v !== null && v !== undefined && v !== "" && Number.isFinite(Number(v)) ? Number(v) : null;
// Daily-loss headroom is a budget, not buying power or permission to trade.
export function dailyBuffer(snapshot, now=Date.now()) {
  const daily=snapshot?.broker_daily_pnl, cap=number(snapshot?.risk?.max_daily_loss_pct);
  const pnl=number(daily?.daily_pnl), equity=number(daily?.day_start_equity);
  const timestamp=Date.parse(snapshot?.timestamp||"");
  if(snapshot?.ok!==true || daily?.ok!==true || !Number.isFinite(timestamp) || now-timestamp>120000 || timestamp-now>60000 || cap===null || cap<=0 || equity===null || equity<=0 || pnl===null)
    return {available:false,label:"Daily loss buffer unavailable",percent:null};
  const budget=equity*cap, remaining=Math.max(0,budget-Math.max(0,-pnl));
  const percent=Math.min(100,remaining/budget*100);
  return {available:true,percent,remaining,budget,label:`Daily loss buffer: ${Math.round(percent)}% remaining. ${remaining.toLocaleString("en-US",{style:"currency",currency:"USD",maximumFractionDigits:0})} of ${budget.toLocaleString("en-US",{style:"currency",currency:"USD",maximumFractionDigits:0})}. Open Risk & Bull Matrix.`};
}
function readSetting(key,fallback){try{return localStorage.getItem(key)??fallback;}catch{return fallback;}}
function saveSetting(key,value){try{localStorage.setItem(key,value);}catch{/* storage may be unavailable */}}
export function mountRoomEnhancements({roomRect,roomSnapshot,open,metrics,refreshMetrics,assetsReady}) {
  if(document.querySelector("#desk-enhancements"))return;
  const root=document.createElement("div");root.id="desk-enhancements";root.className="desk-enhancements";
  root.innerHTML=`<div class="desk-weather" aria-hidden="true"><div class="desk-clouds"></div><svg class="desk-aircraft" viewBox="0 0 24 14"><path fill="currentColor" d="M23 7L13 5 7 0H5L8 5 3 6 0 3V5L2 7 0 9V11L3 8 8 9 5 14H7L13 9Z"/></svg><div class="desk-rain"></div><div class="desk-city-glints"></div></div>
    <div class="desk-projection" aria-hidden="true"></div><div class="desk-shelf-light" aria-hidden="true"></div>
    <button type="button" class="desk-instrument desk-risk-dial" aria-label="Daily loss buffer unavailable. Open Risk & Bull Matrix"><svg viewBox="0 0 130 85" aria-hidden="true"><defs><linearGradient id="dial-brass"><stop stop-color="#57412a"/><stop offset=".35" stop-color="#e5c48c"/><stop offset=".7" stop-color="#8d6c3e"/><stop offset="1" stop-color="#34281b"/></linearGradient></defs><ellipse cx="65" cy="44" rx="63" ry="38" fill="url(#dial-brass)"/><ellipse cx="65" cy="42" rx="58" ry="33" fill="#141c1b" stroke="#080b0b" stroke-width="3"/><path d="M23 48 A44 29 0 0 1 107 48" fill="none" stroke="#b9a176" stroke-width="1.5"/><path d="M23 48L29 46 M28 31L34 34 M44 18L47 25 M65 13V21 M86 18L83 25 M102 31L96 34 M107 48L101 46" stroke="#b9a176"/><g class="desk-risk-needle"><path d="M65 49L27 36L64 44Z" fill="#dcc494"/><circle cx="65" cy="47" r="4" fill="#b59766"/></g><text x="65" y="65" text-anchor="middle" fill="#dbc79f" font-size="7" letter-spacing="1">DAILY BUFFER</text><text class="desk-risk-value" x="65" y="38" text-anchor="middle" fill="#fff2d6" font-size="12">—</text></svg><span class="instrument-tooltip"></span></button>
    <div class="desk-instrument desk-session-clock" role="group" aria-label="World clocks; select a city for market sessions">${CITIES.map(([name],i)=>`<button type="button" data-city="${i}" aria-label="${name} time and market sessions"><span class="clock-face"><i class="clock-hour"></i><i class="clock-minute"></i><b></b></span><span class="clock-city">${name}</span></button>`).join("")}</div>
    <button type="button" class="desk-instrument desk-document-tray" aria-label="Open approvals"><span class="tray-leather"></span><span class="tray-paper"><small>PROPOSAL</small><strong></strong><i></i><i></i></span><span class="tray-label">APPROVALS</span><span class="instrument-tooltip"></span><span class="tray-stamp" aria-hidden="true">SUBMITTED</span></button>
    <div class="desk-regional-accent" role="img"></div>`;
  document.body.append(root);
  const q=s=>root.querySelector(s), dial=q(".desk-risk-dial"),tray=q(".desk-document-tray");
  let state={}, previousIds=null, previousRiskLevel=null, motion=readSetting("sovereign-ambience","on"), rain=readSetting("sovereign-rain","off");
  const reduced=matchMedia("(prefers-reduced-motion: reduce)");
  let timer=null, transient=[];
  function canMove(){return !reduced.matches&&!document.hidden&&document.body.dataset.objectMotion!=="off";}
  function animate(el,frames,options){if(!canMove())return;const a=el.animate(frames,options);transient.push(a);a.finished.catch(()=>{}).finally(()=>{transient=transient.filter(v=>v!==a);});}
  function place(el,box){const r=roomRect();Object.assign(el.style,{left:r.left+box[0]*r.width/100+"px",top:r.top+box[1]*r.height/100+"px",width:box[2]*r.width/100+"px",height:box[3]*r.height/100+"px"});}
  function layout(){
    const scene=roomSnapshot(), p=LAYOUTS[scene.id],r=roomRect();
    root.dataset.ready=String(assetsReady?.()!==false);
    root.dataset.room=scene.id;root.dataset.theme=scene.theme;
    place(dial,p.dial);place(q(".desk-session-clock"),p.clock);place(tray,p.tray);place(q(".desk-regional-accent"),p.accent);
    const [x,y,w,h,label]=ACCENTS[scene.id];
    q(".desk-regional-accent").innerHTML=`<svg viewBox="${x} ${y} ${w} ${h}" aria-hidden="true"><image width="2172" height="724" href="/dashboard/assets/sovereign/regional-accents-v1.png"/></svg>`;
    q(".desk-regional-accent").setAttribute("aria-label",label);
    Object.assign(q(".desk-weather").style,{left:r.left+"px",top:r.top+"px",width:r.width+"px",height:r.height+"px",clipPath:p.window||"inset(100%)"});
    Object.assign(q(".desk-projection").style,{left:"36vw",top:innerHeight-85+"px",width:"28vw",height:"28px"});
    root.style.setProperty("--instrument-scale",String(r.width/1672));
    transient.forEach(a=>a.cancel());q(".desk-shelf-light").classList.remove("lit");
  }
  function setMotion(){root.dataset.ambience=motion;root.dataset.rain=rain;root.dataset.paused=String(!canMove());clearInterval(timer);timer=null;if(!document.hidden){tick();timer=setInterval(tick,30000);}}
  function tick(){
    const now=new Date();
    CITIES.forEach(([name,zone],i)=>{const parts=new Intl.DateTimeFormat("en-GB",{timeZone:zone,hour:"2-digit",minute:"2-digit",hourCycle:"h23"}).formatToParts(now);const h=Number(parts.find(p=>p.type==="hour").value),m=Number(parts.find(p=>p.type==="minute").value);const b=q(`[data-city="${i}"]`);b.querySelector(".clock-hour").style.transform=`rotate(${h%12*30+m/2}deg)`;b.querySelector(".clock-minute").style.transform=`rotate(${m*6}deg)`;b.title=`${name} · ${String(h).padStart(2,"0")}:${String(m).padStart(2,"0")} local time. Open sessions and calendar.`;b.setAttribute("aria-label",b.title);});
    update(state);
    Promise.resolve(refreshMetrics?.()).then(()=>update(state)).catch(()=>{});
  }
  function update(next={}){
    state=next;
    const risk=dailyBuffer(metrics?.().risk);
    dial.dataset.level=!risk.available?"unknown":risk.percent<=10?"danger":risk.percent<=30?"warning":"normal";
    if(previousRiskLevel!==dial.dataset.level&&["warning","danger"].includes(dial.dataset.level))animate(q(".desk-risk-needle"),[{opacity:1},{opacity:.3},{opacity:1}],{duration:450,iterations:2});
    previousRiskLevel=dial.dataset.level;
    dial.setAttribute("aria-label",risk.label);dial.title=risk.label;q(".desk-risk-dial .instrument-tooltip").textContent=risk.label;
    q(".desk-risk-value").textContent=risk.available?Math.round(risk.percent)+"%":"—";
    q(".desk-risk-needle").style.transform=`rotate(${risk.available?risk.percent*1.4:0}deg)`;
    q(".desk-risk-needle").style.opacity=risk.available?"1":"0";
    const items=Array.isArray(next.pending_approvals)?next.pending_approvals:null,ids=items?.map(v=>String(v.id));
    if(previousIds&&ids?.some(id=>!previousIds.includes(id)))animate(q(".tray-paper"),[{transform:"translateY(-10px)",opacity:0},{transform:"translateY(0)",opacity:1}],{duration:380,easing:"ease-out"});
    previousIds=ids;tray.dataset.empty=String(!items?.length);
    const label=items?`${items.length} pending ${items.length===1?"proposal":"proposals"}. Open approvals.`:"Approvals unavailable. Open approvals to check.";
    tray.title=label;tray.setAttribute("aria-label",label);q(".desk-document-tray .instrument-tooltip").textContent=label;
    q(".tray-paper strong").textContent=items?.length?String(items[0].symbol||"Review")+ (items.length>1?` +${items.length-1}`:""):"";
  }
  dial.addEventListener("click",()=>open("lamp",dial));
  q(".desk-session-clock").addEventListener("click",e=>{const b=e.target.closest("[data-city]");if(b){document.body.dataset.sessionCity=b.dataset.city;open("clock",b);}});
  tray.addEventListener("click",()=>{animate(q(".tray-paper"),[{transform:"translateY(0)"},{transform:"translateY(-5px)"},{transform:"translateY(0)"}],{duration:260});open("safe",tray);});
  document.addEventListener("desk:approval-submitted",()=>animate(q(".tray-stamp"),[{opacity:0,transform:"scale(1.2)"},{opacity:1,transform:"scale(1)",offset:.25},{opacity:1,offset:.8},{opacity:0}],{duration:1100}));
  function shelf(e){const target=e.target.closest?.('[data-object-id="vault"],[data-object-id="bookshelf"],.desk-regional-accent');if(!target||!canMove())return;const r=target.getBoundingClientRect(),light=q(".desk-shelf-light");Object.assign(light.style,{left:r.left-12+"px",top:r.top-8+"px",width:r.width+24+"px",height:r.height+16+"px"});light.classList.add("lit");}
  document.addEventListener("pointerover",shelf);document.addEventListener("focusin",shelf);
  for(const event of ["pointerout","focusout"])document.addEventListener(event,()=>q(".desk-shelf-light").classList.remove("lit"));
  const grid=document.querySelector(".sovereign-tools-grid");
  for(const [key,label] of [["ambience","Outdoor ambience"],["rain","Window rain"]]){const b=document.createElement("button");b.type="button";b.id=`desk-${key}-toggle`;const refresh=()=>{const on=(key==="ambience"?motion:rain)==="on";b.textContent=`${label}: ${on?"On":"Off"}`;b.setAttribute("aria-pressed",String(on));};b.addEventListener("click",()=>{if(key==="ambience"){motion=motion==="on"?"off":"on";saveSetting("sovereign-ambience",motion);}else{rain=rain==="on"?"off":"on";saveSetting("sovereign-rain",rain);}refresh();setMotion();});refresh();grid?.append(b);}
  document.addEventListener("desk:layout",layout);document.addEventListener("desk:roomchange",layout);
  document.addEventListener("desk:motionchange",setMotion);document.addEventListener("visibilitychange",()=>{transient.forEach(a=>a.cancel());setMotion();});reduced.addEventListener("change",setMotion);
  layout();setMotion();
  return {update,layout};
}
