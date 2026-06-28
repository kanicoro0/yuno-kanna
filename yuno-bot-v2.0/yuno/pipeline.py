from dataclasses import dataclass
from typing import Optional

from yuno.conversation.context import ContextBuilder
from yuno.conversation.repository import ConversationRepository
from yuno.discord.routing import MessageRouter
from yuno.messages import IncomingMessage, SentMessage
from yuno.speaking.speaker import Speaker


@dataclass(frozen=True)
class PipelineResult:
    should_send: bool
    reply_text: str
    reply_mode: str
    stream_id: Optional[int]
    reply_to_discord_message_id: Optional[str]


class ConversationPipeline:
    def __init__(
        self,
        router: MessageRouter,
        repository: ConversationRepository,
        context_builder: ContextBuilder,
        speaker: Speaker,
    ):
        self.router = router
        self.repository = repository
        self.context_builder = context_builder
        self.speaker = speaker

    async def process(self, message: IncomingMessage) -> PipelineResult:
        route = await self.router.route(message)
        if not route.should_store:
            return PipelineResult(False, "", "none", None, None)

        stream = await self.repository.get_or_create_stream(
            kind=message.stream_kind,
            discord_channel_id=message.discord_channel_id,
            discord_guild_id=message.discord_guild_id,
        )
        await self.repository.append(
            stream_id=stream.id,
            discord_message_id=message.discord_message_id,
            role="user",
            author_id=message.author_id,
            author_name=message.author_name,
            content=route.speaker_content,
            reply_to_discord_message_id=message.reply_to_discord_message_id,
            created_at=message.created_at,
        )
        if not route.should_reply:
            return PipelineResult(False, "", "none", stream.id, None)

        context = await self.context_builder.build(stream.id)
        reply = await self.speaker.speak(context)
        reply_to = (
            message.discord_message_id if route.reply_mode == "discord_reply" else None
        )
        return PipelineResult(True, reply, route.reply_mode, stream.id, reply_to)

    async def record_sent_assistant(
        self,
        result: PipelineResult,
        sent: SentMessage,
    ) -> None:
        if not result.should_send or result.stream_id is None:
            raise ValueError("cannot record an assistant message for a non-send result")
        await self.repository.append(
            stream_id=result.stream_id,
            discord_message_id=sent.discord_message_id,
            role="assistant",
            author_id=sent.author_id,
            author_name=sent.author_name,
            content=sent.content,
            reply_to_discord_message_id=result.reply_to_discord_message_id,
            created_at=sent.created_at,
        )
