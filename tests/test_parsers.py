from coach.sources import parsers as p

FITNESS = """Fitness Assessment Overview
========================

VO2max: 60
Running Level: 87
Threshold Pace: 4:22 /km
5 km Prediction: 20:56
10 km Prediction: 43:26
Half Marathon Prediction: 1:36:42
Marathon Prediction: 3:23:12"""

RECORDS = """Sport Records — 2026-06-01 to 2026-09-24 (2 records)
========================

1. Outdoor Run — 2026-09-24
   Location: (6-8)*1k @3'55
   Time Window: startTimestamp=1790285015 | endTimestamp=1790288095
   Duration: 51:17 | Distance: 10.44 km
   Average Pace: 4:55 /km | Avg HR: 164 bpm | Calories: 747 kcal
   LabelId: 480576807138001095 | SportType: 100

2. Trail Run — 2026-06-06
   Location: Sorèze Trail
   Time Window: startTimestamp=1780729196 | endTimestamp=1780761720
   Duration: 9:02:04 | Distance: 67.43 km
   Average Pace: 8:02 /km | Avg HR: 138 bpm | Calories: 4203 kcal
   LabelId: 478021002018717996 | SportType: 102"""

LOAD = """Training Load Assessment
========================

2026-09-25
Comment: Maintaining
Short-Term Load: 88
Long-Term Load: 89
Load Ratio: 0.98

2026-09-09
Comment: Excessive
Short-Term Load: 141
Long-Term Load: 94
Load Ratio: 1.50"""

HRV = """Sleep HRV — 2026-09-19 to 2026-09-25
========================

HRV Assessment — Last 7 days
========================

2026-09-24:
  HRV Avg: 88 ms — Normal
  Normal Range: 68 - 98 ms
  Baseline: 83 ms
2026-09-23:
  HRV Avg: 59 ms — Below normal
  Normal Range: 70 - 98 ms
  Baseline: 84 ms

Sleep HRV Time Series — Last 7 days
========================

2026-09-19:
  timestamp=1789774490, timezone=8, hrv=94 ms, status=4, confidence=86206"""

SLEEP = """Sleep Overview
========================
Note: each record below is dated by its wake-up day.

2026-09-24
Sleep Score: 95
Daily Sleep: 8h 48min (incl. naps)
Main Sleep (asleep): 7h 13min
Deep Sleep Ratio: 17%
REM Ratio: 24%

2026-09-25
Sleep Score: 0
Sleep detail for this day is not available yet."""

LIBRARY = """Training Plan Library
========================
Plans on this page: 1

1. 10 km objectif sub-40 - 13 decembre [In progress] [mcp]
   Plan ID: 480578599481689163
   Record role: execution
   Editable via MCP: yes
   Dates: 2026-09-28 to 2026-12-13
   Weeks: 11
   Overview: Semaine 1 en decrassage."""

DETAILS = """Training Plan Detail
========================
Periodization
------------------------
Phase 1: Base (2026-09-28 to 2026-10-18), 3 weeks
Phase 4: Race (2026-12-07 to 2026-12-13), 1 weeks

Days (dayNo 7-9)
------------------------
Day 7 - 2026-10-05
Rest day
Day 8 - 2026-10-06
Course 1 [Not started, score 0.0]
Course: VO2max 6x400m
Course JSON: {"dayNo":8,"courseName":"VO2max 6x400m","sportType":1,"sections":[{"sectionType":2,"targetType":1,"targetValue":400}]}
Day 9 - 2026-10-07
Course 1 [Completed, score 88.0]
Course: Footing facile
Course JSON: {"dayNo":9,"courseName":"Footing facile","sportType":1,"sections":[]}

Update hint: to modify this plan, copy ALL course JSON."""


def test_fitness():
    f = p.parse_fitness(FITNESS)
    assert f["vo2max"] == 60 and f["threshold"] == 262
    assert f["p5"] == 1256 and f["p10"] == 2606 and f["half"] == 5802 and f["marathon"] == 12192


def test_records():
    r = p.parse_sport_records(RECORDS)
    assert [x["label_id"] for x in r] == ["480576807138001095", "478021002018717996"]
    assert r[0]["distance_km"] == 10.44 and r[0]["avg_pace"] == 295 and r[0]["avg_hr"] == 164
    assert r[1]["type"] == "Trail" and r[1]["duration_s"] == 9 * 3600 + 2 * 60 + 4


def test_load_hrv_sleep():
    assert [x["ratio"] for x in p.parse_load(LOAD)] == [1.5, 0.98]
    h = p.parse_hrv(HRV)
    assert len(h) == 2 and h[0]["hrv_eval"] == "Below normal" and h[1]["hrv_base"] == 83
    s = p.parse_sleep(SLEEP)
    assert len(s) == 1 and s[0]["sleep_score"] == 95 and s[0]["sleep_total"] == "8h 48min"


def test_plan():
    lib = p.parse_plan_library(LIBRARY)
    assert lib == {"id": "480578599481689163", "name": "10 km objectif sub-40 - 13 decembre",
                   "start": "2026-09-28", "end": "2026-12-13", "weeks": 11}
    d = p.parse_plan_details(DETAILS)
    assert [x["name"] for x in d["phases"]] == ["Base", "Course"]
    assert [x["day_no"] for x in d["days"]] == [7, 8, 9]
    assert d["days"][0]["rest"] and d["days"][1]["courses"][0]["json"]["courseName"] == "VO2max 6x400m"
    assert not p.is_done(d["days"][1]["courses"][0]["status"]) and p.is_done(d["days"][2]["courses"][0]["status"])


SLEEP_FULL = """Sleep Overview
========================
Note: each record below is dated by its wake-up day.

2026-09-24
Sleep Score: 95
Daily Sleep: 8h 48min (incl. naps)
Main Sleep (asleep): 7h 13min
Main Sleep Period (incl. awake): 7h 26min
Sleep metrics scope: daily
Deep Sleep Ratio: 17%
Light Sleep Ratio: 56%
REM Ratio: 24%
Awake Ratio: 3%
Awake Time: 13 min
Awake Count (>5 min): 0
Main Sleep Window: 2026-09-24 01:42 - 2026-09-24 09:08
Naps Total (asleep): 1h 35min
Naps Period (incl. awake): 1h 55min
Nap Window: 2026-09-24 17:25 - 2026-09-24 19:20

2026-09-25
Sleep Score: 72
Daily Sleep: 6h 9min (incl. naps)
Main Sleep (asleep): 5h 28min
Main Sleep Period (incl. awake): 5h 34min
Deep Sleep Ratio: 28%
Light Sleep Ratio: 54%
REM Ratio: 16%
Awake Ratio: 2%
Awake Time: 6 min
Awake Count (>5 min): 0
Main Sleep Window: 2026-09-25 03:21 - 2026-09-25 08:55

2026-09-26
Sleep detail for this day is not available yet."""


def test_parse_sleep_full():
    rows = p.parse_sleep_full(SLEEP_FULL)
    assert [r["date"] for r in rows] == ["2026-09-24", "2026-09-25"]
    a, b = rows
    assert (a["total_min"], a["main_min"], a["naps_min"]) == (528, 433, 95)
    assert (a["deep_pct"], a["rem_pct"], a["awake_min"]) == (17, 24, 13)
    assert a["bedtime"] == "2026-09-24 01:42" and a["naps"] == [{"start": "2026-09-24 17:25", "end": "2026-09-24 19:20"}]
    assert b["naps_min"] == 0 and b["naps"] == [] and b["main_min"] == 328
