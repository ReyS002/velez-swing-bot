const ROOT='/dashboard/assets/guide/';
export async function mountRoomGuide({busy=()=>false}={}){
 const tools=document.querySelector('.sovereign-tools-grid');
 if(!tools||document.querySelector('#room-guide-toggle'))return;
 let catalog;
 try{const response=await fetch(ROOT+'catalog.json?v=1.10.0');if(!response.ok)return;catalog=await response.json();}catch{return;}
 let enabled=false,timer=0,active=null,sequence=0;
 const spoken=new Map(),audio=new Audio();audio.preload='none';
 const toggle=document.createElement('button');toggle.id='room-guide-toggle';toggle.type='button';toggle.setAttribute('aria-pressed','false');toggle.textContent='Winston room guide · Off';tools.prepend(toggle);
 const caption=document.createElement('aside');caption.id='room-guide-caption';caption.hidden=true;caption.setAttribute('aria-label','Winston room guide');
 caption.innerHTML='<div role="status" aria-live="polite" aria-atomic="true"><strong></strong><p></p><small></small></div><div class="room-guide-actions"><button type="button" data-guide-listen>Listen</button><button type="button" data-guide-stop>Stop voice</button><button type="button" data-guide-off>Turn off guide</button></div>';
 document.body.append(caption);
 const listen=caption.querySelector('[data-guide-listen]'),stopButton=caption.querySelector('[data-guide-stop]');
 function occupied(){return busy()||Boolean(window.__broadcastDebug?.state?.().playing)||[...document.querySelectorAll('audio,video')].some(e=>!e.paused&&!e.muted&&e.volume>0);}
 function stop(){sequence++;clearTimeout(timer);audio.pause();audio.removeAttribute('src');audio.load();}
 function clear(){stop();active=null;caption.hidden=true;}
 function status(text){caption.querySelector('small').textContent=text;}
 async function speak(key){
  stop();if(!enabled||occupied()||document.hidden){status('Captions only while other audio or a call is active.');return;}
  const ticket=sequence;audio.src=ROOT+key+'.mp3?v=1.10.0';
  try{await audio.play();if(ticket!==sequence){return;}spoken.set(key,Date.now());status('Winston is speaking.');}
  catch{if(ticket===sequence)status('Voice could not start. You can read the explanation or try Listen.');}
 }
 function show(key,element){
  if(!enabled||!catalog[key]||document.hidden)return;
  stop();active={key,element};caption.querySelector('strong').textContent=catalog[key].title;caption.querySelector('p').textContent=catalog[key].text;caption.hidden=false;
  if(occupied()){status('Captions only while other audio or a call is active.');return;}
  if(Date.now()-(spoken.get(key)||0)<45000){status('Select Listen to hear this explanation again.');return;}
  speak(key);
 }
 function target(node){
  const el=node?.closest?.('[data-object-id],#broadcast-stage,#screen-terminal');if(!el)return null;
  const key=el.dataset.objectId||(el.id==='broadcast-stage'?'broadcast':'tv');return catalog[key]?{key,el}:null;
 }
 function queue(node){const t=target(node);if(!enabled||!t||active?.element===t.el)return;stop();timer=setTimeout(()=>show(t.key,t.el),700);}
 function setEnabled(value){enabled=value;clear();toggle.setAttribute('aria-pressed',String(enabled));toggle.textContent='Winston room guide · '+(enabled?'On':'Off');if(enabled)show('intro',toggle);}
 toggle.addEventListener('click',()=>setEnabled(!enabled));
 listen.addEventListener('click',()=>{if(active)speak(active.key);});stopButton.addEventListener('click',()=>{stop();status('Voice stopped. Captions remain available.');});
 caption.querySelector('[data-guide-off]').addEventListener('click',()=>{setEnabled(false);document.querySelector('[data-desk-action="tools"]')?.focus();});
 document.addEventListener('pointerover',e=>{if(e.pointerType!=='touch')queue(e.target);});
 document.addEventListener('focusin',e=>queue(e.target));
 function leave(e){const old=target(e.target);if(!old||old.el.contains(e.relatedTarget)||caption.contains(e.relatedTarget))return;clearTimeout(timer);if(active?.element===old.el){stop();active=null;caption.hidden=true;}}
 document.addEventListener('pointerout',leave);document.addEventListener('focusout',leave);
 document.addEventListener('click',e=>{if(!caption.contains(e.target)&&e.target!==toggle)clear();},true);
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&enabled){clear();}});
 document.addEventListener('desk:roomchange',clear);document.addEventListener('visibilitychange',()=>{if(document.hidden)clear();});
 document.addEventListener('desk:winston-speaking',e=>{if(e.detail?.speaking){stop();if(active)status('Captions only during your Winston conversation.');}});
 // Covers MusicKit and embedded YouTube without changing their volume or playback.
 setInterval(()=>{if(enabled&&!audio.paused&&occupied()){stop();if(active)status('Captions only while other audio or a call is active.');}},150);
 audio.addEventListener('ended',()=>status('Select Listen to hear this explanation again.'));
 audio.addEventListener('error',()=>{if(active&&audio.getAttribute('src'))status('Voice unavailable. The explanation is shown above.');});
}
