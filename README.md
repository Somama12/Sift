# Sift

Sift is a local, preview-first file organizer for macOS. This repository contains a native menu bar review app and a Python engine for **catch-up scans**, **guarded moves with undo**, and an **Autopilot suggestion inbox**. The [product and technical plan](SIFT_PRODUCT_TECHNICAL_PLAN.md) describes the longer-term product.

## Native Mac app

On an Apple Silicon Mac with macOS 13 or later, install the Python environment described below, then run `mac/build-app.sh` and open `build/Sift.app`. The menu bar item reopens the review window. The window has folder pickers, grouped proposals, per-file names and destinations, apply confirmation, local search, and batch undo. It calls the same guarded move engine as the CLI through a local JSON process bridge.

For a bundle with its own Python engine and PDF libraries, install PyInstaller into `.venv` and run `mac/build-release.sh`. The result is `dist/Sift-macOS-arm64.zip`. This local alpha build is ad-hoc signed; an Apple Developer signing identity and notarization are still needed for ordinary public distribution. Optional OCR needs Tesseract installed on the Mac. Optional model suggestions need Ollama and the local model installed and running. The bundled PDF renderer removes the Poppler requirement for scanned PDF OCR.

## Requirements

Python 3.10 or later. The core commands require no third-party packages or network service. Sift reads UTF-8 text in `.txt`, `.md`, and `.csv` files. For text-based PDFs, install the optional PDF extra in a virtual environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[pdf]'
```

Then use `.venv/bin/python -m sift` in the commands below. PDF text extraction reads at most the first 10 pages and 64,000 characters from PDFs smaller than 20 MB. For local OCR of `.png`, `.jpg`, `.jpeg`, `.tif`, `.tiff`, `.bmp`, and `.webp` images, install Tesseract (`brew install tesseract`). OCR of image-only PDFs also needs the PDF extra above; its embedded renderer works without systemwide Poppler. Poppler's `pdftoppm` remains an optional alternative. It renders at most the first two pages at 150 DPI, capped at 2000 pixels. OCR runs locally, has a 30 second limit per process, and supports English in this prototype. Files with unavailable OCR, unreadable images, or encrypted PDFs remain in the plan for review. The plan records an `extraction_status` for each file.

Run `.venv/bin/sift doctor` to check which optional features are ready. It checks the local Ollama server without sending any file content.

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

During a scan, Sift prints the number and path of each file it starts processing. This is useful when OCR or a cold local model takes time; the final JSON plan is written only after the scan finishes.

For a large plan, use `python3 -m sift review /tmp/sift-demo/plan.json --groups`. Sift shows each destination group and its proposals, then lets you approve the group, deselect it, inspect files individually, or keep its current selections. Run ordinary `review` afterward to change individual selections or destinations.

Sift uses an existing top-level folder when its name matches a category, ignoring case. To use your own structure, add mappings when scanning, such as `--map Receipts=Finance/Invoices --map School=Classes`. Mapped folders must remain inside the chosen destination root.

Sift never deletes files. It only supports moves within one filesystem in this prototype; cross-volume moves fail safely. It resolves name collisions with `(2)`, `(3)`, etc. The default history database is `~/Library/Application Support/Sift/sift.sqlite3`; set `SIFT_DB` to change it. `recover` reconciles interrupted moves, and `undo` does this automatically. An unchanged moved file can be undone if its original path is free. If a file changed or a path is occupied, undo leaves it untouched and reports the conflict.

When you edit a proposed destination or name and apply it, Sift remembers that choice by the file's SHA-256 hash and size in the local history database. If identical content appears again, it suggests the saved choice but leaves it unselected for review. Other files do not inherit that correction.

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

## Local search

```sh
python3 -m sift search ~/Documents "lease agreement"
```

Search reads supported files on demand, requires all descriptive words to match, and ranks filename matches above content matches. You can filter by extension and modification year, for example `"lease agreement ext:pdf year:2025"` or `"invoice last year"`. It stores no search index or extracted text. Broad folders can take time to scan. PDF content is available when the optional PDF extra is installed.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

## Current limits

The classifier is intentionally conservative and rule-based by default. Conflicting category signals go to Review. It skips hidden files, symlinks, app bundles, nested Git projects, and temporary download suffixes. OCR is optional and currently limited to English and a few PDF pages. Encrypted indexing and FSEvents-based background integration remain planned features. The current watcher must be run from a terminal.

### Optional local model

Install [Ollama](https://ollama.com/download/mac), run `ollama pull qwen3:4b-instruct`, and ensure its local server is running. Add `--ollama` to `sift scan` to ask the model about low-confidence files with extracted text. Sift calls only `127.0.0.1:11434`; it cannot be pointed at a remote host. The model can return only an allowed category and a proposed filename. Sift validates both, preserves the original file extension, and keeps every model proposal unselected for review. If the model is unavailable or returns an invalid answer, rule-based classification remains in the plan. The plan's `model_status` field shows whether the model was used. On an 8 GB Apple Silicon Mac, a cold load of this model took about 47 seconds in our test; Sift allows up to 90 seconds per model request. Later requests are faster while Ollama keeps the model loaded. Model classification quality has not yet been benchmarked.
