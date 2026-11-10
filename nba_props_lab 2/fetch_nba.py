"""Official stats import; requires internet to stats.nba.com (which may block some IPs)."""
from pathlib import Path
import time
import pandas as pd
from model import normalize_games


def fetch_seasons(seasons: list[str], target: str = 'data/nba_games.csv') -> tuple[pd.DataFrame, list[str]]:
    try:
        from nba_api.stats.endpoints import playergamelogs
    except ImportError as e:
        raise RuntimeError('Instalá dependencias: pip install -r requirements.txt') from e
    frames=[];log=[]
    for season in seasons:
        try:
            # One request per NBA season, rather than hundreds of player requests.
            endpoint=playergamelogs.PlayerGameLogs(
                season_nullable=season,season_type_nullable='Regular Season',
                per_mode_simple_nullable='Totals',timeout=35)
            df=endpoint.get_data_frames()[0]
            if df.empty:
                log.append(f'{season}: respuesta vacía')
            else:
                games=normalize_games(df)
                frames.append(games)
                log.append(f'{season}: {len(games)} registros importados')
        except Exception as exc:
            log.append(f'{season}: ERROR al consultar stats.nba.com: {exc}')
        time.sleep(1.2)
    if not frames:
        raise RuntimeError('No se descargó ninguna temporada. ' + ' | '.join(log) +
                           '. Podés importar un CSV de registros reales manualmente.')
    all_games=pd.concat(frames,ignore_index=True)
    all_games=all_games.drop_duplicates(['PLAYER_ID','GAME_ID'],keep='last')
    all_games=normalize_games(all_games)
    out=Path(target);out.parent.mkdir(parents=True,exist_ok=True)
    all_games.to_csv(out,index=False)
    return all_games,log
