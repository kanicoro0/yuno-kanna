import discord
from discord.ext import commands

from config import DISCORD_TOKEN, PREFIXES
from yuno_core import setup_commands, setup_events


intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix=commands.when_mentioned_or(*PREFIXES),
    intents=intents,
    help_command=None,
)

setup_commands(bot)
setup_events(bot)


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
