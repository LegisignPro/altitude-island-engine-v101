"""Streamlit AppTest flow: demo extraction -> sequencer tab renders, exports build, guards fire."""
import sys, os
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")

from streamlit.testing.v1 import AppTest

FAILS = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        FAILS.append(f"{name}: {detail}")
        print(f"  FAIL  {name}  {detail}")


def texts(at):
    out = []
    for coll in (at.markdown, at.caption, at.info, at.warning, at.error, at.metric):
        for el in coll:
            out.append(str(getattr(el, "value", "")) + str(getattr(el, "label", "")))
    return "\n".join(out)


def boot(show_date, city="Las Vegas", sender_name="Sam Reed"):
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    check("app boots with no exceptions", not at.exception, str(at.exception))
    if show_date is not None:
        at.sidebar.date_input[0].set_value(show_date)
    at.sidebar.text_input(key=None) if False else None
    for ti in at.sidebar.text_input:
        if ti.label == "Show city":
            ti.set_value(city)
        if ti.label == "Your name":
            ti.set_value(sender_name)
    at.run()
    # "Run Extraction" with no URL falls back to the demo dataset
    at.sidebar.button[0].click().run()
    return at


print("boot + demo extraction")
at = boot(date.today() + timedelta(days=210))     # ~7 months out: prime window
check("no exception after extraction", not at.exception, str(at.exception))
blob = texts(at)
check("demo banner shown", "DEMO DATA" in blob)
check("sequencer tab rendered", "Multi-touch outreach sequencer" in blob)
check("prime phase detected", "RFP window open" in blob)
check("contacts sequenced metric present", any(m.label == "Contacts sequenced" for m in at.metric))
seq_metric = next(m for m in at.metric if m.label == "Contacts sequenced")
check("at least one contact sequenced", int(str(seq_metric.value).replace(",", "")) > 0, str(seq_metric.value))
touches = next(m for m in at.metric if m.label == "Total touches")
check("touches = contacts x 5", int(str(touches.value).replace(",", "")) ==
      int(str(seq_metric.value).replace(",", "")) * 5, f"{touches.value} vs {seq_metric.value}")
check("sender name warning gone once set", "[Your name]" not in blob)

print("preview widgets")
bodies = [ta for ta in at.text_area if ta.key and ta.key.startswith("body_")]
check("five touch bodies rendered", len(bodies) == 5, str(len(bodies)))
check("touch 1 body is a real email", "STOP" in bodies[0].value and len(bodies[0].value) > 400)
subjects = [ti for ti in at.text_input if ti.key and ti.key.startswith("subjA_")]
check("email touches have subjects", len(subjects) >= 3, str(len(subjects)))
check("no empty subject", all(s.value.strip() for s in subjects))

print("downloads")
dl_labels = [d.label for d in at.get("download_button")]
check("sequenced campaign CSV offered", any("sequenced campaign csv" in l.lower() for l in dl_labels),
      str(dl_labels))
check("send calendar CSV offered", any("send calendar" in l.lower() for l in dl_labels), str(dl_labels))
check("full sequence txt offered", any("full sequence" in l.lower() for l in dl_labels), str(dl_labels))

print("timing guard: show already passed")
at2 = boot(date.today() - timedelta(days=10))
check("no exception on past show", not at2.exception, str(at2.exception))
b2 = texts(at2)
check("past show flagged", "Show has passed" in b2)
check("sequence suppressed", not any(ta.key and ta.key.startswith("body_") for ta in at2.text_area))
ov = [cb for cb in at2.checkbox if cb.key == "seq_override"]
check("override offered", len(ov) == 1)
if ov:
    ov[0].set_value(True).run()
    check("override generates for review", any(ta.key and ta.key.startswith("body_") for ta in at2.text_area))
    check("override warns", "Timing guard overridden" in texts(at2))

print("timing guard: too close to the show")
at3 = boot(date.today() + timedelta(days=25))
check("closed phase flagged", "Too close to the show" in texts(at3))
check("no exception on closed show", not at3.exception, str(at3.exception))

print("no show date at all")
at4 = boot(None)
check("unknown phase handled", "No show date set" in texts(at4))
check("still sequences", any(ta.key and ta.key.startswith("body_") for ta in at4.text_area))
check("no exception", not at4.exception, str(at4.exception))

print("non-Vegas city switches the math")
at5 = boot(date.today() + timedelta(days=210), city="Chicago")
b5 = "\n".join(ta.value for ta in at5.text_area if ta.key and ta.key.startswith("body_"))
check("travel math used off-home-turf", "shipped show-ready to Chicago" in b5)
check("no exception", not at5.exception, str(at5.exception))

print("v1 tabs still intact")
b1 = texts(at)
for frag in ["Target islands", "Year-over-year footprint delta", "Home-field freight arbitrage",
             "Apollo firmographics and buyer contacts", "Pitch angles by trigger"]:
    check(f"v1 section still present: {frag}", frag in b1)

print()
if FAILS:
    print(f"{len(FAILS)} FAILURE(S):")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("all app tests passed")
