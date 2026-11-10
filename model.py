"""NBA Props Lab: transparent pre-game, probabilistic baseline (NOT a proven edge)."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any
import numpy as np
import pandas as pd

STATS = {'PTS': 'PTS', 'REB': 'REB', 'AST': 'AST', '3PM': 'FG3M',
         'FG3M': 'FG3M', 'PRA': 'PRA'}
REQUIRED_GAMES = ['PLAYER_ID', 'PLAYER_NAME', 'GAME_ID', 'GAME_DATE',
                  'MIN', 'PTS', 'REB', 'AST', 'FG3M']
REQUIRED_MARKETS = ['game_date', 'player_id', 'stat', 'line']


def _minutes(value: Any) -> float:
    if isinstance(value, str) and ':' in value:
        a, b = value.split(':', 1)
        return float(a) + float(b) / 60
    return float(value) if pd.notna(value) else np.nan


def normalize_games(raw: pd.DataFrame) -> pd.DataFrame:
    """Use official PLAYER_ID (never player names) as the unique player key."""
    x = raw.copy()
    x.columns = [c.strip().upper() for c in x.columns]
    missing = set(REQUIRED_GAMES) - set(x.columns)
    if missing:
        raise ValueError(f'Faltan columnas de partidos: {sorted(missing)}')
    x['PLAYER_ID'] = x['PLAYER_ID'].astype('string').str.strip().str.replace(r'\.0$', '', regex=True)
    x['GAME_ID'] = x['GAME_ID'].astype('string').str.strip()
    x['PLAYER_NAME'] = x['PLAYER_NAME'].astype('string').str.strip()
    x['GAME_DATE'] = pd.to_datetime(x['GAME_DATE'], errors='coerce').dt.normalize()
    x['MIN'] = x['MIN'].map(_minutes)
    for k in ['PTS', 'REB', 'AST', 'FG3M']:
        x[k] = pd.to_numeric(x[k], errors='coerce')
    if 'TEAM_ABBREVIATION' not in x:
        x['TEAM_ABBREVIATION'] = ''
    if 'MATCHUP' not in x:
        x['MATCHUP'] = ''
    bad = x[REQUIRED_GAMES].isna().any(axis=1)
    if bad.any():
        raise ValueError(f'{int(bad.sum())} filas tienen datos esenciales ausentes / inválidos.')
    if (x['MIN'] < 0).any() or (x['MIN'] > 65).any():
        raise ValueError('Hay minutos fuera del rango 0-65.')
    if (x[['PTS', 'REB', 'AST', 'FG3M']] < 0).any().any():
        raise ValueError('Hay estadísticas negativas.')
    if (x[['PTS', 'REB', 'AST', 'FG3M']] % 1 != 0).any().any():
        raise ValueError('Las estadísticas de conteo deben ser enteras.')
    if x.duplicated(['PLAYER_ID', 'GAME_ID']).any():
        raise ValueError('Hay partidos duplicados por jugador; auditá antes de continuar.')
    return x.sort_values(['GAME_DATE','GAME_ID','PLAYER_ID']).reset_index(drop=True)


def audit_games(games: pd.DataFrame) -> pd.DataFrame:
    """Non-destructive quality check, usable even with messy uploads."""
    x = games.copy()
    x.columns = [c.strip().upper() for c in x.columns]
    issues = []
    for col in REQUIRED_GAMES:
        if col not in x:
            issues.append(('Columna ausente', col, len(x)))
        else:
            issues.append(('Valores vacíos', col, int(x[col].isna().sum())))
    if {'PLAYER_ID','GAME_ID'}.issubset(x):
        issues.append(('Duplicados jugador-partido', '*', int(x.duplicated(['PLAYER_ID','GAME_ID']).sum())))
    if 'MIN' in x:
        mins = pd.to_numeric(x['MIN'].astype(str).str.split(':').str[0], errors='coerce')
        issues.append(('Minutos fuera de rango', 'MIN', int(((mins<0)|(mins>65)).sum())))
    if 'PLAYER_ID' in x and 'PLAYER_NAME' in x:
        issues.append(('IDs con nombres distintos', '*', int((x.groupby('PLAYER_ID')['PLAYER_NAME'].nunique()>1).sum())))
    return pd.DataFrame(issues, columns=['problema','columna','cantidad'])


def normalize_markets(raw: pd.DataFrame) -> pd.DataFrame:
    x = raw.copy()
    x.columns = [str(c).strip().lower() for c in x.columns]
    missing = set(REQUIRED_MARKETS) - set(x.columns)
    if missing:
        raise ValueError(f'Faltan columnas de líneas: {sorted(missing)}')
    x['player_id'] = x['player_id'].astype('string').str.strip().str.replace(r'\.0$', '', regex=True)
    x['game_date'] = pd.to_datetime(x['game_date'], errors='coerce').dt.normalize()
    x['stat'] = x['stat'].astype(str).str.strip().str.upper().replace({'3PM':'FG3M'})
    x['line'] = pd.to_numeric(x['line'], errors='coerce')
    if x[['player_id','game_date','stat','line']].isna().any().any():
        raise ValueError('Faltan jugador, fecha, estadística o línea.')
    if (~x['stat'].isin(STATS)).any():
        raise ValueError(f'Prop no soportado: {x.loc[~x["stat"].isin(STATS),"stat"].unique().tolist()}')
    if (x['line'] < 0).any():
        raise ValueError('La línea debe ser >=0.')
    for col, default in [('odds_over', np.nan), ('odds_under', np.nan),
                         ('minutes_expected', np.nan), ('matchup_multiplier', 1.0),
                         ('bookmaker', ''), ('quoted_at_utc', ''), ('tipoff_utc', '')]:
        if col not in x:
            x[col] = default
    x['minutes_expected'] = pd.to_numeric(x['minutes_expected'], errors='coerce')
    x['matchup_multiplier'] = pd.to_numeric(x['matchup_multiplier'], errors='coerce').fillna(1.0)
    if x['minutes_expected'].dropna().between(1,48).eq(False).any():
        raise ValueError('Minutos esperados manuales deben estar entre 1 y 48.')
    if not x['matchup_multiplier'].between(0.75,1.25).all():
        raise ValueError('Ajuste de rival fuera del rango permitido [0.75,1.25].')
    return x


def decimal_odds(value: Any) -> float:
    """Decimal (1.90) or American string (+110, -125). Numeric 110 needs explicit + sign."""
    if value is None or pd.isna(value) or str(value).strip() == '':
        return np.nan
    s = str(value).strip()
    if s.startswith(('+','-')):
        a = float(s)
        if abs(a) < 100:
            raise ValueError(f'Cuota americana inválida: {s}')
        return 1 + (a / 100 if a > 0 else 100 / abs(a))
    odds = float(s)
    if not 1.001 <= odds <= 100:
        raise ValueError(f'Cuota decimal inválida: {s} (americanas requieren + o -).')
    return odds


def _seed(player_id: str, game_date: Any, stat: str) -> int:
    s = f'{player_id}|{game_date}|{stat}'.encode('utf-8')
    return int.from_bytes(hashlib.sha256(s).digest()[:4], 'big')


@dataclass
class Forecast:
    sims: np.ndarray
    mean: float
    median: float
    low80: float
    high80: float
    minutes_mean: float
    minutes_sd: float
    dispersion: float
    history_games: int
    last_game_date: str
    manual_minutes: bool
    caution: str


def forecast_player(games: pd.DataFrame, player_id: Any, game_date: Any,
                    stat: str, minutes_expected: float | None = None,
                    matchup_multiplier: float = 1.0, simulations: int = 12000) -> Forecast:
    """All input games must be strictly earlier than target date; no look-ahead."""
    stat = str(stat).upper()
    if stat not in STATS:
        raise ValueError(f'Stat no soportado: {stat}')
    date = pd.Timestamp(game_date).normalize()
    x = games.loc[(games['PLAYER_ID'].astype(str) == str(player_id)) &
                  (games['GAME_DATE'] < date) & (games['MIN'] >= 5)].copy()
    x = x.sort_values(['GAME_DATE','GAME_ID']).tail(55)
    if len(x) < 8:
        raise ValueError(f'Historial insuficiente: {len(x)} partidos (mínimo 8).')
    x['PRA'] = x['PTS'] + x['REB'] + x['AST']
    col = STATS[stat]
    y = x[col].to_numpy(dtype=float)
    mins = x['MIN'].to_numpy(dtype=float)
    recent = min(10, len(x))
    recent_rate = y[-recent:].sum() / mins[-recent:].sum()
    long_rate = y.sum() / mins.sum()
    recent_weight = recent / (recent + 12)  # prior strength; approximately 45% at 10 games
    rate = recent_weight * recent_rate + (1-recent_weight) * long_rate
    # Minutes: robust baseline from actual recent playing time, override for injuries/rotations.
    manual = minutes_expected is not None and pd.notna(minutes_expected)
    if manual:
        exp_min = float(minutes_expected)
    else:
        exp_min = 0.65 * np.median(mins[-5:]) + 0.35 * np.median(mins[-15:])
    if not 1 <= exp_min <= 48:
        raise ValueError('Los minutos proyectados deben estar entre 1 y 48.')
    min_sd = float(np.clip(np.std(mins[-15:], ddof=1) if len(mins)>1 else 3., 2., 7.))
    # Conservative gamma-Poisson overdispersion estimated on recent per-game deviations.
    # Shrink toward mild overdispersion to prevent fake certainty on small samples.
    local_mu = np.maximum(0.01, rate * mins)
    raw_phi = np.mean(((y - local_mu)**2 - local_mu) / np.maximum(local_mu**2, 1))
    phi = float(np.clip(0.5*max(0.,raw_phi) + 0.5*0.09, 0.035, 0.65))
    rng = np.random.default_rng(_seed(str(player_id),date.date(),stat))
    actual_minutes = np.clip(rng.normal(exp_min,min_sd,simulations),0,48)
    mean_counts = np.clip(rate * actual_minutes * float(matchup_multiplier),0,None)
    multiplier = rng.gamma(shape=1/phi, scale=phi, size=simulations)
    sim = rng.poisson(mean_counts * multiplier).astype(int)
    cautions = []
    if len(x) < 15:
        cautions.append('muestra reducida')
    if min_sd >= 5:
        cautions.append('minutos volátiles')
    if matchup_multiplier != 1.0:
        cautions.append('ajuste manual de rival no calibrado')
    if not manual:
        cautions.append('minutos automáticos: revisar lesiones')
    return Forecast(sims=sim, mean=float(sim.mean()), median=float(np.median(sim)),
                    low80=float(np.quantile(sim,.10)),high80=float(np.quantile(sim,.90)),
                    minutes_mean=exp_min,minutes_sd=min_sd,dispersion=phi,
                    history_games=len(x),last_game_date=str(x['GAME_DATE'].max().date()),
                    manual_minutes=manual,caution='; '.join(cautions))


def evaluate_line(f: Forecast, line: float, odds_over: Any, odds_under: Any) -> list[dict]:
    p_over = float(np.mean(f.sims > line))
    p_under = float(np.mean(f.sims < line))
    p_push = float(np.mean(f.sims == line))
    out = []
    for side, p, raw in [('OVER',p_over,odds_over),('UNDER',p_under,odds_under)]:
        dec = decimal_odds(raw)
        if np.isnan(dec):
            continue
        lose = p_under if side == 'OVER' else p_over
        ev = p*(dec-1)-lose  # full stake refunded on push
        # Raw break-even probability conditional on non-push; market margin not removed.
        p_break_even = (1-p_push)/dec
        out.append(dict(lado=side,probabilidad=p,prob_push=p_push,cuota_decimal=dec,
                        prob_equilibrio=p_break_even,ventaja_pp=(p-p_break_even)*100,
                        ev_unidad=ev))
    return out


def predict_markets(games: pd.DataFrame, markets: pd.DataFrame,
                    min_ev: float = .03, simulations: int = 12000) -> pd.DataFrame:
    rows = []
    cache = {}
    names = games.sort_values('GAME_DATE').drop_duplicates('PLAYER_ID',keep='last').set_index('PLAYER_ID')['PLAYER_NAME'].to_dict()
    for _,r in markets.iterrows():
        key = (str(r.player_id), str(r.game_date),r.stat,
               float(r.minutes_expected) if pd.notna(r.minutes_expected) else None,
               float(r.matchup_multiplier))
        try:
            if key not in cache:
                cache[key] = forecast_player(games,r.player_id,r.game_date,r.stat,
                    key[3], key[4], simulations=simulations)
            f = cache[key]
            bets = evaluate_line(f, r.line, r.odds_over, r.odds_under)
            for bet in bets:
                qualified = bet['ev_unidad'] >= min_ev and f.history_games >= 15
                rows.append({
                    'fecha':str(r.game_date.date()), 'player_id':str(r.player_id),
                    'jugador': names.get(str(r.player_id),'ID desconocido'),
                    'prop': r.stat,'linea':r.line,'casa':r.bookmaker,
                    'proyeccion':round(f.mean,2),'mediana':f.median,
                    'intervalo_80':f'{f.low80:.0f}–{f.high80:.0f}',
                    'minutos_proyectados':round(f.minutes_mean,1),
                    'juegos_historial':f.history_games,
                    'ultimo_partido_historico':f.last_game_date,
                    'lado':bet['lado'], 'probabilidad':round(bet['probabilidad'],4),
                    'prob_push':round(bet['prob_push'],4),
                    'cuota_decimal':round(bet['cuota_decimal'],3),
                    'prob_equilibrio':round(bet['prob_equilibrio'],4),
                    'ventaja_pp':round(bet['ventaja_pp'],2),
                    'ev_unidad':round(bet['ev_unidad'],4),
                    'califica':qualified,'alertas':f.caution,
                    'quoted_at_utc':r.quoted_at_utc,'tipoff_utc':r.tipoff_utc})
        except (ValueError,TypeError,KeyError,OverflowError) as e:
            rows.append({'fecha':str(r.game_date.date()),'player_id':str(r.player_id),
                         'prop':r.stat,'linea':r.line,'error':str(e), 'califica':False})
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values('ev_unidad',ascending=False,na_position='last').reset_index(drop=True)


def backtest(games: pd.DataFrame, historical_markets: pd.DataFrame,
             min_ev:float = .03, simulations:int=3500) -> tuple[pd.DataFrame,pd.DataFrame,dict]:
    """Walk-forward on immutable pre-tipoff quotes. Never use the outcome as an input."""
    m = historical_markets.copy()
    if not {'quoted_at_utc','tipoff_utc'}.issubset(m):
        raise ValueError('Backtest exige quoted_at_utc y tipoff_utc de cada cuota histórica.')
    quoted = pd.to_datetime(m['quoted_at_utc'],utc=True,errors='coerce')
    tipoff = pd.to_datetime(m['tipoff_utc'],utc=True,errors='coerce')
    valid = quoted.notna() & tipoff.notna() & (quoted < tipoff)
    if not valid.all():
        raise ValueError(f'{int((~valid).sum())} cuotas tienen fecha inválida o no son anteriores al inicio del partido.')
    # No pregame quotes after the nominal game date (conservative validation).
    if (m['game_date'].dt.date != (tipoff.dt.tz_convert('America/New_York').dt.date)).any():
        raise ValueError('game_date no coincide con la fecha local del inicio en ET.')
    # Avoid silently counting unrecorded or future outcomes.
    actual = games.copy()
    actual['PRA'] = actual['PTS'] + actual['REB'] + actual['AST']
    actual = actual.drop_duplicates(['PLAYER_ID','GAME_DATE'],keep=False)
    actual_lookup = actual.set_index(['PLAYER_ID','GAME_DATE'])
    all_rows = []
    selected = []
    cache = {}
    for _,r in m.sort_values(['game_date','quoted_at_utc']).iterrows():
        idx = (str(r.player_id),r.game_date)
        if idx not in actual_lookup.index:
            continue
        result = actual_lookup.loc[idx]
        col = STATS[r.stat]
        realized = int(result[col])
        key=(str(r.player_id),str(r.game_date.date()),r.stat,
             float(r.minutes_expected) if pd.notna(r.minutes_expected) else None,
             float(r.matchup_multiplier))
        try:
            if key not in cache:
                cache[key] = forecast_player(games,r.player_id,r.game_date,r.stat,
                    key[3],key[4],simulations=simulations)
            f=cache[key]
            bets=evaluate_line(f,r.line,r.odds_over,r.odds_under)
            prior=games.loc[(games['PLAYER_ID']==str(r.player_id)) &
                            (games['GAME_DATE']<r.game_date) & (games['MIN']>=5)].sort_values('GAME_DATE').tail(10)
            prior_vals=(prior['PTS']+prior['REB']+prior['AST']) if r.stat=='PRA' else prior[STATS[r.stat]]
            naive_over=(float((prior_vals>r.line).sum())+1)/(len(prior_vals)+2)
        except (ValueError,TypeError):
            continue
        for b in bets:
            if realized == r.line:
                outcome='PUSH'
            elif (realized > r.line) == (b['lado']=='OVER'):
                outcome='WIN'
            else:
                outcome='LOSS'
            pnl = b['cuota_decimal']-1 if outcome=='WIN' else (-1 if outcome=='LOSS' else 0.)
            record=dict(fecha=str(r.game_date.date()),jugador=str(result.PLAYER_NAME),
                       player_id=str(r.player_id),prop=r.stat,linea=r.line,
                       casa=r.bookmaker,lado=b['lado'],proyeccion=round(f.mean,2),
                       probabilidad=b['probabilidad'],cuota=b['cuota_decimal'],
                       ev_estimado=b['ev_unidad'],prob_baseline_over=naive_over,
                       real=int(realized),resultado=outcome,
                       pnl_unidades=pnl,quoted_at_utc=str(r.quoted_at_utc),
                       juegos_historial=f.history_games)
            all_rows.append(record)
            if b['ev_unidad'] >= min_ev and f.history_games >= 15:
                selected.append(record)
    all_df=pd.DataFrame(all_rows)
    bets_df=pd.DataFrame(selected)
    if not bets_df.empty:
        bets_df=bets_df.sort_values(['fecha','quoted_at_utc']).reset_index(drop=True)
        bets_df['ganancia_acumulada']=bets_df['pnl_unidades'].cumsum()
        equity=np.r_[0.,bets_df['ganancia_acumulada'].to_numpy()]
        drawdown=np.maximum.accumulate(equity)-equity
        max_dd=float(drawdown.max())
        roi=float(bets_df['pnl_unidades'].mean())
    else:
        max_dd=0.;roi=np.nan
    cal=all_df[all_df['lado']=='OVER'].copy() if not all_df.empty else pd.DataFrame()
    if not cal.empty:
        cal=cal[cal['resultado'] != 'PUSH']
    brier=float(np.mean((cal['probabilidad']-cal['resultado'].eq('WIN'))**2)) if not cal.empty else np.nan
    brier_naive=float(np.mean((cal['prob_baseline_over']-cal['resultado'].eq('WIN'))**2)) if not cal.empty else np.nan
    summary=dict(mercados_evaluados=len(all_df),selecciones=len(bets_df),
                 victorias=int((bets_df['resultado']=='WIN').sum()) if not bets_df.empty else 0,
                 derrotas=int((bets_df['resultado']=='LOSS').sum()) if not bets_df.empty else 0,
                 pushes=int((bets_df['resultado']=='PUSH').sum()) if not bets_df.empty else 0,
                 tasa_acierto=float((bets_df['resultado']=='WIN').sum() / (bets_df['resultado']!='PUSH').sum())
                     if not bets_df.empty and (bets_df['resultado']!='PUSH').any() else np.nan,
                 roi_por_unidad=roi, ganancia_unidades=float(bets_df['pnl_unidades'].sum()) if not bets_df.empty else 0.,
                 max_drawdown_unidades=max_dd, brier_over=brier, brier_baseline_over=brier_naive)
    return bets_df,all_df,summary
