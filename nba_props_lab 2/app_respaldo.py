"""Streamlit UI for personal research; all recommendations are experimental."""
from pathlib import Path
import io
import json
from datetime import date, timedelta
import pandas as pd
import streamlit as st
from model import (normalize_games, normalize_markets, audit_games,
                   predict_markets,backtest,forecast_player,evaluate_line)
from fetch_nba import fetch_seasons
from make_demo import generate_demo
from diagnostics import analyze
from tracker import append_snapshot,settle_snapshot

st.set_page_config(page_title='NBA Props Lab',page_icon='🏀',layout='wide')
st.title('🏀 NBA Props Lab')
st.caption('Laboratorio experimental de probabilidades, valor esperado y backtesting. No es un sistema de ganancias garantizadas.')

root=Path(__file__).resolve().parent
folder=root/'data'
if not (folder/'games_DEMO_SIMULADO.csv').exists():
    generate_demo(folder)

with st.sidebar:
    st.header('Configuración')
    source=st.radio('Origen de los datos',('Demo ficticia','NBA real (CSV guardado)','Subir CSV propio'),index=1 if (folder/'nba_games.csv').exists() else 0)
    ev_pct=st.slider('EV mínimo para marcar selección (%)',0,20,3)
    sims=st.select_slider('Simulaciones por jugador',options=[3000,6000,12000,25000],value=12000)
    st.write('El riesgo por apuesta del backtest es 1 unidad constante.')

upload=None
if source=='Demo ficticia':
    path=folder/'games_DEMO_SIMULADO.csv'
    raw=pd.read_csv(path,dtype={'PLAYER_ID':str,'GAME_ID':str})
    st.warning('MODO DEMO: TODOS los nombres, partidos, cuotas y resultados son INVENTADOS. No sirven para apostar.')
elif source=='NBA real (CSV guardado)':
    path=folder/'nba_games.csv'
    if st.button('Importar temporadas NBA desde stats.nba.com'):
        with st.spinner('Consultando NBA Stats...'):
            try:
                _,logs=fetch_seasons(['2025-26','2026-27'],str(path))
                st.success('Descarga finalizada')
                st.write('\n'.join(logs))
            except Exception as e:
                st.error(f'No se pudo importar automáticamente: {e}. Podés usar un CSV.')
    if not path.exists():
        st.info('Aún no hay NBA real descargada. Usá el botón de importación o subí un CSV.');st.stop()
    raw=pd.read_csv(path,dtype={'PLAYER_ID':str,'GAME_ID':str})
else:
    upload=st.file_uploader('Subir CSV de partidos',type='csv',key='games')
    if upload is None:
        st.info('Adjuntá un CSV de estadísticas NBA con las columnas del README.');st.stop()
    raw=pd.read_csv(upload,dtype={'PLAYER_ID':str,'GAME_ID':str})

with st.expander('Revisión de calidad de los datos'):
    st.dataframe(audit_games(raw),hide_index=True,use_container_width=True)
try:
    games=normalize_games(raw)
except ValueError as exc:
    st.error(f'Datos históricos inválidos: {exc}');st.stop()

c1,c2,c3=st.columns(3)
c1.metric('Registros históricos',f'{len(games):,}')
c2.metric('Jugadores',games['PLAYER_ID'].nunique())
c3.metric('Última fecha de datos',str(games['GAME_DATE'].max().date()))

st.divider()
tab_simple,tab_pred,tab_test,tab_help=st.tabs(['🏀 Analizar jugador (fácil)','Proyecciones por CSV','Backtesting cronológico','Instrucciones'])

with tab_manual:
    st.subheader('Analizá una línea sin preparar archivos')
    if source=='Demo ficticia':
        st.warning('La fuente está en DEMO. Los jugadores y partidos son inventados. Para jugadores reales, elegí «NBA real (CSV guardado)» en la barra lateral.')
    else:
        st.info('Se usan los partidos descargados en esta computadora. Las cuotas y líneas las ingresás vos: no se descargan de Stake ni de otra casa.')

    latest = games.sort_values('GAME_DATE').drop_duplicates('PLAYER_ID',keep='last')
    players = {str(r.PLAYER_ID): (str(r.PLAYER_NAME),str(r.TEAM_ABBREVIATION)) for _,r in latest.iterrows()}
    ids = sorted(players,key=lambda pid:(players[pid][0].casefold(),pid))
    def show_player(pid):
        name,team=players[pid]
        return f'{name} ({team}) · ID {pid}' if team and team!='nan' else f'{name} · ID {pid}'
    player_id=st.selectbox('Jugador',ids,format_func=show_player,
                           help='Elegí por nombre. El ID evita confusiones entre jugadores con nombres parecidos.')
    stat_names={'PTS':'Puntos','REB':'Rebotes','AST':'Asistencias','FG3M':'Triples convertidos','PRA':'Puntos + rebotes + asistencias'}
    a,b,c=st.columns([1.3,1.2,1])
    with a:
        game_date=st.date_input('Fecha del próximo partido',value=pd.Timestamp.today().date(),
                                help='El modelo solo usa partidos anteriores a esta fecha.')
    with b:
        stat=st.selectbox('Estadística',list(stat_names),format_func=lambda k:stat_names[k])
    with c:
        line=st.number_input('Línea que ofrece la casa',min_value=0.,max_value=200.,value=19.5,step=0.5,format='%.1f')

    history=games[(games['PLAYER_ID'].astype(str)==str(player_id)) &
                  (games['GAME_DATE']<pd.Timestamp(game_date)) & (games['MIN']>=5)].sort_values(['GAME_DATE','GAME_ID'])
    last10=history.tail(10).copy()
    if not last10.empty:
        last10['PRA']=last10['PTS']+last10['REB']+last10['AST']
        values=last10[stat]
        st.caption(f'Últimos {len(last10)} partidos anteriores a {game_date}: media {values.mean():.1f}; '
                   f'Over {line:g} en {int((values>line).sum())}/{len(last10)} y '
                   f'Under en {int((values<line).sum())}/{len(last10)}. '
                   'El porcentaje histórico no es la probabilidad del modelo.')
        display_cols=['GAME_DATE','MATCHUP','MIN','PTS','REB','AST','FG3M','PRA']
        available_cols=[col for col in display_cols if col in last10.columns]
        hist_display=last10[available_cols].sort_values('GAME_DATE',ascending=False).copy()
        hist_display['GAME_DATE']=hist_display['GAME_DATE'].dt.strftime('%d/%m/%Y')
        with st.expander('Ver últimos partidos del jugador',expanded=True):
            st.dataframe(hist_display,hide_index=True,use_container_width=True)
    else:
        st.warning('No se encontraron partidos anteriores a esa fecha para el jugador seleccionado.')

    with st.form('manual_prop_form'):
        st.markdown('**Copiá las cuotas de tu casa de apuestas** (decimal como `1.85` o americana como `+110` / `-125`).')
        odd_a,odd_b=st.columns(2)
        with odd_a:
            odds_over=st.text_input('Cuota MÁS de (Over)',value='',placeholder='Ejemplo: 1.90')
        with odd_b:
            odds_under=st.text_input('Cuota MENOS de (Under)',value='',placeholder='Ejemplo: 1.90')
        minutes_manual=st.checkbox('Sé cuántos minutos se espera que juegue (ajuste manual)',value=False)
        minutes_val=st.number_input('Minutos estimados',min_value=1.,max_value=48.,value=30.,step=1.,
                                    disabled=not minutes_manual,help='Si no lo indicás, se estiman según sus partidos recientes.')
        st.caption('No se ajusta automáticamente por lesiones, rival o quintetos. Comprobá todo esto antes de interpretar la predicción.')
        submitted=st.form_submit_button('Calcular proyección y probabilidades',type='primary',use_container_width=True)
    if submitted:
        try:
            from model import forecast_player,evaluate_line
            f=forecast_player(games,player_id,pd.Timestamp(game_date),stat,
                minutes_expected=float(minutes_val) if minutes_manual else None,
                simulations=sims)
            p_over=float((f.sims>line).mean());p_under=float((f.sims<line).mean());p_push=float((f.sims==line).mean())
            st.subheader(f'Resultado experimental · {players[player_id][0]}')
            k1,k2,k3,k4=st.columns(4)
            k1.metric('Proyección media',f'{f.mean:.1f}')
            k2.metric('Probabilidad Over',f'{p_over:.1%}')
            k3.metric('Probabilidad Under',f'{p_under:.1%}')
            k4.metric('Minutos previstos',f'{f.minutes_mean:.1f}')
            st.caption(f'Mediana: {f.median:.0f} · Intervalo central 80%: {f.low80:.0f} a {f.high80:.0f} · '
                       f'Probabilidad de devolución exacta: {p_push:.1%} · '
                       f'{f.history_games} partidos de historial · Último partido usado: {f.last_game_date}.')
            bets=evaluate_line(f,line,odds_over.strip() or None,odds_under.strip() or None)
            if bets:
                rows=[{'Lado':x['lado'],'Cuota':round(x['cuota_decimal'],3),
                    'Probabilidad estimada':f"{x['probabilidad']:.1%}",
                    'Prob. mínima de equilibrio':f"{x['prob_equilibrio']:.1%}",
                    'Valor esperado / 1 unidad':f"{x['ev_unidad']:+.1%}"} for x in bets]
                st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
                st.caption('El valor esperado solo es útil si la probabilidad del modelo está bien calibrada. '
                           'Positivo no equivale a apuesta segura ni garantiza ganancias.')
            else:
                st.info('Para comparar valor esperado, ingresá al menos una cuota (Over o Under) y volvé a calcular.')
            if f.caution: st.warning('Precauciones: '+f.caution)
            if (pd.Timestamp.today().normalize()-games['GAME_DATE'].max()).days>=3:
                st.warning('Los datos pueden estar desactualizados. Importá nuevamente las temporadas antes de usar partidos recientes.')
        except Exception as exc:
            st.error(f'No se pudo calcular esta selección: {exc}')

def get_markets(defaultfile,key):
    if defaultfile:
        st.caption('El archivo elegido es DEMO y está marcado como ficticio.')
    uploader=st.file_uploader('Subir CSV de cuotas y líneas (opcional)',type='csv',key=key)
    if uploader is not None:
        return normalize_markets(pd.read_csv(uploader,dtype={'player_id':str}))
    if defaultfile:
        return normalize_markets(pd.read_csv(defaultfile,dtype={'player_id':str}))
    return None

with tab_simple:
    if source == 'Demo ficticia':
        st.warning('Modo DEMO: jugadores y resultados simulados. Elegí NBA real en la barra lateral para datos oficiales.')
    st.subheader('Seleccioná un jugador y cargá la línea de la apuesta')
    st.caption('Estadísticas históricas: cargadas. Cuotas: las escribís vos desde tu casa de apuestas. No se importan automáticamente.')
    latest = games.sort_values('GAME_DATE').drop_duplicates('PLAYER_ID', keep='last')
    latest = latest.sort_values('PLAYER_NAME')
    choices = {f'{r.PLAYER_NAME} · {r.TEAM_ABBREVIATION} · ID {r.PLAYER_ID}':str(r.PLAYER_ID) for r in latest.itertuples()}
    chosen = st.selectbox('Jugador',list(choices.keys()),index=None,placeholder='Escribí el nombre del jugador...')
    if chosen:
        pid=choices[chosen]
        history=games[games['PLAYER_ID'].astype(str)==pid].sort_values('GAME_DATE',ascending=False).copy()
        history['PRA']=history['PTS']+history['REB']+history['AST']
        st.write('**Últimos 10 partidos registrados**')
        cols=['GAME_DATE','MATCHUP','MIN','PTS','REB','AST','FG3M','PRA']
        preview=history[cols].head(10).copy()
        preview['GAME_DATE']=preview['GAME_DATE'].dt.strftime('%Y-%m-%d')
        st.dataframe(preview,hide_index=True,use_container_width=True)
        c1,c2,c3,c4=st.columns(4)
        for col,widget,label in zip(['PTS','REB','AST','FG3M'],[c1,c2,c3,c4],['Puntos','Rebotes','Asistencias','Triples']):
            widget.metric('Media últimos 10: '+label,f'{history[col].head(10).mean():.1f}')
        st.divider()
        with st.form('form_prop_manual'):
            a,b,c=st.columns(3)
            with a:
                target=st.date_input('Fecha del partido a proyectar',value=max(date.today(),games['GAME_DATE'].max().date()+timedelta(days=1)))
                stat=st.selectbox('Estadística',['PTS','REB','AST','3PM','PRA'],format_func=lambda x:{'PTS':'Puntos','REB':'Rebotes','AST':'Asistencias','3PM':'Triples anotados','PRA':'Puntos + rebotes + asistencias'}[x])
            with b:
                line=st.number_input('Línea de la casa (ej. 19.5)',min_value=0.0,value=19.5,step=0.5)
                bookmaker=st.text_input('Casa de apuestas (opcional)',placeholder='Ej. Stake')
            with c:
                odds_o=st.text_input('Cuota MÁS (opcional)',placeholder='Ej. 1.90')
                odds_u=st.text_input('Cuota MENOS (opcional)',placeholder='Ej. 1.85')
            manual_minutes=st.checkbox('Quiero indicar los minutos esperados (si conozco rotación/lesiones)')
            minute_val=st.number_input('Minutos esperados',min_value=1.,max_value=48.,value=30.,step=1.) if manual_minutes else None
            submitted=st.form_submit_button('📊 Calcular proyección',type='primary')
        if submitted:
            if target <= games['GAME_DATE'].max().date():
                st.warning('La fecha elegida tiene partidos registrados: el modelo usará únicamente registros anteriores a esa fecha. Para apuestas futuras seleccioná la fecha correcta.')
            try:
                f=forecast_player(games,pid,target,stat,minutes_expected=minute_val,simulations=sims)
                vals=evaluate_line(f,float(line),odds_o.strip() or None,odds_u.strip() or None)
                st.subheader('Resultado experimental')
                x,y,z=st.columns(3)
                x.metric('Proyección media',f'{f.mean:.1f}')
                y.metric('Mediana',f'{f.median:.0f}')
                z.metric('Minutos proyectados',f'{f.minutes_mean:.1f}')
                p_more=float((f.sims > line).mean());p_less=float((f.sims < line).mean());p_equal=float((f.sims == line).mean())
                x,y,z=st.columns(3)
                x.metric('Probabilidad MÁS',f'{100*p_more:.1f}%')
                y.metric('Probabilidad MENOS',f'{100*p_less:.1f}%')
                z.metric('Empate / devolución',f'{100*p_equal:.1f}%')
                st.caption(f'80% central simulado: {f.low80:.0f} a {f.high80:.0f} | {f.history_games} partidos de historial | Último: {f.last_game_date}')
                if vals:
                    st.write('**Valor esperado según las cuotas cargadas**')
                    summary=pd.DataFrame(vals)
                    summary['valor_esperado_%']=summary['ev_unidad']*100
                    st.dataframe(summary[['lado','probabilidad','cuota_decimal','ventaja_pp','valor_esperado_%']],hide_index=True,use_container_width=True)
                    st.caption('Un EV positivo NO demuestra que exista ventaja real: el modelo todavía no está validado con cuotas históricas.')
                else:
                    st.info('No escribiste cuotas: se muestran probabilidades y proyección. Podés poner las cuotas arriba y calcular otra vez.')
                if f.caution:
                    st.warning('Advertencias: '+f.caution)
                st.caption('No incluye automáticamente lesiones del día, anuncios de quintetos ni defensa rival. Revisá la fecha y la disponibilidad del jugador.')
            except Exception as e:
                st.error(f'No se pudo proyectar: {e}')
    else:
        st.info('Empezá escribiendo un jugador en el selector de arriba.')

with tab_pred:
    demo_path=folder/'markets_DEMO_SIMULADO.csv' if source=='Demo ficticia' else None
    try:
        m=get_markets(demo_path,'markets_predict')
        if m is None:
            st.info('Cargá un CSV de líneas actuales. No se inventarán cuotas ni partidos.')
        else:
            pred=predict_markets(games,m,ev_pct/100,sims)
            good=pred.loc[pred.get('califica',pd.Series(dtype=bool))==True] if not pred.empty else pd.DataFrame()
            st.caption(f'Filas analizadas: {len(pred)} | candidatos que superan umbral/modelo: {len(good)}. La calificación NO es garantía de ventaja real.')
            if not pred.empty:
                st.dataframe(pred,hide_index=True,use_container_width=True)
                if source!='Demo ficticia':
                    if st.button('Guardar pronósticos en registro prospectivo'):
                        n,dupes=append_snapshot(pred,str(folder/'registro_prospectivo.csv'))
                        st.success(f'{n} pronósticos nuevos registrados; {dupes} duplicados no reescritos.')
                st.download_button('Descargar proyecciones CSV',pred.to_csv(index=False).encode('utf-8-sig'),
                                   'nba_props_proyecciones.csv','text/csv')
            if not good.empty:
                st.subheader('Candidatos experimentales según EV estimado')
                st.dataframe(good[['jugador','prop','linea','lado','probabilidad','cuota_decimal','ev_unidad','alertas']],
                             hide_index=True,use_container_width=True)
    except Exception as e:
        st.error(f'No se pudo evaluar líneas: {e}')

with tab_test:
    st.write('Se aceptan únicamente cuotas históricas con **quoted_at_utc anterior a tipoff_utc**. Los resultados se toman del CSV de partidos. El modelo usa solo partidos anteriores a cada fecha.')
    demo_path=folder/'historical_markets_DEMO_SIMULADO.csv' if source=='Demo ficticia' else None
    try:
        m=get_markets(demo_path,'markets_backtest')
        if m is None:
            st.info('Necesitás un historial real de cuotas prepartido; los resultados pasados por sí solos no permiten evaluar rentabilidad.')
        elif st.button('Ejecutar backtest',type='primary'):
            with st.spinner('Calculando predicciones cronológicas...'):
                bets,all_preds,summary=backtest(games,m,ev_pct/100,3500)
            st.subheader('Métricas — '+('DEMO FICTICIA' if source=='Demo ficticia' else 'Datos aportados'))
            st.json(summary)
            if len(bets):
                st.line_chart(bets.set_index('fecha')['ganancia_acumulada'])
                st.dataframe(bets,hide_index=True,use_container_width=True)
                st.download_button('Descargar registro de apuestas (CSV)',bets.to_csv(index=False).encode('utf-8-sig'),
                                  'registro_backtest.csv','text/csv')
            if len(all_preds):
                st.download_button('Descargar todas las predicciones (CSV)',all_preds.to_csv(index=False).encode('utf-8-sig'),
                                  'predicciones_historicas.csv','text/csv')
            bias,calibration=analyze(all_preds)
            if not bias.empty:
                st.subheader('Diagnóstico de errores por mercado')
                st.dataframe(bias,hide_index=True,use_container_width=True)
            if not calibration.empty:
                st.subheader('Calibración de probabilidades (deciles)')
                st.dataframe(calibration,hide_index=True,use_container_width=True)
            st.info('El backtest no incluye comisiones, cambios posteriores de cuota, límites de apuestas ni corrección por múltiples pruebas. No valida automáticamente el modelo.')
    except Exception as e:
        st.error(f'Backtest no disponible: {e}')

with tab_help:
    st.markdown('''
    **Uso fácil:** en la pestaña **Analizar jugador (fácil)**, elegí jugador, fecha, mercado, línea y escribí la(s) cuota(s). No hace falta preparar CSV para una sola prop.

    **Paso 1:** Importá estadísticas reales o subí un CSV de game logs de NBA.

    **Paso 2:** Prepará una tabla de líneas con `game_date, player_id, stat, line, odds_over, odds_under`.
    La `stat` admite `PTS`, `REB`, `AST`, `3PM`, `FG3M` y `PRA`. Podés añadir `minutes_expected`,
    `matchup_multiplier` (1 por defecto) y `bookmaker`.

    **Paso 3:** Revisá el resultado: `probabilidad` es una estimación experimental,
    `ev_unidad` es el valor esperado teórico por unidad, y `califica` aplica un filtro simple.

    **Registro prospectivo:** desde Proyecciones, guardá pronósticos con marca de tiempo. Para verificar que fueron previos al partido, cargá además `quoted_at_utc` y `tipoff_utc`. Las filas sin esos campos se marcan como no verificables.

    **Paso 4:** Para medir ganancias retrospectivas necesitás cuotas históricas **registradas antes del partido**,
    y `quoted_at_utc` / `tipoff_utc`. No vale copiar cuotas actuales a resultados pasados.

    **Importante:** sin registro de lesiones, cambios de quinteto, rival y cuotas actualizadas,
    los minutos automáticos pueden ser poco fiables. El modelo es una línea de base, no un pronóstico profesional validado.
    ''')
