// Read-only records surfaces shared by all three bot dashboards.
export function createDeskRecords({active, redraw, escapeHtml: escape}) {
  let research=null,performance=null,query='',offset=0,days=30,error='',pending=false,request=0;
  const expanded=new Set();
  async function load(panel=active()) {
    if(!['research','performance'].includes(panel))return;
    const ticket=++request;pending=true;error='';redraw();
    try {
      const url=panel==='research'?'/api/desk/research?q='+encodeURIComponent(query)+'&offset='+offset:'/api/desk/performance?days='+days;
      const response=await fetch(url,{cache:'no-store'});
      if(!response.ok)throw new Error('Records could not be loaded. Please retry.');
      const data=await response.json();
      if(ticket!==request)return;
      if(panel==='research')research=data;else {
        performance=data;
        if(data.cards?.some(card=>card.pending))setTimeout(()=>{if(active()==='performance'&&request===ticket)load('performance');},4000);
      }
    } catch(e) {if(ticket===request)error=e.message;}
    finally {if(ticket===request){pending=false;if(active()===panel)redraw();}}
  }
  const money=value=>value==null?'—':new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(value);
  const when=value=>{const date=new Date(value);return isNaN(date)?'Update time unavailable':date.toLocaleString();};
  const feedback=()=>error?'<p role="alert">'+escape(error)+' <button data-records-refresh>Retry</button></p>':pending?'<p role="status">Updating records…</p>':'';
  function noteText(text) {
    // Escape first: saved research is content, never executable HTML.
    return escape(text).replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>').replace(/`([^`]+)`/g,'<code>$1</code>').replace(/(^|\s)#{1,4}\s+([^#*<\n]+)/g,'$1<h4>$2</h4>');
  }
  function renderResearch() {
    return `<section class="tool-section desk-records"><p>Research saved by Winston in this bot's journal. Open a note to read it in full.</p>
      <form id="saved-research-search"><label for="saved-research-query">Search saved research</label><div class="records-controls"><input id="saved-research-query" name="query" value="${escape(query)}" placeholder="Topic, symbol or words in a note"><button type="submit">Search</button><button type="button" data-records-refresh>Refresh</button></div></form>
      ${feedback()}${(research?.notes||[]).map(note=>`<details class="decision" data-research-id="${note.id}" ${expanded.has(String(note.id))?'open':''}><summary><strong>${escape(note.topic||'Untitled research')}</strong><span class="decision-meta">${escape(when(note.timestamp))}${note.symbol?' · '+escape(note.symbol):''}</span></summary><div class="saved-research-text">${noteText(note.text||'This saved note has no text body.')}</div></details>`).join('')}
      ${research&&!research.notes.length?'<p class="empty-state">No saved research matches. Ask Winston to research a topic, then refresh this drawer.</p>':''}
      ${research?`<div class="records-controls"><button data-research-page="-1" ${offset===0?'disabled':''}>Previous</button><span>${research.total?offset+1:0}–${Math.min(offset+research.limit,research.total)} of ${research.total}</span><button data-research-page="1" ${offset+research.limit>=research.total?'disabled':''}>Next</button></div>`:''}</section>`;
  }
  function renderPerformance() {
    return `<section class="tool-section desk-records"><div class="records-controls"><label for="performance-days">Closed in the last</label><select id="performance-days">${[7,30,90,365].map(n=>`<option value="${n}" ${days===n?'selected':''}>${n} days</option>`).join('')}</select><button data-records-refresh>Refresh</button></div>${feedback()}
      ${(performance?.cards||[]).map(card=>`<article class="tool-section"><h3>${escape(card.label)}${card.bot_id===performance.current_bot?' · Current bot':''}</h3>
      ${!card.ok?`<p>${escape(card.note)}</p>`:`
      <p class="decision-meta">${escape(card.source)} · ${escape(when(card.as_of))}${card.stale?' · Update overdue':''}</p>
      <div class="metric-grid"><div class="metric"><span>Realized P&amp;L</span><strong>${money(card.realized_pnl)}</strong></div><div class="metric"><span>Win rate</span><strong>${card.win_rate_pct==null?'—':card.win_rate_pct.toFixed(1)+'%'}</strong></div><div class="metric"><span>Closed trades</span><strong>${card.closed_trades}</strong></div></div>
      <p>${escape(card.note)}</p>
      ${card.history_complete===false?'<p role="alert">Broker history is incomplete. P&amp;L is withheld until reconciliation finishes.</p>':''}
      ${card.refresh_failed?'<p role="status">The latest broker refresh failed. The last successful result remains visible with its timestamp.</p>':''}
      ${card.unresolved_count?`<p class="decision-meta">${card.unresolved_count} filled entries are open, partially closed, or missing a linked exit; excluded from closed-trade statistics.</p>`:''}
      ${card.journal_orders_not_in_broker_history?`<p class="decision-meta">${card.journal_orders_not_in_broker_history} historical submissions are not present in the connected broker's retrieved history.</p>`:''}
      ${!card.priced_trades?'<p>No attributed closes with recorded P&amp;L in this period yet. Unavailable values are shown as —.</p>':''}
      ${card.missing_pnl?`<p>${card.missing_pnl} close(s) still lack P&amp;L. The amount and win rate above cover only ${card.priced_trades} priced trades.</p>`:''}
      ${card.unlinked_closes_excluded?`<p class="decision-meta">${card.unlinked_closes_excluded} unlinked account close observations excluded.</p>`:''}
      <details ${expanded.has('trades-'+card.bot_id)?'open':''} data-research-id="trades-${card.bot_id}"><summary>Trade history</summary><div class="records-table"><table><thead><tr><th>Symbol</th><th>Closed</th><th>P&amp;L</th></tr></thead><tbody>${(card.trades||[]).map(t=>`<tr><td>${escape(t.symbol||'—')}${t.strategy?'<small>'+escape(t.strategy)+'</small>':''}</td><td>${escape(when(t.closed_at))}</td><td>${money(t.pnl)}</td></tr>`).join('')}</tbody></table>${card.trade_list_truncated?'<p>Showing the latest 100 closes; totals include every close in the selected period.</p>':''}</div></details>`}
      </article>`).join('')}</section>`;
  }
  function bind(root) {
    root.querySelectorAll('[data-records-refresh]').forEach(button=>button.addEventListener('click',()=>load()));
    root.querySelector('#saved-research-search')?.addEventListener('submit',event=>{event.preventDefault();query=new FormData(event.currentTarget).get('query').trim();offset=0;load('research');});
    root.querySelectorAll('[data-research-page]').forEach(button=>button.addEventListener('click',()=>{offset=Math.max(0,offset+Number(button.dataset.researchPage)*20);load('research');}));
    root.querySelector('#performance-days')?.addEventListener('change',event=>{days=Number(event.target.value);load('performance');});
    root.querySelectorAll('[data-research-id]').forEach(detail=>detail.addEventListener('toggle',()=>{if(detail.open)expanded.add(detail.dataset.researchId);else expanded.delete(detail.dataset.researchId);}));
  }
  return {load,renderResearch,renderPerformance,bind};
}
