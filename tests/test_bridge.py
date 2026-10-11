import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class BridgeTests(unittest.TestCase):
    def test_scan_apply_and_undo_are_json_operations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Downloads"
            destination = root / "Organized"
            source.mkdir()
            destination.mkdir()
            file = source / "receipt.txt"
            file.write_text("A receipt", encoding="utf-8")
            environment = dict(os.environ, SIFT_DB=str(root / "sift.sqlite3"))

            def call(request):
                process = subprocess.run([sys.executable, "-m", "sift.bridge"], input=json.dumps(request), text=True, capture_output=True, env=environment, check=False)
                self.assertEqual(process.returncode, 0, process.stderr or process.stdout)
                return json.loads(process.stdout)

            scanned = call({"command": "scan", "source": str(source), "destination": str(destination)})
            self.assertTrue(scanned["ok"])
            plan = scanned["plan"]
            self.assertEqual(len(plan["items"]), 1)
            proposal_id = plan["items"][0]["id"]
            applied = call({"command": "apply", "plan": plan, "selected_ids": [proposal_id]})
            self.assertEqual(applied["results"][0]["state"], "applied")
            self.assertFalse(file.exists())
            undone = call({"command": "undo", "id": applied["batch_id"]})
            self.assertEqual(undone["results"][0]["state"], "undone")
            self.assertTrue(file.exists())


if __name__ == "__main__":
    unittest.main()
