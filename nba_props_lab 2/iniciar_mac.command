#!/bin/bash
cd "$(dirname "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
  echo "Instalá Python 3.11 o superior desde python.org"; read -r; exit 1
fi
if [ ! -f .venv/bin/python ]; then
  python3 -m venv .venv || { echo "No se pudo crear el entorno virtual"; read -r; exit 1; }
fi
.venv/bin/python -m pip install -r requirements.txt || { echo "Error de instalación"; read -r; exit 1; }
.venv/bin/python -m streamlit run app.py
