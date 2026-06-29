from typing import List, Optional, Tuple

from yuno.attention.models import AttentionItem
from yuno.attention.service import AttentionService
from yuno.care.safety import looks_sensitive
from yuno.conversation.models import Stream
from yuno.conversation.repository import ConversationRepository
from yuno.interest.models import InterestTerm
from yuno.interest.service import InterestService, normalize_term
from yuno.memory.models import MemoryMark
from yuno.memory.service import MemoryMarkService


MEMORY_STATUSES = ("pending", "active", "hidden")
ATTENTION_STATUSES = ("open", "closed", "hidden")
INTEREST_STATUSES = ("active", "sleeping", "hidden")


class CoreAdminService:
    def __init__(
        self,
        conversations: ConversationRepository,
        memory: MemoryMarkService,
        attention: AttentionService,
        interest: InterestService,
    ):
        self.conversations = conversations
        self.memory = memory
        self.attention = attention
        self.interest = interest

    async def stream(
        self, channel_id: str, guild_id: Optional[str], create: bool = False
    ) -> Optional[Stream]:
        existing = await self.conversations.get_stream_by_channel_id(channel_id)
        if existing or not create:
            return existing
        return await self.conversations.get_or_create_stream(
            "dm" if guild_id is None else "channel", channel_id, guild_id
        )

    async def list_memory(
        self, channel_id: str, guild_id: Optional[str], status: str, limit: int
    ) -> List[MemoryMark]:
        stream = await self.stream(channel_id, guild_id)
        if not stream:
            return []
        statuses = MEMORY_STATUSES if status == "all" else (status,)
        return await self.memory.repository.list_for_stream(stream.id, statuses, _limit(limit))

    async def add_memory(
        self, channel_id: str, guild_id: Optional[str], content: str,
        status: str = "pending", kind: str = "pin",
    ) -> MemoryMark:
        stream = await self.stream(channel_id, guild_id, True)
        selected_status = status if status in {"pending", "active"} else "pending"
        if selected_status == "active" and looks_sensitive(content):
            selected_status = "pending"
        return await self.memory.create_manual(stream.id, content, kind, selected_status)

    async def set_memory_status(
        self, channel_id: str, public_id: str, status: str
    ) -> Optional[MemoryMark]:
        stream = await self.conversations.get_stream_by_channel_id(channel_id)
        item = await self.memory.repository.get_by_public_id(public_id)
        if not stream or not item or item.stream_id != stream.id:
            return None
        if status == "active":
            return await self.memory.activate(public_id)
        if status == "hidden":
            return await self.memory.hide(public_id)
        if status == "pending":
            return await self.memory.restore_to_pending(public_id)
        raise ValueError("invalid memory status")

    async def list_attention(
        self, channel_id: str, guild_id: Optional[str], status: str, limit: int
    ) -> List[AttentionItem]:
        stream = await self.stream(channel_id, guild_id)
        if not stream:
            return []
        statuses = ATTENTION_STATUSES if status == "all" else (status,)
        return await self.attention.repository.list_for_stream(stream.id, statuses, _limit(limit))

    async def add_attention(
        self, channel_id: str, guild_id: Optional[str], text: str, rank: float = 0.5
    ) -> AttentionItem:
        stream = await self.stream(channel_id, guild_id, True)
        return await self.attention.create_open(stream.id, text, rank=_clamp(rank))

    async def set_attention_status(
        self, channel_id: str, public_id: str, status: str
    ) -> Optional[AttentionItem]:
        stream = await self.conversations.get_stream_by_channel_id(channel_id)
        item = await self.attention.repository.get_by_public_id(public_id)
        if not stream or not item or item.stream_id != stream.id:
            return None
        if status == "closed":
            return await self.attention.close(public_id)
        if status == "hidden":
            return await self.attention.hide(public_id)
        if status == "open":
            return await self.attention.reopen(public_id)
        raise ValueError("invalid attention status")

    async def list_interest(
        self, channel_id: str, guild_id: Optional[str], status: str, limit: int
    ) -> List[InterestTerm]:
        stream = await self.stream(channel_id, guild_id)
        if not stream:
            return []
        statuses = INTEREST_STATUSES if status == "all" else (status,)
        return await self.interest.repository.list_for_stream(stream.id, statuses, _limit(limit))

    async def add_interest(
        self, channel_id: str, guild_id: Optional[str], term: str, weight: float = 0.3
    ) -> InterestTerm:
        stream = await self.stream(channel_id, guild_id, True)
        return await self.interest.repository.upsert_term(
            stream.id, normalize_term(term), _clamp(weight), "manual"
        )

    async def set_interest_status(
        self, channel_id: str, public_id: str, status: str
    ) -> Optional[InterestTerm]:
        stream = await self.conversations.get_stream_by_channel_id(channel_id)
        item = await self.interest.repository.get_by_public_id(public_id)
        if not stream or not item or item.stream_id != stream.id:
            return None
        if status == "hidden":
            return await self.interest.hide(public_id)
        if status == "sleeping":
            return await self.interest.sleep(public_id)
        if status == "active":
            return await self.interest.wake(public_id)
        raise ValueError("invalid interest status")


def _limit(value: int) -> int:
    return max(1, min(20, int(value)))


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
