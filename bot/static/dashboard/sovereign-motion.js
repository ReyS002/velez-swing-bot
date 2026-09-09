// Presentation only: animate navigation, then invoke the existing panel adapter.
// This module never calls broker, voice, music, or approval endpoints.
const ASSETS='/dashboard/assets/sovereign/';
const PANELS=new Set(['phone','music','notes','mission','bookshelf','vault','lamp','journal']);
const OBJECT={notes:'notes',mission:'mission',bookshelf:'bookshelf',vault:'vault',lamp:'lamp',phone:'phone',music:'music',journal:'journal'};
// One visible volume in each 1672 × 941 room plate. Some shelves use horizontal books.
const BOOKS={media:[151,170,10,50],pacific:[384,200,10,51],tokyo:[333,185,10,59],manhattan:[345,222,64,8],dubai:[344,454,10,42]};
export function mountObjectMotion({open,roomRect,roomSnapshot}) {
  if(document.documentElement.dataset.objectMotionMounted)return;
  document.documentElement.dataset.objectMotionMounted='true';
  const reduced=matchMedia('(prefers-reduced-motion: reduce)');
  let preference=true,pending=null,sequence=0;
  try{preference=localStorage.getItem('sovereign-object-motion')!=='off';}catch{}
  function enabled(){return preference&&!reduced.matches;}
  function sync(){document.body.dataset.objectMotion=enabled()?'on':'off';const b=document.getElementById('object-motion-toggle');if(b){b.textContent='Object motion: '+(preference?'On':'Off')+(reduced.matches?' · reduced motion':'');b.setAttribute('aria-pressed',String(preference));}document.dispatchEvent(new CustomEvent('desk:motionchange'));}
  function cancel(){sequence++;if(pending){pending.animations.forEach(a=>a.cancel());pending.cleanup.reverse().forEach(f=>f());pending=null;}document.body.removeAttribute('data-animating-object');}
  function toggle(){cancel();preference=!preference;try{localStorage.setItem('sovereign-object-motion',preference?'on':'off');}catch{}sync();}
  const button=document.createElement('button');button.id='object-motion-toggle';button.type='button';button.addEventListener('click',toggle);document.querySelector('.sovereign-tools-grid')?.append(button);sync();
  reduced.addEventListener('change',()=>{const next=pending?.navigate;cancel();sync();next?.();});
  function run(panel,source){
    cancel();const target=document.querySelector(`[data-object-id="${OBJECT[panel]}"]`);
    const navigate=()=>open(panel,source);
    // Small-screen Tools navigation should remain immediate when its room object is hidden.
    if(!enabled()||!target||!target.getClientRects().length||innerWidth<700){navigate();return;}
    const token=sequence,animations=[],cleanup=[];pending={animations,cleanup,navigate};
    document.body.dataset.animatingObject=panel;
    const append=(parent,html,className)=>{const e=document.createElement('span');e.className=className;e.setAttribute('aria-hidden','true');e.innerHTML=html;parent.append(e);cleanup.push(()=>e.remove());return e;};
    const animate=(e,frames,duration=420,delay=0)=>{const a=e.animate(frames,{duration,delay,easing:'cubic-bezier(.22,.75,.28,1)',fill:'both'});animations.push(a);return a;};
    const svg=(box,body)=>`<svg viewBox="${box}" aria-hidden="true">${body}</svg>`;
    const img=(file,w,h,attr='')=>`<image href="${ASSETS+file}" width="${w}" height="${h}" ${attr}/>`;
    const layer=(rect)=>{
      const e=append(document.body,'','desk-motion-slice');const room=roomRect();
      Object.assign(e.style,{left:rect.left+'px',top:rect.top+'px',width:rect.width+'px',height:rect.height+'px',backgroundImage:panel==='mission'?`url("${ASSETS}spacing-${document.body.dataset.roomAsset}?v=1.4.3")`:panel==='vault'&&roomSnapshot().id!=='media'?`url("${ASSETS}objects-${document.body.dataset.roomAsset}?v=1.4.3")`:getComputedStyle(document.querySelector('.photo-room')).backgroundImage,backgroundSize:`${room.width}px ${room.height}px`,backgroundPosition:`${room.left-rect.left}px ${room.top-rect.top}px`});return e;
    };
    try {
      if(panel==='phone'){
        const art=target.querySelector('.phone-art'),original=art.querySelector('svg');
        const style=original.style.visibility;original.style.visibility='hidden';cleanup.push(()=>original.style.visibility=style);
        const e=append(art,svg('80 145 1100 980',`<defs><clipPath id="motion-phone-base"><path d="M157 278 Q163 230 208 224 L809 222 Q853 225 865 275 L880 880 L1144 881 L1163 950 L1168 978 V1048 Q1168 1090 1109 1095 H149 Q88 1090 87 1048 V978 L111 881 L142 784Z"/></clipPath><clipPath id="motion-receiver"><path d="M878 210 Q885 160 929 155 L1032 153 Q1078 156 1087 199 L1116 800 Q1120 869 1069 884 L944 884 Q900 883 895 830Z"/></clipPath></defs>${img('phone-glass.png',1254,1254,'clip-path="url(#motion-phone-base)"')}<path d="M90 981 Q620 1010 1165 981 V1048 Q1165 1090 1110 1095 H149 Q90 1090 90 1048Z" fill="#171c1d" stroke="#9e8758" stroke-width="3"/><g class="desk-motion-handset">${img('phone-glass.png',1254,1254,'clip-path="url(#motion-receiver)"')}</g>`),'desk-motion-art');
        animate(e.querySelector('g'),[{transform:'translate(0,0) rotate(0)'},{transform:'translate(-10px,-28px) rotate(-5deg)'}]);
      } else if(panel==='music'){
        const art=target.querySelector('.music-art');
        const e=append(art,svg('58 46 910 1420',`<defs><clipPath id="motion-wheel"><circle cx="509" cy="925" r="190"/></clipPath></defs><g class="desk-motion-wheel">${img('pocket-player.png',1024,1536,'clip-path="url(#motion-wheel)"')}</g>`),'desk-motion-art');
        animate(e.querySelector('g'),[{transform:'rotate(0)'},{transform:'rotate(18deg)'}],360);
        animate(art.querySelector('.music-display'),[{filter:'brightness(1)'},{filter:'brightness(1.35)'}],360);
      } else if(panel==='journal'){
        const art=target.querySelector('.journal-art');
        const e=append(art,svg('100 130 1350 768',`<defs><clipPath id="motion-cover"><path d="M167 243 L901 138 Q935 135 952 150 L1415 620 Q1448 661 1416 672 L518 810 Q487 818 477 798 L124 304Z"/></clipPath></defs><path fill="#ede0bd" stroke="#ba9c69" stroke-width="8" d="M167 243 L920 138 L1430 660 L500 810 L124 304Z"/><path d="M216 291 L516 763" stroke="#bca675" stroke-width="9" opacity=".5"/><g class="desk-motion-cover">${img('journal-no-pen.png',1536,1024,'clip-path="url(#motion-cover)"')}<path class="cover-lining" opacity="0" fill="#dccba5" stroke="#6d381a" stroke-width="16" d="M167 243 L920 138 L1430 660 L500 810 L124 304Z"/></g>`),'desk-motion-art');
        // Rotate around the actual diagonal left spine. Project its lift toward
        // the viewer while leaving both spine endpoints fixed on the desk.
        const u=[753,-105],v=[333,567],det=u[0]*v[1]-u[1]*v[0];
        const frames=Array.from({length:31},(_,i)=>{
          const t=i/30,theta=t*145*Math.PI/180;
          const q=[u[0]*Math.cos(theta),u[1]*Math.cos(theta)-560*Math.sin(theta)];
          const a=(q[0]*v[1]-v[0]*u[1])/det,b=(q[1]*v[1]-v[1]*u[1])/det;
          const c=(-q[0]*v[0]+v[0]*u[0])/det,d=(-q[1]*v[0]+v[1]*u[0])/det;
          return {offset:t,transform:`matrix(${a},${b},${c},${d},${167-a*167-c*243},${243-b*167-d*243})`};
        });
        animate(e.querySelector('g'),frames,650);
        animate(e.querySelector('.cover-lining'),[{opacity:0},{opacity:0,offset:.60},{opacity:1,offset:.64},{opacity:1}],650);
      } else if(panel==='notes'){
        const outline=target.querySelector('.statue-outline');
        if(outline){const pulse=animate(outline,[{opacity:Number(getComputedStyle(outline).opacity)},{opacity:.95,offset:.42},{opacity:.55,offset:.70},{opacity:0}],560);pulse.effect.updateTiming({easing:'ease-in-out'});}
      } else if(panel==='lamp'){
        const r=target.getBoundingClientRect();const e=append(document.body,'','desk-motion-light');Object.assign(e.style,{left:r.left+'px',top:(r.bottom-r.height*.08)+'px',width:r.width*1.05+'px',height:r.height*.23+'px'});
        animate(e,[{opacity:0},{opacity:.6}],400);
      } else if(panel==='mission'){
        const r=target.getBoundingClientRect();const e=layer({left:r.left-r.width*.14,top:r.top-r.height*.13,width:r.width*1.28,height:r.height*1.26});
        const face=target.querySelector('.brief-face');if(face){const clone=face.cloneNode(true);e.append(clone);}
        animate(e,[{transform:'perspective(700px) rotateX(0)'},{transform:'perspective(700px) rotateX(-7deg) translateY(-2px)'}],380);
      } else if(panel==='bookshelf'){
        const [x,y,w,h]=BOOKS[roomSnapshot().id],r=roomRect(),scale=r.width/1672;
        const e=layer({left:r.left+x*scale,top:r.top+y*scale,width:w*scale,height:h*scale});
        e.style.borderRadius='1px';animate(e,[{transform:'translate(0,0) scale(1)'},{transform:`translate(${-2*scale}px,${-3*scale}px) scale(1.035)`}],440);
      } else if(panel==='vault'){
        // Only the safe's front door moves. The dark interior replaces the
        // closed door underneath; the shelf, casing and surrounding books stay fixed.
        const r=target.getBoundingClientRect();
        const interior=append(document.body,'','desk-motion-vault-interior');
        Object.assign(interior.style,{left:r.left+'px',top:r.top+'px',width:r.width+'px',height:r.height+'px'});
        const door=layer(r);door.classList.add('desk-motion-vault-door');
        door.style.transformOrigin='0 50%';
        door.style.clipPath='none';door.style.overflow='visible';
        const front=document.createElement('span');front.className='vault-front';
        for(const k of ['backgroundImage','backgroundSize','backgroundPosition'])front.style[k]=door.style[k];
        door.style.backgroundImage='none';door.append(front);
        const back=document.createElement('span');back.className='vault-back';back.innerHTML='<i></i><b></b>';door.append(back);
        // Negative Y rotation brings the free right edge toward the viewer (+Z),
        // then past the hinge to reveal the inner door, never into the cabinet.
        animate(door,[{transform:'perspective(420px) rotateY(0deg)'},{transform:'perspective(420px) rotateY(-112deg)'}],650);

      }
      Promise.all(animations.map(a=>a.finished)).then(()=>{if(sequence!==token)return;cancel();navigate();}).catch(()=>{});
      if(!animations.length){cancel();navigate();}
    }catch{cancel();navigate();}
  }
  window.addEventListener('click',event=>{
    const source=event.target.closest('.room-hotspot[data-panel],.sovereign-dock [data-desk-action],#sovereign-tools [data-desk-action]');
    const panel=source?.dataset.panel||source?.dataset.deskAction;
    if(source&&PANELS.has(panel)){
      event.preventDefault();event.stopImmediatePropagation();run(panel,source);
    }else if(pending)cancel();
  },true);
  window.addEventListener('keydown',event=>{if(event.key==='Escape')cancel();},true);
  for(const name of ['desk:roomchange','desk:layout'])document.addEventListener(name,cancel);
  window.addEventListener('resize',cancel);
  document.addEventListener('visibilitychange',()=>{if(document.hidden)cancel();});
  // Read-only diagnostics used by the same browser checks on each edition.
  window.__deskMotion={enabled,active:()=>document.body.dataset.animatingObject||null,room:roomSnapshot};
}
