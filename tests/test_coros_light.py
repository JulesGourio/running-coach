"""The httpx-only COROS client used on the phone: discovery, login, refresh and MCP calls against a fake server."""
import asyncio
import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx

from coach.config import Settings
from coach.sources import coros_light as cl
from coach.sources.coros_base import CorosError, NeedsLogin

MCP = "https://mcpeu.coros.com/mcp"
AUTH = "https://auth.coros.com"


@pytest.fixture
def s(tmp_path):
    st = Settings()
    st.data_dir = tmp_path
    st.coros_mcp_url = MCP
    return st


def _oauth_routes(router):
    router.post(MCP).mock(return_value=httpx.Response(
        401, headers={"WWW-Authenticate": 'Bearer resource_metadata="https://mcpeu.coros.com/.well-known/oauth-protected-resource/mcp"'}))
    router.get("https://mcpeu.coros.com/.well-known/oauth-protected-resource/mcp").mock(return_value=httpx.Response(
        200, json={"resource": MCP, "authorization_servers": [AUTH], "scopes_supported": ["read", "write"]}))
    router.get(f"{AUTH}/.well-known/oauth-authorization-server").mock(return_value=httpx.Response(200, json={
        "authorization_endpoint": f"{AUTH}/oauth/authorize", "token_endpoint": f"{AUTH}/oauth/token",
        "registration_endpoint": f"{AUTH}/oauth/register"}))
    reg = router.post(f"{AUTH}/oauth/register").mock(return_value=httpx.Response(
        201, json={"client_id": "abc", "redirect_uris": ["http://127.0.0.1:8765/callback"]}))
    return reg


def test_login_start_discovers_registers_and_builds_a_pkce_url(s):
    with respx.mock(assert_all_called=False) as router:
        reg = _oauth_routes(router)
        url = cl.login_start(s)
    q = parse_qs(urlparse(url).query)
    assert url.startswith(f"{AUTH}/oauth/authorize?")
    assert q["client_id"] == ["abc"] and q["code_challenge_method"] == ["S256"]
    assert q["redirect_uri"] == ["http://127.0.0.1:8765/callback"] and q["resource"] == [MCP]
    assert q["scope"] == ["read write"]
    assert json.loads(reg.calls[0].request.content)["token_endpoint_auth_method"] == "none"
    pending = cl.store(s).load()["pending"]
    assert pending["state"] == q["state"][0]


def test_login_start_reuses_the_registration(s):
    with respx.mock(assert_all_called=False) as router:
        reg = _oauth_routes(router)
        cl.login_start(s)
        cl.login_start(s)
    assert reg.call_count == 1


def test_login_finish_exchanges_the_code_and_checks_state(s):
    with respx.mock(assert_all_called=False) as router:
        _oauth_routes(router)
        url = cl.login_start(s)
        token = router.post(f"{AUTH}/oauth/token").mock(return_value=httpx.Response(
            200, json={"access_token": "t1", "refresh_token": "r1", "expires_in": 3600}))
        state = parse_qs(urlparse(url).query)["state"][0]
        with pytest.raises(CorosError, match="state"):
            cl.login_finish(s, "http://127.0.0.1:8765/callback?code=xyz&state=wrong")
        cl.login_finish(s, f"http://127.0.0.1:8765/callback?code=xyz&state={state}")
    form = parse_qs(token.calls[0].request.content.decode())
    assert form["grant_type"] == ["authorization_code"] and form["code"] == ["xyz"] and form["code_verifier"]
    d = cl.store(s).load()
    assert d["tokens"]["access_token"] == "t1" and "pending" not in d
    assert cl.store(s).has_tokens()


def test_login_finish_reports_a_refusal(s):
    cl.store(s).update(pending={"state": "x", "verifier": "v", "redirect_uri": "r"}, client={"client_id": "a"}, meta={})
    with pytest.raises(CorosError, match="access_denied"):
        cl.login_finish(s, "http://127.0.0.1:8765/callback?error=access_denied")


def _logged_in(s, expires_at=None):
    cl.store(s).update(client={"client_id": "abc"}, meta={"token_endpoint": f"{AUTH}/oauth/token", "resource": MCP},
                       tokens={"access_token": "t1", "refresh_token": "r1", "expires_at": expires_at})


def _mcp_server(router, expired_tokens=("t-old",)):
    """initialize answered as SSE with a session id, tools/call answered as JSON, 401 for expired tokens."""
    def handler(request: httpx.Request):
        if request.headers.get("authorization", "").removeprefix("Bearer ") in expired_tokens:
            return httpx.Response(401)
        msg = json.loads(request.content)
        if msg["method"] == "initialize":
            body = "event: message\ndata: " + json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": {"protocolVersion": "2025-06-18"}}) + "\n\n"
            return httpx.Response(200, text=body, headers={"content-type": "text/event-stream", "mcp-session-id": "S1"})
        if msg["method"] == "notifications/initialized":
            assert request.headers["mcp-session-id"] == "S1"
            return httpx.Response(202)
        if msg["method"] == "tools/call":
            assert request.headers["mcp-session-id"] == "S1"
            text = json.dumps("Sport Records\n1. Run")  # COROS double-encodes its text
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": msg["id"],
                                             "result": {"content": [{"type": "text", "text": text}], "isError": False}})
        return httpx.Response(400)
    router.post(MCP).mock(side_effect=handler)
    router.delete(MCP).mock(return_value=httpx.Response(200))


async def _call(s):
    async with cl.CorosLight(s) as c:
        return await c.call("querySportRecords", {})


def test_call_runs_an_mcp_session(s):
    _logged_in(s)
    with respx.mock(assert_all_called=False) as router:
        _mcp_server(router)
        assert asyncio.run(_call(s)) == "Sport Records\n1. Run"


def test_expired_token_is_refreshed_then_the_call_retried(s):
    _logged_in(s)
    cl.store(s).update(tokens={"access_token": "t-old", "refresh_token": "r1", "expires_at": None})
    with respx.mock(assert_all_called=False) as router:
        _mcp_server(router)
        refresh = router.post(f"{AUTH}/oauth/token").mock(return_value=httpx.Response(200, json={"access_token": "t2", "expires_in": 60}))
        assert asyncio.run(_call(s)) == "Sport Records\n1. Run"
    assert parse_qs(refresh.calls[0].request.content.decode())["grant_type"] == ["refresh_token"]
    tok = cl.store(s).load()["tokens"]
    assert tok["access_token"] == "t2" and tok["refresh_token"] == "r1"  # the refresh token is kept


def test_refused_refresh_asks_for_a_new_login(s):
    _logged_in(s, expires_at=1)  # long expired: refreshed before the session starts
    with respx.mock(assert_all_called=False) as router:
        _mcp_server(router)
        router.post(f"{AUTH}/oauth/token").mock(return_value=httpx.Response(400, json={"error": "invalid_grant"}))
        with pytest.raises(NeedsLogin):
            asyncio.run(_call(s))


def test_no_login_yet(s):
    with pytest.raises(NeedsLogin):
        asyncio.run(_call(s))


def test_tool_error_is_raised(s):
    _logged_in(s)
    with respx.mock(assert_all_called=False) as router:
        _mcp_server(router)
        router.post(MCP).mock(side_effect=lambda r: httpx.Response(200, json={
            "jsonrpc": "2.0", "id": json.loads(r.content).get("id"),
            "result": {"content": [{"type": "text", "text": "bad day"}], "isError": True}})
            if json.loads(r.content)["method"] == "tools/call" else
            httpx.Response(200, json={"jsonrpc": "2.0", "id": json.loads(r.content).get("id"), "result": {}}))
        with pytest.raises(CorosError, match="bad day"):
            asyncio.run(_call(s))


def test_sse_parser_handles_several_events():
    text = 'data: {"id": 1}\n\nevent: x\ndata: {"id": 2,\ndata:  "a": 1}\n\n'
    assert cl._sse_messages(text) == [{"id": 1}, {"id": 2, "a": 1}]


def test_factory_prefers_the_library_but_can_be_forced(monkeypatch, s):
    from coach.sources import coros
    monkeypatch.setenv("COACH_COROS_CLIENT", "light")
    assert isinstance(coros.client(s), cl.CorosLight)
    assert coros.connected(s) is False
    _logged_in(s)
    assert coros.connected(s) is True


def test_a_new_region_registers_again(s):
    with respx.mock(assert_all_called=False) as router:
        reg = _oauth_routes(router)
        cl.login_start(s)
        assert cl.store(s).load()["client"]["server"] == MCP
        s.coros_mcp_url = MCP + "?region=us"
        router.post(s.coros_mcp_url).mock(return_value=httpx.Response(401))
        router.get(url__startswith="https://mcpeu.coros.com/.well-known/oauth-protected-resource").mock(
            return_value=httpx.Response(200, json={"resource": MCP, "authorization_servers": [AUTH]}))
        cl.login_start(s)
    assert reg.call_count == 2


def test_two_sessions_refresh_once(s):
    """The sync and a screen action find the token expired together: one refresh, both calls succeed."""
    _logged_in(s)
    cl.store(s).update(tokens={"access_token": "t-old", "refresh_token": "r1", "expires_at": None})

    async def both():
        return await asyncio.gather(_call(s), _call(s))
    with respx.mock(assert_all_called=False) as router:
        _mcp_server(router)
        refresh = router.post(f"{AUTH}/oauth/token").mock(return_value=httpx.Response(200, json={"access_token": "t2", "expires_in": 3600}))
        assert asyncio.run(both()) == ["Sport Records\n1. Run"] * 2
    assert refresh.call_count == 1
