#!/usr/bin/env python3
"""Return the source file path + body for a given fact_id.

Usage:
    trace.py <fact_id>
"""
from __future__ import annotations
import pathlib
import sys

from lib import connect, ensure_schema


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: trace.py <fact_id>", file=sys.stderr)
        return 2
    fid = sys.argv[1]
    conn = connect()
    ensure_schema(conn)
    row = conn.execute(
        "SELECT fact_id, project, file_path, type, name, description, body FROM facts WHERE fact_id = ?",
        (fid,),
    ).fetchone()
    if not row:
        print(f"(fact_id {fid} not found — try `sync` first)", file=sys.stderr)
        return 1

    print(f"fact_id  : {row['fact_id']}")
    print(f"project  : {row['project']}")
    print(f"file     : {row['file_path']}")
    print(f"type     : {row['type']}")
    print(f"name     : {row['name']}")
    print(f"desc     : {row['description']}")
    print(f"--- body ---")
    p = pathlib.Path(row["file_path"])
    if p.exists():
        print(p.read_text(encoding="utf-8", errors="replace"))
    else:
        print(row["body"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
