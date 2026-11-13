"""Chase: build reminder DMs and handle 'done' replies. Returns data only; never sends."""
import json
import re
from datetime import date

from .. import store
from ..outputs import chart

_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_DONE = re.compile(r"\b(done|finished|completed?|did it|sent it|shipped)\b", re.I)
_NEG = re.compile(r"\b(not|isn't|haven't|hasn't|never|almost|nearly|not yet)\b|n't\b", re.I)


def _state_path():
    return store.store_path().with_name("chase_state.json")


def _load_state():
    try:
        return json.loads(_state_path().read_text())
    except (OSError, ValueError):
        return {}


def _save_state(s):
    _state_path().write_text(json.dumps(s))


def _timing(due, today):
    """'today' | 'overdue' | None. Only trusts what the due string literally says."""
    if not due:
        return None
    d = due.strip().lower()
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", d)
    if m:
        try:
            dt = date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return None
        return "today" if dt == today else "overdue" if dt < today else None
    if re.search(r"\b(today|tonight|eod)\b", d):
        return "today"
    if d.startswith("next "):
        return None
    for name in _DAYS:
        if re.search(rf"\b{name}\b", d):
            return "today" if name == _DAYS[today.weekday()] else None
    return None


def due_reminders(demo=False, owner=None, today=None) -> list:
    """[{"to": "priya", "text": "..."}]. demo=True ignores dates and chases each owner's
    first open task, so the demo never depends on the real calendar."""
    today = today or date.today()
    seen_owner, out, state = set(), [], _load_state()
    for t in store.load_tasks():
        who = t.get("owner")
        if not who or t["status"] != "confirmed":
            continue
        if owner and who != owner.strip().lower():
            continue
        when = _timing(t.get("due"), today)
        if demo:
            if who in seen_owner:
                continue
            seen_owner.add(who)
            phrase = "is due today" if when == "today" else (
                f"is due {t['due']}" if t.get("due") else "is open")
        elif when == "today":
            phrase = "is due today"
        elif when == "overdue":
            phrase = f"was due {t['due']}"
        else:
            continue
        state[who] = t["id"]  # remember which task this owner was just asked about
        out.append({"to": who, "text": f"Hi {who}, '{t['title']}' {phrase}. Done?"})
    _save_state(state)
    return out


def progress_line(meeting_id=None) -> str:
    tasks = store.load_tasks(meeting_id)
    done = sum(t["status"] == "done" for t in tasks)
    unassigned = sum(t["status"] != "done" and not t.get("owner") for t in tasks)
    return f"{done} of {len(tasks)} complete, {len(tasks) - done} open, {unassigned} unassigned"


def handle_reply(user, text):
    """If `user` says they're done, mark their task done and return the progress line.
    Returns None for anything else (A should then ignore the message)."""
    if not text or not _DONE.search(text) or _NEG.search(text):
        return None
    who = str(user or "").strip().lower()
    names = {t["owner"] for t in store.load_tasks() if t.get("owner")}
    if who not in names:
        who = next((p for p in re.split(r"\W+", who) if p in names), None)
    if not who:
        return None
    mine = [t for t in store.load_tasks() if t.get("owner") == who and t["status"] != "done"]
    if not mine:
        return None
    state = _load_state()
    target = next((t for t in mine if t["id"] == state.get(who)), mine[0])
    store.update_task(target["id"], status="done")
    return progress_line()
