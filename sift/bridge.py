"""JSON request/response bridge for the native macOS front end."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .core import apply, history, scan, search, undo
from .doctor import diagnose


def database_path() -> Path:
    return Path(os.environ.get("SIFT_DB", "~/Library/Application Support/Sift/sift.sqlite3")).expanduser()


def handle(request: dict) -> dict:
    command = request.get("command")
    if command == "scan":
        source = Path(request["source"])
        destination = Path(request["destination"])
        model = "qwen3:4b-instruct" if request.get("ollama") is True else None
        return {"plan": scan(source, destination, request.get("folder_map"), model=model)}
    if command == "apply":
        plan = request["plan"]
        selected = set(request["selected_ids"])
        batch, results = apply(plan, selected, database_path())
        return {"batch_id": batch, "results": results}
    if command == "undo":
        return {"results": undo(request["id"], database_path())}
    if command == "history":
        return {"batches": history(database_path())}
    if command == "search":
        return {"results": search(Path(request["source"]), request["query"], int(request.get("limit", 20)))}
    if command == "doctor":
        return {"capabilities": diagnose()}
    raise ValueError(f"Unknown bridge command: {command}")


def main() -> int:
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("Request must be an object")
        response = {"ok": True, **handle(request)}
    except (OSError, ValueError, KeyError, TypeError) as error:
        response = {"ok": False, "error": str(error)}
    json.dump(response, sys.stdout)
    sys.stdout.write("\n")
    return 0 if response["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
