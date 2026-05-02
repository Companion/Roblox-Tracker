from __future__ import annotations

import json
import re
from dataclasses import asdict, is_dataclass
from pathlib import Path

from ..events import event_t


_INVALID_FS_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe(s: str) -> str:
    s = (s or "unknown").strip() or "unknown"
    return _INVALID_FS_CHARS.sub("_", s)[:80]


def epath(dir_: Path, user_id: int, username: str | None) -> Path:
    return dir_ / f"{_safe(username or 'unknown')} [{user_id}].events.jsonl"


class uesink:
    name = "per_user_events"

    def __init__(self, base_dir: Path):
        self.dir = base_dir
        self.dir.mkdir(parents=True, exist_ok=True)

    async def emit(self, event: event_t) -> None:
        try:
            payload = asdict(event) if is_dataclass(event) else dict(event.__dict__)
        except TypeError:
            return

        if event.kind == "daily_digest":
            return
        import time as _time
        payload["ts"] = _time.time()
        p = epath(self.dir, event.user_id, event.username)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, default=str) + "\n")
