"""Client for the official COROS MCP server (mcp.coros.com), authenticated with OAuth like Claude or Cursor."""
from __future__ import annotations

import asyncio
import json
import os
import threading
import webbrowser
from contextlib import AsyncExitStack
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
from mcp import Client
from mcp.client.auth import OAuthClientProvider, TokenStorage
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client
from mcp.shared.auth import AuthorizationCodeResult, OAuthClientInformationFull, OAuthClientMetadata, OAuthToken

from coach.config import Settings
from coach.sources import parsers


class CorosError(RuntimeError):
    pass


class NeedsLogin(CorosError):
    pass


def root_error(e: BaseException) -> BaseException:
    """The first underlying error inside (nested) exception groups raised by the MCP transport."""
    while isinstance(e, BaseExceptionGroup) and e.exceptions:
        e = e.exceptions[0]
    return e


def describe(e: BaseException) -> str:
    r = root_error(e)
    return f"{type(r).__name__}: {r}" if not isinstance(r, CorosError) else str(r)


class FileTokenStorage(TokenStorage):
    def __init__(self, path: Path):
        self.path = path

    def _load(self) -> dict:
        try:
            return json.loads(self.path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data))
        os.chmod(tmp, 0o600)
        tmp.replace(self.path)

    async def get_tokens(self) -> OAuthToken | None:
        t = self._load().get("tokens")
        return OAuthToken.model_validate(t) if t else None

    async def set_tokens(self, tokens: OAuthToken) -> None:
        d = self._load()
        d["tokens"] = tokens.model_dump(mode="json", exclude_none=True)
        self._save(d)

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        c = self._load().get("client")
        return OAuthClientInformationFull.model_validate(c) if c else None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        d = self._load()
        d["client"] = client_info.model_dump(mode="json", exclude_none=True)
        self._save(d)

    def has_tokens(self) -> bool:
        return bool(self._load().get("tokens"))


class _CallbackServer:
    """Receives the OAuth redirect on http://127.0.0.1:<port>/callback."""

    def __init__(self, port: int):
        self.port = port
        self.params: dict[str, list[str]] | None = None
        self.done = threading.Event()
        self.httpd: HTTPServer | None = None

    def start(self) -> None:
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                q = parse_qs(urlparse(self.path).query)
                if "code" in q or "error" in q:
                    outer.params = q
                    outer.done.set()
                    msg = "Connexion COROS terminée. Tu peux fermer cet onglet."
                else:
                    msg = "En attente de COROS…"
                body = f"<meta charset='utf-8'><p style='font-family:sans-serif'>{msg}</p>".encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args: Any) -> None:
                pass

        self.httpd = HTTPServer(("127.0.0.1", self.port), Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    async def wait(self, timeout: float = 300) -> AuthorizationCodeResult:
        ok = await asyncio.to_thread(self.done.wait, timeout)
        if self.httpd:
            self.httpd.shutdown()
        if not ok or not self.params:
            raise CorosError("Connexion COROS non terminée (délai dépassé).")
        if "error" in self.params:
            raise CorosError(f"COROS a refusé la connexion : {self.params['error'][0]}")
        first = lambda k: self.params.get(k, [None])[0]  # noqa: E731
        return AuthorizationCodeResult(code=first("code"), state=first("state"), iss=first("iss"))


class CorosMCP:
    """Async context manager around the official COROS MCP server."""

    def __init__(self, settings: Settings, interactive: bool = False):
        self.s = settings
        self.interactive = interactive
        self.storage = FileTokenStorage(settings.token_path)
        self._stack: AsyncExitStack | None = None
        self.client: Client | None = None

    async def __aenter__(self) -> "CorosMCP":
        if not self.interactive and not self.storage.has_tokens():
            raise NeedsLogin("Pas encore connecté à COROS : lance `uv run coach login`.")
        cb = _CallbackServer(self.s.oauth_port)

        async def redirect(url: str) -> None:
            if not self.interactive:
                raise NeedsLogin("La connexion COROS a expiré : relance `uv run coach login`.")
            cb.start()
            print(f"\nOuvre cette adresse pour autoriser l'accès à COROS :\n{url}\n")
            webbrowser.open(url)

        provider = OAuthClientProvider(
            server_url=self.s.coros_mcp_url,
            client_metadata=OAuthClientMetadata(
                client_name="Running Coach (local)",
                redirect_uris=[f"http://127.0.0.1:{self.s.oauth_port}/callback"],
                grant_types=["authorization_code", "refresh_token"],
                response_types=["code"],
                token_endpoint_auth_method="none",
            ),
            storage=self.storage,
            redirect_handler=redirect,
            callback_handler=cb.wait,
        )
        self._stack = AsyncExitStack()
        http = await self._stack.enter_async_context(create_mcp_http_client(auth=provider))
        self.client = await self._stack.enter_async_context(
            Client(streamable_http_client(self.s.coros_mcp_url, http_client=http)))
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._stack:
            await self._stack.aclose()

    async def tool_names(self) -> list[str]:
        res = await self.client.list_tools()
        return [t.name for t in res.tools]

    async def call(self, tool: str, args: dict | None = None) -> str:
        res = await self.client.call_tool(tool, args or {})
        text = "\n".join(getattr(c, "text", "") for c in res.content if getattr(c, "type", "") == "text")
        if res.is_error:
            raise CorosError(f"{tool} : {text or 'erreur COROS'}")
        return text

    # ---- typed helpers ----
    async def sport_records(self, start: str, end: str, limit: int = 200) -> list[dict]:
        t = await self.call("querySportRecords", {
            "startDate": start, "endDate": end, "sportTypeCodes": [100, 101, 102, 103], "minDistanceKm": 0,
            "maxDistanceKm": 1000, "minDurationMinutes": 0, "maxDurationMinutes": 6000, "maxAveragePace": "",
            "locationKeyword": "", "limit": limit})
        return parsers.parse_sport_records(t)

    async def download_fit(self, label_id: str, sport_type: int, dest: Path) -> Path:
        t = await self.call("queryActivityFitFileDownloadUrls", {"labelId": label_id, "sportType": sport_type})
        urls = parsers.parse_fit_urls(t)
        if not urls:
            raise CorosError(f"Pas d'URL de fichier FIT pour {label_id} : {t[:200]}")
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as h:
            r = await h.get(urls[0])
            r.raise_for_status()
        dest.write_bytes(r.content)
        return dest

    async def fitness(self) -> dict | None:
        return parsers.parse_fitness(await self.call("queryFitnessAssessmentOverview"))

    async def recovery(self) -> dict | None:
        return parsers.parse_recovery(await self.call("queryRecoveryStatus"))

    async def load(self, days: int = 30) -> list[dict]:
        return parsers.parse_load(await self.call("queryTrainingLoadAssessment", {"days": days}))

    async def hrv(self, start: str, end: str) -> list[dict]:
        return parsers.parse_hrv(await self.call("querySleepHrv", {"startDate": start, "endDate": end, "days": 7}))

    async def sleep(self, days: int = 7) -> list[dict]:
        return parsers.parse_sleep(await self.call("querySleepOverview", {"days": days}))

    async def rhr(self, days: int = 30) -> list[dict]:
        return parsers.parse_rhr(await self.call("queryRestingHeartRate", {"days": days}))

    async def plan(self) -> dict | None:
        return parsers.parse_plan_library(await self.call("queryTrainingPlanLibrary"))

    async def plan_details(self, plan_id: str, start: str, end: str) -> dict:
        return parsers.parse_plan_details(await self.call(
            "queryTrainingPlanDetails", {"planId": plan_id, "startDay": start, "endDay": end}))
