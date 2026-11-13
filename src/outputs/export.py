"""CSV and markdown minutes. Each returns {"name", "content", "mime"}."""
import csv
import io

from .. import store

NO_OWNER = "UNASSIGNED"
NO_DATE = "No date"


def _owner(t):
    return t["owner"].title() if t.get("owner") else NO_OWNER


def _due(t):
    return t.get("due") or NO_DATE


def _safe_cell(v):
    v = "" if v is None else str(v)
    # stop spreadsheet formula injection from quoted speech
    return "'" + v if v[:1] in ("=", "+", "-", "@") else v


def export_csv(meeting_id=None) -> dict:
    tasks = store.load_tasks(meeting_id)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["id", "title", "owner", "due", "status", "quote", "meeting_id"])
    for t in tasks:
        w.writerow([_safe_cell(x) for x in (
            t["id"], t["title"], _owner(t), _due(t), t["status"], t["quote"], t["meeting_id"])])
    return {"name": "action_items.csv", "content": buf.getvalue(), "mime": "text/csv"}


def _cell(v):
    return str(v).replace("|", "\\|").replace("\n", " ")


def export_minutes(meeting_id=None, decisions=None) -> dict:
    """`decisions` is an optional list of strings from A's extraction."""
    tasks = store.load_tasks(meeting_id)
    done = sum(t["status"] == "done" for t in tasks)
    lines = ["# Meeting minutes", ""]
    if decisions:
        lines += ["## Decisions", ""] + [f"- {d}" for d in decisions] + [""]
    lines += [
        "## Action items", "",
        f"{len(tasks)} tasks: {done} done, {len(tasks) - done} open.", "",
        "| Task | Owner | Due | Status |",
        "|---|---|---|---|",
    ]
    for t in tasks:
        lines.append(f"| {_cell(t['title'])} | {_cell(_owner(t))} | {_cell(_due(t))} | {t['status']} |")
    lines += ["", "## Evidence (verbatim quotes)", ""]
    for t in tasks:
        lines.append(f"- **{t['title']}**: \"{t['quote']}\"")
    unowned = [t for t in tasks if not t.get("owner") and t["status"] != "done"]
    if unowned:
        lines += ["", "## Needs an owner", ""] + [f"- {t['title']}" for t in unowned]
    return {"name": "minutes.md", "content": "\n".join(lines) + "\n", "mime": "text/markdown"}
