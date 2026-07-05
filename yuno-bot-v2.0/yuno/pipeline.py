from dataclasses import dataclass
import logging
from typing import Optional

from yuno.care.models import CareReadResult
from yuno.care.reader import CareReader
from yuno.care.service import CareService, cue_salience, overlaps_attention
from yuno.conversation.context import ContextBuilder
from yuno.conversation.reference_selector import ReferenceSelector
from yuno.conversation.repository import ConversationRepository
from yuno.discord.routing import MessageRouter
from yuno.messages import IncomingMessage, SentMessage
from yuno.speaking.speaker import Speaker
from yuno.turns import PipelineTurn


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
    source_user_message_ids: tuple[int, ...]
    user_content: str
    route_reason: str
    pre_care_completed: bool

    @property
    def single_source_user_message_id(self) -> int:
        if len(self.source_user_message_ids) != 1:
            raise ValueError("current CareService attribution requires one source message")
        return self.source_user_message_ids[0]

    @property
    def care_source_user_message_id(self) -> int:
        if not self.source_user_message_ids:
            raise ValueError("an observation must have at least one source message")
        return self.source_user_message_ids[-1]


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
        """Compatibility path: one eligible stored message becomes one turn."""
        turn = await self.intake(message)
        if turn is None:
            return PipelineResult(False, "", "none", None, None)
        return await self.process_turn(turn)

    async def intake(self, message: IncomingMessage) -> Optional[PipelineTurn]:
        """Route and store one Discord message without yet reading it as a turn."""
        route = await self.router.route(message)
        if not route.should_store:
            return None

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
        reply_to = (
            message.discord_message_id
            if route.reply_mode == "discord_reply"
            else None
        )
        return PipelineTurn.from_stored_message(
            user_record,
            should_reply=route.should_reply,
            route_reason=route.reason,
            reply_mode=route.reply_mode,
            reply_to_discord_message_id=reply_to,
        )

    async def process_turn(self, turn: PipelineTurn) -> PipelineResult:
        """Run existing CareReader/Speaker behavior for an already stored turn."""
        care_result = CareReadResult()
        include_care_mark_ids = []
        pre_care_completed = False
        if (
            turn.route_reason == "listening_only"
            and self.care_reader
            and self.care_service
        ):
            state = await self.care_service.current_state(turn.stream_id)
            salience = cue_salience(turn.content, state.read_cues)
            should_read = salience > 0 or overlaps_attention(
                turn.content, state.care_marks
            )
            if should_read:
                logger.debug(
                    "care_reader called before send stream_id=%s", turn.stream_id
                )
                request = await self.care_service.build_request(
                    turn.stream_id,
                    turn.content,
                    0.0,
                    salience,
                    state,
                )
                care_result = await self.care_reader.read(request)
                application = await self.care_service.apply(
                    turn.stream_id,
                    turn.care_source_user_message_id,
                    care_result,
                )
                include_care_mark_ids = list(
                    application.include_care_mark_ids
                )
                pre_care_completed = True
                logger.debug(
                    "care_reader result stream_id=%s memory=%d attention=%d cues=%d",
                    turn.stream_id,
                    sum(
                        item.kind == 'memory'
                        for item in care_result.care_mark_candidates
                    ),
                    sum(
                        item.kind == 'attention'
                        for item in care_result.care_mark_candidates
                    ),
                    len(care_result.read_cue_updates),
                )
            else:
                logger.debug("care_reader skipped stream_id=%s", turn.stream_id)

        listening_should_speak = (
            turn.route_reason == "listening_only"
            and care_result.wants_to_speak
            and care_result.should_speak
        )
        logger.debug(
            "listening speech decision stream_id=%s should_speak=%s",
            turn.stream_id, listening_should_speak,
        )
        should_speak = turn.should_reply or listening_should_speak
        if not should_speak:
            return PipelineResult(False, "", "none", turn.stream_id, None)

        care_mark_ids = include_care_mark_ids
        if turn.should_reply and self.reference_selector:
            selection = await self.reference_selector.select(
                turn.stream_id, turn.content
            )
            care_mark_ids = list(selection.care_mark_ids)
        context = await self.context_builder.build(
            turn.stream_id,
            care_mark_ids,
        )
        reply = await self.speaker.speak(context)
        reply_mode = turn.reply_mode if turn.should_reply else "plain"
        reply_to = (
            turn.reply_to_discord_message_id
            if reply_mode == "discord_reply"
            else None
        )
        ticket = ObservationTicket(
            stream_id=turn.stream_id,
            source_user_message_ids=turn.source_user_message_ids,
            user_content=turn.content,
            route_reason=turn.route_reason,
            pre_care_completed=pre_care_completed,
        )
        return PipelineResult(
            True, reply, reply_mode, turn.stream_id, reply_to, ticket
        )

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
        salience = cue_salience(ticket.user_content, state.read_cues)
        request = await self.care_service.build_request(
            ticket.stream_id,
            ticket.user_content,
            1.0,
            salience,
            state,
        )
        result = await self.care_reader.read(request)
        await self.care_service.apply(
            ticket.stream_id, ticket.care_source_user_message_id, result
        )
        logger.debug(
            "care_reader observed after send stream_id=%s memory=%d attention=%d cues=%d",
            ticket.stream_id,
            sum(
                item.kind == 'memory'
                for item in result.care_mark_candidates
            ),
            sum(
                item.kind == 'attention'
                for item in result.care_mark_candidates
            ),
            len(result.read_cue_updates),
        )
