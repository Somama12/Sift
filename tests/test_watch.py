import tempfile
import unittest
from pathlib import Path

from sift.core import apply
from sift.watch import dismiss, inbox_plan, watch_tick


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.downloads = self.root / "Downloads"
        self.destination = self.root / "Organized"
        self.downloads.mkdir()
        self.destination.mkdir()
        self.db = self.root / "watch.sqlite3"

    def tick(self, moment, *, stable_seconds=5):
        return watch_tick(self.downloads, self.destination, self.db, observed_at=moment, stable_seconds=stable_seconds)

    def test_existing_files_are_baseline_and_new_file_waits_for_stability(self):
        (self.downloads / "old receipt.txt").write_text("old", encoding="utf-8")
        self.assertTrue(self.tick(0)["initialized"])
        self.assertEqual(self.tick(1)["inbox"], 0)
        temporary = self.downloads / "new.part"
        temporary.write_text("partial", encoding="utf-8")
        self.assertEqual(self.tick(2)["pending"], 0)
        final = self.downloads / "receipt.txt"
        temporary.rename(final)
        self.assertEqual(self.tick(3)["pending"], 1)
        final.write_text("longer complete receipt", encoding="utf-8")
        self.assertEqual(self.tick(4)["pending"], 1)
        self.assertEqual(self.tick(8)["inbox"], 0)
        self.assertEqual(self.tick(9)["queued_now"], 1)
        plan = inbox_plan(self.downloads, self.db)
        self.assertEqual(len(plan["items"]), 1)
        self.assertEqual(plan["items"][0]["category"], "Receipts")
        self.assertFalse(plan["items"][0]["selected"])
        self.assertTrue(final.exists())

    def test_suggestions_persist_and_can_be_dismissed(self):
        self.tick(0)
        (self.downloads / "setup.pkg").write_text("installer", encoding="utf-8")
        self.tick(1)
        self.tick(7)
        plan = inbox_plan(self.downloads, self.db)
        self.assertEqual(len(plan["items"]), 1)
        self.assertFalse(plan["items"][0]["selected"])
        self.assertEqual(self.tick(8)["inbox"], 1)
        self.assertTrue(dismiss(plan["items"][0]["id"], self.db))
        self.assertEqual(len(inbox_plan(self.downloads, self.db)["items"]), 0)

    def test_approved_inbox_plan_uses_existing_apply_flow(self):
        self.tick(0)
        (self.downloads / "receipt.txt").write_text("example", encoding="utf-8")
        self.tick(1)
        self.tick(7)
        plan = inbox_plan(self.downloads, self.db)
        plan["items"][0]["selected"] = True
        _, results = apply(plan, {plan["items"][0]["id"]}, self.db)
        self.assertEqual(results[0]["state"], "applied")
        self.assertEqual(self.tick(8)["inbox"], 0)


if __name__ == "__main__":
    unittest.main()
