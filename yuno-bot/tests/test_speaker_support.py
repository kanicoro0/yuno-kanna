import unittest

from yuno.conversation.context import SpeakerContext, SpeakerReference
from yuno.speaking.speaker import Speaker


class SpeakerSupportMessageTests(unittest.IsolatedAsyncioTestCase):
    async def test_speaker_note_is_kept_without_internal_labels(self) -> None:
        class CapturingClient:
            def __init__(self):
                self.messages = []

            async def complete(self, messages):
                self.messages = messages
                return "ok"

        client = CapturingClient()
        context = SpeakerContext(
            history=({"role": "user", "content": "A: こんにちは"},),
            reply_reason="followup",
            speaker_note="短く返して。",
        )

        await Speaker(client).speak(context)

        payload = str(client.messages)
        self.assertIn("短く返して。", payload)
        self.assertIn("さっきの流れの続きとして自然につないで大丈夫。", payload)
        self.assertNotIn("CareReader note:", payload)
        self.assertNotIn("CareReader reply_reason:", payload)
        self.assertNotIn("speaker_note", payload)
        self.assertNotIn("reply_reason", payload)
        self.assertNotIn("followup", payload)
        self.assertNotIn("CareReader", payload)

    async def test_references_still_pass_through_with_support_message(self) -> None:
        class CapturingClient:
            def __init__(self):
                self.messages = []

            async def complete(self, messages):
                self.messages = messages
                return "ok"

        client = CapturingClient()
        context = SpeakerContext(
            history=({"role": "user", "content": "A: 続きどうする？"},),
            references=(
                SpeakerReference("attention", "care_0001", "あの続きについて", "conversation"),
            ),
            speaker_note="一歩だけ進める感じで。",
        )

        await Speaker(client).speak(context)

        payload = str(client.messages)
        self.assertIn("一歩だけ進める感じで。", payload)
        self.assertIn("あの続きについて", payload)
        self.assertNotIn("care_0001", payload)
        self.assertNotIn("CareReader note:", payload)
        self.assertNotIn("speaker_note", payload)