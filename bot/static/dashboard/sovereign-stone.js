import {statueOutline} from './sovereign-statue.js?v=1.13.0';

// Clip generated stone textures to the room surfaces. The original artwork remains
// visible everywhere else, including all interactive objects and the entire view.
const SURFACES={
 tokyo:{edge:'M0 675 L446 584 L448 548 L1040 548 L1672 641 L1672 941 L0 941Z',inset:'M100 769 C98 708 351 640 515 642 L1210 643 C1287 650 1370 720 1417 769 Q1425 792 1388 793 L150 796 Q100 793 100 769Z',chair:'M490 941 L493 883 Q504 845 546 845 L1107 845 Q1149 849 1153 883 L1159 941Z',monitor:'M606 386H1042V585H817V621H884V635H720V621H787V585H606Z',lamp:'M205 513H218V635H230Q269 637 269 650Q261 665 202 665Q151 663 148 652Q145 638 205 635Z',extra:'M245 622V568L286 560V543L324 517L351 529L365 557H387V623Z M1554 518H1672V666Q1594 665 1577 644L1554 550Z'},
 manhattan:{edge:'M0 683 L570 554 L1035 548 L1672 678 L1672 941 L0 941Z',inset:'M121 740 C164 679 353 643 506 642 L1205 642 C1349 648 1514 692 1572 743 Q1597 785 1509 796 L232 796 Q106 791 121 740Z',chair:'M359 941 L382 890 L408 877 L432 840 Q439 811 473 804 Q479 798 506 797 L1035 800 Q1086 811 1093 839 L1117 888 L1140 899 L1141 941Z',monitor:'M568 386H1038V587H823V621H881V650H695V621H775V587H568Z',lamp:'M186 563H199V631Q249 632 253 650Q251 665 191 669Q128 668 126 653Q126 638 186 631Z',extra:'M373 507L455 495L509 522V567L387 587Z M1530 496H1618V635H1550Z M1610 550H1672V692L1604 656Z'},
 pacific:{edge:'M0 656 L559 538 L1027 539 L1672 595 L1672 941 L0 941Z',inset:'M99 747 C146 694 340 659 479 658 L1269 659 C1381 669 1515 721 1539 755 Q1552 797 1474 803 L174 803 Q69 806 99 747Z',chair:'M277 941 Q302 876 429 881 Q443 813 507 798 L1024 798 Q1093 802 1118 862 L1148 941Z',monitor:'M556 378H1026V585H800V616H850V634H717V616H775V585H556Z',lamp:'M135 589H150L180 620L228 630Q277 632 271 651Q264 673 192 676Q120 676 114 659Q113 643 135 638Z',extra:'M1548 544H1672V642H1564Z'},
 dubai:{edge:'M0 658 L557 574 L1024 568 L1672 695 L1672 941 L0 941Z',inset:'M2 745 C33 687 293 634 445 630 L1273 631 C1419 646 1594 706 1629 751 Q1643 791 1564 804 L102 804 Q-1 788 2 745Z',chair:'M264 941V859H368V941Z M1183 941V858H1270V941Z',monitor:'M556 374H1025V593H809V625H883V646H673V625H776V593H556Z',lamp:'M185 551H202V629Q264 633 264 650Q262 669 200 671Q133 669 132 651Q132 635 185 629Z',extra:'M1531 518H1614V647H1547Z M1602 548H1672V718L1591 667Z'}
};
const MATERIAL_ROOMS=new Set(['pacific','tokyo']);
// Material studies retain the original object coordinates. Only architectural
// surfaces are exposed; shelves, screens, lamps and object silhouettes stay live.
const WALLS={
 pacific:{surface:'M70 0H295V599L70 646Z',protect:'M70 190L282 213V378L70 385Z',lamp:'M201 457Q278 434 377 449L387 467L378 479Q282 493 201 475Z M227 476L136 555L143 574L216 630'},
 tokyo:{surface:'M90 80L312 122V610L90 654Z M0 531L90 516V654L0 675Z M312 501L447 486V584L312 615Z',protect:'M99 153L299 189V440L99 445Z',lamp:'M211 468L371 415 M326 444Q377 429 433 451L459 477Q396 495 320 480Z M207 466V637'}
};
export function stoneFile(id,file){return SURFACES[id]?`${MATERIAL_ROOMS.has(id)?'materials':'stone'}-${file}`:null;}
export function layoutStone(plate,id,file,rect,placed){
 let layer=plate.querySelector('.room-stone');
 const spec=SURFACES[id];
 if(!spec){layer?.remove();plate.querySelector('.room-desk-depth')?.remove();return;}
 if(!layer){layer=document.createElement('span');layer.className='room-stone';layer.setAttribute('aria-hidden','true');plate.append(layer);}
 const theme=file.includes('day')?'day':'night';
 const [x,y,w,h]=placed.notes;
 const outlines=statueOutline(id,theme,w,h).replace(/^<svg[^>]*>/,'').replace(/<\/svg>$/,'');
 const [fx,fy,fw,fh]=placed.mission;
 const frame=`M${fx-3} ${fy-18} L${fx+fw+25} ${fy-12} L${fx+fw+21} ${fy+fh+27} L${fx-23} ${fy+fh+12}Z`;
 const wall=WALLS[id];
 const wallMask=wall?`<path fill="white" d="${wall.surface}"/><path fill="black" d="${wall.protect}"/><path fill="none" stroke="black" stroke-width="6" d="${wall.lamp}"/>`:'';
 const mask=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1672 941"><rect width="1672" height="941" fill="black"/><path fill="white" d="${spec.edge}"/>${wallMask}<g fill="black"><path d="${spec.inset}" stroke="white" stroke-width="6"/><path d="${spec.chair} ${spec.monitor} ${spec.lamp} ${wall?'':spec.extra} ${frame}"/><g transform="translate(${x} ${y}) scale(.333333)">${outlines}</g><ellipse cx="${x+w/2}" cy="${y+h*.88}" rx="${w/2}" ry="${h*.12}"/></g></svg>`;
 const uri=`url("data:image/svg+xml,${encodeURIComponent(mask)}")`;
 Object.assign(layer.style,{position:'fixed',display:'block',pointerEvents:'none',left:rect.left+'px',top:rect.top+'px',width:rect.width+'px',height:rect.height+'px',backgroundImage:`url("/dashboard/assets/sovereign/${stoneFile(id,file)}?v=1.11.0")`,backgroundSize:'100% 100%',maskImage:uri,maskMode:'luminance',maskSize:'100% 100%'});
 layer.dataset.room=id;layer.dataset.theme=theme;
 // Shadow only the vertical desk apron; never darken the working surface,
 // objects, chair, or the floor visible through Dubai's central opening.
 let depth=plate.querySelector('.room-desk-depth');
 if(!depth){depth=document.createElement('span');depth.className='room-desk-depth';depth.setAttribute('aria-hidden','true');plate.append(depth);}
 const faces={tokyo:'M0 850H377V941H0Z M1250 850H1672V941H1250Z',manhattan:'M0 851H370V941H0Z M1187 851H1672V941H1187Z',pacific:'M0 864H1672V941H0Z',dubai:'M0 856H260V941H0Z M1274 856H1672V941H1274Z'};
 const shade=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1672 941"><defs><linearGradient id="d" x2="0" y2="1"><stop stop-color="#090b0d" stop-opacity=".36"/><stop offset="1" stop-color="#151317" stop-opacity=".17"/></linearGradient><mask id="m"><rect width="1672" height="941" fill="white"/><path d="${spec.chair}" fill="black"/></mask></defs><path d="${faces[id]}" fill="url(#d)" mask="url(#m)"/></svg>`;
 Object.assign(depth.style,{position:'fixed',pointerEvents:'none',left:rect.left+'px',top:rect.top+'px',width:rect.width+'px',height:rect.height+'px',backgroundImage:`url("data:image/svg+xml,${encodeURIComponent(shade)}")`,backgroundSize:'100% 100%'});

}
