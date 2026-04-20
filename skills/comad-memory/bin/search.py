#!/usr/bin/env python3
"""FTS5 search over memory index.

Usage:
    search.py <query> [--type=feedback] [--project=<slug>] [--limit=10]
"""
from __future__ import annotations
import sys

from lib import connect, ensure_schema


def parse_args(argv: list[str]) -> tuple[str, dict[str, str]]:
    if len(argv) < 2:
        print("usage: search.py <query> [--type=T] [--project=P] [--limit=N]", file=sys.stderr)
        sys.exit(2)
    opts: dict[str, str] = {}
    positional: list[str] = []
    for tok in argv[1:]:
        if tok.startswith("--") and "=" in tok:
            k, _, v = tok[2:].partition("=")
            opts[k] = v
        else:
            positional.append(tok)
    query = " ".join(positional).strip()
    if not query:
        print("error: empty query", file=sys.stderr)
        sys.exit(2)
    return query, opts


FTS_OPERATORS = (" AND ", " OR ", " NOT ", '"', "*")


def fts_escape(query: str) -> str:
    """Wrap query as an FTS5 phrase unless it already contains operators.

    FTS5 chokes on bare apostrophes, colons, and many other tokens. Wrapping
    in double quotes makes the whole thing a phrase; internal ``"`` must be
    doubled up per FTS5 syntax.
    """
    if any(op in query for op in FTS_OPERATORS):
        return query  # user knows FTS syntax, pass through
    escaped = query.replace('"', '""')
    return f'"{escaped}"'


def main() -> int:
    query, opts = parse_args(sys.argv)
    limit = int(opts.get("limit", "10"))

    conn = connect()
    ensure_schema(conn)

    where = ["facts MATCH ?"]
    params: list[object] = [fts_escape(query)]
    if "type" in opts:
        where.append("type = ?")
        params.append(opts["type"])
    if "project" in opts:
        where.append("project = ?")
        params.append(opts["project"])
    params.append(limit)

    sql = f"""
        SELECT fact_id, project, file_path, type, name, description,
               snippet(facts, 6, '[', ']', '…', 12) AS snip,
               bm25(facts) AS rank
          FROM facts
         WHERE {' AND '.join(where)}
      ORDER BY rank
         LIMIT ?
    """
    rows = conn.execute(sql, params).fetchall()
    if not rows:
        print("(no matches)")
        return 0

    for row in rows:
        print(
            f"[{row['type'] or '-'}] {row['name']}  ({row['fact_id']})\n"
            f"  proj: {row['project']}\n"
            f"  file: {row['file_path']}\n"
            f"  desc: {row['description']}\n"
            f"  hit : {row['snip']}\n"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
