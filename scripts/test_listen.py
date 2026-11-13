import asyncio, os, time
import httpx
from dotenv import load_dotenv
from mcp import ClientSession

load_dotenv()
URL = "https://www.nonilion.com/mcp"
HEADERS = {"Authorization": f"Bearer {os.environ['NONILION_TOKEN']}"}

def connect():
    try:
        from mcp.client.streamable_http import streamable_http_client
        http = httpx.AsyncClient(headers=HEADERS, timeout=httpx.Timeout(60.0, read=60.0),
                                 follow_redirects=True)
        return streamable_http_client(URL, http_client=http)
    except ImportError:
        from mcp.client.streamable_http import streamablehttp_client
        return streamablehttp_client(URL, headers=HEADERS)

async def call(s, name, args=None):
    res = await s.call_tool(name, args or {})
    out = "\n".join(c.text for c in res.content if hasattr(c, "text"))
    print(f"\n--- {name} ---\n{out[:3000]}", flush=True)
    return out

async def run_session(deadline):
    async with connect() as (r, w, *_):
        async with ClientSession(r, w) as s:
            await s.initialize()
            await call(s, "enter_room", {"name": "FollowThrough"})
            while time.time() < deadline:
                await call(s, "listen", {"wait_seconds": 10})
            await call(s, "read_room_chat", {"limit": 10})

async def main():
    print("Starting in 5 seconds. Then you have 2.5 minutes to do these in your room:")
    print(" 1. type a chat message that tags @FollowThrough")
    print(" 2. drop a small .txt file into the room chat")
    print(" 3. type a normal message without tagging")
    await asyncio.sleep(5)
    deadline = time.time() + 150
    while time.time() < deadline:
        try:
            await run_session(deadline)
            break
        except Exception as e:
            print(f"\n[connection dropped: {type(e).__name__}; reconnecting]", flush=True)
            await asyncio.sleep(2)

asyncio.run(main())