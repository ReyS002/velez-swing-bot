// One Broadcast player follows the room's own calibrated wall surface.
import {broadcastCorners, roomSnapshot} from "./sovereign-room.js?v=1.1.0";
import {createBriefView} from "./broadcast-brief.js?v=1.2.0";
const $ = selector => document.querySelector(selector);
const state = {enabled:false, expanded:false, playing:false, muted:false, volume:0.6, ducked:false, provider:"native", youtube:null, youtubeReady:false, lastFocus:null, config:{}};
const tickerLinks = {
  SPY: "https://finance.yahoo.com/quote/SPY/",
  QQQ: "https://finance.yahoo.com/quote/QQQ/",
  VIX: "https://finance.yahoo.com/quote/%5EVIX/",
  DXY: "https://finance.yahoo.com/quote/DX-Y.NYB/",
  GLD: "https://finance.yahoo.com/quote/GLD/",
  "EUR/USD": "https://finance.yahoo.com/quote/EURUSD%3DX/",
  BTC: "https://finance.yahoo.com/quote/BTC-USD/",
  ETH: "https://finance.yahoo.com/quote/ETH-USD/",
};
let stage, video, marketTimer, youtubePromise, surfaceMotion, brief;
let selected=null, selectionVersion=0, storageKey="", playerRevealed=false;
function saveSettings(){try{localStorage.setItem(storageKey,JSON.stringify({channel:selected?.id,muted:state.muted,volume:state.volume}));}catch{}}
const escape = value => {const node=document.createElement("span");node.textContent=String(value??"");return node.innerHTML;};
const time = seconds => {const n=Math.max(0,Math.floor(Number(seconds)||0));return String(Math.floor(n/60)).padStart(2,"0")+":"+String(n%60).padStart(2,"0");};

// Project the entire live player onto four wall corners, including its hit targets.
// CSS matrix3d is column-major; the last row supplies perspective division.
function surfaceTransform(points,width,height) {
  const [[x0,y0],[x1,y1],[x2,y2],[x3,y3]]=points;
  const dx1=x1-x2,dx2=x3-x2,dx3=x0-x1+x2-x3;
  const dy1=y1-y2,dy2=y3-y2,dy3=y0-y1+y2-y3;
  const denominator=dx1*dy2-dx2*dy1;
  const g=Math.abs(denominator)>1e-8?(dx3*dy2-dx2*dy3)/denominator:0;
  const h=Math.abs(denominator)>1e-8?(dx1*dy3-dx3*dy1)/denominator:0;
  return `matrix3d(${[(x1-x0+g*x1)/width,(y1-y0+g*y1)/width,0,g/width,(x3-x0+h*x3)/height,(y3-y0+h*y3)/height,0,h/height,0,0,1,0,x0,y0,0,1].join(",")})`;
}
function surfaceBox() {
  const style=getComputedStyle(stage);
  return {left:parseFloat(style.left),top:parseFloat(style.top),width:parseFloat(style.width),height:parseFloat(style.height)};
}
function visibleCorners() {
  if(!stage.getClientRects().length)return null;
  const box=surfaceBox(),transform=getComputedStyle(stage).transform;
  const matrix=new DOMMatrix(transform==="none"?undefined:transform);
  return [[0,0],[box.width,0],[box.width,box.height],[0,box.height]].map(([x,y])=>{
    const point=new DOMPoint(x,y).matrixTransform(matrix);
    return [box.left+point.x/point.w,box.top+point.y/point.w];
  });
}
function cancelSurfaceMotion() {
  surfaceMotion?.cancel();surfaceMotion=null;stage?.classList.remove("broadcast-moving");
}
function moveSurface(from) {
  if(!from||!stage.getClientRects().length||!stage.animate||matchMedia("(prefers-reduced-motion: reduce)").matches)return;
  const box=surfaceBox();
  const start=surfaceTransform(from.map(([x,y])=>[x-box.left,y-box.top]),box.width,box.height);
  const end=getComputedStyle(stage).transform;
  stage.classList.add("broadcast-moving");
  const animation=stage.animate([{transform:start},{transform:end}],{duration:440,easing:"cubic-bezier(.22,.75,.2,1)",fill:"both"});
  surfaceMotion=animation;
  animation.onfinish=()=>{if(surfaceMotion===animation)cancelSurfaceMotion();};
}
function positionStage() {
  if(!stage)return;
  cancelSurfaceMotion();
  if(state.expanded){stage.style.transform="none";return;}
  const corners=broadcastCorners();
  const left=Math.min(...corners.map(p=>p[0])),top=Math.min(...corners.map(p=>p[1]));
  const width=Math.max(...corners.map(p=>p[0]))-left,height=Math.max(...corners.map(p=>p[1]))-top;
  Object.assign(stage.style,{left:`${left}px`,top:`${top}px`,width:`${width}px`,height:`${height}px`,transform:surfaceTransform(corners.map(([x,y])=>[x-left,y-top]),width,height)});
  stage.dataset.orientation=roomSnapshot().id==="media"?"wide":"portrait";
}
function chrome() {
  $("#broadcast-play").textContent=state.playing?"Ⅱ":"▶";
  $("#broadcast-play").setAttribute("aria-label",state.playing?"Pause Broadcast":"Play Broadcast");
  $("#broadcast-mute").textContent=state.muted?"Muted":"Sound";
  $("#broadcast-mute").setAttribute("aria-pressed",String(state.muted));
  $("#broadcast-mute").setAttribute("aria-label",state.muted?"Unmute Broadcast":"Mute Broadcast");
  stage.classList.toggle("is-playing",state.playing);
  $("#broadcast-time").textContent=state.provider==="youtube"&&selected?.kind==="live"?"LIVE":time(state.provider==="brief"?brief?.time():state.provider==="youtube"?state.youtube?.getCurrentTime?.():video.currentTime);
  stage.classList.toggle("player-revealed",playerRevealed);
}
function volume() {
  const effective=state.volume*(state.ducked?0.18:1);
  video.volume=effective;video.muted=state.muted;
  if(state.youtubeReady){state.youtube.setVolume(effective*100);if(state.muted)state.youtube.mute();else state.youtube.unMute();}
  brief?.volume(effective,state.muted);
  chrome();
}
function fitYoutube(){
  const iframe=$("#broadcast-youtube");if(iframe?.tagName!=="IFRAME")return;
  const box=$(".broadcast-picture").getBoundingClientRect();
  const parent=$(".broadcast-picture"),w=parent.clientWidth,h=parent.clientHeight;
  const logicalW=Math.max(480,w),logicalH=Math.max(270,h);
  Object.assign(iframe.style,{width:logicalW+"px",height:logicalH+"px",transform:`scale(${w/logicalW},${h/logicalH})`,transformOrigin:"0 0"});
}
async function youtubePlayer() {
  if(state.youtubeReady)return state.youtube;
  if(youtubePromise)return youtubePromise;
  youtubePromise=new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>reject(new Error("Video service did not load. Try again.")),15000);
    function create(){
      $("#broadcast-youtube").hidden=false;video.hidden=true;
      state.youtube=new window.YT.Player("broadcast-youtube",{
        videoId:selected?.youtube_video_id,
        host:"https://www.youtube-nocookie.com",
        playerVars:{playsinline:1,rel:0,origin:location.origin},
        events:{
          onReady:()=>{clearTimeout(timer);state.youtubeReady=true;fitYoutube();$("#broadcast-youtube").hidden=state.provider!=="youtube";if(selected?.youtube_playlist_id)state.youtube.cuePlaylist({listType:"playlist",list:selected.youtube_playlist_id});volume();resolve(state.youtube);},
          onStateChange:event=>{if(state.provider!=="youtube")return;state.playing=event.data===1;
            if(event.data===1){$("#broadcast-message").textContent="";playerRevealed=true;}
            if(event.data===0&&selected?.kind==="live"){$("#broadcast-source").textContent="STREAM ENDED";$("#broadcast-message").textContent="This stream has ended. Choose another channel or visit its official page.";}
            chrome();},
          onError:event=>{clearTimeout(timer);if(state.provider!=="youtube")return;state.playing=false;chrome();$("#broadcast-message").textContent=`This stream cannot play here (${event.data}). Choose another channel or use Visit channel.`;reject(new Error("Video unavailable"));}
        }
      });
    }
    if(window.YT?.Player)return create();
    const previous=window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady=()=>{previous?.();create();};
    if(!document.querySelector('script[src="https://www.youtube.com/iframe_api"]')){
      const script=document.createElement("script");script.src="https://www.youtube.com/iframe_api";script.onerror=()=>{clearTimeout(timer);reject(new Error("Video service could not be reached."));};document.head.append(script);
    }
  }).catch(error=>{youtubePromise=null;throw error;});
  return youtubePromise;
}
async function play() {
  if(!state.enabled)return expand();
  try{
    if(state.provider==="brief"){expand();await brief.play();return;}
    if(state.provider==="none"){expand();return;}
    const version=selectionVersion;
    if(state.provider==="youtube"){playerRevealed=true;chrome();const player=await youtubePlayer();if(version!==selectionVersion)return;player.playVideo();}
    else await video.play();
    $("#broadcast-message").textContent="";
  }catch(error){$("#broadcast-message").textContent=error.message||"Playback could not start. Press Play to retry.";}
  chrome();
}
function pause(){brief?.pause();video?.pause();state.youtube?.pauseVideo?.();state.playing=false;if(stage)chrome();}
function expand(){
  if(!stage||state.expanded)return;
  const from=visibleCorners();cancelSurfaceMotion();
  state.lastFocus=document.activeElement;state.expanded=true;
  document.body.classList.add("broadcast-expanded");
  stage.style.transform="none";
  stage.setAttribute("role","dialog");stage.setAttribute("aria-modal","true");
  $("#broadcast-scrim").hidden=false;$("#broadcast-minimize").hidden=false;
  moveSurface(from);$("#broadcast-minimize").focus({preventScroll:true});
}
async function minimize(){
  if(!state.expanded)return;
  if(document.fullscreenElement===stage){
    try{await document.exitFullscreen();}catch{return;}
    if(!state.expanded)return;
  }
  const from=visibleCorners();cancelSurfaceMotion();
  state.expanded=false;document.body.classList.remove("broadcast-expanded");
  stage.setAttribute("role","region");stage.removeAttribute("aria-modal");
  $("#broadcast-scrim").hidden=true;$("#broadcast-minimize").hidden=true;
  positionStage();moveSurface(from);state.lastFocus?.focus({preventScroll:true});
}
async function market() {
  if(document.hidden||!state.enabled)return;
  try{
    const response=await fetch("/api/broadcast/market",{cache:"no-store"});
    if(!response.ok)throw new Error("Market feed unavailable");
    const data=await response.json();
    const rows=data.items||data.quotes||[];
    const items=Object.keys(tickerLinks).map(symbol=>rows.find(row=>row.symbol===symbol)||{symbol,price:null,change_percent:null,status:"unavailable"});
    const available=data.ok&&items.some(item=>item.price!=null&&Number.isFinite(Number(item.price)));
    $("#broadcast-market-status").textContent=available?`${data.source||"Market data"}${data.delayed?" · Delayed":""}`:(data.reason==="broadcast_disabled"?"Broadcast disabled":"Market feed unavailable");
    $("#bull-tape").innerHTML=items.slice(0,12).map(item=>{
      const value=(item.price==null?NaN:Number(item.price));
      const change=(item.change_percent==null?NaN:Number(item.change_percent));
      return `<a href="${tickerLinks[item.symbol]}" target="_blank" rel="noopener noreferrer" title="${escape([item.instrument_label||item.symbol,item.source||"Unavailable",item.freshness||item.status,item.as_of||"No update time"].join(" · "))}" aria-label="Open ${escape(item.symbol)} market details in a new tab"><b>${escape(item.symbol==='GLD'?'GLD ETF':item.symbol||item.label)}</b> ${Number.isFinite(value)?value.toLocaleString(undefined,{maximumFractionDigits:2}):"—"}${item.stale?" (stale)":item.delayed?" (delayed)":""} <em class="${change<0?"negative":"positive"}">${Number.isFinite(change)?`${change>0?"+":""}${change.toFixed(2)}%`:""}</em></a>`;
    }).join("");
    const updated=data.as_of||data.updated_at||data.timestamp;
    if(updated)$("#broadcast-market-status").textContent+=` · ${new Date(updated).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"})}`;
  }catch{$("#broadcast-market-status").textContent="Market feed unavailable";$("#bull-tape").innerHTML="<span>Unable to refresh market data</span>";}
}
function scheduleMarket(){clearInterval(marketTimer);marketTimer=null;if(!document.hidden&&state.enabled){market();marketTimer=setInterval(market,60000);}}
async function selectChannel(id){
  const channel=state.config.channels?.find(item=>item.id===id);if(!channel)return;
  selectionVersion++;pause();brief?.reset();selected=channel;playerRevealed=false;
  state.provider=channel.kind==="brief"?"brief":channel.youtube_video_id||channel.youtube_playlist_id?"youtube":channel.video_url?"native":"none";
  state.config.preview=channel.id==="legacy"&&Boolean(state.config.preview);
  $("#broadcast-select").value=id;
  stage.dataset.channelKind=channel.kind;stage.dataset.provider=state.provider;
  $("#broadcast-source").textContent=({live:"LIVE CHANNEL",replay:"REPLAY",brief:"PRIVATE",external:"OFFICIAL CHANNEL","coming-soon":"COMING SOON"})[channel.kind]||"VIDEO";
  $("#broadcast-brief").hidden=state.provider!=="brief";
  $("#broadcast-placeholder").hidden=state.provider!=="none";
  $("#broadcast-placeholder h2").textContent=channel.label;
  $("#broadcast-placeholder p").textContent=channel.kind==="coming-soon"?"Your Academy content will have its own home here once the channel is ready.":"Open the official channel for current programs and event replays.";
  video.hidden=state.provider!=="native";
  $("#broadcast-youtube").hidden=state.provider!=="youtube";
  $("#broadcast-feature strong").textContent=channel.label;
  $("#broadcast-feature small").textContent="Open / Play ▶";
  $("#broadcast-play").disabled=!state.enabled||state.provider==="none";
  $("#broadcast-message").textContent=channel.kind==="live"?"Press Play for the assigned stream. If it has ended, choose another channel.":channel.program?"Replay · "+channel.program:"";
  const link=$("#broadcast-channel");link.hidden=true;
  try{const url=new URL(channel.youtube_channel_url);if(url.protocol==="https:"&&["youtube.com","www.youtube.com"].includes(url.hostname)){link.href=url.href;link.hidden=false;}}catch{}
  if(state.provider==="native")video.src=channel.video_url;
  if(state.youtubeReady&&state.provider==="youtube"){
    if(channel.youtube_playlist_id)state.youtube.cuePlaylist({listType:"playlist",list:channel.youtube_playlist_id});
    else state.youtube.cueVideoById(channel.youtube_video_id);
  }
  if(state.config.preview){$("#broadcast-source").textContent="PREVIEW";$("#broadcast-message").textContent="Preview video · No live channel has been assigned.";$("#broadcast-feature small").textContent="Open to watch ↗";}
  saveSettings();chrome();
}
async function init(){
  stage=$("#broadcast-stage")||document.createElement("section");
  stage.id="broadcast-stage";stage.className="broadcast-stage";stage.removeAttribute("aria-hidden");stage.setAttribute("role","region");stage.setAttribute("aria-label","Broadcast");
  stage.innerHTML=`<header class="broadcast-header"><strong>BROADCAST</strong><label class="broadcast-channel-picker"><span class="sr-only">Broadcast channel</span><select id="broadcast-select" aria-label="Broadcast channel"></select></label><span id="broadcast-source">Loading</span><button id="broadcast-minimize" type="button" aria-label="Return Broadcast to wall" hidden>Return to wall ×</button></header>
    <div class="broadcast-picture"><video id="broadcast-video" preload="none" playsinline loop poster="/dashboard/assets/broadcast/broadcast-preview-poster.png"></video><div id="broadcast-youtube" hidden></div><div id="broadcast-brief" hidden></div><div id="broadcast-placeholder" hidden><small>BROADCAST</small><h2></h2><p></p></div><button id="broadcast-feature" type="button" aria-label="Open Broadcast"><span>YOUR PRIVATE STUDIO</span><strong>Broadcast</strong><small>Open to watch ↗</small></button></div>
    <div class="broadcast-controls"><button id="broadcast-play" type="button" aria-label="Play Broadcast">▶</button><button id="broadcast-mute" type="button" aria-label="Mute Broadcast">Sound</button><label class="broadcast-volume"><input id="broadcast-volume" type="range" min="0" max="100" value="60" aria-label="Broadcast volume"></label><span id="broadcast-time">00:00</span><button id="broadcast-expand" type="button" aria-label="Expand Broadcast">↗</button><button id="broadcast-fullscreen" type="button" aria-label="View Broadcast fullscreen">⛶</button></div>
    <div class="broadcast-tape"><small id="broadcast-market-status">Market feed standby</small><div id="bull-tape"><span>Awaiting market data</span></div></div>
    <footer class="broadcast-footer"><button id="broadcast-stop" type="button">End session</button><span id="broadcast-message" role="status"></span><a id="broadcast-channel" hidden target="_blank" rel="noopener noreferrer">Visit channel ↗</a></footer>`;
  if(!stage.isConnected)$("#app-shell").append(stage);
  let scrim=$("#broadcast-scrim");if(!scrim){scrim=document.createElement("div");scrim.id="broadcast-scrim";scrim.className="broadcast-scrim";$("#app-shell").append(scrim);}scrim.hidden=true;scrim.addEventListener("click",minimize);
  video=$("#broadcast-video");
  new ResizeObserver(fitYoutube).observe($(".broadcast-picture"));
  brief=createBriefView($("#broadcast-brief"),playing=>{if(state.provider==="brief"){state.playing=playing;chrome();}});
  $("#broadcast-select").addEventListener("change",event=>selectChannel(event.target.value));
  video.addEventListener("play",()=>{state.playing=true;chrome();});
  video.addEventListener("pause",()=>{state.playing=false;chrome();});
  video.addEventListener("timeupdate",chrome);
  video.addEventListener("error",()=>{$("#broadcast-message").textContent="Broadcast video could not load. Try again later.";});
  $("#broadcast-feature").addEventListener("click",()=>state.expanded?play():expand());
  stage.addEventListener("click",event=>{if(!state.expanded&&!event.target.closest("button,input,a,label,iframe,select"))expand();});
  $("#broadcast-expand").addEventListener("click",expand);
  $("#broadcast-minimize").addEventListener("click",minimize);
  $("#broadcast-stop").addEventListener("click",()=>{pause();brief.stop();video.currentTime=0;state.youtube?.stopVideo?.();playerRevealed=false;minimize();chrome();});
  $("#broadcast-play").addEventListener("click",()=>state.playing?pause():play());
  $("#broadcast-mute").addEventListener("click",()=>{state.muted=!state.muted;volume();saveSettings();});
  $("#broadcast-volume").addEventListener("input",event=>{state.volume=Number(event.target.value)/100;volume();saveSettings();});
  $("#broadcast-fullscreen").addEventListener("click",async()=>{expand();try{if(document.fullscreenElement)await document.exitFullscreen();else if(stage.requestFullscreen)await stage.requestFullscreen();else $("#broadcast-message").textContent="Expanded view is ready. Fullscreen is not supported in this browser.";}catch{$("#broadcast-message").textContent="Fullscreen was not available. Expanded view is ready.";}});
  document.addEventListener("desk:broadcast-open",expand);
  document.addEventListener("desk:roomchange",positionStage);
  document.addEventListener("desk:layout",positionStage);
  document.addEventListener("desk:winston-speaking",event=>{if(event.detail?.source==="broadcast-brief")return;if(event.detail?.speaking&&state.provider==="brief")brief.pause();state.ducked=Boolean(event.detail?.speaking);volume();});
  document.addEventListener("visibilitychange",()=>{if(document.hidden)pause();scheduleMarket();});
  document.addEventListener("keydown",event=>{
    if(!state.expanded)return;
    if(event.key==="Escape"){event.preventDefault();event.stopImmediatePropagation();minimize();}
    if(event.key==="Tab"){const elements=[...stage.querySelectorAll("button,input,select,a[href],iframe")].filter(el=>!el.hidden&&el.getClientRects().length);const first=elements[0],last=elements.at(-1);if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}}
  },true);
  document.addEventListener("fullscreenchange",()=>{cancelSurfaceMotion();$("#broadcast-fullscreen").setAttribute("aria-label",document.fullscreenElement?"Exit Broadcast fullscreen":"View Broadcast fullscreen");});
  matchMedia("(prefers-reduced-motion: reduce)").addEventListener("change",event=>{if(event.matches)cancelSurfaceMotion();});
  window.addEventListener("resize",positionStage);positionStage();
  try{const response=await fetch("/api/broadcast/config",{cache:"no-store"});if(!response.ok)throw Error();state.config=await response.json();state.enabled=Boolean(state.config.enabled);}
  catch{state.config={};$("#broadcast-message").textContent="Broadcast configuration is unavailable.";}
  document.body.dataset.broadcastEnabled=String(state.enabled);
  // Legacy preview config remains supported for older fixtures and installations.
  if(!state.config.channels?.length)state.config.channels=[{id:"legacy",label:"Broadcast",kind:"replay",youtube_video_id:state.config.youtube_video_id,video_url:state.config.video_url||"/dashboard/assets/broadcast/broadcast-preview.mp4",youtube_channel_url:state.config.youtube_channel_url}];
  storageKey=`desk-broadcast:v2:${state.config.storage_scope||"workspace"}`;
  let saved={};try{saved=JSON.parse(localStorage.getItem(storageKey)||"{}");}catch{}
  if(typeof saved.muted==="boolean")state.muted=saved.muted;
  if(Number.isFinite(saved.volume))state.volume=Math.max(0,Math.min(1,saved.volume));
  $("#broadcast-volume").value=String(state.volume*100);
  for(const channel of state.config.channels){const option=document.createElement("option");option.value=channel.id;option.textContent=channel.label+(channel.kind==="coming-soon"?" · Coming soon":channel.kind==="replay"?" · Replay":"");$("#broadcast-select").append(option);}
  await selectChannel(state.config.channels.some(c=>c.id===saved.channel)?saved.channel:state.config.default_channel||state.config.channels[0].id);
  if(!state.enabled)$("#broadcast-message").textContent="Broadcast is disabled for this workspace.";
  volume();scheduleMarket();
  window.__broadcastDebug={state:()=>({enabled:state.enabled,expanded:state.expanded,playing:state.playing,time:state.provider==="youtube"?state.youtube?.getCurrentTime?.():video.currentTime,provider:state.provider,preview:state.config.preview,channel:selected?.id,muted:state.muted,volume:state.volume,environment:roomSnapshot().id}),expand,minimize,play,pause,position:positionStage};
  window.__broadcastReady=true;
}
init();
