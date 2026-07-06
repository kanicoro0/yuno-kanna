from typing import Iterable, List, Optional, Set

from yuno.listening.models import ListeningChange, ListeningChannel
from yuno.listening.repository import ListeningChannelRepository


class ListeningChannelService:
    def __init__(
        self,
        repository: ListeningChannelRepository,
        env_channel_ids: Iterable[int] = (),
    ):
        self.repository = repository
        self.env_channel_ids: Set[str] = {str(value) for value in env_channel_ids}

    async def list_all(self) -> List[ListeningChannel]:
        db_items = await self.repository.list_all()
        by_id = {item.discord_channel_id: item for item in db_items}
        for channel_id in self.env_channel_ids:
            by_id[channel_id] = ListeningChannel(channel_id, None, "env")
        return sorted(by_id.values(), key=lambda item: int(item.discord_channel_id))

    async def list_for_guild(self, guild_id: str) -> List[ListeningChannel]:
        items = await self.repository.list_for_guild(guild_id)
        by_id = {item.discord_channel_id: item for item in items}
        for channel_id in self.env_channel_ids:
            by_id[channel_id] = ListeningChannel(channel_id, None, "env")
        return sorted(by_id.values(), key=lambda item: int(item.discord_channel_id))

    async def add(self, channel_id: str, guild_id: str) -> ListeningChange:
        if channel_id in self.env_channel_ids:
            return ListeningChange(False, "env", "already_listening")
        if await self.repository.get(channel_id):
            return ListeningChange(False, "db", "already_listening")
        await self.repository.add(channel_id, guild_id)
        return ListeningChange(True, "db", "added")

    async def remove(self, channel_id: str) -> ListeningChange:
        if channel_id in self.env_channel_ids:
            return ListeningChange(False, "env", "env_protected")
        removed = await self.repository.remove(channel_id)
        return ListeningChange(removed, "db" if removed else None,
                               "removed" if removed else "not_found")

    async def clear(self, guild_id: Optional[str] = None) -> int:
        return await self.repository.clear(guild_id)

    async def is_listening(self, channel_id: str) -> bool:
        return channel_id in self.env_channel_ids or await self.repository.get(channel_id) is not None

    async def sources(self, channel_id: str) -> Set[str]:
        result = set()
        if channel_id in self.env_channel_ids:
            result.add("env")
        if await self.repository.get(channel_id):
            result.add("db")
        return result
