from dataclasses import dataclass
import logging
import time
from typing import Optional

from yuno.care.models import CareReadResult
from yuno.care.maintenance import CareMaintenanceService
from yuno.care.reader import CareReader
from yuno.care.service import (
    CareApplication,
    CareService,
    cue_salience,
    immediate_care_decision,
)
from yuno.care_marks.models import CareMark
from yuno.conversation.context import ContextBuilder
from yuno.conversation.reference_selector import ReferenceSelector
from yuno.conversation.repository import ConversationRepository
from yuno.discord.routing import MessageRouter
from yuno.messages import IncomingMessage, SentMessage
from yuno.speaking.speaker import Speaker
from yuno.turns import PipelineTurn


logger = logging.getLogger(__name__)
CARE_READER_ROUTE_REASONS = frozenset({
    "dm", "mention", "reply_to_yuno", "name_call", "listening_only", "name_seen",
})
PASSIVE_CARE_READER_ROUTE_REASONS = frozenset({"listening_only", "name_seen"})


@dataclass(frozen=True)
class PipelineResult:
    should_send: bool
    reply_text: str
    reply_mode: str
    stream_id: Optional[int]
    reply_to_discord_message_id: Optional[str]
    observation_ticket: Optional["ObservationTicket"] = None
    care_mark_changes: tuple[CareMark, ...] = ()


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
        maintenance_service: Optional[CareMaintenanceService] = None,
    ):
        self.router = router
        self.repository = repository
        self.context_builder = context_builder
        self.speaker = speaker
        self.care_reader = care_reader
        self.care_service = care_service
        self.reference_selector = reference_selector
        self.maintenance_service = maintenance_service

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
        """Read the turn, then call Speaker only when the final decision speaks."""
        care_result = CareReadResult()
        include_care_mark_ids = []
        pre_care_completed = False
        care_mark_changes: tuple[CareMark, ...] = ()
        if self._should_read_before_speaking(turn):
            state = await self.care_service.current_state(turn.stream_id)
            salience = cue_salience(turn.content, state.read_cues)
            trigger = immediate_care_decision(turn.content, state)
            if self._requires_care_trigger(turn) and not trigger.run:
                logger.debug(
                    "care_reader skipped before speech decision stream_id=%s route=%s reason=%s",
                    turn.stream_id,
                    turn.route_reason,
                    trigger.reason,
                )
            else:
                request = await self.care_service.build_request(
                    turn.stream_id,
                    turn.content,
                    _addressing_strength(turn.route_reason),
                    salience,
                    state,
                    route_reason=turn.route_reason,
                    reply_mode=turn.reply_mode,
                )
                logger.debug(
                    "care_reader called before speech decision stream_id=%s route=%s",
                    turn.stream_id,
                    turn.route_reason,
                )
                started = time.monotonic()
                try:
                    care_result = await self.care_reader.read(request)
                finally:
                    logger.info(
                        "timing care_read stream_id=%s phase=pre ms=%.1f",
                        turn.stream_id,
                        _elapsed_ms(started),
                    )
                started = time.monotonic()
                try:
                    application = await self.care_service.apply(
                        turn.stream_id,
                        turn.care_source_user_message_id,
                        care_result,
                    )
                finally:
                    logger.info(
                        "timing care_apply stream_id=%s phase=pre ms=%.1f",
                        turn.stream_id,
                        _elapsed_ms(started),
                    )
                await self._auto_maintain(turn.stream_id, application)
                include_care_mark_ids = list(application.include_care_mark_ids)
                care_mark_changes = application.affected_care_marks
                pre_care_completed = True
                logger.debug(
                    "care_reader result stream_id=%s decision=%s speak=%s reason=%s memory=%d attention=%d cues=%d",
                    turn.stream_id,
                    care_result.decision_made,
                    care_result.should_speak,
                    care_result.reply_reason,
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

        should_speak = self._should_speak(turn, care_result)
        logger.debug(
            "speech decision stream_id=%s route_reply=%s care_decision=%s should_speak=%s",
            turn.stream_id,
            turn.should_reply,
            care_result.decision_made,
            should_speak,
        )
        if not should_speak:
            return PipelineResult(
                False,
                "",
                "none",
                turn.stream_id,
                None,
                care_mark_changes=care_mark_changes,
            )

        care_mark_ids = include_care_mark_ids
        if self.reference_selector:
            selection = await self.reference_selector.select(
                turn.stream_id, turn.content
            )
            care_mark_ids = list(dict.fromkeys((
                *care_mark_ids,
                *selection.care_mark_ids,
            )))
        context = await self.context_builder.build(
            turn.stream_id,
            care_mark_ids,
            route_reason=turn.route_reason,
            reply_reason=care_result.reply_reason,
            speaker_note=care_result.speaker_note,
        )
        started = time.monotonic()
        try:
            reply = await self.speaker.speak(context)
        finally:
            logger.info(
                "timing speaker_generation stream_id=%s ms=%.1f",
                turn.stream_id,
                _elapsed_ms(started),
            )
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
            True,
            reply,
            reply_mode,
            turn.stream_id,
            reply_to,
            ticket,
            care_mark_changes,
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
    ) -> Optional[CareApplication]:
        if (
            ticket is None
            or ticket.pre_care_completed
            or not self.care_reader
            or not self.care_service
        ):
            return None
        state = await self.care_service.current_state(ticket.stream_id)
        decision = immediate_care_decision(ticket.user_content, state)
        if not decision.run:
            logger.debug(
                "post-send care_reader skipped stream_id=%s reason=%s",
                ticket.stream_id,
                decision.reason,
            )
            return None
        request = await self.care_service.build_request(
            ticket.stream_id,
            ticket.user_content,
            1.0,
            decision.cue_salience,
            state,
            route_reason=ticket.route_reason,
            reply_mode="plain",
        )
        started = time.monotonic()
        try:
            care_result = await self.care_reader.read(request)
        finally:
            logger.info(
                "timing care_read stream_id=%s phase=post ms=%.1f",
                ticket.stream_id,
                _elapsed_ms(started),
            )
        started = time.monotonic()
        try:
            application = await self.care_service.apply(
                ticket.stream_id,
                ticket.care_source_user_message_id,
                care_result,
            )
        finally:
            logger.info(
                "timing care_apply stream_id=%s phase=post ms=%.1f",
                ticket.stream_id,
                _elapsed_ms(started),
            )
        await self._auto_maintain(ticket.stream_id, application)
        logger.debug(
            "post-send care_reader result stream_id=%s memory=%d attention=%d cues=%d",
            ticket.stream_id,
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
        return application

    async def _auto_maintain(
        self, stream_id: int, application: CareApplication
    ) -> None:
        if self.maintenance_service is None:
            return
        if not application.created_care_mark_ids:
            return
        started = time.monotonic()
        try:
            await self.maintenance_service.auto_close_after_activity(
                stream_id,
                protected_public_ids=tuple(dict.fromkeys((
                    *application.created_care_mark_ids,
                    *(
                        mark.public_id
                        for mark in application.affected_care_marks
                    ),
                ))),
            )
        except Exception:
            logger.exception("automatic care maintenance failed")
        finally:
            logger.info(
                "timing auto_maintenance stream_id=%s ms=%.1f",
                stream_id,
                _elapsed_ms(started),
            )

    def _should_read_before_speaking(self, turn: PipelineTurn) -> bool:
        return (
            turn.route_reason in CARE_READER_ROUTE_REASONS
            and self.care_reader is not None
            and self.care_service is not None
        )

    def _requires_care_trigger(self, turn: PipelineTurn) -> bool:
        return turn.route_reason in PASSIVE_CARE_READER_ROUTE_REASONS

    def _should_speak(
        self, turn: PipelineTurn, care_result: CareReadResult
    ) -> bool:
        if care_result.decision_made:
            return care_result.should_speak
        return turn.should_reply


def _addressing_strength(route_reason: str) -> float:
    if route_reason in {"dm", "mention", "reply_to_yuno"}:
        return 1.0
    if route_reason == "name_call":
        return 0.8
    if route_reason == "name_seen":
        return 0.3
    return 0.0


def _elapsed_ms(started: float) -> float:
    return (time.monotonic() - started) * 1000
