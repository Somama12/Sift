import tempfile
import unittest
from pathlib import Path

from sift.core import duplicates


class DuplicateTests(unittest.TestCase):
    def test_reports_only_exact_duplicates_without_modifying_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            (source / "one.txt").write_text("same content", encoding="utf-8")
            (source / "nested").mkdir()
            (source / "nested" / "two.txt").write_text("same content", encoding="utf-8")
            (source / "different.txt").write_text("othercontent", encoding="utf-8")
            (source / "project" / ".git").mkdir(parents=True)
            (source / "project" / "copy.txt").write_text("same content", encoding="utf-8")
            result = duplicates(source)
            self.assertEqual(len(result), 1)
            self.assertEqual({Path(path).name for path in result[0]["paths"]}, {"one.txt", "two.txt"})
            self.assertTrue((source / "one.txt").exists())
            self.assertTrue((source / "nested" / "two.txt").exists())


if __name__ == "__main__":
    unittest.main()
