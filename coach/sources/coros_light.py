"""The official COROS MCP server with httpx only: OAuth 2.1 (PKCE, client registration, refresh) and the
streamable HTTP transport, without the `mcp` library (whose pydantic-core / rpds-py builds do not exist on Android).

Login happens in two steps, so the phone can show COROS's page in a web view and catch the redirect itself:
``login_start(s)`` returns the address to open; ``login_finish(s, redirected_url)`` exchanges the code. The
redirect address is the same loopback one as on the PC; nothing has to listen on it on the phone.
Tokens live in ``data/.coros_oauth_light.json`` (the app's private folder on the phone, mode 600 on the PC).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from coach.config import Settings
from coach.sources.coros_base import CorosError, CorosTools, NeedsLogin, tool_text

PROTOCOL_VERSION = "2025-06-18"
CLIENT_NAME = "Running Coach (mobile)"
ACCEPT = "application/json, text/event-stream"


def redirect_uri(s: Settings) -> str:
    return f"http://127.0.0.1:{s.oauth_port}/callback"


# The background sync and a screen action run in the same process: one refresh and one file write at a time.
_lock = threading.RLock()  # file writes
_refresh_lock = threading.Lock()  # token refresh (a plain Lock: taken in a worker thread, released here)


class LightStore:
    """The client registration, the tokens, the discovered endpoints and a login in progress, in one file."""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict:
        try:
            return json.loads(self.path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data))
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        tmp.replace(self.path)

    def update(self, **parts: Any) -> dict:
        with _lock:
            d = self.load()
            d.update(parts)
            self.save(d)
            return d

    def has_tokens(self) -> bool:
        return bool(self.load().get("tokens", {}).get("access_token"))

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)


def store(s: Settings) -> LightStore:
    return LightStore(s.data_dir / ".coros_oauth_light.json")


# ---- discovery ----------------------------------------------------------------------------------------------

def _origin(url: str) -> str:
    u = urlparse(url)
    return f"{u.scheme}://{u.netloc}"


def _path(url: str) -> str:
    return urlparse(url).path.rstrip("/")


def _json(http: httpx.Client, url: str) -> dict | None:
    try:
        r = http.get(url, headers={"Accept": "application/json", "MCP-Protocol-Version": PROTOCOL_VERSION})
    except httpx.HTTPError:
        return None
    if r.status_code != 200:
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _resource_metadata_url(header: str | None) -> str | None:
    if not header or "resource_metadata" not in header:
        return None
    part = header.split("resource_metadata", 1)[1].lstrip(" =")
    return part.split('"')[1] if part.startswith('"') else part.split(",")[0].strip()


def discover(http: httpx.Client, mcp_url: str) -> dict:
    """Endpoints of COROS's authorization server, the way MCP clients find them (RFC 9728 then RFC 8414)."""
    origin, path = _origin(mcp_url), _path(mcp_url)
    hinted = None
    try:
        r = http.post(mcp_url, json={"jsonrpc": "2.0", "id": 0, "method": "ping"},
                      headers={"Accept": ACCEPT, "Content-Type": "application/json"})
        if r.status_code == 401:
            hinted = _resource_metadata_url(r.headers.get("www-authenticate"))
    except httpx.HTTPError:
        pass
    prm = None
    for url in [hinted, f"{origin}/.well-known/oauth-protected-resource{path}", f"{origin}/.well-known/oauth-protected-resource"]:
        if url and (prm := _json(http, url)):
            break
    issuer = ((prm or {}).get("authorization_servers") or [origin])[0].rstrip("/")
    i_origin, i_path = _origin(issuer), _path(issuer)
    candidates = ([f"{i_origin}/.well-known/oauth-authorization-server{i_path}", f"{i_origin}/.well-known/openid-configuration{i_path}",
                   f"{issuer}/.well-known/openid-configuration"] if i_path else
                  [f"{i_origin}/.well-known/oauth-authorization-server", f"{i_origin}/.well-known/openid-configuration"])
    asm = next((m for m in (_json(http, u) for u in candidates) if m), None) or {}
    scopes = (prm or {}).get("scopes_supported") or []
    return {
        "authorization_endpoint": asm.get("authorization_endpoint") or f"{i_origin}/authorize",
        "token_endpoint": asm.get("token_endpoint") or f"{i_origin}/token",
        "registration_endpoint": asm.get("registration_endpoint") or f"{i_origin}/register",
        "resource": (prm or {}).get("resource") or mcp_url,
        "scope": " ".join(scopes) if scopes else None,
    }


# ---- login --------------------------------------------------------------------------------------------------

def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def login_start(s: Settings, http: httpx.Client | None = None) -> str:
    """Register this device as a COROS client if needed and return the authorization address to open."""
    st = store(s)
    redirect = redirect_uri(s)
    with (http or httpx.Client(timeout=30, follow_redirects=True)) as h:
        meta = discover(h, s.coros_mcp_url)
        client = st.load().get("client") or {}
        # a registration belongs to one server: a new region (or address) registers again
        if (not client.get("client_id") or redirect not in client.get("redirect_uris", [])
                or client.get("server") != s.coros_mcp_url):
            r = h.post(meta["registration_endpoint"], json={
                "client_name": CLIENT_NAME, "redirect_uris": [redirect],
                "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"],
                "token_endpoint_auth_method": "none", **({"scope": meta["scope"]} if meta["scope"] else {})})
            if r.status_code >= 400:
                raise CorosError(f"COROS refuse l'enregistrement de l'appli ({r.status_code}) : {r.text[:200]}")
            client = {**r.json(), "server": s.coros_mcp_url}
    verifier = _b64(secrets.token_bytes(48))
    state = _b64(secrets.token_bytes(24))
    challenge = _b64(hashlib.sha256(verifier.encode()).digest())
    st.update(client=client, meta=meta, pending={"state": state, "verifier": verifier, "redirect_uri": redirect,
                                                 "at": time.time()})
    q = {"response_type": "code", "client_id": client["client_id"], "redirect_uri": redirect,
         "code_challenge": challenge, "code_challenge_method": "S256", "state": state, "resource": meta["resource"]}
    if meta["scope"]:
        q["scope"] = meta["scope"]
    sep = "&" if "?" in meta["authorization_endpoint"] else "?"
    return meta["authorization_endpoint"] + sep + urlencode(q)


def _save_tokens(st: LightStore, tok: dict, old: dict | None = None) -> dict:
    if not tok.get("access_token"):
        raise CorosError("Réponse de COROS sans jeton d'accès.")
    out = {"access_token": tok["access_token"], "token_type": tok.get("token_type", "Bearer"),
           "refresh_token": tok.get("refresh_token") or (old or {}).get("refresh_token"),
           "scope": tok.get("scope"),
           "expires_at": time.time() + float(tok["expires_in"]) if tok.get("expires_in") else None}
    st.update(tokens=out)
    return out


def login_finish(s: Settings, redirected_to: str, http: httpx.Client | None = None) -> None:
    """Exchange the code found in the redirect address (`…/callback?code=…&state=…`) for tokens."""
    st = store(s)
    d = st.load()
    pending, client, meta = d.get("pending"), d.get("client") or {}, d.get("meta") or {}
    if not pending:
        raise CorosError("Aucune connexion COROS en cours : recommence.")
    q = parse_qs(urlparse(redirected_to).query)
    if "error" in q:
        raise CorosError(f"COROS a refusé la connexion : {q['error'][0]}")
    code, state = (q.get("code") or [None])[0], (q.get("state") or [None])[0]
    if not code:
        raise CorosError("Adresse de retour sans code d'autorisation.")
    if state != pending["state"]:
        raise CorosError("Réponse de COROS inattendue (state différent) : recommence la connexion.")
    with (http or httpx.Client(timeout=30)) as h:
        r = h.post(meta["token_endpoint"], data={
            "grant_type": "authorization_code", "code": code, "redirect_uri": pending["redirect_uri"],
            "client_id": client["client_id"], "code_verifier": pending["verifier"], "resource": meta["resource"]})
    if r.status_code >= 400:
        raise CorosError(f"COROS refuse le code ({r.status_code}) : {r.text[:200]}")
    _save_tokens(st, r.json())
    d = st.load()
    d.pop("pending", None)
    st.save(d)


# ---- the MCP session ----------------------------------------------------------------------------------------

def _sse_messages(text: str) -> list[dict]:
    out, data = [], []
    for line in text.splitlines() + [""]:
        if line.startswith("data:"):
            data.append(line[5:].lstrip())
        elif not line.strip() and data:
            try:
                out.append(json.loads("\n".join(data)))
            except json.JSONDecodeError:
                pass
            data = []
    return out


class CorosLight(CorosTools):
    """Async context manager with the same interface as `CorosMCP`."""

    def __init__(self, settings: Settings, interactive: bool = False, http: httpx.AsyncClient | None = None):
        self.s = settings
        self.st = store(settings)
        self._http = http
        self.http: httpx.AsyncClient | None = None
        self.session_id: str | None = None
        self._ids = 0

    async def __aenter__(self) -> "CorosLight":
        if not self.st.has_tokens():
            raise NeedsLogin("Pas encore connecté à COROS : connecte-toi dans Réglages.")
        self.http = self._http or httpx.AsyncClient(timeout=90, follow_redirects=True)
        try:
            d = self.st.load()
            exp = (d.get("tokens") or {}).get("expires_at")
            if exp and exp < time.time() + 60:
                await self._refresh()
            init = await self._rpc("initialize", {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                                                  "clientInfo": {"name": CLIENT_NAME, "version": "1"}})
            self.protocol = (init or {}).get("protocolVersion", PROTOCOL_VERSION)
            await self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        except BaseException:
            if self._http is None:
                await self.http.aclose()
            raise
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self.http and self.session_id:
            try:
                await self.http.delete(self.s.coros_mcp_url, headers=self._headers())
            except httpx.HTTPError:
                pass
        if self.http and self._http is None:
            await self.http.aclose()

    _sent_token: str | None = None

    def _headers(self) -> dict:
        tok = (self.st.load().get("tokens") or {}).get("access_token")
        self._sent_token = tok
        h = {"Accept": ACCEPT, "Content-Type": "application/json", "Authorization": f"Bearer {tok}",
             "MCP-Protocol-Version": getattr(self, "protocol", PROTOCOL_VERSION)}
        if self.session_id:
            h["Mcp-Session-Id"] = self.session_id
        return h

    async def _refresh(self) -> None:
        """Refresh the access token, one caller at a time; a caller that waited reuses the new token."""
        import asyncio
        used = self._sent_token
        await asyncio.to_thread(_refresh_lock.acquire)
        try:
            d = self.st.load()
            tok, client, meta = d.get("tokens") or {}, d.get("client") or {}, d.get("meta") or {}
            fresh = not tok.get("expires_at") or tok["expires_at"] > time.time() + 60
            if used and tok.get("access_token") and tok["access_token"] != used and fresh:
                return  # another caller refreshed meanwhile (refresh tokens are single use)
            if not tok.get("refresh_token") or not meta.get("token_endpoint"):
                raise NeedsLogin("La connexion COROS a expiré : reconnecte-toi dans Réglages.")
            r = await self.http.post(meta["token_endpoint"], data={
                "grant_type": "refresh_token", "refresh_token": tok["refresh_token"], "client_id": client.get("client_id"),
                "resource": meta.get("resource")})
            if r.status_code >= 400:
                raise NeedsLogin("La connexion COROS a expiré : reconnecte-toi dans Réglages.")
            _save_tokens(self.st, r.json(), tok)
        finally:
            _refresh_lock.release()

    async def _post(self, msg: dict, retry: bool = True) -> httpx.Response:
        r = await self.http.post(self.s.coros_mcp_url, json=msg, headers=self._headers())
        if r.status_code == 401 and retry:
            await self._refresh()
            return await self._post(msg, retry=False)
        if r.status_code == 401:
            raise NeedsLogin("La connexion COROS a expiré : reconnecte-toi dans Réglages.")
        if r.status_code == 404 and self.session_id and retry:
            raise CorosError("Session COROS expirée : relance la synchronisation.")
        if r.status_code >= 400:
            raise CorosError(f"COROS a répondu {r.status_code} : {r.text[:200]}")
        if sid := r.headers.get("mcp-session-id"):
            self.session_id = sid
        return r

    async def _rpc(self, method: str, params: dict) -> Any:
        self._ids += 1
        rid = self._ids
        r = await self._post({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        ctype = r.headers.get("content-type", "")
        msgs = _sse_messages(r.text) if "text/event-stream" in ctype else [r.json()]
        reply = next((m for m in msgs if isinstance(m, dict) and m.get("id") == rid), None)
        if reply is None:
            raise CorosError(f"Pas de réponse de COROS à {method}.")
        if "error" in reply:
            err = reply["error"] or {}
            raise CorosError(f"{method} : {err.get('message') or err}")
        return reply.get("result")

    async def tool_names(self) -> list[str]:
        res = await self._rpc("tools/list", {})
        return [t["name"] for t in (res or {}).get("tools", [])]

    async def call(self, tool: str, args: dict | None = None) -> str:
        res = await self._rpc("tools/call", {"name": tool, "arguments": args or {}}) or {}
        return tool_text(res.get("content") or [], bool(res.get("isError")), tool)
