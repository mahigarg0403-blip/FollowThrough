"""Chase: build reminders, deliver them (DM first, channel fallback), handle 'done' replies."""
import json
import re
from datetime import date

from .. import store
from ..outputs import chart

_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_DONE = re.compile(r"\b(done|finished|completed?|did it|sent it|shipped)\b", re.I)
_NEG = re.compile(r"\b(not|isn't|haven't|hasn't|never|almost|nearly|not yet)\b|n't\b", re.I)

# owner (lowercase) -> Nonilion user id. Fill in for real members; anyone missing is
# treated like a guest and gets the channel fallback instead of a DM.
USER_IDS = {}  # e.g. {"priya": "u_123", "arjun": "u_456", "mei": "u_789"}


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
        # Any owned, not-yet-done task counts (covers owners assigned via the grouped question).
        if not who or t["status"] in ("done", "unassigned", "needs_owner"):
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


def _dm_failed(res):
    """Placeholder: adjust to whatever A's send_dm returns on failure."""
    return res is False or (isinstance(res, dict) and (res.get("error") or res.get("ok") is False))


def deliver(reminders, send_dm, post) -> str:
    """Send each reminder by DM; if that fails (guest, no account, API error), @mention
    the owner in the channel instead. Returns a one-line summary and never raises."""
    dm, channel = [], []
    for r in reminders:
        who, text = r["to"], r["text"]
        try:
            uid = USER_IDS.get(who)
            if USER_IDS and not uid:
                raise RuntimeError("no Nonilion account mapped")
            res = send_dm(uid or who, text)
            if _dm_failed(res):
                raise RuntimeError(res)
            dm.append(who)
        except Exception:
            post(f"@{who} {text}")
            channel.append(who)
    if not reminders:
        return "No reminders due right now."
    parts = []
    if dm:
        parts.append(f"DM'd {', '.join(dm)}")
    if channel:
        parts.append(f"couldn't DM {', '.join(channel)} (guest or no account), so I mentioned them here")
    return "Reminders: " + "; ".join(parts) + "."


def run_reminders(send_dm, post, demo=False, owner=None):
    """One call for the chat command: build, deliver, post the summary."""
    post(deliver(due_reminders(demo=demo, owner=owner), send_dm, post))


def progress_line(meeting_id=None) -> str:
    tasks = store.load_tasks(meeting_id)
    done = sum(t["status"] == "done" for t in tasks)
    unassigned = sum(t["status"] != "done" and not t.get("owner") for t in tasks)
    return f"{done} of {len(tasks)} complete, {len(tasks) - done} open, {unassigned} unassigned"


def handle_reply(user, text):
    """If `user` says they're done (in a DM or in the channel), mark their task done and
    return the progress line. Returns None for anything else (A should ignore it)."""
    if not text or not _DONE.search(text) or _NEG.search(text):
        return None
    who = str(user or "").strip().lower()
    names = {t["owner"] for t in store.load_tasks() if t.get("owner")}
    if who not in names:
        # also try reverse lookup from a Nonilion user id
        who = next((n for n, uid in USER_IDS.items() if uid == who), who)
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


def refresh_chart():
    """Path to a fresh workload chart PNG; A posts it right after the progress line."""
    return chart.make_chart()