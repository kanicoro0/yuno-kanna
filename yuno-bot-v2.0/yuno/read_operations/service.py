from typing import List

from yuno.conversation.models import ConversationMessage
from yuno.conversation.repository import ConversationRepository
from yuno.read_operations.models import (
    ReadOperation,
    ReadOperationResult,
    ReadPersistence,
    ReadPurpose,
    ReadRange,
    ReadSource,
    UnsupportedReadOperation,
)


MAX_LAST_N = 50
MAX_SUMMARY_INPUT_CHARACTERS = 6_000
EMPTY_SUMMARY_INPUT = 'Range read: no visible messages in the current stream.'


class ReadOperationService:
    '''Prepare bounded ConversationLog text for a later summarization step.'''

    def __init__(self, repository: ConversationRepository):
        self.repository = repository

    async def read(
        self,
        operation: ReadOperation,
        *,
        current_stream_id: int,
    ) -> ReadOperationResult:
        self._require_supported(operation)
        requested = operation.last_n
        if requested < 1:
            raise ValueError('last_n must be positive')
        limit = min(requested, MAX_LAST_N)
        messages = await self.repository.recent(current_stream_id, limit)
        if not messages:
            return ReadOperationResult(
                range_read='no visible messages in current stream',
                summary_input=EMPTY_SUMMARY_INPUT,
                message_count=0,
            )

        range_read = f'last {len(messages)} visible messages in current stream'
        header = f'Range read: {range_read}.\n'
        body = _bounded_transcript(
            messages,
            MAX_SUMMARY_INPUT_CHARACTERS - len(header),
        )
        return ReadOperationResult(
            range_read=range_read,
            summary_input=header + body,
            message_count=len(messages),
        )

    @staticmethod
    def _require_supported(operation: ReadOperation) -> None:
        supported = (
            operation.source is ReadSource.CURRENT_STREAM
            and operation.range is ReadRange.LAST_N
            and operation.purpose is ReadPurpose.SUMMARIZE
            and operation.persistence is ReadPersistence.REPLY_ONLY
        )
        if not supported:
            raise UnsupportedReadOperation(
                'only current_stream + last_n + summarize + reply_only is supported'
            )


def _bounded_transcript(
    messages: List[ConversationMessage],
    character_limit: int,
) -> str:
    selected: List[str] = []
    remaining = max(0, character_limit)
    for message in reversed(messages):
        rendered = _safe_render(message)
        separator_size = 1 if selected else 0
        available = remaining - separator_size
        if available <= 0:
            break
        if len(rendered) > available:
            rendered = rendered[:available]
        selected.append(rendered)
        remaining -= len(rendered) + separator_size
        if remaining <= 0:
            break
    return '\n'.join(reversed(selected))


def _safe_render(message: ConversationMessage) -> str:
    if message.role == 'user':
        return f'{message.author_name}: {message.content}'
    return f'Yuno: {message.content}'
