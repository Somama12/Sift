"""Scanning, guarded moves, and crash-recoverable undo."""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import stat
import uuid
from datetime import datetime, timezone
from pathlib import Path

SKIP_DIRS = {".git", ".svn", "node_modules", ".venv", "venv", "__pycache__"}
PACKAGES = {".app", ".bundle", ".framework", ".photoslibrary", ".pages", ".numbers", ".key"}
TEMP = {".crdownload", ".download", ".part", ".partial", ".tmp"}
KEYWORDS = {
    "Receipts": ("receipt", "invoice"),
    "Bills": ("bill", "statement", "utility"),
    "School": ("lecture", "assignment", "homework", "syllabus"),
    "Travel": ("flight", "itinerary", "boarding", "hotel"),
    "Contracts": ("contract", "lease", "agreement"),
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def fingerprint(path: Path) -> dict:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"Not a regular file: {path}")
    return {"device": info.st_dev, "inode": info.st_ino, "size": info.st_size, "mtime_ns": info.st_mtime_ns}


def digest(path: Path) -> str:
    hashed = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hashed.update(chunk)
    return hashed.hexdigest()


def extract(path: Path) -> str:
    if path.suffix.lower() not in {".txt", ".md", ".csv"}:
        return ""
    try:
        with path.open("rb") as stream:
            return stream.read(64_000).decode("utf-8", errors="replace")
    except OSError:
        return ""


def classify(path: Path, content: str) -> tuple[str, str, str]:
    extension = path.suffix.lower()
    stem = path.stem.lower()
    if extension in {".dmg", ".pkg", ".mpkg"}:
        return "Installers", "high", "installer file type"
    if "screenshot" in stem or "screen shot" in stem:
        return "Screenshots", "high", "screenshot filename"
    for category, words in KEYWORDS.items():
        if any(re.search(r"\b" + word + r"\b", stem) for word in words):
            return category, "medium", "filename keyword"
    text = content[:5000].lower()
    for category, words in KEYWORDS.items():
        if any(re.search(r"\b" + word + r"\b", text) for word in words):
            return category, "low", "content keyword"
    return "Review", "low", "no reliable category"


def safe_name(value: str) -> str:
    value = re.sub(r"[^\w .()\-]", " ", value, flags=re.UNICODE)
    value = re.sub(r"\s+", " ", value).strip(" .-")
    return value[:100].rstrip(" .-") or "Untitled"


def propose_name(path: Path, content: str) -> str:
    stem = path.stem.replace("_", " ")
    if re.fullmatch(r"(?:scan|document|img|image|untitled)[\s()\-\d]*", stem, re.I):
        line = next((line.strip() for line in content.splitlines() if len(line.strip()) >= 5), "")
        if line:
            stem = line[:70]
    return safe_name(stem) + path.suffix.lower()


def scan(source: Path, destination_root: Path) -> dict:
    source = source.expanduser().resolve()
    destination_root = destination_root.expanduser().resolve()
    if not source.is_dir():
        raise ValueError("Source must be a directory")
    if destination_root.exists() and not destination_root.is_dir():
        raise ValueError("Destination root must be a directory")
    if not destination_root.exists() and not destination_root.parent.is_dir():
        raise ValueError("Destination parent must exist")
    items = []
    for root, dirs, files in os.walk(source, followlinks=False):
        folder = Path(root)
        if inside(folder, destination_root) or (folder / ".git").exists():
            dirs[:] = []
            continue
        dirs[:] = [name for name in dirs if not name.startswith(".") and name not in SKIP_DIRS and Path(name).suffix.lower() not in PACKAGES and not (folder / name).is_symlink() and not (folder / name / ".git").exists() and not inside(folder / name, destination_root)]
        for name in files:
            path = folder / name
            if name.startswith(".") or path.suffix.lower() in TEMP or path.is_symlink():
                continue
            try:
                before = fingerprint(path)
                content = extract(path)
                if fingerprint(path) != before:
                    continue
                category, confidence, reason = classify(path, content)
                items.append({"id": uuid.uuid4().hex, "source": str(path), "destination_folder": str(destination_root / category), "name": propose_name(path, content), "category": category, "confidence": confidence, "reason": reason, "fingerprint": before, "selected": confidence == "high"})
            except (OSError, ValueError):
                continue
    return {"version": 1, "created_at": now(), "source": str(source), "destination_root": str(destination_root), "items": sorted(items, key=lambda item: item["source"])}


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("CREATE TABLE IF NOT EXISTS batches (id TEXT PRIMARY KEY, created_at TEXT NOT NULL)")
    connection.execute("CREATE TABLE IF NOT EXISTS moves (id TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES batches(id), source TEXT NOT NULL, destination TEXT NOT NULL, sha256 TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
    connection.commit()
    return connection


def check_target(path: Path, root: Path) -> None:
    if not inside(path, root) or path == root:
        raise ValueError("Destination must be inside the selected root")
    current = path.parent
    while inside(current, root):
        if current.is_symlink():
            raise ValueError("Destination contains a symlink")
        if current == root:
            break
        current = current.parent


def validate(item: dict, plan: dict) -> tuple[Path, Path]:
    source = Path(item["source"])
    root = Path(plan["destination_root"])
    folder = Path(item["destination_folder"])
    name = item["name"]
    if not source.is_absolute() or not root.is_absolute() or not folder.is_absolute():
        raise ValueError("Plan paths must be absolute")
    if not inside(source, Path(plan["source"])):
        raise ValueError("Source is outside the scanned folder")
    if name != Path(name).name or name != safe_name(Path(name).stem) + Path(name).suffix.lower() or name.startswith("."):
        raise ValueError("Unsafe proposed name")
    check_target(folder / name, root)
    if fingerprint(source) != item["fingerprint"]:
        raise ValueError("Source changed since scan")
    return source, folder / name


def unused_target(path: Path) -> Path:
    for number in range(1, 10000):
        candidate = path if number == 1 else path.with_name(f"{path.stem} ({number}){path.suffix}")
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
    raise ValueError("Too many filename collisions")


def apply(plan: dict, selected_ids: set[str], db_path: Path) -> tuple[str, list[dict]]:
    if plan.get("version") != 1:
        raise ValueError("Unsupported plan version")
    if len({item["id"] for item in plan["items"]}) != len(plan["items"]):
        raise ValueError("Duplicate proposal IDs")
    connection = connect(db_path)
    batch_id = uuid.uuid4().hex[:12]
    connection.execute("INSERT INTO batches VALUES (?, ?)", (batch_id, now()))
    connection.commit()
    results = []
    for item in plan["items"]:
        if item["id"] not in selected_ids:
            continue
        try:
            source, target = validate(item, plan)
            target.parent.mkdir(parents=True, exist_ok=True)
            target = unused_target(target)
            if source.stat().st_dev != target.parent.stat().st_dev:
                raise ValueError("Cross-volume moves are not supported yet")
            sha = digest(source)
            if fingerprint(source) != item["fingerprint"]:
                raise ValueError("Source changed while hashing")
            with connection:
                connection.execute("INSERT INTO moves VALUES (?, ?, ?, ?, ?, 'prepared', ?, ?)", (item["id"], batch_id, str(source), str(target), sha, now(), now()))
            os.link(source, target, follow_symlinks=False)  # fails if target now exists
            os.unlink(source)
            with connection:
                connection.execute("UPDATE moves SET state='applied', updated_at=? WHERE id=?", (now(), item["id"]))
            results.append({"id": item["id"], "state": "applied", "destination": str(target)})
        except (OSError, ValueError, KeyError, sqlite3.Error) as error:
            results.append({"id": item.get("id"), "state": "failed", "error": str(error)})
    connection.close()
    return batch_id, results


def recover(db_path: Path) -> list[dict]:
    connection = connect(db_path)
    results = []
    for row in connection.execute("SELECT * FROM moves WHERE state IN ('prepared', 'undo_prepared')").fetchall():
        source, target = Path(row["source"]), Path(row["destination"])
        try:
            if row["state"] == "prepared":
                if source.exists() and target.exists() and source.samefile(target):
                    target.unlink()  # rollback a link made before source removal
                    state = "rolled_back"
                elif source.exists() and not target.exists():
                    state = "rolled_back"
                elif not source.exists() and target.is_file() and digest(target) == row["sha256"]:
                    state = "applied"
                else:
                    state = "conflict"
            else:
                if source.exists() and target.exists() and source.samefile(target):
                    source.unlink()  # rollback a link made before destination removal
                    state = "applied"
                elif not source.exists() and target.is_file() and digest(target) == row["sha256"]:
                    state = "applied"
                elif source.is_file() and not target.exists() and digest(source) == row["sha256"]:
                    state = "undone"
                else:
                    state = "conflict"
            with connection:
                connection.execute("UPDATE moves SET state=?, updated_at=? WHERE id=?", (state, now(), row["id"]))
            results.append({"id": row["id"], "state": state})
        except OSError as error:
            results.append({"id": row["id"], "state": "failed", "error": str(error)})
    connection.close()
    return results


def undo(identifier: str, db_path: Path) -> list[dict]:
    recover(db_path)
    connection = connect(db_path)
    rows = connection.execute("SELECT * FROM moves WHERE (batch_id=? OR id=?) AND state='applied' ORDER BY created_at DESC", (identifier, identifier)).fetchall()
    results = []
    for row in rows:
        source, target = Path(row["source"]), Path(row["destination"])
        try:
            if source.exists() or source.is_symlink() or not target.is_file() or target.is_symlink():
                raise ValueError("Original path occupied or moved file missing")
            if digest(target) != row["sha256"]:
                raise ValueError("Moved file changed; refusing undo")
            source.parent.mkdir(parents=True, exist_ok=True)
            with connection:
                connection.execute("UPDATE moves SET state='undo_prepared', updated_at=? WHERE id=?", (now(), row["id"]))
            os.link(target, source, follow_symlinks=False)
            os.unlink(target)
            with connection:
                connection.execute("UPDATE moves SET state='undone', updated_at=? WHERE id=?", (now(), row["id"]))
            results.append({"id": row["id"], "state": "undone"})
        except (OSError, ValueError) as error:
            results.append({"id": row["id"], "state": "failed", "error": str(error)})
    connection.close()
    return results


def history(db_path: Path) -> list[dict]:
    connection = connect(db_path)
    rows = connection.execute("SELECT b.id, b.created_at, COUNT(m.id) AS total, SUM(CASE WHEN m.state='applied' THEN 1 ELSE 0 END) AS applied FROM batches b LEFT JOIN moves m ON m.batch_id=b.id GROUP BY b.id ORDER BY b.created_at DESC").fetchall()
    connection.close()
    return [dict(row) for row in rows]
