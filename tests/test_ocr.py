import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sift.core import scan


class OCRTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "Downloads"
        self.destination = self.root / "Organized"
        self.source.mkdir()
        self.destination.mkdir()
        self.fixtures = Path(__file__).parent / "fixtures"

    def test_image_without_ocr_keeps_file_for_review(self):
        (self.source / "scan001.png").write_bytes((self.fixtures / "lease_scan.png").read_bytes())
        with patch("sift.core.shutil.which", return_value=None):
            item = scan(self.source, self.destination)["items"][0]
        self.assertEqual(item["extraction_status"], "ocr_unavailable")
        self.assertEqual(item["category"], "Review")
        self.assertFalse(item["selected"])

    @unittest.skipUnless(shutil.which("tesseract"), "Tesseract is not installed")
    def test_image_ocr_classifies_scan(self):
        (self.source / "scan001.png").write_bytes((self.fixtures / "lease_scan.png").read_bytes())
        item = scan(self.source, self.destination)["items"][0]
        self.assertEqual(item["extraction_status"], "image_ocr")
        self.assertEqual(item["category"], "Contracts")
        self.assertIn("LEASE", item["name"])
        self.assertFalse(item["selected"])

    @unittest.skipUnless(shutil.which("tesseract") and shutil.which("pdftoppm") and importlib.util.find_spec("pypdf"), "PDF OCR tools are not installed")
    def test_scanned_pdf_ocr_classifies_scan(self):
        (self.source / "scan001.pdf").write_bytes((self.fixtures / "lease_scan.pdf").read_bytes())
        item = scan(self.source, self.destination)["items"][0]
        self.assertEqual(item["extraction_status"], "pdf_ocr")
        self.assertEqual(item["category"], "Contracts")
        self.assertIn("LEASE", item["name"])
        self.assertFalse(item["selected"])


if __name__ == "__main__":
    unittest.main()
