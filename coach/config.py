from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# The official MCP server's hostname is region-specific; unlike the unofficial API's base URLs
# (coach/sources/coros_web.py), COROS does not serve a single global host for it.
MCP_URLS = {
    "eu": "https://mcpeu.coros.com/mcp",
    "us": "https://mcp.coros.com/mcp",
    "asia": "https://mcpcn.coros.com/mcp",
    "cn": "https://mcpcn.coros.com/mcp",
}


def _float(name: str) -> float | None:
    v = os.getenv(name, "").strip()
    return float(v) if v else None


def _pace(name: str) -> float | None:
    v = os.getenv(name, "").strip()
    if not v:
        return None
    if ":" in v:
        m, s = v.split(":")
        return int(m) * 60 + int(s)
    return float(v)


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("COACH_DATA_DIR", ROOT / "data")))
    coros_region: str = field(default_factory=lambda: os.getenv("COROS_REGION", "eu"))
    coros_mcp_url: str = field(default_factory=lambda: os.getenv("COROS_MCP_URL")
                                or MCP_URLS.get(os.getenv("COROS_REGION", "eu"), MCP_URLS["eu"]))
    coros_email: str | None = field(default_factory=lambda: os.getenv("COROS_EMAIL") or None)
    coros_password: str | None = field(default_factory=lambda: os.getenv("COROS_PASSWORD") or None)
    oauth_port: int = field(default_factory=lambda: int(os.getenv("COACH_OAUTH_PORT", "8765")))
    # Athlete overrides; anything left empty is estimated from the data.
    hr_max: float | None = field(default_factory=lambda: _float("ATHLETE_HR_MAX"))
    hr_rest: float | None = field(default_factory=lambda: _float("ATHLETE_HR_REST"))
    lthr: float | None = field(default_factory=lambda: _float("ATHLETE_LTHR"))
    threshold_pace: float | None = field(default_factory=lambda: _pace("ATHLETE_THRESHOLD_PACE"))
    sex: str = field(default_factory=lambda: os.getenv("ATHLETE_SEX", "M"))
    goal_label: str = field(default_factory=lambda: os.getenv("GOAL_LABEL", "10 km"))
    goal_date: str | None = field(default_factory=lambda: os.getenv("GOAL_DATE", "2026-12-13"))
    goal_distance_m: float = field(default_factory=lambda: float(os.getenv("GOAL_DISTANCE_M", "10000")))
    goal_a: float | None = field(default_factory=lambda: _pace("GOAL_TIME_A") or 2400)
    goal_b: float | None = field(default_factory=lambda: _pace("GOAL_TIME_B") or 2490)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "coach.sqlite"

    @property
    def fit_dir(self) -> Path:
        return self.data_dir / "fit"

    @property
    def token_path(self) -> Path:
        return self.data_dir / ".coros_oauth.json"


def get_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    s.fit_dir.mkdir(parents=True, exist_ok=True)
    return s
