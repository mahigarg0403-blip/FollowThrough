import datetime as dt
import json, os, re, time

from src.agent import cards
from src.agent.store_shim import load_tasks, update_task

# Task owner name -> real Nonilion display name of someone ONLINE in the office.
# Override on Render without code changes:  OWNER_HANDLES={"priya":"B's name","arjun":"C's name","mei":"Mahi Garg"}
OWNER_HANDLES = {"priya": "Mahi Garg", "arjun": "Mahi Garg", "mei": "Mahi Garg"}
if os.getenv("OWNER_HANDLES"):
    OWNER_HANDLES.update({k.lower(): v for k, v in json.loads(os.environ["OWNER_HANDLES"]).items()})

NUDGE_EVERY = int(os.getenv("NUDGE_EVERY", "3600"))   # seconds between reminders per task
SNOOZE_FOR = int(os.getenv("SNOOZE_FOR", "14400"))
MAX_NUDGES = int(os.getenv("MAX_NUDGES", "3"))        # then escalate to the room

STATE = {}   # task id -> reminder bookkeeping

def _st(tid):
    return STATE.setdefault(tid, {"count": 0, "last": 0.0, "snooze": 0.0,
                                  "blocked": None, "board": None, "escalated": False})

def handle_for(owner):
    return OWNER_HANDLES.get((owner or "").lower(), owner or "")

def is_open(t):
    return bool(t.get("owner")) and t.get("status") not in ("done", "unassigned")

def mine(tasks, who):
    s = (who or "").strip().lower()
    first = s.split()[0] if s else ""
    return [t for t in tasks if is_open(t)
            and (handle_for(t["owner"]).lower() == s or t["owner"].lower() == first)]

# ---------- due dates ----------
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

def parse_due(text, today=None):
    today = today or dt.date.today()
    t = (text or "").strip().lower()
    if not t:
        return None
    if re.search(r"\b(today|eod|end of day|tonight)\b", t):
        return today
    if "tomorrow" in t:
        return today + dt.timedelta(days=1)
    for i, d in enumerate(DAYS):
        if d in t:
            return today + dt.timedelta(days=(i - today.weekday()) % 7)
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", t)
    if m:
        try:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.search(r"\bthe (\d{1,2})(?:st|nd|rd|th)?\b|\b(\d{1,2})(?:st|nd|rd|th)\b", t)
    if m:
        day = int(m.group(1) or m.group(2))
        for add in (0, 1):
            y, mo = today.year, today.month + add
            if mo > 12:
                y, mo = y + 1, 1
            try:
                d = dt.date(y, mo, day)
            except ValueError:
                continue
            if d >= today:
                return d
    return None

def due_state(t, today=None):
    today = today or dt.date.today()
    d = parse_due(t.get("due"), today)
    if d is None: return "nodate"
    if d < today: return "overdue"
    if d == today: return "today"
    return "later"

def due_tag(t, today=None):
    return {"overdue": " overdue", "today": "due today"}.get(due_state(t, today), "")

# ---------- message text ----------
def task_list(items, today=None):
    lines = []
    for i, t in items:
        extra = due_tag(t, today)
        if _st(t["id"])["blocked"]:
            extra += f"  🚧 blocked: {_st(t['id'])['blocked']}"
        lines.append(f"**{i}. {t['title']}**  ·  due {t.get('due') or 'no date'}{extra}")
    return "\n".join(lines)

def _owner_text(handle, items, head, tail):
    body = "\n\n".join(f"**{i}. {t['title']}**  ·  due {t.get('due') or 'no date'}{due_tag(t)}\n"
                       f"{cards.quote_line(t)}" for i, t in items)
    return f"{head}\n\n{body}\n\n{tail}"

def owner_dm_text(handle, items):
    first = handle.split()[0] if handle else "there"
    return _owner_text(handle, items, f"Hi {first}, FollowThrough here. From today's meeting you own:",
                       "I'll check in when things are due. Reply **done 1**, **snooze**, "
                       "**blocked: why**, or say **my tasks** anytime.")

def chase_text(handle, items, today=None):
    first = handle.split()[0] if handle else "there"
    return _owner_text(handle, items, f"Hi {first}, quick check-in from FollowThrough:",
                       "Reply **done 1** when it's finished, **snooze** for later, or **blocked: why** if you're stuck.")

# ---------- 1:1 replies ----------
DONE_RE = re.compile(r"^\s*(?:i(?:'m|\s*am|'ve|\s*have)?\s+)?(?:done|finished|completed|complete)\b|^\s*[✅✔]", re.I)
BLOCKED_RE = re.compile(r"^\s*(?:blocked|stuck)\b[:\-\s]*(.*)", re.I | re.S)
SNOOZE_RE = re.compile(r"\b(snooze|later|remind me|not yet|tomorrow)\b", re.I)
LIST_RE = re.compile(r"\b(my tasks|what'?s open|what do i have|open tasks|mine|status)\b", re.I)
GREET_RE = re.compile(r"^\s*(hi|hello|hey|help)\b", re.I)
_STOP = {"done", "the", "and", "finished", "completed", "complete", "blocked", "stuck", "snooze", "task", "for"}

def pick_task(cands, text):
    m = re.search(r"\b(\d+)\b", text)
    if m and 1 <= int(m.group(1)) <= len(cands):
        return cands[int(m.group(1)) - 1]
    words = set(re.findall(r"[a-z]{3,}", text.lower())) - _STOP
    best, score = None, 0
    for t in cands:
        s = len(words & set(re.findall(r"[a-z]{3,}", t["title"].lower())))
        if s > score:
            best, score = t, s
    if best:
        return best
    return cands[0] if len(cands) == 1 else None

def handle_owner_message(sender, text):
    """Returns (reply_text or None, event or None, tasks affected)."""
    tasks = load_tasks()
    mine_ = mine(tasks, sender)
    items = list(enumerate(mine_, 1))
    low = (text or "").strip()
    if GREET_RE.match(low):
        return cards.HELP, None, []
    if DONE_RE.match(low):
        if not mine_:
            return "You have no open tasks from me right now", None, []
        picked = mine_ if re.search(r"\ball\b", low, re.I) else [pick_task(mine_, low)]
        if picked == [None]:
            return "Which one is done?\n\n" + task_list(items), None, []
        for t in picked:
            update_task(t["id"], status="done")
            t["status"] = "done"
            _st(t["id"])["blocked"] = None
        left = len(mine_) - len(picked)
        names = ", ".join(f"**{t['title']}**" for t in picked)
        return f"✅ Marked done: {names}. " + (f"{left} still open for you." if left else "That's everything. Nice work! 🎉"), "done", picked
    m = BLOCKED_RE.match(low)
    if m:
        reason = m.group(1).strip() or "no reason given"
        t = pick_task(mine_, low) if mine_ else None
        if not t:
            return "Which task are you blocked on?\n\n" + task_list(items), None, []
        _st(t["id"])["blocked"] = reason
        return f"🚧 Noted. I'll tell the team **{t['title']}** is blocked: {reason}", "blocked", [t]
    if SNOOZE_RE.search(low) and mine_:
        for t in mine_:
            _st(t["id"])["snooze"] = time.time() + SNOOZE_FOR
        return f"Okay, I'll check back in {SNOOZE_FOR // 3600} hour(s).", "snoozed", mine_
    if LIST_RE.search(low):
        if not mine_:
            return "You have no open tasks from me", None, []
        return f"**Your open tasks ({len(mine_)})**\n\n{task_list(items)}", None, []
    return None, None, []

# ---------- chasing ----------
def _bump(st, t, now, notes):
    st["count"] += 1
    st["last"] = now
    if st["count"] >= MAX_NUDGES and not st["escalated"]:
        st["escalated"] = True
        notes.append(f"⚠️ **{t['owner']}** hasn't closed **{t['title']}** after "
                     f"{st['count']} reminders. Someone may need to step in.")

async def _remind_in_room(n, handle, items, now, notes):
    """DM not possible (guest / offline / error): @mention in the room instead."""
    lines = []
    for i, t in items:
        when = due_state(t)
        flag = " · **overdue**" if when == "overdue" else " · **due today**" if when == "today" else ""
        lines.append(f"**{t['title']}** · {t['owner']} · due {t.get('due') or 'no date'}{flag}\n"
                     f"Reply `{t['owner']}: done` when it's finished.")
    await n.post(f"**{handle}**, I couldn't DM you, so I'm reminding you here:\n\n" + "\n\n".join(lines))    
    for _, t in items:
        _bump(_st(t["id"]), t, now, notes)
    notes.append(f"• couldn't DM **{handle}** ({n.last_error or 'not reachable'}), so I reminded them in the room")

async def chase_cycle(n, tasks, force=False):
    """DM owners about due tasks; fall back to a room @mention if the DM fails.
    Returns (dms_sent, notes_for_the_room)."""
    now, today = time.time(), dt.date.today()
    online = {x.lower() for x in (n.online or [])}
    groups, notes, sent = {}, [], 0
    for t in tasks:
        if not is_open(t):
            continue
        st = _st(t["id"])
        if not force:
            if due_state(t, today) not in ("overdue", "today"):
                continue
            if now < st["snooze"] or now - st["last"] < NUDGE_EVERY:
                continue
        groups.setdefault(handle_for(t["owner"]), []).append(t)
    for handle, due_items in groups.items():
        allmine = mine(tasks, handle)
        items = [(allmine.index(t) + 1, t) for t in due_items if t in allmine]
        if not items:
            continue
        reachable = not online or handle.lower() in online
        if reachable and await n.dm(handle, chase_text(handle, items, today)):
            sent += 1
            for _, t in items:
                _bump(_st(t["id"]), t, now, notes)
        else:
            await _remind_in_room(n, handle, items, now, notes)
    return sent, notes

async def send_intro_dms(n, tasks):
    """After a meeting: DM each owner their own task list. Returns handles we couldn't reach."""
    failed, online = [], {x.lower() for x in (n.online or [])}
    for h in sorted({handle_for(t["owner"]) for t in tasks if is_open(t)}):
        if online and h.lower() not in online:
            failed.append(h)
            continue
        items = list(enumerate(mine(tasks, h), 1))
        if not await n.dm(h, owner_dm_text(h, items)):
            failed.append(h)
    return failed

# ---------- optional: mirror tasks onto Nonilion's own task board ----------
async def mirror_new(n, tasks):
    for t in tasks:
        st = _st(t["id"])
        if not is_open(t) or st["board"]:
            continue
        d = parse_due(t.get("due"))
        st["board"] = await n.board_create(f"{t['title']} (owner: {t['owner']})", d.isoformat() if d else None)

async def mirror_done(n, t):
    bid = _st(t["id"])["board"]
    if bid:
        await n.board_done(bid)