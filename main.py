import discord
from discord.ext import commands

from config import get_config
from logging_config import configure_logging
from commands import register_commands

#fake comment to restart the discord bot
def create_bot() -> commands.Bot:
    intents = discord.Intents.default()
    intents.guilds = True
    intents.members = True
    return commands.Bot(command_prefix="!", intents=intents)


def main() -> None:
    token, api_key, universe_id, permissions, verification_role_id = get_config()

    logger = configure_logging()
    logger.info("Universe: %s", universe_id)
    logger.info("Verification Role ID: %s", verification_role_id)

    bot = create_bot()
    
    # Initialize database pool on startup
    from database import Database
    
    @bot.event
    async def on_connect():
        try:
            await Database.get_pool()
        except Exception as e:
            # It's possible the bot connects before the DB is ready or configured, 
            # but we want to fail fast if DB is required and missing?
            # actually config checks existence of var, but connection might fail.
            # We log it.
            print(f"Failed to initialize database pool: {e}")

    register_commands(bot, universe_id=universe_id, api_key=api_key, permissions=permissions, verification_role_id=verification_role_id)
    bot.run(token)


if __name__ == "__main__":
    main()
