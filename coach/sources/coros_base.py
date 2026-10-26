"""What every COROS client shares: errors, and the typed helpers over the official MCP tools.

Two clients implement `call(tool, args) -> str`: `coros_mcp.CorosMCP` (the `mcp` library, on the PC) and
`coros_light.CorosLight` (httpx only, on the phone). `coros.client()` picks one. Nothing here imports `mcp`.
"""
from __future__ import annotations

import json
from pathlib import Path

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


def tool_text(content: list, is_error: bool, tool: str) -> str:
    """Join the text parts of a tool result. COROS wraps its text in an extra layer of JSON encoding
    (a quoted string with escaped \\n) instead of returning it literally; unwrap it."""
    parts = []
    for c in content:
        kind = c.get("type") if isinstance(c, dict) else getattr(c, "type", "")
        if kind != "text":
            continue
        t = c.get("text", "") if isinstance(c, dict) else getattr(c, "text", "")
        if t[:1] == '"':
            try:
                t = json.loads(t)
            except (json.JSONDecodeError, TypeError):
                pass
        parts.append(t)
    text = "\n".join(parts)
    if is_error:
        raise CorosError(f"{tool} : {text or 'erreur COROS'}")
    return text


class CorosTools:
    """Typed helpers; subclasses provide `async call(tool, args) -> str` and the async context manager."""

    async def call(self, tool: str, args: dict | None = None) -> str:  # pragma: no cover - abstract
        raise NotImplementedError

    async def sport_records(self, start: str, end: str, limit: int = 200, all_sports: bool = False) -> list[dict]:
        t = await self.call("querySportRecords", {
            "startDate": start, "endDate": end, "sportTypeCodes": [65535] if all_sports else [100, 101, 102, 103], "minDistanceKm": 0,
            "maxDistanceKm": 1000, "minDurationMinutes": 0, "maxDurationMinutes": 6000, "maxAveragePace": "",
            "locationKeyword": "", "limit": limit})
        return parsers.parse_sport_records(t)

    async def download_fit(self, label_id: str, sport_type: int, dest: Path) -> Path:
        import httpx

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

    async def sleep_range(self, start: str, end: str) -> list[dict]:
        return parsers.parse_sleep_full(await self.call("querySleepOverview", {"startDate": start, "endDate": end}))

    async def rhr(self, days: int = 30) -> list[dict]:
        return parsers.parse_rhr(await self.call("queryRestingHeartRate", {"days": days}))

    async def plan(self) -> dict | None:
        return parsers.parse_plan_library(await self.call("queryTrainingPlanLibrary"))

    async def plan_details(self, plan_id: str, start: str, end: str) -> dict:
        return parsers.parse_plan_details(await self.call(
            "queryTrainingPlanDetails", {"planId": plan_id, "startDay": start, "endDay": end}))
