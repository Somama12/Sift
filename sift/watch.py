"""Persistent suggestion-only watcher for newly arrived files."""

from __future__ import annotations

import json
import time
from pathlib import Path

from .core import connect, destination_folders, eligible_files, fingerprint, now, proposal_for_file


def _tables(connection) -> None:
    connection.execute("CREATE TABLE IF NOT EXISTS watch_roots (source TEXT PRIMARY KEY, destination_root TEXT NOT NULL, initialized_at TEXT NOT NULL)")
    connection.execute("CREATE TABLE IF NOT EXISTS watch_files (source TEXT NOT NULL, path TEXT NOT NULL, fingerprint TEXT NOT NULL, state TEXT NOT NULL, stable_since REAL NOT NULL, updated_at REAL NOT NULL, proposal TEXT, PRIMARY KEY (source, path), FOREIGN KEY (source) REFERENCES watch_roots(source))")
    connection.commit()


def watch_tick(source: Path, destination_root: Path, db_path: Path, *, stable_seconds: float = 5, observed_at: float | None = None, folder_map: dict[str, str] | None = None, model: str | None = None) -> dict:
    """Observe one interval and queue proposals only after files stay unchanged."""
    if stable_seconds < 0:
        raise ValueError("Stable interval must be nonnegative")
    source = source.expanduser().resolve()
    destination_root = destination_root.expanduser().resolve()
    if not source.is_dir():
        raise ValueError("Watch source must be a directory")
    mapped, existing = destination_folders(destination_root, folder_map)
    moment = time.time() if observed_at is None else observed_at
    connection = connect(db_path)
    _tables(connection)
    row = connection.execute("SELECT destination_root FROM watch_roots WHERE source=?", (str(source),)).fetchone()
    initializing = row is None
    if row and row["destination_root"] != str(destination_root):
        connection.close()
        raise ValueError("This watch source already has a different destination root")
    if initializing:
        connection.execute("INSERT INTO watch_roots VALUES (?, ?, ?)", (str(source), str(destination_root), now()))
        connection.commit()
    seen = set()
    queued = 0
    for path in eligible_files(source, destination_root):
        seen.add(str(path))
        try:
            current = fingerprint(path)
        except (OSError, ValueError):
            continue
        encoded = json.dumps(current, sort_keys=True)
        saved = connection.execute("SELECT fingerprint, state, stable_since FROM watch_files WHERE source=? AND path=?", (str(source), str(path))).fetchone()
        if saved is None:
            state = "baseline" if initializing else "pending"
            with connection:
                connection.execute("INSERT INTO watch_files VALUES (?, ?, ?, ?, ?, ?, NULL)", (str(source), str(path), encoded, state, moment, moment))
            continue
        if saved["fingerprint"] != encoded:
            with connection:
                connection.execute("UPDATE watch_files SET fingerprint=?, state='pending', stable_since=?, updated_at=?, proposal=NULL WHERE source=? AND path=?", (encoded, moment, moment, str(source), str(path)))
            continue
        if saved["state"] == "pending" and moment - saved["stable_since"] >= stable_seconds:
            proposal = proposal_for_file(path, destination_root, mapped, existing, model)
            if proposal is None or proposal["fingerprint"] != current:
                continue
            proposal["selected"] = False  # Autopilot starts in suggestion mode for every category.
            with connection:
                connection.execute("UPDATE watch_files SET state='queued', proposal=?, updated_at=? WHERE source=? AND path=?", (json.dumps(proposal), moment, str(source), str(path)))
            queued += 1
    for saved in connection.execute("SELECT path FROM watch_files WHERE source=?", (str(source),)).fetchall():
        if saved["path"] not in seen:
            with connection:
                connection.execute("DELETE FROM watch_files WHERE source=? AND path=?", (str(source), saved["path"]))
    pending = connection.execute("SELECT COUNT(*) FROM watch_files WHERE source=? AND state='pending'", (str(source),)).fetchone()[0]
    inbox = connection.execute("SELECT COUNT(*) FROM watch_files WHERE source=? AND state='queued'", (str(source),)).fetchone()[0]
    connection.close()
    return {"initialized": initializing, "queued_now": queued, "pending": pending, "inbox": inbox}


def inbox_plan(source: Path, db_path: Path) -> dict:
    source = source.expanduser().resolve()
    connection = connect(db_path)
    _tables(connection)
    root = connection.execute("SELECT destination_root FROM watch_roots WHERE source=?", (str(source),)).fetchone()
    if root is None:
        connection.close()
        raise ValueError("This folder has not been watched yet")
    items = []
    for row in connection.execute("SELECT path, proposal FROM watch_files WHERE source=? AND state='queued' ORDER BY path", (str(source),)).fetchall():
        try:
            proposal = json.loads(row["proposal"])
            if fingerprint(Path(row["path"])) == proposal["fingerprint"]:
                items.append(proposal)
        except (OSError, ValueError, TypeError, KeyError):
            continue
    connection.close()
    return {"version": 1, "created_at": now(), "source": str(source), "destination_root": root["destination_root"], "items": items}


def dismiss(proposal_id: str, db_path: Path) -> bool:
    connection = connect(db_path)
    _tables(connection)
    for row in connection.execute("SELECT source, path, proposal FROM watch_files WHERE state='queued'").fetchall():
        try:
            if json.loads(row["proposal"])["id"] == proposal_id:
                with connection:
                    connection.execute("UPDATE watch_files SET state='dismissed', proposal=NULL WHERE source=? AND path=?", (row["source"], row["path"]))
                connection.close()
                return True
        except (ValueError, TypeError, KeyError):
            continue
    connection.close()
    return False
