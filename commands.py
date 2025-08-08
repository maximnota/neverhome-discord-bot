import logging
import asyncio
import discord
from discord import app_commands
from discord.ext import commands

from permissions import has_moderator_role, is_admin
from roblox_service import resolve_roblox_user_id_by_username, set_user_game_join_restriction
from discord_utils import find_member_by_nickname
from config import PermissionsConfig
from logging_config import bind_discord_log_channel


logger = logging.getLogger("neverhome-bot")


def register_commands(
    bot: commands.Bot,
    *,
    universe_id: str,
    api_key: str,
    permissions: PermissionsConfig,
) -> None:
    @bot.event
    async def on_ready():
        try:
            await bot.tree.sync()
            logger.info("Logged in as %s | Slash commands synced.", bot.user)
            # Bind the Discord logging channel named "logs" across joined guilds
            log_channel = None
            for guild in bot.guilds:
                # Prefer text channel named exactly "logs"
                for channel in guild.text_channels:
                    if channel.name.lower() == "logs":
                        log_channel = channel
                        break
                if log_channel:
                    break
            if log_channel is not None:
                bind_discord_log_channel(log_channel, asyncio.get_running_loop())
                logger.info("Logging bound to #%s in guild '%s'", log_channel.name, log_channel.guild.name)
            else:
                logger.warning("No channel named 'logs' found in any connected guilds.")
        except Exception as error:
            logger.error("Failed to sync slash commands: %s", error)
    _ = on_ready

    @bot.tree.command(name="hello", description="Say hello")
    async def hello(interaction: discord.Interaction):
        logger.info("/hello invoked by %s", interaction.user)
        await interaction.response.send_message(
            f"Hey {interaction.user.mention}! This is a slash command!",
            ephemeral=True,
        )
    _ = hello

    @app_commands.guild_only()
    @bot.tree.command(name="gameban", description="Apply a Cloud v2 game-join restriction (ban) for a Roblox user ID")
    @app_commands.describe(
        roblox_user_id="Roblox user ID to restrict from joining",
        duration="Duration in seconds (-1 for permanent)",
        display_reason="Reason shown to players",
        private_reason="Moderator-only reason (not shown to players)",
        exclude_alt_accounts="Also apply to detected alt accounts",
    )
    async def gameban(
        interaction: discord.Interaction,
        roblox_user_id: int,
        duration: int,
        display_reason: str,
        private_reason: str,
        exclude_alt_accounts: bool = False,
    ):
        await interaction.response.defer(ephemeral=True)
        logger.info(
            "/gameban invoked by %s for Roblox userId=%s duration=%s excludeAlts=%s",
            interaction.user,
            roblox_user_id,
            duration,
            exclude_alt_accounts,
        )

        # Require non-empty reasons
        if not display_reason.strip() or not private_reason.strip():
            await interaction.followup.send(
                "Both display_reason and private_reason are required and cannot be empty.",
                ephemeral=True,
            )
            return

        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.followup.send("Use this command in a server.", ephemeral=True)
            return

        if not (is_admin(interaction.user, permissions) or has_moderator_role(interaction.user, permissions)):
            await interaction.followup.send(
                "You need Admin or Mod/Supermod permissions to use this command.",
                ephemeral=True,
            )
            logger.info("/gameban denied for %s due to insufficient permissions", interaction.user)
            return

        status, body = set_user_game_join_restriction(
            universe_id=universe_id,
            api_key=api_key,
            user_id=roblox_user_id,
            duration_seconds=duration,
            display_reason=display_reason,
            private_reason=f"{private_reason} (via Discord by {interaction.user.name})",
            exclude_alt_accounts=exclude_alt_accounts,
        )

        if 200 <= status < 300:
            human_dur = "forever" if duration == -1 else f"{duration} seconds"
            await interaction.followup.send(
                f"✅ Applied game-join restriction to Roblox user ID {roblox_user_id} for {human_dur}.",
                ephemeral=True,
            )
            logger.info(
                "BLOCKED (Roblox) userId=%s display=**%s** private=**%s**",
                roblox_user_id,
                display_reason,
                private_reason,
            )
        else:
            await interaction.followup.send(
                f"❌ Restriction failed (HTTP {status}). Details: {body}",
                ephemeral=True,
            )
            logger.warning(
                "Roblox restriction failed for userId=%s: HTTP %s %s",
                roblox_user_id,
                status,
                body,
            )

    _ = gameban

    @app_commands.guild_only()
    @bot.tree.command(name="discordban", description="Ban a Discord member from this server")
    @app_commands.describe(
        target="Member to ban",
        reason="Reason for the ban",
        delete_message_seconds="Delete message history in seconds (0-604800)",
    )
    async def discordban(
        interaction: discord.Interaction,
        target: discord.Member,
        reason: str,
        delete_message_seconds: int = 0,
    ):
        await interaction.response.defer(ephemeral=True)
        logger.info("/discordban invoked by %s for target=%s", interaction.user, target)

        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.followup.send("Use this command in a server.", ephemeral=True)
            return

        if not (is_admin(interaction.user, permissions) or interaction.user.guild_permissions.ban_members):
            await interaction.followup.send(
                "You need Admin or Ban Members permission to use this command.",
                ephemeral=True,
            )
            logger.info("/discordban denied for %s due to insufficient permissions", interaction.user)
            return

        # Require non-empty reason
        if not reason.strip():
            await interaction.followup.send(
                "Reason is required and cannot be empty.",
                ephemeral=True,
            )
            return

        try:
            seconds = max(0, min(int(delete_message_seconds), 604800))
            try:
                await interaction.guild.ban(
                    target,
                    reason=f"{reason} (by {interaction.user} via Discord)",
                    delete_message_seconds=seconds,
                )
            except TypeError:
                days = max(0, min(seconds // 86400, 7))
                await interaction.guild.ban(
                    target,
                    reason=f"{reason} (by {interaction.user} via Discord)",
                    delete_message_days=days,
                )
            await interaction.followup.send(
                f"✅ Banned {target.mention} from this server.",
                ephemeral=True,
            )
            logger.info(
                "BLOCKED (Discord) nickname=%s user=%s reason=**%s**",
                target.display_name,
                target,
                reason,
            )
        except discord.Forbidden:
            await interaction.followup.send("I don't have permission to ban that member.", ephemeral=True)
            logger.warning("Failed to ban %s: missing permissions", target)
        except Exception as error:
            await interaction.followup.send(f"❌ Failed to ban member: {error}", ephemeral=True)
            logger.error("Failed to ban %s: %s", target, error)

    _ = discordban

    @app_commands.guild_only()
    @bot.tree.command(name="banboth", description="Ban a user on Roblox and Discord by shared nickname")
    @app_commands.describe(
        nickname="Shared nickname (same on Roblox and Discord)",
        duration="Roblox ban duration in seconds (-1 for permanent)",
        display_reason="Reason shown to Roblox players",
        private_reason="Moderator-only reason for Roblox",
        exclude_alt_accounts="Also apply to detected alt accounts",
        delete_message_seconds="Delete Discord message history in seconds (0-604800)",
    )
    async def banboth(
        interaction: discord.Interaction,
        nickname: str,
        duration: int,
        display_reason: str,
        private_reason: str,
        exclude_alt_accounts: bool = False,
        delete_message_seconds: int = 0,
    ):
        await interaction.response.defer(ephemeral=True)
        logger.info(
            "/banboth invoked by %s for nickname='%s' duration=%s excludeAlts=%s",
            interaction.user,
            nickname,
            duration,
            exclude_alt_accounts,
        )

        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.followup.send("Use this command in a server.", ephemeral=True)
            return

        if not (is_admin(interaction.user, permissions) or has_moderator_role(interaction.user, permissions)):
            await interaction.followup.send(
                "You need Admin or Mod/Supermod permissions to use this command.",
                ephemeral=True,
            )
            return

        # Require non-empty reasons
        if not display_reason.strip() or not private_reason.strip():
            await interaction.followup.send(
                "Both display_reason and private_reason are required and cannot be empty.",
                ephemeral=True,
            )
            return

        roblox_user_id = resolve_roblox_user_id_by_username(nickname)
        if not roblox_user_id:
            await interaction.followup.send(
                f"Could not resolve Roblox username for nickname '{nickname}'.",
                ephemeral=True,
            )
            return

        member = await find_member_by_nickname(interaction.guild, nickname)
        if not member:
            await interaction.followup.send(
                f"Could not find Discord member with nickname '{nickname}'.",
                ephemeral=True,
            )
            return

        status, body = set_user_game_join_restriction(
            universe_id=universe_id,
            api_key=api_key,
            user_id=roblox_user_id,
            duration_seconds=duration,
            display_reason=display_reason,
            private_reason=f"{private_reason} (via Discord by {interaction.user.name})",
            exclude_alt_accounts=exclude_alt_accounts,
        )

        if not (200 <= status < 300):
            await interaction.followup.send(
                f"❌ Roblox restriction failed (HTTP {status}). Details: {body}",
                ephemeral=True,
            )
            logger.warning(
                "Roblox restriction failed for nickname=%s userId=%s: HTTP %s %s",
                nickname,
                roblox_user_id,
                status,
                body,
            )
            return

        seconds = max(0, min(int(delete_message_seconds), 604800))
        try:
            try:
                await interaction.guild.ban(
                    member,
                    reason=f"{display_reason} (by {interaction.user} via Discord)",
                    delete_message_seconds=seconds,
                )
            except TypeError:
                days = max(0, min(seconds // 86400, 7))
                await interaction.guild.ban(
                    member,
                    reason=f"{display_reason} (by {interaction.user} via Discord)",
                    delete_message_days=days,
                )
        except discord.Forbidden:
            await interaction.followup.send(
                "Roblox ban applied, but I don't have permission to ban that Discord member.",
                ephemeral=True,
            )
            logger.warning(
                "BLOCKED (Roblox) nickname=%s userId=%s; Discord ban failed: missing permissions",
                nickname,
                roblox_user_id,
            )
            return
        except Exception as error:
            await interaction.followup.send(
                f"Roblox ban applied, but Discord ban failed: {error}",
                ephemeral=True,
            )
            logger.error(
                "BLOCKED (Roblox) nickname=%s userId=%s; Discord ban failed: %s",
                nickname,
                roblox_user_id,
                error,
            )
            return

        await interaction.followup.send(
            f"✅ Banned '{nickname}' on Roblox (userId {roblox_user_id}) and Discord.",
            ephemeral=True,
        )
        logger.info(
            "BLOCKED (Both) nickname=%s robloxUserId=%s discordUser=%s display=**%s** private=**%s** blockedBy=%s",
            nickname,
            roblox_user_id,
            member,
            display_reason,
            private_reason,
            interaction.user,
        )

    _ = banboth


