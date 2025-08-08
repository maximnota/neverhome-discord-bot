from typing import Optional

import discord


async def find_member_by_nickname(guild: discord.Guild, nickname: str) -> Optional[discord.Member]:
    lower = nickname.lower()
    for member in guild.members:
        names = [getattr(member, "nick", None), getattr(member, "display_name", None), getattr(member, "name", None)]
        if any((n or "").lower() == lower for n in names):
            return member

    try:
        async for member in guild.fetch_members(limit=None):
            names = [getattr(member, "nick", None), getattr(member, "display_name", None), getattr(member, "name", None)]
            if any((n or "").lower() == lower for n in names):
                return member
    except Exception:
        return None

    return None


