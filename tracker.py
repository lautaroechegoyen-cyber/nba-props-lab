"""Append-only prospective pregame forecast log, with post-game settlement columns."""
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd


def append_snapshot(pred: pd.DataFrame, target: str='data/registro_prospectivo.csv') -> tuple[int,int]:
    """Freeze a snapshot of ALL priced props (not just winners or qualifying picks)."""
    if pred.empty or 'cuota_decimal' not in pred:
        return 0,0
    x=pred[pred['cuota_decimal'].notna()].copy()
    x['registrado_utc']=datetime.now(timezone.utc).isoformat()
    x['verificable_pregame']=False
    if {'tipoff_utc','quoted_at_utc'}.issubset(x):
        tipoff=pd.to_datetime(x['tipoff_utc'],utc=True,errors='coerce')
        quoted=pd.to_datetime(x['quoted_at_utc'],utc=True,errors='coerce')
        stamp=pd.to_datetime(x['registrado_utc'],utc=True)
        x['verificable_pregame']=tipoff.notna() & quoted.notna() & (quoted < tipoff) & (stamp < tipoff)
    x['resultado']='PENDIENTE';x['valor_real']=pd.NA;x['pnl_unidades']=pd.NA
    keys=['fecha','player_id','prop','linea','casa','lado','cuota_decimal']
    path=Path(target);path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        old=pd.read_csv(path,dtype={'player_id':str})
    else:
        old=pd.DataFrame(columns=x.columns)
    past=set(tuple(row) for row in old.reindex(columns=keys).itertuples(index=False,name=None))
    new=x[[tuple(row) not in past for row in x[keys].itertuples(index=False,name=None)]]
    if not new.empty:
        pd.concat([old,new],ignore_index=True).to_csv(path,index=False)
    return len(new),len(x)-len(new)


def settle_snapshot(games:pd.DataFrame,target:str='data/registro_prospectivo.csv') -> pd.DataFrame:
    path=Path(target)
    if not path.exists():
        raise ValueError('No existe registro prospectivo. Guardá un análisis antes del partido.')
    ledger=pd.read_csv(path,dtype={'player_id':str})
    games=games.copy();games['PRA']=games['PTS']+games['REB']+games['AST']
    games['fecha']=games['GAME_DATE'].dt.strftime('%Y-%m-%d')
    lookup=games.drop_duplicates(['PLAYER_ID','fecha']).set_index(['PLAYER_ID','fecha'])
    statmap={'PTS':'PTS','REB':'REB','AST':'AST','PRA':'PRA','3PM':'FG3M','FG3M':'FG3M'}
    for i,r in ledger.iterrows():
        if r['resultado']!='PENDIENTE':
            continue
        key=(str(r['player_id']),str(r['fecha']))
        if key not in lookup.index:
            continue
        realized=int(lookup.loc[key,statmap[r['prop']]])
        if realized==float(r['linea']):
            outcome='PUSH';pnl=0
        elif (realized>float(r['linea'])) == (r['lado']=='OVER'):
            outcome='WIN';pnl=float(r['cuota_decimal'])-1
        else:
            outcome='LOSS';pnl=-1
        ledger.at[i,'resultado']=outcome
        ledger.at[i,'valor_real']=realized
        ledger.at[i,'pnl_unidades']=pnl
    ledger.to_csv(path,index=False)
    return ledger
