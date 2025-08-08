import os
import uuid
import requests
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
API_KEY = os.getenv("ROBLOX_API_KEY")
UNIVERSE_ID = os.getenv("UNIVERSE_ID")  # string is fine

# Optional: use role IDs for precise checks (recommended)
MOD_ROLE_ID = int(os.getenv("DISCORD_MOD_ROLE_ID", "0"))       # e.g. 123456789012345678
SUPERMOD_ROLE_ID = int(os.getenv("DISCORD_SUPERMOD_ROLE_ID", "0"))

# Safety checks
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN missing")
if not API_KEY:
    raise RuntimeError("ROBLOX_API_KEY missing")
if not UNIVERSE_ID:
    raise RuntimeError("UNIVERSE_ID missing")

print(f"Universe: {UNIVERSE_ID}")

# Intents: need members to read roles
intents = discord.Intents.default()
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

def _build_duration_string(seconds: int | None) -> str | None:
    """
    Cloud v2 duration format: '<n>s' (e.g., '3600s').
    Return None for permanent (no duration field).
    """
    if seconds is None or seconds == -1:
        return None
    if seconds <= 0:
        raise ValueError("Duration must be -1 (forever) or a positive number of seconds.")
    return f"{int(seconds)}s"

def set_user_game_join_restriction(user_id: int, duration_seconds: int, display_reason: str, private_reason: str, exclude_alt_accounts: bool = False) -> tuple[int, dict | str]:
    """
    Cloud v2 UserRestriction PATCH:
    PATCH https://apis.roblox.com/cloud/v2/universes/{UNIVERSE_ID}/user-restrictions/{user_id}?updateMask=...
    Body includes restriction with proper field names and types.
    """
    base_url = f"https://apis.roblox.com/cloud/v2/universes/{UNIVERSE_ID}/user-restrictions/{user_id}"

    headers = {
        "x-api-key": API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "x-idempotency-key": str(uuid.uuid4()),
    }

    # Build duration string if applicable
    try:
        duration_str = _build_duration_string(duration_seconds)
    except ValueError as ve:
        return 400, str(ve)

    restriction = {
    }
    if duration_str is not None:
        restriction["duration"] = duration_str

    body = {"restriction": restriction}
    mask_fields = ["restriction.excludeAltAccounts"]
    if duration_str is not None:
        mask_fields.append("restriction.duration")
    params = {"updateMask": ",".join(mask_fields)}


    # Generate updateMask fields
    mask_fields = [
    ]
    if duration_str is not None:
        mask_fields.append("restriction.duration")

    params = {
        "updateMask": ",".join(mask_fields)
    }

    try:
        resp = requests.patch(base_url, headers=headers, params=params, json=body, timeout=20)
    except requests.RequestException as e:
        return 0, f"Network error: {e}"

    try:
        payload = resp.json()
    except ValueError:
        payload = resp.text

    return resp.status_code, payload


def has_moderator_role(member: discord.Member) -> bool:
    # Prefer ID checks if provided
    if MOD_ROLE_ID or SUPERMOD_ROLE_ID:
        role_ids = {r.id for r in member.roles}
        if MOD_ROLE_ID and MOD_ROLE_ID in role_ids:
            return True
        if SUPERMOD_ROLE_ID and SUPERMOD_ROLE_ID in role_ids:
            return True
        return False

    # Fallback: name-based (case-insensitive)
    role_names = {r.name.lower() for r in member.roles}
    return ("mod" in role_names) or ("supermod" in role_names)

@bot.event
async def on_ready():
    try:
        await bot.tree.sync()
        print(f"Logged in as {bot.user} | Slash commands synced.")
    except Exception as e:
        print("Failed to sync slash commands:", e)

@bot.tree.command(name="hello", description="Say hello")
async def hello(interaction: discord.Interaction):
    await interaction.response.send_message(
        f"Hey {interaction.user.mention}! This is a slash command!",
        ephemeral=True
    )

@app_commands.guild_only()
@bot.tree.command(
    name="gameban",
    description="Apply a Cloud v2 game-join restriction (ban) for a Roblox user ID"
)
@app_commands.describe(
    roblox_user_id="Roblox user ID to restrict from joining",
    duration="Duration in seconds (-1 for permanent)",
    display_reason="Reason shown to players",
    private_reason="Moderator-only reason (not shown to players)",
    exclude_alt_accounts="Also apply to detected alt accounts"
)
async def gameban(
    interaction: discord.Interaction,
    roblox_user_id: int,
    duration: int,
    display_reason: str,
    private_reason: str,
    exclude_alt_accounts: bool = False
):
    await interaction.response.defer(ephemeral=True)

    # Ensure this is in a guild and we have a Member to check roles
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        await interaction.followup.send("Use this command in a server.", ephemeral=True)
        return

    # Role gate: must have 'mod' or 'supermod'
    if not has_moderator_role(interaction.user):
        await interaction.followup.send(
            "You need the Mod or Supermod role to use this command.",
            ephemeral=True
        )
        return

    status, body = set_user_game_join_restriction(
        user_id=roblox_user_id,
        duration_seconds=duration,
        display_reason=display_reason,
        private_reason=f"{private_reason} (via Discord by {interaction.user.name})",
        exclude_alt_accounts=exclude_alt_accounts
    )

    if 200 <= status < 300:
        human_dur = "forever" if duration == -1 else f"{duration} seconds"
        await interaction.followup.send(
            f"✅ Applied game-join restriction to Roblox user ID {roblox_user_id} for {human_dur}.",
            ephemeral=True
        )
    else:
        await interaction.followup.send(
            f"❌ Restriction failed (HTTP {status}). Details: {body}",
            ephemeral=True
        )

bot.run(TOKEN)
