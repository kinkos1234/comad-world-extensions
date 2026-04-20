"""Shared helpers for comad-memory scripts."""
from __future__ import annotations
import hashlib
import os
import pathlib
import sqlite3
import sys

HOME = pathlib.Path(os.path.expanduser("~"))
DB_PATH = HOME / ".claude" / ".comad" / "memory" / "facts.sqlite"
LOG_PATH = HOME / ".claude" / ".comad" / "memory" / "sync.log"
MEMORY_ROOT_GLOB = HOME / ".claude" / "projects"


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS facts USING fts5(
            fact_id UNINDEXED,
            project UNINDEXED,
            file_path UNINDEXED,
            type,
            name,
            description,
            body,
            mtime UNINDEXED,
            tokenize='unicode61 remove_diacritics 2'
        );
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """
    )
    conn.commit()


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Parse minimal YAML frontmatter. Returns ({} , body) if absent."""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text
    raw = text[4:end]
    body = text[end + 5 :]
    fm: dict[str, str] = {}
    current_key: str | None = None
    for line in raw.splitlines():
        if not line.strip():
            continue
        if line.startswith(" ") and current_key:
            fm[current_key] = (fm.get(current_key, "") + " " + line.strip()).strip()
            continue
        if ":" in line:
            k, _, v = line.partition(":")
            key = k.strip()
            val = v.strip().strip('"').strip("'")
            fm[key] = val
            current_key = key
    return fm, body


def fact_id_for(path: pathlib.Path) -> str:
    return hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:16]


def project_slug_of(path: pathlib.Path) -> str:
    # .../.claude/projects/{slug}/memory/foo.md
    parts = path.parts
    try:
        idx = parts.index("projects")
        return parts[idx + 1]
    except (ValueError, IndexError):
        return "unknown"


def iter_memory_files() -> list[pathlib.Path]:
    if not MEMORY_ROOT_GLOB.exists():
        return []
    out = []
    for mem_dir in MEMORY_ROOT_GLOB.glob("*/memory"):
        for md in mem_dir.glob("*.md"):
            out.append(md)
    return sorted(out)


def log(msg: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a") as f:
        f.write(msg + "\n")
    print(msg, file=sys.stderr)
