import asyncio, json, os
import httpx
from dotenv import load_dotenv
from mcp import ClientSession

load_dotenv()
URL = "https://www.nonilion.com/mcp"
HEADERS = {"Authorization": f"Bearer {os.environ['NONILION_TOKEN']}"}
BOT_NAME = "FollowThrough"

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

class Nonilion:
    def __init__(self, session):
        self.s = session

    async def call(self, name, args=None):
        res = await self.s.call_tool(name, args or {})
        text = "\n".join(c.text for c in res.content if hasattr(c, "text"))
        return _parse(text)

    async def enter(self):
        await self.call("enter_room", {"name": BOT_NAME})

    async def listen(self, wait=10):
        _, d = await self.call("listen", {"wait_seconds": wait})
        return (d or {}).get("events", [])

    async def read_chat(self, limit=15):
        _, d = await self.call("read_room_chat", {"limit": limit})
        return (d or {}).get("messages", [])

    async def post(self, text, reply_to=None, file=None, media_urls=None):
        args = {"text": text}
        if reply_to:
            args["reply_to"] = reply_to
        if file:
            args["file"] = file          # {"name": "x.csv", "content": "...", "mime": "text/csv"}
        if media_urls:
            args["media_urls"] = media_urls
        await self.call("post_room_chat", args)

    async def dm(self, to, text, file=None):
        args = {"to": to, "text": text}
        if file:
            args["file"] = file
        await self.call("send_direct_message", args)

async def run_forever(handler):
    """Keep a session alive and reconnect whenever the connection drops."""
    while True:
        try:
            async with _connect() as (r, w, *_):
                async with ClientSession(r, w) as s:
                    await s.initialize()
                    n = Nonilion(s)
                    await n.enter()
                    await handler(n)
        except Exception as e:
            print(f"[reconnecting: {type(e).__name__}]", flush=True)
            await asyncio.sleep(2)