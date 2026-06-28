from pathlib import Path
import tempfile
import unittest

from yuno.conversation.repository import ConversationRepository
from yuno.conversation.service import ConversationService
from yuno.infra.database import Database
from yuno.infra.openai_client import OpenAITextClient
from yuno.speaking.speaker import Speaker


class PipelineSmokeTests(unittest.IsolatedAsyncioTestCase):
    async def test_mock_one_turn_is_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "smoke.sqlite3")
            await database.open()
            try:
                repository = ConversationRepository(database)
                stream = await repository.get_or_create_stream("dm", "10", None)
                await repository.append(
                    stream.id, "user-1", "user", "7", "こはる", "まだいる？"
                )
                history = await ConversationService(repository).speaker_history(stream.id)
                reply = await Speaker(OpenAITextClient("", "")).speak(history)
                await repository.append(
                    stream.id, "bot-1", "assistant", "99", "ゆの", reply
                )

                persisted = await repository.recent(stream.id)
                self.assertEqual(len(persisted), 2)
                self.assertEqual(persisted[0].content, "まだいる？")
                self.assertEqual(persisted[1].role, "assistant")
                self.assertTrue(persisted[1].content)
            finally:
                await database.close()
