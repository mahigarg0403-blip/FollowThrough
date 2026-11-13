import json, re
from src.agent.llm import ask_llm

PROMPT = """You extract decisions and action items from a meeting transcript.
Return ONLY valid JSON, no other text, in exactly this shape:
{"decisions": ["..."],
 "tasks": [{"title": "...", "owner": null, "due": null, "quote": "..."}]}

Rules:
- "quote" must be copied EXACTLY, word for word, from the transcript.
- "owner" is a person's first name, and only if the transcript explicitly
  makes that person responsible in or right next to the quote. Otherwise null.
- "due" only if a deadline is stated (keep the wording, e.g. "Friday"). Otherwise null.
- Never infer or guess an owner or a date. Use null.
- One task per commitment. Skip chit-chat."""

def _norm(s):
    return re.sub(r"\s+", " ", s).strip().lower()

def extract_tasks(transcript, meeting_id="m1"):
    text = ask_llm(PROMPT, transcript).strip()
    text = re.sub(r"^```(?:json)?|```$", "", text).strip()
    data = json.loads(text)

    lines = [_norm(l) for l in transcript.splitlines()]
    full = _norm(transcript)
    tasks = []
    for i, t in enumerate(data.get("tasks", []), 1):
        quote = _norm(t.get("quote") or "")
        owner = (t.get("owner") or "").strip()
        verified = bool(quote) and quote in full

        owner_ok = False
        if verified and owner:
            near = quote
            for j, line in enumerate(lines):
                if quote in line:
                    near += " " + line + " " + (lines[j - 1] if j else "")
                    break
            owner_ok = owner.lower() in near

        if not (verified and owner_ok):
            owner = None
        tasks.append({
            "id": f"{meeting_id}-{i}",
            "title": t["title"],
            "owner": owner.lower() if owner else None,
            "due": t.get("due") if verified else None,
            "quote": t["quote"] if verified else "(quote could not be verified)",
            "status": "confirmed" if owner else "needs_owner",
            "meeting_id": meeting_id,
        })
    return data.get("decisions", []), tasks

if __name__ == "__main__":
    text = open("data/sample_transcript.txt").read()
    decisions, tasks = extract_tasks(text)
    for t in tasks:
        print(t["owner"], "|", t["due"], "|", t["title"], "|", t["quote"])