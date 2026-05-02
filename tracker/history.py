from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Optional

from .events import sessionended
from .snapshot import snapshot_t


_INVALID_FS_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe(s: str) -> str:
    s = (s or "unknown").strip() or "unknown"
    return _INVALID_FS_CHARS.sub("_", s)[:80]


def _bn(snap_or_username: str | snapshot_t, user_id: int | None = None) -> str:
    if isinstance(snap_or_username, snapshot_t):
        return f"{_safe(snap_or_username.username or 'unknown')} [{snap_or_username.user_id}]"
    return f"{_safe(snap_or_username)} [{user_id}]"


def spath(dir_: Path, snap: snapshot_t) -> Path:
    return dir_ / f"{_bn(snap)}.sessions.jsonl"


def ppath(dir_: Path, snap: snapshot_t) -> Path:
    return dir_ / f"{_bn(snap)}.presence.jsonl"


def addsess(dir_: Path, snap: snapshot_t, ev: sessionended) -> None:
    p = spath(dir_, snap)
    p.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": ev.ended_at,
        "started_at": ev.started_at,
        "duration_seconds": ev.duration_seconds,
        "place_id": ev.place_id,
        "game_name": ev.game_name,
    }
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def addpres(dir_: Path, snap: snapshot_t) -> None:
    if not snap.presence:
        return
    p = ppath(dir_, snap)
    p.parent.mkdir(parents=True, exist_ok=True)
    rec = {"ts": snap.fetched_at, "p": snap.presence, "place_id": snap.place_id}
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def findfiles(dir_: Path, query: str) -> list[Path]:
    out = []
    is_id = query.isdigit()
    for p in dir_.glob("*.json"):
        m = re.match(r"^(.+) \[(\d+)\]\.json$", p.name)
        if not m:
            continue
        name, uid = m.group(1), m.group(2)
        if is_id and uid == query:
            out.append(p)
        elif not is_id and name.lower() == query.lower():
            out.append(p)
    return out


def loadsess(dir_: Path, snap: snapshot_t) -> list[dict]:
    p = spath(dir_, snap)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line: continue
        try: out.append(json.loads(line))
        except json.JSONDecodeError: continue
    return out


def loadpres(dir_: Path, snap: snapshot_t) -> list[dict]:
    p = ppath(dir_, snap)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line: continue
        try: out.append(json.loads(line))
        except json.JSONDecodeError: continue
    return out


def aggsess(sessions: list[dict]) -> dict:
    now = time.time()
    today_start = time.mktime(time.strptime(time.strftime("%Y-%m-%d"), "%Y-%m-%d"))
    week_start = today_start - 6 * 86400

    total = sum(int(s.get("duration_seconds", 0)) for s in sessions)
    today = sum(int(s.get("duration_seconds", 0)) for s in sessions if s.get("ts", 0) >= today_start)
    week = sum(int(s.get("duration_seconds", 0)) for s in sessions if s.get("ts", 0) >= week_start)

    per_game: dict[str, int] = {}
    for s in sessions:
        key = s.get("game_name") or f"place {s.get('place_id')}"
        per_game[key] = per_game.get(key, 0) + int(s.get("duration_seconds", 0))

    return {
        "total_seconds": total,
        "today_seconds": today,
        "week_seconds": week,
        "session_count": len(sessions),
        "per_game_seconds": dict(sorted(per_game.items(), key=lambda kv: -kv[1])),
    }


def patterns(presence: list[dict],
                   online_states: tuple[str, ...] = ("online", "in_game", "studio")) -> dict:
    out = {
        "sample_size": len(presence),
        "peak_hour": None,
        "bedtime_hour": None,
        "wakeup_hour": None,
        "tz_offset_hours": None,
    }
    if len(presence) < 24:
        return out

    by_hour = [0] * 24
    for rec in presence:
        ts = rec.get("ts")
        if not ts: continue
        if rec.get("p") in online_states:
            by_hour[time.localtime(ts).tm_hour] += 1

    if sum(by_hour) == 0:
        return out
    peak = max(range(24), key=lambda h: by_hour[h])
    out["peak_hour"] = peak


    out["tz_offset_hours"] = (20 - peak) % 24

    if out["tz_offset_hours"] > 12:
        out["tz_offset_hours"] -= 24


    sleep_starts = [0] * 24
    sleep_ends   = [0] * 24
    prev = None
    for rec in presence:
        cur = "online" if rec.get("p") in online_states else "offline"
        ts = rec.get("ts")
        if prev is not None and ts is not None:
            h = time.localtime(ts).tm_hour
            if prev == "online" and cur == "offline":
                sleep_starts[h] += 1
            elif prev == "offline" and cur == "online":
                sleep_ends[h] += 1
        prev = cur

    if sum(sleep_starts) >= 5:
        out["bedtime_hour"] = max(range(24), key=lambda h: sleep_starts[h])
    if sum(sleep_ends) >= 5:
        out["wakeup_hour"] = max(range(24), key=lambda h: sleep_ends[h])

    return out


