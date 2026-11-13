import asyncio, json, os, traceback
import httpx
from dotenv import load_dotenv
from mcp import ClientSession

load_dotenv()
URL = "https://www.nonilion.com/mcp"
HEADERS = {"Authorization": f"Bearer {os.environ['NONILION_TOKEN']}"}
BOT_NAME = "FollowThrough"
_FAIL_STARTS = ("couldn", "could not", "can't", "cannot", "failed", "error",
                "unable", "no one", "nobody", "not ")

def _connect():
    try:
        from mcp.client.streamable_http import streamable_http_client
        http = httpx.AsyncClient(headers=HEADERS, timeout=httpx.Timeout(60.0), follow_redirects=True)
        return streamable_http_client(URL, http_client=http)
    except ImportError:
        from mcp.client.streamable_http import streamablehttp_client
        return streamablehttp_client(URL, headers=HEADERS)

def _parse(text):
    i = text.find("\n\n{")
    if i == -1:
        return text, None
    try:
        return text[:i], json.loads(text[i + 2:])
    except Exception:
        return text, None

def _root(e):
    while getattr(e, "exceptions", None):
        e = e.exceptions[0]
    return e

class Nonilion:
    def __init__(self, session):
        self.s = session
        self.online = []          # names currently in the office (from listen)
        self.last_error = None

    async def call(self, name, args=None):
        res = await self.s.call_tool(name, args or {})
        text = "\n".join(c.text for c in res.content if hasattr(c, "text"))
        failed = getattr(res, "is_error", None)
        if failed is None:
            failed = getattr(res, "isError", False)
        if not failed and text.strip().lower().startswith(_FAIL_STARTS):
            failed = True
        self.last_error = text[:300] if failed else None
        return _parse(text)

    async def enter(self):
        await self.call("enter_room", {"name": BOT_NAME})

    async def listen(self, wait=10):
        _, d = await self.call("listen", {"wait_seconds": wait})
        d = d or {}
        self.online = d.get("online", self.online)
        return d.get("events", [])

    async def read_chat(self, limit=15):
        _, d = await self.call("read_room_chat", {"limit": limit})
        return (d or {}).get("messages", [])

    async def post(self, text, reply_to=None, file=None, media_urls=None, mention=None):
        args = {"text": text}
        if reply_to: args["reply_to"] = reply_to
        if file: args["file"] = file          # {"name","content","mime"}
        if media_urls: args["media_urls"] = media_urls
        if mention: args["mention"] = mention
        await self.call("post_room_chat", args)
        return self.last_error is None

    async def reply(self, text):
        """Answer a 1:1 message that arrived through listen."""
        await self.call("reply", {"text": text, "speak": False})
        return self.last_error is None

    async def dm(self, to, text, file=None):
        args = {"to": to, "text": text}
        if file: args["file"] = file
        await self.call("send_direct_message", args)
        return self.last_error is None

    async def board_create(self, description, deadline=None):
        args = {"description": description, "status": "TODO", "priority": "MEDIUM"}
        if deadline: args["deadline"] = deadline
        msg, d = await self.call("create_task", args)
        print("[board] create_task ->", msg[:200], flush=True)
        if self.last_error: return None
        if isinstance(d, dict):
            for k in ("id", "taskId", "task_id"):
                if d.get(k): return str(d[k])
            if isinstance(d.get("task"), dict) and d["task"].get("id"):
                return str(d["task"]["id"])
        return None

    async def board_done(self, task_id):
        await self.call("update_task", {"task_id": task_id, "status": "DONE", "progress": 100})

async def run_forever(handler):
    """Keep a session alive and reconnect whenever it drops."""
    delay = 2
    while True:
        try:
            async with _connect() as (r, w, *_):
                async with ClientSession(r, w) as s:
                    await s.initialize()
                    n = Nonilion(s)
                    await n.enter()
                    delay = 2
                    await handler(n)
        except Exception as e:
            root = _root(e)
            mod = type(root).__module__
            if mod.startswith(("httpx", "httpcore", "anyio")) or isinstance(root, OSError):
                print(f"[reconnecting: {type(root).__name__}]", flush=True)
                await asyncio.sleep(2)
            else:
                print("[BUG in handler, reconnecting]", flush=True)
                traceback.print_exception(root)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)