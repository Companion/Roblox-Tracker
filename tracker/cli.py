from __future__ import annotations

import asyncio
import json
import logging
import re
import signal
import sys
import time
from pathlib import Path

import click

from .config import cfgstore
from .state import statestore
from .dispatcher import dispatcher_t
from .poller import poller_t
from .roblox_api import rblxclient
from .events import event_t
from . import history


def _basedir() -> Path:
    return Path.cwd()


def _cfgpath() -> Path:
    return _basedir() / "config.json"


def _statedir() -> Path:
    return _basedir() / "tracked users"


def _legacyfile() -> Path:
    return _basedir() / "state.json"


def _mkstate() -> statestore:
    return statestore(_statedir(), legacy_state_file=_legacyfile())


def _cookie() -> str | None:
    cfg = cfgstore(_cfgpath())
    return ((cfg.data.get("roblox") or {}).get("cookie")) or None


def _resolveuser(user: str, cookie: str | None = None):
    async def _go():
        async with rblxclient(cookie=cookie) as client:
            if user.isdigit():
                uid = int(user)
                info = await client.user_info(uid)
                return uid, info.get("name") or user
            uid = await client.resolve_username(user)
            if uid is None:
                return None, None
            info = await client.user_info(uid)
            return uid, info.get("name") or user
    return asyncio.run(_go())


def _findstate(query: str):
    state = _mkstate()
    if query.isdigit():
        return state.get(int(query))
    for uid, snap in state._snapshots.items():
        if (snap.username or "").lower() == query.lower():
            return snap
    return None


def _fmtdur(seconds: int) -> str:
    s = max(0, int(seconds))
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    if h: return f"{h}h{m:02d}m"
    if m: return f"{m}m{s:02d}s"
    return f"{s}s"


@click.group()
def cli():
    pass


@cli.command()
@click.option("--verbose/--quiet", default=True)
def run(verbose: bool):
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    cfg = cfgstore(_cfgpath())
    cfg.start_watching()
    state = _mkstate()
    dispatcher = dispatcher_t(cfg.data, _basedir(), state_dir=_statedir())
    poller = poller_t(cfg, state, dispatcher, _statedir())

    async def _main():
        loop = asyncio.get_running_loop()
        if sys.platform != "win32":
            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.add_signal_handler(sig, poller.stop)
                except NotImplementedError:
                    pass
        try:
            await poller.run()
        finally:
            await dispatcher.aclose()
            cfg.stop_watching()

    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        poller.stop()


@cli.command()
@click.argument("user")
@click.option("--alias", default=None, help="Friendly label for this user")
def add(user: str, alias: str | None):
    cookie = _cookie()
    uid, resolved_name = _resolveuser(user, cookie=cookie)
    if uid is None:
        click.echo(f"could not resolve user: {user}", err=True)
        sys.exit(1)


    async def _hist():
        async with rblxclient(cookie=cookie) as client:
            try:
                return await client.unamehist(uid)
            except Exception:
                return []
    prior = asyncio.run(_hist())

    cfg = cfgstore(_cfgpath())

    def _mut(d):
        users = d.setdefault("users", [])
        for u in users:
            if u.get("user_id") == uid:
                if alias:
                    u["alias"] = alias
                return
        entry = {"user_id": uid, "username": resolved_name}
        if alias:
            entry["alias"] = alias
        users.append(entry)

    cfg.mutate(_mut)
    click.echo(f"added {resolved_name} (uid={uid})")
    if prior:
        click.echo(f"  prior usernames: {', '.join(prior)}")


@cli.command()
@click.argument("user")
def remove(user: str):
    cfg = cfgstore(_cfgpath())
    state = _mkstate()

    target_uid = None
    target_name = None
    for u in cfg.data.get("users", []):
        if user.isdigit() and u.get("user_id") == int(user):
            target_uid = u["user_id"]; target_name = u.get("username"); break
        if u.get("username", "").lower() == user.lower():
            target_uid = u["user_id"]; target_name = u.get("username"); break

    if target_uid is None:
        click.echo(f"not found in config: {user}", err=True)
        sys.exit(1)

    cfg.mutate(lambda d: d.update(users=[u for u in d.get("users", []) if u.get("user_id") != target_uid]))
    state.remove(target_uid)
    state.save()
    click.echo(f"removed {target_name} (uid={target_uid})")


@cli.command(name="list")
def list_cmd():
    cfg = cfgstore(_cfgpath())
    users = cfg.data.get("users", [])
    if not users:
        click.echo("(no users)")
        return
    for u in users:
        line = f"{u.get('user_id'):>15}  @{u.get('username','')}"
        if u.get("alias"):
            line += f"  ({u['alias']})"
        if u.get("webhook"):
            line += "  [own webhook]"
        click.echo(line)


@cli.command(name="reset")
@click.option("--yes", "assume_yes", is_flag=True, default=False,
              help="Skip the confirmation prompt.")
@click.option("--config", "wipe_config", is_flag=True, default=False,
              help="Also delete config.json (loses webhook URL, cookie, all settings).")
def reset_cmd(assume_yes: bool, wipe_config: bool):
    import shutil

    base = _basedir()
    state_dir = _statedir()
    legacy_state = _legacyfile()
    events_log = base / "events.log"
    config_file = _cfgpath()

    targets: list[tuple[str, Path]] = []
    if state_dir.exists():
        n = sum(1 for _ in state_dir.glob("*"))
        targets.append((f"directory {state_dir.name}/ ({n} file(s))", state_dir))
    if legacy_state.exists():
        targets.append((f"file {legacy_state.name}", legacy_state))
    if events_log.exists():
        targets.append((f"file {events_log.name}", events_log))
    if wipe_config and config_file.exists():
        targets.append((f"file {config_file.name}", config_file))

    cfg_users_to_clear = 0
    if not wipe_config and config_file.exists():
        try:
            cfg_users_to_clear = len(cfgstore(config_file).data.get("users") or [])
        except Exception:
            cfg_users_to_clear = 0

    if not targets and cfg_users_to_clear == 0:
        click.echo("nothing to reset.")
        return

    click.echo("This will delete:")
    for label, _ in targets:
        click.echo(f"  - {label}")
    if cfg_users_to_clear:
        click.echo(f"  - {cfg_users_to_clear} user(s) from config.json (settings preserved)")

    if not assume_yes:
        if not click.confirm("Proceed?", default=False):
            click.echo("aborted."); return

    for label, p in targets:
        try:
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
            click.echo(f"removed {label}")
        except OSError as e:
            click.echo(f"failed to remove {label}: {e}", err=True)

    if not wipe_config and cfg_users_to_clear and config_file.exists():
        try:
            cfg = cfgstore(config_file)
            cfg.mutate(lambda d: d.update(users=[]))
            click.echo(f"cleared user list in {config_file.name}")
        except Exception as e:
            click.echo(f"failed to clear users in config: {e}", err=True)

    click.echo("done. fresh slate.")


@cli.command(name="test-webhook")
def test_webhook():
    cfg = cfgstore(_cfgpath())
    dispatcher = dispatcher_t(cfg.data, _basedir(), state_dir=_statedir())

    fake = event_t(
        user_id=1,
        username="Roblox",
        display_name="Roblox",
        headshot_url="https://www.roblox.com/headshot-thumbnail/image?userId=1&width=150&height=150",
        type="went_online",
    )

    async def _go():
        try:
            await dispatcher.emit(fake)
        finally:
            await dispatcher.aclose()

    asyncio.run(_go())
    click.echo("test event dispatched.")


@cli.command()
@click.argument("user")
def snapshot(user: str):
    from .snapshot import mksnap

    async def _go():
        async with rblxclient(cookie=_cookie()) as client:
            uid = int(user) if user.isdigit() else await client.resolve_username(user)
            if uid is None:
                click.echo("not found", err=True); sys.exit(1)
            cfg = cfgstore(_cfgpath())
            snap = await mksnap(client, uid, cfg.data.get("events", {}))
            click.echo(json.dumps(snap.to_dict(), indent=2, default=str))

    asyncio.run(_go())


@cli.command(name="usernames")
@click.argument("user")
def usernames_cmd(user: str):
    cookie = _cookie()
    uid, name = _resolveuser(user, cookie=cookie)
    if uid is None:
        click.echo(f"could not resolve: {user}", err=True); sys.exit(1)

    async def _go():
        async with rblxclient(cookie=cookie) as client:
            return await client.unamehist(uid)
    prior = asyncio.run(_go())
    click.echo(f"@{name} (uid={uid})")
    if not prior:
        click.echo("  (no prior usernames recorded)")
        return
    for n in prior:
        click.echo(f"  - {n}")


@cli.command(name="stats")
@click.argument("user")
def stats_cmd(user: str):
    snap = _findstate(user)
    if snap is None:
        click.echo(f"no state recorded for: {user} (start `tracker run` first)", err=True); sys.exit(1)
    sessions = history.loadsess(_statedir(), snap)
    agg = history.aggsess(sessions)
    click.echo(f"@{snap.username} (uid={snap.user_id})")
    click.echo(f"  sessions:  {agg['session_count']}")
    click.echo(f"  total:     {_fmtdur(agg['total_seconds'])}")
    click.echo(f"  today:     {_fmtdur(agg['today_seconds'])}")
    click.echo(f"  last 7d:   {_fmtdur(agg['week_seconds'])}")
    if agg["per_game_seconds"]:
        click.echo("  per game:")
        for game, secs in list(agg["per_game_seconds"].items())[:10]:
            click.echo(f"    {_fmtdur(secs):>8}  {game}")


@cli.command(name="history")
@click.argument("user")
@click.option("--limit", default=20, help="How many recent sessions to show")
def history_cmd(user: str, limit: int):
    snap = _findstate(user)
    if snap is None:
        click.echo(f"no state recorded for: {user}", err=True); sys.exit(1)
    sessions = history.loadsess(_statedir(), snap)
    if not sessions:
        click.echo("(no sessions yet)"); return
    sessions = sessions[-limit:]
    click.echo(f"@{snap.username} - last {len(sessions)} sessions")
    for s in sessions:
        ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(s.get("ts", 0)))
        dur = _fmtdur(int(s.get("duration_seconds", 0)))
        click.echo(f"  {ts}  {dur:>8}  {s.get('game_name') or s.get('place_id')}")


@cli.command(name="lastseen")
def lastseen_cmd():
    state = _mkstate()
    rows = []
    now = time.time()
    for uid, snap in state._snapshots.items():
        last_online_ts = None
        if snap.last_online:
            try:

                import datetime
                s = snap.last_online.replace("Z", "+00:00").rstrip()
                last_online_ts = datetime.datetime.fromisoformat(s).timestamp()
            except (ValueError, TypeError):
                pass
        rows.append((snap, last_online_ts))

    if not rows:
        click.echo("(no tracked users with state yet - run `tracker run` first)"); return


    def sort_key(r):
        snap, ts = r
        is_online = snap.presence in ("online", "in_game", "studio")
        return (0 if is_online else 1, -(ts or 0))
    rows.sort(key=sort_key)

    click.echo(f"{'user':<24} {'status':<10} {'last seen':<24} {'streak':>7}")
    click.echo("-" * 70)
    for snap, ts in rows:
        name = f"@{snap.username}"
        status = snap.presence or "?"
        if ts:
            ago = now - ts
            d, rem = divmod(int(ago), 86400)
            h, _ = divmod(rem, 3600)
            ago_str = f"{d}d{h}h ago" if d else (f"{h}h ago" if h else "<1h ago")
            seen = time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
            seen_col = f"{seen} ({ago_str})"
        else:
            seen_col = "-"
        streak = f"{snap.current_streak_days}d" if snap.current_streak_days else "-"
        click.echo(f"{name:<24} {status:<10} {seen_col:<24} {streak:>7}")


@cli.command(name="patterns")
@click.argument("user")
def patterns_cmd(user: str):
    snap = _findstate(user)
    if snap is None:
        click.echo(f"no state recorded for: {user}", err=True); sys.exit(1)
    presence = history.loadpres(_statedir(), snap)
    p = history.patterns(presence)
    click.echo(f"@{snap.username} (uid={snap.user_id}) - based on {p['sample_size']} ticks")
    if p["sample_size"] < 24:
        click.echo("  not enough data yet - let the poller run for a day or so")
        return
    if p["peak_hour"] is not None:
        click.echo(f"  peak online hour:    {p['peak_hour']:02d}:00 (host local)")
    if p["tz_offset_hours"] is not None:
        sign = "+" if p["tz_offset_hours"] >= 0 else ""
        click.echo(f"  estimated tz offset: {sign}{p['tz_offset_hours']}h vs host local")
    if p["bedtime_hour"] is not None:
        click.echo(f"  typical bedtime:     ~{p['bedtime_hour']:02d}:00 (host local)")
    if p["wakeup_hour"] is not None:
        click.echo(f"  typical wake-up:     ~{p['wakeup_hour']:02d}:00 (host local)")


@cli.command(name="digest")
@click.argument("user")
@click.option("--hours", default=24, help="Look back this many hours")
def digest_cmd(user: str, hours: int):
    from . import digest as dmod
    snap = _findstate(user)
    if snap is None:
        click.echo(f"no state recorded for: {user}", err=True); sys.exit(1)
    cfg = cfgstore(_cfgpath())
    user_entry = next((u for u in cfg.data.get("users", []) if u.get("user_id") == snap.user_id), {})
    dispatcher = dispatcher_t(cfg.data, _basedir(), state_dir=_statedir())
    d = dmod.mkdigest(_statedir(), snap, period_hours=hours)

    async def _go():
        try:
            await dispatcher.emit(d, user_entry=user_entry)
        finally:
            await dispatcher.aclose()
    asyncio.run(_go())
    click.echo(f"digest dispatched for @{snap.username}: {d.summary()}")


