import asyncio, os, json
import httpx
from dotenv import load_dotenv
from mcp import ClientSession

load_dotenv()
URL = "https://www.nonilion.com/mcp"
HEADERS = {"Authorization": f"Bearer {os.environ['NONILION_TOKEN']}"}
WANT = {"whoami", "enter_room", "leave_room", "listen", "reply", "say_out_loud",
        "read_room_chat", "post_room_chat", "send_direct_message",
        "list_chat_handles", "list_people", "create_task", "update_task",
        "list_tasks", "get_team_tasks"}

def connect():
    try:
        from mcp.client.streamable_http import streamable_http_client
        http = httpx.AsyncClient(headers=HEADERS, timeout=30, follow_redirects=True)
        return streamable_http_client(URL, http_client=http)
    except ImportError:
        from mcp.client.streamable_http import streamablehttp_client
        return streamablehttp_client(URL, headers=HEADERS)

async def main():
    async with connect() as (r, w, *_):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = await s.list_tools()
            print("total tools:", len(tools.tools))
            for t in tools.tools:
                if t.name in WANT:
                    print("==", t.name)
                    print(t.description)
                    schema = getattr(t, "input_schema", None) or getattr(t, "inputSchema", None)
                    print(json.dumps(schema))
            print("ALL TOOL NAMES:", ", ".join(sorted(t.name for t in tools.tools)))

asyncio.run(main())