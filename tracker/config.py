from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable, Optional


DEFAULT_CONFIG: dict = {
    "poll_interval_seconds": 60,


    "send_status_on_startup": True,


    "roblox": {
        "cookie": "",
    },


    "thresholds": {
        "visits_min_delta": 100,
        "favorites_min_delta": 1,
        "collectibles_max_pages": 5,
    },

    "users": [


    ],
    "events": {

        "presence": True,
        "bio": True,
        "username": True,
        "display_name": True,
        "ban": True,
        "badges": True,
        "friends": True,
        "friend_count": True,
        "groups": True,
        "avatar": True,
        "headshot": True,
        "followers": True,
        "following": True,
        "game_sessions": True,
        "collectibles": True,
        "rap": True,
        "user_games": True,
    },


    "digest": {
        "enabled": False,
        "hour_local": 9,
        "period_hours": 24,
        "quiet_hours": "",
    },

    "sinks": {
        "file_log": {
            "enabled": True,
            "path": "events.log",
        },
        "desktop": {
            "enabled": False,
        },
        "webhook": {
            "enabled": False,
            "url": "",
            "username": "Roblox Tracker",
            "avatar_url": "",


            "events": {


            },

            "default_ping": "",
        },
    },
}


class cfgstore:

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self._data: dict = {}
        self._mtime: float = 0.0
        self._on_change: list[Callable[[dict], None]] = []
        self._stop = threading.Event()
        self._watcher: Optional[threading.Thread] = None
        self.load(create_if_missing=True)

    @property
    def data(self) -> dict:
        with self._lock:
            return _deep_copy_json(self._data)

    def load(self, create_if_missing: bool = False) -> None:
        if not self.path.exists():
            if create_if_missing:
                self._data = _deep_copy_json(DEFAULT_CONFIG)
                self.save()
                self._mtime = self.path.stat().st_mtime
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise RuntimeError(f"failed to load config {self.path}: {e}") from e
        merged = _merge_defaults(_deep_copy_json(DEFAULT_CONFIG), raw)
        with self._lock:
            self._data = merged
            self._mtime = self.path.stat().st_mtime

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            payload = _deep_copy_json(self._data)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".config-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            os.replace(tmp, self.path)
            self._mtime = self.path.stat().st_mtime
        except Exception:
            try: os.unlink(tmp)
            except OSError: pass
            raise

    def mutate(self, fn: Callable[[dict], None]) -> None:
        with self._lock:
            fn(self._data)
        self.save()
        self._notify()

    def on_change(self, cb: Callable[[dict], None]) -> None:
        self._on_change.append(cb)

    def start_watching(self, interval: float = 2.0) -> None:
        if self._watcher is not None:
            return
        self._stop.clear()
        t = threading.Thread(target=self._watch_loop, args=(interval,), daemon=True, name="config-watch")
        self._watcher = t
        t.start()

    def stop_watching(self) -> None:
        self._stop.set()
        if self._watcher:
            self._watcher.join(timeout=5)
            self._watcher = None

    def _watch_loop(self, interval: float) -> None:
        while not self._stop.is_set():
            try:
                if self.path.exists():
                    m = self.path.stat().st_mtime
                    if m != self._mtime:
                        self.load()
                        self._notify()
            except OSError:
                pass
            self._stop.wait(interval)

    def _notify(self) -> None:
        snapshot = self.data
        for cb in list(self._on_change):
            try:
                cb(snapshot)
            except Exception:
                pass


def _deep_copy_json(d):
    return json.loads(json.dumps(d))


def _merge_defaults(defaults: dict, override: dict) -> dict:
    if not isinstance(override, dict):
        return override
    out = dict(defaults)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _merge_defaults(out[k], v)
        else:
            out[k] = v
    return out
