"""Ubicación de los datos NBA compartidos por todos los usuarios.

El CSV está versionado en GitHub: la app solo lo lee.
"""
from pathlib import Path
import pandas as pd
from model import normalize_games

SHARED_FILENAME = 'nba_games.csv'

def shared_path(root: str | Path) -> Path:
    """Prioriza la raíz y admite el CSV anterior de data/ si no existe."""
    root = Path(root)
    primary = root / SHARED_FILENAME
    legacy = root / 'data' / SHARED_FILENAME
    return primary if primary.exists() or not legacy.exists() else legacy

def load_shared_games(root: str | Path) -> pd.DataFrame:
    path = shared_path(root)
    if not path.is_file():
        raise FileNotFoundError(
            f'No existe {SHARED_FILENAME} en el proyecto. '
            'El administrador debe publicarlo en GitHub.'
        )
    raw = pd.read_csv(path, dtype={'PLAYER_ID': str, 'GAME_ID': str})
    return normalize_games(raw)

def dataset_summary(games: pd.DataFrame) -> dict:
    if games.empty:
        return {'records': 0, 'players': 0, 'last_date': None}
    return {'records': len(games),
            'players': int(games['PLAYER_ID'].nunique()),
            'last_date': str(games['GAME_DATE'].max().date())}
