# NBA Props Lab — Modelo estadístico experimental de NBA

Este proyecto implementa una **primera versión FUNCIONAL** para analizar mercados de puntos, rebotes, asistencias, triples y PRA. Abarca auditoría, importación de datos, simulación probabilística, cálculo de valor esperado, backtesting *walk-forward*, registro de selecciones e interfaz visual. **No se ha demostrado que tenga ventaja sobre las casas de apuestas.**

## Arranque sencillo

**Mac**: instalá Python 3.11+ desde python.org, abrí Terminal en esta carpeta y ejecutá:

```bash
bash iniciar_mac.command
```

**Windows**: con Python 3.11+ instalado, ejecutá `iniciar_windows.bat`. El navegador se abrirá en `http://localhost:8501`.

Estos lanzadores instalan las dependencias y ejecutan Streamlit. El primer modo es una **demo completamente inventada**, útil para recorrer los botones sin conectarse a internet.

## Cómo usar datos REALES

En la barra lateral seleccioná **NBA real (CSV guardado)**, tocá *Importar temporadas NBA* y esperá la respuesta. Se descargan registros de las temporadas 2025-26 y 2026-27 mediante `nba_api` (`PlayerGameLogs`, un request por temporada). Si `stats.nba.com` responde con error de red/403/bloqueo por región, la app lo informará: podés subir un CSV real alternativo. El sistema **no utiliza la demo como si fueran datos reales**.

Si tenés acceso a terminal:

```bash
python cli.py fetch --seasons 2024-25 2025-26 2026-27
python cli.py audit --games data/nba_games.csv
python cli.py predict --games data/nba_games.csv --markets data/markets_PLANTILLA_VACIA.csv
```

La **plantilla vacía de mercados** debe ser completada con cuotas reales ANTES de ejecutar la predicción. No se inventan cuotas, calendarios ni lesiones.

## Datos necesarios

### Partidos / game logs

CSV con estas columnas (en mayúsculas o minúsculas):

| Campo | Ejemplo | Función |
|---|---|---|
| `PLAYER_ID` | `203999` | ID único, no apodo |
| `PLAYER_NAME` | `Nombre Apellido` | Mostrar jugador |
| `GAME_ID` | `0022600001` | Distinguir partido |
| `GAME_DATE` | `2026-11-05` | Fecha real |
| `MIN` | `32.5` | Minutos jugados |
| `PTS`, `REB`, `AST`, `FG3M` | `22`, `9`, `5`, `2` | Estadísticas oficiales |
| `TEAM_ABBREVIATION`, `MATCHUP` | `DEN`, `DEN vs. LAL` | Contexto opcional |

`PRA` se calcula como PTS+REB+AST en el MISMO partido, no como suma de distribuciones independientes.

### Líneas y cuotas

Usá `data/markets_PLANTILLA_VACIA.csv` y completá:

| Campo | Ejemplo | Obligatorio |
|---|---|---|
| `game_date` | `2026-11-11` | Sí |
| `player_id` | `203999` | Sí, idéntico a logs |
| `stat` | `PTS` | Sí. `PTS`, `REB`, `AST`, `FG3M`, `3PM`, `PRA` |
| `line` | `22.5` | Sí |
| `odds_over`, `odds_under` | `1.90` o `+105`, `-125` | Al menos una cuota para obtener candidatos |
| `minutes_expected` | `33` | Opcional; mejor si incluye lesiones/rotaciones |
| `matchup_multiplier` | `1.00` | Opcional. Ajuste MANUAL 0.75–1.25, no calibrado |
| `bookmaker` | `CASA` | Opcional |
| `quoted_at_utc` | `2026-11-11T15:00:00Z` | Requerido para backtest |
| `tipoff_utc` | `2026-11-12T00:30:00Z` | Requerido para backtest |

Para mercados futuros, las fechas de las cuotas no son obligatorias en la primera versión; para **backtesting sí lo son** y se comprueba que `quoted_at_utc < tipoff_utc`.

**RECORDÁ:** nunca uses la cotización actual para simular que estaba disponible antes de un partido pasado. Registrá también las líneas NO elegidas cuando dispongas de ellas; de lo contrario los análisis pueden sufrir sesgo de selección.

## Cómo funciona (base estadística)

1. **Calidad**: detecta campos faltantes, ID duplicados por juego y nombres inconsistentes; bloquea duplicados y campos inválidos.
2. **Proyección simple reproducible**: usa últimos 55 partidos con al menos 5 minutos. Estima tasa de conteo por minuto; mezcla tasa reciente (10 juegos) con tasa histórica. Proyecta minutos por medianas recientes, o permite que los ingreses manualmente.
3. **Distribución**: simula minutos con dispersión estimada; tasa con una distribución gamma y conteos con Poisson (mezcla: binomial negativa). Es una APROXIMACIÓN: no modela todos los mecanismos de puntos, asistencias o triples. Devuelve media, mediana, intervalo 10.º–90.º y probabilidad de over, under y push.
4. **Valor esperado por unidad**: `EV = P(acierto)×(cuota_decimal−1) − P(pérdida)`; empate en línea entera reembolsa. `califica` si EV modelado ≥ 3% (configurable) y al menos 15 partidos observados. **Este filtro es orientativo, no una evidencia de rentabilidad.**
5. **Backtesting temporal**: cada predicción de un juego usa únicamente partidos con fecha anterior; exige el momento anterior al salto inicial para cada cotización; calcula ROI por unidad, tasa de acierto, caída máxima y Brier score del over.
6. **Registro**: exporta CSV con todas las predicciones evaluadas y un ledger con selecciones clasificadas, incluso las pérdidas.
7. **Mejora**: las tablas exportables sirven para identificar fallos persistentes. Cambios de algoritmo requieren una validación posterior con fechas que no se hayan utilizado para diseñarlos.
8. **Automatización local**: la importación desde la app, los comandos CLI y la interfaz permiten repetir el flujo. No hay un servicio en segundo plano ni conexión automática con una casa de apuestas.

### Límites importantes

- **Lesiones, quintetos, cambios de minutos, *usage*, defensa rival, ritmo y correlaciones entre jugadores NO se obtienen ni se ajustan automáticamente.** El único ajuste rival disponible es un factor MANUAL y debe usarse con cautela.
- Las probabilidades no están calibradas todavía contra una muestra real fuera de entrenamiento; pueden ser excesivamente optimistas.
- No calcula automáticamente cuotas actuales, *closing line value* ni probabilidades de combinadas; multiplicar probabilidades del mismo partido sería engañoso por la correlación.
- No incorpora comisiones, límites de apuesta ni márgenes a la distribución predictiva. La probabilidad implícita de cuota simple **incluye margen de la casa**; no se considera una probabilidad objetiva.
- Historial de menos de 8 partidos: predicción bloqueada; de 8 a 14: posible visualización con alerta, pero no `califica`.
- El generador `make_demo.py` inventa los datos **a propósito** y todos sus CSV incluyen `DEMO_SIMULADO` en el nombre. No emplear para decisiones de dinero.
- Si el proyecto se quisiera elevar a producción, habría que sumar datos de lesiones y quintetos disponibles antes de cada partido, contexto real (defensa/ritmo), *modelado jerárquico*, calibración por temporada/mercado, cotizaciones con timestamp, controles de múltiples comparaciones y pruebas prospectivas en modo papel.

## Comandos reproducibles

```bash
# Genera sólo DEMO ficticia:
python cli.py demo

# Predict DEMO:
python cli.py predict --games data/games_DEMO_SIMULADO.csv --markets data/markets_DEMO_SIMULADO.csv

# Backtest DEMO (no implica ventaja real):
python cli.py backtest --games data/games_DEMO_SIMULADO.csv --markets data/historical_markets_DEMO_SIMULADO.csv

# Tests (instalá requirements-test.txt):
python -m pytest -q
```

## Fuentes técnicas

- `nba_api` documentación de `PlayerGameLogs`: https://github.com/swar/nba_api/blob/master/src/nba_api/stats/endpoints/playergamelogs.py
- Guía de endpoints: https://github.com/swar/nba_api/blob/master/docs/nba_api/stats/endpoint_guide.md

Desarrollado para estudio, auditoría y predicción experimental. Ningún resultado asegura beneficios futuros.

## Registro prospectivo y mejora (etapas 6 y 7)

Para registrar **antes** de los encuentros las probabilidades y líneas evaluadas (incluidas las que no superan el filtro):

```bash
python cli.py track --games data/nba_games.csv --markets data/markets_actuales.csv
# Cuando los partidos hayan terminado y hayas actualizado los registros oficiales:
python cli.py settle --games data/nba_games.csv
```

El archivo `data/registro_prospectivo.csv` conserva fecha de registro, cuotas y proyecciones originales; no reescribe pronósticos previos con datos posteriores. El sistema distingue `verificable_pregame=True/False`, y **solo** considera verificable la predicción cuando conoce la hora del inicio y la cotización y el registro ocurrió antes del partido. No permite inferir retroactivamente que la cuota era válida.

El backtest también exporta `*_sesgos.csv` y `*_calibracion.csv` para estudiar errores por tipo de prop, sesgo promedio y fiabilidad de probabilidades por decil. Esos reportes sugieren qué revisar, **pero no ajustan automáticamente los parámetros** para no contaminar la evaluación.

## Diez posibles variables predictivas (plan de mejora)

| Variable | Estado en v1 | Cuidado temporal |
|---|---|---|
| Minutos recientes | Sí | Solo anteriores al partido |
| Media de puntos/rebotes/asistencias por minuto | Sí | Solo anteriores |
| Tendencia últimos 10 juegos | Sí | Solo anteriores |
| Variabilidad de minutos | Sí | Solo anteriores |
| Varianza de resultados / sobredispersión | Sí | Solo anteriores |
| Composición de quinteto y lesiones | No; actualizar minutos manualmente | Deben conocerse antes del salto inicial |
| Ritmo del rival | No | Usar posesiones calculadas hasta día anterior |
| Defensa rival por tipo de acción | No | Evitar promedios que incluyan el juego a predecir |
| Cambios de uso/tasa con ausencias | No | Usar disponibilidad confirmada antes del partido |
| Localía, descanso y *back-to-back* | No | Solo calendario conocido ex ante |

Estas variables no se incorporan automáticamente porque una variable sin datos fiables puede empeorar el modelo. Se aconseja compararlas en validaciones cronológicas de temporada a temporada antes de incorporarlas. El Brier score de backtesting incluye ahora una comparación contra una línea base ingenua: la frecuencia observada de over en los últimos diez juegos, suavizada con pseudoconteos.

Si ejecutaste el lanzador y querés usar los comandos de consola, en Mac utilizá `.venv/bin/python cli.py ...` y en Windows `.venv\\Scripts\\python.exe cli.py ...`.
