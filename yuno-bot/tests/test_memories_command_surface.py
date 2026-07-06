import unittest

from yuno.care_marks.models import CareMark
from yuno.commands.core import (
    _MARK_KIND_CHOICES,
    _MARK_STATUS_CHOICES,
    render_care_marks,
)


def mark(public_id, kind, status, text):
    return CareMark(
        id=1,
        public_id=public_id,
        stream_id=1,
        source_message_id=None,
        kind=kind,
        status=status,
        text=text,
        created_at="created",
        updated_at="updated",
    )


class MemoriesCommandSurfaceTests(unittest.TestCase):
    def test_render_care_marks_includes_public_id_for_status_command(self):
        text = render_care_marks((
            mark("cm_123", "memory", "active", "覚えておきたいこと"),
        ))

        self.assertIn("`cm_123`", text)
        self.assertIn("覚えている", text)
        self.assertIn("覚えておきたいこと", text)

    def test_add_and_status_commands_have_user_choices(self):
        kind_values = {choice.value for choice in _MARK_KIND_CHOICES}
        status_values = {choice.value for choice in _MARK_STATUS_CHOICES}

        self.assertEqual(kind_values, {"memory", "attention"})
        self.assertEqual(
            status_values,
            {"draft", "active", "open", "closed", "hidden"},
        )


if __name__ == "__main__":
    unittest.main()
