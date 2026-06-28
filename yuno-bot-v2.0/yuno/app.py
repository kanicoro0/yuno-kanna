import logging
from typing import Any, Optional

import discord
from discord.ext import commands

from yuno.config import Settings, load_settings
from yuno.conversation.repository import ConversationRepository
from yuno.conversation.service import ConversationService
from yuno.discord.events import ConversationRuntime, register_events
from yuno.infra.database import Database
from yuno.infra.openai_client import OpenAITextClient
from yuno.speaking.speaker import Speaker


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
    conversations = ConversationService(repository)
    speaker = Speaker(OpenAITextClient(settings.openai_api_key, settings.openai_model))
    bot = YunoBot(
        settings,
        database,
        command_prefix=commands.when_mentioned,
        intents=intents,
        help_command=None,
        application_id=settings.discord_client_id,
    )
    register_events(
        bot,
        ConversationRuntime(settings, repository, conversations, speaker),
    )

    @bot.tree.command(name="status", description="ゆのが保存する会話の範囲を確認します")
    async def status(interaction: discord.Interaction) -> None:
        listening = sorted(settings.listening_channel_ids)
        channels = "、".join(f"<#{channel_id}>" for channel_id in listening) or "なし"
        await interaction.response.send_message(
            "会話ログの保存範囲\n"
            "- DM: 保存して返信\n"
            "- 直接mention: 保存して返信\n"
            f"- listening対象: {channels}（人の発言を保存、mention時だけ返信）\n"
            "- それ以外のチャンネル発言: 保存しない",
            ephemeral=True,
        )

    return bot
