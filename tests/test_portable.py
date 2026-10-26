"""The engine must run on the phone, where the PC-only libraries are absent (no mcp, Streamlit, plotly, FastAPI)."""
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PC_ONLY = ["mcp", "streamlit", "plotly", "fastapi", "uvicorn", "pydantic", "pydantic_core", "starlette"]
PC_MODULES = {"coach.mcp_server", "coach.api", "coach.sources.coros_mcp", "coach.cli"}


def test_engine_imports_without_pc_libraries():
    code = textwrap.dedent(f"""
        import importlib, importlib.abc, pkgutil, sys
        BLOCKED = {PC_ONLY!r}
        class Block(importlib.abc.MetaPathFinder):
            def find_spec(self, name, path=None, target=None):
                if name.split(".")[0] in BLOCKED:
                    raise ImportError("bloqué sur le téléphone : " + name)
        sys.meta_path.insert(0, Block())
        import coach
        names = [m.name for m in pkgutil.walk_packages(coach.__path__, "coach.")]
        for n in names:
            if n not in {sorted(PC_MODULES)!r}:
                importlib.import_module(n)
        import appkit, appkit.ui, appkit.bridge
        from coach.sources import coros
        assert coros.kind() == "light", coros.kind()
        print(len(names))
    """)
    env = {"PYTHONPATH": f"{ROOT}:{ROOT / 'android' / 'kit' / 'python'}", "PATH": "/usr/bin:/bin"}
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
