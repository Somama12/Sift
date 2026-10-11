import tempfile
import unittest
import json
import importlib.util
import io
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

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

    def test_scan_reports_each_eligible_file_before_processing(self):
        first = self.source / "first.txt"
        second = self.source / "second.txt"
        first.write_text("receipt", encoding="utf-8")
        second.write_text("lease", encoding="utf-8")
        seen = []
        plan = scan(self.source, self.destination, on_progress=lambda number, path: seen.append((number, path.name)))
        self.assertEqual([number for number, _ in seen], [1, 2])
        self.assertEqual({name for _, name in seen}, {"first.txt", "second.txt"})
        self.assertEqual(len(plan["items"]), 2)
        self.assertTrue(first.exists() and second.exists())

    def test_conflicting_content_categories_go_to_review(self):
        (self.source / "scan009.txt").write_text("Invoice and residential lease", encoding="utf-8")
        item = scan(self.source, self.destination)["items"][0]
        self.assertEqual(item["category"], "Review")
        self.assertEqual(item["reason"], "conflicting category signals")
        self.assertFalse(item["selected"])

    def test_fast_scan_skips_content_extraction(self):
        (self.source / "scan009.txt").write_text("Invoice from a store", encoding="utf-8")
        item = scan(self.source, self.destination, deep=False)["items"][0]
        self.assertEqual(item["extraction_status"], "not_scanned")
        self.assertEqual(item["category"], "Review")
        self.assertFalse(item["selected"])

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

    def test_group_review_approves_one_group_and_inspects_another(self):
        (self.source / "contract.txt").write_text("Agreement", encoding="utf-8")
        (self.source / "invoice.txt").write_text("Invoice", encoding="utf-8")
        (self.source / "receipt.txt").write_text("Receipt", encoding="utf-8")
        plan_file = self.root / "plan.json"
        plan_file.write_text(json.dumps(scan(self.source, self.destination)), encoding="utf-8")
        output = io.StringIO()
        with patch("builtins.input", side_effect=["a", "i", "y", "n"]), redirect_stdout(output):
            self.assertEqual(main(["review", str(plan_file), "--groups"]), 0)
        items = {Path(item["source"]).name: item for item in json.loads(plan_file.read_text())["items"]}
        self.assertTrue(items["contract.txt"]["selected"])
        self.assertTrue(items["invoice.txt"]["selected"])
        self.assertFalse(items["receipt.txt"]["selected"])
        self.assertIn("2 proposals", output.getvalue())
        self.assertTrue((self.source / "contract.txt").exists())

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

    def test_local_model_suggestion_is_validated_and_unselected(self):
        (self.source / "scan005.txt").write_text("Meeting notes about the rental property", encoding="utf-8")
        response = MagicMock()
        response.status = 200
        response.read.return_value = json.dumps({"message": {"content": json.dumps({"category": "Contracts", "filename": "Lease Agreement.pdf"})}}).encode()
        connection = MagicMock()
        connection.getresponse.return_value = response
        with patch("sift.core.http.client.HTTPConnection", return_value=connection) as constructor:
            plan = scan(self.source, self.destination, model="qwen3:4b-instruct")
        constructor.assert_called_once_with("127.0.0.1", 11434, timeout=90)
        payload = json.loads(connection.request.call_args.kwargs["body"])
        self.assertEqual(payload["model"], "qwen3:4b-instruct")
        item = plan["items"][0]
        self.assertEqual(item["category"], "Contracts")
        self.assertEqual(item["name"], "Lease Agreement.txt")
        self.assertEqual(item["model_status"], "used")
        self.assertFalse(item["selected"])

    def test_invalid_model_category_falls_back_to_rules(self):
        (self.source / "scan005.txt").write_text("This text has no known category", encoding="utf-8")
        response = MagicMock()
        response.status = 200
        response.read.return_value = json.dumps({"message": {"content": json.dumps({"category": "../../Secrets", "filename": "bad.txt"})}}).encode()
        connection = MagicMock()
        connection.getresponse.return_value = response
        with patch("sift.core.http.client.HTTPConnection", return_value=connection):
            plan = scan(self.source, self.destination, model="qwen3:4b-instruct")
        item = plan["items"][0]
        self.assertEqual(item["category"], "Review")
        self.assertEqual(item["model_status"], "unavailable_or_invalid")

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
