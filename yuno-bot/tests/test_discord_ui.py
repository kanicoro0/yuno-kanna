from types import SimpleNamespace
import unittest

from yuno.discord.ui import (
    DENIED_TEXT,
    EPHEMERAL_TEXT_LIMIT,
    STALE_TEXT,
    YunoView,
    require_permission,
    respond_ephemeral,
)
from yuno.permissions import PermissionLevel, PermissionService


class FakeResponse:
    def __init__(self):
        self.done = False
        self.calls = []

    def is_done(self):
        return self.done

    async def send_message(self, content, **kwargs):
        self.calls.append((content, kwargs))
        self.done = True


class FakeInteraction:
    def __init__(self, user_id, *, guild_id='1', administrator=False):
        self.user = SimpleNamespace(
            id=user_id,
            guild_permissions=SimpleNamespace(administrator=administrator),
        )
        self.guild_id = guild_id
        self.response = FakeResponse()
        self.edits = []

    async def edit_original_response(self, **kwargs):
        self.edits.append(kwargs)


class DiscordUiTests(unittest.IsolatedAsyncioTestCase):
    async def test_visible_button_label_has_no_internal_words(self):
        async def handler(interaction):
            pass

        view = YunoView(timeout=None)
        button = view.add_yuno_button(
            label='もう少し見る',
            custom_id='test:more',
            handler=handler,
        )

        self.assertEqual(button.label, 'もう少し見る')
        visible = ' '.join((button.label, STALE_TEXT, DENIED_TEXT)).casefold()
        for internal in ('caremark', 'readcue', 'db', 'env'):
            self.assertNotIn(internal, visible)

    async def test_permission_helper_allows_owner_and_admin(self):
        permissions = PermissionService({'10'})

        owner = FakeInteraction(10, guild_id=None)
        admin = FakeInteraction(20, administrator=True)

        self.assertTrue(await require_permission(
            owner, permissions, PermissionLevel.GUILD_ADMIN
        ))
        self.assertTrue(await require_permission(
            admin, permissions, PermissionLevel.GUILD_ADMIN
        ))

    async def test_permission_helper_rejects_user_ephemerally(self):
        interaction = FakeInteraction(20, administrator=False)

        allowed = await require_permission(
            interaction,
            PermissionService({'10'}),
            PermissionLevel.GUILD_ADMIN,
        )

        self.assertFalse(allowed)
        self.assertEqual(interaction.response.calls[0][0], DENIED_TEXT)
        self.assertTrue(interaction.response.calls[0][1]['ephemeral'])

    async def test_timeout_disables_buttons_and_stale_press_is_quiet(self):
        async def handler(interaction):
            pass

        view = YunoView(timeout=None)
        button = view.add_yuno_button(
            label='閉じる', custom_id='test:close', handler=handler
        )

        await view.on_timeout()
        interaction = FakeInteraction(10)

        self.assertTrue(view.is_stale)
        self.assertTrue(button.disabled)
        self.assertFalse(await view.interaction_check(interaction))
        self.assertEqual(interaction.response.calls[0][0], STALE_TEXT)

    async def test_timeout_ignores_message_refresh_failure(self):
        class MissingMessage:
            async def edit(self, **kwargs):
                raise RuntimeError('message is gone')

        view = YunoView(timeout=None)
        view.bind_message(MissingMessage())

        await view.on_timeout()

        self.assertTrue(view.is_stale)

    async def test_ephemeral_helper_bounds_and_then_edits_text(self):
        interaction = FakeInteraction(10)

        self.assertTrue(await respond_ephemeral(interaction, 'x' * 1000))
        sent = interaction.response.calls[0]
        self.assertEqual(len(sent[0]), EPHEMERAL_TEXT_LIMIT)
        self.assertTrue(sent[1]['ephemeral'])

        self.assertTrue(await respond_ephemeral(interaction, 'できたよ'))
        self.assertEqual(interaction.edits, [{'content': 'できたよ'}])


if __name__ == '__main__':
    unittest.main()
