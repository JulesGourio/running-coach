from __future__ import annotations

import json
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

# Settings that can also be edited in the app (phone Réglages): stored in data/profil.json.
# A value set in the environment (.env on the PC) always wins over the file.
PROFILE_KEYS = {
    "GOAL_LABEL": "Nom de l'objectif (ex. 10 km)",
    "GOAL_DATE": "Date de la course (AAAA-MM-JJ)",
    "GOAL_DISTANCE_M": "Distance de la course (m)",
    "GOAL_TIME_A": "Objectif A (min:s ou h:min:s)",
    "GOAL_TIME_B": "Objectif B (min:s ou h:min:s)",
    "ATHLETE_HR_MAX": "FC max (vide : estimée)",
    "ATHLETE_HR_REST": "FC de repos (vide : mesurée)",
    "ATHLETE_LTHR": "FC au seuil (vide : estimée)",
    "ATHLETE_THRESHOLD_PACE": "Allure seuil min:s/km (vide : COROS)",
    "ATHLETE_SEX": "Sexe (M ou F)",
    "COROS_REGION": "Région du compte COROS (eu, us, asia)",
}


def data_dir() -> Path:
    return Path(os.getenv("COACH_DATA_DIR", ROOT / "data"))


def profile_path() -> Path:
    return data_dir() / "profil.json"


def profile() -> dict[str, str]:
    try:
        d = json.loads(profile_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return {k: str(v) for k, v in d.items() if k in PROFILE_KEYS and v not in (None, "")}


def save_profile(values: dict) -> dict[str, str]:
    """Merge `values` into the profile file (an empty value removes the key) and return the new profile."""
    unknown = set(values) - set(PROFILE_KEYS)
    if unknown:
        raise ValueError(f"réglage inconnu : {', '.join(sorted(unknown))}")
    cur = profile()
    for k, v in values.items():
        v = "" if v is None else str(v).strip()
        if v:
            cur[k] = v
        else:
            cur.pop(k, None)
    _check(cur)
    p = profile_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")
    return cur


BOUNDS = {"ATHLETE_HR_MAX": (120, 230), "ATHLETE_HR_REST": (25, 110), "ATHLETE_LTHR": (100, 220),
          "GOAL_DISTANCE_M": (400, 250000)}


def _check(p: dict[str, str]) -> None:
    import math
    from datetime import date
    for k, (lo, hi) in BOUNDS.items():
        if k in p:
            try:
                v = float(p[k].replace(",", "."))
            except ValueError as e:
                raise ValueError(f"{PROFILE_KEYS[k]} : nombre attendu") from e
            if not math.isfinite(v) or not lo <= v <= hi:
                raise ValueError(f"{PROFILE_KEYS[k]} : entre {lo} et {hi}")
    for k in ("GOAL_TIME_A", "GOAL_TIME_B", "ATHLETE_THRESHOLD_PACE"):
        if k in p and parse_clock(p[k]) is None:
            raise ValueError(f"{PROFILE_KEYS[k]} : format attendu 4:05 ou 1:29:00")
    if "GOAL_DATE" in p:
        date.fromisoformat(p["GOAL_DATE"])
    if "COROS_REGION" in p and p["COROS_REGION"] not in MCP_URLS:
        raise ValueError("Région COROS : eu, us ou asia")
    if "ATHLETE_SEX" in p and p["ATHLETE_SEX"] not in ("M", "F"):
        raise ValueError("Sexe : M ou F")


def valid_profile(values: dict) -> tuple[dict[str, str], list[str]]:
    """The keys of `values` that pass the checks one by one, and the rejected ones."""
    ok, bad = {}, []
    for k, v in values.items():
        if k not in PROFILE_KEYS or v in (None, ""):
            continue
        try:
            _check({k: str(v).strip()})
            ok[k] = str(v).strip()
        except ValueError:
            bad.append(k)
    return ok, bad


def parse_clock(v: str) -> float | None:
    """'4:05' -> 245, '1:29:00' -> 5340, '245' -> 245."""
    v = v.strip()
    try:
        parts = [int(x) for x in v.split(":")]
    except ValueError:
        return None
    if len(parts) == 1:
        return float(parts[0])
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return None


def env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    if v is not None and v.strip():
        return v.strip()
    return profile().get(name, default)


def _float(name: str) -> float | None:
    v = (env(name) or "").replace(",", ".")
    return float(v) if v else None


def _pace(name: str) -> float | None:
    v = env(name) or ""
    return parse_clock(v) if v else None


def _secret(env_name: str, vault_name: str) -> str | None:
    if os.getenv(env_name):
        return os.getenv(env_name)
    from coach import vault
    return vault.get(vault_name) or None


@dataclass
class Settings:
    data_dir: Path = field(default_factory=data_dir)
    coros_region: str = field(default_factory=lambda: env("COROS_REGION", "eu"))
    coros_mcp_url: str = field(default_factory=lambda: os.getenv("COROS_MCP_URL")
                                or MCP_URLS.get(env("COROS_REGION", "eu"), MCP_URLS["eu"]))
    coros_email: str | None = field(default_factory=lambda: _secret("COROS_EMAIL", "coros_email"))
    coros_password: str | None = field(default_factory=lambda: _secret("COROS_PASSWORD", "coros_password"))
    oauth_port: int = field(default_factory=lambda: int(os.getenv("COACH_OAUTH_PORT", "8765")))
    # Athlete overrides; anything left empty is estimated from the data.
    hr_max: float | None = field(default_factory=lambda: _float("ATHLETE_HR_MAX"))
    hr_rest: float | None = field(default_factory=lambda: _float("ATHLETE_HR_REST"))
    lthr: float | None = field(default_factory=lambda: _float("ATHLETE_LTHR"))
    threshold_pace: float | None = field(default_factory=lambda: _pace("ATHLETE_THRESHOLD_PACE"))
    sex: str = field(default_factory=lambda: env("ATHLETE_SEX", "M"))
    goal_label: str = field(default_factory=lambda: env("GOAL_LABEL", "10 km"))
    goal_date: str | None = field(default_factory=lambda: env("GOAL_DATE", "2026-12-13"))
    goal_distance_m: float = field(default_factory=lambda: _float("GOAL_DISTANCE_M") or 10000.0)
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
