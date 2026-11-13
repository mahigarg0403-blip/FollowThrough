try:
    from src.store import save_tasks, load_tasks, update_task
except ImportError:
    _DB = {}

    def save_tasks(meeting_id, tasks):
        _DB[meeting_id] = {t["id"]: dict(t) for t in tasks}

    def load_tasks(meeting_id=None):
        rows = []
        for mid, d in _DB.items():
            if meeting_id in (None, mid):
                rows += list(d.values())
        return rows

    def update_task(task_id, **fields):
        for d in _DB.values():
            if task_id in d:
                d[task_id].update(fields)