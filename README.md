# Altitude Exhibits — Island Lead Engine v1.01

Low-volume, high-intent island exhibitors (400 to 3,000 sq ft by default) from
MapYourShow facts and Apollo firmographics. No modelled revenue, no guessed
websites, no synthetic lead scores.

**v1.01 = v1 plus outreach sequencing.** Everything in v1 is unchanged. The new
piece is `sequencer.py` and a sixth tab that turns v1's single intro line into a
dated, multi-channel sequence per contact.

## Run

    pip install -r requirements.txt
    streamlit run app.py

Optional: put the Apollo master key in `.streamlit/secrets.toml` (locally) or
App settings > Secrets (Streamlit Community Cloud):

    APOLLO_API_KEY = "xxxxxxxx"

Without a key the sidebar defaults to **mock Apollo responses**: deterministic
placeholder firmographics labelled MOCK in every table and in the export.

## Files

| File | Purpose |
|---|---|
| `app.py` | Streamlit UI: sidebar, 6 tabs, metrics, tables, exports |
| `scraper.py` | MapYourShow JSON endpoints (halls, gallery, floor-plan geometry, detail-page websites) + demo fallback |
| `delta_engine.py` | Prior-year CSV join, sq-ft delta, `CRITICAL: NEWBORN ISLAND` flag |
| `freight.py` | HQ state -> freight arbitrage tag |
| `apollo.py` | Organisation enrichment (1 credit), people search (0 credits), new-hire flag, mock mode |
| `pitch_generator.py` | Trigger hierarchy A > B > C > D, intro lines, Instantly/Smartlead CSV |
| **`sequencer.py`** | **NEW: timing model, cadences, per-trigger touch copy, send calendar, sequenced campaign CSV** |
| `tests/` | Module tests + Streamlit AppTest flow (v1) and sequencer tests (v1.01) |

## Workflow

1. Sidebar: paste any URL on the show's `mapyourshow.com` host, set the sq-ft
   range, click **Run Extraction**. Pavilions, associations, "State of" and
   "Department" listings are removed.
2. **Tab 2**: upload last year's extraction. Companies that jumped from under
   200 sq ft to 400+ are flagged NEWBORN ISLAND.
3. **Tab 4**: run Apollo. Employee count, HQ and industry per company
   (>1,000 employees dropped); buyer contacts by title with months-in-role
   (< 6 months = NEW HIRE).
4. **Tab 3**: freight arbitrage by HQ region (needs Tab 4).
5. **Tab 5**: one trigger and pitch angle per company, preview, lead CSV export.
6. **Tab 6 (new)**: set the show date, show city and sender block in the
   sidebar, then generate the full sequence. Preview any contact's touches,
   download one touch, one sequence, the send calendar, or the whole campaign.

## Tab 6 — the outreach sequencer

The deployed app sent one generic arc to everybody: four emails at day
0 / +4 / +10 / +18. v1.01 keeps the idea and fixes the parts that do not
survive contact with a real list.

**1. The trigger drives every touch, not just the opener.** A newborn island
gets rigging, height limits and crate-count copy from touch 1 through the
breakup. A new hire gets the "second concept next to the incumbent's" arc. A
freight lead gets the shipping math. AOR friction gets fixed-price. Four
different sequences, chosen by the same A > B > C > D hierarchy as v1.

**2. Multi-channel.** Standard cadence is Email (day 0), LinkedIn connection
note (+3), Email with the cost math (+7), a call task with a script (+14),
Email breakup (+24). Five emails in a row from a cold domain is how a sending
domain gets burned. A LinkedIn note is capped and checked at 300 characters.

**3. Timing comes from the show date, not from today.**

| Months to show | Phase | What happens |
|---|---|---|
| > 9 | Opens later | First touch scheduled for 9 months out, not now |
| 5 – 9 | RFP window open | Send now — this is when custom builds are sourced |
| 2 – 5 | Late | Compressed cadence, leads with turnkey rentals |
| 0 – 2 | Too close | **Sequence suppressed.** A custom build cannot ship in that window |
| past | Show has passed | **Sequence suppressed.** Pull next year's directory |

Suppression can be overridden for review, and the override banners every export
so a review copy cannot be mistaken for a sendable one.

**4. No weekend sends.** Every touch date rolls forward off Saturday and Sunday.

**5. Paced starts.** First touches are staggered across business days at a
configurable rate (default 25/day) so a 300-lead list does not leave as one
blast. The send calendar shows the peak email volume per day before anything is
exported.

**6. Fact-safe merge.** Every merge field has a guarded fallback. Missing
contact name, booth number, hall, HQ state or prior-year footprint rewrites the
sentence rather than merging an empty value. No email ships with
"Hi , your None sq ft booth" — this is the failure mode that makes
personalisation actively worse than none.

**7. Two subject lines per email** for the sequencer to split-test.

**8. CAN-SPAM shape.** Every signature carries a physical postal address
(sidebar) and an opt-out line.

### Exports

| Download | Contents |
|---|---|
| Sequenced campaign CSV | One row per contact: all v1 lead columns plus `touch_N_channel`, `touch_N_send_date`, `touch_N_subject`, `touch_N_subject_b`, `touch_N_body`. Imports straight into Instantly or Smartlead — map each touch block to a step. |
| Send calendar CSV | One row per touch, in send order: date, channel, touch number, company, contact, subject. |
| Single sequence `.txt` | One contact's whole sequence, for pasting into a manual send. |
| Single touch `.txt` | One email/note/call script. |

Emails: Apollo people search never reveals addresses on the Free plan, so
`email` is usually blank. Let Instantly / Smartlead's finder fill it from name +
domain, or wire `apollo.reveal_email()` on a paid plan. Before sending: use a
separate sending domain, warm it for two to three weeks, and verify addresses —
unverified scraped addresses are the fastest way into a spam trap.

## Tests

    python tests/test_sequencer.py       # v1.01: timing, business days, pacing, fact-safe merge, exports
    python tests/test_app_sequencer.py   # v1.01: AppTest through tab 6, both timing guards, venue branch

`test_sequencer.py` (106 assertions) and `test_app_sequencer.py` (44) both pass
on Streamlit 1.63 / pandas 3.0. The v1 suites (`tests/test_modules.py`,
`tests/test_app.py`) live in the v1 folder and still apply unchanged — none of
the v1 modules were touched; copy them across if you want one test directory.
