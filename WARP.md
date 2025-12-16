# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Common commands

### Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Run the bot (local)

```bash
python main.py
```

### Run with Docker

```bash
docker build -t neverhome-discord-bot .
docker run --rm --env-file .env neverhome-discord-bot
```

### Tests / lint

No test suite or lint/typecheck tooling is configured in this repository (no `tests/`, `pyproject.toml`, `tox.ini`, etc.).

## Configuration (env vars)

Configuration is loaded in `config.py` via `python-dotenv` (`load_dotenv()`), so local development typically uses a `.env` file next to `main.py`.

Required env vars (enforced by `get_config()` in `config.py`):
- `DISCORD_TOKEN`
- `ROBLOX_API_KEY`
- `UNIVERSE_ID`
- `VERIFICATION_ROLE_ID`

Optional role IDs used for permission checks (default to `0`):
- `DISCORD_MOD_ROLE_ID`
- `DISCORD_SUPERMOD_ROLE_ID`
- `DISCORD_ADMIN_ROLE_ID`

## Architecture (big picture)

This repo is a single-process Discord bot that exposes moderation workflows via Discord *slash commands* and (optionally) calls Roblox Open Cloud APIs.

### Entry point and wiring
- `main.py` is the entry point.
  - Creates a `discord.ext.commands.Bot` with `guilds` + `members` intents enabled.
  - Loads env/config via `get_config()`.
  - Initializes logging via `configure_logging()`.
  - Registers all slash commands by calling `register_commands()` from `commands.py`.

### Slash command layer
- `commands.py` defines `register_commands(bot, universe_id, api_key, permissions, verification_role_id)`.
  - Uses `discord.app_commands` decorators on `bot.tree.command(...)` functions.
  - Permission gating is centralized via helpers in `permissions.py`.
  - Several commands defer responses and then use `interaction.followup.send(..., ephemeral=True)`.

If you’re adding/modifying commands, this is the main file to edit.

### Roblox integration
- `roblox_service.py` is the boundary for Roblox HTTP calls.
  - `resolve_roblox_user_id_by_username()` resolves usernames -> numeric userId via Roblox Users API.
  - `set_user_game_join_restriction()` PATCHes Roblox Open Cloud v2 user restrictions for a universe.

Discord command handlers should call into these functions (rather than making HTTP calls directly) so the Roblox boundary stays in one place.

### Discord utilities
- `discord_utils.py` contains helper logic that isn’t directly a command (currently: finding members by nickname/display name/name).

### Permissions model
- `permissions.py` provides:
  - `is_admin(member, PermissionsConfig)`
  - `has_moderator_role(member, PermissionsConfig)`

Role IDs come from env vars; if IDs are not set, the code falls back to role-name checks ("mod" / "supermod") and Discord’s `administrator` permission.

### Logging model (important)
- `logging_config.py` configures a single logger (`neverhome-bot`) with a custom async handler that posts logs to a Discord text channel.
- In `commands.py:on_ready`, the bot searches across connected guilds for a text channel named exactly `logs` (case-insensitive) and binds logging to it via `bind_discord_log_channel()`.

If logs are “missing”, first confirm the bot can see a `#logs` channel and has permission to send messages there.
