import unittest

from yuno.config import _call_names


class ConfigTests(unittest.TestCase):
    def test_default_call_names(self) -> None:
        self.assertEqual(_call_names(""), ("ゆの", "唯乃", "yuno"))

    def test_call_names_are_trimmed_and_deduplicated(self) -> None:
        self.assertEqual(_call_names(" ゆの, yuno,ゆの "), ("ゆの", "yuno"))
