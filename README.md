# Sift

Sift is a local, preview-first file organizer for macOS. This repository contains a Python command-line prototype for **catch-up scans**, **guarded moves with undo**, and an **Autopilot suggestion inbox**. The [product and technical plan](SIFT_PRODUCT_TECHNICAL_PLAN.md) describes the later menu bar app, OCR, and richer local AI.

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

## Autopilot suggestion mode

```sh
python3 -m sift watch ~/Downloads --to ~/Documents --interval 3 --stable-seconds 5
```

The first watch pass records existing files as a baseline. Later passes track newly arrived files, ignore temporary download extensions, and queue a suggestion only after a file's size and modification time remain unchanged for the stable interval. The watcher stores its state in the local Sift database, so files that arrive while it is stopped are found when it restarts. Press Ctrl-C to stop it. It **never moves files**.

In another terminal, export and review the inbox:

```sh
python3 -m sift inbox ~/Downloads --output /tmp/sift-inbox.plan.json
python3 -m sift review /tmp/sift-inbox.plan.json
python3 -m sift apply /tmp/sift-inbox.plan.json
```

All Autopilot suggestions begin unselected, including installers and screenshots. Use `sift dismiss PROPOSAL_ID` to remove an unwanted suggestion; changing the file later makes it eligible again. `sift watch ... --once` makes one observation and exits, which is useful for testing. `--map` and `--ollama` work with `watch` as they do with `scan`.

## Exact duplicates

```sh
python3 -m sift duplicates ~/Downloads
```

Sift groups files with the same byte size and SHA-256 hash. It reads and reports them locally, without changing or deleting anything. Files that change while being hashed are omitted. Near-duplicate detection is a later feature.

## Local keyword search

```sh
python3 -m sift search ~/Documents "lease agreement"
```

Search reads supported files on demand and ranks filename matches above content matches. It stores no search index or extracted text. It is keyword search rather than semantic or conversational search; broad folders can take time to scan. PDF content is available when the optional PDF extra is installed.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

## Current limits

The classifier is intentionally conservative and rule-based by default. It skips hidden files, symlinks, app bundles, nested Git projects, and temporary download suffixes. OCR, encrypted indexing, a menu bar interface, and FSEvents-based background integration remain planned features. The current watcher must be run from a terminal.

### Optional local model

Install [Ollama](https://ollama.com/download/mac), pull `qwen3:4b-instruct`, and ensure its local server is running. Add `--ollama` to `sift scan` to ask the model about low-confidence files with extracted text. Sift calls only `127.0.0.1:11434`; it cannot be pointed at a remote host. The model can return only an allowed category and a proposed filename. Sift validates both, preserves the original file extension, and keeps every model proposal unselected for review. If the model is unavailable or returns an invalid answer, rule-based classification remains in the plan. The plan's `model_status` field shows whether the model was used. Model quality and speed have not yet been benchmarked on this Mac.
