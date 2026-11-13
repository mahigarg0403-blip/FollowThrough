import json, os
from src.agent.store_shim import load_tasks, update_task
from src.chase.chase import handle_reply

_M = json.load(open("owner_map.json")) if os.path.exists("owner_map.json") else {}
HANDLE_TO_OWNER = {v.lstrip("@").lower(): k for k, v in _M.items()}

async def handle_dm(n, ev):
    sender = ev["from"].lstrip("@").lower()
    owner = HANDLE_TO_OWNER.get(sender, sender)
    text = (ev.get("text") or "").strip().lower()
    if text.startswith("not mine"):
        mine = [t for t in load_tasks() if (t.get("owner") or "").lower() == owner
                and t["status"] != "done"]
        for t in mine:
            update_task(t["id"], owner=None, status="needs_owner")
        await n.dm(sender, f"Okay, I've marked {len(mine)} task(s) as needing an owner.")
        await n.post(f"{owner.title()} says {len(mine)} task(s) aren't theirs. Who takes them?")
        return
    line = handle_reply(owner, text)          # B's function: handles "done"
    if line:
        await n.dm(sender, "Got it, marked done ✅")
        await n.post(line)                    # progress line in the room