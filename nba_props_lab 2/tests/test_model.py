import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from model import normalize_games,normalize_markets,decimal_odds,forecast_player,evaluate_line,predict_markets,backtest
from make_demo import generate_demo

@pytest.fixture(scope='module')
def demo(tmp_path_factory):
    path=tmp_path_factory.mktemp('nba_props_demo')
    return (*generate_demo(path),path)

def test_demo_generates_three_realistic_structures(demo):
    games,markets,path=demo
    assert len(games)==270
    assert set(['PLAYER_ID','GAME_ID','GAME_DATE','FG3M']).issubset(games)
    assert len(markets)>10
    assert 'DEMO' in (path/'games_DEMO_SIMULADO.csv').name

def test_decimal_american():
    assert decimal_odds('-110')==pytest.approx(1+100/110)
    assert decimal_odds('+125')==pytest.approx(2.25)
    assert decimal_odds(1.9)==pytest.approx(1.9)
    with pytest.raises(ValueError): decimal_odds('110')

def test_duplicate_protection(demo):
    games,_,_=demo
    with pytest.raises(ValueError):
        normalize_games(pd.concat([games,games.iloc[[0]]],ignore_index=True))

def test_no_future_leakage(demo):
    games,_,_=demo
    pid='DEMO101'; dt='2026-05-15'
    f1=forecast_player(games,pid,dt,'PRA',simulations=5000)
    extra=games[(games.PLAYER_ID==pid)&(games.GAME_DATE>=pd.Timestamp(dt))].copy()
    extra['PTS']=1000;extra['REB']=1000;extra['AST']=1000
    altered=pd.concat([games[~games.index.isin(extra.index)],extra],ignore_index=True)
    f2=forecast_player(altered,pid,dt,'PRA',simulations=5000)
    assert np.array_equal(f1.sims,f2.sims)

def test_probabilities_push_and_ev(demo):
    games,_,_=demo
    f=forecast_player(games,'DEMO101','2026-08-01','PTS',simulations=5000)
    lines=evaluate_line(f,19,1.9,1.9)
    assert len(lines)==2
    assert sum([lines[0]['probabilidad'],lines[1]['probabilidad'],lines[0]['prob_push']])==pytest.approx(1)
    for b in lines:
        expected=(b['probabilidad']*(b['cuota_decimal']-1) -
                 (1-b['probabilidad']-b['prob_push']))
        assert b['ev_unidad']==pytest.approx(expected)

def test_backtest_with_only_pregame_quotes(demo):
    games,markets,_=demo
    m=normalize_markets(markets)
    bets,all_preds,summary=backtest(games,m,min_ev=-1,simulations=500)
    assert summary['mercados_evaluados']>0
    assert len(bets)>0
    assert set(bets.resultado).issubset({'WIN','LOSS','PUSH'})
    assert 'ganancia_acumulada' in bets
    assert summary['selecciones']==len(bets)


def test_backtest_rejects_after_tipoff(demo):
    games,markets,_=demo
    m=normalize_markets(markets)
    m.loc[0,'quoted_at_utc']=m.loc[0,'tipoff_utc']
    with pytest.raises(ValueError,match='anteriores'):
        backtest(games,m)


def test_predict_markets(demo):
    games,_,path=demo
    m=normalize_markets(pd.read_csv(path/'markets_DEMO_SIMULADO.csv'))
    preds=predict_markets(games,m,simulations=700)
    assert len(preds)==24
    assert preds.probabilidad.dropna().between(0,1).all()
    assert preds['ultimo_partido_historico'].max() < preds['fecha'].min()
