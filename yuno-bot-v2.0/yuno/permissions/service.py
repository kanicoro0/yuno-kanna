from typing import Iterable

from yuno.permissions.models import (
    ActorIdentity,
    DiscordPermissionContext,
    PermissionLevel,
)


class PermissionService:
    """Code-owned permission decisions shared by UI and future tool paths."""

    def __init__(self, owner_user_ids: Iterable[str] = ()):
        self._owner_user_ids = frozenset(
            str(user_id).strip() for user_id in owner_user_ids if str(user_id).strip()
        )

    def level_for(
        self,
        actor: ActorIdentity,
        discord: DiscordPermissionContext = DiscordPermissionContext(),
    ) -> PermissionLevel:
        if actor.user_id in self._owner_user_ids:
            return PermissionLevel.OWNER
        if discord.guild_id is not None and discord.is_guild_admin:
            return PermissionLevel.GUILD_ADMIN
        return PermissionLevel.USER

    def allows(
        self,
        actor: ActorIdentity,
        required: PermissionLevel,
        discord: DiscordPermissionContext = DiscordPermissionContext(),
    ) -> bool:
        return self.level_for(actor, discord) >= required
