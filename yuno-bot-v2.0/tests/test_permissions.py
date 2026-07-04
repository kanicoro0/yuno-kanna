import unittest

from yuno.permissions import (
    ActorIdentity,
    DiscordPermissionContext,
    PermissionLevel,
    PermissionService,
)


class PermissionServiceTests(unittest.TestCase):
    def test_owner_is_allowed_for_owner_action(self) -> None:
        service = PermissionService({"10"})

        self.assertTrue(
            service.allows(ActorIdentity("10"), PermissionLevel.OWNER)
        )

    def test_guild_admin_is_allowed_for_guild_admin_action(self) -> None:
        service = PermissionService()
        discord = DiscordPermissionContext(guild_id="100", is_guild_admin=True)

        self.assertTrue(
            service.allows(
                ActorIdentity("20"), PermissionLevel.GUILD_ADMIN, discord
            )
        )
        self.assertFalse(
            service.allows(ActorIdentity("20"), PermissionLevel.OWNER, discord)
        )

    def test_normal_user_is_denied_for_admin_action(self) -> None:
        service = PermissionService()

        self.assertFalse(
            service.allows(ActorIdentity("20"), PermissionLevel.GUILD_ADMIN)
        )

    def test_missing_guild_context_does_not_grant_guild_admin(self) -> None:
        service = PermissionService()
        discord = DiscordPermissionContext(is_guild_admin=True)

        self.assertEqual(
            service.level_for(ActorIdentity("20"), discord), PermissionLevel.USER
        )

    def test_no_configured_owner_does_not_grant_owner(self) -> None:
        service = PermissionService()

        self.assertFalse(
            service.allows(ActorIdentity("10"), PermissionLevel.OWNER)
        )


if __name__ == "__main__":
    unittest.main()
