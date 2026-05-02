from __future__ import annotations

import time
from pathlib import Path

from ..events import event_t


class filesink:
    name = "file_log"

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    async def emit(self, event: event_t) -> None:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {event.kind} | uid={event.user_id} @{event.username} | {event.summary()}\n"

        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line)
