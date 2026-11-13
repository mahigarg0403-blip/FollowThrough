"""Run from the project root:  python discover.py   (or: python discover.py --events)
Stop your local main.py AND pause the Render service first (one bot at a time).
Prints every tool Nonilion gives the bot and saves the full details to nonilion_tools.json.
"""
import asyncio, json, sys
from mcp import ClientSession
from src.agent.nonilion import _connect, Nonilion


async def main():
    async with _connect() as (r, w, *_):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = (await s.list_tools()).tools
            out = [{"name": t.name, "description": t.description,
                    "schema": getattr(t, "input_schema", None) or getattr(t, "inputSchema", None)}
                   for t in tools]
            json.dump(out, open("nonilion_tools.json", "w"), indent=2)
            for t in out:
                print("-", t["name"], ":", (t["description"] or "").replace("\n", " ")[:160])
            print(f"\n{len(out)} tools. Full details saved to nonilion_tools.json")

            if "--events" in sys.argv:
                n = Nonilion(s)
                await n.enter()
                print("\nListening 40s. Send the bot a DM, then post a message in the room...")
                for _ in range(4):
                    res = await s.call_tool("listen", {"wait_seconds": 10})
                    print("RAW listen:", [getattr(c, "text", c) for c in res.content])


asyncio.run(main())