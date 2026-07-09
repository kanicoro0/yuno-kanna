import unittest

from yuno.commands.guide import GUIDE_TEXT, create_guide_command


class FakeResponse:
    def __init__(self):
        self.calls = []

    async def send_message(self, content, **kwargs):
        self.calls.append((content, kwargs))


class FakeInteraction:
    def __init__(self):
        self.response = FakeResponse()


class GuideTests(unittest.IsolatedAsyncioTestCase):
    def test_guide_text_names_current_user_actions(self):
        for visible in (
            '/status',
            '/listening',
            '/memories list',
            '/memories recent',
            'ゆのに預ける',
            '残す',
            'あとで見る',
            '閉じる',
            '隠す',
            '戻す',
        ):
            self.assertIn(visible, GUIDE_TEXT)
        self.assertIn('会話の中でそのまま頼めるよ', GUIDE_TEXT)
        self.assertIn('コマンドか右クリックから開いてね', GUIDE_TEXT)
        self.assertNotIn('ボタンはつかない', GUIDE_TEXT)

    def test_guide_text_hides_internal_names(self):
        for internal in (
            'CareMark',
            'ReadCue',
            'source_message_id',
            'public_id',
            'memory',
            'attention',
            'draft',
            'active',
            'hidden',
            'service',
            'class',
            'sync',
            'DB',
        ):
            self.assertNotIn(internal, GUIDE_TEXT)

    async def test_guide_command_replies_ephemerally_without_view(self):
        command = create_guide_command()
        interaction = FakeInteraction()

        await command.callback(interaction)

        content, kwargs = interaction.response.calls[0]
        self.assertEqual(content, GUIDE_TEXT)
        self.assertTrue(kwargs['ephemeral'])
        self.assertNotIn('view', kwargs)


if __name__ == '__main__':
    unittest.main()
