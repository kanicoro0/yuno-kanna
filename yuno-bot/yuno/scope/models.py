from dataclasses import dataclass
from enum import Enum
from typing import Dict, Union


DiscordId = Union[str, int]


class ScopeKind(str, Enum):
    GLOBAL = "global"
    GUILD = "guild"
    CHANNEL = "channel"
    STREAM = "stream"


@dataclass(frozen=True)
class GlobalScope:
    kind = ScopeKind.GLOBAL

    def to_dict(self) -> Dict[str, object]:
        return {"kind": self.kind.value}


@dataclass(frozen=True)
class GuildScope:
    guild_id: str
    kind = ScopeKind.GUILD

    def __init__(self, guild_id: DiscordId):
        object.__setattr__(self, "guild_id", _discord_id(guild_id, "guild_id"))

    def to_dict(self) -> Dict[str, object]:
        return {"kind": self.kind.value, "guild_id": self.guild_id}


@dataclass(frozen=True)
class ChannelScope:
    channel_id: str
    kind = ScopeKind.CHANNEL

    def __init__(self, channel_id: DiscordId):
        object.__setattr__(self, "channel_id", _discord_id(channel_id, "channel_id"))

    def to_dict(self) -> Dict[str, object]:
        return {"kind": self.kind.value, "channel_id": self.channel_id}


@dataclass(frozen=True)
class StreamScope:
    stream_id: int
    kind = ScopeKind.STREAM

    def __post_init__(self) -> None:
        if isinstance(self.stream_id, bool) or not isinstance(self.stream_id, int):
            raise TypeError("stream_id must be an integer")
        if self.stream_id <= 0:
            raise ValueError("stream_id must be positive")

    def to_dict(self) -> Dict[str, object]:
        return {"kind": self.kind.value, "stream_id": self.stream_id}


OperationScope = Union[GlobalScope, GuildScope, ChannelScope, StreamScope]


def _discord_id(value: DiscordId, name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{name} must not be empty")
    return normalized
