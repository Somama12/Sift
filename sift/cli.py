"""Command-line interface for the Sift prototype."""

from __future__ import annotations

import argparse
import json
import os
import time
from itertools import groupby
from pathlib import Path

from .core import apply, duplicates, history, recover, scan, search, undo
from .watch import dismiss, inbox_plan, watch_tick


def database_path() -> Path:
    return Path(os.environ.get("SIFT_DB", "~/Library/Application Support/Sift/sift.sqlite3")).expanduser()


def parse_mappings(values: list[str]) -> dict[str, str]:
    result = {}
    for mapping in values:
        if "=" not in mapping:
            raise ValueError("Folder mapping must be CATEGORY=FOLDER")
        category, folder = mapping.split("=", 1)
        result[category] = folder
    return result


def review_item(item: dict) -> None:
    print(f"\n[{item['confidence']}] {item['source']} -> {item['destination_folder']}/{item['name']} ({item['reason']}; extraction: {item.get('extraction_status', 'unknown')}; model: {item.get('model_status', 'not_requested')})")
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


def review_groups(items: list[dict]) -> None:
    for destination, members in groupby(sorted(items, key=lambda item: (item["destination_folder"], item["source"])), key=lambda item: item["destination_folder"]):
        group = list(members)
        selected = sum(bool(item.get("selected")) for item in group)
        print(f"\n{destination}: {len(group)} proposals, {selected} selected")
        for item in group:
            mark = "x" if item.get("selected") else " "
            print(f"  [{mark}] [{item['confidence']}] {item['source']} -> {item['name']} ({item['reason']})")
        choice = input("Group: [a]pprove all, [n]one, [i]nspect each, Enter keep: ").strip().lower()
        if choice in {"a", "approve"}:
            for item in group:
                item["selected"] = True
        elif choice in {"n", "none"}:
            for item in group:
                item["selected"] = False
        elif choice in {"i", "inspect"}:
            for item in group:
                review_item(item)
        elif choice:
            raise ValueError(f"Unknown group choice: {choice}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sift", description="Local, preview-first file organizer")
    commands = parser.add_subparsers(dest="command", required=True)
    scan_cmd = commands.add_parser("scan", help="save a proposal plan without moving files")
    scan_cmd.add_argument("source", type=Path)
    scan_cmd.add_argument("--to", dest="destination", type=Path, required=True)
    scan_cmd.add_argument("--output", type=Path, required=True)
    scan_cmd.add_argument("--map", action="append", default=[], metavar="CATEGORY=FOLDER", help="use a folder inside the destination root for a category")
    scan_cmd.add_argument("--ollama", action="store_true", help="ask local Ollama qwen3:4b-instruct for low-confidence text files")
    watch_cmd = commands.add_parser("watch", help="queue suggestions for stable new files; never move them")
    watch_cmd.add_argument("source", type=Path)
    watch_cmd.add_argument("--to", dest="destination", type=Path, required=True)
    watch_cmd.add_argument("--interval", type=float, default=3)
    watch_cmd.add_argument("--stable-seconds", type=float, default=5)
    watch_cmd.add_argument("--once", action="store_true", help="observe one interval and exit")
    watch_cmd.add_argument("--map", action="append", default=[], metavar="CATEGORY=FOLDER")
    watch_cmd.add_argument("--ollama", action="store_true")
    inbox_cmd = commands.add_parser("inbox", help="export queued suggestions as a reviewable plan")
    inbox_cmd.add_argument("source", type=Path)
    inbox_cmd.add_argument("--output", type=Path, required=True)
    dismiss_cmd = commands.add_parser("dismiss", help="remove a suggestion from the inbox")
    dismiss_cmd.add_argument("id")
    duplicates_cmd = commands.add_parser("duplicates", help="report exact duplicate files without changing them")
    duplicates_cmd.add_argument("source", type=Path)
    search_cmd = commands.add_parser("search", help="search filenames and supported document text locally")
    search_cmd.add_argument("source", type=Path)
    search_cmd.add_argument("query")
    search_cmd.add_argument("--limit", type=int, default=20)
    show_cmd = commands.add_parser("show", help="review a saved plan")
    show_cmd.add_argument("plan", type=Path)
    review_cmd = commands.add_parser("review", help="select and edit proposals in a saved plan")
    review_cmd.add_argument("plan", type=Path)
    review_cmd.add_argument("--groups", action="store_true", help="approve or reject proposals by destination folder")
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
            plan = scan(args.source, args.destination, parse_mappings(args.map), model="qwen3:4b-instruct" if args.ollama else None)
            args.output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
            print(f"Saved {len(plan['items'])} proposals to {args.output}. No files moved.")
        elif args.command == "watch":
            if args.interval <= 0:
                raise ValueError("Watch interval must be positive")
            while True:
                result = watch_tick(args.source, args.destination, database_path(), stable_seconds=args.stable_seconds, folder_map=parse_mappings(args.map), model="qwen3:4b-instruct" if args.ollama else None)
                print(f"Queued now: {result['queued_now']}; pending: {result['pending']}; inbox: {result['inbox']}. No files moved.", flush=True)
                if args.once:
                    break
                time.sleep(args.interval)
        elif args.command == "inbox":
            plan = inbox_plan(args.source, database_path())
            args.output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
            print(f"Saved {len(plan['items'])} suggestions to {args.output}. No files moved.")
        elif args.command == "dismiss":
            if not dismiss(args.id, database_path()):
                raise ValueError("Suggestion ID not found")
            print("Suggestion dismissed. No files moved.")
        elif args.command == "duplicates":
            groups = duplicates(args.source)
            for group in groups:
                print(json.dumps(group))
            print(f"{len(groups)} duplicate groups. No files changed.")
        elif args.command == "search":
            results = search(args.source, args.query, args.limit)
            for result in results:
                print(json.dumps(result))
            print(f"{len(results)} results. No files changed.")
        elif args.command in {"show", "review", "apply"}:
            plan = json.loads(args.plan.read_text(encoding="utf-8"))
            selected = set(args.ids.split(",")) if args.command == "apply" and args.ids else {item["id"] for item in plan["items"] if item.get("selected", False)}
            known = {item["id"] for item in plan["items"]}
            if not selected <= known:
                raise ValueError("Unknown proposal ID")
            if args.command == "review" and args.groups:
                review_groups(plan["items"])
                args.plan.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
                print(f"Saved review: {sum(item['selected'] for item in plan['items'])} selected. No files moved.")
                return 0
            for item in sorted(plan["items"], key=lambda item: (item["destination_folder"], item["source"])):
                if args.command == "review":
                    review_item(item)
                elif args.command == "show" or item["id"] in selected:
                    mark = "x" if item.get("selected") else " "
                    print(f"[{mark}] [{item['confidence']}] {item['id']}  {item['source']} -> {item['destination_folder']}/{item['name']} ({item['reason']}; extraction: {item.get('extraction_status', 'unknown')}; model: {item.get('model_status', 'not_requested')})")
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
    except KeyboardInterrupt:
        print("\nStopped watching. No files moved.")
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        parser.exit(1, f"Sift: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
