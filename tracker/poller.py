from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from .config import cfgstore
from .state import statestore
from .dispatcher import dispatcher_t
from .differ import diff
from .roblox_api import rblxclient
from .snapshot import mksnap
from . import history
from . import digest as digest_mod
from .events import sessionended, together, status_t

log = logging.getLogger("tracker.poller")


class poller_t:
    def __init__(self, config: cfgstore, state: statestore, dispatcher: dispatcher_t, state_dir: Path):
        self.config = config
        self.state = state
        self.dispatcher = dispatcher
        self.state_dir = state_dir
        self._stop = asyncio.Event()
        self._cfgchg = asyncio.Event()
        self._loop: asyncio.AbstractEventLoop | None = None

        self._pairs: set = set()
        self._started = False
        config.on_change(self._oncfgchg)

    def _oncfgchg(self, _data: dict) -> None:
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._cfgchg.set)

    async def run(self) -> None:
        self._loop = asyncio.get_running_loop()
        cookie = (self.config.data.get("roblox") or {}).get("cookie") or None
        async with rblxclient(cookie=cookie) as client:
            if client.authed:
                log.info(".ROBLOSECURITY cookie loaded - using authenticated requests")
            while not self._stop.is_set():
                cfg = self.config.data
                self.dispatcher.update_config(cfg)
                interval = max(15, int(cfg.get("poll_interval_seconds", 60)))
                users = cfg.get("users") or []
                enabled = cfg.get("events", {})
                thresholds = cfg.get("thresholds", {})

                started = time.time()
                if users:
                    log.info("polling %d user(s)", len(users))
                    results = await asyncio.gather(
                        *(self._polluser(client, u, enabled, thresholds) for u in users),
                        return_exceptions=True,
                    )

                    snaps_by_uid = {}
                    entries_by_uid = {}
                    for r in results:
                        if isinstance(r, tuple) and len(r) == 2 and r[0] is not None:
                            snap, entry = r
                            snaps_by_uid[snap.user_id] = snap
                            entries_by_uid[snap.user_id] = entry


                    if not self._started and cfg.get("send_status_on_startup", True):
                        await self._emitstatus(snaps_by_uid, entries_by_uid)
                    self._started = True


                    if enabled.get("together_in_game", True):
                        await self._emitpairs(snaps_by_uid, entries_by_uid)
                    self.state.save()

                elapsed = time.time() - started
                wait = max(1.0, interval - elapsed)
                await self._sleepwait(wait)

    async def _sleepwait(self, seconds: float) -> None:
        stop_task = asyncio.create_task(self._stop.wait())
        cfg_task = asyncio.create_task(self._cfgchg.wait())
        try:
            done, pending = await asyncio.wait(
                {stop_task, cfg_task},
                timeout=seconds,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()
            if cfg_task in done:
                self._cfgchg.clear()
                log.info("config changed, re-evaluating")
        finally:
            for t in (stop_task, cfg_task):
                if not t.done():
                    t.cancel()

    async def _polluser(self, client: rblxclient, user_entry: dict,
                         enabled: dict, thresholds: dict):
        uid = user_entry.get("user_id")
        if not isinstance(uid, int):
            return (None, None)
        try:
            new_snap = await mksnap(client, uid, enabled, thresholds=thresholds)
        except Exception as e:
            log.warning("snapshot failed for uid=%s: %s", uid, e)
            return (None, None)

        old_snap = self.state.get(uid)
        events = diff(old_snap, new_snap, enabled, thresholds=thresholds)


        try:
            history.addpres(self.state_dir, new_snap)
        except OSError as e:
            log.warning("presence-log write failed for uid=%s: %s", uid, e)

        cfg = self.config.data
        digest_cfg = _digestcfg(cfg, user_entry)
        suppress = _quiet(digest_cfg, time.time())

        for ev in events:
            try:
                await self.dispatcher.emit(ev, user_entry=user_entry, suppress_webhook=suppress)
            except Exception as e:
                log.warning("dispatch failed: %s", e)
            if isinstance(ev, sessionended):
                try:
                    history.addsess(self.state_dir, new_snap, ev)
                except OSError as e:
                    log.warning("session-log write failed for uid=%s: %s", uid, e)


        try:
            now = time.time()
            if digest_mod.digestdue(new_snap, digest_cfg, now):
                d_event = digest_mod.mkdigest(
                    self.state_dir, new_snap,
                    period_hours=int(digest_cfg.get("period_hours", 24)),
                    now=now,
                )

                await self.dispatcher.emit(d_event, user_entry=user_entry, suppress_webhook=False)
                new_snap.last_digest_date = time.strftime("%Y-%m-%d", time.localtime(now))
        except Exception as e:
            log.warning("digest failed for uid=%s: %s", uid, e)

        self.state.set(new_snap)
        return (new_snap, user_entry)

    async def _emitstatus(self, snaps: dict, entries: dict) -> None:
        coros = []
        for uid, snap in snaps.items():
            entry = entries.get(uid, {})
            ev = status_t(
                user_id=snap.user_id, username=snap.username,
                display_name=snap.display_name, headshot_url=snap.headshot_url,
                presence=snap.presence, game_name=snap.last_location,
                place_id=snap.place_id, last_online=snap.last_online,
                current_streak_days=snap.current_streak_days,
                followers_count=snap.followers_count,
                friends_count=snap.friends_count,
            )

            coros.append(self.dispatcher.emit(ev, user_entry=entry, suppress_webhook=False))
        if coros:
            await asyncio.gather(*coros, return_exceptions=True)

    async def _emitpairs(self, snaps: dict, entries: dict) -> None:

        by_place: dict[int, list[int]] = {}
        for uid, snap in snaps.items():
            if snap.presence == "in_game" and isinstance(snap.place_id, int):
                by_place.setdefault(snap.place_id, []).append(uid)


        observed: set = set()
        for pid, uids in by_place.items():
            if len(uids) < 2:
                continue
            uids_sorted = sorted(uids)
            for i in range(len(uids_sorted)):
                for j in range(i + 1, len(uids_sorted)):
                    observed.add((frozenset({uids_sorted[i], uids_sorted[j]}), pid))


        new_pairings = observed - self._pairs
        self._pairs = observed

        for pair, place_id in new_pairings:
            uid_a, uid_b = sorted(pair)
            sa, sb = snaps[uid_a], snaps[uid_b]
            ea, eb = entries[uid_a], entries[uid_b]
            game_name = sa.last_location or sb.last_location

            await self.dispatcher.emit(
                together(
                    user_id=sa.user_id, username=sa.username,
                    display_name=sa.display_name, headshot_url=sa.headshot_url,
                    other_user_id=sb.user_id, other_username=sb.username,
                    other_display_name=sb.display_name,
                    place_id=place_id, game_name=game_name,
                ),
                user_entry=ea,
            )
            await self.dispatcher.emit(
                together(
                    user_id=sb.user_id, username=sb.username,
                    display_name=sb.display_name, headshot_url=sb.headshot_url,
                    other_user_id=sa.user_id, other_username=sa.username,
                    other_display_name=sa.display_name,
                    place_id=place_id, game_name=game_name,
                ),
                user_entry=eb,
            )

    def stop(self) -> None:
        self._stop.set()


def _digestcfg(cfg: dict, user_entry: dict) -> dict:
    base = dict(cfg.get("digest") or {})
    override = (user_entry or {}).get("digest")
    if isinstance(override, dict):
        base.update(override)
    return base


def _quiet(digest_cfg: dict, now: float) -> bool:
    qh = (digest_cfg.get("quiet_hours") or "").strip()
    if not qh:
        return False
    try:
        start_s, end_s = qh.split("-", 1)
        start, end = int(start_s), int(end_s)
    except ValueError:
        return False
    h = time.localtime(now).tm_hour
    if start == end:
        return False
    if start < end:
        return start <= h < end

    return h >= start or h < end
