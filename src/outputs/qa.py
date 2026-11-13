"""Grounded Q&A. Answers only from stored tasks; no LLM, so it cannot invent."""
import re

from .. import store

FALLBACK = ("I can only answer from the stored tasks. Try \"what's open for <name>?\" "
            "or \"what's unassigned?\".")
_STOP = {"me", "us", "you", "everyone", "everybody", "the", "this", "that", "today", "now",
         "a", "an", "it", "them", "all", "we", "our", "my", "team", "week"}


def _fmt(t):
    due = t.get("due") or "No date"
    return f"{t['title']} (due {due})\n   \"{t['quote']}\""


def _list(tasks):
    return "\n".join(f"{i}. {_fmt(t)}" for i, t in enumerate(tasks, 1))


def _email_draft():
    tasks = [t for t in store.load_tasks() if store.is_open(t)]
    lines = ["I can't send email, but here's a draft you can edit and send:", "",
             "Subject: Follow-ups from our meeting", "", "Hi,", "",
             "Thanks for your time. Here is where we landed:"]
    for t in tasks:
        who = t["owner"].title() if t.get("owner") else "owner to be confirmed"
        when = f"due {t['due']}" if t.get("due") else "no due date yet"
        lines.append(f"- {t['title']}: {who}, {when}")
    if not tasks:
        lines.append("- (no open action items)")
    lines += ["", "Best regards"]
    return "\n".join(lines)


def answer_question(text: str) -> str:
    q = (text or "").strip().lower()
    if not q:
        return FALLBACK
    if re.search(r"\b(e-?mail|send|mail)\b", q):
        return _email_draft()

    tasks = store.load_tasks()
    openl = [t for t in tasks if store.is_open(t)]
    owners = sorted({t["owner"] for t in tasks if t.get("owner")})

    if re.search(r"\b(unassigned|no owner|unowned)\b", q):
        un = [t for t in openl if not t.get("owner")]
        return f"Unassigned ({len(un)}):\n{_list(un)}" if un else "Nothing is unassigned."

    named = [o for o in owners if re.search(rf"\b{re.escape(o)}\b", q)]
    if named:
        who = named[0]
        mine = [t for t in openl if t.get("owner") == who]
        if mine:
            return f"Open for {who} ({len(mine)}):\n{_list(mine)}"
        n_done = sum(1 for t in tasks if t.get("owner") == who)
        return f"{who} has no open tasks ({n_done} total, all done)."

    m = re.search(r"\b(?:for|does|is|has)\s+([a-z][\w'-]*)", q)
    if m and m.group(1) not in _STOP and re.search(r"\b(open|task|tasks|pending|todo|assigned|working)\b", q):
        return f"I don't have any tasks for {m.group(1)}."

    if re.search(r"\b(open|pending|outstanding|tasks?)\b", q):
        return f"Open tasks ({len(openl)}):\n{_list(openl)}" if openl else "No open tasks."
    return FALLBACK
