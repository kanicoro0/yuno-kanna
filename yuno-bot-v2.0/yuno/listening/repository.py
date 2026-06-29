from typing import List, Optional

from yuno.conversation.models import utc_now
from yuno.infra.database import Database
from yuno.listening.models import ListeningChannel


class ListeningChannelRepository:
    def __init__(self, database: Database):
        self.database = database

    async def list_all(self) -> List[ListeningChannel]:
        rows = await (await self.database.connection.execute(
            "SELECT * FROM listening_channels ORDER BY discord_channel_id"
        )).fetchall()
        return [self._model(row) for row in rows]

    async def list_for_guild(self, guild_id: str) -> List[ListeningChannel]:
        rows = await (await self.database.connection.execute(
            """SELECT * FROM listening_channels
               WHERE discord_guild_id = ? ORDER BY discord_channel_id""",
            (guild_id,),
        )).fetchall()
        return [self._model(row) for row in rows]

    async def get(self, channel_id: str) -> Optional[ListeningChannel]:
        row = await (await self.database.connection.execute(
            "SELECT * FROM listening_channels WHERE discord_channel_id = ?",
            (channel_id,),
        )).fetchone()
        return self._model(row) if row else None

    async def add(self, channel_id: str, guild_id: str) -> ListeningChannel:
        await self.database.connection.execute(
            """INSERT INTO listening_channels(
                   discord_channel_id, discord_guild_id, created_at
               ) VALUES (?, ?, ?)
               ON CONFLICT(discord_channel_id) DO NOTHING""",
            (channel_id, guild_id, utc_now()),
        )
        await self.database.connection.commit()
        item = await self.get(channel_id)
        if item is None:
            raise RuntimeError("failed to add listening channel")
        return item

    async def remove(self, channel_id: str) -> bool:
        cursor = await self.database.connection.execute(
            "DELETE FROM listening_channels WHERE discord_channel_id = ?",
            (channel_id,),
        )
        await self.database.connection.commit()
        return cursor.rowcount > 0

    async def clear(self, guild_id: Optional[str] = None) -> int:
        if guild_id is None:
            cursor = await self.database.connection.execute(
                "DELETE FROM listening_channels"
            )
        else:
            cursor = await self.database.connection.execute(
                "DELETE FROM listening_channels WHERE discord_guild_id = ?",
                (guild_id,),
            )
        await self.database.connection.commit()
        return cursor.rowcount

    @staticmethod
    def _model(row) -> ListeningChannel:
        return ListeningChannel(
            discord_channel_id=row["discord_channel_id"],
            discord_guild_id=row["discord_guild_id"],
            source="db",
            created_at=row["created_at"],
        )
