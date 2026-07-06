import logging
from typing import Any, Optional

import discord
from discord.ext import commands

from yuno.care.maintenance import CareMaintenanceService
from yuno.care.maintenance_reader import LLMCareMaintenanceReader
from yuno.care.reader import CareReader
from yuno.care.service import CareService
from yuno.care_marks.repository import CareMarkRepository
from yuno.care_marks.service import CareMarkService
from yuno.commands.admin_service import CareMarkCommandService
from yuno.commands.core import create_memories_group
from yuno.commands.guide import create_guide_command
from yuno.commands.message_actions import create_selected_message_command
from yuno.commands.listening import create_listening_group
from yuno.commands.status import create_status_command
from yuno.config import Settings, load_settings
from yuno.conversation.context import ContextBuilder
from yuno.conversation.reference_selector import ReferenceSelector
from yuno.conversation.repository import ConversationRepository
from yuno.discord.care_reactions import (
    CareReactionSurface,
    CareReactionTargetResolver,
)
from yuno.discord.routing import MessageRouter
from yuno.discord.events import ConversationRuntime, register_events
from yuno.infra.database import Database
from yuno.infra.openai_client import OpenAITextClient
from yuno.listening.repository import ListeningChannelRepository
from yuno.listening.service import ListeningChannelService
from yuno.permissions import PermissionService
from yuno.pipeline import ConversationPipeline
from yuno.read_cues.repository import ReadCueRepository
from yuno.read_cues.service import ReadCueService
from yuno.speaking.speaker import Speaker


class YunoBot(commands.Bot):
    def __init__(self, settings: Settings, database: Database, **kwargs: Any):
        super().__init__(**kwargs)
        self.settings = settings
        self.database = database

    async def setup_hook(self) -> None:
        await self.database.open()
        await self._clear_guild_scoped_commands()
        await self.tree.sync()
        print("Slash commands synced globally")

    async def _clear_guild_scoped_commands(self) -> None:
        async for guild in self.fetch_guilds(limit=None):
            target = discord.Object(id=guild.id)
            self.tree.clear_commands(guild=target)
            await self.tree.sync(guild=target)
            print(f"Cleared guild slash commands: {guild.id}")

    async def close(self) -> None:
        await self.database.close()
        await super().close()

    def run(self, token: Optional[str] = None, *args: Any, **kwargs: Any) -> None:
        selected_token = token or self.settings.discord_token
        if not selected_token:
            raise RuntimeError("DISCORD_TOKEN is required to connect to Discord")
        super().run(selected_token, *args, **kwargs)


def create_bot(settings: Optional[Settings] = None) -> YunoBot:
    settings = settings or load_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    intents = discord.Intents.default()
    intents.message_content = True
    database = Database(settings.database_file)
    repository = ConversationRepository(database)
    care_marks = CareMarkService(CareMarkRepository(database))
    read_cues = ReadCueService(ReadCueRepository(database))
    permissions = PermissionService(settings.owner_user_ids)
    listening = ListeningChannelService(
        ListeningChannelRepository(database), settings.listening_channel_ids
    )
    client = OpenAITextClient(settings.openai_api_key, settings.openai_model)
    speaker = Speaker(client)
    care_service = CareService(repository, care_marks, read_cues)
    maintenance = CareMaintenanceService(
        repository, care_marks, LLMCareMaintenanceReader(client)
    )
    pipeline = ConversationPipeline(
        MessageRouter(settings, repository, listening),
        repository,
        ContextBuilder(repository, care_marks),
        speaker,
        CareReader(client),
        care_service,
        ReferenceSelector(care_marks, read_cues),
        maintenance,
    )
    bot = YunoBot(
        settings,
        database,
        command_prefix=commands.when_mentioned,
        intents=intents,
        help_command=None,
        application_id=settings.discord_client_id,
    )
    register_events(bot, ConversationRuntime(
        pipeline,
        care_reactions=CareReactionSurface(
            CareReactionTargetResolver(repository)
        ),
    ))
    mark_commands = CareMarkCommandService(repository, care_marks)
    bot.tree.add_command(create_memories_group(
        mark_commands, permissions, maintenance
    ))
    bot.tree.add_command(create_guide_command())
    bot.tree.add_command(create_selected_message_command(
        mark_commands, permissions
    ))
    bot.tree.add_command(create_listening_group(listening))
    bot.tree.add_command(create_status_command(
        listening, settings.yuno_call_names, permissions
    ))

    return bot
