from dataclasses import dataclass
import logging
from typing import Optional

from yuno.care.models import CareReadResult
from yuno.care.reader import CareReader
from yuno.care.service import CareService, interest_salience, overlaps_attention
from yuno.conversation.context import ContextBuilder
from yuno.conversation.repository import ConversationRepository
from yuno.discord.routing import MessageRouter
from yuno.messages import IncomingMessage, SentMessage
from yuno.speaking.speaker import Speaker


logger = logging.getLogger(__name__)


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
        care_reader: Optional[CareReader] = None,
        care_service: Optional[CareService] = None,
    ):
        self.router = router
        self.repository = repository
        self.context_builder = context_builder
        self.speaker = speaker
        self.care_reader = care_reader
        self.care_service = care_service

    async def process(self, message: IncomingMessage) -> PipelineResult:
        route = await self.router.route(message)
        if not route.should_store:
            return PipelineResult(False, "", "none", None, None)

        stream = await self.repository.get_or_create_stream(
            kind=message.stream_kind,
            discord_channel_id=message.discord_channel_id,
            discord_guild_id=message.discord_guild_id,
        )
        user_record = await self.repository.append(
            stream_id=stream.id,
            discord_message_id=message.discord_message_id,
            role="user",
            author_id=message.author_id,
            author_name=message.author_name,
            content=route.speaker_content,
            reply_to_discord_message_id=message.reply_to_discord_message_id,
            created_at=message.created_at,
        )
        care_result = CareReadResult()
        application = None
        if self.care_reader and self.care_service:
            state = await self.care_service.current_state(stream.id)
            _, attention, interests = state
            salience = interest_salience(route.speaker_content, interests)
            should_read = route.should_reply or salience > 0 or overlaps_attention(
                route.speaker_content, attention
            )
            if should_read:
                logger.debug(
                    "care_reader called stream_id=%s directed=%s",
                    stream.id, route.should_reply,
                )
                request = await self.care_service.build_request(
                    stream.id,
                    route.speaker_content,
                    1.0 if route.should_reply else 0.0,
                    salience,
                    state,
                )
                care_result = await self.care_reader.read(request)
                application = await self.care_service.apply(
                    stream.id, user_record.id, care_result
                )
                logger.debug(
                    "care_reader result stream_id=%s memory=%d attention=%d interest=%d",
                    stream.id,
                    len(care_result.memory_candidates),
                    len(care_result.attention_candidates),
                    len(care_result.interest_updates),
                )
            else:
                logger.debug("care_reader skipped stream_id=%s", stream.id)

        listening_should_speak = (
            route.reason == "listening_only"
            and care_result.wants_to_speak
            and care_result.should_speak
        )
        logger.debug(
            "listening speech decision stream_id=%s should_speak=%s",
            stream.id, listening_should_speak,
        )
        should_speak = route.should_reply or listening_should_speak
        if not should_speak:
            return PipelineResult(False, "", "none", stream.id, None)

        memory_ids = list(care_result.include_memory_ids)
        attention_ids = list(care_result.include_attention_ids)
        if application:
            memory_ids.extend(application.created_memory_ids)
            attention_ids.extend(application.created_attention_ids)
        context = await self.context_builder.build(
            stream.id,
            memory_ids or None,
            attention_ids or None,
        )
        reply = await self.speaker.speak(context)
        reply_mode = route.reply_mode if route.should_reply else "plain"
        reply_to = message.discord_message_id if reply_mode == "discord_reply" else None
        return PipelineResult(True, reply, reply_mode, stream.id, reply_to)

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
