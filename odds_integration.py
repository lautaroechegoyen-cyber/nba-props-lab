"""The Odds API NBA player props adapter. No stats.nba.com calls during user sessions.

Adapted from the uploaded props-nba-backend Node.js application.
Uses the shared CSV from GitHub for historical performance.
"""
from __future__ import annotations
import math
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Callable
from zoneinfo import ZoneInfo
import pandas as pd
import requests
from model import STATS

API_ROOT = 'https://api.the-odds-api.com/v4/sports/basketball_nba'
NBA_TIMEZONE = ZoneInfo('America/New_York')
MARKETS = {
    'PTS': 'player_points',
    'REB': 'player_rebounds',
    'AST': 'player_assists',
    '3PM': 'player_threes',
    'PRA': 'player_points_rebounds_assists',
}

class OddsAPIError(RuntimeError):
    """Safe error with no credentials or raw request URLs."""

def normalized_name(name: str) -> str:
    text = unicodedata.normalize('NFKD', str(name))
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', ' ', text.lower()).strip()

def _as_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Timestamp sin zona horaria')
    return parsed.astimezone(timezone.utc)

def _get_json(url: str, params: dict, get: Callable, timeout: int = 20) -> tuple[object, dict]:
    # Never display exception detail here: it may include a URL with apiKey.
    try:
        response = get(url, params=params, timeout=timeout)
    except requests.Timeout as exc:
        raise OddsAPIError('La API de cuotas agotó el tiempo de espera.') from exc
    except requests.RequestException as exc:
        raise OddsAPIError('No se pudo contactar con la API de cuotas.') from exc
    if not response.ok:
        if response.status_code in (401, 403):
            raise OddsAPIError('Clave inválida, sin permisos o plan incompatible con props NBA.')
        if response.status_code == 429:
            raise OddsAPIError('Se alcanzó el límite de consultas de la API de cuotas.')
        raise OddsAPIError(f'La API de cuotas respondió con HTTP {response.status_code}.')
    try:
        return response.json(), dict(response.headers)
    except ValueError as exc:
        raise OddsAPIError('La API de cuotas devolvió JSON inválido.') from exc

def _price(value) -> float | None:
    try:
        n = float(value)
        return n if math.isfinite(n) and 1.001 <= n <= 100 else None
    except (TypeError, ValueError):
        return None

def parse_event_odds(payload: dict, bookmaker: str, event: dict) -> list[dict]:
    """Combine Over and Under quotations for each player/stat/line."""
    reverse = {api: code for code, api in MARKETS.items()}
    try:
        tipoff = _as_utc(event['commence_time'])
    except (KeyError, TypeError, ValueError):
        return []
    date_et = tipoff.astimezone(NBA_TIMEZONE).date().isoformat()
    lines = {}
    for book in payload.get('bookmakers', []):
        if book.get('key') != bookmaker:
            continue
        for market in book.get('markets', []):
            stat = reverse.get(market.get('key'))
            if not stat:
                continue
            for outcome in market.get('outcomes', []):
                side = outcome.get('name', '').strip().lower()
                if side not in ('over', 'under'):
                    continue
                player = str(outcome.get('description', '')).strip()
                try:
                    line = float(outcome.get('point'))
                except (TypeError, ValueError):
                    continue
                if not player or not math.isfinite(line) or line < 0:
                    continue
                price = _price(outcome.get('price'))
                if price is None:
                    continue
                key = (normalized_name(player), stat, line)
                row = lines.setdefault(key, dict(
                    player=player, stat=stat, line=line,
                    odds_over=None, odds_under=None, bookmaker=bookmaker,
                    event_id=event['id'],
                    game=f"{event.get('away_team', '?')} @ {event.get('home_team', '?')}",
                    game_date=date_et, tipoff_utc=tipoff.isoformat(),
                    last_update=market.get('last_update', book.get('last_update', '')),
                ))
                row['odds_over' if side == 'over' else 'odds_under'] = price
    return list(lines.values())

def fetch_live_props(api_key: str, bookmaker: str = 'fanduel', stat: str = 'PTS',
                     max_events: int = 3, *, get: Callable | None = None,
                     now: datetime | None = None) -> tuple[list[dict], list[str], int | None]:
    """Load only upcoming props (next 36h), limiting API credit spend."""
    if not api_key or not api_key.strip():
        raise OddsAPIError('Configurá ODDS_API_KEY en Streamlit Secrets.')
    if not re.fullmatch(r'[a-z0-9_]{2,40}', bookmaker):
        raise ValueError('Código de casa inválido.')
    if stat not in MARKETS:
        raise ValueError('Estadística no soportada.')
    if not 1 <= max_events <= 6:
        raise ValueError('Máximo entre 1 y 6 partidos.')
    get = get or requests.get
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    events, _ = _get_json(f'{API_ROOT}/events', {'apiKey': api_key}, get)
    if not isinstance(events, list):
        raise OddsAPIError('Respuesta de partidos inválida.')
    upcoming = []
    for event in events:
        try:
            when = _as_utc(event['commence_time'])
            if now <= when <= now + timedelta(hours=36) and re.fullmatch(r'[a-zA-Z0-9]+', str(event['id'])):
                upcoming.append((when, event))
        except (KeyError, TypeError, ValueError):
            continue
    upcoming.sort(key=lambda entry: entry[0])
    rows, errors, quota = [], [], None
    for _, event in upcoming[:max_events]:
        params = {'apiKey': api_key, 'regions': 'us', 'bookmakers': bookmaker,
                  'markets': MARKETS[stat], 'oddsFormat': 'decimal'}
        try:
            payload, headers = _get_json(f"{API_ROOT}/events/{event['id']}/odds", params, get)
            if not isinstance(payload, dict):
                raise OddsAPIError('Respuesta de cuotas inválida.')
            rows.extend(parse_event_odds(payload, bookmaker, event))
            remaining = headers.get('x-requests-remaining')
            if remaining is not None:
                try:
                    quota = max(int(remaining), 0)
                except (ValueError, TypeError):
                    pass
        except OddsAPIError as exc:
            errors.append(f"{event.get('away_team', '?')} @ {event.get('home_team', '?')}: {exc}")
    return rows, errors, quota

def match_players(games: pd.DataFrame, props: list[dict]) -> tuple[list[dict], int]:
    """Exact normalized names only, requiring a unique NBA PLAYER_ID."""
    latest = games.sort_values('GAME_DATE').drop_duplicates('PLAYER_ID', keep='last')
    lookup: dict[str, list[tuple[str, str]]] = {}
    for row in latest.itertuples():
        lookup.setdefault(normalized_name(row.PLAYER_NAME), []).append(
            (str(row.PLAYER_ID), str(row.TEAM_ABBREVIATION))
        )
    matched, unmatched = [], 0
    for prop in props:
        candidates = lookup.get(normalized_name(prop['player']), [])
        if len(candidates) != 1:
            unmatched += 1
            continue
        player_id, team = candidates[0]
        matched.append({**prop, 'player_id': player_id, 'team': team})
    return matched, unmatched

def historical_hits(games: pd.DataFrame, prop: dict, n: int = 10,
                    location: str = '', side: str = 'OVER') -> dict:
    """Descriptive hit rate using ONLY games before the event's game date."""
    if not 1 <= n <= 40 or location not in ('', 'L', 'V') or side not in ('OVER','UNDER'):
        raise ValueError('Filtros históricos inválidos.')
    if prop['stat'] not in MARKETS or prop['stat'] not in STATS:
        raise ValueError('Mercado inválido.')
    game_date = pd.Timestamp(prop['game_date'])
    rows = games.loc[(games['PLAYER_ID'].astype(str) == str(prop['player_id'])) &
                     (games['GAME_DATE'] < game_date)].sort_values('GAME_DATE', ascending=False).copy()
    if location:
        is_home = rows['MATCHUP'].astype(str).str.contains('vs.', regex=False)
        is_away = rows['MATCHUP'].astype(str).str.contains('@', regex=False)
        rows = rows.loc[is_home if location == 'L' else is_away]
    rows = rows.head(n)
    vals = rows['PTS'] + rows['REB'] + rows['AST'] if prop['stat'] == 'PRA' else rows[STATS[prop['stat']]]
    line = float(prop['line'])
    wins = int(((vals > line) if side == 'OVER' else (vals < line)).sum())
    pushes = int((vals == line).sum())
    samples = len(vals)
    return {
        'games': samples, 'hits': wins, 'pushes': pushes,
        'hit_pct': round(100 * wins / samples, 1) if samples else None,
        'average': round(float(vals.mean()), 2) if samples else None,
        'history': [
            {'Fecha': d.date().isoformat(), 'Rival': m, 'Resultado': float(v),
             'Supera': bool(v > line) if side == 'OVER' else bool(v < line)}
            for d, m, v in zip(rows['GAME_DATE'], rows['MATCHUP'], vals)
        ]
    }
