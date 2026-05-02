from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Optional

from .events import dailydigest
from .snapshot import snapshot_t
from .sinks.per_user_events import epath
from . import history


def _today(ts: float) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(ts))


def digestdue(snap: snapshot_t, cfg_digest: dict, now: float) -> bool:
    if not cfg_digest.get("enabled"):
        return False
    today = _today(now)
    last = snap.last_digest_date
    if last == today:
        return False
    hour_local = int(cfg_digest.get("hour_local", 9))
    current_hour = time.localtime(now).tm_hour


    return current_hour >= hour_local


def mkdigest(state_dir: Path, snap: snapshot_t, period_hours: int = 24,
                 now: Optional[float] = None) -> dailydigest:
    now = now if now is not None else time.time()
    period_start = now - period_hours * 3600

    events = _loadev(state_dir, snap, since=period_start)
    sessions = [s for s in history.loadsess(state_dir, snap)
                if (s.get("ts") or 0) >= period_start]

    online_seconds = sum(int(s.get("duration_seconds", 0)) for s in sessions)
    games_played: dict[str, int] = {}
    for s in sessions:
        key = s.get("game_name") or f"place {s.get('place_id')}"
        games_played[key] = games_played.get(key, 0) + int(s.get("duration_seconds", 0))

    badges_earned: list[str] = []
    friends_added = 0
    friends_removed = 0
    groups_joined: list[str] = []
    groups_left: list[str] = []
    bio_changed = False
    avatar_changed = False
    rap_delta = 0
    other: dict[str, int] = {}

    for e in events:
        kind = e.get("type")
        if kind == "badge_earned":
            n = e.get("badge_name") or f"badge {e.get('badge_id')}"
            badges_earned.append(n)
        elif kind == "friend_added":
            friends_added += 1
        elif kind == "friend_removed":
            friends_removed += 1
        elif kind == "group_joined":
            groups_joined.append(e.get("group_name") or f"group {e.get('group_id')}")
        elif kind == "group_left":
            groups_left.append(e.get("group_name") or f"group {e.get('group_id')}")
        elif kind == "bio_changed":
            bio_changed = True
        elif kind in ("avatar_changed", "headshot_changed"):
            avatar_changed = True
        elif kind == "rap_changed":
            rap_delta += int(e.get("new", 0)) - int(e.get("old", 0))
        elif kind in ("went_online", "went_offline", "joined_game", "left_game",
                      "went_to_studio", "game_session_ended"):

            pass
        else:
            other[kind] = other.get(kind, 0) + 1

    return dailydigest(
        user_id=snap.user_id,
        username=snap.username,
        display_name=snap.display_name,
        headshot_url=snap.headshot_url,
        period_hours=period_hours,
        period_started_at=period_start,
        period_ended_at=now,
        online_seconds=online_seconds,
        session_count=len(sessions),
        games_played=dict(sorted(games_played.items(), key=lambda kv: -kv[1])),
        badges_earned=badges_earned,
        friends_added=friends_added,
        friends_removed=friends_removed,
        groups_joined=groups_joined,
        groups_left=groups_left,
        bio_changed=bio_changed,
        avatar_changed=avatar_changed,
        rap_delta=rap_delta,
        other_event_counts=other,
    )


def _loadev(state_dir: Path, snap: snapshot_t, since: float) -> list[dict]:
    p = epath(state_dir, snap.user_id, snap.username)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (d.get("ts") or 0) >= since:
            out.append(d)
    return out
