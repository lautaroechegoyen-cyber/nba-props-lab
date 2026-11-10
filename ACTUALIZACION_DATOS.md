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
