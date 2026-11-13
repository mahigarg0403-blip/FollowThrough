"""Run from repo root: python tests/check_golden.py  (uses a throwaway store)."""
import json, os, sys, tempfile
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
tmp = tempfile.mkdtemp()
os.environ["FT_STORE"] = str(Path(tmp) / "tasks.json")

from src import store
from src.outputs import chart, export, qa
from src.chase import chase

transcript = (root / "data/sample_transcript.txt").read_text()
sample = json.loads((root / "data/sample_tasks.json").read_text())
for t in sample:
    assert t["quote"] in transcript, f"quote not verbatim: {t['quote']}"
    assert t["owner"] is None or t["owner"].islower()
store.save_tasks("demo-meeting", sample)

print("== chart_text"); print(chart.chart_text())
lines = chart.chart_text().splitlines()
assert lines[:4] == ["priya      ███ 3", "arjun      ██ 2", "mei        ██ 2", "unassigned █ 1"], lines
print("\n== csv"); c = export.export_csv(); print(c["content"]); assert c["name"] == "action_items.csv"
print("== minutes"); m = export.export_minutes(decisions=["Three pricing tiers, no custom plans at launch"]); print(m["content"])
print("== qa: open for priya"); print(qa.answer_question("What's open for Priya?"))
print("\n== qa: unknown"); print(qa.answer_question("what's open for Zoe?"))
assert "don't have any tasks for zoe" in qa.answer_question("what's open for Zoe?")
print("\n== qa: email"); print(qa.answer_question("Email this to the client"))
assert qa.answer_question("what's the weather").startswith("I can only answer")
print("\n== reminders (demo)"); r = chase.due_reminders(demo=True, owner="priya"); print(r)
assert r == [{"to": "priya", "text": "Hi priya, 'Send pricing deck' is due Friday. Done?"}] or "Send pricing deck" in r[0]["text"]
assert chase.handle_reply("Priya", "not done yet") is None
assert chase.handle_reply("Priya", "thanks!") is None
print("\n== reply"); line = chase.handle_reply("Priya", "Done"); print(line)
assert line == "1 of 8 complete, 7 open, 1 unassigned", line
assert next(t for t in store.load_tasks() if t["id"] == "demo-meeting-t1")["status"] == "done"
print(chart.chart_text())
png = chart.make_chart(path=str(Path(tmp) / "w.png")); assert Path(png).stat().st_size > 1000
store.update_task("demo-meeting-t8", owner="Mei", status="confirmed")
assert store.tasks_for_owner("MEI")[-1]["title"].startswith("Follow up")
print("\nALL CHECKS PASSED")
