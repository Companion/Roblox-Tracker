from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from .events import event_t
from .sinks.file_log import filesink
from .sinks.desktop import desksink
from .sinks.webhook import websink
from .sinks.per_user_events import uesink


class dispatcher_t:
    def __init__(self, config: dict, base_dir: Path, state_dir: Optional[Path] = None):
        self.base_dir = base_dir
        self.state_dir = state_dir or (base_dir / "tracked users")
        self._global_config: dict = {}
        self._file: Optional[filesink] = None
        self._desktop: Optional[desksink] = None
        self._webhook: Optional[websink] = None
        self._per_user_events = uesink(self.state_dir)
        self.update_config(config)

    def update_config(self, config: dict) -> None:
        self._global_config = config
        sinks = config.get("sinks", {})

        fl = sinks.get("file_log", {})
        if fl.get("enabled"):
            path = Path(fl.get("path") or "events.log")
            if not path.is_absolute():
                path = self.base_dir / path
            self._file = filesink(path)
        else:
            self._file = None

        if sinks.get("desktop", {}).get("enabled"):
            self._desktop = desksink()
        else:
            self._desktop = None

        wh_global = sinks.get("webhook", {})
        if self._webhook is None:
            self._webhook = websink(wh_global)
        else:
            self._webhook.update_config(wh_global)

    async def aclose(self) -> None:
        if self._webhook:
            await self._webhook.aclose()

    async def emit(self, event: event_t, user_entry: Optional[dict] = None,
                   suppress_webhook: bool = False) -> None:
        coros = []

        coros.append(self._per_user_events.emit(event))
        if self._file:
            coros.append(self._file.emit(event))
        if self._desktop and not suppress_webhook:
            coros.append(self._desktop.emit(event))
        if self._webhook and not suppress_webhook:

            override = (user_entry or {}).get("webhook")
            if override:
                effective = _merge(self._global_config.get("sinks", {}).get("webhook", {}), override)
                effective.setdefault("enabled", True)
                coros.append(self._webhook.emit(event, effective_config=effective))
            else:
                coros.append(self._webhook.emit(event))
        if coros:
            await asyncio.gather(*coros, return_exceptions=True)


def _merge(base: dict, override: dict) -> dict:
    out = dict(base) if isinstance(base, dict) else {}
    if not isinstance(override, dict):
        return out
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out
