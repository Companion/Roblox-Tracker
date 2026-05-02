from __future__ import annotations

import logging
import time
from typing import Optional

import httpx

log = logging.getLogger("tracker.webhook")

from ..events import (
    event_t, EVENT_COLORS, EVENT_PRETTY,
    biochanged, joinedgame, leftgame, badgeearned, friendadded, friendremoved, friendcntchanged,
    groupjoined, groupleft, avatarchanged, headshotchanged, followerschanged,
    followingchanged, unamechanged, dnchanged, banchanged,
    sessionended, limitedacq, limitedrem, rapchanged,
    visitschanged, favchanged, accountdeleted, streakms,
    returned, dailydigest, premiumchanged, verifiedchanged,
    rbxbadge, together, velspike, wentonline, wentoffline,
    wenttostudio, status_t,
)


EVENT_TITLES: dict[str, str] = {
    "went_online":            "Came online",
    "went_offline":           "Went offline",
    "joined_game":            "Joined a game",
    "left_game":              "Left the game",
    "went_to_studio":         "Opened Studio",
    "bio_changed":            "Updated bio",
    "username_changed":       "Changed username",
    "display_name_changed":   "Changed display name",
    "badge_earned":           "Earned a badge",
    "friend_added":           "Added a friend",
    "friend_removed":         "Removed a friend",
    "group_joined":           "Joined a group",
    "group_left":             "Left a group",
    "avatar_changed":         "Avatar changed",
    "headshot_changed":       "Profile picture changed",
    "followers_changed":      "Follower count changed",
    "following_changed":      "Following count changed",
    "ban_state_changed":      "Ban state changed",
    "account_deleted":        "Account no longer accessible",
    "streak_milestone":       "Streak milestone",
    "returned_after_absence": "Back online after absence",
    "daily_digest":           "Daily digest",
    "premium_changed":        "Premium status changed",
    "verified_badge_changed": "Verified badge changed",
    "roblox_badge_granted":   "Roblox badge",
    "together_in_game":       "Playing together",
    "visit_velocity_spike":   "Visit velocity spike",
    "limited_acquired":       "Limited acquired",
    "limited_removed":        "Limited removed",
    "rap_changed":            "RAP changed",
    "game_visits_changed":    "Game visits changed",
    "game_favorites_changed": "Game favorites changed",
    "game_session_ended":     "Session ended",
    "current_status":         "Current status",
    "friend_count_changed":   "Friend count changed",
}


class websink:
    name = "webhook"

    def __init__(self, config: dict):
        self.config = config
        self._client = httpx.AsyncClient(timeout=15.0)

    def update_config(self, config: dict) -> None:
        self.config = config

    async def aclose(self) -> None:
        await self._client.aclose()

    async def emit(self, event: event_t, effective_config: dict | None = None) -> None:
        cfg = effective_config if effective_config is not None else self.config
        if not cfg.get("enabled"):
            return
        url = cfg.get("url")
        if not url:
            return

        per_event = (cfg.get("events") or {}).get(event.kind, {}) or {}
        if per_event.get("enabled") is False:
            return

        embed = self._build_embed(event, per_event)
        ping = per_event.get("ping", cfg.get("default_ping") or "")
        payload = {
            "username": cfg.get("username") or "Roblox Tracker",
            "avatar_url": cfg.get("avatar_url") or None,
            "embeds": [embed],
        }
        if ping:
            payload["content"] = ping
            payload["allowed_mentions"] = {"parse": ["users", "roles", "everyone"]}
        payload = {k: v for k, v in payload.items() if v is not None}

        try:
            r = await self._client.post(url, json=payload)
            if r.status_code == 429:
                try:    retry = float(r.json().get("retry_after", 1.0))
                except Exception: retry = 1.0
                import asyncio
                await asyncio.sleep(retry)
                r = await self._client.post(url, json=payload)
            if r.status_code >= 400:

                body = ""
                try: body = r.text[:600]
                except Exception: pass
                log.warning("Discord rejected webhook event=%s status=%s body=%s",
                            event.kind, r.status_code, body)
        except httpx.HTTPError as e:
            log.warning("webhook POST failed event=%s: %s", event.kind, e)


    def _build_embed(self, event: event_t, per_event: dict) -> dict:
        color = per_event.get("color", EVENT_COLORS.get(event.kind, 0x95A5A6))


        title = per_event.get("title_template")
        if title:
            try:
                title = title.format(**self._title_context(event))
            except (KeyError, IndexError, ValueError):
                title = EVENT_TITLES.get(event.kind, EVENT_PRETTY.get(event.kind, event.kind))
        else:
            title = EVENT_TITLES.get(event.kind, EVENT_PRETTY.get(event.kind, event.kind))

        profile_url = f"https://www.roblox.com/users/{event.user_id}/profile"

        embed: dict = {
            "color": int(color),
            "title": title[:256],
            "url": profile_url,
            "author": {
                "name": _author_name(event),
                "url": profile_url,
                **({"icon_url": event.headshot_url} if event.headshot_url else {}),
            },
            "timestamp": _iso_now(),
            "footer": {"text": f"rblx-tracker • uid {event.user_id}"},
        }
        if event.headshot_url:
            embed["thumbnail"] = {"url": event.headshot_url}

        desc = self._description_for(event)
        if desc:
            embed["description"] = _truncate(desc, 4096)

        fields = self._fields_for(event)
        if fields:
            embed["fields"] = fields

        return embed


    def _description_for(self, event: event_t) -> Optional[str]:
        if isinstance(event, joinedgame):
            if event.game_name and event.place_id:
                return f"Now playing **[{event.game_name}](https://www.roblox.com/games/{event.place_id})**"
            if event.place_id:
                return f"Now playing **[place {event.place_id}](https://www.roblox.com/games/{event.place_id})**"
            if event.game_name:
                return f"Now playing **{event.game_name}**"
            return "Started playing - *game hidden by user privacy*"
        if isinstance(event, leftgame):
            if event.game_name:
                return f"Stopped playing **{event.game_name}**"
            return "Stopped playing *(private)*"
        if isinstance(event, sessionended):
            mins = event.duration_seconds // 60
            secs = event.duration_seconds % 60
            dur = f"**{mins}m {secs}s**" if mins else f"**{secs}s**"
            where = (f"[{event.game_name}](https://www.roblox.com/games/{event.place_id})"
                     if event.game_name and event.place_id
                     else (event.game_name or (f"place {event.place_id}" if event.place_id else "*(private)*")))
            return f"Played {where} for {dur}"
        if isinstance(event, status_t):
            return _current_status_desc(event)
        if isinstance(event, wentonline):
            return "User is **online** on Roblox"
        if isinstance(event, wentoffline):
            return "User went **offline**"
        if isinstance(event, wenttostudio):
            return "Opened **Roblox Studio**"
        if isinstance(event, biochanged):
            old = event.old or "*(empty)*"
            new = event.new or "*(empty)*"
            return f"**Before**\n```\n{_truncate(old, 1500)}\n```\n**After**\n```\n{_truncate(new, 1500)}\n```"
        if isinstance(event, unamechanged):
            return f"`@{event.old or '?'}` -> `@{event.new or '?'}`"
        if isinstance(event, dnchanged):
            return f"`{event.old or '?'}` -> `{event.new or '?'}`"
        if isinstance(event, badgeearned):
            link = f"[**{event.badge_name or event.badge_id}**](https://www.roblox.com/badges/{event.badge_id})"
            d = (event.badge_description or "").strip()
            return f"Earned {link}" + (f"\n> {_truncate(d, 800)}" if d else "")
        if isinstance(event, friendadded):
            return f"Added [uid {event.friend_id}](https://www.roblox.com/users/{event.friend_id}/profile) as a friend"
        if isinstance(event, friendremoved):
            return f"Removed [uid {event.friend_id}](https://www.roblox.com/users/{event.friend_id}/profile) from friends"
        if isinstance(event, groupjoined):
            link = f"[**{event.group_name or event.group_id}**](https://www.roblox.com/groups/{event.group_id})"
            return f"Joined {link}" + (f" as **{event.role}**" if event.role else "")
        if isinstance(event, groupleft):
            link = f"[**{event.group_name or event.group_id}**](https://www.roblox.com/groups/{event.group_id})"
            return f"Left {link}"
        if isinstance(event, avatarchanged):
            adds = len(event.added)
            rems = len(event.removed)
            bits = []
            if adds: bits.append(f"+{adds} item(s)")
            if rems: bits.append(f"−{rems} item(s)")
            return "Updated avatar - " + ", ".join(bits) if bits else "Updated avatar"
        if isinstance(event, headshotchanged):
            return "Profile picture updated"
        if isinstance(event, (followerschanged, followingchanged)):
            kind = "Followers" if isinstance(event, followerschanged) else "Following"
            d = event.new - event.old
            sign = "+" if d >= 0 else ""
            return f"**{kind}**: `{event.old:,}` -> `{event.new:,}` ({sign}{d:,})"
        if isinstance(event, friendcntchanged):
            d = event.new - event.old
            sign = "+" if d >= 0 else ""
            note = "" if abs(d) <= 1 else "  *(individual names hidden by user privacy)*"
            return f"**Friends**: `{event.old:,}` -> `{event.new:,}` ({sign}{d:,}){note}"
        if isinstance(event, banchanged):
            return "Account is now **banned**" if event.is_banned else "Account is **active** again"
        if isinstance(event, accountdeleted):
            return ("Profile no longer reachable. Account was **deleted, terminated, "
                    "or hidden by moderation**.")
        if isinstance(event, premiumchanged):
            return ("Now has **Roblox Premium**" if event.is_premium
                    else "Lost **Roblox Premium**")
        if isinstance(event, verifiedchanged):
            return ("Now has the **verified badge**" if event.has_verified_badge
                    else "Lost the **verified badge**")
        if isinstance(event, rbxbadge):
            verb = "Lost" if event.removed else "Was awarded"
            d = (event.badge_description or "").strip()
            return f"{verb} the **{event.badge_name}** Roblox badge" + (f"\n> {_truncate(d, 600)}" if d else "")
        if isinstance(event, together):
            other_link = f"[{event.other_display_name or event.other_username}](https://www.roblox.com/users/{event.other_user_id}/profile)"
            game = (f"[{event.game_name}](https://www.roblox.com/games/{event.place_id})"
                    if event.game_name and event.place_id
                    else (event.game_name or (f"place {event.place_id}" if event.place_id else "the same game")))
            return f"Currently in {game} with {other_link}"
        if isinstance(event, velspike):
            link = f"[{event.game_name or event.place_id}](https://www.roblox.com/games/{event.place_id})"
            return (f"{link} visits surged to **{int(event.visits_per_hour):,}/hr** "
                    f"(baseline ~{int(event.baseline_per_hour):,}/hr)")
        if isinstance(event, limitedacq):
            link = f"[**{event.name or event.asset_id}**](https://www.roblox.com/catalog/{event.asset_id})"
            return f"Acquired {link} - RAP **{event.rap:,}**"
        if isinstance(event, limitedrem):
            return f"No longer owns **{event.name or event.asset_id}**"
        if isinstance(event, rapchanged):
            d = event.new - event.old
            sign = "+" if d >= 0 else ""
            return f"**RAP**: `{event.old:,}` -> `{event.new:,}` ({sign}{d:,})"
        if isinstance(event, visitschanged):
            d = event.new - event.old
            link = f"[{event.game_name or event.place_id}](https://www.roblox.com/games/{event.place_id})"
            return f"{link} visits: `{event.old:,}` -> `{event.new:,}` (+{d:,})"
        if isinstance(event, favchanged):
            d = event.new - event.old
            sign = "+" if d >= 0 else ""
            link = f"[{event.game_name or event.place_id}](https://www.roblox.com/games/{event.place_id})"
            return f"{link} favorites: `{event.old:,}` -> `{event.new:,}` ({sign}{d:,})"
        if isinstance(event, streakms):
            return f"Online **{event.days} days in a row**"
        if isinstance(event, returned):
            return f"Came back online after **{event.days_away} days** away"
        if isinstance(event, dailydigest):
            mins = event.online_seconds // 60
            return (f"Activity over the last **{event.period_hours}h** - "
                    f"online {mins} min across {event.session_count} session(s)")
        return None


    def _fields_for(self, event: event_t) -> list[dict]:
        f: list[dict] = []
        if isinstance(event, joinedgame) and event.place_id:
            f.append({"name": "Place ID", "value": f"`{event.place_id}`", "inline": True})
        elif isinstance(event, sessionended) and event.place_id:
            f.append({"name": "Place ID", "value": f"`{event.place_id}`", "inline": True})
        elif isinstance(event, badgeearned):
            f.append({"name": "Badge ID", "value": f"`{event.badge_id}`", "inline": True})
        elif isinstance(event, groupjoined) or isinstance(event, groupleft):
            f.append({"name": "Group ID", "value": f"`{event.group_id}`", "inline": True})
        elif isinstance(event, avatarchanged):
            if event.added:
                f.append({"name": f"Added ({len(event.added)})", "value": _truncate(", ".join(f"`{a}`" for a in event.added[:15]), 1024), "inline": False})
            if event.removed:
                f.append({"name": f"Removed ({len(event.removed)})", "value": _truncate(", ".join(f"`{a}`" for a in event.removed[:15]), 1024), "inline": False})
        elif isinstance(event, together):
            f.append({"name": "With", "value": f"@{event.other_username}", "inline": True})
            if event.place_id:
                f.append({"name": "Place ID", "value": f"`{event.place_id}`", "inline": True})
        elif isinstance(event, dailydigest):
            mins = event.online_seconds // 60
            f.append({"name": "Online", "value": f"{mins} min", "inline": True})
            f.append({"name": "Sessions", "value": str(event.session_count), "inline": True})
            if event.rap_delta:
                sign = "+" if event.rap_delta >= 0 else ""
                f.append({"name": "RAP delta", "value": f"{sign}{event.rap_delta:,}", "inline": True})
            if event.games_played:
                top = list(event.games_played.items())[:5]
                f.append({"name": "Top games", "value": "\n".join(f"• {g} - {s//60}m" for g, s in top), "inline": False})
            if event.badges_earned:
                names = ", ".join(event.badges_earned[:8])
                if len(event.badges_earned) > 8:
                    names += f" (+{len(event.badges_earned) - 8} more)"
                f.append({"name": f"Badges (+{len(event.badges_earned)})", "value": _truncate(names, 1024), "inline": False})
            social_bits = []
            if event.friends_added:   social_bits.append(f"+{event.friends_added} friend(s)")
            if event.friends_removed: social_bits.append(f"-{event.friends_removed} friend(s)")
            if event.groups_joined:   social_bits.append(f"{len(event.groups_joined)} group(s) joined")
            if event.groups_left:     social_bits.append(f"{len(event.groups_left)} group(s) left")
            if social_bits:
                f.append({"name": "Social", "value": "\n".join(social_bits), "inline": False})
            misc_bits = []
            if event.bio_changed:    misc_bits.append("bio changed")
            if event.avatar_changed: misc_bits.append("avatar changed")
            if misc_bits:
                f.append({"name": "Other", "value": " · ".join(misc_bits), "inline": False})
        return f


    def _title_context(self, event: event_t) -> dict:
        return {
            "display_name": event.display_name or "",
            "username": event.username or "",
            "user_id": event.user_id,
            "event": event.kind,
            "event_pretty": EVENT_PRETTY.get(event.kind, event.kind),
            "event_emoji_title": EVENT_TITLES.get(event.kind, event.kind),
            "old": getattr(event, "old", "") or "",
            "new": getattr(event, "new", "") or "",
        }


def _current_status_desc(e: "status_t") -> str:
    p = (e.presence or "unknown").lower()
    bits: list[str] = []
    if p == "in_game":
        if e.game_name and e.place_id:
            bits.append(f"**In a game** - playing **[{e.game_name}](https://www.roblox.com/games/{e.place_id})**")
        elif e.place_id:
            bits.append(f"**In a game** - [place {e.place_id}](https://www.roblox.com/games/{e.place_id})")
        elif e.game_name:
            bits.append(f"**In a game** - **{e.game_name}**")
        else:
            bits.append("**In a game** - *(game hidden by user privacy)*")
    elif p == "studio":
        bits.append("**In Roblox Studio**")
    elif p == "online":
        bits.append("**Online** on the website")
    elif p == "offline":
        if e.last_online:
            bits.append(f"**Offline** - last seen `{e.last_online}`")
        else:
            bits.append("**Offline**")
    elif p == "invisible":
        bits.append("**Invisible / hidden**")
    else:
        bits.append(f"Status: `{e.presence}`")

    extras: list[str] = []
    if e.current_streak_days:
        extras.append(f"streak `{e.current_streak_days}d`")
    if e.followers_count:
        extras.append(f"followers `{e.followers_count:,}`")
    if e.friends_count:
        extras.append(f"friends `{e.friends_count}`")
    if extras:
        bits.append("  ·  ".join(extras))
    return "\n".join(bits)


def _author_name(event: event_t) -> str:
    dn = event.display_name or ""
    un = event.username or ""
    if dn and un and dn != un:
        return f"{dn} (@{un})"
    return dn or un or f"uid {event.user_id}"


def _truncate(s: str, n: int) -> str:
    s = s or ""
    return s if len(s) <= n else s[: n - 1] + "…"


def _iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
