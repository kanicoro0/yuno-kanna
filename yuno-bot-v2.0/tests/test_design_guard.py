from pathlib import Path
import unittest

from yuno.conversation.context import SpeakerContext, SpeakerReference
from yuno.app import status_text
from yuno.listening.models import ListeningChannel
from yuno.care.reader import CARE_SYSTEM_PROMPT
from yuno.speaking.speaker import SYSTEM_PROMPT
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

    def test_status_describes_care_reader_listening_behavior(self) -> None:
        text = status_text((ListeningChannel("10", "1", "db"),), ("ゆの",))
        self.assertIn("通常発言は保存", text)
        self.assertIn("CareReader", text)
        self.assertIn("必要な時だけ返答", text)

    def test_prompts_do_not_claim_unprovided_capabilities(self) -> None:
        self.assertIn("与えられていないものを見たふり", SYSTEM_PROMPT)
        for word in ("履歴", "references", "memory mark", "attention item"):
            self.assertNotIn(word, SYSTEM_PROMPT.casefold())
        for word in ("画像", "音声", "外部リンク"):
            self.assertIn(word, CARE_SYSTEM_PROMPT)
        self.assertIn("テキストだけ", CARE_SYSTEM_PROMPT)

    def test_command_responses_are_ephemeral(self) -> None:
        for relative in ("commands/core.py", "commands/listening.py"):
            source = (ROOT / "yuno" / relative).read_text(encoding="utf-8")
            self.assertIn("ephemeral=True", source)


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
        self.assertNotIn("mem_0001", payload)
        self.assertNotIn("public_id", payload)
        self.assertNotIn("\"kind\"", payload)
        self.assertNotIn("\"source\"", payload)
        self.assertNotIn("references", payload)
        for forbidden in (
            "interest_salience", "addressing_strength", "reply_mode",
            "wants_to_speak", "should_speak", "CareReader reason",
        ):
            self.assertNotIn(forbidden, payload)
