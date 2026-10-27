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

from mcp import Client
from mcp.client.auth import OAuthClientProvider, TokenStorage
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client
from mcp.shared.auth import AuthorizationCodeResult, OAuthClientInformationFull, OAuthClientMetadata, OAuthToken

from coach.config import Settings
from coach.sources.coros_base import CorosError, CorosTools, NeedsLogin, describe, root_error, tool_text

__all__ = ["CorosError", "CorosMCP", "NeedsLogin", "describe", "root_error"]


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


class CorosMCP(CorosTools):
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
        return tool_text(res.content, res.is_error, tool)
