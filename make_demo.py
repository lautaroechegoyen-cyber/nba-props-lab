"""Deterministic artificial examples. DO NOT interpret demo projections as real NBA edges."""
from pathlib import Path
import numpy as np
import pandas as pd
from model import normalize_games, normalize_markets


def generate_demo(folder='data'):
    folder=Path(folder);folder.mkdir(exist_ok=True,parents=True)
    rng=np.random.default_rng(789123)
    players=[('DEMO101','JUGADOR FICTICIO A',.70,.23,.19,.083),
             ('DEMO102','JUGADOR FICTICIO B',.52,.33,.16,.062),
             ('DEMO103','JUGADOR FICTICIO C',.49,.17,.26,.075)]
    dates=pd.date_range('2026-02-15',periods=90,freq='3D')
    games=[];historical=[]
    for j,(pid,name,p_rate,r_rate,a_rate,three_rate) in enumerate(players):
        for i,date in enumerate(dates):
            min_play=float(np.clip(rng.normal(30+j,4),17,40))
            rating=rng.gamma(14,1/14)
            vals={key:int(rng.poisson(max(0,rate*min_play*rating))) for key,rate in
                  [('PTS',p_rate),('REB',r_rate),('AST',a_rate),('FG3M',three_rate)]}
            games.append(dict(PLAYER_ID=pid,PLAYER_NAME=name,GAME_ID=f'DEMO{j}{i:04}',
                              GAME_DATE=date.strftime('%Y-%m-%d'),MIN=round(min_play,1),
                              TEAM_ABBREVIATION=f'D{j+1}',MATCHUP='DEMO @ DEMO',**vals))
            if i>=25 and i%3==0:
                stat='PTS' if i%2==0 else 'REB'
                longrate=p_rate if stat=='PTS' else r_rate
                line=max(0.5,round(longrate*(30+j)-0.5)+0.5)
                t=pd.Timestamp(date.date()).tz_localize('America/New_York')+pd.Timedelta(hours=19,minutes=30)
                quote=t-pd.Timedelta(hours=3)
                historical.append(dict(game_date=date.strftime('%Y-%m-%d'),player_id=pid,
                                       stat=stat,line=line,odds_over='1.90',odds_under='1.90',
                                       minutes_expected='',matchup_multiplier=1.0,
                                       bookmaker='CASA FICTICIA',
                                       quoted_at_utc=quote.tz_convert('UTC').isoformat(),
                                       tipoff_utc=t.tz_convert('UTC').isoformat()))
    games=normalize_games(pd.DataFrame(games))
    games.to_csv(folder/'games_DEMO_SIMULADO.csv',index=False)
    m=pd.DataFrame(historical)
    normalize_markets(m).to_csv(folder/'historical_markets_DEMO_SIMULADO.csv',index=False)
    upcoming=[]
    next_date=(dates.max()+pd.Timedelta(days=3)).strftime('%Y-%m-%d')
    for pid,name,*_ in players:
        for stat,line in [('PTS',20.5),('REB',7.5),('AST',5.5),('PRA',32.5)]:
            upcoming.append(dict(game_date=next_date,player_id=pid,stat=stat,
                                 line=line,odds_over=1.91,odds_under=1.91,
                                 minutes_expected='',matchup_multiplier=1.0,
                                 bookmaker='CASA FICTICIA',quoted_at_utc='',tipoff_utc=''))
    pd.DataFrame(upcoming).to_csv(folder/'markets_DEMO_SIMULADO.csv',index=False)
    cols=['game_date','player_id','stat','line','odds_over','odds_under',
          'minutes_expected','matchup_multiplier','bookmaker','quoted_at_utc','tipoff_utc']
    pd.DataFrame(columns=cols).to_csv(folder/'markets_PLANTILLA_VACIA.csv',index=False)
    pd.DataFrame(columns=cols).to_csv(folder/'historical_markets_PLANTILLA_VACIA.csv',index=False)
    return games,m

if __name__=='__main__':
    g,m=generate_demo()
    print(f'DEMO inventada generada: {len(g)} registros, {len(m)} cuotas históricas ficticias')
