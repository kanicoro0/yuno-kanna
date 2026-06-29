from pathlib import Path
import unittest

from yuno.conversation.context import SpeakerContext, SpeakerReference
from yuno.speaking.speaker import Speaker


ROOT = Path(__file__).resolve().parents[1]


class DesignGuardTests(unittest.TestCase):
    def test_design_principles_exist_and_readme_links_to_them(self) -> None:
        principles = ROOT / "docs" / "yuno_design_principles.md"
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertTrue(principles.exists())
        self.assertIn("docs/yuno_design_principles.md", readme)

    def test_speaker_surface_does_not_name_core_decisions(self) -> None:
        speaker = (ROOT / "yuno" / "speaking" / "speaker.py").read_text(encoding="utf-8")
        for forbidden in (
            "routing reason", "reply_mode", "interest_salience",
            "addressing_strength", "wants_to_speak", "should_speak",
        ):
            self.assertNotIn(forbidden, speaker)


class SpeakerReferenceBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_speaker_receives_reference_content_without_core_scores(self) -> None:
        class CapturingClient:
            def __init__(self):
                self.messages = []

            async def complete(self, messages):
                self.messages = messages
                return "返事"

        client = CapturingClient()
        context = SpeakerContext(
            history=({"role": "user", "content": "A: いまの話"},),
            references=(
                SpeakerReference("memory", "mem_0001", "参照する断片", "conversation"),
            ),
        )
        await Speaker(client).speak(context)
        payload = str(client.messages)
        self.assertIn("参照する断片", payload)
        for forbidden in (
            "interest_salience", "addressing_strength", "reply_mode",
            "wants_to_speak", "should_speak", "CareReader reason",
        ):
            self.assertNotIn(forbidden, payload)
