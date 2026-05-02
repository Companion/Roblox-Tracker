# roblox tracker

A background script that watches a list of Roblox users and tells you when
something about them changes. Goes online, joins a game, earns a badge, edits
their bio, gains followers, etc. Writes everything to a log file and can post
to a Discord webhook with formatted embeds. Optional desktop notifications.

It polls the public Roblox API on a timer. No magic, no scraping, no automation
of the Roblox client.

## Install

```bash
pip install -e .
```

Needs Python 3.10 or newer.

## Using it

```bash
tracker add Roblox            # by username
tracker add 1 --alias founder # by user id, with a label

tracker list                  # who you're tracking
tracker remove Roblox

tracker run                   # start polling, Ctrl-C to stop
```

The first time you run anything it creates `config.json` in the current
directory. Edit it while `tracker run` is going and changes pick up within
a couple of seconds, no restart needed.

State files live in `tracked users/`, one JSON per user, plus per-user
`.events.jsonl`, `.sessions.jsonl`, and `.presence.jsonl` for history.

## What it tracks

Default-on, all toggleable in `config.json` under `events`:

- presence (online, offline, joined a game, left a game, opened Studio)
- bio, username, and display name changes
- avatar item changes and profile picture changes
- friends added, removed, or count changing (count works even on UK
  privacy-locked accounts)
- followers and following count changes
- groups joined and left
- badges earned (with badge name and description)
- limiteds acquired or removed, and total RAP
- visit and favorite counts on experiences they've made
- visit velocity spikes (when one of their games suddenly takes off)
- ban or termination state
- Premium status
- verified badge
- Roblox-issued badges (Administrator, Welcome to the Club, etc.)
- streaks (3, 7, 14, 30... days online in a row)
- co-presence (two tracked users in the same game at once)

It also computes a daily digest, an estimated timezone, and typical
bedtime/wake-up time from accumulated presence data.

## Discord webhook

Open `config.json` and set:

```json
"webhook": {
  "enabled": true,
  "url": "https://discord.com/api/webhooks/.../...",
  "username": "Roblox Tracker",
  "default_ping": "",
  "events": {
    "went_online":  { "ping": "<@&ROLE_ID>" },
    "badge_earned": { "color": 16776960 },
    "bio_changed":  { "enabled": false }
  }
}
```

Then `tracker test-webhook` to fire a sample.

Per-event keys you can override:

- `enabled` (false to silence that event type for the webhook)
- `color` (Discord color int)
- `title_template` (placeholders: `{display_name}`, `{username}`,
  `{user_id}`, `{event}`, `{event_pretty}`, `{old}`, `{new}`)
- `ping` (e.g. `<@123>`, `<@&456>`, `@everyone`)

You can also give a single user their own webhook by adding a `"webhook"`
block under their entry in `users` - same shape, deep-merges over the global
one.

## Privacy / cookie

Some things are gated:

- A user's full friends list returns 403 for UK / under-18 / privacy-locked
  accounts. Friend count still works.
- Game info (which place they're in) is hidden unless the requester is
  authenticated and friends with them.
- Inventory contents are hidden unless the requester owns them.

If you set `roblox.cookie` in `config.json` to your own
`.ROBLOSECURITY` cookie value, requests get authenticated and the gated
endpoints unlock for users you're friends with on that account. The cookie
is a session token, so treat it like a password - anyone with it can act
as you on Roblox.

## Useful commands

```bash
tracker run                  # start polling
tracker list
tracker lastseen             # everyone sorted by who's been offline longest
tracker stats <user>         # total / today / weekly play time + per game
tracker history <user>       # recent game sessions
tracker patterns <user>      # estimated timezone, bedtime, wake-up
tracker usernames <user>     # prior usernames
tracker digest <user>        # build and dispatch a daily-digest embed now
tracker snapshot <user>      # raw JSON of one fetch (debug)
tracker test-webhook         # post a sample event
tracker reset                # wipe all tracked-user data, keeps settings
tracker reset --config       # wipe everything including config.json
```

## Files it creates

- `config.json` - your settings, hot-reloaded
- `tracked users/<name> [<uid>].json` - last known state per user
- `tracked users/<name> [<uid>].events.jsonl` - every event
- `tracked users/<name> [<uid>].sessions.jsonl` - completed game sessions
- `tracked users/<name> [<uid>].presence.jsonl` - presence ticks for the heatmap
- `events.log` - human-readable event stream

All of these are in `.gitignore`.

## Things Roblox doesn't expose

So you can't track:

- which specific server a user is in (mostly hidden, even with cookie)
- private inventory contents
- chat / DMs
- another user's Robux balance
- trade history

## Notes

Default poll interval is 60 seconds. The presence endpoint rate-limits
hard, so if you watch many users you'll want to bump that up.

Desktop notifications need `plyer` (installed automatically) and an actual
desktop session - won't work on a headless server.
