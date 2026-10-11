# Sift

Sift is a local, preview-first file organizer for macOS. This repository currently contains a Python command-line prototype for the first two safety features: **scan and review proposals**, then **apply and undo guarded moves**. The [product and technical plan](SIFT_PRODUCT_TECHNICAL_PLAN.md) describes the later menu bar app, OCR, local AI, and Autopilot.

## Requirements

Python 3.10 or later. The core commands require no third-party packages or network service. Sift reads UTF-8 text in `.txt`, `.md`, and `.csv` files. For text-based PDFs, install the optional PDF extra in a virtual environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[pdf]'
```

Then use `.venv/bin/python -m sift` in the commands below. PDF extraction reads at most the first 10 pages and 64,000 characters from PDFs smaller than 20 MB. The plan records an `extraction_status` for each file. Scanned/image-only and encrypted PDFs are not yet understood and usually go to `Review`.

## Try it on a test folder

```sh
mkdir -p /tmp/sift-demo/Downloads /tmp/sift-demo/Organized
printf 'Invoice from Example Company\n' > /tmp/sift-demo/Downloads/scan001.txt
python3 -m sift scan /tmp/sift-demo/Downloads --to /tmp/sift-demo/Organized --output /tmp/sift-demo/plan.json
python3 -m sift show /tmp/sift-demo/plan.json
python3 -m sift review /tmp/sift-demo/plan.json
SIFT_DB=/tmp/sift-demo/sift.sqlite3 python3 -m sift apply /tmp/sift-demo/plan.json
SIFT_DB=/tmp/sift-demo/sift.sqlite3 python3 -m sift history
SIFT_DB=/tmp/sift-demo/sift.sqlite3 python3 -m sift undo BATCH_ID
```

`scan`, `show`, and `review` never move files. High-confidence proposals start selected; medium and low confidence proposals start unselected. `review` lets you approve, reject, or edit each proposal. `apply` prints the selected moves and requires typing `apply`; `--yes` is available for scripted use after plan review. Use `--ids ID1,ID2` to apply only chosen proposals. Sift checks that edited paths and source fingerprints remain valid.

Sift uses an existing top-level folder when its name matches a category, ignoring case. To use your own structure, add mappings when scanning, such as `--map Receipts=Finance/Invoices --map School=Classes`. Mapped folders must remain inside the chosen destination root.

Sift never deletes files. It only supports moves within one filesystem in this prototype; cross-volume moves fail safely. It resolves name collisions with `(2)`, `(3)`, etc. The default history database is `~/Library/Application Support/Sift/sift.sqlite3`; set `SIFT_DB` to change it. `recover` reconciles interrupted moves, and `undo` does this automatically. An unchanged moved file can be undone if its original path is free. If a file changed or a path is occupied, undo leaves it untouched and reports the conflict.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

## Current limits

The classifier is intentionally conservative and rule-based. This release does **not** claim AI document understanding. It skips hidden files, symlinks, app bundles, nested Git projects, and temporary download suffixes. OCR, local model inference, encrypted indexing, a menu bar interface, and background watching remain planned features. The planned prototype model runtime is Ollama with `qwen3:4b-instruct` for ambiguous files, subject to local quality and performance tests; it is not installed or used by this version.
