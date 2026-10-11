import stat
import tempfile
import unittest
from pathlib import Path

from sift.core import apply, scan


class CorrectionTests(unittest.TestCase):
    def test_approved_edit_is_suggested_for_identical_file_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Downloads"
            destination = root / "Organized"
            source.mkdir()
            destination.mkdir()
            file = source / "scan001.txt"
            file.write_text("Notice for a rental property", encoding="utf-8")
            database = root / "state" / "sift.sqlite3"

            plan = scan(source, destination, db_path=database)
            item = plan["items"][0]
            self.assertEqual(item["category"], "Review")
            item["destination_folder"] = str(destination.resolve() / "Legal")
            item["name"] = "Rental Notice.txt"
            _, results = apply(plan, {item["id"]}, database)
            self.assertEqual(results[0]["state"], "applied", results)
            self.assertEqual(stat.S_IMODE(database.stat().st_mode), 0o600)

            duplicate = source / "new-copy.txt"
            duplicate.write_text("Notice for a rental property", encoding="utf-8")
            remembered = scan(source, destination, db_path=database)["items"][0]
            self.assertEqual(remembered["destination_folder"], str(destination.resolve() / "Legal"))
            self.assertEqual(remembered["name"], "Rental Notice.txt")
            self.assertEqual(remembered["reason"], "saved correction for identical file")
            self.assertFalse(remembered["selected"])

            duplicate.write_text("Different content", encoding="utf-8")
            changed = scan(source, destination, db_path=database)["items"][0]
            self.assertEqual(changed["category"], "Review")
            self.assertEqual(changed["reason"], "no reliable category")

    def test_unavailable_memory_does_not_hide_scan_proposals(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Downloads"
            destination = root / "Organized"
            source.mkdir()
            destination.mkdir()
            (source / "receipt.txt").write_text("receipt", encoding="utf-8")
            plan = scan(source, destination, db_path=source)
            self.assertEqual(len(plan["items"]), 1)


if __name__ == "__main__":
    unittest.main()
