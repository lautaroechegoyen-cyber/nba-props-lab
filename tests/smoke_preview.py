"""Comprueba la preview desplegada (sin credenciales ni modificaciones)."""
import os
import re
import time
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = os.getenv("PREVIEW_URL", "https://nba-props-lab-preview.streamlit.app").rstrip("/")
SCREENSHOT = Path("preview-smoke.png")

def health():
    errors = []
    for attempt in range(5):
        try:
            req = urllib.request.Request(BASE + "/_stcore/health", headers={"User-Agent": "NBA-Props-Lab-CI/1.0"})
            with urllib.request.urlopen(req, timeout=30) as res:
                body = res.read(100).decode("utf-8", errors="ignore").strip().lower()
                print(f"Health status={res.status} body={body!r}", flush=True)
                if res.status == 200 and body == "ok":
                    return
                errors.append(f"HTTP {res.status} {body}")
        except Exception as exc:
            errors.append(str(exc))
        time.sleep(8)
    print("Health no verificable: " + repr(errors) + ". Intentando abrir la app con navegador.", flush=True)

def main():
    health()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 960})
        try:
            page.goto(BASE, wait_until="domcontentloaded", timeout=120000)
            print(f"URL final del navegador: {page.url}", flush=True)
            page.get_by_text("NBA Props Lab", exact=False).first.wait_for(state="visible", timeout=120000)
            page.get_by_text("Registros históricos").first.wait_for(state="visible", timeout=90000)
            page.get_by_text("Base compartida:", exact=False).first.wait_for(state="visible", timeout=60000)
            metrics = page.locator('[data-testid="stMetric"]')
            metrics.first.wait_for(state="visible", timeout=60000)
            value = metrics.first.locator('[data-testid="stMetricValue"]').inner_text()
            count = int(re.sub(r"\D", "", value))
            print(f"Registros históricos visibles: {count}", flush=True)
            assert count > 1000, f"Base NBA insuficiente: {count}"
            page.get_by_text("Analizar jugador (fácil)", exact=False).first.wait_for(state="visible", timeout=30000)
            errors = page.locator('[data-testid="stException"]')
            assert errors.count() == 0, f"Streamlit mostró una excepción: {errors.all_inner_texts()}"
            print("PREVIEW OK: se abre Streamlit, muestra CSV compartido, registros y analizador.", flush=True)
        finally:
            page.screenshot(path=str(SCREENSHOT), full_page=True, timeout=30000)
            browser.close()

if __name__ == "__main__":
    main()
