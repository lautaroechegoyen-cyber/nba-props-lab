# NBA Props Lab — actualización de estadísticas compartidas

La aplicación publicada lee `nba_games.csv` de la **raíz de GitHub**.
Todos los visitantes ven la misma base sin pedir estadísticas a stats.nba.com.
Para compatibilidad, si ese CSV no existe se admite `data/nba_games.csv`.

## Actualizar desde GitHub

GitHub → Actions → **Actualizar estadísticas NBA** → **Run workflow**.
También se intenta diariamente a las 13:15 UTC (10:15 de Argentina).
El workflow une por PLAYER_ID + GAME_ID, conserva la historia y hace commit
solo si hay diferencias. Ante un timeout, mantiene la última base válida.
**Las consultas a NBA Stats desde GitHub pueden ser bloqueadas:** en ese caso
la tarea falla, pero la aplicación sigue leyendo el CSV anterior.

## Agregar temporadas históricas

En una Mac o PC con acceso a NBA Stats:

```bash
python -m pip install -r requirements.txt
python cli.py fetch --seasons 2022-23 2023-24 2024-25 2025-26 2026-27 --output nba_games.csv
python cli.py audit --games nba_games.csv
```

Luego subí el archivo actualizado a la raíz de GitHub. La app no necesita
actualizarse por sesión. Las cuotas se siguen ingresando manualmente.

## Verificar

Usá Python 3.12 y ejecutá:

```bash
python -m pip install -r requirements-test.txt
python -m pytest -q
python -m streamlit run app.py
```

Streamlit Community Cloud debe apuntar a la rama main, archivo app.py.
Al integrar cambios en main, Cloud vuelve a desplegar desde GitHub.

**Limitaciones:** la base histórica se publica en un repositorio público y
puede estar desactualizada; los CSV de pronósticos escritos en el disco
temporal de Streamlit Cloud no son un registro multiusuario persistente.
No se incluyen lesiones/rotaciones en tiempo real ni cuotas automáticas.
Las probabilidades son experimentales; no hay rentabilidad demostrada.

## Integración de props y cuotas — The Odds API

Se incorporó el backend recibido como un adaptador Python (`odds_integration.py`) y una
pestaña **Cuotas NBA automáticas**. En Streamlit Community Cloud no es necesario
levantar otro servidor Node.js ni consultar `stats.nba.com` por visitante.

1. En Streamlit Cloud abrí la aplicación → Settings → Secrets.
2. Agregá la clave del proveedor de forma privada, por ejemplo:

    ODDS_API_KEY = "tu_clave_real"

3. Reiniciá la app y seleccioná **NBA real (CSV compartido)**.
4. Abrí **Cuotas NBA automáticas**, elegí casa, mercado y cantidad de partidos.
5. Apretá **Consultar cuotas disponibles**. Podés filtrar jugadores,
   últimos 5/10/15/25 partidos, local/visitante, Más/Menos y porcentaje histórico.

**Seguridad:** nunca subas `.env`, la clave o archivos `.cache-*.json` al
repositorio. El ZIP original contenía `.env`: si compartiste la clave con otras
personas, regenerala desde el proveedor. Las peticiones se hacen desde
Python y no desde el navegador del visitante. No se registra la clave en los
mensajes de error. Si la clave no está configurada, todas las funciones
manuales siguen disponibles.

**Créditos y disponibilidad:** la API externa puede cobrar créditos por
mercado y evento, aunque no devuelva ninguna línea. Limitamos a 1/3/6 eventos,
seleccionamos un mercado por consulta y reutilizamos la respuesta 15 minutos
entre sesiones. La cobertura depende del bookmaker y el plan; no se garantiza
que Stake figure como casa soportada. Los porcentajes históricos descriptivos
no sustituyen un modelo predictivo ni implican rentabilidad.
