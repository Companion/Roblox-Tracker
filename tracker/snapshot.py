from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional

from .roblox_api import rblxclient, rblxerror

_log = logging.getLogger("tracker.snapshot")
_warned: set[tuple[int, str]] = set()


def _warnonce(user_id: int, key: str, msg: str) -> None:
    k = (user_id, key)
    if k in _warned:
        return
    _warned.add(k)
    _log.info(msg)


PRESENCE_NAMES = {
    0: "offline",
    1: "online",
    2: "in_game",
    3: "studio",
    4: "invisible",
}


@dataclass
class snapshot_t:
    user_id: int
    fetched_at: float


    username: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    created: Optional[str] = None
    is_banned: Optional[bool] = None
    account_deleted: bool = False
    has_verified_badge: Optional[bool] = None
    is_premium: Optional[bool] = None
    roblox_badge_ids: list[int] = field(default_factory=list)
    roblox_badges_meta: dict[str, dict] = field(default_factory=dict)


    presence: Optional[str] = None
    last_location: Optional[str] = None
    place_id: Optional[int] = None
    universe_id: Optional[int] = None
    game_id: Optional[str] = None
    last_online: Optional[str] = None


    headshot_url: Optional[str] = None
    avatar_asset_ids: list[int] = field(default_factory=list)


    friends_count: int = 0
    followers_count: int = 0
    following_count: int = 0
    friend_ids: list[int] = field(default_factory=list)


    badge_ids: list[int] = field(default_factory=list)
    badges_meta: dict[str, dict] = field(default_factory=dict)
    group_ids: list[int] = field(default_factory=list)
    groups_meta: dict[str, dict] = field(default_factory=dict)


    collectible_user_asset_ids: list[int] = field(default_factory=list)
    collectibles_meta: dict[str, dict] = field(default_factory=dict)
    total_rap: int = 0


    user_games: dict[str, dict] = field(default_factory=dict)


    current_session: Optional[dict] = None


    current_streak_days: int = 0
    longest_streak_days: int = 0
    last_online_date: Optional[str] = None


    last_digest_date: Optional[str] = None


    visit_velocity_baseline: dict[str, float] = field(default_factory=dict)


    fetched_sections: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "snapshot_t":

        known = {f for f in cls.__dataclass_fields__}
        clean = {k: v for k, v in d.items() if k in known}
        return cls(**clean)


async def mksnap(client: rblxclient, user_id: int, enabled: dict[str, bool],
                         thresholds: Optional[dict] = None) -> snapshot_t:
    import time
    snap = snapshot_t(user_id=user_id, fetched_at=time.time())
    fetched: dict[str, bool] = {}

    needs_user_info = any(enabled.get(k, True) for k in ("username", "display_name", "bio", "ban"))
    needs_presence = enabled.get("presence", True)
    needs_headshot = enabled.get("headshot", True)
    needs_avatar = enabled.get("avatar", True)
    needs_friends = enabled.get("friends", True) or enabled.get("friends_count", True)
    needs_followers = enabled.get("followers", True)
    needs_following = enabled.get("following", True)
    needs_badges = enabled.get("badges", True)
    needs_groups = enabled.get("groups", True)
    needs_collectibles = enabled.get("collectibles", True) or enabled.get("rap", True)
    needs_user_games = enabled.get("user_games", True)
    needs_premium = enabled.get("premium", True)
    needs_roblox_badges = enabled.get("roblox_badges", True)

    async def _user_info():
        try:
            d = await client.user_info(user_id)
            snap.username = d.get("name")
            snap.display_name = d.get("displayName")
            snap.description = d.get("description")
            snap.created = d.get("created")
            snap.is_banned = d.get("isBanned")
            snap.has_verified_badge = d.get("hasVerifiedBadge")
            snap.account_deleted = False
            fetched["user_info"] = True
        except rblxerror as e:

            if "404" in str(e):
                snap.account_deleted = True
                fetched["user_info"] = True
            else:
                fetched["user_info"] = False

    async def _presence():
        try:
            p = await client.presence(user_id)
            ptype = p.get("userPresenceType")
            snap.presence = PRESENCE_NAMES.get(ptype, "unknown") if ptype is not None else None
            snap.last_location = p.get("lastLocation")
            snap.place_id = p.get("placeId")
            snap.universe_id = p.get("universeId")
            snap.game_id = p.get("gameId")
            snap.last_online = p.get("lastOnline")
            fetched["presence"] = True


            if snap.presence == "in_game" and not snap.place_id and not snap.last_location:
                hint = ("set roblox.cookie + add this user as a friend to see game details"
                        if not getattr(client, "authed", False)
                        else "this user's join-privacy is friends-only and you're not on their list")
                _warnonce(user_id, "presence_private",
                           f"uid={user_id}: in_game but place hidden by user privacy ({hint})")
        except rblxerror:
            fetched["presence"] = False

    async def _headshot():
        try:
            snap.headshot_url = await client.headshot(user_id)
            fetched["headshot"] = True
        except rblxerror:
            fetched["headshot"] = False

    async def _avatar():
        try:
            d = await client.avatar(user_id)
            assets = d.get("assets") or []
            snap.avatar_asset_ids = sorted(int(a["id"]) for a in assets if "id" in a)
            fetched["avatar"] = True
        except rblxerror:
            fetched["avatar"] = False

    async def _friends():


        list_ok = False
        try:
            fl = await client.friends(user_id)
            snap.friend_ids = sorted(int(f["id"]) for f in fl if "id" in f)
            list_ok = True
        except rblxerror as e:
            if "403" in str(e):
                _warnonce(user_id, "friends_403",
                           f"uid={user_id}: friends list restricted (HTTP 403) - likely UK / privacy-locked account; falling back to count-only tracking")
        fetched["friends"] = list_ok

        try:
            snap.friends_count = await client.friends_count(user_id)
            fetched["friends_count"] = True
        except rblxerror:

            if list_ok:
                snap.friends_count = len(snap.friend_ids)
                fetched["friends_count"] = True
            else:
                fetched["friends_count"] = False

    async def _followers():
        try:
            snap.followers_count = await client.followers_count(user_id)
            fetched["followers"] = True
        except rblxerror:
            fetched["followers"] = False

    async def _following():
        try:
            snap.following_count = await client.following_count(user_id)
            fetched["following"] = True
        except rblxerror:
            fetched["following"] = False

    async def _badges():
        try:
            bl = await client.badges(user_id)
            snap.badge_ids = sorted(int(b["id"]) for b in bl if "id" in b)
            snap.badges_meta = {
                str(b["id"]): {"name": b.get("name"), "description": b.get("description")}
                for b in bl if "id" in b
            }
            fetched["badges"] = True
        except rblxerror:
            fetched["badges"] = False

    async def _groups():
        try:
            gl = await client.groups(user_id)
            snap.group_ids = sorted(int(g["group"]["id"]) for g in gl if g.get("group"))
            snap.groups_meta = {
                str(g["group"]["id"]): {
                    "name": g["group"].get("name"),
                    "role": (g.get("role") or {}).get("name"),
                }
                for g in gl if g.get("group")
            }
            fetched["groups"] = True
        except rblxerror:
            fetched["groups"] = False

    async def _collectibles():
        try:
            max_pages = int((thresholds or {}).get("collectibles_max_pages", 5))
            cl = await client.collectibles(user_id, max_pages=max_pages)
            uaids: list[int] = []
            meta: dict[str, dict] = {}
            rap = 0
            for item in cl:
                uaid = item.get("userAssetId")
                if uaid is None:
                    continue
                uaids.append(int(uaid))
                price = int(item.get("recentAveragePrice") or 0)
                rap += price
                meta[str(int(uaid))] = {
                    "name": item.get("name"),
                    "asset_id": item.get("assetId"),
                    "rap": price,
                }
            snap.collectible_user_asset_ids = sorted(uaids)
            snap.collectibles_meta = meta
            snap.total_rap = rap
            fetched["collectibles"] = True
        except rblxerror as e:
            fetched["collectibles"] = False
            if "403" in str(e):
                _warnonce(user_id, "collectibles_403",
                           f"uid={user_id}: collectibles inventory is private (HTTP 403); set roblox.cookie in config to track it")

    async def _premium():
        try:
            snap.is_premium = await client.premium(user_id)
            fetched["premium"] = True
        except rblxerror as e:
            fetched["premium"] = False
            if "403" in str(e):
                _warnonce(user_id, "premium_403",
                           f"uid={user_id}: premium endpoint returns 403 (auth required); skipping")

    async def _roblox_badges():
        try:
            rb = await client.roblox_badges(user_id)
            snap.roblox_badge_ids = sorted(int(b["id"]) for b in rb if "id" in b)
            snap.roblox_badges_meta = {
                str(int(b["id"])): {
                    "name": b.get("name"),
                    "description": b.get("description"),
                    "image_url": b.get("imageUrl"),
                }
                for b in rb if "id" in b
            }
            fetched["roblox_badges"] = True
        except rblxerror:
            fetched["roblox_badges"] = False

    async def _user_games():
        try:
            gl = await client.user_games(user_id)
            ug: dict[str, dict] = {}
            for g in gl:
                pid = g.get("rootPlace", {}).get("id") if isinstance(g.get("rootPlace"), dict) else g.get("id")
                if pid is None:
                    continue
                ug[str(int(pid))] = {
                    "name": g.get("name"),
                    "visits": int(g.get("placeVisits") or 0),
                    "favorites": int(g.get("favoritedCount") or 0),
                }
            snap.user_games = ug
            fetched["user_games"] = True
        except rblxerror:
            fetched["user_games"] = False

    tasks = []
    if needs_user_info: tasks.append(_user_info())
    if needs_presence: tasks.append(_presence())
    if needs_headshot: tasks.append(_headshot())
    if needs_avatar: tasks.append(_avatar())
    if needs_friends: tasks.append(_friends())
    if needs_followers: tasks.append(_followers())
    if needs_following: tasks.append(_following())
    if needs_badges: tasks.append(_badges())
    if needs_groups: tasks.append(_groups())
    if needs_collectibles: tasks.append(_collectibles())
    if needs_user_games: tasks.append(_user_games())
    if needs_premium: tasks.append(_premium())
    if needs_roblox_badges: tasks.append(_roblox_badges())

    await asyncio.gather(*tasks)
    snap.fetched_sections = fetched
    return snap
