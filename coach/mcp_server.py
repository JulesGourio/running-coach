"""Local MCP server: lets Claude (Claude Code in VS Code) read the analyses and save written verdicts.
The tools live in `tools` (shared with the phone app); only the async sync is specific to this server."""
from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from coach import tools
from coach.config import get_settings
from coach.db import DB

server = MCPServer("running-coach", instructions=tools.INSTRUCTIONS)
for _fn in tools.TOOLS:
    server.tool()(_fn)


@server.tool()
async def synchroniser(jours: int = 14) -> str:
    """Récupère les dernières données COROS (connexion faite au préalable avec `uv run coach login`)
    et analyse les nouvelles séances."""
    from coach.sources.coros_base import describe
    from coach.sync import analyze, sync_mcp
    s = get_settings()
    db = DB(s.db_path)
    logs: list[str] = []
    try:
        await sync_mcp(s, db, days=jours, interactive=False, log=logs.append)
    except Exception as e:  # noqa: BLE001 - report any sync failure back to Claude as text
        return f"Synchronisation impossible : {describe(e)}"
    analyze(s, db, log=logs.append)
    return "\n".join(logs)


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
