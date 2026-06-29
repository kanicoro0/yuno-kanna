import logging
from typing import Any, Optional

import discord
from discord.ext import commands

from yuno.attention.repository import AttentionRepository
from yuno.attention.service import AttentionService
from yuno.care.reader import CareReader
from yuno.care.service import CareService
from yuno.commands.admin_service import CoreAdminService
from yuno.commands.core import (
    create_attention_group, create_interest_group, create_memory_group,
)
from yuno.commands.listening import create_listening_group
from yuno.config import Settings, load_settings
from yuno.conversation.context import ContextBuilder
from yuno.conversation.reference_selector import ReferenceSelector
from yuno.conversation.repository import ConversationRepository
from yuno.discord.routing import MessageRouter
from yuno.discord.events import ConversationRuntime, register_events
from yuno.infra.database import Database
from yuno.infra.openai_client import OpenAITextClient
from yuno.interest.repository import InterestRepository
from yuno.interest.service import InterestService
from yuno.listening.repository import ListeningChannelRepository
from yuno.listening.service import ListeningChannelService
from yuno.memory.repository import MemoryMarkRepository
from yuno.memory.service import MemoryMarkService
from yuno.pipeline import ConversationPipeline
from yuno.speaking.speaker import Speaker


def status_text(listening_items, call_names) -> str:
    channels = "、".join(
        f"<#{item.discord_channel_id}>({item.source})" for item in listening_items
    ) or "なし"
    names = "、".join(call_names)
    return (
        "ゆのが聞いている範囲\n"
        "- DM: 保存して返します\n"
        "- mention: 保存してreplyで返します\n"
        "- ゆのへのreply: 保存してreplyで返します\n"
        f"- 聞き耳の場所: {channels}\n"
        "  通常発言は保存します。関心語や開いた気がかりに触れた時だけCareReaderが読み、必要な時だけ返します\n"
        "- 聞き耳の場所でゆのへ向けられた発言: 保存して返します\n"
        "- それ以外の通常発言: 保存しません\n"
        f"- 今の呼び名: {names}"
    )


class YunoBot(commands.Bot):
    def __init__(self, settings: Settings, database: Database, **kwargs: Any):
        super().__init__(**kwargs)
        self.settings = settings
        self.database = database

    async def setup_hook(self) -> None:
        await self.database.open()
        await self.tree.sync()
        print("Slash commands synced globally")

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
    memory = MemoryMarkService(MemoryMarkRepository(database))
    attention = AttentionService(AttentionRepository(database))
    interest = InterestService(InterestRepository(database))
    listening = ListeningChannelService(
        ListeningChannelRepository(database), settings.listening_channel_ids
    )
    client = OpenAITextClient(settings.openai_api_key, settings.openai_model)
    speaker = Speaker(client)
    care_service = CareService(repository, memory, attention, interest)
    pipeline = ConversationPipeline(
        MessageRouter(settings, repository, listening),
        repository,
        ContextBuilder(repository, memory, attention, interest),
        speaker,
        CareReader(client),
        care_service,
        ReferenceSelector(memory, attention, interest),
    )
    bot = YunoBot(
        settings,
        database,
        command_prefix=commands.when_mentioned,
        intents=intents,
        help_command=None,
        application_id=settings.discord_client_id,
    )
    register_events(bot, ConversationRuntime(pipeline))
    admin = CoreAdminService(repository, memory, attention, interest)
    bot.tree.add_command(create_memory_group(admin))
    bot.tree.add_command(create_attention_group(admin))
    bot.tree.add_command(create_interest_group(admin))
    bot.tree.add_command(create_listening_group(listening))

    @bot.tree.command(name="status", description="ゆのがどこで聞いて、どこで返すかを確認します")
    async def status(interaction: discord.Interaction) -> None:
        listening_items = await listening.list_all()
        await interaction.response.send_message(
            status_text(listening_items, settings.yuno_call_names),
            ephemeral=True,
        )

    return bot