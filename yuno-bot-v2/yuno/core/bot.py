import logging
from typing import Any, Optional

import discord
from discord.ext import commands

from yuno.actions.executor import ActionExecutor
from yuno.actions.planner import Planner
from yuno.actions.speaker import Speaker
from yuno.commands.control import create_autorespond_group, register_sleep_commands
from yuno.commands.general import register_general_commands
from yuno.commands.memory import create_memory_group
from yuno.core.config import Settings, load_settings
from yuno.core.events import ConversationRuntime, register_events
from yuno.core.preplanning import PrePlanner
from yuno.infra.discord_utils import PREFIXES
from yuno.infra.json_store import JsonStore
from yuno.infra.openai_client import OpenAIJsonClient
from yuno.memory.retrieval import MemoryRetriever
from yuno.memory.storage import MemoryStorage
from yuno.runtime.settings import RuntimeSettings


class YunoBot(commands.Bot):
    def __init__(self, settings: Settings, **kwargs: Any):
        super().__init__(**kwargs)
        self.settings = settings

    async def setup_hook(self) -> None:
        if self.settings.yuno_env.casefold() == "dev" and self.settings.discord_guild_id:
            guild = discord.Object(id=self.settings.discord_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            print("Slash commands synced to the development guild")
        else:
            await self.tree.sync()
            print("Slash commands synced globally")

    def run(self, token: Optional[str] = None, *args: Any, **kwargs: Any) -> None:
        selected_token = token or self.settings.discord_token
        if not selected_token:
            raise RuntimeError("DISCORD_TOKEN is required to connect to Discord")
        super().run(selected_token, *args, **kwargs)


def create_bot(settings: Optional[Settings] = None) -> YunoBot:
    settings = settings or load_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    intents = discord.Intents.default()
    intents.message_content = True
    bot = YunoBot(
        settings,
        command_prefix=commands.when_mentioned_or(*PREFIXES),
        intents=intents,
        help_command=None,
        application_id=settings.discord_client_id,
    )

    storage = MemoryStorage(JsonStore(settings.memory_file))
    runtime_settings = RuntimeSettings(JsonStore(settings.runtime_settings_file))
    ai_client = OpenAIJsonClient(settings.openai_api_key, settings.openai_model)
    runtime = ConversationRuntime(
        planner=Planner(ai_client),
        executor=ActionExecutor(storage),
        speaker=Speaker(ai_client),
        retriever=MemoryRetriever(storage),
        preplanner=PrePlanner(runtime_settings),
    )
    bot.tree.add_command(create_memory_group(storage))
    bot.tree.add_command(create_autorespond_group(runtime_settings))
    register_sleep_commands(bot.tree, runtime_settings)
    register_general_commands(bot.tree, settings, storage, runtime_settings, ai_client)
    register_events(bot, runtime)
    return bot
