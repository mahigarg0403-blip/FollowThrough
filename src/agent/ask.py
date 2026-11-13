import json, re
from src.agent.llm import ask_llm

SYS = ("You map a chat message to task assignments. Return ONLY JSON: "
       '{"assignments":[{"n":1,"owner":"name"}]}. Include an assignment ONLY if the '
       "message explicitly names a person for that numbered task. If unsure, return an empty list.")

def format_results(decisions, tasks):
    ok = [t for t in tasks if t["owner"]]
    missing = [t for t in tasks if not t["owner"]]
    lines = [f"I found {len(tasks)} task(s) and {len(decisions)} decision(s)."]
    if decisions:
        lines += ["", "Decisions:"] + [f"• {d}" for d in decisions]
    if ok:
        lines += ["", "Confirmed (owner and quote verified):"]
        for t in ok:
            lines.append(f"• {t['title']} | {t['owner']} | {t['due'] or 'no date given'}")
            lines.append(f"   “{t['quote']}”")
    if missing:
        lines += ["", f"{len(missing)} task(s) have no clear owner. I won't guess, so I'm asking below."]
    return "\n".join(lines)

def question_text(missing, timeout):
    lines = ["These tasks have no clear owner. Who should take each one?"]
    for i, t in enumerate(missing, 1):
        lines.append(f"{i}. {t['title']}")
    lines += ["", f"Reply like “1: Arjun”. Anything unanswered in {timeout} seconds is marked UNASSIGNED."]
    return "\n".join(lines)

def parse_answers(text, missing):
    found = {}
    for num, name in re.findall(r"(\d+)\s*[:=\-]\s*([A-Za-z]+)", text):
        i = int(num)
        if 1 <= i <= len(missing):
            found[i] = name.lower()
    if found:
        return found
    listing = "\n".join(f"{i}. {t['title']}" for i, t in enumerate(missing, 1))
    try:
        raw = ask_llm(SYS, f"Tasks:\n{listing}\n\nMessage: {text}")
        raw = re.sub(r"^```(?:json)?|```$", "", raw.strip()).strip()
        for a in json.loads(raw).get("assignments", []):
            i, owner = int(a["n"]), str(a["owner"]).strip().lower()
            if 1 <= i <= len(missing) and owner and owner in text.lower():
                found[i] = owner          # the name must really appear in the message
    except Exception:
        pass
    return found