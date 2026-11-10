import ast
from pathlib import Path
import pytest

def test_modules_parse():
    for name in ['app.py','cli.py','shared_data.py','fetch_nba.py','model.py',
                 'tracker.py','diagnostics.py','make_demo.py']:
        ast.parse(Path(name).read_text(encoding='utf-8'),filename=name)

def test_app_reads_shared_data_without_network():
    src=Path('app.py').read_text(encoding='utf-8')
    assert 'shared_path(root)' in src
    assert 'fetch_seasons(' not in src
    assert 'Analizar jugador (fácil)' in src
    assert 'Proyecciones por CSV' in src
    assert 'Backtesting cronológico' in src

def test_streamlit_app_smoke():
    pytest.importorskip('streamlit')
    from streamlit.testing.v1 import AppTest
    at=AppTest.from_file(Path(__file__).resolve().parents[1] / 'app.py',default_timeout=90).run()
    assert not at.exception,[e.message for e in at.exception]
