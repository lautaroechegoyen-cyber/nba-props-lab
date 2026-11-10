"""Streamlit UI for personal research; all recommendations are experimental."""
from pathlib import Path
import io
import json
from datetime import date, timedelta
import pandas as pd
import streamlit as st
from model import (normalize_games, normalize_markets, audit_games,
                   predict_markets,backtest,forecast_player,evaluate_line)
from shared_data import shared_path
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
    shared_csv = shared_path(root)
    source=st.radio('Origen de los datos',('Demo ficticia','NBA real (CSV compartido)','Subir CSV propio'),index=1 if shared_csv.exists() else 0)
    ev_pct=st.slider('EV mínimo para marcar selección (%)',0,20,3)
    sims=st.select_slider('Simulaciones por jugador',options=[3000,6000,12000,25000],value=12000)
    st.write('El riesgo por apuesta del backtest es 1 unidad constante.')

upload=None
if source=='Demo ficticia':
    path=folder/'games_DEMO_SIMULADO.csv'
    raw=pd.read_csv(path,dtype={'PLAYER_ID':str,'GAME_ID':str})
    st.warning('MODO DEMO: TODOS los nombres, partidos, cuotas y resultados son INVENTADOS. No sirven para apostar.')
elif source=='NBA real (CSV compartido)':
    path=shared_csv
    if not path.exists():
        st.error('No se encuentra nba_games.csv en GitHub. El administrador debe actualizar la base compartida.')
        st.stop()
    try:
        raw=pd.read_csv(path,dtype={'PLAYER_ID':str,'GAME_ID':str})
    except (OSError, pd.errors.ParserError) as exc:
        st.error(f'No se pudo leer la base compartida: {exc}')
        st.stop()
    st.caption('Base compartida: se carga del CSV publicado con la app. No requiere conexión a stats.nba.com.')
else:
    upload=st.file_uploader('Subir CSV de partidos',type='csv',key='games')
    if upload is None:
        st.info('Adjuntá un CSV de estadísticas NBA con las columnas del README.');st.stop()
    raw=pd.read_csv(upload,dtype={'PLAYER_ID':str,'GAME_ID':str})

with st.expander('Revisión de calidad de los datos'):
    st.dataframe(audit_games(raw),hide_index=True,width='stretch')
try:
    games=normalize_games(raw)
except ValueError as exc:
    st.error(f'Datos históricos inválidos: {exc}');st.stop()

c1,c2,c3=st.columns(3)
c1.metric('Registros históricos',f'{len(games):,}')
c2.metric('Jugadores',games['PLAYER_ID'].nunique())
c3.metric('Última fecha de datos',str(games['GAME_DATE'].max().date()))
if source == 'NBA real (CSV compartido)':
    age = (date.today() - games['GAME_DATE'].max().date()).days
    if age > 3:
        st.warning(f'La base compartida está desactualizada ({age} días). '
                   'El administrador debe ejecutar el actualizador de GitHub Actions. '
                   'No se descarga información al abrir la app.')
    with st.expander('Cómo se actualiza la base compartida'):
        st.write('Los datos se actualizan desde GitHub Actions (automáticamente, o con Run workflow). '
                 'El administrador puede importar temporadas anteriores con '
                 '`python cli.py fetch --seasons 2022-23 2023-24 2024-25 2025-26 2026-27`. '
                 'La API puede bloquear las solicitudes: una actualización fallida mantiene la base anterior.')

st.divider()
tab_simple,tab_pred,tab_test,tab_help=st.tabs(['🏀 Analizar jugador (fácil)','Proyecciones por CSV','Backtesting cronológico','Instrucciones'])

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
        st.dataframe(preview,hide_index=True,width='stretch')
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
                    st.dataframe(summary[['lado','probabilidad','cuota_decimal','ventaja_pp','valor_esperado_%']],hide_index=True,width='stretch')
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
                st.dataframe(pred,hide_index=True,width='stretch')
                if source!='Demo ficticia':
                    if st.button('Guardar pronósticos en registro prospectivo'):
                        n,dupes=append_snapshot(pred,str(folder/'registro_prospectivo.csv'))
                        st.success(f'{n} pronósticos nuevos registrados; {dupes} duplicados no reescritos.')
                st.download_button('Descargar proyecciones CSV',pred.to_csv(index=False).encode('utf-8-sig'),
                                   'nba_props_proyecciones.csv','text/csv')
            if not good.empty:
                st.subheader('Candidatos experimentales según EV estimado')
                st.dataframe(good[['jugador','prop','linea','lado','probabilidad','cuota_decimal','ev_unidad','alertas']],
                             hide_index=True,width='stretch')
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
                st.dataframe(bets,hide_index=True,width='stretch')
                st.download_button('Descargar registro de apuestas (CSV)',bets.to_csv(index=False).encode('utf-8-sig'),
                                  'registro_backtest.csv','text/csv')
            if len(all_preds):
                st.download_button('Descargar todas las predicciones (CSV)',all_preds.to_csv(index=False).encode('utf-8-sig'),
                                  'predicciones_historicas.csv','text/csv')
            bias,calibration=analyze(all_preds)
            if not bias.empty:
                st.subheader('Diagnóstico de errores por mercado')
                st.dataframe(bias,hide_index=True,width='stretch')
            if not calibration.empty:
                st.subheader('Calibración de probabilidades (deciles)')
                st.dataframe(calibration,hide_index=True,width='stretch')
            st.info('El backtest no incluye comisiones, cambios posteriores de cuota, límites de apuestas ni corrección por múltiples pruebas. No valida automáticamente el modelo.')
    except Exception as e:
        st.error(f'Backtest no disponible: {e}')

with tab_help:
    st.markdown('''
    **Uso fácil:** en la pestaña **Analizar jugador (fácil)**, elegí jugador, fecha, mercado, línea y escribí la(s) cuota(s). No hace falta preparar CSV para una sola prop.

    **Paso 1:** La base NBA real es compartida en GitHub; también podés subir un CSV propio.

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
