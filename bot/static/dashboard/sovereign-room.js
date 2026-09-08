import {mountObjectMotion} from "./sovereign-motion.js?v=1.3.0";
// Shared Sovereign room shell. Keep byte-identical across bot editions.
export const SOVEREIGN_VERSION = "1.3.0";
const ASSETS = "/dashboard/assets/sovereign/";
const percent = ([x, y, w, h]) => ({ x: x / 100, y: y / 100, w: w / 100, h: h / 100 });
export const ROOMS = {
  media: { name: "Executive", modes: { night: "Cinema", day: "Focus" }, defaultTheme: "night", images: { night: "executive-cinema-clean.png", day: "executive-focus-clean.png" }, screen: [37.25,45.55,25.1,18.1], broadcast: [31.699,15.409,36.603,27.843], objects: { phone:[19.6,65.8,9.7,15.8],music:[32.5,66.8,4.6,11.7],journal:[68.8,76.4,10.8,8.7],keyboard:[38.5,74.6,19.2,6],trackpad:[58.6,75.6,5.9,4.8],lamp:[12,48,15,25],mission:[69.65,59.3,6.45,10.6],notes:[78.5,61,12,14],safe:[75.8,90.5,14,4.5],bookshelf:[8,15,7,36] } },
  pacific: { name: "Hawaii", modes: { night: "Sunset", day: "Day" }, defaultTheme: "night", images: { night: "hawaii-sunset-clean.png", day: "hawaii-day-clean.png" }, screen: [33.7,40.65,27.2,20.65], broadcast: [4.8,21.6,11.6,25.5], objects: {phone:[13.5,67.5,11.6,17],music:[27,66.8,4.6,10.7],journal:[69.5,77,10.1,10.1],keyboard:[32.5,71.5,25,6.5],trackpad:[58.4,72.9,5.9,4.9],lamp:[7,47,16.5,24.5],mission:[70.7,55.9,7,11.5],notes:[81.5,55,11.5,17],safe:[80,94,17,4.4],bookshelf:[18.4,17,7.5,30]} },
  tokyo: { name: "Tokyo", modes: { day: "Clear Day", night: "Blue Hour" }, defaultTheme: "day", images: { day: "tokyo-day-clean.png", night: "tokyo-night-clean.png" }, screen:[36.55,41.6,25.4,19.8], broadcast:[6.7,18.5,10.35,27.6], objects:{phone:[12,66,13.9,17.7],music:[31,65.5,5.4,12.5],journal:[66.9,74.1,10.6,10.4],keyboard:[36.8,72.6,19.5,5.8],trackpad:[57.3,74.1,6.7,4.6],lamp:[8.5,39,19.5,27.5],mission:[69.8,54.8,6.15,12.1],notes:[79.7,56.5,10.5,13.4],safe:[81.5,92,13.7,3.5],bookshelf:[18.8,20,6.5,19]} },
  manhattan: { name:"New York", modes:{night:"Night",day:"Day"}, defaultTheme:"night", images:{night:"manhattan-night-clean.png",day:"manhattan-day-clean.png"},screen:[34.35,41.65,27.4,19.85],broadcast:[4.05,22.1,12.85,24.8],objects:{phone:[13.8,63,10.9,17],music:[27.8,66.3,4.4,11],journal:[69.6,73.6,8.9,9.4],keyboard:[33.3,72.5,24,6.3],trackpad:[58.7,73.3,6.5,4.8],lamp:[7.5,47,15.4,23.5],mission:[70.2,54.35,6.7,11.8],notes:[80.7,55.8,9.2,13.8],safe:[79.7,91.5,10.5,3.7],bookshelf:[19,12,7.1,33]} },
  dubai: {name:"Dubai",modes:{day:"Day",night:"Night"},defaultTheme:"day",images:{day:"dubai-day-clean.png",night:"dubai-night-clean.png"},screen:[33.75,40.4,27.2,21.8],broadcast:[4.7,21.1,12.45,21.3],objects:{phone:[13.5,66.5,12,15.3],music:[27.3,66.6,4,10.7],journal:[71,75.1,9.6,9.5],keyboard:[32.3,72.2,24.8,6],trackpad:[57.5,73,7.2,4.5],lamp:[8,45.5,13.6,25.5],mission:[71,55.35,6.9,11.7],notes:[80.5,53.2,11,17.5],safe:[81.4,92,10.2,3.5],bookshelf:[19.2,11.5,6.6,31]}}
};
// Clockwise wall-plane corners in the original 1672 × 941 room artwork.
// Executive faces the viewer; the scenic-room walls recede toward the window.
const BROADCAST_CORNERS = {
  media: [[530,145],[1142,145],[1142,407],[530,407]],
  pacific: [[75,197],[278,220],[278,432],[75,449]],
  tokyo: [[105,160],[294,197],[294,434],[105,445]],
  manhattan: [[66,193],[289,228],[289,436],[66,450]],
  dubai: [[76,191],[294,232],[294,403],[76,405]],
};
export function broadcastCorners() {
  const rect=roomRect();
  return BROADCAST_CORNERS[roomId].map(([x,y])=>[rect.left+x*rect.width/1672,rect.top+y*rect.height/941]);
}
export const PANEL_LABELS = {tv:"Trading screen",laptop:"Command",mission:"Session Brief",calendar:"Calendar",clock:"Market sessions",window:"Market conditions",phone:"Winston",music:"Apple Music",journal:"Trade journal",notes:"Bull Report & notes",safe:"Approvals & vault",lamp:"Risk & Bull Matrix",drawer:"Research lab",bookshelf:"Strategy library",mentor:"Mentor",account:"Account & access"};
const OBJECTS = { phone:["phone","Call Winston","phone-call"],music:["music","Apple Music","music"],journal:["journal","Trade journal","book-open"],keyboard:["laptop","Command","keyboard"],trackpad:["laptop","Command","mouse-pointer-2"],lamp:["lamp","Risk & Bull Matrix","lamp"],mission:["mission","Session Brief","target"],notes:["notes","Bull Report & notes","file-text"],safe:["safe","Approvals & vault","inbox"],bookshelf:["bookshelf","Strategy library","library"] };
const read = (key, fallback) => { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } };
const savedRoom = localStorage.getItem("bull-pilot-environment");
let roomId = ROOMS[savedRoom] ? savedRoom : "media";
let lighting = read("sovereign-room-lighting", {});
if (!lighting[roomId]) lighting[roomId] = savedRoom && localStorage.getItem("velez-room-theme") || ROOMS[roomId].defaultTheme;
let adapter = null, lastFocus = null, expandedChart = false;
let config = { product: "Trading Bull Desk", broker_provider: "", account_mode: "workspace" };
let preloadToken = 0;
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
export function roomSnapshot() { return { id:roomId,name:ROOMS[roomId].name,theme:lighting[roomId],mode:ROOMS[roomId].modes[lighting[roomId]] }; }
export function roomRect() {
  const scale = Math.min(window.innerWidth / 1672, window.innerHeight / 941);
  const width = 1672 * scale, height = 941 * scale;
  return {left:(window.innerWidth-width)/2,top:(window.innerHeight-height)/2,width,height};
}
export function roomRegions() { const r=ROOMS[roomId]; return {screen:percent(r.screen),broadcast:percent(r.broadcast),phone:percent(r.objects.phone)}; }
export function roomHotspots() {return Object.entries(ROOMS[roomId].objects).map(([id,rect])=>({id,panel:OBJECTS[id][0],label:OBJECTS[id][1],icon:OBJECTS[id][2],...percent(rect)}));}
export function objectMarkup(definition) {
  const id=definition.id;
  if(id==="phone") return `<span class="prop-art phone-art"><svg viewBox="80 145 1100 980" aria-hidden="true"><defs><clipPath id="phone-silhouette"><path d="M86 978 L98 930 L111 881 L133 801 L142 784 L157 278 Q163 230 208 224 L809 222 Q853 225 865 275 L878 210 Q885 160 929 155 L1032 153 Q1078 156 1087 199 L1116 800 L1144 881 L1163 950 L1168 978 L1168 1048 Q1168 1073 1139 1090 Q1128 1103 1109 1108 L149 1108 Q128 1102 116 1088 Q88 1069 87 1048 Z"/></clipPath></defs><image href="${ASSETS}phone-glass.png" width="1254" height="1254" clip-path="url(#phone-silhouette)"/></svg><span class="phone-display"><small>WINSTON</small><strong>Start call</strong><span>Brief · Research</span></span></span><span class="prop-caption">Winston</span>`;
  if(id==="music") return `<span class="prop-art music-art"><svg viewBox="58 46 910 1420" aria-hidden="true"><defs><clipPath id="player-silhouette"><path d="M160 129 Q162 49 235 50 L795 50 Q865 51 866 125 L884 1148 Q926 1160 939 1205 L963 1310 L963 1394 Q963 1447 900 1457 L119 1457 Q61 1447 61 1395 L61 1310 L84 1213 Q95 1171 139 1154 Z"/></clipPath></defs><image href="${ASSETS}pocket-player.png" width="1024" height="1536" clip-path="url(#player-silhouette)"/></svg><span class="music-display"><small>APPLE MUSIC</small><span class="prop-now-playing">Your music</span></span></span><span class="prop-caption">Music</span>`;
  if(id==="journal") return `<span class="prop-art journal-art"><svg viewBox="100 130 1350 768" aria-hidden="true"><defs><clipPath id="journal-silhouette"><path d="M167 243 L901 138 Q935 135 952 150 L1415 620 Q1448 661 1416 672 L1438 720 Q1448 743 1419 752 L518 890 Q487 898 477 878 L124 374 Q84 300 137 260 Z"/></clipPath></defs><image href="${ASSETS}journal.png" width="1536" height="1024" clip-path="url(#journal-silhouette)"/></svg></span><span class="prop-caption">Journal</span>`;
  if(id==="mission") return `<span class="brief-face"><strong>SESSION BRIEF</strong><span>Mission</span><span>Calendar</span><span>Watchlist</span></span>`;
  if(id==="safe") return `<span class="approval-plaque">APPROVALS <small class="approval-count"></small></span>`;
  return `<i data-lucide="${definition.icon}"></i><span>${definition.label}</span>`;
}
function applyBounds(element, region) { const rect=roomRect(); Object.assign(element.style,{left:`${rect.left+region.x*rect.width}px`,top:`${rect.top+region.y*rect.height}px`,width:`${region.w*rect.width}px`,height:`${region.h*rect.height}px`}); }
function layout() {
  const rect=roomRect();document.documentElement.style.setProperty("--room-scale",String(rect.width/1672));
  const screen=$("#screen-terminal");if(screen&&!expandedChart)applyBounds(screen,roomRegions().screen);
  adapter?.position?.();
  document.dispatchEvent(new CustomEvent("desk:layout",{detail:roomSnapshot()}));
}
export function syncRoomTheme(theme) {
  lighting[roomId]=theme==="day"?"day":"night";
  localStorage.setItem("sovereign-room-lighting",JSON.stringify(lighting));
  document.body.dataset.environment=roomId;
  document.body.dataset.roomTheme=lighting[roomId];
  document.body.dataset.glassTreatment=lighting[roomId]==="day"?"champagne":"smoked";
  const url=ASSETS+ROOMS[roomId].images[lighting[roomId]];
  const plate=$(".photo-room");
  if(plate){const token=++preloadToken;const image=new Image();image.onload=()=>{if(token===preloadToken){plate.style.backgroundImage=`url("${url}")`;document.body.dataset.roomAsset=ROOMS[roomId].images[lighting[roomId]];}};image.onerror=()=>announce("This room image could not load. Try switching rooms again.");image.src=url;}
  const picker=$("#sovereign-room-select");if(picker)picker.value=roomId;
  const toggle=$("#theme-toggle");if(toggle){toggle.innerHTML=`<span>${ROOMS[roomId].modes[lighting[roomId]]}</span><i data-lucide="sun-moon"></i>`;toggle.setAttribute("aria-label",`Lighting: ${ROOMS[roomId].modes[lighting[roomId]]}. Switch to ${ROOMS[roomId].modes[lighting[roomId]==="day"?"night":"day"]}`);}
  document.dispatchEvent(new CustomEvent("desk:roomchange",{detail:roomSnapshot()}));
}
export function selectRoom(id) {
  if(!ROOMS[id])return;
  roomId=id;localStorage.setItem("bull-pilot-environment",id);
  adapter?.setTheme(lighting[id]||ROOMS[id].defaultTheme);
  syncRoomTheme(lighting[id]||ROOMS[id].defaultTheme);
  adapter?.buildHotspots();layout();announce(`${ROOMS[id].name}, ${ROOMS[id].modes[lighting[id]]}`);
}
function announce(message){const region=$("#sovereign-announcer");if(region)region.textContent=message;}
function escape(value){const span=document.createElement("span");span.textContent=String(value??"");return span.innerHTML;}
function closeTools(restore=true){const tools=$("#sovereign-tools");if(!tools)return;tools.hidden=true;$("[data-desk-action=tools]")?.setAttribute("aria-expanded","false");if(restore)lastFocus?.focus();}
function openPanel(panel, source){closeTools(false);if(expandedChart)expandChart(false);lastFocus=source||document.activeElement;adapter.open(panel);const heading=$("#panel-title");heading?.setAttribute("tabindex","-1");heading?.focus({preventScroll:true});}
function expandChart(open=true){expandedChart=open;document.body.classList.toggle("sovereign-chart-expanded",open);$("#sovereign-chart-close").hidden=!open;if(open){adapter.close();const screen=$("#screen-terminal");if(screen)screen.hidden=false;$("#sovereign-chart-close").focus();}else{layout();lastFocus?.focus();}}
function openTools(source){lastFocus=source;const tools=$("#sovereign-tools");tools.hidden=false;$("[data-desk-action=tools]")?.setAttribute("aria-expanded","true");tools.querySelector("button")?.focus();}
function handleAction(event){const target=event.target.closest("[data-desk-action]");if(!target)return;const action=target.dataset.deskAction;
  if(action==="tools")return $("#sovereign-tools").hidden?openTools(target):closeTools();
  if(action==="close-tools")return closeTools();
  if(action==="desk"){closeTools(false);adapter.close();if(expandedChart)expandChart(false);return;}
  if(action==="broadcast"){closeTools(false);adapter.close();document.dispatchEvent(new CustomEvent("desk:broadcast-open"));return;}
  if(action==="expand-chart"){lastFocus=target;return expandChart(true);}
  if(action==="close-chart")return expandChart(false);
  if(action==="pro-console"){closeTools(false);adapter.openProConsole?.();return;}
  if(PANEL_LABELS[action])openPanel(action,target);
}
export function updateSovereignChrome({panel,open,state,music,winston}={}) {
  if(!adapter)return;
  $$(".sovereign-dock [data-desk-action]").forEach(button=>button.setAttribute("aria-pressed",String(open&&(button.dataset.deskAction===panel||(button.dataset.deskAction==="journal"&&panel==="notes")))));
  const tabs=$("#sovereign-panel-tabs");const group=panel==="tv"?[["expand-chart","Open full chart"]]:["mission","calendar","clock","window"].includes(panel)?[["mission","Mission"],["calendar","Calendar"],["clock","Sessions"],["window","Conditions"],["laptop","Watchlist"]]:["journal","notes"].includes(panel)?[["journal","Trades"],["notes","Report & notes"]]:[];
  if(tabs&&tabs.dataset.group!==group.map(x=>x[0]).join()){tabs.dataset.group=group.map(x=>x[0]).join();tabs.innerHTML=group.map(([id,label])=>`<button type="button" data-desk-action="${id}">${label}</button>`).join("");}
  tabs?.querySelectorAll("button").forEach(button=>button.setAttribute("aria-pressed",String(button.dataset.deskAction===panel)));
  const title=$("#panel-title");if(title&&open&&PANEL_LABELS[panel])title.textContent=PANEL_LABELS[panel];
  const status=state||adapter.state();
  const count=status?.pending_approvals?.length;const badge=$(".approval-count");if(badge)badge.textContent=count>0?String(count):"";
  const now=$(".prop-now-playing");if(now)now.textContent=music?.nowPlaying?.title||"Your music";
  document.body.classList.toggle("sovereign-speaking",Boolean(winston?.speaking));
  if(!open)document.body.classList.remove("phone-active");
}
export function workspaceConfiguration(){return config;}
export function workspaceAccountMarkup(){return `<div class="mood-card good"><div><span>Workspace access</span><strong>${escape(config.product)}</strong><p>Your trading workspace and permissions.</p></div></div><div class="data-list"><div class="data-row"><span>Sign-in</span><strong>${escape(config.authenticated?"Connected":"Workspace access")}</strong></div><div class="data-row"><span>Plan</span><strong>${escape(config.tier||"Workspace")}</strong></div><div class="data-row"><span>Account management</span><strong>Managed by your workspace administrator</strong></div></div><p class="muted">Contact your workspace administrator for changes to sign-in or subscription access.</p>`;}
export function mountSovereign(options) {
  if(adapter)return;adapter=options;config.product=options.product;document.body.classList.add("sovereign");document.body.dataset.sovereignVersion=SOVEREIGN_VERSION;
  const topbar=$(".topbar");const brand=topbar?.querySelector("h1");if(brand)brand.textContent=options.product;
  const eyebrow=topbar?.querySelector(".brand-lockup .eyebrow");if(eyebrow)eyebrow.textContent="SOVEREIGN DESK";
  const statusStrip=topbar?.querySelector(".status-strip");const roomControl=document.createElement("label");roomControl.className="sovereign-room-picker";roomControl.innerHTML=`<span class="sr-only">Room</span><select id="sovereign-room-select" aria-label="Room">${Object.entries(ROOMS).map(([id,r])=>`<option value="${id}">${r.name}</option>`).join("")}</select>`;statusStrip?.append(roomControl);
  roomControl.querySelector("select").addEventListener("change",e=>selectRoom(e.target.value));
  if(!$("#account-toggle")){const account=document.createElement("button");account.type="button";account.id="account-toggle";account.className="theme-toggle";account.dataset.deskAction="account";account.innerHTML='<i data-lucide="user-round"></i><span>Account</span>';statusStrip?.append(account);}
  const nav=document.createElement("nav");nav.className="sovereign-dock";nav.setAttribute("aria-label","Desk navigation");nav.innerHTML=[["desk","Desk","armchair"],["laptop","Command","terminal"],["mentor","Mentor","sparkles"],["journal","Journal","book-open"],["broadcast","Broadcast","radio"],["tools","Tools","grid-2x2"]].map(([id,label,icon])=>`<button type="button" data-desk-action="${id}"${id==="tools"?' aria-expanded="false" aria-controls="sovereign-tools"':''}><i data-lucide="${icon}"></i><span>${label}</span></button>`).join("");$("#app-shell").append(nav);
  const tools=document.createElement("section");tools.id="sovereign-tools";tools.className="sovereign-tools";tools.hidden=true;tools.setAttribute("role","dialog");tools.setAttribute("aria-modal","true");tools.setAttribute("aria-labelledby","sovereign-tools-title");tools.innerHTML=`<header><div><small>YOUR WORKSPACE</small><h2 id="sovereign-tools-title">Tools</h2></div><button type="button" data-desk-action="close-tools" aria-label="Close tools">×</button></header><div class="sovereign-tools-grid">${Object.entries(PANEL_LABELS).map(([id,label])=>`<button type="button" data-desk-action="${id}">${label}<span>↗</span></button>`).join("")}${options.openProConsole?'<button type="button" data-desk-action="pro-console">Pro Console<span>↗</span></button>':''}</div>`;$("#app-shell").append(tools);
  const tabs=document.createElement("nav");tabs.id="sovereign-panel-tabs";tabs.setAttribute("aria-label","Related workspace views");$("#panel-body")?.before(tabs);
  const expand=document.createElement("button");expand.type="button";expand.className="sovereign-chart-expand";expand.dataset.deskAction="expand-chart";expand.setAttribute("aria-label","Expand trading chart");expand.innerHTML='<i data-lucide="maximize-2"></i>';
  expand.addEventListener("click",event=>event.stopPropagation());$("#screen-terminal")?.append(expand);
  // Keep the embedded chart interactive; its own buttons must not open a panel.
  expand.addEventListener("click",()=>{lastFocus=expand;expandChart(true);});
  const close=document.createElement("button");close.id="sovereign-chart-close";close.type="button";close.className="sovereign-chart-close";close.dataset.deskAction="close-chart";close.textContent="Return to desk";close.hidden=true;$("#app-shell").append(close);
  const announceRegion=document.createElement("div");announceRegion.id="sovereign-announcer";announceRegion.className="sr-only";announceRegion.setAttribute("role","status");$("#app-shell").append(announceRegion);
  document.addEventListener("click",handleAction);
  document.addEventListener("keydown",event=>{if(!tools.hidden){if(event.key==="Escape"){event.preventDefault();event.stopImmediatePropagation();closeTools();}if(event.key==="Tab"){const buttons=[...tools.querySelectorAll("button")];const first=buttons[0],last=buttons.at(-1);if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}}}else if(event.key==="Escape"&&expandedChart){event.preventDefault();event.stopImmediatePropagation();expandChart(false);}},true);
  $("#panel-close")?.addEventListener("click",()=>lastFocus?.focus());
  window.addEventListener("resize",layout);
  syncRoomTheme(lighting[roomId]);layout();window.lucide?.createIcons();
  fetch("/api/desk/config",{cache:"no-store"}).then(response=>response.ok?response.json():{}).then(value=>{config={...config,...value};if(brand&&value.product)brand.textContent=value.product;document.dispatchEvent(new CustomEvent("desk:config",{detail:config}));}).catch(()=>{});
  mountObjectMotion({open:openPanel,roomRect,roomSnapshot});
  window.__sovereign={version:SOVEREIGN_VERSION,rooms:ROOMS,room:roomSnapshot,selectRoom,regions:roomRegions,broadcastCorners,hotspots:roomHotspots,rect:roomRect,open:(id)=>openPanel(id),config:()=>config};
}
