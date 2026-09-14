"""
sequencer.py -- multi-touch outreach sequencing for the Island Lead Engine.

v1 produced ONE custom intro line per company. This module turns that single
line into a full, dated, multi-channel sequence and keeps the trigger angle
running through every touch.

What it adds over the single-sequence model in the deployed app
(4 emails at day 0 / +4 / +10 / +18, one generic arc for everybody):

 1. TRIGGER-AWARE ARC.  Each of the four triggers (A newborn island,
    B new hire, C freight / Vegas local, D AOR friction) gets its own
    subject lines and its own body for every touch, not just the opener.
 2. MULTI-CHANNEL.  Email + LinkedIn + a call task, because five emails in
    a row from an unknown domain is how a sending domain gets burned.
 3. SHOW-DATE TIMING.  Send dates are derived from the RFP window
    (custom builds are sourced 5-9 months out), not from "today". A show
    that is too close, or already over, suppresses the custom-build
    sequence instead of sending a wrongly-timed email.
 4. BUSINESS-DAY SEND DATES.  No touch ever lands on a Saturday or Sunday.
 5. DAILY SEND CAP.  First touches are paced across business days so a
    300-lead list does not leave as one blast.
 6. FACT-SAFE MERGE.  Every merge field has a guarded fallback. If the
    contact name, booth number, hall, HQ state or prior-year footprint is
    missing, the sentence is rewritten without it. No email ever ships with
    "Hi , your None sq ft booth".
 7. SUBJECT A/B.  Two subject lines per touch for the sequencer to split.
 8. FLAT CAMPAIGN CSV.  One row per contact with every touch's channel,
    send date, subject, subject_b and body as columns -- the shape
    Instantly and Smartlead import directly.

Every merge field is still an observed fact: MapYourShow geometry, the
uploaded prior-year CSV, or Apollo firmographics. Nothing is modelled.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

import pitch_generator as pg

# =============================================================================
# Sender / company constants
# =============================================================================

COMPANY_NAME = "Altitude Exhibits"
COMPANY_SITE = "altitudeexhibits.com"
HOME_CITY = "Las Vegas"

DEFAULT_SENDER = {
    "name": "",
    "title": "Account Executive",
    "phone": "",
    "email": "",
    "calendar": "",
    "postal": "Las Vegas, NV",   # CAN-SPAM requires a physical postal address
}

# =============================================================================
# Timing model: the RFP window
# =============================================================================

MONTHS_EARLY = 9.0    # above this, hold the first touch until 9 months out
MONTHS_PRIME = 5.0    # 5-9 months out: the buying window, send now
MONTHS_LATE = 2.0     # 2-5 months out: build may be committed, pitch rentals
DAYS_PER_MONTH = 30.44

PHASE_EARLY = "early"
PHASE_PRIME = "prime"
PHASE_LATE = "late"
PHASE_CLOSED = "closed"
PHASE_PAST = "past"
PHASE_UNKNOWN = "unknown"

PHASE_LABELS = {
    PHASE_EARLY: "Opens later",
    PHASE_PRIME: "RFP window open",
    PHASE_LATE: "Late - lead with rentals",
    PHASE_CLOSED: "Too close to the show",
    PHASE_PAST: "Show has passed",
    PHASE_UNKNOWN: "No show date set",
}


def outreach_timeline(show_date: date | None, today: date | None = None) -> dict:
    """Phase, first-touch date and whether a custom-build sequence should go out."""
    today = today or date.today()
    if not show_date:
        return {"phase": PHASE_UNKNOWN, "label": PHASE_LABELS[PHASE_UNKNOWN], "months_out": None,
                "days_out": None, "first_touch": next_business_day(today), "sendable": True,
                "reason": "No show date set: send dates start today and carry no timing hook."}

    days_out = (show_date - today).days
    months_out = days_out / DAYS_PER_MONTH

    if days_out < 0:
        return {"phase": PHASE_PAST, "label": PHASE_LABELS[PHASE_PAST], "months_out": months_out,
                "days_out": days_out, "first_touch": next_business_day(today), "sendable": False,
                "reason": "The show is over. Sequence suppressed: pull next year's directory instead."}
    if months_out < MONTHS_LATE:
        return {"phase": PHASE_CLOSED, "label": PHASE_LABELS[PHASE_CLOSED], "months_out": months_out,
                "days_out": days_out, "first_touch": next_business_day(today), "sendable": False,
                "reason": (f"Only {days_out} days to the floor. A custom build cannot be designed, fabricated and "
                           f"shipped in that window, so the custom sequence is suppressed. Run these leads as a "
                           f"rental / next-year list instead.")}
    if months_out > MONTHS_EARLY:
        start = next_business_day(show_date - timedelta(days=int(MONTHS_EARLY * DAYS_PER_MONTH)))
        return {"phase": PHASE_EARLY, "label": PHASE_LABELS[PHASE_EARLY], "months_out": months_out,
                "days_out": days_out, "first_touch": start, "sendable": True,
                "reason": (f"{months_out:.1f} months out. Budgets are not set yet: the first touch is scheduled for "
                           f"{start:%b %d, %Y}, nine months before the show.")}
    if months_out >= MONTHS_PRIME:
        return {"phase": PHASE_PRIME, "label": PHASE_LABELS[PHASE_PRIME], "months_out": months_out,
                "days_out": days_out, "first_touch": next_business_day(today), "sendable": True,
                "reason": f"{months_out:.1f} months out: inside the 5-9 month window where custom builds are sourced."}
    return {"phase": PHASE_LATE, "label": PHASE_LABELS[PHASE_LATE], "months_out": months_out,
            "days_out": days_out, "first_touch": next_business_day(today), "sendable": True,
            "reason": (f"{months_out:.1f} months out. Most builds are committed by now, so the sequence leads with "
                       f"turnkey rentals and a takeover offer rather than a ground-up custom build.")}


# =============================================================================
# Business-day scheduling
# =============================================================================

def next_business_day(d: date) -> date:
    while d.weekday() >= 5:          # 5 = Saturday, 6 = Sunday
        d += timedelta(days=1)
    return d


def send_date(start: date, offset_days: int) -> date:
    """Offset in calendar days, then rolled forward off the weekend."""
    return next_business_day(start + timedelta(days=offset_days))


def pace_start_dates(n: int, first_touch: date, per_day: int) -> list[date]:
    """
    Stagger first touches across business days so a big list does not leave as
    one blast. Returns one start date per lead, in the order the leads are given
    (callers pass them already sorted by trigger priority).
    """
    per_day = max(1, int(per_day))
    out: list[date] = []
    day = next_business_day(first_touch)
    for i in range(n):
        if i and i % per_day == 0:
            day = next_business_day(day + timedelta(days=1))
        out.append(day)
    return out


# =============================================================================
# Cadences
# =============================================================================

CH_EMAIL = "Email"
CH_LINKEDIN = "LinkedIn"
CH_CALL = "Call"

CADENCES: dict[str, list[dict]] = {
    "Standard - 5 touches / 24 days": [
        {"n": 1, "day": 0,  "channel": CH_EMAIL,    "kind": "open"},
        {"n": 2, "day": 3,  "channel": CH_LINKEDIN, "kind": "connect"},
        {"n": 3, "day": 7,  "channel": CH_EMAIL,    "kind": "math"},
        {"n": 4, "day": 14, "channel": CH_CALL,     "kind": "call"},
        {"n": 5, "day": 24, "channel": CH_EMAIL,    "kind": "close"},
    ],
    "Compressed - 4 touches / 12 days": [
        {"n": 1, "day": 0,  "channel": CH_EMAIL,    "kind": "open"},
        {"n": 2, "day": 2,  "channel": CH_LINKEDIN, "kind": "connect"},
        {"n": 3, "day": 5,  "channel": CH_EMAIL,    "kind": "math"},
        {"n": 4, "day": 12, "channel": CH_EMAIL,    "kind": "close"},
    ],
    "Email only - 4 touches / 18 days": [
        {"n": 1, "day": 0,  "channel": CH_EMAIL, "kind": "open"},
        {"n": 2, "day": 4,  "channel": CH_EMAIL, "kind": "bump"},
        {"n": 3, "day": 10, "channel": CH_EMAIL, "kind": "math"},
        {"n": 4, "day": 18, "channel": CH_EMAIL, "kind": "close"},
    ],
}
DEFAULT_CADENCE = "Standard - 5 touches / 24 days"


def cadence_for_phase(phase: str) -> str:
    """The late window has less runway, so it gets the compressed cadence by default."""
    return "Compressed - 4 touches / 12 days" if phase == PHASE_LATE else DEFAULT_CADENCE


# =============================================================================
# Fact-safe merge context
# =============================================================================

def _clean(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return "" if text.lower() in ("nan", "none", "n/a") else text


def _int_or_none(value):
    try:
        if value is None or pd.isna(value):
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _poss(name: str) -> str:
    """Possessive that does not produce \"Technologies's\"."""
    name = (name or "").strip()
    return name + ("'" if name.endswith("s") else "'s")


def build_context(row: pd.Series, show_name: str, show_date: date | None,
                  venue_city: str, sender: dict) -> dict:
    """Every merge field, already guarded. Missing facts come back as empty strings."""
    sqft = _int_or_none(row.get("sqft")) or 0
    first = _clean(row.get("first_name"))
    company = _clean(row.get("exhibitor_name")) or "your team"
    booth = _clean(row.get("booth_number"))
    hall = _clean(row.get("hall"))
    state = _clean(row.get("hq_state")) or _clean(row.get("hq_country"))
    city = _clean(row.get("hq_city"))
    title = _clean(row.get("contact_title"))
    prior = _int_or_none(row.get("prior_sqft"))
    venue_city = _clean(venue_city) or HOME_CITY
    is_home = HOME_CITY.lower() in venue_city.lower() or "vegas" in _clean(show_name).lower()

    sender = {**DEFAULT_SENDER, **(sender or {})}
    sig_lines = [
        _clean(sender["name"]) or "[Your name]",
        f"{_clean(sender['title']) or 'Account Executive'}, {COMPANY_NAME}",
        COMPANY_SITE,
    ]
    if _clean(sender["phone"]):
        sig_lines.append(_clean(sender["phone"]))
    if _clean(sender["calendar"]):
        sig_lines.append(_clean(sender["calendar"]))
    sig_lines.append(_clean(sender["postal"]) or "Las Vegas, NV")
    sig_lines.append("Reply STOP and I will close the file and not contact you again.")

    return {
        "company": company,
        "first": first,
        "greet": f"Hi {first}," if first else f"Hi {company} team,",
        "sqft": sqft,
        "sqft_txt": f"{sqft:,} sq ft" if sqft else "island footprint",
        "dims": pg.dims_label(row.get("width"), row.get("length"), sqft),
        "booth": booth,
        "booth_txt": f", Booth {booth}" if booth else "",
        "hall_txt": f" in {hall}" if hall else "",
        "show": _clean(show_name) or "the show",
        "show_month": f"{show_date:%B}" if show_date else "",
        "show_when": f" in {show_date:%B %Y}" if show_date else "",
        "state": state,
        "origin_txt": f" from {city + ', ' + state if city and state else (state or city)}" if (state or city) else "",
        "title": title,
        "title_txt": title or "the role",
        "prior": prior,
        "venue_city": venue_city,
        "is_home": is_home,
        "freight_tag": _clean(row.get("freight_tag")),
        "signature": "\n".join(sig_lines),
        "sender_first": (_clean(sender["name"]).split(" ")[0] if _clean(sender["name"]) else "we"),
    }


# =============================================================================
# Copy: subjects and bodies, by trigger and touch kind
# =============================================================================

def _subjects(trigger: str, kind: str, c: dict) -> tuple[str, str]:
    show, company, dims = c["show"], c["company"], c["dims"]
    booth = f" ({c['booth']})" if c["booth"] else ""
    if kind == "open":
        if trigger == pg.TRIGGER_A:
            return (f"{_poss(company)} first island at {show}", f"{dims} at {show}{booth} - the rigging question")
        if trigger == pg.TRIGGER_B:
            return (f"Your first {show} booth", f"{company} + {show}: a second concept, no obligation")
        if trigger == pg.TRIGGER_C:
            return (f"{_poss(company)} {dims} and the freight on it", f"Building {show} locally instead of shipping it")
        return (f"{dims} at {show} - fixed price", f"{company} at {show}{booth}")
    if kind in ("connect",):
        return (f"{show} exhibitor - {COMPANY_NAME}", f"{company} at {show}")
    if kind == "bump":
        return (f"Re: {dims} at {show}", f"Following up - {show}")
    if kind == "math":
        if c["is_home"]:
            return (f"The {HOME_CITY} math on a {dims}", f"What the {dims} actually costs to land")
        return (f"The multi-show math on a {dims}", f"One build, the whole {show_year(c)} calendar")
    if kind == "call":
        return (f"15 minutes on {show}?", f"{company} / {COMPANY_NAME} - quick call")
    return (f"Closing the loop on {show}", f"Last note on the {dims}")


def show_year(c: dict) -> str:
    return c["show_when"].strip().split(" ")[-1] if c["show_when"] else "next"


def _offer_line(trigger: str, c: dict) -> str:
    if trigger == pg.TRIGGER_A:
        return (f"Happy to send a free structural sketch of the {c['dims']}: hanging sign clearance, rigging points "
                f"and crate count, so you can see what the hall will and will not allow before you commit to a design.")
    if trigger == pg.TRIGGER_B:
        return (f"Happy to put a free 3D concept of the {c['dims']} next to whatever is already on the table. "
                f"No pitch attached - if the incumbent design is better, use theirs.")
    if trigger == pg.TRIGGER_C:
        return (f"Happy to send a free side-by-side on the {c['dims']}: ship-it-in versus build-and-store-it-here, "
                f"with the freight, drayage and I&D lines broken out.")
    return (f"Happy to send a free fixed-price scope for the {c['dims']}: one number, design included, "
            f"with the post-show change-order line written out of it.")


def _open_body(trigger: str, c: dict, timeline: dict) -> str:
    """Touch 1. The v1 intro line, expanded into a full email with the timing hook and the offer."""
    hook = _timing_hook(c, timeline)
    parts = [c["greet"], ""]

    if trigger == pg.TRIGGER_A:
        prior_txt = (f"up from {c['prior']:,} sq ft last year " if c["prior"] else "")
        parts.append(f"{c['company']} is on the {c['show']} floor plan with a {c['dims']} island "
                     f"({c['sqft_txt']}){c['booth_txt']}{c['hall_txt']}, {prior_txt}- so this is a real step up.")
        parts.append("")
        parts.append("The first island is where the rules change: hall height limits, hanging-sign approval, "
                     "rigging quotes that arrive late, and drayage billed per crate rather than per booth. "
                     "Most of the cost surprises on a first island are decided at design stage, not on site.")
    elif trigger == pg.TRIGGER_B:
        role = f" into {c['title']}" if c["title"] else ""
        parts.append(f"Congratulations on the move{role} at {c['company']}. The {c['dims']} at {c['show']}"
                     f"{c['booth_txt']} is the first floor plan with your name on it.")
        parts.append("")
        parts.append("If the incumbent agency is preparing to roll out last year's design with a new graphic "
                     "package, that is the easy version of this. It is also the version nobody remembers.")
    elif trigger == pg.TRIGGER_C:
        if c["freight_tag"] and "Local" in c["freight_tag"]:
            parts.append(f"{c['company']} and {COMPANY_NAME} are both {HOME_CITY} companies, and you have a "
                         f"{c['dims']} ({c['sqft_txt']}) at {c['show']}{c['booth_txt']}.")
            parts.append("")
            parts.append(f"An exhibit built and stored a few miles from the hall has no inbound freight, no "
                         f"round-trip drayage on the return leg, and the crew that fabricated it does the install.")
        else:
            parts.append(f"Noticed {c['company']} is bringing a {c['dims']} ({c['sqft_txt']}) into {c['show']}"
                         f"{c['booth_txt']}{c['origin_txt']}.")
            parts.append("")
            parts.append(f"An island that size ships in several crates. Cross-country freight, round-trip drayage "
                         f"and travel for an out-of-town I&D crew are usually the three biggest lines on the invoice "
                         f"that have nothing to do with the booth itself.")
    else:
        parts.append(f"{_poss(c['company'])} {c['dims']} ({c['sqft_txt']}) at {c['show']}{c['booth_txt']} is right at the "
                     f"footprint where agency change orders start showing up after the show closes.")
        parts.append("")
        parts.append("The pattern is consistent: a clean quote up front, then post-show reconciliation with "
                     "labour overages, a drayage markup and design revisions billed hourly.")

    parts.append("")
    if hook:
        parts.append(hook)
        parts.append("")
    parts.append(_offer_line(trigger, c))
    parts.append("")
    parts.append(f"{COMPANY_NAME} designs, fabricates, installs and dismantles out of {HOME_CITY}"
                 + (f", which is where {c['show']} is." if c["is_home"] else ", and ships show-ready anywhere.")
                 + f" Work samples: {COMPANY_SITE}.")
    parts.append("")
    parts.append(f"Worth 15 minutes before your {c['show']} design is locked?")
    parts.append("")
    parts.append(c["signature"])
    return "\n".join(parts)


def _timing_hook(c: dict, timeline: dict) -> str:
    phase = timeline["phase"]
    if phase == PHASE_PRIME:
        months = int(round(timeline["months_out"] or 0))
        return (f"You are roughly {months} months out, which is when the strong builds get locked in - "
                f"fabrication slots for {c['show_month'] or 'show month'} fill from the inside out.")
    if phase == PHASE_EARLY:
        months = int(round(timeline["months_out"] or 0))
        return (f"{c['show']} is still about {months} months away, so this is early on purpose: the design decisions "
                f"that control cost happen long before the build does.")
    if phase == PHASE_LATE:
        weeks = max(1, int((timeline["days_out"] or 0) // 7))
        return (f"With {c['show']} about {weeks} weeks out you may already have a build committed. If anything has "
                f"slipped, our turnkey rental inventory is built for exactly this window.")
    return ""


def _connect_body(trigger: str, c: dict) -> str:
    """LinkedIn connection note. Under 300 characters, which is the field limit."""
    if trigger == pg.TRIGGER_B:
        note = (f"Congrats on the new role. Saw {c['company']}'s {c['dims']} at {c['show']} - "
                f"we build islands in {HOME_CITY}. Happy to share a concept if it is useful.")
    elif trigger == pg.TRIGGER_A:
        note = (f"Saw {c['company']} stepping up to a {c['dims']} island at {c['show']}. We build islands in "
                f"{HOME_CITY}; happy to share what the hall allows on height and rigging.")
    else:
        note = (f"Saw {_poss(c['company'])} {c['dims']} at {c['show']}. We design and build islands in {HOME_CITY} - "
                f"sent you a note on the freight and drayage side.")
    return note[:297] + ("..." if len(note) > 297 else "")


def _bump_body(trigger: str, c: dict) -> str:
    return "\n".join([
        c["greet"], "",
        f"Short bump on the note about your {c['dims']} at {c['show']}.",
        "",
        f"If exhibits are not yours, who owns the {c['show']} build? Happy to go to them instead and leave you alone.",
        "", c["signature"],
    ])


def _math_body(trigger: str, c: dict) -> str:
    parts = [c["greet"], ""]
    if c["is_home"]:
        parts.append(f"The {HOME_CITY} math on a {c['sqft_txt']} island, roughly:")
        parts.append("")
        parts.append("- Inbound freight: zero. The exhibit is already in the city.")
        parts.append("- Drayage: one short move instead of a round trip from an out-of-state dock.")
        parts.append("- I&D: a local crew, no per-diem, no flights, no hotel block.")
        parts.append("- Between shows: it sits in our warehouse instead of paying storage somewhere else "
                     "and shipping back in.")
    else:
        parts.append(f"The multi-show math on a {c['sqft_txt']} island, roughly:")
        parts.append("")
        parts.append(f"- Built in {HOME_CITY}, shipped show-ready to {c['venue_city']}, so nothing is fabricated on site.")
        parts.append("- Designed to reconfigure, so the same structure covers a 20x20 and a 20x30 without a rebuild.")
        parts.append("- Stored here between shows and re-crated for the next one - one asset, whole calendar.")
    parts.append("")
    if c["prior"]:
        parts.append(f"Stepping from {c['prior']:,} sq ft to {c['sqft']:,} usually more than doubles the labour and "
                     f"drayage line, not just the structure. That is the part that gets under-budgeted.")
        parts.append("")
    parts.append(f"I can put a rough all-in number on your {c['dims']} - structure, graphics, freight, drayage, "
                 f"I&D - in about a day, from the floor plan alone. Want me to send it over?")
    parts.append("")
    parts.append(c["signature"])
    return "\n".join(parts)


def _call_body(trigger: str, c: dict) -> str:
    """A call task, not an email. This is the script the rep reads."""
    angle = pg.TRIGGERS[trigger]["pitch_angle"]
    who = c["first"] or "whoever owns trade shows"
    lines = [
        f"CALL TASK - {c['company']}",
        f"Ask for: {who}" + (f" ({c['title']})" if c["title"] else ""),
        f"Hook: {c['dims']} ({c['sqft_txt']}) at {c['show']}{c['booth_txt']}.",
        f"Angle: {angle}",
        "",
        "Opener: \"I sent a note last week about your island at " + c["show"] + ". I build exhibits in "
        + HOME_CITY + " - I am not going to pitch you on the phone, I just want to know who is handling the build "
        "and whether the design is already locked.\"",
        "",
        "If locked: ask what they wish had gone differently last time, and ask to be on the next RFP list.",
        "If not locked: offer the free " + ("structural sketch" if trigger == pg.TRIGGER_A else "fixed-price scope")
        + " and book 15 minutes.",
        "If voicemail: leave name, company, city, the booth reference, and say an email is in their inbox.",
    ]
    return "\n".join(lines)


def _close_body(trigger: str, c: dict) -> str:
    parts = [c["greet"], ""]
    parts.append(f"Last note from me on {c['show']} - I would rather close the file than keep landing in your inbox.")
    parts.append("")
    if trigger == pg.TRIGGER_A:
        parts.append(f"The offer stands either way: a free structural sketch of the {c['dims']} showing height, "
                     f"rigging points and crate count. It is useful even if you build it with someone else.")
    elif trigger == pg.TRIGGER_B:
        parts.append(f"The offer stands either way: a free 3D concept for the {c['dims']}, yours to keep, "
                     f"whoever ends up building it.")
    elif trigger == pg.TRIGGER_C:
        parts.append(f"The offer stands either way: the freight and drayage side-by-side on the {c['dims']}. "
                     f"Worth having before you approve the next exhibit invoice.")
    else:
        parts.append(f"The offer stands either way: a fixed-price scope for the {c['dims']}, so you have a second "
                     f"number to hold the current one against.")
    parts.append("")
    parts.append(f"If the timing is simply wrong, tell me which show is the right one and I will come back then.")
    parts.append("")
    parts.append(c["signature"])
    return "\n".join(parts)


BODY_BUILDERS = {
    "open": lambda trig, c, tl: _open_body(trig, c, tl),
    "connect": lambda trig, c, tl: _connect_body(trig, c),
    "bump": lambda trig, c, tl: _bump_body(trig, c),
    "math": lambda trig, c, tl: _math_body(trig, c),
    "call": lambda trig, c, tl: _call_body(trig, c),
    "close": lambda trig, c, tl: _close_body(trig, c),
}


# =============================================================================
# Sequence assembly
# =============================================================================

def build_sequence(row: pd.Series, show_name: str, show_date: date | None, venue_city: str,
                   sender: dict, cadence_name: str, start: date, timeline: dict | None = None) -> list[dict]:
    """The full dated sequence for one contact."""
    timeline = timeline or outreach_timeline(show_date)
    cadence = CADENCES.get(cadence_name) or CADENCES[DEFAULT_CADENCE]
    trigger = str(row.get("trigger") or pg.TRIGGER_D)
    if trigger not in pg.TRIGGERS:
        trigger = pg.TRIGGER_D
    c = build_context(row, show_name, show_date, venue_city, sender)

    touches = []
    for spec in cadence:
        subject, subject_b = _subjects(trigger, spec["kind"], c)
        body = BODY_BUILDERS[spec["kind"]](trigger, c, timeline)
        touches.append({
            "n": spec["n"],
            "day": spec["day"],
            "channel": spec["channel"],
            "kind": spec["kind"],
            "send_date": send_date(start, spec["day"]),
            "subject": subject if spec["channel"] == CH_EMAIL else "",
            "subject_b": subject_b if spec["channel"] == CH_EMAIL else "",
            "body": body,
        })
    return touches


def sequence_text(row: pd.Series, touches: list[dict]) -> str:
    """Whole sequence as one plain-text block, for the per-lead download."""
    head = [f"{row.get('exhibitor_name', '')} -- {row.get('trigger_badge', '')}",
            f"Booth {row.get('booth_number') or 'n/a'}, {_int_or_none(row.get('sqft')) or 0:,} sq ft",
            f"Contact: {_clean(row.get('contact_name')) or 'not found'} "
            f"{('(' + _clean(row.get('contact_title')) + ')') if _clean(row.get('contact_title')) else ''}".strip(),
            f"Email: {_clean(row.get('email')) or '(to be found by the sequencer)'}", ""]
    blocks = []
    for t in touches:
        header = f"--- TOUCH {t['n']} | {t['channel']} | {t['send_date']:%a %b %d, %Y} (day +{t['day']}) ---"
        subj = f"Subject A: {t['subject']}\nSubject B: {t['subject_b']}\n" if t["subject"] else ""
        blocks.append(f"{header}\n{subj}\n{t['body']}\n")
    return "\n".join(head) + "\n".join(blocks)


def sequence_all(df: pd.DataFrame, show_name: str, show_date: date | None, venue_city: str, sender: dict,
                 cadence_name: str, per_day: int, timeline: dict | None = None) -> list[dict]:
    """
    Sequence every row (already contact-level and sorted by trigger priority).
    Returns a list of {"row": Series, "touches": [...], "start": date}.
    """
    timeline = timeline or outreach_timeline(show_date)
    if df.empty:
        return []
    starts = pace_start_dates(len(df), timeline["first_touch"], per_day)
    out = []
    for (_, row), start in zip(df.iterrows(), starts):
        out.append({"row": row, "start": start,
                    "touches": build_sequence(row, show_name, show_date, venue_city, sender,
                                              cadence_name, start, timeline)})
    return out


# =============================================================================
# Exports
# =============================================================================

def schedule_frame(sequences: list[dict]) -> pd.DataFrame:
    """One row per touch, for the send calendar."""
    rows = []
    for item in sequences:
        r = item["row"]
        for t in item["touches"]:
            rows.append({
                "send_date": t["send_date"],
                "channel": t["channel"],
                "touch": t["n"],
                "exhibitor_name": _clean(r.get("exhibitor_name")),
                "contact_name": _clean(r.get("contact_name")),
                "contact_title": _clean(r.get("contact_title")),
                "trigger_badge": _clean(r.get("trigger_badge")),
                "subject": t["subject"],
                "email": _clean(r.get("email")),
            })
    if not rows:
        return pd.DataFrame(columns=["send_date", "channel", "touch", "exhibitor_name", "contact_name",
                                     "contact_title", "trigger_badge", "subject", "email"])
    return pd.DataFrame(rows).sort_values(["send_date", "touch", "exhibitor_name"]).reset_index(drop=True)


def daily_volume(schedule: pd.DataFrame) -> pd.DataFrame:
    """Sends per day per channel: the deliverability check before anything leaves."""
    if schedule.empty:
        return pd.DataFrame(columns=["send_date", "Email", "LinkedIn", "Call", "total"])
    piv = schedule.pivot_table(index="send_date", columns="channel", values="touch",
                               aggfunc="count", fill_value=0).reset_index()
    for ch in (CH_EMAIL, CH_LINKEDIN, CH_CALL):
        if ch not in piv.columns:
            piv[ch] = 0
    piv["total"] = piv[[CH_EMAIL, CH_LINKEDIN, CH_CALL]].sum(axis=1)
    return piv[["send_date", CH_EMAIL, CH_LINKEDIN, CH_CALL, "total"]]


def build_sequence_export(sequences: list[dict], show_name: str, max_touches: int | None = None) -> pd.DataFrame:
    """
    Flat campaign CSV: every v1 column, plus one block of columns per touch
    (channel, send date, subject, subject B, body). This is the shape Instantly
    and Smartlead import without any reshaping.
    """
    if not sequences:
        return pd.DataFrame(columns=pg.EXPORT_COLUMNS + ["sequence_start", "cadence_touches"])
    base = pg.build_export(pd.DataFrame([s["row"] for s in sequences]), show_name)
    n_touches = max_touches or max(len(s["touches"]) for s in sequences)
    extra: dict[str, list] = {"sequence_start": [], "cadence_touches": []}
    for i in range(1, n_touches + 1):
        for suffix in ("channel", "send_date", "subject", "subject_b", "body"):
            extra[f"touch_{i}_{suffix}"] = []
    for s in sequences:
        extra["sequence_start"].append(s["start"].isoformat())
        extra["cadence_touches"].append(len(s["touches"]))
        by_n = {t["n"]: t for t in s["touches"]}
        for i in range(1, n_touches + 1):
            t = by_n.get(i)
            extra[f"touch_{i}_channel"].append(t["channel"] if t else "")
            extra[f"touch_{i}_send_date"].append(t["send_date"].isoformat() if t else "")
            extra[f"touch_{i}_subject"].append(t["subject"] if t else "")
            extra[f"touch_{i}_subject_b"].append(t["subject_b"] if t else "")
            extra[f"touch_{i}_body"].append(t["body"] if t else "")
    out = base.reset_index(drop=True)
    for col, values in extra.items():
        out[col] = values
    return out
