import os
from dataclasses import dataclass
from typing import Tuple

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class PermissionsConfig:
    mod_role_id: int
    supermod_role_id: int
    admin_role_id: int


def get_config() -> Tuple[str, str, str, PermissionsConfig]:
    """Load and validate environment configuration.

    Returns a tuple of (discord_token, roblox_api_key, universe_id, permissions_config).
    """
    discord_token = os.getenv("DISCORD_TOKEN")
    roblox_api_key = os.getenv("ROBLOX_API_KEY")
    universe_id = os.getenv("UNIVERSE_ID")

    if not discord_token:
        raise RuntimeError("DISCORD_TOKEN missing")
    if not roblox_api_key:
        raise RuntimeError("ROBLOX_API_KEY missing")
    if not universe_id:
        raise RuntimeError("UNIVERSE_ID missing")

    permissions = PermissionsConfig(
        mod_role_id=int(os.getenv("DISCORD_MOD_ROLE_ID", "0")),
        supermod_role_id=int(os.getenv("DISCORD_SUPERMOD_ROLE_ID", "0")),
        admin_role_id=int(os.getenv("DISCORD_ADMIN_ROLE_ID", "0")),
    )

    return discord_token, roblox_api_key, universe_id, permissions


