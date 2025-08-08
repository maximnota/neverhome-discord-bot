import uuid
from typing import Dict, Optional, Tuple, Union

import logging
import requests


logger = logging.getLogger("neverhome-bot")


def _build_duration_string(seconds: Optional[int]) -> Optional[str]:
    if seconds is None or seconds == -1:
        return None
    if seconds <= 0:
        raise ValueError("Duration must be -1 (forever) or a positive number of seconds.")
    return f"{int(seconds)}s"


def resolve_roblox_user_id_by_username(username: str) -> Optional[int]:
    try:
        resp = requests.post(
            "https://users.roblox.com/v1/usernames/users",
            json={"usernames": [username], "excludeBannedUsers": False},
            timeout=15,
        )
        data = resp.json()
        if resp.status_code != 200:
            logger.warning(
                "Roblox username lookup failed for '%s': HTTP %s %s",
                username,
                resp.status_code,
                data,
            )
            return None
        matches = data.get("data") or []
        if not matches:
            logger.info("Roblox username '%s' not found", username)
            return None
        user_id = matches[0].get("id")
        logger.info("Resolved Roblox username '%s' -> userId %s", username, user_id)
        return int(user_id) if user_id is not None else None
    except Exception as error:
        logger.error("Roblox username lookup error for '%s': %s", username, error)
        return None


def set_user_game_join_restriction(
    *,
    universe_id: str,
    api_key: str,
    user_id: int,
    duration_seconds: int,
    display_reason: str,
    private_reason: str,
    exclude_alt_accounts: bool = False,
) -> Tuple[int, Union[Dict, str]]:
    base_url = f"https://apis.roblox.com/cloud/v2/universes/{universe_id}/user-restrictions/{user_id}"

    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "x-idempotency-key": str(uuid.uuid4()),
    }

    try:
        duration_str = _build_duration_string(duration_seconds)
    except ValueError as error:
        return 400, str(error)

    game_join_restriction = {
        "active": True,
        "displayReason": display_reason,
        "privateReason": private_reason,
        "excludeAltAccounts": bool(exclude_alt_accounts),
    }
    if duration_str is not None:
        game_join_restriction["duration"] = duration_str

    body = {"gameJoinRestriction": game_join_restriction}
    params = {"updateMask": "gameJoinRestriction"}

    try:
        logger.debug(
            "Applying Roblox game-join restriction: userId=%s duration=%s display=**%s** private=**%s** excludeAlts=%s",
            user_id,
            duration_str or "PERMANENT",
            display_reason,
            private_reason,
            bool(exclude_alt_accounts),
        )
        resp = requests.patch(base_url, headers=headers, params=params, json=body, timeout=20)
    except requests.RequestException as error:
        logger.error("Roblox restriction network error for userId=%s: %s", user_id, error)
        return 0, f"Network error: {error}"

    try:
        payload = resp.json()
    except ValueError:
        payload = resp.text

    if 200 <= resp.status_code < 300:
        logger.debug(
            "Roblox restriction applied successfully for userId=%s | display=**%s** private=**%s**",
            user_id,
            display_reason,
            private_reason,
        )
    else:
        logger.warning(
            "Roblox restriction failed for userId=%s: HTTP %s %s | display=**%s** private=**%s**",
            user_id,
            resp.status_code,
            payload,
            display_reason,
            private_reason,
        )
    return resp.status_code, payload


