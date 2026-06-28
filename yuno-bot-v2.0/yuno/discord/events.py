from dataclasses import dataclass
import logging
from typing import Optional

import discord
from discord.ext import commands

from yuno.config import Settings
from yuno.conversation.repository import ConversationRepository
from yuno.conversation.service import ConversationService
from yuno.discord.routing import route_message
from yuno.speaking.speaker import Speaker


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConversationRuntime:
    settings: Settings
    repository: ConversationRepository
    conversations: ConversationService
    speaker: Speaker


def register_events(bot: commands.Bot, runtime: ConversationRuntime) -> None:
    @bot.event
    async def on_ready() -> None:
        print(f"Yuno v2.0 ready: {bot.user}")

    @bot.event
    async def on_message(message: discord.Message) -> None:
        if message.author.bot or bot.user is None:
            return
        route = route_message(message, bot.user, runtime.settings)
        if not route.should_store or not route.clean_content:
            return

        stream = await runtime.repository.get_or_create_stream(
            kind="dm" if message.guild is None else "channel",
            discord_channel_id=str(message.channel.id),
            discord_guild_id=str(message.guild.id) if message.guild else None,
        )
        reference_id: Optional[str] = None
        if message.reference and message.reference.message_id:
            reference_id = str(message.reference.message_id)
        await runtime.repository.append(
            stream_id=stream.id,
            discord_message_id=str(message.id),
            role="user",
            author_id=str(message.author.id),
            author_name=message.author.display_name,
            content=route.clean_content,
            reply_to_discord_message_id=reference_id,
            created_at=message.created_at.isoformat(),
        )
        if not route.should_reply:
            return

        try:
            history = await runtime.conversations.speaker_history(stream.id)
            async with message.channel.typing():
                reply = await runtime.speaker.speak(history)
            sent = await message.reply(
                reply,
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            # The reply becomes durable only after Discord accepted it.
            await runtime.repository.append(
                stream_id=stream.id,
                discord_message_id=str(sent.id),
                role="assistant",
                author_id=str(bot.user.id),
                author_name=bot.user.display_name,
                content=sent.content,
                reply_to_discord_message_id=str(message.id),
                created_at=sent.created_at.isoformat(),
            )
        except discord.HTTPException:
            logger.exception("Discord send failed")
        except Exception:
            logger.exception("Conversation pipeline failed")
            try:
                await message.reply(
                    "ちょっと言葉を落としちゃった。もう一度、呼んで",
                    mention_author=False,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.HTTPException:
                pass
