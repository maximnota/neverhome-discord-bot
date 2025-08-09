import logging
import asyncio
import csv
import io
from typing import List, Dict, Optional, Tuple
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
            # Attempt to DM the user prior to the ban so they receive the message
            try:
                appeal_url = "https://discord.gg/5PyPkuE4Ak"
                dm_message = (
                    f"You have been banned from '{interaction.guild.name}'.\n"
                    f"Reason: {reason}\n"
                    f"You can appeal here: {appeal_url}"
                )
                await target.send(dm_message)
            except Exception:
                # Ignore DM failures (user has DMs closed, blocked bot, etc.)
                pass
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
            # Attempt to DM the user prior to the ban so they receive the message
            try:
                appeal_url = "https://discord.gg/5PyPkuE4Ak"
                dm_message = (
                    f"You have been banned from '{interaction.guild.name}' and restricted from the game.\n"
                    f"Reason: {display_reason}\n"
                    f"You can appeal here: {appeal_url}"
                )
                await member.send(dm_message)
            except Exception:
                # Ignore DM failures (user has DMs closed, blocked bot, etc.)
                pass
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

    async def parse_ban_csv(csv_content: str) -> Tuple[List[Dict[str, str]], List[str]]:
        """
        Parse CSV content for ban wave operations.
        Returns (parsed_entries, errors)
        
        Supports two formats:
        1. With headers (case-insensitive, flexible):
           - username/nickname/name: The user's nickname
           - reason: Ban reason
           - duration (optional): Ban duration in seconds, defaults to -1 (permanent)
           - roblox_id (optional): Roblox user ID
           - discord_id (optional): Discord user ID  
           - exclude_alt_accounts (optional): Whether to exclude alt accounts, defaults to False
        
        2. Without headers (positional):
           - Column 1: username
           - Column 2: reason
           - Column 3: duration (optional, defaults to -1)
           - Column 4: exclude_alt_accounts (optional, defaults to false)
        """
        entries = []
        errors = []
        
        try:
            lines = csv_content.strip().split('\n')
            if not lines:
                errors.append("CSV file is empty")
                return entries, errors
            
            # Check if first line looks like headers
            first_line = lines[0].lower()
            has_headers = any(keyword in first_line for keyword in ['username', 'nickname', 'name', 'reason'])
            
            if has_headers:
                # Parse with headers
                csv_reader = csv.DictReader(io.StringIO(csv_content))
                
                # Normalize column names to lowercase for flexible matching
                if csv_reader.fieldnames:
                    normalized_fieldnames = [name.lower().strip() for name in csv_reader.fieldnames]
                    csv_reader.fieldnames = normalized_fieldnames
                
                for row_num, row in enumerate(csv_reader, start=2):  # Start at 2 since row 1 is headers
                    # Normalize row keys
                    normalized_row = {k.lower().strip(): v.strip() if v else "" for k, v in row.items()}
                    
                    # Extract username/nickname
                    username = (normalized_row.get('username') or 
                               normalized_row.get('nickname') or 
                               normalized_row.get('name', '')).strip()
                    
                    if not username:
                        errors.append(f"Row {row_num}: Missing username/nickname")
                        continue
                    
                    # Extract reason
                    reason = normalized_row.get('reason', '').strip()
                    if not reason:
                        errors.append(f"Row {row_num}: Missing reason for user '{username}'")
                        continue
                    
                    # Extract optional fields
                    roblox_id = normalized_row.get('roblox_id', '').strip()
                    discord_id = normalized_row.get('discord_id', '').strip()
                    
                    # Parse duration
                    duration_str = normalized_row.get('duration', '-1').strip()
                    try:
                        duration = int(duration_str) if duration_str else -1
                    except ValueError:
                        errors.append(f"Row {row_num}: Invalid duration '{duration_str}' for user '{username}', using permanent")
                        duration = -1
                    
                    # Parse exclude_alt_accounts
                    exclude_alt_str = normalized_row.get('exclude_alt_accounts', 'false').lower().strip()
                    exclude_alt_accounts = exclude_alt_str in ('true', '1', 'yes', 'y')
                    
                    entries.append({
                        'username': username,
                        'roblox_id': roblox_id,
                        'discord_id': discord_id,
                        'reason': reason,
                        'duration': duration,
                        'exclude_alt_accounts': exclude_alt_accounts,
                        'row_num': row_num
                    })
            else:
                # Parse without headers (positional)
                csv_reader = csv.reader(io.StringIO(csv_content))
                
                for row_num, row in enumerate(csv_reader, start=1):
                    if not row or len(row) < 2:
                        errors.append(f"Row {row_num}: Need at least username and reason")
                        continue
                    
                    # Clean up values
                    row = [cell.strip() for cell in row]
                    
                    username = row[0]
                    reason = row[1]
                    
                    if not username:
                        errors.append(f"Row {row_num}: Missing username")
                        continue
                    
                    if not reason:
                        errors.append(f"Row {row_num}: Missing reason for user '{username}'")
                        continue
                    
                    # Parse duration (column 3, optional)
                    duration = -1
                    if len(row) > 2 and row[2]:
                        try:
                            duration = int(row[2])
                        except ValueError:
                            errors.append(f"Row {row_num}: Invalid duration '{row[2]}' for user '{username}', using permanent")
                            duration = -1
                    
                    # Parse exclude_alt_accounts (column 4, optional)
                    exclude_alt_accounts = False
                    if len(row) > 3 and row[3]:
                        exclude_alt_str = row[3].lower().strip()
                        exclude_alt_accounts = exclude_alt_str in ('true', '1', 'yes', 'y')
                    
                    entries.append({
                        'username': username,
                        'roblox_id': '',  # Not available in positional format
                        'discord_id': '',  # Not available in positional format
                        'reason': reason,
                        'duration': duration,
                        'exclude_alt_accounts': exclude_alt_accounts,
                        'row_num': row_num
                    })
                
        except Exception as e:
            errors.append(f"Failed to parse CSV: {str(e)}")
        
        return entries, errors

    async def process_ban_wave_entry(
        entry: Dict[str, str],
        guild: discord.Guild,
        universe_id: str,
        api_key: str,
        moderator_name: str,
        ban_type: str = "both"
    ) -> Dict[str, str]:
        """
        Process a single ban wave entry.
        Returns a result dictionary with status information.
        """
        username = entry['username']
        reason = entry['reason']
        duration = entry['duration']
        exclude_alt_accounts = entry['exclude_alt_accounts']
        row_num = entry['row_num']
        
        result = {
            'username': username,
            'row_num': row_num,
            'roblox_success': False,
            'discord_success': False,
            'roblox_error': '',
            'discord_error': '',
            'roblox_user_id': '',
            'discord_member': ''
        }
        
        # Process Roblox ban if needed
        if ban_type in ["roblox", "both"]:
            try:
                # Use provided roblox_id or resolve from username
                roblox_user_id = entry.get('roblox_id')
                if not roblox_user_id:
                    roblox_user_id = resolve_roblox_user_id_by_username(username)
                
                if not roblox_user_id:
                    result['roblox_error'] = f"Could not resolve Roblox user ID for '{username}'"
                else:
                    result['roblox_user_id'] = str(roblox_user_id)
                    
                    status, body = set_user_game_join_restriction(
                        universe_id=universe_id,
                        api_key=api_key,
                        user_id=int(roblox_user_id),
                        duration_seconds=duration,
                        display_reason=reason,
                        private_reason=f"{reason} (via Discord ban wave by {moderator_name})",
                        exclude_alt_accounts=exclude_alt_accounts,
                    )
                    
                    if 200 <= status < 300:
                        result['roblox_success'] = True
                    else:
                        result['roblox_error'] = f"HTTP {status}: {body}"
                        
            except Exception as e:
                result['roblox_error'] = f"Exception: {str(e)}"
        
        # Process Discord ban if needed
        if ban_type in ["discord", "both"]:
            try:
                # Find Discord member
                member = None
                
                # Use provided discord_id if available
                discord_id = entry.get('discord_id')
                if discord_id:
                    try:
                        member = guild.get_member(int(discord_id))
                    except (ValueError, TypeError):
                        pass
                
                # Fall back to nickname search
                if not member:
                    member = await find_member_by_nickname(guild, username)
                
                if not member:
                    result['discord_error'] = f"Could not find Discord member '{username}'"
                else:
                    result['discord_member'] = str(member)
                    
                    # Attempt to DM the user first
                    try:
                        appeal_url = "https://discord.gg/5PyPkuE4Ak"
                        dm_message = (
                            f"You have been banned from '{guild.name}'.\n"
                            f"Reason: {reason}\n"
                            f"You can appeal here: {appeal_url}"
                        )
                        await member.send(dm_message)
                    except Exception:
                        # Ignore DM failures
                        pass
                    
                    # Perform the ban
                    try:
                        await guild.ban(
                            member,
                            reason=f"{reason} (by {moderator_name} via ban wave)",
                            delete_message_seconds=0,
                        )
                        result['discord_success'] = True
                    except TypeError:
                        # Fallback for older discord.py versions
                        await guild.ban(
                            member,
                            reason=f"{reason} (by {moderator_name} via ban wave)",
                            delete_message_days=0,
                        )
                        result['discord_success'] = True
                        
            except discord.Forbidden:
                result['discord_error'] = "Missing permissions to ban member"
            except Exception as e:
                result['discord_error'] = f"Exception: {str(e)}"
        
        return result

    @app_commands.guild_only()
    @bot.tree.command(name="banwave", description="Perform a ban wave using a CSV file")
    @app_commands.describe(
        csv_file="CSV file with ban information (username, reason, duration, etc.)",
        ban_type="Type of ban to perform",
        dry_run="Preview the bans without executing them"
    )
    async def banwave(
        interaction: discord.Interaction,
        csv_file: discord.Attachment,
        ban_type: str = "both",
        dry_run: bool = False,
    ):
        await interaction.response.defer(ephemeral=True)
        logger.info(
            "/banwave invoked by %s with file=%s ban_type=%s dry_run=%s",
            interaction.user,
            csv_file.filename,
            ban_type,
            dry_run,
        )

        # Validate ban_type
        if ban_type not in ["roblox", "discord", "both"]:
            await interaction.followup.send(
                "❌ Invalid ban_type. Must be 'roblox', 'discord', or 'both'.",
                ephemeral=True,
            )
            return

        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.followup.send("Use this command in a server.", ephemeral=True)
            return

        # Check permissions
        if not (is_admin(interaction.user, permissions) or has_moderator_role(interaction.user, permissions)):
            await interaction.followup.send(
                "You need Admin or Mod/Supermod permissions to use this command.",
                ephemeral=True,
            )
            logger.info("/banwave denied for %s due to insufficient permissions", interaction.user)
            return

        # Validate file type and size
        if not csv_file.filename.lower().endswith('.csv'):
            await interaction.followup.send(
                "❌ Please upload a CSV file (.csv extension).",
                ephemeral=True,
            )
            return

        if csv_file.size > 1024 * 1024:  # 1MB limit
            await interaction.followup.send(
                "❌ CSV file is too large. Maximum size is 1MB.",
                ephemeral=True,
            )
            return

        try:
            # Download and parse CSV
            csv_content = (await csv_file.read()).decode('utf-8')
            entries, parse_errors = await parse_ban_csv(csv_content)

            if parse_errors:
                error_msg = "❌ CSV parsing errors:\n" + "\n".join(parse_errors[:10])
                if len(parse_errors) > 10:
                    error_msg += f"\n... and {len(parse_errors) - 10} more errors"
                await interaction.followup.send(error_msg, ephemeral=True)
                return

            if not entries:
                await interaction.followup.send(
                    "❌ No valid entries found in CSV file.",
                    ephemeral=True,
                )
                return

            # Show preview
            preview_msg = f"📋 **Ban Wave Preview** ({'DRY RUN' if dry_run else 'EXECUTION MODE'})\n"
            preview_msg += f"**File:** {csv_file.filename}\n"
            preview_msg += f"**Ban Type:** {ban_type}\n"
            preview_msg += f"**Total Entries:** {len(entries)}\n\n"
            
            if len(entries) <= 5:
                preview_msg += "**Entries:**\n"
                for entry in entries:
                    duration_str = "permanent" if entry['duration'] == -1 else f"{entry['duration']}s"
                    preview_msg += f"• {entry['username']}: {entry['reason']} ({duration_str})\n"
            else:
                preview_msg += "**First 5 entries:**\n"
                for entry in entries[:5]:
                    duration_str = "permanent" if entry['duration'] == -1 else f"{entry['duration']}s"
                    preview_msg += f"• {entry['username']}: {entry['reason']} ({duration_str})\n"
                preview_msg += f"... and {len(entries) - 5} more entries\n"

            await interaction.followup.send(preview_msg, ephemeral=True)

            if dry_run:
                logger.info("Ban wave dry run completed for %s entries", len(entries))
                return

            # Execute ban wave
            await interaction.followup.send(
                f"🚀 Starting ban wave execution for {len(entries)} entries...",
                ephemeral=True,
            )
            
            # Log ban wave initiation with summary
            logger.info(
                "BANWAVE INITIATED by %s - File: %s, Type: %s, Entries: %s",
                interaction.user,
                csv_file.filename,
                ban_type,
                len(entries)
            )
            
            # Log all entries being processed
            for entry in entries:
                duration_str = "permanent" if entry['duration'] == -1 else f"{entry['duration']}s"
                logger.info(
                    "BANWAVE QUEUE: Row %s - %s - Reason: **%s** - Duration: %s - Exclude alts: %s",
                    entry['row_num'],
                    entry['username'],
                    entry['reason'],
                    duration_str,
                    entry['exclude_alt_accounts']
                )

            successful_bans = []
            failed_bans = []
            
            for i, entry in enumerate(entries):
                # Send progress update every 10 entries or on last entry
                if (i + 1) % 10 == 0 or i == len(entries) - 1:
                    progress_msg = f"⏳ Processing entry {i + 1}/{len(entries)}: {entry['username']}"
                    await interaction.followup.send(progress_msg, ephemeral=True)

                result = await process_ban_wave_entry(
                    entry, interaction.guild, universe_id, api_key, 
                    interaction.user.name, ban_type
                )

                # Determine overall success
                if ban_type == "both":
                    success = result['roblox_success'] and result['discord_success']
                elif ban_type == "roblox":
                    success = result['roblox_success']
                elif ban_type == "discord":
                    success = result['discord_success']

                if success:
                    successful_bans.append(result)
                    logger.info(
                        "BANWAVE SUCCESS: %s (row %s) - Reason: **%s** - Duration: %s - Roblox: %s (ID: %s), Discord: %s (%s)",
                        result['username'],
                        result['row_num'],
                        entry['reason'],
                        "permanent" if entry['duration'] == -1 else f"{entry['duration']}s",
                        result['roblox_success'],
                        result['roblox_user_id'] or "N/A",
                        result['discord_success'],
                        result['discord_member'] or "N/A"
                    )
                else:
                    failed_bans.append(result)
                    logger.warning(
                        "BANWAVE FAILURE: %s (row %s) - Reason: **%s** - Duration: %s - Roblox error: %s, Discord error: %s",
                        result['username'],
                        result['row_num'],
                        entry['reason'],
                        "permanent" if entry['duration'] == -1 else f"{entry['duration']}s",
                        result['roblox_error'] or "Success",
                        result['discord_error'] or "Success"
                    )

                # Small delay to avoid rate limits
                await asyncio.sleep(0.5)

            # Send final summary
            summary_msg = f"✅ **Ban Wave Complete**\n"
            summary_msg += f"**Successful:** {len(successful_bans)}\n"
            summary_msg += f"**Failed:** {len(failed_bans)}\n"

            if failed_bans:
                summary_msg += f"\n❌ **Failures:**\n"
                for failure in failed_bans[:10]:  # Show first 10 failures
                    errors = []
                    if failure['roblox_error']:
                        errors.append(f"Roblox: {failure['roblox_error']}")
                    if failure['discord_error']:
                        errors.append(f"Discord: {failure['discord_error']}")
                    error_text = "; ".join(errors)
                    summary_msg += f"• Row {failure['row_num']} ({failure['username']}): {error_text}\n"
                
                if len(failed_bans) > 10:
                    summary_msg += f"... and {len(failed_bans) - 10} more failures\n"

            await interaction.followup.send(summary_msg, ephemeral=True)
            
            # Final summary log
            logger.info(
                "BANWAVE COMPLETED by %s - File: %s - Successful: %s, Failed: %s",
                interaction.user,
                csv_file.filename,
                len(successful_bans),
                len(failed_bans)
            )

        except UnicodeDecodeError:
            await interaction.followup.send(
                "❌ Could not decode CSV file. Please ensure it's saved as UTF-8.",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.followup.send(
                f"❌ Unexpected error processing ban wave: {str(e)}",
                ephemeral=True,
            )
            logger.error("Ban wave failed with exception: %s", e, exc_info=True)

    _ = banwave

