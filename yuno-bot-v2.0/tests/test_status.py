import unittest

from yuno.commands.status import create_status_command, status_text
from yuno.listening.models import ListeningChannel


class StatusTextTests(unittest.TestCase):
    def test_user_status_contains_only_safe_basic_information(self) -> None:
        text = status_text(
            (ListeningChannel("10", "1", "db"),),
            ("ゆの", "唯乃"),
        )

        self.assertIn("<#10>(db)", text)
        self.assertIn("ゆの、唯乃", text)
        for unsafe in ("DATABASE_FILE", "OPENAI_API_KEY", "Traceback", ":\\"):
            self.assertNotIn(unsafe, text)


class StatusCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_status_is_read_only_and_ephemeral(self) -> None:
        class ReadOnlyListening:
            def __init__(self) -> None:
                self.read_count = 0

            async def list_all(self):
                self.read_count += 1
                return [ListeningChannel("10", "1", "db")]

        class Response:
            def __init__(self) -> None:
                self.text = None
                self.ephemeral = None

            async def send_message(self, text, ephemeral=False) -> None:
                self.text = text
                self.ephemeral = ephemeral

        class Interaction:
            def __init__(self) -> None:
                self.response = Response()

        listening = ReadOnlyListening()
        interaction = Interaction()
        command = create_status_command(listening, ("ゆの",))

        await command.callback(interaction)

        self.assertEqual(listening.read_count, 1)
        self.assertIn("ゆのが聞いている範囲", interaction.response.text)
        self.assertTrue(interaction.response.ephemeral)


if __name__ == "__main__":
    unittest.main()
