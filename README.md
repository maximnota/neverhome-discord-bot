## Neverhome Discord Bot

A Discord bot that can apply Roblox Open Cloud game-join restrictions and perform Discord moderation actions using slash commands.

### Features
- Hello command for connectivity testing
- Roblox gameban via Open Cloud v2
- Discord server ban
- "Ban both" workflow by shared nickname (Roblox username and Discord member)

### Requirements
- Python 3.10+
- Dependencies in `requirements.txt`:
  - requests
  - discord.py
  - python-dotenv

### Setup
1. Create a `.env` file next to `main.py` with:
   ```env
   DISCORD_TOKEN=your_bot_token
   ROBLOX_API_KEY=your_roblox_open_cloud_api_key
   UNIVERSE_ID=your_universe_id
   # Optional role IDs
   DISCORD_MOD_ROLE_ID=0
   DISCORD_SUPERMOD_ROLE_ID=0
   DISCORD_ADMIN_ROLE_ID=0
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the bot:
   ```bash
   python main.py
   ```

### Quick start:
1) Create a .env file:
   DISCORD_TOKEN=your_bot_token
   ROBLOX_API_KEY=your_open_cloud_api_key
   UNIVERSE_ID=your_universe_id
   DISCORD_MOD_ROLE_ID=0
   DISCORD_SUPERMOD_ROLE_ID=0
   DISCORD_ADMIN_ROLE_ID=0
2) Install deps: pip install -r requirements.txt
3) Run: python main.py

### Project Structure
```
neverhome-discord-bot/
├─ main.py                 # Entry point; wires config, logging, and commands
├─ config.py               # Env loading and validation
├─ logging_config.py       # Logging setup (stdout + rotating file)
├─ permissions.py          # Permission helpers (admin/mod checks)
├─ roblox_service.py       # Roblox API integrations
├─ discord_utils.py        # Discord helper utilities
├─ commands.py             # Slash command registrations
├─ requirements.txt        # Python dependencies
└─ README.md               # This file
```

### Slash Commands
- `/hello` — quick test
- `/gameban` — apply Roblox game-join restriction to a userId
- `/discordban` — ban a Discord member (with message deletion window)
- `/banboth` — resolve by nickname, ban on Roblox and Discord

### Notes
- Ensure the bot has the necessary Discord permissions: View Members, Ban Members, and use slash commands.
- Intents: The bot enables `guilds` and `members` intents to read roles.
- Roblox: You need an Open Cloud API Key with access to the target Universe.


