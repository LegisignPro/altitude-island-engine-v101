"""Unit tests for sequencer.py -- timing, business days, pacing, fact-safe merge, export shape."""
import sys, os
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

import pitch_generator as pg
import scraper
import sequencer as seq

FAILS = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        FAILS.append(f"{name}: {detail}")
        print(f"  FAIL  {name}  {detail}")


def demo_frame():
    rows, meta = scraper.load_fallback_dataset()
    df = pd.DataFrame(rows, columns=scraper.EXHIBITOR_COLUMNS)
    df["sqft"] = pd.to_numeric(df["sqft"], errors="coerce").fillna(0).astype(int)
    df = df[df["sqft"] >= 400].copy()
    for col, val in [("prior_sqft", None), ("yoy_status", "NO PRIOR DATA"), ("newborn_island", False),
                     ("first_name", ""), ("last_name", ""), ("contact_name", ""), ("contact_title", ""),
                     ("email", ""), ("linkedin", ""), ("months_in_role", None), ("new_hire", False),
                     ("hq_city", ""), ("hq_state", ""), ("hq_country", ""), ("freight_tag", "HQ unknown"),
                     ("employees", None), ("industry", ""), ("apollo_source", "")]:
        df[col] = val
    return pg.assign_pitches(df, meta["show_name"]), meta


print("timeline phases")
today = date(2026, 9, 14)
cases = [
    (today + timedelta(days=400), seq.PHASE_EARLY, True),
    (today + timedelta(days=210), seq.PHASE_PRIME, True),   # ~6.9 months
    (today + timedelta(days=100), seq.PHASE_LATE, True),    # ~3.3 months
    (today + timedelta(days=20), seq.PHASE_CLOSED, False),
    (today - timedelta(days=5), seq.PHASE_PAST, False),
    (None, seq.PHASE_UNKNOWN, True),
]
for show, phase, sendable in cases:
    tl = seq.outreach_timeline(show, today=today)
    check(f"phase {phase}", tl["phase"] == phase, f"got {tl['phase']} for {show}")
    check(f"sendable {phase}", tl["sendable"] is sendable, f"got {tl['sendable']}")

tl_early = seq.outreach_timeline(today + timedelta(days=400), today=today)
check("early first touch is ~9 months before the show",
      270 <= (today + timedelta(days=400) - tl_early["first_touch"]).days <= 276,
      str(tl_early["first_touch"]))
check("prime first touch is today or the next business day",
      seq.outreach_timeline(today + timedelta(days=210), today=today)["first_touch"] >= today)

print("business days")
check("saturday rolls to monday", seq.next_business_day(date(2026, 9, 19)) == date(2026, 9, 21))
check("sunday rolls to monday", seq.next_business_day(date(2026, 9, 20)) == date(2026, 9, 21))
check("weekday untouched", seq.next_business_day(date(2026, 9, 18)) == date(2026, 9, 18))
for name, cadence in seq.CADENCES.items():
    start = date(2026, 9, 14)
    dates = [seq.send_date(start, s["day"]) for s in cadence]
    check(f"no weekend send in '{name}'", all(d.weekday() < 5 for d in dates), str(dates))
    check(f"send dates non-decreasing in '{name}'", dates == sorted(dates), str(dates))

print("pacing")
starts = seq.pace_start_dates(12, date(2026, 9, 14), per_day=5)
check("pacing caps per day", max(starts.count(d) for d in set(starts)) == 5, str(sorted(set(starts))))
check("pacing spans 3 business days", len(set(starts)) == 3, str(sorted(set(starts))))
check("pacing never weekends", all(d.weekday() < 5 for d in starts))

print("fact-safe merge")
targets, meta = demo_frame()
row = targets.iloc[0].copy()
row["booth_number"] = ""
row["hall"] = ""
row["first_name"] = ""
row["contact_title"] = ""
row["prior_sqft"] = None
row["hq_state"] = ""
touches = seq.build_sequence(row, meta["show_name"], None, "Las Vegas", {},
                             seq.DEFAULT_CADENCE, date(2026, 9, 14))
blob = "\n".join(t["subject"] + t["subject_b"] + t["body"] for t in touches)
for bad in ("None", "nan", "Hi ,", "{", "}", "n/a sq ft", " ,"):
    check(f"no '{bad}' leaks into the copy", bad not in blob,
          blob[max(0, blob.find(bad) - 60):blob.find(bad) + 60] if bad in blob else "")
check("company greeting used when no first name", "team," in touches[0]["body"])

print("trigger-aware copy")
bodies = {}
for trig in pg.TRIGGERS:
    r = targets.iloc[0].copy()
    r["trigger"] = trig
    r["first_name"] = "Dana"
    r["contact_title"] = "Event Manager"
    r["hq_state"] = "OH"
    r["freight_tag"] = "High Freight Savings Potential"
    r["prior_sqft"] = 100
    tch = seq.build_sequence(r, meta["show_name"], date(2027, 4, 20), "Las Vegas", {"name": "Sam Reed"},
                             seq.DEFAULT_CADENCE, date(2026, 9, 14))
    bodies[trig] = "\n".join(t["subject"] + t["body"] for t in tch)
    check(f"trigger {trig} greets by first name", "Hi Dana," in tch[0]["body"])
    check(f"trigger {trig} signature carries the sender", "Sam Reed" in tch[0]["body"])
    check(f"trigger {trig} has an opt-out line", "STOP" in tch[0]["body"])
check("all four triggers produce different openers", len({bodies[t][:400] for t in bodies}) == 4)
check("newborn copy cites the prior footprint", "100" in bodies[pg.TRIGGER_A])
check("linkedin note under 300 chars",
      all(len(t["body"]) <= 300 for t in seq.build_sequence(targets.iloc[0], meta["show_name"], None, "Las Vegas",
                                                            {}, seq.DEFAULT_CADENCE, date(2026, 9, 14))
          if t["channel"] == seq.CH_LINKEDIN))

print("venue branch")
r = targets.iloc[0].copy()
vegas = "\n".join(t["body"] for t in seq.build_sequence(r, "NAB Show", date(2027, 4, 20), "Las Vegas", {},
                                                        seq.DEFAULT_CADENCE, date(2026, 9, 14)))
chi = "\n".join(t["body"] for t in seq.build_sequence(r, "IMTS", date(2027, 4, 20), "Chicago", {},
                                                      seq.DEFAULT_CADENCE, date(2026, 9, 14)))
check("vegas gets the home-turf math", "Inbound freight: zero" in vegas)
check("other cities get the travel math", "shipped show-ready to Chicago" in chi)

print("sequence_all + exports")
seqs = seq.sequence_all(targets, meta["show_name"], date(2027, 4, 20), "Las Vegas",
                        {"name": "Sam Reed", "title": "AE"}, seq.DEFAULT_CADENCE, per_day=3)
check("one sequence per row", len(seqs) == len(targets))
sched = seq.schedule_frame(seqs)
check("schedule rows = rows x touches", len(sched) == len(targets) * 5, f"{len(sched)}")
check("schedule sorted by date", list(sched["send_date"]) == sorted(sched["send_date"]))
vol = seq.daily_volume(sched)
check("daily volume totals match", int(vol["total"].sum()) == len(sched))
exp = seq.build_sequence_export(seqs, meta["show_name"])
check("export has one row per contact", len(exp) == len(targets))
for col in pg.EXPORT_COLUMNS:
    check(f"export keeps v1 column {col}", col in exp.columns)
for i in range(1, 6):
    for suffix in ("channel", "send_date", "subject", "subject_b", "body"):
        check(f"export has touch_{i}_{suffix}", f"touch_{i}_{suffix}" in exp.columns)
check("export bodies are non-empty", (exp["touch_1_body"].str.len() > 200).all())
check("export send dates are ISO", exp["touch_5_send_date"].str.match(r"\d{4}-\d{2}-\d{2}").all())
csv = exp.to_csv(index=False)
check("export round-trips through CSV", len(pd.read_csv(pd.io.common.StringIO(csv))) == len(exp))
check("sequence_text renders", "TOUCH 1" in seq.sequence_text(seqs[0]["row"], seqs[0]["touches"]))

print("empty inputs")
check("sequence_all on empty frame", seq.sequence_all(pd.DataFrame(), "x", None, "Las Vegas", {},
                                                      seq.DEFAULT_CADENCE, 25) == [])
check("schedule_frame on empty", seq.schedule_frame([]).empty)
check("daily_volume on empty", seq.daily_volume(seq.schedule_frame([])).empty)
check("export on empty", seq.build_sequence_export([], "x").empty)

print()
if FAILS:
    print(f"{len(FAILS)} FAILURE(S):")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("all sequencer tests passed")
