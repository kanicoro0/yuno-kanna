from typing import Dict, List

from yuno.conversation.context import RECENT_MESSAGE_LIMIT, build_speaker_history
from yuno.conversation.repository import ConversationRepository


class ConversationService:
    def __init__(self, repository: ConversationRepository):
        self.repository = repository

    async def speaker_history(self, stream_id: int) -> List[Dict[str, str]]:
        recent = await self.repository.recent(stream_id, RECENT_MESSAGE_LIMIT)
        return build_speaker_history(recent)
