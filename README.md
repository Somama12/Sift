# Sift

Sift is a local, preview-first file organizer for macOS. This repository currently contains a Python command-line prototype for the first two safety features: **scan and review proposals**, then **apply and undo guarded moves**. The [product and technical plan](SIFT_PRODUCT_TECHNICAL_PLAN.md) describes the later menu bar app, OCR, local AI, and Autopilot.

## Requirements

Python 3.10 or later. No third-party packages or network service are required. This prototype reads filenames and UTF-8 text in `.txt`, `.md`, and `.csv` files. It does not yet understand PDFs or image contents, so those files may go to `Review`.

## Try it on a test folder

```sh
mkdir -p /tmp/sift-demo/Downloads /tmp/sift-demo/Organized
printf 'Invoice from Example Company\n' > /tmp/sift-demo/Downloads/scan001.txt
python3 -m sift scan /tmp/sift-demo/Downloads --to /tmp/sift-demo/Organized --output /tmp/sift-demo/plan.json
python3 -m sift show /tmp/sift-demo/plan.json
SIFT_DB=/tmp/sift-demo/sift.sqlite3 python3 -m sift apply /tmp/sift-demo/plan.json
SIFT_DB=/tmp/sift-demo/sift.sqlite3 python3 -m sift history
SIFT_DB=/tmp/sift-demo/sift.sqlite3 python3 -m sift undo BATCH_ID
```

`scan` and `show` never move files. `apply` prints the exact selected moves and requires typing `apply`; `--yes` is available for scripted use after plan review. Use `--ids ID1,ID2` to apply only chosen proposals. Proposal destination folders and names can be edited in the JSON plan before applying. Sift checks that paths and source fingerprints remain valid.

Sift never deletes files. It only supports moves within one filesystem in this prototype; cross-volume moves fail safely. It resolves name collisions with `(2)`, `(3)`, etc. The default history database is `~/Library/Application Support/Sift/sift.sqlite3`; set `SIFT_DB` to change it. `recover` reconciles interrupted moves, and `undo` does this automatically. An unchanged moved file can be undone if its original path is free. If a file changed or a path is occupied, undo leaves it untouched and reports the conflict.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

## Current limits

The classifier is intentionally conservative and rule-based. This release does **not** claim AI document understanding. It skips hidden files, symlinks, app bundles, nested Git projects, and temporary download suffixes. OCR, PDF extraction, local model inference, encrypted indexing, a menu bar interface, and background watching remain planned features.
