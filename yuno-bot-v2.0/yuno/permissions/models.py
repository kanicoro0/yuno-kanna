from dataclasses import dataclass
from enum import IntEnum
from typing import Optional


class PermissionLevel(IntEnum):
    USER = 1
    GUILD_ADMIN = 2
    OWNER = 3


@dataclass(frozen=True)
class ActorIdentity:
    user_id: str


@dataclass(frozen=True)
class DiscordPermissionContext:
    guild_id: Optional[str] = None
    is_guild_admin: bool = False
