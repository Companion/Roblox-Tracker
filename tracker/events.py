from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class event_t:
    user_id: int
    username: Optional[str]
    display_name: Optional[str]
    headshot_url: Optional[str]
    type: str = "event"

    @property
    def kind(self) -> str:
        return self.type

    def summary(self) -> str:
        return f"{self.display_name or self.username or self.user_id}: {self.type}"


@dataclass
class status_t(event_t):
    type: str = "current_status"
    presence: Optional[str] = None
    game_name: Optional[str] = None
    place_id: Optional[int] = None
    last_online: Optional[str] = None
    current_streak_days: int = 0
    followers_count: int = 0
    friends_count: int = 0
    def summary(self) -> str:
        return f"{self.display_name} is currently {self.presence or 'unknown'}"


@dataclass
class wentonline(event_t):
    type: str = "went_online"
    def summary(self) -> str:
        return f"{self.display_name} came online"


@dataclass
class wentoffline(event_t):
    type: str = "went_offline"
    def summary(self) -> str:
        return f"{self.display_name} went offline"


@dataclass
class joinedgame(event_t):
    type: str = "joined_game"
    game_name: Optional[str] = None
    place_id: Optional[int] = None
    def summary(self) -> str:
        where = self.game_name or (str(self.place_id) if self.place_id else "(private - game hidden by user)")
        return f"{self.display_name} joined game: {where}"


@dataclass
class leftgame(event_t):
    type: str = "left_game"
    game_name: Optional[str] = None
    def summary(self) -> str:
        where = self.game_name or "(private)"
        return f"{self.display_name} left game: {where}"


@dataclass
class wenttostudio(event_t):
    type: str = "went_to_studio"
    def summary(self) -> str:
        return f"{self.display_name} opened Roblox Studio"


@dataclass
class biochanged(event_t):
    type: str = "bio_changed"
    old: Optional[str] = None
    new: Optional[str] = None
    def summary(self) -> str:
        return f"{self.display_name} changed their bio"


@dataclass
class unamechanged(event_t):
    type: str = "username_changed"
    old: Optional[str] = None
    new: Optional[str] = None
    def summary(self) -> str:
        return f"username: @{self.old} -> @{self.new}"


@dataclass
class dnchanged(event_t):
    type: str = "display_name_changed"
    old: Optional[str] = None
    new: Optional[str] = None
    def summary(self) -> str:
        return f"display name: {self.old} -> {self.new}"


@dataclass
class badgeearned(event_t):
    type: str = "badge_earned"
    badge_id: int = 0
    badge_name: Optional[str] = None
    badge_description: Optional[str] = None
    def summary(self) -> str:
        return f"{self.display_name} earned badge: {self.badge_name}"


@dataclass
class friendcntchanged(event_t):
    type: str = "friend_count_changed"
    old: int = 0
    new: int = 0
    def summary(self) -> str:
        d = self.new - self.old
        sign = "+" if d > 0 else ""
        return f"{self.display_name} friends: {self.old} -> {self.new} ({sign}{d})"


@dataclass
class friendadded(event_t):
    type: str = "friend_added"
    friend_id: int = 0
    def summary(self) -> str:
        return f"{self.display_name} added friend (id={self.friend_id})"


@dataclass
class friendremoved(event_t):
    type: str = "friend_removed"
    friend_id: int = 0
    def summary(self) -> str:
        return f"{self.display_name} removed friend (id={self.friend_id})"


@dataclass
class groupjoined(event_t):
    type: str = "group_joined"
    group_id: int = 0
    group_name: Optional[str] = None
    role: Optional[str] = None
    def summary(self) -> str:
        return f"{self.display_name} joined group: {self.group_name}"


@dataclass
class groupleft(event_t):
    type: str = "group_left"
    group_id: int = 0
    group_name: Optional[str] = None
    def summary(self) -> str:
        return f"{self.display_name} left group: {self.group_name}"


@dataclass
class avatarchanged(event_t):
    type: str = "avatar_changed"
    added: list[int] = field(default_factory=list)
    removed: list[int] = field(default_factory=list)
    def summary(self) -> str:
        return f"{self.display_name} changed avatar (+{len(self.added)} / -{len(self.removed)})"


@dataclass
class headshotchanged(event_t):
    type: str = "headshot_changed"
    old_url: Optional[str] = None
    new_url: Optional[str] = None
    def summary(self) -> str:
        return f"{self.display_name} changed profile picture"


@dataclass
class followerschanged(event_t):
    type: str = "followers_changed"
    old: int = 0
    new: int = 0
    def summary(self) -> str:
        delta = self.new - self.old
        sign = "+" if delta > 0 else ""
        return f"{self.display_name} followers: {self.old} -> {self.new} ({sign}{delta})"


@dataclass
class followingchanged(event_t):
    type: str = "following_changed"
    old: int = 0
    new: int = 0
    def summary(self) -> str:
        delta = self.new - self.old
        sign = "+" if delta > 0 else ""
        return f"{self.display_name} following: {self.old} -> {self.new} ({sign}{delta})"


@dataclass
class banchanged(event_t):
    type: str = "ban_state_changed"
    is_banned: bool = False
    def summary(self) -> str:
        return f"{self.display_name} {'BANNED' if self.is_banned else 'unbanned'}"


@dataclass
class premiumchanged(event_t):
    type: str = "premium_changed"
    is_premium: bool = False
    def summary(self) -> str:
        return f"{self.display_name} {'gained' if self.is_premium else 'lost'} Roblox Premium"


@dataclass
class verifiedchanged(event_t):
    type: str = "verified_badge_changed"
    has_verified_badge: bool = False
    def summary(self) -> str:
        return f"{self.display_name} {'gained' if self.has_verified_badge else 'lost'} the verified badge"


@dataclass
class rbxbadge(event_t):
    type: str = "roblox_badge_granted"
    badge_id: int = 0
    badge_name: Optional[str] = None
    badge_description: Optional[str] = None
    image_url: Optional[str] = None
    removed: bool = False
    def summary(self) -> str:
        verb = "lost" if self.removed else "was granted"
        return f"{self.display_name} {verb} Roblox badge: {self.badge_name}"


@dataclass
class together(event_t):
    type: str = "together_in_game"
    other_user_id: int = 0
    other_username: Optional[str] = None
    other_display_name: Optional[str] = None
    place_id: Optional[int] = None
    game_name: Optional[str] = None
    def summary(self) -> str:
        return f"{self.display_name} is playing {self.game_name or self.place_id} with {self.other_display_name}"


@dataclass
class velspike(event_t):
    type: str = "visit_velocity_spike"
    place_id: int = 0
    game_name: Optional[str] = None
    visits_per_hour: float = 0.0
    baseline_per_hour: float = 0.0
    def summary(self) -> str:
        return (f"{self.display_name}'s '{self.game_name}' visit velocity spiked to "
                f"{int(self.visits_per_hour)}/hr (baseline {int(self.baseline_per_hour)}/hr)")


@dataclass
class accountdeleted(event_t):
    type: str = "account_deleted"
    def summary(self) -> str:
        return f"{self.display_name or self.username or self.user_id}: account no longer accessible"


@dataclass
class streakms(event_t):
    type: str = "streak_milestone"
    days: int = 0
    def summary(self) -> str:
        return f"{self.display_name} has been online {self.days} days in a row"


@dataclass
class returned(event_t):
    type: str = "returned_after_absence"
    days_away: int = 0
    def summary(self) -> str:
        return f"{self.display_name} is back online after {self.days_away} days"


@dataclass
class dailydigest(event_t):
    type: str = "daily_digest"
    period_hours: int = 24
    period_started_at: float = 0.0
    period_ended_at: float = 0.0
    online_seconds: int = 0
    session_count: int = 0
    games_played: dict[str, int] = field(default_factory=dict)
    badges_earned: list[str] = field(default_factory=list)
    friends_added: int = 0
    friends_removed: int = 0
    groups_joined: list[str] = field(default_factory=list)
    groups_left: list[str] = field(default_factory=list)
    bio_changed: bool = False
    avatar_changed: bool = False
    rap_delta: int = 0
    other_event_counts: dict[str, int] = field(default_factory=dict)
    def summary(self) -> str:
        return f"{self.display_name} - daily digest ({self.session_count} sessions, {self.online_seconds//60}m online)"


@dataclass
class sessionended(event_t):
    type: str = "game_session_ended"
    place_id: Optional[int] = None
    game_name: Optional[str] = None
    duration_seconds: int = 0
    started_at: float = 0.0
    ended_at: float = 0.0
    def summary(self) -> str:
        m, s = divmod(self.duration_seconds, 60)
        h, m = divmod(m, 60)
        d = f"{h}h{m}m" if h else (f"{m}m{s}s" if m else f"{s}s")
        where = self.game_name or (str(self.place_id) if self.place_id else "(private)")
        return f"{self.display_name} played {where} for {d}"


@dataclass
class limitedacq(event_t):
    type: str = "limited_acquired"
    user_asset_id: int = 0
    asset_id: Optional[int] = None
    name: Optional[str] = None
    rap: int = 0
    def summary(self) -> str:
        return f"{self.display_name} acquired limited: {self.name} (RAP {self.rap})"


@dataclass
class limitedrem(event_t):
    type: str = "limited_removed"
    user_asset_id: int = 0
    asset_id: Optional[int] = None
    name: Optional[str] = None
    def summary(self) -> str:
        return f"{self.display_name} no longer owns limited: {self.name}"


@dataclass
class rapchanged(event_t):
    type: str = "rap_changed"
    old: int = 0
    new: int = 0
    def summary(self) -> str:
        d = self.new - self.old
        sign = "+" if d >= 0 else ""
        return f"{self.display_name} RAP: {self.old} -> {self.new} ({sign}{d})"


@dataclass
class visitschanged(event_t):
    type: str = "game_visits_changed"
    place_id: int = 0
    game_name: Optional[str] = None
    old: int = 0
    new: int = 0
    def summary(self) -> str:
        d = self.new - self.old
        return f"{self.display_name}'s '{self.game_name}' visits: {self.old} -> {self.new} (+{d})"


@dataclass
class favchanged(event_t):
    type: str = "game_favorites_changed"
    place_id: int = 0
    game_name: Optional[str] = None
    old: int = 0
    new: int = 0
    def summary(self) -> str:
        d = self.new - self.old
        sign = "+" if d >= 0 else ""
        return f"{self.display_name}'s '{self.game_name}' favorites: {self.old} -> {self.new} ({sign}{d})"


EVENT_COLORS: dict[str, int] = {
    "went_online":          0x57F287,
    "joined_game":          0x57F287,
    "went_to_studio":       0x57F287,
    "badge_earned":         0x57F287,
    "friend_added":         0x57F287,
    "went_offline":         0xED4245,
    "left_game":            0xED4245,
    "friend_removed":       0xED4245,
    "ban_state_changed":    0xED4245,
    "bio_changed":          0x5865F2,
    "username_changed":     0x5865F2,
    "display_name_changed": 0x5865F2,
    "avatar_changed":       0x5865F2,
    "headshot_changed":     0x5865F2,
    "group_joined":         0xFEE75C,
    "group_left":           0xFEE75C,
    "followers_changed":    0x9B59B6,
    "following_changed":    0x9B59B6,
    "game_session_ended":   0x95A5A6,
    "limited_acquired":     0xF1C40F,
    "limited_removed":      0xE67E22,
    "rap_changed":          0xF1C40F,
    "game_visits_changed":  0x1ABC9C,
    "game_favorites_changed": 0x1ABC9C,
    "account_deleted":      0x000000,
    "streak_milestone":     0x57F287,
    "returned_after_absence": 0x5865F2,
    "daily_digest":         0x9B59B6,
    "premium_changed":      0xF1C40F,
    "verified_badge_changed": 0x1DA1F2,
    "roblox_badge_granted": 0xFF7F50,
    "together_in_game":     0x57F287,
    "visit_velocity_spike": 0x1ABC9C,
    "current_status":       0x95A5A6,
    "friend_count_changed": 0x9B59B6,
}

DEFAULT_TITLE_TEMPLATE = "{display_name} (@{username}) - {event_pretty}"

EVENT_PRETTY: dict[str, str] = {
    "went_online":          "came online",
    "went_offline":         "went offline",
    "joined_game":          "joined a game",
    "left_game":            "left the game",
    "went_to_studio":       "opened Studio",
    "bio_changed":          "changed bio",
    "username_changed":     "changed username",
    "display_name_changed": "changed display name",
    "badge_earned":         "earned a badge",
    "friend_added":         "added a friend",
    "friend_removed":       "removed a friend",
    "group_joined":         "joined a group",
    "group_left":           "left a group",
    "avatar_changed":       "changed avatar",
    "headshot_changed":     "changed profile picture",
    "followers_changed":    "follower count changed",
    "following_changed":    "following count changed",
    "ban_state_changed":    "ban state changed",
    "game_session_ended":   "finished a game session",
    "limited_acquired":     "acquired a limited",
    "limited_removed":      "lost a limited",
    "rap_changed":          "RAP changed",
    "game_visits_changed":  "game visits changed",
    "game_favorites_changed": "game favorites changed",
    "account_deleted":      "account deleted/terminated",
    "streak_milestone":     "online streak milestone",
    "returned_after_absence": "returned after absence",
    "daily_digest":         "daily digest",
    "premium_changed":      "Premium status changed",
    "verified_badge_changed": "verified badge changed",
    "roblox_badge_granted": "Roblox badge changed",
    "together_in_game":     "co-presence in game",
    "visit_velocity_spike": "visit velocity spike",
    "current_status":       "current status",
    "friend_count_changed": "friend count changed",
}
