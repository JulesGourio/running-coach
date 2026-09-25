"""Fallback: the unofficial COROS Training Hub API (email + password).

Not supported by COROS and may break at any time. Only activities and FIT files are fetched here;
health metrics (HRV, sleep, load) come from the official MCP source.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import httpx

from coach.sources.coros_mcp import CorosError

BASE_URLS = {
    "eu": "https://teameuapi.coros.com",
    "us": "https://teamapi.coros.com",
    "asia": "https://teamcnapi.coros.com",
    "cn": "https://teamcnapi.coros.com",
}
RUN_SPORTS = {100: "Course", 101: "Tapis", 102: "Trail", 103: "Piste"}
FIT_FILE_TYPE = 4


def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class CorosWeb:
    def __init__(self, email: str, password: str, region: str = "eu", client: httpx.Client | None = None):
        if not email or not password:
            raise CorosError("COROS_EMAIL et COROS_PASSWORD sont requis pour l'API non officielle (fichier .env).")
        self.base = BASE_URLS.get(region, BASE_URLS["eu"])
        self.email, self.password = email, password
        self.http = client or httpx.Client(timeout=60, follow_redirects=True)
        self.token: str | None = None

    def _check(self, r: httpx.Response) -> dict:
        r.raise_for_status()
        body = r.json()
        if str(body.get("result")) not in ("0000", "0"):
            raise CorosError(f"COROS : {body.get('message') or body.get('result')}")
        return body.get("data") or {}

    def login(self) -> None:
        pwd = hashlib.md5(self.password.encode()).hexdigest()
        data = self._check(self.http.post(f"{self.base}/account/login",
                                          json={"account": self.email, "accountType": 2, "pwd": pwd}))
        self.token = data.get("accessToken")
        if not self.token:
            raise CorosError("Connexion COROS refusée : pas de jeton renvoyé.")

    def _headers(self) -> dict:
        if not self.token:
            self.login()
        return {"accessToken": self.token}

    def activities(self, start: str, end: str) -> list[dict]:
        out, page = [], 1
        while True:
            data = self._check(self.http.get(f"{self.base}/activity/query", headers=self._headers(), params={
                "size": 100, "pageNumber": page, "startDay": start, "endDay": end, "modeList": "100,101,102,103"}))
            for a in data.get("dataList") or []:
                sport = int(a.get("sportType") or 0)
                if sport not in RUN_SPORTS:
                    continue
                day = str(a.get("date") or "")
                dist_m = _num(a.get("distance"))
                dur = _num(a.get("totalTime"))
                out.append({
                    "label_id": str(a.get("labelId")),
                    "sport_type": sport,
                    "date": f"{day[:4]}-{day[4:6]}-{day[6:8]}" if len(day) == 8 else day,
                    "start_ts": int(a["startTime"]) if a.get("startTime") else None,
                    "type": RUN_SPORTS[sport],
                    "name": a.get("name"),
                    "distance_km": dist_m / 1000 if dist_m else None,
                    "duration_s": dur,
                    "avg_pace": dur / (dist_m / 1000) if dist_m and dur else None,
                    "avg_hr": _num(a.get("avgHr")),
                })
            total = int(data.get("totalPage") or 1)
            if page >= total:
                break
            page += 1
        return out

    def download_fit(self, label_id: str, sport_type: int, dest: Path) -> Path:
        data = self._check(self.http.post(f"{self.base}/activity/detail/download", headers=self._headers(),
                                          params={"labelId": label_id, "sportType": sport_type,
                                                  "fileType": FIT_FILE_TYPE}))
        url = data.get("fileUrl")
        if not url:
            raise CorosError(f"Pas d'URL de fichier FIT pour {label_id}.")
        r = self.http.get(url)
        r.raise_for_status()
        dest.write_bytes(r.content)
        return dest
