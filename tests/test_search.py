import tempfile
import unittest
from pathlib import Path

from sift.core import search


class SearchTests(unittest.TestCase):
    def test_finds_name_and_content_and_skips_projects(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "Lease Agreement.txt").write_text("rental terms", encoding="utf-8")
            (root / "scan001.txt").write_text("lease agreement with landlord", encoding="utf-8")
            (root / "unrelated.txt").write_text("school notes", encoding="utf-8")
            (root / "project" / ".git").mkdir(parents=True)
            (root / "project" / "lease.txt").write_text("lease", encoding="utf-8")
            results = search(root, "find my lease agreement")
            self.assertEqual([Path(item["path"]).name for item in results], ["Lease Agreement.txt", "scan001.txt"])
            self.assertGreater(results[0]["score"], results[1]["score"])


if __name__ == "__main__":
    unittest.main()
