"""Which COROS client to use: the `mcp` library when it is installed (PC), the httpx-only one otherwise (phone).
`COACH_COROS_CLIENT=light` forces the light client on the PC (to test it), `=mcp` forces the library."""
from __future__ import annotations

import importlib.util
import os

from coach.config import Settings
from coach.sources.coros_base import CorosTools


def kind() -> str:
    forced = os.getenv("COACH_COROS_CLIENT", "").strip().lower()
    if forced in ("light", "mcp"):
        return forced
    try:
        return "mcp" if importlib.util.find_spec("mcp") is not None else "light"
    except (ImportError, ValueError):
        return "light"


def connected(s: Settings) -> bool:
    """Whether a COROS login is stored for the client in use."""
    if kind() == "light":
        from coach.sources.coros_light import store
        return store(s).has_tokens()
    try:
        data = s.token_path.read_text()
    except FileNotFoundError:
        return False
    return '"tokens"' in data


def client(s: Settings, interactive: bool = False) -> CorosTools:
    if kind() == "light":
        from coach.sources.coros_light import CorosLight
        return CorosLight(s, interactive=interactive)
    from coach.sources.coros_mcp import CorosMCP
    return CorosMCP(s, interactive=interactive)
