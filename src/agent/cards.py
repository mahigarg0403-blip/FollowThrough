import html

HELP = ("👋 I'm FollowThrough. Message me anytime:\n"
        "• **my tasks**: see what's open for you\n"
        "• **done 1** or **done pricing deck**: mark a task finished\n"
        "• **snooze**: remind me later\n"
        "• **blocked: reason**: tell the team you're stuck")

def is_unassigned(t):
    return not t.get("owner") and t.get("status") != "done"

def counts(tasks):
    total = len(tasks)
    done = sum(t.get("status") == "done" for t in tasks)
    un = sum(is_unassigned(t) for t in tasks)
    return total, done, un, total - done - un

def progress_line(tasks):
    total, done, un, op = counts(tasks)
    return f"**{done} of {total}** done · {op} open · {un} unassigned"

def workload(tasks):
    w = {}
    for t in tasks:
        if t.get("status") == "done":
            continue
        k = t["owner"] if t.get("owner") else "unassigned"
        w[k] = w.get(k, 0) + 1
    return w

def workload_text(tasks):
    w = workload(tasks)
    if not w:
        return "Nothing open 🎉"
    mx, width = max(w.values()), max(len(k) for k in w)
    rows = sorted(w.items(), key=lambda kv: (kv[0] == "unassigned", -kv[1], kv[0]))
    return "\n".join(f"{k.ljust(width)}  {'█' * max(1, round(v / mx * 10))} {v}" for k, v in rows)

def quote_line(t):
    q = (t.get("quote") or "").strip()
    return "⚠ quote not verified" if not q or q.startswith("(quote") else f"“{q}”"

def task_block(t):
    who = f"👤 **{t['owner']}**" if t.get("owner") else "👤 **no owner yet**"
    due = f"📅 **{t['due']}**" if t.get("due") else "📅 no date given"
    return f"**{t['title']}**\n{who}   {due}\n{quote_line(t)}"

def results_message(decisions, tasks):
    ok = [t for t in tasks if t.get("owner")]
    missing = [t for t in tasks if not t.get("owner")]
    parts = [f"✅ **Meeting processed:** {len(decisions)} decision(s) · {len(tasks)} task(s) "
             f"({len(ok)} confirmed, {len(missing)} need an owner)"]
    if decisions:
        parts.append("**Decisions**\n" + "\n".join(f"• {d}" for d in decisions))
    if ok:
        parts.append("**Confirmed (owner and quote verified)**\n\n" + "\n\n".join(task_block(t) for t in ok))
    if missing:
        parts.append("**Needs an owner (I won't guess)**\n\n" + "\n\n".join(task_block(t) for t in missing))
    return "\n\n".join(parts)

def question_message(missing, timeout):
    lines = ["❓ **Who should own these?**"]
    for i, t in enumerate(missing, 1):
        lines.append(f"**{i}. {t['title']}**\n{quote_line(t)}")
    lines.append(f"Reply like **1: Mei** or **1: Mei, 2: Arjun**. "
                 f"Anything unanswered in {timeout} seconds is marked UNASSIGNED.")
    return "\n\n".join(lines)

def unassigned_message(left):
    return ("🚫 **No answer, so I'm marking these UNASSIGNED instead of guessing**\n"
            + "\n".join(f"• {t['title']}" for t in left))

def summary_message(tasks, extra=""):
    if not tasks:
        return "No tasks yet. Drop a .txt transcript in this chat."
    out = (f"📊 **Where things stand**\n{progress_line(tasks)}\n\n"
           f"**Open tasks per owner**\n{workload_text(tasks)}")
    return out + (f"\n\n{extra}" if extra else "")

def report_file(tasks, decisions):
    e = html.escape
    total, done, un, op = counts(tasks)
    rows = []
    for t in tasks:
        st = "done" if t.get("status") == "done" else ("unassigned" if is_unassigned(t) else "confirmed")
        badge = {"done": "✓ DONE", "unassigned": "UNASSIGNED", "confirmed": "✓ CONFIRMED"}[st]
        q = (t.get("quote") or "").strip()
        qh = "quote not verified" if not q or q.startswith("(quote") else f"“{e(q)}”"
        rows.append(f'<div class="card"><div class="top"><h3>{e(t["title"])}</h3>'
                    f'<span class="b {st}">{badge}</span></div>'
                    f'<p class="meta">Owner <b>{e(t.get("owner") or "-")}</b> &nbsp; '
                    f'Due <b>{e(t.get("due") or "-")}</b></p><p class="q">{qh}</p></div>')
    w = workload(tasks)
    mx = max(w.values()) if w else 1
    bars = ""
    for k, v in sorted(w.items()):
        cls = "red" if k == "unassigned" else ""
        bars += (f'<div class="bar"><span>{e(k)}</span><i class="{cls}" '
                 f'style="width:{int(v / mx * 100)}%"></i><b>{v}</b></div>')
    decs = "".join(f"<li>{e(d)}</li>" for d in decisions) or "<li>None recorded</li>"
    page = _REPORT.replace("__ROWS__", "".join(rows)).replace("__BARS__", bars) \
        .replace("__DECS__", decs).replace("__TOTAL__", str(total)).replace("__DONE__", str(done)) \
        .replace("__OPEN__", str(op)).replace("__UN__", str(un))
    return {"name": "followthrough_report.html", "content": page, "mime": "text/html"}

_REPORT = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>FollowThrough report</title>
<style>
:root{--bg:#0f1417;--card:#1a2328;--line:#2b363b;--text:#f2efe8;--muted:#9aa5a8;--amber:#f5b84a;--green:#5fd38d;--red:#ff6b6b}
*{box-sizing:border-box}body{margin:0;padding:32px;background:var(--bg);color:var(--text);font-family:system-ui,sans-serif;line-height:1.4;max-width:860px;margin:auto}
h1{margin:0 0 4px}h2{font-size:14px;letter-spacing:.08em;color:var(--amber);margin:28px 0 10px}
.chips{display:flex;gap:10px;flex-wrap:wrap}.chip{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 16px}
.chip b{font-size:22px;display:block}.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin-bottom:12px}
.top{display:flex;justify-content:space-between;gap:12px;align-items:center}h3{margin:0;font-size:18px}.meta{color:var(--muted);margin:6px 0}
.q{color:var(--amber);font-style:italic;margin:6px 0 0}.b{font-size:12px;font-weight:700;border:1px solid;border-radius:999px;padding:3px 10px}
.confirmed,.done{color:var(--green)}.unassigned{color:var(--red)}
.bar{display:flex;align-items:center;gap:10px;margin:8px 0}.bar span{width:110px;color:var(--muted)}
.bar i{display:block;height:18px;background:var(--amber);border-radius:6px}.bar i.red{background:var(--red)}
</style></head><body>
<h1>FollowThrough</h1><p style="color:var(--muted)">Meeting report: decisions, owners, deadlines and the exact words behind each task.</p>
<div class="chips"><div class="chip"><b>__TOTAL__</b>tasks</div><div class="chip"><b>__DONE__</b>done</div>
<div class="chip"><b>__OPEN__</b>open</div><div class="chip"><b>__UN__</b>unassigned</div></div>
<h2>DECISIONS</h2><ul>__DECS__</ul><h2>TASKS</h2>__ROWS__<h2>OPEN TASKS PER OWNER</h2>__BARS__
</body></html>"""