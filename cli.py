"""Terminal interface for downloads, projections, walk-forward tests, and auditing."""
from pathlib import Path
import argparse
import json
import pandas as pd
from model import normalize_games,normalize_markets,predict_markets,backtest,audit_games
from make_demo import generate_demo
from tracker import append_snapshot,settle_snapshot
from diagnostics import analyze
from fetch_nba import current_seasons


def main():
    parser=argparse.ArgumentParser(description='NBA Props Lab – proyecciones experimentales')
    sub=parser.add_subparsers(dest='cmd',required=True)
    x=sub.add_parser('fetch',help='Descargar game logs NBA reales')
    x.add_argument('--seasons',nargs='+',default=None, help='Ej. 2022-23 2023-24; por defecto actual y anterior')
    x.add_argument('--output',default='nba_games.csv', help='CSV compartido en la raíz de GitHub')
    sub.add_parser('demo',help='Crear datos FICTICIOS para probar')
    x=sub.add_parser('audit'); x.add_argument('--games',required=True)
    for command in ['predict','backtest','track','settle']:
        x=sub.add_parser(command)
        x.add_argument('--games',required=True)
        if command!='settle': x.add_argument('--markets',required=True)
        x.add_argument('--min-ev',type=float,default=.03)
        x.add_argument('--output',default=('data/registro_prospectivo.csv' if command in ['track','settle'] else 'data/'+command+'_resultado.csv'))
    args=parser.parse_args()
    if args.cmd=='demo':
        generate_demo();print('Datos demo generados en data/. ATENCIÓN: sintéticos, no NBA real.');return
    if args.cmd=='fetch':
        from fetch_nba import fetch_seasons
        games,logs=fetch_seasons(args.seasons or current_seasons(),args.output)
        print('\n'.join(logs)); print(f'Archivo: {args.output} | filas: {len(games)}');return
    raw=pd.read_csv(args.games,dtype={'PLAYER_ID':str,'GAME_ID':str})
    if args.cmd=='audit':
        print(audit_games(raw).to_string(index=False));return
    games=normalize_games(raw)
    if args.cmd=='settle':
        settled=settle_snapshot(games,args.output)
        print('Total filas:',len(settled),'| resueltas:',int((settled.resultado!='PENDIENTE').sum()))
        return
    markets=normalize_markets(pd.read_csv(args.markets,dtype={'player_id':str}))
    out=Path(args.output);out.parent.mkdir(exist_ok=True,parents=True)
    if args.cmd in ['predict','track']:
        pred=predict_markets(games,markets,min_ev=args.min_ev)
        if args.cmd=='track':
            n,duplicates=append_snapshot(pred,args.output)
            print(f'Pronósticos guardados {n}, duplicados evitados {duplicates}')
            return
        pred.to_csv(out,index=False)
        print(pred[['jugador','prop','linea','lado','proyeccion','probabilidad','ev_unidad','califica']].to_string(index=False) if not pred.empty else 'Sin proyecciones')
    else:
        bets,all_preds,summary=backtest(games,markets,min_ev=args.min_ev)
        bets.to_csv(out,index=False)
        all_preds.to_csv(out.with_name(out.stem+'_todas_las_cuotas.csv'),index=False)
        print(json.dumps(summary,ensure_ascii=False,indent=2))
        bias,cal=analyze(all_preds)
        if not bias.empty: bias.to_csv(out.with_name(out.stem+'_sesgos.csv'),index=False)
        if not cal.empty: cal.to_csv(out.with_name(out.stem+'_calibracion.csv'),index=False)
    print('Archivo guardado:',out)

if __name__ == '__main__':main()
