"""Actualizador incremental: se ejecuta fuera de Streamlit.

Si la API de NBA falla, el CSV existente NO se elimina.
"""
from __future__ import annotations
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Callable
import pandas as pd
from model import normalize_games

SEASON_PATTERN = re.compile(r'^20\d{2}-\d{2}$')

def current_seasons(today=None) -> list[str]:
    """Temporada en curso y anterior, con corte octubre-septiembre."""
    from datetime import date
    today = today or date.today()
    start = today.year if today.month >= 10 else today.year - 1
    return [f'{year}-{(year + 1) % 100:02d}' for year in (start-1, start)]

def _nba_fetch(season: str) -> pd.DataFrame:
    try:
        from nba_api.stats.endpoints import playergamelogs
    except ImportError as exc:
        raise RuntimeError('Falta nba_api; instalá requirements.txt') from exc
    result = playergamelogs.PlayerGameLogs(
        season_nullable=season,
        season_type_nullable='Regular Season',
        per_mode_simple_nullable='Totals',
        timeout=35
    )
    return result.get_data_frames()[0]

def fetch_seasons(seasons: list[str] | None = None,
                  target: str = 'nba_games.csv',
                  fetcher: Callable[[str], pd.DataFrame] | None = None,
                  retries: int = 2,
                  pause_seconds: float = 1.2) -> tuple[pd.DataFrame, list[str]]:
    """Conserva históricos y actualiza por PLAYER_ID + GAME_ID.

    Valida todo antes de sustituir el CSV. Permite simular la API en pruebas.
    """
    seasons = list(dict.fromkeys(seasons or current_seasons()))
    for season in seasons:
        if not SEASON_PATTERN.fullmatch(season) or int(season[-2:]) != (int(season[:4])+1) % 100:
            raise ValueError(f'Temporada inválida: {season}')
    if retries < 1:
        raise ValueError('retries debe ser >= 1')
    source = fetcher or _nba_fetch
    destination = Path(target)
    old = None
    if destination.exists():
        old = normalize_games(pd.read_csv(destination, dtype={'PLAYER_ID':str, 'GAME_ID':str}))
    batches, logs = [], []
    for season in seasons:
        for attempt in range(1, retries + 1):
            try:
                response = source(season)
                if response is None or response.empty:
                    logs.append(f'{season}: respuesta vacía; se conservan los datos anteriores')
                    break
                batch = normalize_games(response)
                batches.append(batch)
                logs.append(f'{season}: recibidos {len(batch)} registros')
                break
            except Exception as exc:
                if attempt < retries:
                    if pause_seconds:
                        time.sleep(pause_seconds * attempt)
                else:
                    logs.append(f'{season}: error tras {retries} intento(s): {exc}')
        if pause_seconds:
            time.sleep(pause_seconds)
    if not batches:
        raise RuntimeError('No se pudieron obtener registros nuevos. No se modificó la base. ' + ' | '.join(logs))
    combined = pd.concat(([old] if old is not None else []) + batches,
                         ignore_index=True)
    combined = combined.drop_duplicates(['PLAYER_ID','GAME_ID'], keep='last')
    combined = normalize_games(combined)
    if old is not None and len(combined) < len(old):
        raise RuntimeError('La actualización eliminaría registros previos: no se guardó.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='',
                suffix='.csv', prefix='.nba_games_', dir=destination.parent,
                delete=False) as handle:
            tmp_path = Path(handle.name)
            combined.to_csv(handle, index=False)
        os.replace(tmp_path, destination)
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink()
    logs.append(f'Base guardada: {len(combined)} filas; antes: {len(old) if old is not None else 0}')
    return combined, logs
