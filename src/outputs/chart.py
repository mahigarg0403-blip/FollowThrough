"""Workload chart: open tasks per owner. Counted from the store, never hardcoded."""
from collections import Counter
from pathlib import Path

from .. import store

UNASSIGNED = "unassigned"


def _counts(meeting_id=None):
    tasks = store.load_tasks(meeting_id)
    open_tasks = [t for t in tasks if store.is_open(t)]
    c = Counter((t.get("owner") or UNASSIGNED) for t in open_tasks)
    # busiest first, then name; unassigned always last
    rows = sorted(((k, v) for k, v in c.items() if k != UNASSIGNED), key=lambda kv: (-kv[1], kv[0]))
    if c.get(UNASSIGNED):
        rows.append((UNASSIGNED, c[UNASSIGNED]))
    return rows, len(tasks), len(open_tasks)


def chart_text(meeting_id=None) -> str:
    rows, total, n_open = _counts(meeting_id)
    if not rows:
        return "No open tasks."
    width = max(len(k) for k, _ in rows)
    lines = [f"{k.ljust(width)} {'█' * v} {v}" for k, v in rows]
    lines.append(f"{n_open} open of {total} tasks")
    return "\n".join(lines)


def make_chart(meeting_id=None, path="workload.png") -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows, total, n_open = _counts(meeting_id)
    names = [k.title() for k, _ in rows] or ["(none)"]
    vals = [v for _, v in rows] or [0]
    colors = ["#9AA0A6" if n == "Unassigned" else "#2A6FDB" for n in names]
    fig, ax = plt.subplots(figsize=(6, 3.5), dpi=150)
    bars = ax.barh(names[::-1], vals[::-1], color=colors[::-1])
    for b, v in zip(bars, vals[::-1]):
        ax.text(v + 0.05, b.get_y() + b.get_height() / 2, str(v), va="center")
    ax.set_title(f"Open tasks per owner ({total - n_open} of {total} complete)", loc="left")
    ax.set_xlim(0, max(vals) + 1)
    ax.xaxis.set_visible(False)
    for s in ("top", "right", "bottom"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return str(Path(path).resolve())
