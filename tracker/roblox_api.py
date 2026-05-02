from __future__ import annotations

import asyncio
import httpx
from typing import Optional

USER_AGENT = "rblx-tracker/0.2 (+https://github.com/local)"

PRESENCE_URL = "https://presence.roblox.com/v1/presence/users"
USER_INFO_URL = "https://users.roblox.com/v1/users/{id}"
USERNAME_LOOKUP_URL = "https://users.roblox.com/v1/usernames/users"
USERNAME_HISTORY_URL = "https://users.roblox.com/v1/users/{id}/username-history"
HEADSHOT_URL = "https://thumbnails.roblox.com/v1/users/avatar-headshot"
AVATAR_URL = "https://avatar.roblox.com/v1/users/{id}/avatar"
FRIENDS_URL = "https://friends.roblox.com/v1/users/{id}/friends"
FRIENDS_COUNT_URL = "https://friends.roblox.com/v1/users/{id}/friends/count"
FOLLOWERS_COUNT_URL = "https://friends.roblox.com/v1/users/{id}/followers/count"
FOLLOWING_COUNT_URL = "https://friends.roblox.com/v1/users/{id}/followings/count"
BADGES_URL = "https://badges.roblox.com/v1/users/{id}/badges"
GROUPS_URL = "https://groups.roblox.com/v2/users/{id}/groups/roles"
COLLECTIBLES_URL = "https://inventory.roblox.com/v1/users/{id}/assets/collectibles"
USER_GAMES_URL = "https://games.roblox.com/v2/users/{id}/games"
PREMIUM_URL = "https://premiumfeatures.roblox.com/v1/users/{id}/validate-membership"
ROBLOX_BADGES_URL = "https://accountinformation.roblox.com/v1/users/{id}/roblox-badges"


class rblxerror(Exception):
    pass


class rblxclient:
    def __init__(self, timeout: float = 15.0, cookie: Optional[str] = None):
        cookies = {".ROBLOSECURITY": cookie} if cookie else None
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            cookies=cookies,
        )
        self._authed = bool(cookie)

    @property
    def authed(self) -> bool:
        return self._authed

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.aclose()

    async def _get(self, url: str, **kwargs) -> dict:
        for attempt in range(3):
            try:
                r = await self._client.get(url, **kwargs)
                if r.status_code == 429:
                    await asyncio.sleep(2 ** attempt)
                    continue


                if 400 <= r.status_code < 500:
                    raise rblxerror(f"GET {url} -> HTTP {r.status_code}")
                r.raise_for_status()
                return r.json()
            except rblxerror:
                raise
            except httpx.HTTPError as e:
                if attempt == 2:
                    raise rblxerror(f"GET {url} failed: {e}") from e
                await asyncio.sleep(1 + attempt)
        raise rblxerror(f"GET {url} exhausted retries")

    async def _post(self, url: str, json: dict) -> dict:
        for attempt in range(3):
            try:
                r = await self._client.post(url, json=json)
                if r.status_code == 429:
                    await asyncio.sleep(2 ** attempt)
                    continue
                if 400 <= r.status_code < 500:
                    raise rblxerror(f"POST {url} -> HTTP {r.status_code}")
                r.raise_for_status()
                return r.json()
            except rblxerror:
                raise
            except httpx.HTTPError as e:
                if attempt == 2:
                    raise rblxerror(f"POST {url} failed: {e}") from e
                await asyncio.sleep(1 + attempt)
        raise rblxerror(f"POST {url} exhausted retries")

    async def resolve_username(self, username: str) -> Optional[int]:
        data = await self._post(
            USERNAME_LOOKUP_URL,
            {"usernames": [username], "excludeBannedUsers": False},
        )
        items = data.get("data") or []
        if not items:
            return None
        return int(items[0]["id"])

    async def user_info(self, user_id: int) -> dict:
        return await self._get(USER_INFO_URL.format(id=user_id))

    async def presence(self, user_id: int) -> dict:
        data = await self._post(PRESENCE_URL, {"userIds": [user_id]})
        items = data.get("userPresences") or []
        return items[0] if items else {}

    async def headshot(self, user_id: int) -> Optional[str]:
        data = await self._get(
            HEADSHOT_URL,
            params={"userIds": user_id, "size": "150x150", "format": "Png", "isCircular": "false"},
        )
        items = data.get("data") or []
        if not items:
            return None
        return items[0].get("imageUrl")

    async def avatar(self, user_id: int) -> dict:
        return await self._get(AVATAR_URL.format(id=user_id))

    async def friends(self, user_id: int) -> list[dict]:
        data = await self._get(FRIENDS_URL.format(id=user_id))
        return data.get("data") or []

    async def friends_count(self, user_id: int) -> int:
        data = await self._get(FRIENDS_COUNT_URL.format(id=user_id))
        return int(data.get("count", 0))

    async def followers_count(self, user_id: int) -> int:
        data = await self._get(FOLLOWERS_COUNT_URL.format(id=user_id))
        return int(data.get("count", 0))

    async def following_count(self, user_id: int) -> int:
        data = await self._get(FOLLOWING_COUNT_URL.format(id=user_id))
        return int(data.get("count", 0))

    async def badges(self, user_id: int, limit: int = 100) -> list[dict]:
        data = await self._get(
            BADGES_URL.format(id=user_id),
            params={"limit": limit, "sortOrder": "Desc"},
        )
        return data.get("data") or []

    async def groups(self, user_id: int) -> list[dict]:
        data = await self._get(GROUPS_URL.format(id=user_id))
        return data.get("data") or []

    async def unamehist(self, user_id: int, limit: int = 50) -> list[str]:
        data = await self._get(
            USERNAME_HISTORY_URL.format(id=user_id),
            params={"limit": limit, "sortOrder": "Desc"},
        )
        return [item.get("name") for item in (data.get("data") or []) if item.get("name")]

    async def collectibles(self, user_id: int, limit: int = 100, max_pages: int = 5) -> list[dict]:
        all_items: list[dict] = []
        cursor = ""
        for _ in range(max_pages):
            params = {"sortOrder": "Asc", "limit": limit}
            if cursor:
                params["cursor"] = cursor
            data = await self._get(COLLECTIBLES_URL.format(id=user_id), params=params)
            all_items.extend(data.get("data") or [])
            cursor = data.get("nextPageCursor") or ""
            if not cursor:
                break
        return all_items

    async def premium(self, user_id: int) -> bool:

        for attempt in range(3):
            try:
                r = await self._client.get(PREMIUM_URL.format(id=user_id))
                if r.status_code == 429:
                    await asyncio.sleep(2 ** attempt); continue
                if 400 <= r.status_code < 500:
                    raise rblxerror(f"GET premium -> HTTP {r.status_code}")
                r.raise_for_status()
                return bool(r.json())
            except rblxerror:
                raise
            except httpx.HTTPError as e:
                if attempt == 2:
                    raise rblxerror(f"GET premium failed: {e}") from e
                await asyncio.sleep(1 + attempt)
        raise rblxerror("GET premium exhausted retries")

    async def roblox_badges(self, user_id: int) -> list[dict]:
        return await self._get_list(ROBLOX_BADGES_URL.format(id=user_id))

    async def _get_list(self, url: str) -> list[dict]:
        r = await self._get(url)

        if isinstance(r, list):
            return r
        if isinstance(r, dict):
            return r.get("data") or []
        return []

    async def user_games(self, user_id: int, limit: int = 50) -> list[dict]:
        data = await self._get(
            USER_GAMES_URL.format(id=user_id),
            params={"accessFilter": "Public", "limit": limit, "sortOrder": "Desc"},
        )
        return data.get("data") or []
