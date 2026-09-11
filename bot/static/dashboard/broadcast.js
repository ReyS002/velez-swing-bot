// One Broadcast player follows the room's own calibrated wall surface.
import {broadcastCorners, roomSnapshot} from "./sovereign-room.js?v=1.6.0";
import {createBriefView} from "./broadcast-brief.js?v=1.2.2";
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
let serverChannels=[],managerKey="",managerDialog=null,managerReturnFocus=null;
let managerState={custom:[],overrides:{},order:[],disabled:[]};
const MANAGER_LIMIT=14;
function saveSettings(){try{localStorage.setItem(storageKey,JSON.stringify({channel:selected?.id,muted:state.muted,volume:state.volume}));}catch{}}
const escape = value => {const node=document.createElement("span");node.textContent=String(value??"");return node.innerHTML;};
const time = seconds => {const n=Math.max(0,Math.floor(Number(seconds)||0));return String(Math.floor(n/60)).padStart(2,"0")+":"+String(n%60).padStart(2,"0");};
const clone = value => JSON.parse(JSON.stringify(value));
const validVideoId = value => /^[A-Za-z0-9_-]{11}$/.test(String(value||""));
const validPlaylistId = value => /^[A-Za-z0-9_-]{10,80}$/.test(String(value||""));
function validChannelUrl(value){
  try{const url=new URL(String(value||""));return url.protocol==="https:"&&["youtube.com","www.youtube.com"].includes(url.hostname)&&!url.username&&!url.password;}
  catch{return false;}
}
function cleanManagerState(value){
  const input=value&&typeof value==="object"?value:{};
  return {
    custom:Array.isArray(input.custom)?input.custom.filter(item=>item&&typeof item==="object").slice(0,MANAGER_LIMIT):[],
    overrides:input.overrides&&typeof input.overrides==="object"&&!Array.isArray(input.overrides)?input.overrides:{},
    order:Array.isArray(input.order)?input.order.map(String).slice(0,MANAGER_LIMIT):[],
    disabled:Array.isArray(input.disabled)?input.disabled.map(String).slice(0,MANAGER_LIMIT):[],
  };
}
function readManager(){
  try{return cleanManagerState(JSON.parse(localStorage.getItem(managerKey)||"{}"));}
  catch{return cleanManagerState({});}
}
function writeManager(){
  managerState=cleanManagerState(managerState);
  try{localStorage.setItem(managerKey,JSON.stringify(managerState));}catch{}
}
function managedCatalog(){
  const disabled=new Set(managerState.disabled);
  const defaults=serverChannels.map(channel=>({...clone(channel),...(managerState.overrides[channel.id]||{}),managed_default:true}));
  const custom=managerState.custom.map(channel=>({...clone(channel),managed_custom:true}));
  const all=[...defaults,...custom].filter((channel,index,rows)=>channel?.id&&rows.findIndex(item=>item.id===channel.id)===index);
  const rank=new Map(managerState.order.map((id,index)=>[id,index]));
  all.sort((left,right)=>(rank.get(left.id)??999)-(rank.get(right.id)??999));
  return all.map(channel=>({...channel,enabled:!disabled.has(channel.id)}));
}
function channelType(channel){
  if(channel.kind==="brief")return "Private brief";
  if(channel.youtube_playlist_id)return "YouTube playlist";
  if(channel.youtube_video_id)return channel.kind==="live"?"YouTube live video":"YouTube video";
  if(channel.kind==="coming-soon")return "Coming soon";
  return "Official channel link";
}
function managerStatus(message,error=false){
  const target=managerDialog?.querySelector("[data-channel-status]");
  if(target){target.textContent=message||"";target.dataset.error=String(error);}
}
function renderManager(){
  if(!managerDialog)return;
  const channels=managedCatalog();
  const list=managerDialog.querySelector("[data-channel-list]");
  list.innerHTML=channels.map((channel,index)=>{
    const fixed=channel.id==="winston";
    const source=channel.managed_custom?"Personal":"Desk default";
    return '<article class="channel-manager-row'+(channel.enabled?"":" is-disabled")+'" data-channel-id="'+channel.id+'">'+
      '<div><small>'+escape(channel.category||"My Channels")+' · '+source+'</small><strong>'+escape(channel.label)+'</strong><span>'+escape(channelType(channel))+'</span></div>'+
      '<div class="channel-manager-actions">'+
      '<button type="button" data-channel-action="up" aria-label="Move '+escape(channel.label)+' up" '+(index===0?"disabled":"")+'>↑</button>'+
      '<button type="button" data-channel-action="down" aria-label="Move '+escape(channel.label)+' down" '+(index===channels.length-1?"disabled":"")+'>↓</button>'+
      (fixed?'':('<button type="button" data-channel-action="toggle">'+(channel.enabled?"Disable":"Enable")+'</button>'))+
      (fixed?'':('<button type="button" data-channel-action="edit">Edit</button>'))+
      (channel.managed_custom?'<button type="button" data-channel-action="remove">Remove</button>':'')+
      '</div></article>';
  }).join("");
  managerDialog.querySelector("[data-channel-count]").textContent=channels.length+" of "+MANAGER_LIMIT+" channels";
}
function resetManagerForm(){
  const form=managerDialog?.querySelector("[data-channel-form]");
  if(!form)return;
  form.reset();form.elements.channel_id.value="";form.elements.kind.value="live";form.elements.category.value="My Channels";
  managerDialog.querySelector("[data-channel-form-title]").textContent="Add a channel";
  managerDialog.querySelector("[data-channel-save]").textContent="Add channel";
  managerStatus("");
}
function editManagerChannel(channel){
  const form=managerDialog?.querySelector("[data-channel-form]");
  if(!form||!channel||channel.id==="winston")return;
  form.elements.channel_id.value=channel.id;
  form.elements.label.value=channel.label||"";
  form.elements.category.value=channel.category||"My Channels";
  form.elements.kind.value=["live","replay","external","coming-soon"].includes(channel.kind)?channel.kind:"external";
  form.elements.video_id.value=channel.youtube_video_id||"";
  form.elements.playlist_id.value=channel.youtube_playlist_id||"";
  form.elements.channel_url.value=channel.youtube_channel_url||"";
  managerDialog.querySelector("[data-channel-form-title]").textContent="Edit "+channel.label;
  managerDialog.querySelector("[data-channel-save]").textContent="Save changes";
  form.elements.label.focus();
}
function managerFormChannel(form){
  const label=String(form.elements.label.value||"").trim();
  const category=String(form.elements.category.value||"My Channels").trim();
  const kind=String(form.elements.kind.value||"external");
  const video=String(form.elements.video_id.value||"").trim();
  const playlist=String(form.elements.playlist_id.value||"").trim();
  const url=String(form.elements.channel_url.value||"").trim();
  if(!label)return {error:"Add a channel name."};
  if(video&&!validVideoId(video))return {error:"A YouTube video ID is exactly 11 letters, numbers, dashes, or underscores."};
  if(playlist&&!validPlaylistId(playlist))return {error:"That playlist ID does not look complete."};
  if(url&&!validChannelUrl(url))return {error:"Use a full public YouTube channel URL beginning with https://."};
  if(["live","replay"].includes(kind)&&!video&&!playlist)return {error:"Live and replay entries need a video ID or playlist ID."};
  if(kind==="external"&&!url)return {error:"An official-channel entry needs its YouTube channel URL."};
  const channel={label:label.slice(0,48),category:(category||"My Channels").slice(0,32),kind};
  if(video)channel.youtube_video_id=video;
  if(playlist)channel.youtube_playlist_id=playlist;
  if(url)channel.youtube_channel_url=url;
  return {channel};
}
function slugChannel(label){
  const base=String(label||"channel").toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"").slice(0,25)||"channel";
  let id="custom-"+base,suffix=2;const known=new Set(managedCatalog().map(channel=>channel.id));
  while(known.has(id))id="custom-"+base+"-"+suffix++;
  return id;
}
async function applyManager(preferredId){
  writeManager();
  state.config.channels=managedCatalog();
  await rebuildChannelPicker(preferredId);
  renderManager();
}
function reorderManager(id,direction){
  const ids=managedCatalog().map(channel=>channel.id),index=ids.indexOf(id),next=index+direction;
  if(index<0||next<0||next>=ids.length)return;
  [ids[index],ids[next]]=[ids[next],ids[index]];managerState.order=ids;applyManager(selected?.id);
}
function closeManager(){
  if(!managerDialog||managerDialog.hidden)return;
  managerDialog.hidden=true;document.body.classList.remove("channel-manager-open");managerReturnFocus?.focus({preventScroll:true});
}
function ensureManager(){
  if(managerDialog)return managerDialog;
  managerDialog=document.createElement("section");
  managerDialog.id="broadcast-channel-manager";managerDialog.className="broadcast-channel-manager";managerDialog.hidden=true;
  managerDialog.setAttribute("role","dialog");managerDialog.setAttribute("aria-modal","true");managerDialog.setAttribute("aria-labelledby","channel-manager-title");
  managerDialog.innerHTML='<header><div><small>BROADCAST SETTINGS</small><h2 id="channel-manager-title">Channel Manager</h2><p>Choose what appears on this browser&#39;s desk TV.</p></div><button type="button" data-channel-close aria-label="Close Channel Manager">×</button></header>'+
    '<div class="channel-manager-explainer"><strong>How YouTube works here</strong><p>A video ID plays one exact public video. A playlist ID plays a list that can receive new videos later. Viewers stream public content directly from YouTube in their own browser and do not use your YouTube account.</p></div>'+
    '<div class="channel-manager-layout"><section><div class="channel-manager-list-head"><strong>Your lineup</strong><span data-channel-count></span></div><div class="channel-manager-list" data-channel-list></div><button class="channel-manager-reset" type="button" data-channel-action="reset">Restore desk defaults</button></section>'+
    '<form class="channel-manager-form" data-channel-form><input type="hidden" name="channel_id"><h3 data-channel-form-title>Add a channel</h3>'+
    '<label>Channel name<input name="label" maxlength="48" required placeholder="Example: ECB Press Conference"></label>'+
    '<label>Category<input name="category" maxlength="32" value="My Channels" placeholder="Central Banks"></label>'+
    '<label>Playback type<select name="kind"><option value="live">Live video</option><option value="replay">Replay or playlist</option><option value="external">Official channel link</option><option value="coming-soon">Coming soon</option></select></label>'+
    '<label>Video ID <small>One exact video · 11 characters</small><input name="video_id" autocomplete="off" placeholder="QB5BNdBFujE"></label>'+
    '<label>Playlist ID <small>A list you can update on YouTube</small><input name="playlist_id" autocomplete="off" placeholder="PL..."></label>'+
    '<label>YouTube channel URL<input name="channel_url" type="url" autocomplete="off" placeholder="https://www.youtube.com/@channel"></label>'+
    '<p class="channel-manager-status" data-channel-status role="status"></p><div class="channel-manager-form-actions"><button type="button" data-channel-action="cancel">Clear</button><button type="submit" data-channel-save>Add channel</button></div></form></div>';
  document.body.append(managerDialog);
  document.addEventListener("keydown",event=>{
    if(managerDialog?.hidden||event.key!=="Escape")return;
    event.preventDefault();event.stopImmediatePropagation();closeManager();
  },true);
  managerDialog.querySelector("[data-channel-close]").addEventListener("click",closeManager);
  managerDialog.querySelector("[data-channel-form]").addEventListener("submit",event=>{
    event.preventDefault();
    const form=event.currentTarget,id=String(form.elements.channel_id.value||"");
    const result=managerFormChannel(form);
    if(result.error){managerStatus(result.error,true);return;}
    const existing=managedCatalog().find(channel=>channel.id===id);
    if(id&&existing?.managed_default)managerState.overrides[id]=result.channel;
    else if(id){
      const index=managerState.custom.findIndex(channel=>channel.id===id);
      if(index>=0)managerState.custom[index]={id,...result.channel};
    }else{
      if(managedCatalog().length>=MANAGER_LIMIT){managerStatus("Remove a personal channel before adding another.",true);return;}
      const channelId=slugChannel(result.channel.label);
      managerState.custom.push({id:channelId,...result.channel});
      managerState.order=managedCatalog().map(channel=>channel.id);
    }
    applyManager(id||managerState.custom.at(-1)?.id);resetManagerForm();
  });
  managerDialog.addEventListener("click",event=>{
    const button=event.target.closest("[data-channel-action]");if(!button)return;
    const id=button.closest("[data-channel-id]")?.dataset.channelId,action=button.dataset.channelAction;
    if(action==="cancel")return resetManagerForm();
    if(action==="reset"){if(confirm("Restore the default channel lineup for this browser?")){managerState=cleanManagerState({});applyManager(serverChannels[0]?.id);resetManagerForm();}return;}
    const channel=managedCatalog().find(item=>item.id===id);if(!channel)return;
    if(action==="edit")return editManagerChannel(channel);
    if(action==="up")return reorderManager(id,-1);
    if(action==="down")return reorderManager(id,1);
    if(action==="toggle"){
      const disabled=new Set(managerState.disabled);if(disabled.has(id))disabled.delete(id);else disabled.add(id);managerState.disabled=[...disabled];applyManager(selected?.id);return;
    }
    if(action==="remove"){
      managerState.custom=managerState.custom.filter(item=>item.id!==id);managerState.order=managerState.order.filter(item=>item!==id);managerState.disabled=managerState.disabled.filter(item=>item!==id);applyManager(selected?.id);resetManagerForm();
    }
  });
  managerDialog.addEventListener("keydown",event=>{
    if(event.key==="Escape"){event.preventDefault();event.stopImmediatePropagation();closeManager();return;}
    if(event.key!=="Tab")return;
    const focusable=[...managerDialog.querySelectorAll("button,input,select")].filter(element=>!element.disabled&&element.getClientRects().length);
    const first=focusable[0],last=focusable.at(-1);
    if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
    else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
  });
  return managerDialog;
}
function openManager(){
  managerReturnFocus=document.activeElement;const dialog=ensureManager();renderManager();resetManagerForm();
  dialog.hidden=false;document.body.classList.add("channel-manager-open");dialog.querySelector("[data-channel-close]").focus({preventScroll:true});
}
function rebuildChannelPicker(preferredId){
  const select=$("#broadcast-select");if(!select)return Promise.resolve();
  const channels=state.config.channels.filter(channel=>channel.enabled!==false);
  select.innerHTML="";
  const groups=new Map();
  for(const channel of channels){
    const category=channel.category||"Other";if(!groups.has(category))groups.set(category,[]);groups.get(category).push(channel);
  }
  for(const [category,items] of groups){
    const group=document.createElement("optgroup");group.label=category;
    for(const channel of items){
      const option=document.createElement("option");option.value=channel.id;
      option.textContent=channel.label+(channel.kind==="coming-soon"?" · Coming soon":channel.kind==="replay"?" · Replay":channel.kind==="external"?" · Visit":"");
      group.append(option);
    }
    select.append(group);
  }
  const target=channels.find(channel=>channel.id===preferredId)||channels[0];
  if(!target){select.disabled=true;return Promise.resolve();}
  select.disabled=false;select.value=target.id;
  return selectChannel(target.id);
}

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
  if(document.body.dataset.objectMotion==="off"||!from||!stage.getClientRects().length||!stage.animate||matchMedia("(prefers-reduced-motion: reduce)").matches)return;
  const box=surfaceBox();
  const start=surfaceTransform(from.map(([x,y])=>[x-box.left,y-box.top]),box.width,box.height);
  const end=getComputedStyle(stage).transform;
  stage.classList.add("broadcast-moving");
  const animation=stage.animate([{transform:start},{transform:end}],{duration:500,easing:"cubic-bezier(.22,.75,.2,1)",fill:"both"});
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
  const parent=$(".broadcast-picture"),w=parent.clientWidth,h=parent.clientHeight;
  if(!w||!h)return;
  // Meet YouTube's minimum viewport with one scale on both axes. Its player
  // then fits the source video naturally, without stretching faces or captions.
  const scale=Math.min(1,w/480,h/270);
  Object.assign(iframe.style,{width:(w/scale)+"px",height:(h/scale)+"px",transform:`scale(${scale})`,transformOrigin:"0 0"});
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
          onStateChange:event=>{if(state.provider!=="youtube")return;
            const matches=!selected?.youtube_video_id||state.youtube?.getVideoData?.().video_id===selected.youtube_video_id;
            if(event.data===5&&matches&&state.requestedPlay)state.youtube.playVideo();
            state.playing=event.data===1&&matches;
            if(state.playing)state.requestedPlay=false;
            if(event.data===1){$("#broadcast-message").textContent="";playerRevealed=true;}
            if(event.data===0&&selected?.kind==="live"){$("#broadcast-source").textContent="STREAM ENDED";$("#broadcast-message").textContent="This stream has ended. Choose another channel or visit its official page.";}
            chrome();},
          onError:event=>{state.requestedPlay=false;clearTimeout(timer);if(state.provider!=="youtube")return;state.playing=false;chrome();$("#broadcast-message").textContent=`This stream cannot play here (${event.data}). Choose another channel or use Visit channel.`;reject(new Error("Video unavailable"));}
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
    if(state.provider==="youtube"){state.requestedPlay=true;playerRevealed=true;chrome();const player=await youtubePlayer();if(version!==selectionVersion)return;player.playVideo();}
    else await video.play();
    $("#broadcast-message").textContent="";
  }catch(error){$("#broadcast-message").textContent=error.message||"Playback could not start. Press Play to retry.";}
  chrome();
}
function pause(){state.requestedPlay=false;brief?.pause();video?.pause();state.youtube?.pauseVideo?.();state.playing=false;if(stage)chrome();}
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
      return `<a href="${tickerLinks[item.symbol]}" target="_blank" rel="noopener noreferrer" title="${escape([item.instrument_label||item.symbol,item.source||"Unavailable",item.freshness||item.status,item.as_of||"No update time"].join(" · "))}" aria-label="Open ${escape(item.symbol)} market details in a new tab"><b>${escape(item.symbol==='GLD'?'GLD ETF':item.symbol||item.label)}</b> ${Number.isFinite(value)?value.toLocaleString(undefined,{maximumFractionDigits:2}):"—"}${item.price!=null&&item.stale?" (stale)":item.price!=null&&item.delayed?" (delayed)":""} <em class="${change<0?"negative":"positive"}">${Number.isFinite(change)?`${change>0?"+":""}${change.toFixed(2)}%`:""}</em></a>`;
    }).join("");
    if(data.market_status==="closed")$("#broadcast-market-status").textContent+=" · Equities closed";
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
  $("#broadcast-brief").addEventListener("brief:timeupdate",chrome);
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
  document.addEventListener("desk:broadcast-channels-manager",openManager);
  document.addEventListener("desk:motionchange",()=>{if(document.body.dataset.objectMotion==="off")cancelSurfaceMotion();});
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
  managerKey=`desk-broadcast-manager:v1:${state.config.storage_scope||"workspace"}`;
  serverChannels=clone(state.config.channels);
  managerState=readManager();
  state.config.channels=managedCatalog();
  let saved={};try{saved=JSON.parse(localStorage.getItem(storageKey)||"{}");}catch{}
  if(typeof saved.muted==="boolean")state.muted=saved.muted;
  if(Number.isFinite(saved.volume))state.volume=Math.max(0,Math.min(1,saved.volume));
  $("#broadcast-volume").value=String(state.volume*100);
  await rebuildChannelPicker(state.config.channels.some(c=>c.id===saved.channel&&c.enabled!==false)?saved.channel:state.config.default_channel||state.config.channels.find(c=>c.enabled!==false)?.id);
  if(!state.enabled)$("#broadcast-message").textContent="Broadcast is disabled for this workspace.";
  volume();scheduleMarket();
  window.__broadcastDebug={state:()=>({enabled:state.enabled,expanded:state.expanded,playing:state.playing,time:state.provider==="brief"?brief?.time():state.provider==="youtube"?state.youtube?.getCurrentTime?.():video.currentTime,provider:state.provider,preview:state.config.preview,channel:selected?.id,muted:state.muted,volume:state.volume,environment:roomSnapshot().id,channels:managedCatalog()}),expand,minimize,play,pause,position:positionStage,openManager};
  window.__broadcastReady=true;
}
init();
