from datetime import date
import pandas as pd
import pytest
from fetch_nba import current_seasons, fetch_seasons
from model import normalize_games, forecast_player
from shared_data import shared_path, load_shared_games, dataset_summary

def rows(points=10):
    return pd.DataFrame([{
        'PLAYER_ID':'203999','PLAYER_NAME':'Jugador de prueba',
        'GAME_ID':'0022600001','GAME_DATE':'2026-11-01','MIN':30,
        'PTS':points,'REB':8,'AST':4,'FG3M':2,'TEAM_ABBREVIATION':'DEN',
        'MATCHUP':'DEN vs. LAL'
    }])

def write(path, frame):
    path.parent.mkdir(parents=True,exist_ok=True)
    frame.to_csv(path,index=False)

def test_root_shared_csv_is_preferred(tmp_path):
    write(tmp_path / 'data/nba_games.csv',rows(9))
    write(tmp_path / 'nba_games.csv',rows(20))
    assert shared_path(tmp_path) == tmp_path/'nba_games.csv'
    games=load_shared_games(tmp_path)
    assert len(games)==1 and games.iloc[0]['PTS']==20
    assert dataset_summary(games)['players']==1

def test_legacy_fallback(tmp_path):
    write(tmp_path / 'data/nba_games.csv',rows())
    assert shared_path(tmp_path)==tmp_path/'data/nba_games.csv'
    assert load_shared_games(tmp_path).iloc[0]['GAME_ID']=='0022600001'

def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError,match='GitHub'):
        load_shared_games(tmp_path)

def test_merge_deduplicates_and_preserves(tmp_path):
    dest=tmp_path/'nba_games.csv'
    write(dest,rows(10))
    new=rows(12)
    row=rows(18).copy()
    row['GAME_ID']='0022600002'
    row['GAME_DATE']='2026-11-02'
    new=pd.concat([new,row],ignore_index=True)
    after,logs=fetch_seasons(['2026-27'],str(dest),fetcher=lambda _:new,
                             retries=1,pause_seconds=0)
    assert len(after)==2
    assert load_shared_games(tmp_path).loc[lambda d:d.GAME_ID=='0022600001','PTS'].iloc[0]==12
    assert any('Base guardada' in x for x in logs)

def test_timeout_keeps_csv_intact(tmp_path):
    dest=tmp_path/'nba_games.csv'
    write(dest,rows())
    before=dest.read_bytes()
    def fail(_):
        raise TimeoutError('Read timed out')
    with pytest.raises(RuntimeError,match='No se modificó'):
        fetch_seasons(['2026-27'],str(dest),fetcher=fail,retries=2,pause_seconds=0)
    assert dest.read_bytes()==before

def test_partial_error_uses_successful_data(tmp_path):
    dest=tmp_path/'nba_games.csv'
    write(dest,rows())
    def partially_blocked(season):
        if season=='2025-26':
            raise TimeoutError('API bloqueada')
        return rows(17)
    data,logs=fetch_seasons(['2025-26','2026-27'],str(dest),
                            fetcher=partially_blocked,retries=1,pause_seconds=0)
    assert len(data)==1 and data.iloc[0]['PTS']==17
    assert any('error' in x for x in logs)

def test_invalid_download_keeps_original(tmp_path):
    dest=tmp_path/'nba_games.csv'
    write(dest,rows())
    before=dest.read_bytes()
    invalid=rows()
    invalid['PTS']=-1
    with pytest.raises(RuntimeError):
        fetch_seasons(['2026-27'],str(dest),fetcher=lambda _:invalid,
                      retries=1,pause_seconds=0)
    assert dest.read_bytes()==before

def test_seasons():
    assert current_seasons(date(2026,11,10))==['2025-26','2026-27']
    assert current_seasons(date(2027,1,10))==['2025-26','2026-27']
    assert current_seasons(date(2027,10,10))==['2026-27','2027-28']

def test_invalid_season(tmp_path):
    with pytest.raises(ValueError):
        fetch_seasons(['unknown'],str(tmp_path/'nba_games.csv'),fetcher=lambda _:rows(),pause_seconds=0)

def test_forecast_excludes_future():
    records=[]
    for i in range(20):
        row=rows(10+i%3).iloc[0].to_dict()
        row['GAME_ID']=f'{2002600000+i:010d}'
        row['GAME_DATE']=(pd.Timestamp('2026-10-01')+pd.Timedelta(days=i)).date().isoformat()
        records.append(row)
    future=dict(records[-1])
    future.update(GAME_ID='0022600999',GAME_DATE='2026-11-01',PTS=95)
    games=normalize_games(pd.DataFrame(records+[future]))
    pred=forecast_player(games,'203999',date(2026,10,22),'PTS',simulations=500)
    assert pred.history_games==20
    assert pred.last_game_date=='2026-10-20'
