import asyncio, hashlib, json, os, time
import httpx
from src.agent.nonilion import run_forever, BOT_NAME
from src.agent.extract import extract_tasks
from src.agent.ask import format_results, question_text, parse_answers
from src.agent.store_shim import save_tasks, update_task

ASK_TIMEOUT = int(os.getenv("ASK_TIMEOUT", "30"))
TRANSCRIPT_EXT = (".txt", ".md")

class State:
    seen = set()
    started = False
    pending = None      # {"tasks": [...], "deadline": float}

S = State()

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

async def on_transcript(n, msg, text):
    meeting_id = f"m{int(time.time())}"
    await n.post("Got the transcript. Reading it now...", reply_to=msg["id"])
    decisions, tasks = await asyncio.to_thread(extract_cached, text, meeting_id)
    save_tasks(meeting_id, tasks)
    await n.post(format_results(decisions, tasks))
    missing = [t for t in tasks if not t["owner"]]
    if missing:
        S.pending = {"tasks": missing, "deadline": time.time() + ASK_TIMEOUT}
        await n.post(question_text(missing, ASK_TIMEOUT))

async def answer_pending(n, msg):
    missing = S.pending["tasks"]
    found = parse_answers(msg.get("text", ""), missing)
    if not found:
        return False
    lines = []
    for i, owner in found.items():
        t = missing[i - 1]
        t["owner"], t["status"] = owner, "confirmed"
        update_task(t["id"], owner=owner, status="confirmed")
        lines.append(f"• {t['title']} → {owner}")
    S.pending["tasks"] = [t for t in missing if not t["owner"]]
    await n.post("Assigned:\n" + "\n".join(lines), reply_to=msg["id"])
    if not S.pending["tasks"]:
        S.pending = None
    return True

async def check_timeout(n):
    if S.pending and time.time() > S.pending["deadline"]:
        left = S.pending["tasks"]
        for t in left:
            t["status"] = "unassigned"
            update_task(t["id"], status="unassigned")
        await n.post("No answer, so I'm marking these UNASSIGNED instead of guessing:\n"
                     + "\n".join(f"• {t['title']}" for t in left))
        S.pending = None

async def on_command(n, msg):
    # TODO (A, later): wire B's functions here, one branch each:
    #   "csv"/"minutes" -> n.post(file={...}) ; "chart" -> n.post(media_urls=[...])
    #   "open for <name>" -> answer_question ; "remind" -> run_reminders
    await n.post("Drop a .txt transcript in this chat and I'll pull out the tasks.",
                 reply_to=msg["id"])

async def process(n, msg):
    if msg.get("byAgent") or msg.get("from") == BOT_NAME:
        return
    for m in msg.get("media", []):
        if m.get("kind") == "file" and m["name"].lower().endswith(TRANSCRIPT_EXT):
            return await on_transcript(n, msg, await fetch_text(m["url"]))
    if S.pending and await answer_pending(n, msg):
        return
    if msg.get("mentionsYou"):
        await on_command(n, msg)

async def handler(n):
    while True:
        await n.listen(10)                      # wakes early when something happens
        msgs = await n.read_chat(15)
        if not S.started:                       # ignore history on first start
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
                raise                           # connection problem: reconnect and retry
            except Exception as e:
                import traceback; traceback.print_exc()
                await n.post("Sorry, I hit an error reading that. Please try again.")
            S.seen.add(m["id"])
        await check_timeout(n)

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