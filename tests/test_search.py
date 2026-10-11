import tempfile
import unittest
import os
from datetime import datetime
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

    def test_all_terms_and_filters(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "lease agreement.txt"
            target.write_text("landlord", encoding="utf-8")
            (root / "lease only.txt").write_text("unrelated", encoding="utf-8")
            (root / "lease agreement.md").write_text("landlord", encoding="utf-8")
            last_year = datetime.now().year - 1
            timestamp = datetime(last_year, 6, 1).timestamp()
            os.utime(target, (timestamp, timestamp))
            results = search(root, "find lease agreement ext:txt last year")
            self.assertEqual([Path(row["path"]).name for row in results], [target.name])
            self.assertEqual([Path(row["path"]).name for row in search(root, f"year:{last_year} ext:txt")], [target.name])


if __name__ == "__main__":
    unittest.main()
