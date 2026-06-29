from dataclasses import dataclass
import logging

import discord
from discord.ext import commands

from yuno.discord.input import to_incoming_message
from yuno.messages import SentMessage
from yuno.pipeline import ConversationPipeline, PipelineResult


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConversationRuntime:
    pipeline: ConversationPipeline


def register_events(bot: commands.Bot, runtime: ConversationRuntime) -> None:
    @bot.event
    async def on_ready() -> None:
        print(f"Yuno v2.0 ready: {bot.user}")

    @bot.event
    async def on_message(message: discord.Message) -> None:
        if bot.user is None:
            return
        incoming = to_incoming_message(message, bot.user)
        try:
            result = await runtime.pipeline.process(incoming)
        except Exception:
            logger.exception("Conversation pipeline failed before send")
            return
        if not result.should_send:
            return

        try:
            sent = await send_result(message, result)
        except discord.HTTPException:
            logger.exception("Discord send failed")
            return

        await finalize_sent_message(
            runtime.pipeline,
            result,
            SentMessage(
                discord_message_id=str(sent.id),
                author_id=str(bot.user.id),
                author_name=bot.user.display_name,
                content=sent.content,
                created_at=sent.created_at.isoformat(),
            ),
        )


async def finalize_sent_message(
    pipeline: ConversationPipeline,
    result: PipelineResult,
    sent: SentMessage,
) -> None:
    try:
        await pipeline.record_sent_assistant(result, sent)
    except Exception:
        logger.exception("Discord send succeeded but assistant log commit failed")
        return

    try:
        await pipeline.observe_after_send(result.observation_ticket)
    except Exception:
        logger.exception("Assistant log saved but post-send observation failed")


async def send_result(
    source: discord.Message,
    result: PipelineResult,
) -> discord.Message:
    if result.reply_mode == "discord_reply":
        return await source.reply(
            result.reply_text,
            mention_author=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )
    if result.reply_mode == "plain":
        return await source.channel.send(
            result.reply_text,
            allowed_mentions=discord.AllowedMentions.none(),
        )
    raise ValueError(f"unsupported reply mode: {result.reply_mode}")
