#!/usr/bin/env python3
"""Incremental sync of ~/.claude/projects/*/memory/*.md into FTS5 index.

Usage:
    python3 sync.py              # incremental (mtime-based)
    python3 sync.py --full       # drop and rebuild
"""
from __future__ import annotations
import datetime
import sys

from lib import (
    connect,
    ensure_schema,
    fact_id_for,
    iter_memory_files,
    log,
    parse_frontmatter,
    project_slug_of,
)


def main() -> int:
    full = "--full" in sys.argv
    conn = connect()
    ensure_schema(conn)

    if full:
        conn.execute("DELETE FROM facts")

    files = iter_memory_files()
    if not files:
        log("sync: no memory files found")
        return 0

    existing = {
        row["fact_id"]: row["mtime"]
        for row in conn.execute("SELECT fact_id, mtime FROM facts").fetchall()
    }

    inserted = 0
    updated = 0
    skipped = 0
    failed = 0

    for path in files:
        try:
            # Skip MEMORY.md — it's the index, not a fact
            if path.name == "MEMORY.md":
                skipped += 1
                continue

            fid = fact_id_for(path)
            mtime = str(int(path.stat().st_mtime))
            if not full and existing.get(fid) == mtime:
                skipped += 1
                continue

            text = path.read_text(encoding="utf-8", errors="replace")
            if not text.strip():
                skipped += 1
                continue

            fm, body = parse_frontmatter(text)
            name = fm.get("name", path.stem)
            desc = fm.get("description", "")
            mtype = fm.get("type", "")
            if not mtype:
                # Fallback: infer from filename prefix — feedback_/project_/reference_/user_
                prefix = path.stem.split("_", 1)[0]
                if prefix in {"feedback", "project", "reference", "user"}:
                    mtype = prefix

            # Skip if still untyped — likely not a curated memory (session logs etc.)
            if not mtype:
                skipped += 1
                continue

            proj = project_slug_of(path)

            if fid in existing:
                conn.execute(
                    "DELETE FROM facts WHERE fact_id = ?",
                    (fid,),
                )
                updated += 1
            else:
                inserted += 1

            conn.execute(
                "INSERT INTO facts(fact_id, project, file_path, type, name, description, body, mtime) VALUES (?,?,?,?,?,?,?,?)",
                (fid, proj, str(path), mtype, name, desc, body, mtime),
            )
        except Exception as e:
            log(f"sync: FAILED {path}: {e}")
            failed += 1

    # Orphan purge: DB fact_ids whose source file no longer exists or is now
    # excluded (MEMORY.md / empty / untyped). Keeps incremental sync in parity
    # with --full rebuild.
    live_ids = {fact_id_for(p) for p in files if p.name != "MEMORY.md"}
    current_db_ids = {
        row["fact_id"] for row in conn.execute("SELECT fact_id FROM facts").fetchall()
    }
    orphan_ids = current_db_ids - live_ids
    if orphan_ids:
        conn.executemany(
            "DELETE FROM facts WHERE fact_id = ?", [(x,) for x in orphan_ids]
        )
    purged = len(orphan_ids)

    conn.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES ('last_sync', ?)",
        (datetime.datetime.now(datetime.timezone.utc).isoformat(),),
    )
    conn.commit()

    total_rows = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
    conn.close()

    log(
        f"sync: ts={datetime.datetime.now().isoformat(timespec='seconds')} "
        f"files={len(files)} inserted={inserted} updated={updated} "
        f"skipped={skipped} purged={purged} failed={failed} "
        f"total_facts={total_rows}"
    )
    print(
        f"synced: {inserted} new / {updated} updated / {skipped} unchanged / "
        f"{purged} purged / {failed} failed (total facts: {total_rows})"
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
