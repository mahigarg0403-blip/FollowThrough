"""Task storage for FollowThrough. One JSON file, no dependencies.

Task dict: id, title, owner (lowercase str or None), due (str or None),
quote, status, meeting_id.  status: confirmed | needs_owner | unassigned | done

Rule: this module never invents an owner or a date. Missing values stay None.
Set FT_STORE to use a different file (tests do this).
"""
import json
import os
import tempfile
import threading
from pathlib import Path

STATUSES = ("confirmed", "needs_owner", "unassigned", "done")
FIELDS = ("id", "title", "owner", "due", "quote", "status", "meeting_id")
_LOCK = threading.RLock()


def store_path() -> Path:
    env = os.environ.get("FT_STORE")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent / "data" / "tasks.json"


def _read() -> list:
    p = store_path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8") or "[]")
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _write(tasks: list) -> None:
    p = store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(tasks, f, indent=2, ensure_ascii=False)
    os.replace(tmp, p)  # atomic: a crash never leaves half a file


def _clean_owner(owner):
    if owner is None:
        return None
    owner = str(owner).strip().lower()
    return owner or None


def _clean_due(due):
    if due is None:
        return None
    due = str(due).strip()
    return due or None


def _normalise(task: dict, meeting_id: str, n: int) -> dict:
    t = dict(task)
    if "meeting_id" not in t and "source_meeting_id" in t:  # brief's older name
        t["meeting_id"] = t["source_meeting_id"]
    owner = _clean_owner(t.get("owner"))
    status = t.get("status") or ("confirmed" if owner else "needs_owner")
    if status not in STATUSES:
        raise ValueError(f"bad status {status!r}; use one of {STATUSES}")
    return {
        "id": t.get("id") or f"{meeting_id}-t{n}",
        "title": str(t.get("title") or "").strip(),
        "owner": owner,
        "due": _clean_due(t.get("due")),
        "quote": str(t.get("quote") or ""),
        "status": status,
        "meeting_id": meeting_id,
    }


def save_tasks(meeting_id, tasks) -> list:
    """Replace all tasks of this meeting with `tasks`. Returns the saved list."""
    meeting_id = str(meeting_id)
    new = [_normalise(t, meeting_id, i) for i, t in enumerate(tasks, 1)]
    with _LOCK:
        others = [t for t in _read() if t.get("meeting_id") != meeting_id]
        _write(others + new)
    return new


def load_tasks(meeting_id=None) -> list:
    """All tasks, or only those of one meeting."""
    with _LOCK:
        tasks = _read()
    if meeting_id is not None:
        tasks = [t for t in tasks if t.get("meeting_id") == str(meeting_id)]
    return tasks


def update_task(task_id, **fields):
    """Merge fields into one task. Returns the updated task, or None if no such id."""
    bad = set(fields) - set(FIELDS)
    if bad:
        raise ValueError(f"unknown field(s): {sorted(bad)}")
    if "owner" in fields:
        fields["owner"] = _clean_owner(fields["owner"])
    if "due" in fields:
        fields["due"] = _clean_due(fields["due"])
    if "status" in fields and fields["status"] not in STATUSES:
        raise ValueError(f"bad status {fields['status']!r}; use one of {STATUSES}")
    with _LOCK:
        tasks = _read()
        for t in tasks:
            if t.get("id") == task_id:
                t.update(fields)
                _write(tasks)
                return dict(t)
    return None


def tasks_for_owner(name) -> list:
    """All tasks (any status) for this owner, case-insensitive."""
    name = _clean_owner(name)
    if name is None:
        return []
    return [t for t in load_tasks() if t.get("owner") == name]


def is_open(task: dict) -> bool:
    return task.get("status") != "done"


def seed_sample() -> list:
    """Load data/sample_tasks.json into the store (demo/testing)."""
    f = Path(__file__).resolve().parent.parent / "data" / "sample_tasks.json"
    sample = json.loads(f.read_text(encoding="utf-8"))
    return save_tasks(sample[0]["meeting_id"], sample)


if __name__ == "__main__":
    import sys
    if "--seed" in sys.argv:
        print(f"seeded {len(seed_sample())} tasks into {store_path()}")
    else:
        print(json.dumps(load_tasks(), indent=2))
