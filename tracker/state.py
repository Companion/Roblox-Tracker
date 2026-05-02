from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Optional

from .snapshot import snapshot_t


_INVALID_FS_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe_name(s: str) -> str:
    s = (s or "unknown").strip() or "unknown"
    return _INVALID_FS_CHARS.sub("_", s)[:80]


def _file_for(dirpath: Path, snap: snapshot_t) -> Path:
    name = _safe_name(snap.username or "unknown")
    return dirpath / f"{name} [{snap.user_id}].json"


class statestore:
    def __init__(self, dirpath: Path, legacy_state_file: Optional[Path] = None):
        self.dir = dirpath
        self._snapshots: dict[int, snapshot_t] = {}
        self._files: dict[int, Path] = {}
        self.dir.mkdir(parents=True, exist_ok=True)
        self._migrate_legacy(legacy_state_file)
        self._load()

    def _migrate_legacy(self, legacy: Optional[Path]) -> None:
        if not legacy or not legacy.exists():
            return
        try:
            data = json.loads(legacy.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        users = data.get("users") or {}
        for uid_str, snap_dict in users.items():
            try:
                snap = snapshot_t.from_dict(snap_dict)
            except (TypeError, ValueError):
                continue
            self._snapshots[snap.user_id] = snap
            self._write_one(snap)
        try:
            legacy.unlink()
        except OSError:
            pass

    def _load(self) -> None:
        for p in self.dir.glob("*.json"):
            try:
                snap_dict = json.loads(p.read_text(encoding="utf-8"))
                snap = snapshot_t.from_dict(snap_dict)
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                continue

            self._snapshots[snap.user_id] = snap
            self._files[snap.user_id] = p

    def get(self, user_id: int) -> Optional[snapshot_t]:
        return self._snapshots.get(user_id)

    def set(self, snap: snapshot_t) -> None:
        self._snapshots[snap.user_id] = snap

    def remove(self, user_id: int) -> None:
        self._snapshots.pop(user_id, None)
        old = self._files.pop(user_id, None)
        if old and old.exists():
            try: old.unlink()
            except OSError: pass

    def save(self) -> None:
        for snap in list(self._snapshots.values()):
            self._write_one(snap)

    def _write_one(self, snap: snapshot_t) -> None:
        target = _file_for(self.dir, snap)
        old = self._files.get(snap.user_id)

        if old and old != target and old.exists():
            try: old.unlink()
            except OSError: pass

        fd, tmp = tempfile.mkstemp(dir=self.dir, prefix=".snap-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(snap.to_dict(), f, indent=2, default=str)
            os.replace(tmp, target)
            self._files[snap.user_id] = target
        except Exception:
            try: os.unlink(tmp)
            except OSError: pass
            raise
