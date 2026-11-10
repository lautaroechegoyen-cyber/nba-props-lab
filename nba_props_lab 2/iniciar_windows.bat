@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv || (echo No se pudo crear el entorno virtual. & pause & exit /b 1)
)
.venv\Scripts\python.exe -m pip install -r requirements.txt || (echo Instalacion fallida. & pause & exit /b 1)
.venv\Scripts\python.exe -m streamlit run app.py
pause
