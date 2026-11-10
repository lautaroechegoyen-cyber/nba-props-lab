from datetime import datetime, timezone
import pandas as pd
import pytest
import requests
from model import normalize_games
from odds_integration import (normalized_name, parse_event_odds, fetch_live_props,
                              match_players, historical_hits, OddsAPIError)

EVENT = {'id':'event1','commence_time':'2026-11-11T01:00:00Z',
         'home_team':'Denver Nuggets','away_team':'Los Angeles Lakers'}
ODDS = {'bookmakers':[{'key':'fanduel','markets':[{'key':'player_points',
       'last_update':'2026-11-10T20:45:00Z',
       'outcomes':[{'name':'Over','description':'Nikola Jokić','point':24.5,'price':1.9},
                   {'name':'Under','description':'Nikola Jokić','point':24.5,'price':1.91},
                   {'name':'Over','description':'Nikola Jokić','point':-2.5,'price':1.6},
                   {'name':'Over','description':'Someone Else','point':11.5,'price':1.8}]}]}]}

class FakeResponse:
    def __init__(self, data, status=200, headers=None):
        self.data,self.status_code,self.headers=data,status,headers or {}
        self.ok=200<=status<300
    def json(self):
        return self.data

def games():
    data=[]
    for i in range(15):
        data.append({'PLAYER_ID':'203999','PLAYER_NAME':'Nikola Jokic',
                     'GAME_ID':f'001{i:07}',
                     'GAME_DATE':(pd.Timestamp('2026-10-19')+
                         pd.Timedelta(days=i)).strftime('%Y-%m-%d'),
                     'TEAM_ABBREVIATION':'DEN',
                     'MATCHUP':'DEN vs. LAL' if i%2==0 else 'DEN @ LAL',
                     'MIN':32,'PTS':20+i,'REB':8,'AST':4,'FG3M':2})
    return normalize_games(pd.DataFrame(data))

def test_names_and_market_quotes():
    assert normalized_name('Nikola Jokić') == 'nikola jokic'
    rows=parse_event_odds(ODDS,'fanduel',EVENT)
    assert len(rows)==2
    line=next(x for x in rows if x['player']=='Nikola Jokić')
    assert line['odds_over']==1.9 and line['odds_under']==1.91
    assert line['game_date']=='2026-11-10'
    match,unmatch=match_players(games(),rows)
    assert len(match)==1 and unmatch==1 and match[0]['player_id']=='203999'

def test_historical_hit_rates_exclude_future():
    prop={'player_id':'203999','stat':'PTS','line':24.5,'game_date':'2026-11-10'}
    h=historical_hits(games(),prop,n=10)
    assert h['games']==10 and h['hits']==10 and h['average']==29.5
    assert h['history'][0]['Fecha']=='2026-11-02'

def test_home_away_filters_and_push():
    prop={'player_id':'203999','stat':'PTS','line':24,'game_date':'2026-11-10'}
    home=historical_hits(games(),prop,n=10,location='L')
    away=historical_hits(games(),prop,n=10,location='V',side='UNDER')
    assert home['games']==8 and home['pushes']==1
    assert away['games']==7
    assert all('vs.' in row['Rival'] for row in home['history'])

def test_fetch_only_one_market_and_bounded_events():
    calls=[]
    def get(url,params,timeout):
        calls.append((url,params))
        return FakeResponse([EVENT] if url.endswith('/events') else ODDS,
                            headers={'x-requests-remaining':'52'})
    rows,errors,quota=fetch_live_props('SECRET','fanduel','PTS',1,get=get,
              now=datetime(2026,11,10,20,tzinfo=timezone.utc))
    assert len(rows)==2 and not errors and quota==52
    assert len(calls)==2 and calls[1][1]['markets']=='player_points'
    assert calls[1][1]['bookmakers']=='fanduel'
    assert 'SECRET' not in str(rows)

def test_skip_started_or_far_future_games():
    calls=[]
    events=[{**EVENT,'id':'started','commence_time':'2026-11-09T22:00:00Z'},
            {**EVENT,'id':'late','commence_time':'2026-11-14T01:00:00Z'}]
    def get(url,params,timeout):
        calls.append(url)
        return FakeResponse(events)
    rows,errors,quota=fetch_live_props('private',get=get,
                    now=datetime(2026,11,10,20,tzinfo=timezone.utc))
    assert not rows and len(calls)==1

def test_errors_do_not_leak_api_key():
    def get(url,params,timeout):
        raise requests.Timeout('https://bad.example?apiKey=SUPERSECRET')
    with pytest.raises(OddsAPIError) as exc:
        fetch_live_props('SUPERSECRET',get=get)
    assert 'SUPERSECRET' not in str(exc.value)

def test_reject_bad_key_or_bookmaker():
    with pytest.raises(OddsAPIError):
        fetch_live_props('')
    with pytest.raises(ValueError):
        fetch_live_props('private',bookmaker='x?apiKey=hacked')

def test_one_provider_failure_is_isolated():
    def get(url,params,timeout):
        if url.endswith('/events'):
            return FakeResponse([EVENT])
        return FakeResponse({},status=403)
    props,errors,quota=fetch_live_props('private','fanduel','PTS',1,get=get,
                     now=datetime(2026,11,10,20,tzinfo=timezone.utc))
    assert not props and len(errors)==1 and 'Clave inválida' in errors[0]
