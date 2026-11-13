"""Glue between FollowThrough's chat handler and B's outputs/Q&A/chase.

route(text, user, meeting_id, decisions) -> str | None
Returns a plain-text reply, or None if the message is not one of these commands
(so main.py can carry on with its own logic). Text only: no file uploads needed.
"""
import re

from src.outputs import export, chart, qa
from src.chase import chase

_CHASE_REPLY = re.compile(r"^\s*([A-Za-z]+)\s*:\s*(.+)$")   # "priya: done"  (not "1: Arjun")
_QA_WORDS = re.compile(r"\b(open|tasks?|unassigned|pending|e-?mail|draft|who|what's|whats)\b", re.I)


def _block(s):
    return f"```\n{s}\n```"


def route(text, user=None, meeting_id=None, decisions=None):
    t = (text or "").strip()
    low = t.lower()
    if not t:
        return None

    if "csv" in low:
        return "Here is the CSV:\n" + _block(export.export_csv(meeting_id)["content"].strip())
    if "minutes" in low:
        return export.export_minutes(meeting_id, decisions)["content"]
    if "chart" in low or "workload" in low:
        return "Workload (open tasks per owner):\n" + _block(chart.chart_text(meeting_id))

    if re.search(r"\b(remind|chase)\b", low):
        rem = chase.due_reminders(demo=True)
        if not rem:
            return "Nothing to chase right now."
        return "\n".join(f"@{r['to'].title()}: {r['text']}" for r in rem)

    # "priya: done"  or just "done" from the owner themselves
    m = _CHASE_REPLY.match(t)
    who, body = (m.group(1), m.group(2)) if m else (user, t)
    line = chase.handle_reply(who, body)
    if line:
        return f"Marked done. Progress: {line}\n" + _block(chart.chart_text(meeting_id))

    if _QA_WORDS.search(low) or "?" in low:
        return qa.answer_question(t)
    return None
