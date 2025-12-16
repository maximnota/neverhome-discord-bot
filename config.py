import os
from dataclasses import dataclass
from typing import Tuple, Optional

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class PermissionsConfig:
    mod_role_id: int
    supermod_role_id: int
    admin_role_id: int
    verification_role_id: int


def get_config() -> Tuple[Optional[str], Optional[str], Optional[str], PermissionsConfig, int]:
    """Load and validate environment configuration.

    Returns a tuple of (discord_token, roblox_api_key, universe_id, permissions_config, verification_role_id).
    roblox_api_key and universe_id can be None if using database configuration.
    """
    discord_token = os.getenv("DISCORD_TOKEN")
    
    # These are now optional as they might be fetched from DB per guild
    roblox_api_key = os.getenv("ROBLOX_API_KEY")
    universe_id = os.getenv("UNIVERSE_ID")
    
    verification_role_id = os.getenv("VERIFICATION_ROLE_ID")
    database_url = os.getenv("DATABASE_URL")
    # Check for standard libpq env vars as fallback
    has_pg_env = any(os.getenv(k) for k in ("PGHOST", "PGUSER", "PGDATABASE"))

    if not discord_token:
        raise RuntimeError("DISCORD_TOKEN missing")
    if not verification_role_id:
        raise RuntimeError("VERIFICATION_ROLE_ID missing")
    # If no DB configured (either URL or params) and no legacy API key...
    if not (database_url or has_pg_env) and (not roblox_api_key or not universe_id):
         # If no DB, we MUST have the legacy env vars
        raise RuntimeError("Must provide either DATABASE_URL/PG* vars or (ROBLOX_API_KEY and UNIVERSE_ID)")

    permissions = PermissionsConfig(
        mod_role_id=int(os.getenv("DISCORD_MOD_ROLE_ID", "0")),
        supermod_role_id=int(os.getenv("DISCORD_SUPERMOD_ROLE_ID", "0")),
        admin_role_id=int(os.getenv("DISCORD_ADMIN_ROLE_ID", "0")),
        verification_role_id=int(verification_role_id),
    )

    return discord_token, roblox_api_key, universe_id, permissions, int(verification_role_id)
