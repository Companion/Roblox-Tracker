from __future__ import annotations

import time
from typing import Optional

from .snapshot import snapshot_t
from . import events as ev


_STREAK_MILESTONES = {3, 7, 14, 30, 50, 100, 200, 365, 500, 730, 1000}
_ABSENCE_MIN_DAYS = 7


def diff(old: Optional[snapshot_t], new: snapshot_t, enabled: dict[str, bool],
         thresholds: Optional[dict] = None) -> list[ev.event_t]:
    thresholds = thresholds or {}
    visits_threshold = int(thresholds.get("visits_min_delta", 100))
    favorites_threshold = int(thresholds.get("favorites_min_delta", 1))


    if old is not None:
        new.current_session = old.current_session
        new.current_streak_days = old.current_streak_days
        new.longest_streak_days = old.longest_streak_days
        new.last_online_date = old.last_online_date
        new.last_digest_date = old.last_digest_date

    if new.fetched_sections.get("presence", False):
        if new.presence == "in_game" and new.place_id is not None:
            cur = new.current_session
            if not cur or cur.get("place_id") != new.place_id:


                new.current_session = {
                    "place_id": new.place_id,
                    "game_name": new.last_location,
                    "started_at": new.fetched_at,
                }


    streak_events: list[ev.event_t] = []
    if (new.fetched_sections.get("presence", False)
            and new.presence in ("online", "in_game", "studio")):
        today = time.strftime("%Y-%m-%d", time.localtime(new.fetched_at))
        prev = new.last_online_date
        if prev != today:
            if prev is None:
                new.current_streak_days = 1
            else:
                gap = _days_between(prev, today)
                if gap == 1:
                    new.current_streak_days += 1
                else:
                    if old is not None and gap >= _ABSENCE_MIN_DAYS:

                        streak_events.append(ev.returned(
                            user_id=new.user_id, username=new.username,
                            display_name=new.display_name, headshot_url=new.headshot_url,
                            days_away=gap,
                        ))
                    new.current_streak_days = 1
            new.last_online_date = today
            if new.current_streak_days > new.longest_streak_days:
                new.longest_streak_days = new.current_streak_days

            if (old is not None
                    and new.current_streak_days != (old.current_streak_days if old else 0)
                    and new.current_streak_days in _STREAK_MILESTONES):
                streak_events.append(ev.streakms(
                    user_id=new.user_id, username=new.username,
                    display_name=new.display_name, headshot_url=new.headshot_url,
                    days=new.current_streak_days,
                ))

    if old is None:
        return []

    out: list[ev.event_t] = list(streak_events)
    base = dict(
        user_id=new.user_id,
        username=new.username,
        display_name=new.display_name,
        headshot_url=new.headshot_url,
    )


    if (enabled.get("account_deleted", True)
            and new.fetched_sections.get("user_info", False)
            and old.fetched_sections.get("user_info", False)
            and new.account_deleted and not old.account_deleted):
        out.append(ev.accountdeleted(**base))

    def _ok(section: str) -> bool:

        return old.fetched_sections.get(section, False) and new.fetched_sections.get(section, False)

    def _end_session(reason_now: float) -> Optional[ev.sessionended]:
        sess = old.current_session if old else None
        if not sess:
            return None
        new.current_session = None
        if not enabled.get("game_sessions", True):
            return None
        return ev.sessionended(
            **base,
            place_id=sess.get("place_id"),
            game_name=sess.get("game_name"),
            started_at=float(sess.get("started_at") or 0.0),
            ended_at=reason_now,
            duration_seconds=int(max(0, reason_now - float(sess.get("started_at") or reason_now))),
        )


    if enabled.get("presence", True) and _ok("presence") and old.presence != new.presence:
        if old.presence == "offline" and new.presence == "online":
            out.append(ev.wentonline(**base))
        elif new.presence == "offline" and old.presence in ("online", "in_game", "studio"):
            if old.presence == "in_game":
                out.append(ev.leftgame(**base, game_name=old.last_location))
                ended = _end_session(new.fetched_at)
                if ended: out.append(ended)
            out.append(ev.wentoffline(**base))
        elif new.presence == "in_game" and old.presence != "in_game":
            out.append(ev.joinedgame(**base, game_name=new.last_location, place_id=new.place_id))

        elif old.presence == "in_game" and new.presence == "online":
            out.append(ev.leftgame(**base, game_name=old.last_location))
            ended = _end_session(new.fetched_at)
            if ended: out.append(ended)
        elif new.presence == "studio" and old.presence != "studio":
            out.append(ev.wenttostudio(**base))
            if old.presence == "in_game":
                ended = _end_session(new.fetched_at)
                if ended: out.append(ended)


    if (enabled.get("presence", True) and _ok("presence")
            and new.presence == "in_game" and old.presence == "in_game"
            and (old.place_id != new.place_id)):
        out.append(ev.leftgame(**base, game_name=old.last_location))
        ended = _end_session(new.fetched_at)
        if ended: out.append(ended)
        out.append(ev.joinedgame(**base, game_name=new.last_location, place_id=new.place_id))
        new.current_session = {
            "place_id": new.place_id,
            "game_name": new.last_location,
            "started_at": new.fetched_at,
        }


    if enabled.get("bio", True) and _ok("user_info") and (old.description or "") != (new.description or ""):
        out.append(ev.biochanged(**base, old=old.description, new=new.description))


    if enabled.get("username", True) and _ok("user_info") and old.username and new.username and old.username != new.username:
        out.append(ev.unamechanged(**base, old=old.username, new=new.username))


    if enabled.get("display_name", True) and _ok("user_info") and old.display_name and new.display_name and old.display_name != new.display_name:
        out.append(ev.dnchanged(**base, old=old.display_name, new=new.display_name))


    if enabled.get("ban", True) and _ok("user_info") and old.is_banned is not None and new.is_banned is not None and old.is_banned != new.is_banned:
        out.append(ev.banchanged(**base, is_banned=bool(new.is_banned)))


    if (enabled.get("verified_badge", True) and _ok("user_info")
            and old.has_verified_badge is not None and new.has_verified_badge is not None
            and old.has_verified_badge != new.has_verified_badge):
        out.append(ev.verifiedchanged(**base, has_verified_badge=bool(new.has_verified_badge)))


    if (enabled.get("premium", True) and _ok("premium")
            and old.is_premium is not None and new.is_premium is not None
            and old.is_premium != new.is_premium):
        out.append(ev.premiumchanged(**base, is_premium=bool(new.is_premium)))


    if enabled.get("roblox_badges", True) and _ok("roblox_badges"):
        old_set = set(old.roblox_badge_ids)
        new_set = set(new.roblox_badge_ids)
        for bid in new_set - old_set:
            meta = new.roblox_badges_meta.get(str(bid), {})
            out.append(ev.rbxbadge(
                **base, badge_id=bid, badge_name=meta.get("name"),
                badge_description=meta.get("description"),
                image_url=meta.get("image_url"), removed=False,
            ))
        for bid in old_set - new_set:
            meta = old.roblox_badges_meta.get(str(bid), {})
            out.append(ev.rbxbadge(
                **base, badge_id=bid, badge_name=meta.get("name"),
                badge_description=meta.get("description"),
                image_url=meta.get("image_url"), removed=True,
            ))


    if enabled.get("badges", True) and _ok("badges"):
        old_set = set(old.badge_ids)
        for bid in new.badge_ids:
            if bid not in old_set:
                meta = new.badges_meta.get(str(bid), {})
                out.append(ev.badgeearned(
                    **base,
                    badge_id=bid,
                    badge_name=meta.get("name"),
                    badge_description=meta.get("description"),
                ))


    if enabled.get("friends", True) and _ok("friends"):
        old_set = set(old.friend_ids)
        new_set = set(new.friend_ids)
        for fid in new_set - old_set:
            out.append(ev.friendadded(**base, friend_id=fid))
        for fid in old_set - new_set:
            out.append(ev.friendremoved(**base, friend_id=fid))


    if (enabled.get("friend_count", True)
            and _ok("friends_count") and not _ok("friends")
            and old.friends_count != new.friends_count):
        out.append(ev.friendcntchanged(**base, old=old.friends_count, new=new.friends_count))


    if enabled.get("groups", True) and _ok("groups"):
        old_set = set(old.group_ids)
        new_set = set(new.group_ids)
        for gid in new_set - old_set:
            meta = new.groups_meta.get(str(gid), {})
            out.append(ev.groupjoined(**base, group_id=gid, group_name=meta.get("name"), role=meta.get("role")))
        for gid in old_set - new_set:
            meta = old.groups_meta.get(str(gid), {})
            out.append(ev.groupleft(**base, group_id=gid, group_name=meta.get("name")))


    if enabled.get("avatar", True) and _ok("avatar"):
        old_set = set(old.avatar_asset_ids)
        new_set = set(new.avatar_asset_ids)
        if old_set != new_set:
            out.append(ev.avatarchanged(
                **base,
                added=sorted(new_set - old_set),
                removed=sorted(old_set - new_set),
            ))


    if enabled.get("headshot", True) and _ok("headshot") and old.headshot_url and new.headshot_url:

        if _strip_query(old.headshot_url) != _strip_query(new.headshot_url):
            out.append(ev.headshotchanged(**base, old_url=old.headshot_url, new_url=new.headshot_url))


    if enabled.get("collectibles", True) and _ok("collectibles"):
        old_set = set(old.collectible_user_asset_ids)
        new_set = set(new.collectible_user_asset_ids)
        for uaid in new_set - old_set:
            meta = new.collectibles_meta.get(str(uaid), {})
            out.append(ev.limitedacq(
                **base,
                user_asset_id=uaid,
                asset_id=meta.get("asset_id"),
                name=meta.get("name"),
                rap=int(meta.get("rap") or 0),
            ))
        for uaid in old_set - new_set:
            meta = old.collectibles_meta.get(str(uaid), {})
            out.append(ev.limitedrem(
                **base,
                user_asset_id=uaid,
                asset_id=meta.get("asset_id"),
                name=meta.get("name"),
            ))


    if enabled.get("rap", True) and _ok("collectibles") and old.total_rap != new.total_rap:
        out.append(ev.rapchanged(**base, old=old.total_rap, new=new.total_rap))


    if enabled.get("user_games", True) and _ok("user_games"):

        new.visit_velocity_baseline = dict(old.visit_velocity_baseline or {})
        elapsed_hours = max(1e-6, (new.fetched_at - old.fetched_at) / 3600.0)
        ema_alpha = float(thresholds.get("velocity_ema_alpha", 0.3))
        spike_ratio = float(thresholds.get("velocity_spike_ratio", 3.0))
        spike_min_per_hour = float(thresholds.get("velocity_min_per_hour", 100.0))

        for pid_str, ng in new.user_games.items():
            og = old.user_games.get(pid_str)
            if not og:
                continue
            pid = int(pid_str)
            v_old, v_new = int(og.get("visits", 0)), int(ng.get("visits", 0))
            f_old, f_new = int(og.get("favorites", 0)), int(ng.get("favorites", 0))

            if v_new != v_old and abs(v_new - v_old) >= visits_threshold:
                out.append(ev.visitschanged(
                    **base, place_id=pid, game_name=ng.get("name"),
                    old=v_old, new=v_new,
                ))
            if f_new != f_old and abs(f_new - f_old) >= favorites_threshold:
                out.append(ev.favchanged(
                    **base, place_id=pid, game_name=ng.get("name"),
                    old=f_old, new=f_new,
                ))


            if v_new >= v_old:
                rate = (v_new - v_old) / elapsed_hours
                baseline = new.visit_velocity_baseline.get(pid_str)
                if baseline is None:
                    new.visit_velocity_baseline[pid_str] = rate
                else:
                    if (enabled.get("visit_velocity", True)
                            and rate >= spike_min_per_hour
                            and rate >= baseline * spike_ratio):
                        out.append(ev.velspike(
                            **base, place_id=pid, game_name=ng.get("name"),
                            visits_per_hour=rate, baseline_per_hour=baseline,
                        ))

                    new.visit_velocity_baseline[pid_str] = (
                        ema_alpha * rate + (1 - ema_alpha) * baseline
                    )


    if enabled.get("followers", True) and _ok("followers") and old.followers_count != new.followers_count:
        out.append(ev.followerschanged(**base, old=old.followers_count, new=new.followers_count))
    if enabled.get("following", True) and _ok("following") and old.following_count != new.following_count:
        out.append(ev.followingchanged(**base, old=old.following_count, new=new.following_count))

    return out


def _strip_query(url: str) -> str:
    return url.split("?", 1)[0]


def _days_between(d1: str, d2: str) -> int:
    import datetime
    a = datetime.date.fromisoformat(d1)
    b = datetime.date.fromisoformat(d2)
    return (b - a).days
