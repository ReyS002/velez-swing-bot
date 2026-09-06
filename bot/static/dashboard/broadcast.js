// One Broadcast player follows the room's own calibrated wall surface.
import {roomRect, roomRegions, roomSnapshot} from "./sovereign-room.js?v=1.0.0";
const $ = selector => document.querySelector(selector);
const state = {enabled:false, expanded:false, playing:false, muted:false, volume:0.6, ducked:false, provider:"native", youtube:null, youtubeReady:false, lastFocus:null, config:{}};
const tickerLinks = {
  SPY: "https://finance.yahoo.com/quote/SPY/",
  QQQ: "https://finance.yahoo.com/quote/QQQ/",
  VIX: "https://finance.yahoo.com/quote/%5EVIX/",
  DXY: "https://finance.yahoo.com/quote/DX-Y.NYB/",
  GOLD: "https://finance.yahoo.com/quote/GC%3DF/",
  "EUR/USD": "https://finance.yahoo.com/quote/EURUSD%3DX/",
  BTC: "https://finance.yahoo.com/quote/BTC-USD/",
  ETH: "https://finance.yahoo.com/quote/ETH-USD/",
};
let stage, video, marketTimer, youtubePromise;
const escape = value => {const node=document.createElement("span");node.textContent=String(value??"");return node.innerHTML;};
const time = seconds => {const n=Math.max(0,Math.floor(Number(seconds)||0));return String(Math.floor(n/60)).padStart(2,"0")+":"+String(n%60).padStart(2,"0");};

function positionStage() {
  if(!stage||state.expanded)return;
  const r=roomRect(),p=roomRegions().broadcast;
  Object.assign(stage.style,{left:`${r.left+p.x*r.width}px`,top:`${r.top+p.y*r.height}px`,width:`${p.w*r.width}px`,height:`${p.h*r.height}px`});
  stage.dataset.orientation=p.w/p.h>1?"wide":"portrait";
}
function chrome() {
  $("#broadcast-play").textContent=state.playing?"Ⅱ":"▶";
  $("#broadcast-play").setAttribute("aria-label",state.playing?"Pause Broadcast":"Play Broadcast");
  $("#broadcast-mute").textContent=state.muted?"Muted":"Sound";
  $("#broadcast-mute").setAttribute("aria-pressed",String(state.muted));
  $("#broadcast-mute").setAttribute("aria-label",state.muted?"Unmute Broadcast":"Mute Broadcast");
  stage.classList.toggle("is-playing",state.playing);
  $("#broadcast-time").textContent=time(state.provider==="youtube"?state.youtube?.getCurrentTime?.():video.currentTime);
}
function volume() {
  const effective=state.volume*(state.ducked?0.18:1);
  video.volume=effective;video.muted=state.muted;
  if(state.youtubeReady){state.youtube.setVolume(effective*100);if(state.muted)state.youtube.mute();else state.youtube.unMute();}
  chrome();
}
async function youtubePlayer() {
  if(state.youtubeReady)return state.youtube;
  if(youtubePromise)return youtubePromise;
  youtubePromise=new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>reject(new Error("Video service did not load. Try again.")),15000);
    function create(){
      $("#broadcast-youtube").hidden=false;video.hidden=true;
      state.youtube=new window.YT.Player("broadcast-youtube",{
        videoId:state.config.youtube_video_id,
        host:"https://www.youtube-nocookie.com",
        playerVars:{playsinline:1,rel:0,origin:location.origin},
        events:{
          onReady:()=>{clearTimeout(timer);state.youtubeReady=true;volume();resolve(state.youtube);},
          onStateChange:event=>{state.playing=event.data===1;chrome();},
          onError:()=>{clearTimeout(timer);state.playing=false;chrome();$("#broadcast-message").textContent="This video is unavailable. Check the assigned broadcast.";reject(new Error("Video unavailable"));}
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
    if(state.provider==="youtube"){const player=await youtubePlayer();player.playVideo();}
    else await video.play();
    $("#broadcast-message").textContent=state.config.preview?"Preview video · No live channel has been assigned.":"";
  }catch(error){$("#broadcast-message").textContent=error.message||"Playback could not start. Press Play to retry.";}
  chrome();
}
function pause(){video?.pause();state.youtube?.pauseVideo?.();state.playing=false;if(stage)chrome();}
function expand(){
  if(!stage||state.expanded)return;
  state.lastFocus=document.activeElement;state.expanded=true;
  document.body.classList.add("broadcast-expanded");
  stage.setAttribute("role","dialog");stage.setAttribute("aria-modal","true");
  $("#broadcast-scrim").hidden=false;$("#broadcast-minimize").hidden=false;
  $("#broadcast-minimize").focus();
}
function minimize(){
  if(!state.expanded)return;
  state.expanded=false;document.body.classList.remove("broadcast-expanded");
  stage.setAttribute("role","region");stage.removeAttribute("aria-modal");
  $("#broadcast-scrim").hidden=true;$("#broadcast-minimize").hidden=true;
  positionStage();state.lastFocus?.focus();
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
      const value=Number(item.price??item.last??item.value);
      const change=Number(item.change_percent??item.change_pct??item.percent_change);
      return `<a href="${tickerLinks[item.symbol]}" target="_blank" rel="noopener noreferrer" aria-label="Open ${escape(item.symbol)} market details in a new tab"><b>${escape(item.symbol||item.label)}</b> ${Number.isFinite(value)?value.toLocaleString(undefined,{maximumFractionDigits:2}):"—"} <em class="${change<0?"negative":"positive"}">${Number.isFinite(change)?`${change>0?"+":""}${change.toFixed(2)}%`:""}</em></a>`;
    }).join("");
    const updated=data.as_of||data.updated_at||data.timestamp;
    if(updated)$("#broadcast-market-status").textContent+=` · ${new Date(updated).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"})}`;
  }catch{$("#broadcast-market-status").textContent="Market feed unavailable";$("#bull-tape").innerHTML="<span>Unable to refresh market data</span>";}
}
function scheduleMarket(){clearInterval(marketTimer);marketTimer=null;if(!document.hidden&&state.enabled){market();marketTimer=setInterval(market,60000);}}
async function init(){
  stage=$("#broadcast-stage")||document.createElement("section");
  stage.id="broadcast-stage";stage.className="broadcast-stage";stage.removeAttribute("aria-hidden");stage.setAttribute("role","region");stage.setAttribute("aria-label","Broadcast");
  stage.innerHTML=`<header class="broadcast-header"><strong>BROADCAST</strong><span id="broadcast-source">Loading</span><button id="broadcast-minimize" type="button" aria-label="Return Broadcast to wall" hidden>Return to room</button></header>
    <div class="broadcast-picture"><video id="broadcast-video" preload="none" playsinline loop poster="/dashboard/assets/broadcast/broadcast-preview-poster.png"></video><div id="broadcast-youtube" hidden></div><button id="broadcast-feature" type="button" aria-label="Open Broadcast"><span>YOUR PRIVATE STUDIO</span><strong>Broadcast</strong><small>Open to watch ↗</small></button></div>
    <div class="broadcast-controls"><button id="broadcast-play" type="button" aria-label="Play Broadcast">▶</button><button id="broadcast-mute" type="button" aria-label="Mute Broadcast">Sound</button><label class="broadcast-volume"><input id="broadcast-volume" type="range" min="0" max="100" value="60" aria-label="Broadcast volume"></label><span id="broadcast-time">00:00</span><button id="broadcast-expand" type="button" aria-label="Expand Broadcast">↗</button><button id="broadcast-fullscreen" type="button" aria-label="View Broadcast fullscreen">⛶</button></div>
    <div class="broadcast-tape"><small id="broadcast-market-status">Market feed standby</small><div id="bull-tape"><span>Awaiting market data</span></div></div>
    <footer class="broadcast-footer"><button id="broadcast-stop" type="button">End session</button><span id="broadcast-message" role="status"></span><a id="broadcast-channel" hidden target="_blank" rel="noopener noreferrer">Visit channel ↗</a></footer>`;
  if(!stage.isConnected)$("#app-shell").append(stage);
  let scrim=$("#broadcast-scrim");if(!scrim){scrim=document.createElement("div");scrim.id="broadcast-scrim";scrim.className="broadcast-scrim";$("#app-shell").append(scrim);}scrim.hidden=true;scrim.addEventListener("click",minimize);
  video=$("#broadcast-video");
  video.addEventListener("play",()=>{state.playing=true;chrome();});
  video.addEventListener("pause",()=>{state.playing=false;chrome();});
  video.addEventListener("timeupdate",chrome);
  video.addEventListener("error",()=>{$("#broadcast-message").textContent="Broadcast video could not load. Try again later.";});
  $("#broadcast-feature").addEventListener("click",expand);
  $("#broadcast-expand").addEventListener("click",expand);
  $("#broadcast-minimize").addEventListener("click",minimize);
  $("#broadcast-stop").addEventListener("click",()=>{pause();video.currentTime=0;state.youtube?.seekTo?.(0,true);minimize();chrome();});
  $("#broadcast-play").addEventListener("click",()=>state.playing?pause():play());
  $("#broadcast-mute").addEventListener("click",()=>{state.muted=!state.muted;volume();});
  $("#broadcast-volume").addEventListener("input",event=>{state.volume=Number(event.target.value)/100;volume();});
  $("#broadcast-fullscreen").addEventListener("click",async()=>{expand();try{if(document.fullscreenElement)await document.exitFullscreen();else if(stage.requestFullscreen)await stage.requestFullscreen();else $("#broadcast-message").textContent="Expanded view is ready. Fullscreen is not supported in this browser.";}catch{$("#broadcast-message").textContent="Fullscreen was not available. Expanded view is ready.";}});
  document.addEventListener("desk:broadcast-open",expand);
  document.addEventListener("desk:roomchange",positionStage);
  document.addEventListener("desk:layout",positionStage);
  document.addEventListener("desk:winston-speaking",event=>{state.ducked=Boolean(event.detail?.speaking);volume();});
  document.addEventListener("visibilitychange",()=>{if(document.hidden)pause();scheduleMarket();});
  document.addEventListener("keydown",event=>{
    if(!state.expanded)return;
    if(event.key==="Escape"){event.preventDefault();event.stopImmediatePropagation();minimize();}
    if(event.key==="Tab"){const elements=[...stage.querySelectorAll("button,input,a[href],iframe")].filter(el=>!el.hidden&&el.getClientRects().length);const first=elements[0],last=elements.at(-1);if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}}
  },true);
  document.addEventListener("fullscreenchange",()=>$("#broadcast-fullscreen").setAttribute("aria-label",document.fullscreenElement?"Exit Broadcast fullscreen":"View Broadcast fullscreen"));
  window.addEventListener("resize",positionStage);positionStage();
  try{const response=await fetch("/api/broadcast/config",{cache:"no-store"});if(!response.ok)throw Error();state.config=await response.json();state.enabled=Boolean(state.config.enabled);}
  catch{state.config={};$("#broadcast-message").textContent="Broadcast configuration is unavailable.";}
  document.body.dataset.broadcastEnabled=String(state.enabled);
  state.provider=state.config.youtube_video_id?"youtube":"native";
  state.config.preview=state.config.preview??!(state.config.youtube_video_id||state.config.video_url);
  video.src=state.config.video_url||"/dashboard/assets/broadcast/broadcast-preview.mp4";
  $("#broadcast-source").textContent=!state.enabled?"OFFLINE":state.config.preview?"PREVIEW":"VIDEO";
  if(!state.enabled){$("#broadcast-play").disabled=true;$("#broadcast-message").textContent="Broadcast is disabled for this workspace.";}
  else if(state.config.preview)$("#broadcast-message").textContent="Preview video · No live channel has been assigned.";
  if(state.config.youtube_channel_url){const link=$("#broadcast-channel");try{const url=new URL(state.config.youtube_channel_url);if(url.protocol==="https:"&&["youtube.com","www.youtube.com"].includes(url.hostname)){link.href=url.href;link.hidden=false;}}catch{}}
  volume();scheduleMarket();
  window.__broadcastDebug={state:()=>({enabled:state.enabled,expanded:state.expanded,playing:state.playing,time:video.currentTime,provider:state.provider,preview:state.config.preview,environment:roomSnapshot().id}),expand,minimize,play,pause,position:positionStage};
  window.__broadcastReady=true;
}
init();
