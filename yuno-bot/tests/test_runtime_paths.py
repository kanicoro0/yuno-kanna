import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from yuno.app import create_bot
from yuno.config import PROJECT_ROOT, load_settings, resolve_database_path


class RuntimePathTests(unittest.IsolatedAsyncioTestCase):
    async def test_relative_database_path_is_project_root_based_from_any_cwd(self) -> None:
        expected = (PROJECT_ROOT / "data" / "yuno.sqlite3").resolve()
        original = Path.cwd()
        try:
            for cwd in (PROJECT_ROOT, PROJECT_ROOT.parent):
                os.chdir(cwd)
                with patch("yuno.config.load_dotenv"), patch.dict(
                    os.environ, {"DATABASE_FILE": "data/yuno.sqlite3"}, clear=True
                ):
                    settings = load_settings()
                    bot = create_bot(settings)
                    try:
                        self.assertEqual(bot.settings.database_file, expected)
                    finally:
                        await bot.close()
        finally:
            os.chdir(original)

    def test_absolute_database_path_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            absolute = (Path(directory) / "custom.sqlite3").resolve()
            self.assertEqual(resolve_database_path(str(absolute)), absolute)

    def test_gitignores_cover_runtime_files(self) -> None:
        root_ignore = (PROJECT_ROOT.parent / ".gitignore").read_text(encoding="utf-8")
        local_ignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("/data/", root_ignore)
        self.assertIn("yuno-bot-v2.0/data/", root_ignore)
        for pattern in ("*.sqlite3", "*.sqlite3-shm", "*.sqlite3-wal", "*.db", ".env"):
            self.assertTrue(pattern in root_ignore or pattern in local_ignore)
