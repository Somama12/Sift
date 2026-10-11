import tempfile
import unittest
import json
import importlib.util
from pathlib import Path
from unittest.mock import patch

from sift.core import apply, history, recover, scan, undo
from sift.cli import main


class SiftTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "Downloads"
        self.destination = self.root / "Organized"
        self.source.mkdir()
        self.destination.mkdir()
        self.db = self.root / "sift.sqlite3"

    def test_scan_skips_projects_temporary_and_destination(self):
        (self.source / "project" / ".git").mkdir(parents=True)
        (self.source / "project" / "notes.txt").write_text("contract", encoding="utf-8")
        (self.source / "unfinished.crdownload").write_text("receipt", encoding="utf-8")
        (self.source / "scan0023.txt").write_text("Invoice from Smith", encoding="utf-8")
        plan = scan(self.source, self.destination)
        self.assertEqual(len(plan["items"]), 1)
        self.assertEqual(plan["items"][0]["category"], "Receipts")
        self.assertEqual(plan["items"][0]["name"], "Invoice from Smith.txt")
        self.assertTrue((self.source / "scan0023.txt").exists())

    def test_apply_collision_and_batch_undo(self):
        (self.source / "receipt.txt").write_text("first", encoding="utf-8")
        (self.source / "other").mkdir()
        (self.source / "other" / "receipt.txt").write_text("second", encoding="utf-8")
        plan = scan(self.source, self.destination)
        batch, results = apply(plan, {item["id"] for item in plan["items"]}, self.db)
        self.assertEqual([row["state"] for row in results], ["applied", "applied"])
        self.assertTrue((self.destination / "Receipts" / "receipt.txt").exists())
        self.assertTrue((self.destination / "Receipts" / "receipt (2).txt").exists())
        self.assertEqual(history(self.db)[0]["applied"], 2)
        self.assertEqual([row["state"] for row in undo(batch, self.db)], ["undone", "undone"])
        self.assertEqual((self.source / "receipt.txt").read_text(), "first")
        self.assertEqual((self.source / "other" / "receipt.txt").read_text(), "second")

    def test_changed_source_is_not_moved(self):
        file = self.source / "receipt.txt"
        file.write_text("old", encoding="utf-8")
        plan = scan(self.source, self.destination)
        file.write_text("different", encoding="utf-8")
        _, result = apply(plan, {plan["items"][0]["id"]}, self.db)
        self.assertEqual(result[0]["state"], "failed")
        self.assertEqual(file.read_text(), "different")

    def test_review_selects_low_confidence_proposal(self):
        (self.source / "scan001.txt").write_text("Invoice from Smith", encoding="utf-8")
        plan_file = self.root / "plan.json"
        plan_file.write_text(json.dumps(scan(self.source, self.destination)), encoding="utf-8")
        self.assertFalse(json.loads(plan_file.read_text())["items"][0]["selected"])
        with patch("builtins.input", return_value="y"):
            self.assertEqual(main(["review", str(plan_file)]), 0)
        self.assertTrue(json.loads(plan_file.read_text())["items"][0]["selected"])

    def test_folder_mapping_uses_existing_structure(self):
        (self.source / "receipt.txt").write_text("example", encoding="utf-8")
        target = self.destination / "Finance" / "Invoices"
        target.mkdir(parents=True)
        plan = scan(self.source, self.destination, {"Receipts": "Finance/Invoices"})
        self.assertEqual(plan["items"][0]["destination_folder"], str(target.resolve()))
        with self.assertRaises(ValueError):
            scan(self.source, self.destination, {"Receipts": "../outside"})

    @unittest.skipUnless(importlib.util.find_spec("pypdf"), "PDF extra is not installed")
    def test_extracts_text_from_pdf(self):
        fixture = Path(__file__).parent / "fixtures" / "invoice.pdf"
        file = self.source / "scan004.pdf"
        file.write_bytes(fixture.read_bytes())
        plan = scan(self.source, self.destination)
        self.assertEqual(len(plan["items"]), 1)
        self.assertEqual(plan["items"][0]["category"], "Receipts")
        self.assertEqual(plan["items"][0]["extraction_status"], "pdf_text")
        self.assertIn("Invoice", plan["items"][0]["name"])

    def test_undo_refuses_changed_destination(self):
        (self.source / "receipt.txt").write_text("original", encoding="utf-8")
        plan = scan(self.source, self.destination)
        batch, result = apply(plan, {plan["items"][0]["id"]}, self.db)
        target = Path(result[0]["destination"])
        target.write_text("edited", encoding="utf-8")
        undone = undo(batch, self.db)
        self.assertEqual(undone[0]["state"], "failed")
        self.assertTrue(target.exists())

    def test_recover_rolls_back_interrupted_link(self):
        (self.source / "receipt.txt").write_text("original", encoding="utf-8")
        plan = scan(self.source, self.destination)
        with patch("sift.core.os.unlink", side_effect=OSError("simulated interruption")):
            _, result = apply(plan, {plan["items"][0]["id"]}, self.db)
        self.assertEqual(result[0]["state"], "failed")
        self.assertEqual(recover(self.db)[0]["state"], "rolled_back")
        self.assertTrue((self.source / "receipt.txt").exists())
        self.assertFalse((self.destination / "Receipts" / "receipt.txt").exists())


if __name__ == "__main__":
    unittest.main()
