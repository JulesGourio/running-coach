import asyncio
import json
from types import SimpleNamespace

from coach.sources.coros_mcp import CorosMCP


def _client(text: str, is_error: bool = False):
    """A stub of mcp.Client exposing only what CorosMCP.call() uses."""
    content = [SimpleNamespace(type="text", text=text)]
    result = SimpleNamespace(content=content, is_error=is_error)

    async def call_tool(tool, args):
        return result

    return SimpleNamespace(call_tool=call_tool)


def _call(text: str) -> str:
    c = CorosMCP.__new__(CorosMCP)  # bypass __init__: .call() only needs .client
    c.client = _client(text)
    return asyncio.run(c.call("someTool"))


def test_call_unwraps_double_json_encoded_text():
    # COROS's official MCP server wraps its text content in an extra layer of JSON encoding
    # (a quoted string with escaped \n) instead of returning the text literally.
    real = "Sport Records — 2026-06-01 to 2026-09-24 (1 records)\n========================\n\n1. Outdoor Run"
    wrapped = json.dumps(real)
    assert _call(wrapped) == real


def test_call_passes_through_plain_text():
    real = "Sport Records — 2026-06-01 to 2026-09-24 (1 records)\n========================"
    assert _call(real) == real


def test_call_tolerates_malformed_quoted_text():
    # Starts with a quote but isn't valid JSON: don't crash, just pass it through untouched.
    odd = '"not actually json'
    assert _call(odd) == odd
