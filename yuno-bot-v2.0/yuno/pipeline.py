from dataclasses import dataclass
import logging
from typing import Optional

from yuno.care.models import CareReadResult
from yuno.care.reader import CareReader
from yuno.care.service import CareService, interest_salience, overlaps_attention
from yuno.conversation.context import ContextBuilder
from yuno.conversation.reference_selector import ReferenceSelector
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
    observation_ticket: Optional["ObservationTicket"] = None


@dataclass(frozen=True)
class ObservationTicket:
    stream_id: int
    user_message_id: int
    user_content: str
    route_reason: str
    pre_care_completed: bool


class ConversationPipeline:
    def __init__(
        self,
        router: MessageRouter,
        repository: ConversationRepository,
        context_builder: ContextBuilder,
        speaker: Speaker,
        care_reader: Optional[CareReader] = None,
        care_service: Optional[CareService] = None,
        reference_selector: Optional[ReferenceSelector] = None,
    ):
        self.router = router
        self.repository = repository
        self.context_builder = context_builder
        self.speaker = speaker
        self.care_reader = care_reader
        self.care_service = care_service
        self.reference_selector = reference_selector

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
        pre_care_completed = False
        if (
            route.reason == "listening_only"
            and self.care_reader
            and self.care_service
        ):
            state = await self.care_service.current_state(stream.id)
            _, attention, interests = state
            salience = interest_salience(route.speaker_content, interests)
            should_read = salience > 0 or overlaps_attention(
                route.speaker_content, attention
            )
            if should_read:
                logger.debug("care_reader called before send stream_id=%s", stream.id)
                request = await self.care_service.build_request(
                    stream.id,
                    route.speaker_content,
                    0.0,
                    salience,
                    state,
                )
                care_result = await self.care_reader.read(request)
                await self.care_service.apply(
                    stream.id, user_record.id, care_result
                )
                pre_care_completed = True
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
        if route.should_reply and self.reference_selector:
            selection = await self.reference_selector.select(
                stream.id, route.speaker_content
            )
            memory_ids = list(selection.memory_ids)
            attention_ids = list(selection.attention_ids)
        context = await self.context_builder.build(
            stream.id,
            memory_ids,
            attention_ids,
        )
        reply = await self.speaker.speak(context)
        reply_mode = route.reply_mode if route.should_reply else "plain"
        reply_to = message.discord_message_id if reply_mode == "discord_reply" else None
        ticket = ObservationTicket(
            stream_id=stream.id,
            user_message_id=user_record.id,
            user_content=route.speaker_content,
            route_reason=route.reason,
            pre_care_completed=pre_care_completed,
        )
        return PipelineResult(True, reply, reply_mode, stream.id, reply_to, ticket)

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

    async def observe_after_send(
        self, ticket: Optional[ObservationTicket]
    ) -> None:
        if (
            ticket is None
            or ticket.pre_care_completed
            or not self.care_reader
            or not self.care_service
        ):
            return
        state = await self.care_service.current_state(ticket.stream_id)
        _, _, interests = state
        salience = interest_salience(ticket.user_content, interests)
        request = await self.care_service.build_request(
            ticket.stream_id,
            ticket.user_content,
            1.0,
            salience,
            state,
        )
        result = await self.care_reader.read(request)
        await self.care_service.apply(
            ticket.stream_id, ticket.user_message_id, result
        )
        logger.debug(
            "care_reader observed after send stream_id=%s memory=%d attention=%d interest=%d",
            ticket.stream_id,
            len(result.memory_candidates),
            len(result.attention_candidates),
            len(result.interest_updates),
        )
