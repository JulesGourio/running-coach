from __future__ import annotations

from dataclasses import dataclass

import numpy as np

HR_ZONES = [("Z1 récup", 0.0, 0.85), ("Z2 endurance", 0.85, 0.90), ("Z3 tempo", 0.90, 0.95),
            ("Z4 seuil", 0.95, 1.00), ("Z5 VO2max", 1.00, 9.9)]
# Fraction of threshold speed.
PACE_ZONES = [("Z1 récup", 0.0, 0.78), ("Z2 endurance", 0.78, 0.88), ("Z3 tempo", 0.88, 0.95),
              ("Z4 seuil", 0.95, 1.02), ("Z5 VO2max", 1.02, 9.9)]


@dataclass
class Athlete:
    hr_max: float = 195.0
    hr_rest: float = 50.0
    lthr: float | None = None
    threshold_pace: float = 270.0  # s/km
    sex: str = "M"

    @property
    def lt_hr(self) -> float:
        return self.lthr or round(0.89 * self.hr_max)

    @property
    def threshold_speed(self) -> float:
        return 1000.0 / self.threshold_pace

    def hr_zone_bounds(self) -> list[tuple[str, float, float]]:
        return [(n, lo * self.lt_hr, hi * self.lt_hr) for n, lo, hi in HR_ZONES]

    def pace_zone_bounds(self) -> list[tuple[str, float, float]]:
        """(name, fastest pace s/km, slowest pace s/km)."""
        ts = self.threshold_speed
        return [(n, 1000 / (hi * ts), 1000 / (lo * ts) if lo else float("inf")) for n, lo, hi in PACE_ZONES]


def hr_zone_index(hr: np.ndarray, a: Athlete) -> np.ndarray:
    edges = np.array([hi for _, _, hi in HR_ZONES[:-1]]) * a.lt_hr
    return np.digitize(hr, edges)


def speed_zone_index(speed: np.ndarray, a: Athlete) -> np.ndarray:
    edges = np.array([hi for _, _, hi in PACE_ZONES[:-1]]) * a.threshold_speed
    return np.digitize(speed, edges)
