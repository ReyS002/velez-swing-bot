from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from types import SimpleNamespace
import json

import pytest

from bot.broadcast_channels import channel_catalog
from bot.broadcast_market import BroadcastMarketService
from bot.calendar_feeds import CalendarFeedService
from bot.desk_brief import DeskBriefService, build_brief
from bot.earnings_cache import EarningsCalendarCache

CSV = 'symbol,name,reportDate,fiscalDateEnding,estimate,currency\nAAPL,Apple,2026-09-10,2026-06-30,1.2,USD\n'
class Response:
    status_code=200
    def __init__(self, value): self.value=value; self.text=value if isinstance(value,str) else json.dumps(value)
    def json(self): return self.value
    def raise_for_status(self): pass
class Session:
    def __init__(self, values): self.values=iter(values); self.calls=[]
    def get(self,url,**kwargs): self.calls.append((url,kwargs)); return Response(next(self.values))


def test_shared_calendar_single_bulk_request_and_failure_retains_rows(tmp_path):
    now=[1000000]; session=Session([CSV,'{"Information":"Daily quota"}',CSV])
    caches=[EarningsCalendarCache(path=tmp_path/'shared.json',key='test',session=session,clock=lambda:now[0]) for _ in range(3)]
    with ThreadPoolExecutor(max_workers=3) as pool:
        values=list(pool.map(lambda c:c.refresh(),caches))
    assert len(session.calls)==1
    assert all(v['source']['ok'] for v in values)
    assert 'symbol' not in session.calls[0][1]['params']
    assert values[0]['items'][0]['time_status']=='not_provided'
    now[0]+=43201
    failed=caches[1].refresh()
    assert failed['items']==values[0]['items']
    assert failed['source']['stale'] and not failed['source']['ok']
    assert failed['source']['reason']=='provider_limit_or_key_error'
    caches[2].refresh(); assert len(session.calls)==2
    now[0]+=1801
    assert caches[2].refresh()['source']['ok']
    assert len(session.calls)==3


def test_invalid_calendar_and_corrupt_cache_are_not_empty_success(tmp_path):
    path=tmp_path/'cache.json';path.write_text('{"version":1,"items":[],"last_success":"broken"}')
    cache=EarningsCalendarCache(path=path,key='test',session=Session(['symbol,reportDate\n']),clock=lambda:1000000)
    result=cache.refresh()
    assert not result['source']['ok']
    assert result['source']['reason']=='invalid_calendar'
    assert json.loads(path.read_text())['last_success']==0


def test_earnings_filters_complete_watchlist_and_current_positions(tmp_path,monkeypatch):
    monkeypatch.setenv('DESK_EARNINGS_CACHE_PATH',str(tmp_path/'shared.json'))
    broker=SimpleNamespace(is_configured=lambda:True,get_positions_raw=lambda:[{'symbol':'AAPL','asset_class':'us_equity'}])
    config={'symbols':[{'symbol':f'SYM{i}','type':'equity'} for i in range(20)]}
    service=CalendarFeedService(broker,config,deque())
    csv=CSV+''.join(f'SYM{i},Symbol,2026-09-10,,1,USD\n' for i in range(20))
    service.earnings_cache=EarningsCalendarCache(path=tmp_path/'shared.json',key='test',session=Session([csv]))
    service.earnings_cache.refresh()
    value=service._earnings(date(2026,9,1),date(2026,9,30))
    assert len(value['items'])==21
    assert value['source']['position_symbols_status']=='ready'
    broker.get_positions_raw=lambda:[]
    service.config={'symbols':[{'symbol':'SYM19','type':'equity'}]}
    assert [r['symbol'] for r in service._earnings(date(2026,9,1),date(2026,9,30))['items']]==['SYM19']


def test_display_credentials_never_touch_execution_adapter(monkeypatch):
    monkeypatch.setenv('DESK_DISPLAY_TRADIER_TOKEN','display-only')
    monkeypatch.setenv('DESK_DISPLAY_ALPACA_KEY','display-only')
    monkeypatch.setenv('DESK_DISPLAY_ALPACA_SECRET','display-only')
    monkeypatch.delenv('DENDRIX_BROADCAST_FEED_URL',raising=False)
    monkeypatch.setattr('bot.broadcast_market.time.time',lambda:1800000000)
    class ForbiddenBroker:
        def __getattribute__(self,name): raise AssertionError('Execution adapter accessed: '+name)
    session=Session([
        {'quotes':{'quote':[{'symbol':'SPY','last':500,'trade_date':1799990000000},{'symbol':'VIX','last':18,'trade_date':1800000000000},{'symbol':'GLD','last':300,'trade_date':1800000000000}]}},
        {'clock':{'state':'open'}},
        {'SPY':{'latestTrade':{'p':501,'t':'2027-01-15T08:00:00Z'},'prevDailyBar':{'c':500}}},
        {'snapshots':{'BTC/USD':{'latestTrade':{'p':90000,'t':'2027-01-15T08:00:00Z'}}}},
    ])
    service=BroadcastMarketService(ForbiddenBroker(),session=session)
    value=service.payload();quotes={r['symbol']:r for r in value['items']}
    assert quotes['SPY']['price']==501 and quotes['SPY']['fallback']
    assert quotes['SPY']['replaced_stale_primary']
    assert quotes['VIX']['price']==18
    assert quotes['GLD']['instrument_label']=='SPDR Gold Shares ETF'
    assert 'GOLD' not in quotes
    assert quotes['DXY']['price'] is None
    service.session=Session([])
    failed=service.payload(refresh=True)
    spy=next(r for r in failed['items'] if r['symbol']=='SPY')
    assert spy['price']==501 and spy['stale'] and spy['freshness']=='refresh_failed'


def daily():
    return {'timestamp':'2026-09-07T15:00:00Z','broker':{'ok':False},'execution_armed':False,'watchlist':[{'symbol':'SPY'},{'symbol':'AAPL'}], 'positions':[], 'risk':{'max_dollar_risk_per_trade':1000},'calendar':{'sources':{'alpha_vantage':{'ok':True}},'events':[{'title':'Consumer Price Index','date':'2026-09-11','time':'08:30','source':'BLS'}],'earnings':[{'symbol':'AAPL','date':'2026-09-10','source':'Alpha Vantage'}]}}


def test_brief_is_factual_broker_aware_and_about_one_minute():
    value=build_brief(daily(),{'items':[]},product='Bull Pilot',provider='Robinhood')
    assert 60<=value['estimated_seconds']<=90
    assert 'Robinhood is not ready' in value['narration']
    assert 'proposal mode' in value['narration']
    assert 'without confirmed release times' in value['narration']
    assert value['private'] and value['facts_only']


def test_followup_owner_isolation_expiry_and_saved_snapshot(monkeypatch):
    calls=[]; clock=[1]
    monkeypatch.setattr('bot.desk_brief.time.monotonic',lambda:clock[0])
    brain=SimpleNamespace(brief_reply=lambda q,c,f:(calls.append(c) or {'reply':'Review the saved events.','provider':'test'}))
    service=DeskBriefService(daily,lambda:{'items':[]},brain,product='Bull Pilot',provider=lambda:'Robinhood')
    brief=service.create('owner-a')
    assert not service.ask('owner-b',brief['id'],'What next?')['ok']
    assert calls==[]
    service.daily=lambda: (_ for _ in ()).throw(AssertionError('Must use saved snapshot'))
    assert service.ask('owner-a',brief['id'],'What next?')['ok']
    assert calls[0]['snapshot']['narration']==brief['narration']
    clock[0]=1802
    assert not service.ask('owner-a',brief['id'],'Again?')['ok']
    assert len(calls)==1


def test_channel_overrides_validate_ids_and_keep_academy_separate(tmp_path,monkeypatch):
    path=tmp_path/'channels.json';path.write_text(json.dumps({'academy':{'kind':'replay','youtube_playlist_id':'PL1234567890','youtube_channel_url':'javascript:evil'},'bloomberg':{'youtube_video_id':'invalid'},'winston':{'kind':'live','youtube_video_id':'12345678901'}}))
    monkeypatch.setenv('DESK_BROADCAST_CHANNELS_PATH',str(path))
    values={r['id']:r for r in channel_catalog()}
    assert values['academy']['youtube_playlist_id']=='PL1234567890'
    assert 'youtube_channel_url' not in values['academy']
    assert values['bloomberg']['youtube_video_id']=='QB5BNdBFujE'
    assert values['winston']['kind']=='brief'

def test_brief_endpoints_require_auth_and_keep_snapshot_private(monkeypatch,tmp_path):
    from fastapi.testclient import TestClient
    from bot.webhook_server import create_app
    for prefix in ('BULLPILOT','VELEZ'):
        monkeypatch.setenv(prefix+'_DASHBOARD_AUTH_ENABLED','true')
        monkeypatch.setenv(prefix+'_DASHBOARD_USERNAME','operator')
        monkeypatch.setenv(prefix+'_DASHBOARD_PASSWORD','test-only-password')
        monkeypatch.setenv(prefix+'_JOURNAL_DB',str(tmp_path/'journal.sqlite'))
    monkeypatch.setenv('BULLPILOT_CLIENT_AUTH_ENABLED','false')
    app=create_app({'portfolio':{'initial_cash':100000},'risk':{},'symbols':[],'webhook':{'execute_orders':False},'scanner':{'enabled':False},'mentor_operations':{'enabled':False},'telegram_command_center':{'enabled':False}})
    app.state.desk_brief.daily=daily
    app.state.desk_brief.market=lambda:{'items':[]}
    app.state.desk_brief.winston=SimpleNamespace(brief_reply=lambda q,c,f:f)
    client=TestClient(app)
    assert client.get('/api/broadcast/brief').status_code==401
    client.auth=('operator','test-only-password')
    response=client.get('/api/broadcast/brief')
    assert response.status_code==200
    assert 'private' in response.headers['cache-control'] and 'no-store' in response.headers['cache-control']
    value=response.json()
    ask=client.post('/api/broadcast/brief/ask',headers={'Origin':'http://testserver'},json={'brief_id':value['id'],'question':'Explain the saved market context'})
    assert ask.status_code==200 and ask.json()['brief_id']==value['id']
    unknown=client.post('/api/broadcast/brief/ask',headers={'Origin':'http://testserver'},json={'brief_id':'unknown','question':'Explain'})
    assert unknown.status_code==404

def test_brief_uses_primary_brain_and_never_refreshes_engine(monkeypatch):
    from bot.webhook_server import WinstonAIService
    monkeypatch.setenv('WINSTON_LLM_PROVIDER','openai_compatible')
    monkeypatch.setenv('WINSTON_LLM_BASE_URL','https://primary.example/v1')
    monkeypatch.setenv('WINSTON_LLM_MODEL','openai/gpt-oss-20b')
    monkeypatch.setenv('WINSTON_LLM_API_KEY','test-only')
    monkeypatch.setenv('WINSTON_RESEARCH_LLM_PROVIDER','gemini')
    monkeypatch.setenv('WINSTON_RESEARCH_LLM_BASE_URL','https://unrelated.example')
    calls=[]
    def post(url,**kwargs):
        calls.append((url,kwargs))
        return Response({'choices':[{'message':{'content':'The saved snapshot reports that Robinhood is not ready. Display quotes are independent.'}}]})
    monkeypatch.setattr('bot.webhook_server.requests.post',post)
    class NoLiveEngine:
        def __getattribute__(self,name):raise AssertionError('Live engine read: '+name)
    result=WinstonAIService(NoLiveEngine()).brief_reply('Is the broker ready?',{'snapshot':{'narration':'Robinhood is not ready. Display quotes are independent.'}},{'reply':'Saved reference'})
    assert not result['degraded'] and result['provider']=='openai_compatible'
    assert calls[0][0]=='https://primary.example/v1/chat/completions'
    assert calls[0][1]['json']['reasoning_effort']=='low'
    assert 'Saved briefing context' in calls[0][1]['json']['messages'][1]['content']
    assert 'Robinhood is not ready' in calls[0][1]['json']['messages'][1]['content']
