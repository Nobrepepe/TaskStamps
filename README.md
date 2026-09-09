# Task Stamps

A local-first desktop habit tracker where recurring tasks are rewarded with
collectible character stamps. You create fictional worlds full of characters,
each with a portrait and 15 numbered stamp images. Every active task is held
by one randomly assigned character; completing the task on a scheduled day
places that character's next stamp onto today's board. Keep the streak going
through stamp 15 to finish the character's run and draw a new one — miss a
scheduled day and the streak drops.

Everything runs offline. No accounts, no cloud, no telemetry.

## Features

- **Daily stamp board** — a large 16:9 board per calendar day; stamps land
  with a random position, slight rotation and scale, preferring uncrowded
  spots. Layouts are saved once and reproduce identically forever.
- **Daily Boss rotation** — characters with dedicated Boss artwork rotate
  in creation order each calendar day. Scheduled completions strike the Boss;
  defeating it can play that character's optional Boss sound.
- **Recurring weekday tasks** — each task runs on specific weekdays
  (Monday–Sunday); a streak means consecutive *scheduled* completions.
- **Character assignments** — one character per active task, drawn randomly
  from a chosen world or all worlds, with strict exclusivity enforced in both
  business logic and SQLite partial unique indexes.
- **Missed-day handling** — missed scheduled days are detected at startup,
  on focus after a date change, and before every completion; one drop and one
  replacement draw per lapse, no matter how long the app was closed.
- **Pause / resume** — paused tasks keep their character and streak; paused
  periods are stored as ranges and never count as missed.
- **Same-day undo** — including the tricky stamp-15 case, which restores the
  finished assignment at streak 14 (finished characters stay reserved for the
  rest of the day so this is always safe).
- **Calendar history** — monthly view with stamp counts and mini previews;
  any past day's board reproduces exactly, using the exact asset versions
  from completion time.
- **Immutable asset versions** — replacing artwork or sounds creates a new
  version; history keeps rendering the old bytes. Unreferenced files are only
  removed through an explicit maintenance action.
- **Sounds** — the global stamp sound plays on every completion, followed by
  the per-stamp sound or character default when assigned, with a mute switch
  and master volume.
- **Vice Chests** — write your own rewards into nine slots: Minor, Medium and
  Major tasks crossed with streaks 5, 10 and 15. Reaching a milestone drops a
  chest onto one random reward from that slot, waiting in the inventory until
  you claim it. Trivial tasks award stamps only.
- **Boss chests** — defeating the daily Boss seals a chest holding all nine
  slots at once. Opening it rolls one reward, weighted by difficulty, so a
  Major reward at streak 15 is the rarest thing in it.
- **Backup / restore / export** — single-archive backups (database + assets
  + settings + schema metadata), validated restore with an automatic safety
  backup, and human-readable JSON export.

## Technology

- Python 3.12+ (tested on 3.14)
- [Flet](https://flet.dev) for the desktop interface
- SQLite (stdlib `sqlite3`) with migrations, WAL, foreign keys and partial
  unique indexes
- `pytest` for tests
- Standard library everywhere else (PNG/WAV placeholder generation included)

## Project structure

```text
├── pyproject.toml
├── README.md
├── src/task_stamps/
│   ├── app.py                  # Flet shell: navigation, dialogs, sound, file picking
│   ├── config.py               # per-user data dir resolution (+ env override)
│   ├── container.py            # single dependency container (no scattered globals)
│   ├── domain/
│   │   ├── enums.py            # statuses, pools, end reasons, weekday names
│   │   ├── exceptions.py       # user-presentable domain errors
│   │   └── models/             # dataclass entities + board read model
│   ├── data/
│   │   ├── database.py         # connection, re-entrant transactions, migration runner
│   │   ├── migrations/         # ordered SQL migrations
│   │   └── repositories/       # one repository per aggregate
│   ├── services/
│   │   ├── assignment_service.py   # eligibility, random draws, exclusivity
│   │   ├── completion_service.py   # atomic completion, rollover, undo
│   │   ├── schedule_service.py     # weekday rules + missed-day evaluation
│   │   ├── board_service.py        # normalized placement generation/projection
│   │   ├── streak_service.py       # progress summaries
│   │   ├── task_service.py         # draft/active/paused/archived lifecycle
│   │   ├── library_service.py      # worlds & characters, readiness, safe archive
│   │   ├── asset_service.py        # validated imports, immutable versions
│   │   ├── backup_service.py       # backup/restore/export/factory reset
│   │   ├── chest_service.py        # reward slots, chest grants and claims
│   │   ├── boss_service.py         # daily Boss rotation and progress
│   │   ├── settings_service.py     # typed persisted settings
│   ├── views/                  # Today, Tasks, Calendar, Worlds(+characters), Settings
│   ├── components/             # board renderer, cards, aspect-ratio images
│   └── utilities/              # clock, rng, ids, dates, audio, placeholder art
└── tests/
    ├── unit/                   # completion, streaks, missed days, undo, board, assets
    ├── integration/            # backup/restore/reset end-to-end
    └── helpers.py / conftest.py
```

Views call services; services coordinate repositories inside transactions;
repositories own persistence. Business rules never live in Flet handlers.

## Installation

```bash
git clone <this-repository> task-stamps   # or copy the project directory
cd task-stamps

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Linux desktops need the usual Flet/GTK runtime (present on any standard
GNOME/KDE install). No other system dependencies are required; audio playback
uses whichever of `ffplay`, `paplay`, `pw-play`, `mpv` or `aplay` is found,
and silently degrades to no sound otherwise.

## Running the app

```bash
task-stamps
# or
python -m task_stamps
```

## Desktop launcher (Linux)

To start the app from the application menu or a pinned taskbar icon instead of
a terminal, install the desktop entry once:

```bash
./packaging/install-desktop-entry.sh
```

This copies `packaging/task-stamps.svg` into the user icon theme and writes
`~/.local/share/applications/task-stamps.desktop` pointing at
`packaging/task-stamps`, a launcher that runs the app from the project's
`.venv` — no shell activation needed. Search for **Task Stamps** in the
launcher, start it, then right-click its task manager entry and choose *Pin*.

- `packaging/task-stamps` is also a normal executable: run it from anywhere,
  or double-click it in a file manager.
- Launcher output goes to `logs/launcher.log` in the data directory below,
  next to the app's own `task_stamps.log`.
- Re-run the install script after moving the project directory; run it with
  `--uninstall` to remove the entry and icons.
- If the virtual environment is missing, the launcher shows an error dialog
  with the commands to recreate it rather than failing silently.

## Running the tests

```bash
pytest
```

The suite (105 tests) covers streak progression, chest grants at streaks 5,
10 and 15, Boss chest sealing/opening and its weighted odds, claiming and the
undo rules that protect it, per-day completion rules, missed-day drops
(including multi-day closures and the "today is never missed" rule) and the
three-miss auto-pause, pause behavior, the stamp-15 rollover and its undo,
character exclusivity and pool rules, placement bounds/persistence/resize
independence, asset version immutability, schema migrations, and
backup/restore validation. Tests use
temporary databases and asset directories, a fixed fake clock and a seeded
random provider.

## Where your data lives

| Platform | Default location |
| --- | --- |
| Linux | `$XDG_DATA_HOME/task-stamps/app_data` (or `~/.local/share/task-stamps/app_data`) |
| Windows | `%APPDATA%\task-stamps\app_data` |
| macOS | `~/Library/Application Support/task-stamps/app_data` |

Layout: `database/tasks_app.sqlite3`, `assets/{worlds,characters,stamps,sounds}/`,
`backups/`, `logs/`.

For development or a portable setup, point the app anywhere:

```bash
TASK_STAMPS_DATA_DIR=./.local_data task-stamps
```

## World Hub content

Task Stamps can act as a consumer of [World Hub](../WorldHub) publications
(Package Protocol 1, Application Contract 1). The authoritative contract this
app supports lives at `worldhub/application-contract.json`.

- **Install a ZIP** — Settings → World Hub content → *Install publication
  ZIP…*. The package is extracted to a staging area, fully validated (safe
  paths, manifest, embedded contract, every checksum, all references, then
  Task Stamps' own rules: 15 stamps and a portrait per character), previewed,
  and only then activated.
- **Link a production folder** — point at the World Hub folder containing
  `current.json`, then use *Check for update* whenever you republish. The
  publication is copied into this app's own data directory
  (`worldhub-content/`), so everything keeps working when the Hub library or
  drive is unavailable.
- **Activation is failure-safe** — the database import runs in one
  transaction, the previous publication is retained for *Roll back*, and a
  rejected or corrupt package changes nothing.
- **Hub mode** — while a publication is active the Worlds/Characters library
  is read-only; updates arrive through Settings. Legacy in-app authoring
  returns if you never install a publication.
- **What stays yours** — tasks, schedules, assignments, streaks, completions,
  board placements, rewards, chests, and settings are app-owned and survive
  content updates, retirements, failed imports, and rollback. Hub art is
  imported through the immutable asset-version system, so historical boards
  keep rendering the exact bytes they were completed with. Characters that
  leave a publication are archived (never deleted) and active tasks are
  reassigned using the existing safe replacement behavior.
- **Provenance** — every install writes a receipt
  (`worldhub-content/receipts/<publicationId>.json`) recording the source
  library, production, publication, contract version, and checksums; backups
  include the receipts and active pointer but not the recoverable package
  caches.

## Backup and restore

- **Settings → Create backup** writes a single `.zip` into `backups/`
  containing the SQLite database (snapshotted with the online backup API),
  every managed image and sound, settings, and schema metadata.
- **Settings → Restore backup…** validates the archive (structure, origin,
  schema compatibility, database readability), automatically creates a
  `pre_restore` safety backup of your current data, then swaps database and
  assets in together — never partially.
- **Settings → Export JSON** writes a readable export of all worlds,
  characters, tasks, schedules, assignments, completions and placement
  metadata (no binary payloads).
- **Settings → Reset all data…** requires confirmation, then deletes all game
  data, settings, and imported assets. Backups and logs are retained.

## Packaging for Linux

Flet bundles a desktop runtime, so a self-contained build is:

```bash
pip install "flet[all]"          # provides the `flet` CLI
flet pack src/task_stamps/__main__.py --name task-stamps
```

Notes:

- User data lives outside the bundle (see above), so upgrades are safe.
- The code avoids platform-specific logic (path resolution and audio players
  are probed at runtime), so a Windows package later only needs the same
  `flet pack` step on Windows.

## Known limitations

- Sound playback shells out to a system player; on a machine with none of
  the probed players installed, stamps are silent (a warning is logged).
- Undo is same-day only by design; historical boards are read-only.
- One completion per task per local calendar day — no bonus or backdated
  completions in this version.
- Restore replaces current data wholesale (after the automatic safety
  backup); there is no selective merge.
- Timezone changes mid-day follow the OS local date, which may shift when a
  day "ends".

## Future extension points

- A migration framework hook already exists (`data/migrations/`) — add
  `(version, sql)` entries to evolve the schema.
- `RandomProvider` and `Clock` are injected, so alternate draw strategies
  (rarity tiers, pity timers) drop in cleanly.
- The board renderer consumes a pure read model (`BoardStamp`), making
  alternative board visualizations straightforward.
- Asset versions carry checksums, enabling future dedup or integrity audits.
