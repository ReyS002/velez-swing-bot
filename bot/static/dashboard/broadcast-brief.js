// Private brief content stays in memory. Voice cards advance on actual audio completion.
export function createBriefView(root, onPlayback) {
  let snapshot=null, audio=null, active=-1, generation=0, controller=null, muted=false, level=.6, mode='read', busy=false;
  const urls=new Map(), preparing=new Map(), requests=new Set();
  root.innerHTML=`<div class="desk-brief-heading"><div><small>PRIVATE · YOUR DESK</small><h2>Winston Desk Brief</h2></div><button type="button" data-action="refresh">Prepare brief</button></div>
    <p class="desk-brief-status" role="status">A fresh snapshot of your markets, calendar and desk, narrated by Winston.</p>
    <nav class="desk-brief-modes" aria-label="Brief format"><button type="button" data-mode="read" aria-pressed="true">Read</button><button type="button" data-mode="listen" aria-pressed="false">Listen</button><button type="button" data-mode="watch" aria-pressed="false">Watch brief</button></nav>
    <div class="desk-brief-cards"></div><form class="desk-brief-ask" hidden><label>Ask Winston about this brief<input name="question" maxlength="1000" autocomplete="off" placeholder="What should I review first?" required></label><button type="submit">Ask Winston</button><p class="desk-brief-answer" role="status"></p></form>`;
  const $=s=>root.querySelector(s), status=text=>$('.desk-brief-status').textContent=text;
  const speaking=value=>{onPlayback(value);document.dispatchEvent(new CustomEvent('desk:winston-speaking',{detail:{speaking:value,source:'broadcast-brief'}}));};
  function pause(){if(busy){generation++;controller?.abort();busy=false;}audio?.pause();speaking(false);}
  function stop(){generation++;for(const request of requests)request.abort();requests.clear();preparing.clear();controller?.abort();controller=null;busy=false;pause();if(audio){audio.removeAttribute('src');audio.load();audio=null;}for(const url of urls.values())URL.revokeObjectURL(url);urls.clear();active=-1;}
  function volume(value,isMuted){level=value;muted=isMuted;if(audio){audio.volume=level;audio.muted=muted;}}
  function highlight(index){root.dataset.mode=mode;root.querySelectorAll('.desk-brief-card').forEach((card,i)=>{card.classList.toggle('active',i===index);card.setAttribute('aria-current',String(i===index));});}
  async function prepare(){
    stop();snapshot=null;const mine=generation;controller=new AbortController();busy=true;
    status('Preparing your desk snapshot…');$('.desk-brief-cards').replaceChildren();$('.desk-brief-ask').hidden=true;$('.desk-brief-answer').textContent='';
    try{
      const response=await fetch('/api/broadcast/brief',{cache:'no-store',signal:controller.signal});
      if(!response.ok)throw Error('The brief could not load. Try preparing it again.');
      const value=await response.json();if(mine!==generation)return;
      snapshot=value;
      for(const section of value.sections){
        const card=document.createElement('article');card.className='desk-brief-card';
        const heading=document.createElement('h3');heading.textContent=section.title;
        const body=document.createElement('p');body.textContent=section.text;
        const source=document.createElement('small');source.textContent=(section.sources||[]).join(' · ')||'Source unavailable';
        card.append(heading,body,source);$('.desk-brief-cards').append(card);
      }
      status(`Saved ${new Date(value.generated_at).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})} · About ${value.estimated_seconds} seconds · Facts from your desk`);
      $('.desk-brief-ask').hidden=false;highlight(-1);
    }catch(error){if(error.name!=='AbortError')status(error.message);}finally{if(mine===generation)busy=false;}
    return snapshot;
  }
  async function audioFor(index,mine){
    if(urls.has(index))return urls.get(index);
    if(preparing.has(index))return preparing.get(index);
    const request=new AbortController();requests.add(request);controller=request;
    const promise=(async()=>{
      try{
        const response=await fetch('/api/winston/speech',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:snapshot.sections[index].text}),signal:request.signal});
        if(!response.ok)throw Error('Winston’s voice is unavailable. You can still read the complete brief.');
        const blob=await response.blob();if(mine!==generation)throw new DOMException('Stopped','AbortError');
        const url=URL.createObjectURL(blob);urls.set(index,url);return url;
      }finally{requests.delete(request);preparing.delete(index);}
    })();
    preparing.set(index,promise);return promise;
  }
  async function playSection(index,mine){
    if(mine!==generation||!snapshot)return;
    if(index>=snapshot.sections.length){active=-1;speaking(false);highlight(-1);status('Brief complete. Ask Winston below, or prepare a fresh snapshot.');return;}
    busy=true;active=index;highlight(index);status(`Preparing Winston’s voice · ${snapshot.sections[index].title}`);
    try{
      const url=await audioFor(index,mine);
      if(mine!==generation)return;
      audio=new Audio(url);volume(level,muted);
      audio.onplay=()=>{if(mine===generation)speaking(true);};audio.onpause=()=>{if(mine===generation)speaking(false);};
      audio.onended=()=>playSection(index+1,mine);
      audio.onerror=()=>{if(mine!==generation)return;speaking(false);status('Audio playback failed. Press Listen to retry, or read the brief.');};
      await audio.play();if(mine!==generation){audio.pause();return;}
      if(index+1<snapshot.sections.length)audioFor(index+1,mine).catch(()=>{});
      status(`${mode==='watch'?'Watching':'Listening'} · ${index+1} of ${snapshot.sections.length} · ${snapshot.sections[index].title}`);
    }catch(error){if(mine===generation&&error.name!=='AbortError'){speaking(false);status(error.message||'Press Listen to start audio.');}}
    finally{if(mine===generation)busy=false;}
  }
  async function play(){
    if(busy)return;
    if(!snapshot){await prepare();if(!snapshot)return;}
    if(mode==='read')setMode('listen',false);
    if(audio?.paused&&!audio.ended&&active>=0){try{await audio.play();}catch{status('Press Listen to resume narration.');}return;}
    await playSection(0,generation);
  }
  function setMode(value,start=true){mode=value;root.dataset.mode=value;root.querySelectorAll('[data-mode]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.mode===value)));if(value==='read'){pause();highlight(-1);}else if(start)play();}
  $('[data-action=refresh]').onclick=prepare;
  root.querySelectorAll('[data-mode]').forEach(button=>button.onclick=()=>setMode(button.dataset.mode));
  $('.desk-brief-ask').onsubmit=async event=>{
    event.preventDefault();if(!snapshot)return;
    const form=event.currentTarget, button=form.querySelector('button'), id=snapshot.id, mine=generation;
    button.disabled=true;$('.desk-brief-answer').textContent='Winston is reviewing the saved snapshot…';
    try{
      const response=await fetch('/api/broadcast/brief/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({brief_id:id,question:form.elements.question.value})});
      const result=await response.json();if(mine!==generation)return;
      if(!response.ok||!result.ok)throw Error('This brief has expired. Prepare a fresh one to continue.');
      $('.desk-brief-answer').textContent=(result.degraded?'Saved brief reference: ':'Winston’s interpretation: ')+result.reply;
    }catch(error){if(mine===generation)$('.desk-brief-answer').textContent=error.message;}finally{button.disabled=false;}
  };
  return {play,pause,stop,volume,prepare,reset(){stop();snapshot=null;$('.desk-brief-cards').replaceChildren();$('.desk-brief-ask').hidden=true;status('Prepare a fresh snapshot of your desk.');},time:()=>audio?.currentTime||0};
}
