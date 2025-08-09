import discord
from discord.ext import commands

from config import get_config
from logging_config import configure_logging
from commands import register_commands


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
    register_commands(bot, universe_id=universe_id, api_key=api_key, permissions=permissions, verification_role_id=verification_role_id)
    bot.run(token)


if __name__ == "__main__":
    main()
