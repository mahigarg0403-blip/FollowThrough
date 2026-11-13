import asyncio, hashlib, json, os, re, time, traceback
import httpx
from src.agent.nonilion import run_forever, BOT_NAME
from src.agent.extract import extract_tasks
from src.agent.ask import parse_answers
from src.agent import cards, tracker
from src.agent.store_shim import save_tasks, load_tasks, update_task
from src import store
from src.outputs.export import export_csv, export_minutes
from src.agent.commands import route
import base64
from collections import Counter

import matplotlib
matplotlib.use("Agg")
import inspect
from src.outputs import chart

ASK_TIMEOUT = int(os.getenv("ASK_TIMEOUT", "30"))
AUTO_CHASE = os.getenv("AUTO_CHASE", "0") == "1"
MIRROR = os.getenv("MIRROR_TO_BOARD", "0") == "1"
TRANSCRIPT_EXT = (".txt", ".md")
CHASE_REPLY = re.compile(r"^\s*([A-Za-z]+)\s*:\s*((?:done|finished|completed)\b.*)$", re.I)  # "priya: done"
DM_TYPES = {"message", "dm", "direct_message", "direct"}

class State:
    seen = set()
    started = False
    pending = None        # {"orig": [tasks], "deadline": float}
    meeting_id = None
    decisions = []
    last_chase = 0.0

S = State()

def current_tasks():
    return load_tasks(S.meeting_id) if S.meeting_id else []

def extract_cached(text, meeting_id):
    """Cache by transcript hash so a rate limit can never break the demo."""
    os.makedirs("data", exist_ok=True)
    path = f"data/cache_{hashlib.sha256(text.encode()).hexdigest()[:16]}.json"
    if os.path.exists(path):
        decisions, tasks = json.load(open(path))
    else:
        decisions, tasks = extract_tasks(text, meeting_id)
        json.dump([decisions, tasks], open(path, "w"))
    for i, t in enumerate(tasks, 1):
        t["id"], t["meeting_id"] = f"{meeting_id}-{i}", meeting_id
    return decisions, tasks

async def fetch_text(url):
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(url)
        r.raise_for_status()
        return r.text

def build_chart():
    """Fresh workload PNG path. Passes the meeting id only if make_chart accepts an argument."""
    fn = chart.make_chart
    return fn(S.meeting_id) if inspect.signature(fn).parameters else fn()

def text_chart(tasks):
    c = Counter()
    for t in tasks:
        if t["status"] == "done":
            continue
        o = t.get("owner")
        key = o.title() if o and t["status"] not in ("unassigned", "needs_owner") else "Unassigned"
        c[key] += 1
    if not c:
        return "All tasks are done 🎉"
    w = max(len(k) for k in c)
    rows = [f"{k.ljust(w)}  {'█' * v} {v}"
            for k, v in sorted(c.items(), key=lambda x: (x[0] == "Unassigned", -x[1]))]
    return "**Open tasks per owner**\n```\n" + "\n".join(rows) + "\n```"

from xml.sax.saxutils import escape

def svg_chart(tasks):
    c = Counter()
    for t in tasks:
        if t["status"] == "done":
            continue
        o = t.get("owner")
        key = o.title() if o and t["status"] not in ("unassigned", "needs_owner") else "Unassigned"
        c[key] += 1
    items = sorted(c.items(), key=lambda x: (x[0] == "Unassigned", -x[1]))
    if not items:
        items = [("All done", 0)]
    mx = max(v for _, v in items) or 1
    row_h, left, width = 48, 120, 560
    h = 70 + row_h * len(items)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{h}" viewBox="0 0 {width} {h}">',
           f'<rect width="{width}" height="{h}" rx="14" fill="#0f1419"/>',
           '<text x="24" y="38" font-family="Arial" font-size="16" font-weight="bold" fill="#e0a83c">OPEN TASKS PER OWNER</text>']
    for i, (name, v) in enumerate(items):
        y = 60 + i * row_h
        bw = max(6, int((width - left - 70) * v / mx)) if v else 0
        color = "#d9534f" if name == "Unassigned" else "#e0a83c"
        out.append(f'<text x="24" y="{y + 24}" font-family="Arial" font-size="15" fill="#cfd6dd">{escape(name)}</text>')
        out.append(f'<rect x="{left}" y="{y}" width="{bw}" height="32" rx="6" fill="{color}"/>')
        out.append(f'<text x="{left + bw + 10}" y="{y + 22}" font-family="Arial" font-size="15" font-weight="bold" fill="#ffffff">{v}</text>')
    out.append("</svg>")
    return "\n".join(out)


async def post_chart(n, reply_to=None, caption="Workload chart:"):
    tasks = current_tasks()
    await n.post(f"{caption}\n\n{text_chart(tasks)}", reply_to=reply_to)
    try:
        f = {"name": "workload_chart.svg", "content": svg_chart(tasks), "mime": "image/svg+xml"}
        if not await n.post("Chart image", file=f):
            print("[chart upload failed]", n.last_error, flush=True)
    except Exception:
        traceback.print_exc()
        
        await n.post("I couldn't draw the chart just now. Text version:\n\n"
                     + cards.workload_text(current_tasks()), reply_to=reply_to)
        
# ---------- meeting flow ----------
async def on_transcript(n, msg, text):
    meeting_id = f"m{int(time.time())}"
    await n.post("📥 Got the transcript. Reading it now…", reply_to=msg["id"])
    decisions, tasks = await asyncio.to_thread(extract_cached, text, meeting_id)
    p = store.store_path()          # fresh demo state: outputs only cover this meeting
    if p.exists():
        p.unlink()
    tracker.STATE.clear()
    save_tasks(meeting_id, tasks)
    S.meeting_id, S.decisions, S.pending = meeting_id, decisions, None
    await n.post(cards.results_message(decisions, tasks))
    missing = [t for t in tasks if not t["owner"]]
    if missing:
        S.pending = {"orig": missing, "deadline": time.time() + ASK_TIMEOUT}
        await n.post(cards.question_message(missing, ASK_TIMEOUT))
    else:
        await finalize(n)

async def answer_pending(n, msg):
    orig = S.pending["orig"]
    found = parse_answers(msg.get("text", ""), orig)     # numbers refer to the original question
    if not found:
        return False
    lines = []
    for i, owner in found.items():
        t = orig[i - 1]
        if t["owner"]:
            continue
        t["owner"], t["status"] = owner, "confirmed"
        update_task(t["id"], owner=owner, status="confirmed")
        lines.append(f"• **{t['title']}** → {owner}")
    if lines:
        await n.post("✅ **Assigned**\n" + "\n".join(lines), reply_to=msg["id"])
    if all(t["owner"] for t in orig):
        S.pending = None
        await finalize(n)
    return True

async def check_timeout(n):
    if S.pending and time.time() > S.pending["deadline"]:
        left = [t for t in S.pending["orig"] if not t["owner"]]
        for t in left:
            t["status"] = "unassigned"
            update_task(t["id"], status="unassigned")
        S.pending = None
        if left:
            await n.post(cards.unassigned_message(left))
        await finalize(n)

async def finalize(n):
    """Summary + report file + DM every owner their list."""
    tasks = current_tasks()
    await n.post(cards.summary_message(tasks, "I'm DMing each owner their list now. "
                 "Say **report**, **csv**, **minutes**, **status** or **chase now** anytime."))
    await n.post("📎 Full report (open in your browser):", file=cards.report_file(tasks, S.decisions))
    failed = await tracker.send_intro_dms(n, tasks)
    if failed:
        await n.post("ℹ️ Couldn't DM " + ", ".join(failed) + " (not in the office right now). "
                     "I'll try again at the next reminder.")
    if MIRROR:
        await tracker.mirror_new(n, tasks)

# ---------- owners: 1:1 replies and chasing ----------
async def handle_owner_text(n, sender, text, via):
    reply, event, affected = tracker.handle_owner_message(sender, text)
    if reply is None:
        return False
    if via == "dm":
        if not await n.reply(reply):
            await n.dm(sender, reply)
    else:
        await n.post(reply)
    if event == "done":
        if MIRROR:
            for t in affected:
                await tracker.mirror_done(n, t)
        tasks = current_tasks()
        await n.post(f"**Progress update:** {cards.progress_line(tasks)}")
        await post_chart(n)
    elif event == "blocked":
        t = affected[0]
        await n.post(f"**{t['title']}** ({t['owner']}) is blocked: {tracker.STATE[t['id']]['blocked']}")
    return True

async def do_chase(n, reply_to=None):
    tasks = current_tasks()
    if not tasks:
        return await n.post("No meeting loaded yet. Drop a transcript first.", reply_to=reply_to)
    sent, notes = await tracker.chase_cycle(n, tasks, force=True)
    head = f"Sent {sent} reminder DM(s)." if sent else "No DMs went out."
    await n.post("\n".join([head] + notes), reply_to=reply_to)

async def auto_chase(n):
    if not AUTO_CHASE or not S.meeting_id or S.pending:
        return
    if time.time() - S.last_chase < 60:
        return
    S.last_chase = time.time()
    sent, notes = await tracker.chase_cycle(n, current_tasks())
    if notes:
        await n.post("\n".join(notes))

async def on_event(n, ev):
    if ev.get("type") == "room_chat":
        return                                   # room chat is read through read_chat
    print("[event]", json.dumps(ev)[:300], flush=True)   # shows us what a 1:1 message looks like
    if not (ev.get("type") in DM_TYPES or ev.get("via") == "dm"):
        return
    sender, text = ev.get("from") or "someone", (ev.get("text") or "").strip()
    if not text:
        return
    if await handle_owner_text(n, sender, text, "dm"):
        return
    if re.search(r"\b(chase|remind)\b", text, re.I) and "me later" not in text.lower():
        return await do_chase(n)
    try:
        reply = route(text, sender, S.meeting_id, S.decisions)
    except Exception:
        traceback.print_exc()
        reply = None
    reply = reply or cards.HELP
    if not await n.reply(reply):
        await n.dm(sender, reply)

# ---------- room commands ----------
async def on_command(n, msg):
    text = msg.get("text", "") or ""
    low, mid, rid = text.lower(), S.meeting_id, msg["id"]
    if re.search(r"\b(online|who is here|members)\b", low):
        return await n.post("Online right now: " + (", ".join(n.online or []) or "nobody listed"),
                            reply_to=rid)
    if re.search(r"\b(chase|remind)", low):
        return await do_chase(n, rid)
    if "report" in low or "dashboard" in low:
        
        if not mid:
            return await n.post("No meeting loaded yet. Drop a transcript first.", reply_to=rid)
        return await n.post("📎 Full report (open in your browser):", reply_to=rid,
                            file=cards.report_file(current_tasks(), S.decisions))
    if re.search(r"\b(chart|graph|workload)\b", low):
        if not mid:
            return await n.post("No meeting loaded yet. Drop a transcript first.", reply_to=rid)
        return await post_chart(n, rid)
    if re.search(r"\b(status|progress|summary)\b", low):
        return await n.post(cards.summary_message(current_tasks()), reply_to=rid)
    try:
        if "csv" in low:
            return await n.post("Here is the CSV.", reply_to=rid, file=export_csv(mid))
        if "minutes" in low:
            return await n.post("Here are the minutes.", reply_to=rid, file=export_minutes(mid, S.decisions))
    except Exception:
        traceback.print_exc()
    try:
        reply = route(text, msg.get("from"), mid, S.decisions)
    except Exception:
        traceback.print_exc()
        reply = None
    await n.post(reply or "Drop a .txt transcript in this chat and I'll pull out the tasks.", reply_to=rid)

async def process(n, msg):
    if msg.get("byAgent") or msg.get("from") == BOT_NAME:
        return
    for m in msg.get("media", []):
        if m.get("kind") == "file" and m["name"].lower().endswith(TRANSCRIPT_EXT):
            return await on_transcript(n, msg, await fetch_text(m["url"]))
    if S.pending and await answer_pending(n, msg):
        return
    m = CHASE_REPLY.match(msg.get("text", "") or "")
    if m and await handle_owner_text(n, m.group(1), m.group(2), "room"):
        return
    if msg.get("mentionsYou"):
        await on_command(n, msg)

async def handler(n):
    while True:
        events = await n.listen(10)              # wakes early when something happens
        for ev in events:
            try:
                await on_event(n, ev)
            except (ExceptionGroup, httpx.TransportError):
                raise
            except Exception:
                traceback.print_exc()
        msgs = await n.read_chat(15)
        if not S.started:                        # ignore history on first start
            S.seen.update(m["id"] for m in msgs)
            S.started = True
            print("FollowThrough is ready.", flush=True)
            continue
        for m in msgs:
            if m["id"] in S.seen:
                continue
            try:
                await process(n, m)
            except (ExceptionGroup, httpx.TransportError):
                raise                            # connection problem: reconnect
            except Exception:
                traceback.print_exc()
                try:
                    await n.post("Sorry, I hit an error reading that. Please try again.")
                except Exception:
                    pass
            S.seen.add(m["id"])
        await check_timeout(n)
        await auto_chase(n)

async def serve_health():
    port = int(os.getenv("PORT", "10000"))

    async def handle(reader, writer):
        try:
            await reader.read(1024)
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 2\r\n\r\nok")
            await writer.drain()
        finally:
            writer.close()

    return await asyncio.start_server(handle, "0.0.0.0", port)

async def main():
    server = None
    if os.getenv("PORT"):          # Render sets PORT for web services
        server = await serve_health()
    await run_forever(handler)

if __name__ == "__main__":
    asyncio.run(main())