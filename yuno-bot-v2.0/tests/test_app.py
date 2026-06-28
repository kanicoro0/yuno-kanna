from pathlib import Path
import tempfile
import unittest

from yuno.app import create_bot
from yuno.config import Settings


class AppTests(unittest.TestCase):
    def test_bot_can_be_constructed_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(
                discord_token="",
                discord_client_id=None,
                openai_api_key="",
                openai_model="",
                database_file=Path(directory) / "test.sqlite3",
                listening_channel_ids=frozenset({123}),
                yuno_call_names=("ゆの", "唯乃", "yuno"),
                log_level="INFO",
            )
            bot = create_bot(settings)
            self.assertEqual(bot.settings.listening_channel_ids, frozenset({123}))
            self.assertIn("status", [command.name for command in bot.tree.get_commands()])
