"""Command-line interface for the Sift prototype."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .core import apply, history, recover, scan, undo


def database_path() -> Path:
    return Path(os.environ.get("SIFT_DB", "~/Library/Application Support/Sift/sift.sqlite3")).expanduser()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sift", description="Local, preview-first file organizer")
    commands = parser.add_subparsers(dest="command", required=True)
    scan_cmd = commands.add_parser("scan", help="save a proposal plan without moving files")
    scan_cmd.add_argument("source", type=Path)
    scan_cmd.add_argument("--to", dest="destination", type=Path, required=True)
    scan_cmd.add_argument("--output", type=Path, required=True)
    scan_cmd.add_argument("--map", action="append", default=[], metavar="CATEGORY=FOLDER", help="use a folder inside the destination root for a category")
    show_cmd = commands.add_parser("show", help="review a saved plan")
    show_cmd.add_argument("plan", type=Path)
    review_cmd = commands.add_parser("review", help="select and edit proposals in a saved plan")
    review_cmd.add_argument("plan", type=Path)
    apply_cmd = commands.add_parser("apply", help="apply reviewed proposals")
    apply_cmd.add_argument("plan", type=Path)
    apply_cmd.add_argument("--ids", help="comma-separated proposal IDs; omit to select all")
    apply_cmd.add_argument("--yes", action="store_true", help="confirm the displayed changes")
    undo_cmd = commands.add_parser("undo", help="undo a batch or a single proposal")
    undo_cmd.add_argument("id")
    commands.add_parser("history", help="list batches")
    commands.add_parser("recover", help="reconcile interrupted moves")
    args = parser.parse_args(argv)
    try:
        if args.command == "scan":
            folder_map = {}
            for mapping in args.map:
                if "=" not in mapping:
                    raise ValueError("Folder mapping must be CATEGORY=FOLDER")
                category, folder = mapping.split("=", 1)
                folder_map[category] = folder
            plan = scan(args.source, args.destination, folder_map)
            args.output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
            print(f"Saved {len(plan['items'])} proposals to {args.output}. No files moved.")
        elif args.command in {"show", "review", "apply"}:
            plan = json.loads(args.plan.read_text(encoding="utf-8"))
            selected = set(args.ids.split(",")) if args.command == "apply" and args.ids else {item["id"] for item in plan["items"] if item.get("selected", False)}
            known = {item["id"] for item in plan["items"]}
            if not selected <= known:
                raise ValueError("Unknown proposal ID")
            for item in sorted(plan["items"], key=lambda item: (item["destination_folder"], item["source"])):
                if args.command == "review":
                    print(f"\n[{item['confidence']}] {item['source']} -> {item['destination_folder']}/{item['name']} ({item['reason']})")
                    choice = input("Approve? [y/N/e] (e = edit destination/name): ").strip().lower()
                    if choice == "e":
                        folder = input(f"Destination folder [{item['destination_folder']}]: ").strip()
                        name = input(f"Name [{item['name']}]: ").strip()
                        if folder:
                            item["destination_folder"] = folder
                        if name:
                            item["name"] = name
                        item["selected"] = True
                    else:
                        item["selected"] = choice in {"y", "yes"}
                elif args.command == "show" or item["id"] in selected:
                    mark = "x" if item.get("selected") else " "
                    print(f"[{mark}] [{item['confidence']}] {item['id']}  {item['source']} -> {item['destination_folder']}/{item['name']} ({item['reason']})")
            if args.command == "review":
                args.plan.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
                print(f"Saved review: {sum(item['selected'] for item in plan['items'])} selected. No files moved.")
                return 0
            print(f"{len(selected)} selected; no files moved yet.")
            if args.command == "apply":
                if not args.yes and input("Apply these moves? Type 'apply' to continue: ").strip() != "apply":
                    print("Cancelled.")
                    return 0
                batch, results = apply(plan, selected, database_path())
                print(f"Batch {batch}")
                for result in results:
                    print(json.dumps(result))
                return 1 if any(result["state"] == "failed" for result in results) else 0
        elif args.command == "undo":
            results = undo(args.id, database_path())
            for result in results:
                print(json.dumps(result))
            if not results:
                print("No applied moves found for that ID.")
            return 1 if any(result["state"] == "failed" for result in results) else 0
        elif args.command == "history":
            for row in history(database_path()):
                print(json.dumps(row))
        elif args.command == "recover":
            for row in recover(database_path()):
                print(json.dumps(row))
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        parser.exit(1, f"Sift: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
