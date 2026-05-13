#!/usr/bin/env python3
"""Export SkillGraph slices as Markdown or Mermaid."""

from __future__ import annotations

import argparse
import re
import sqlite3
from pathlib import Path

from graph_audit import LIVE_STATUSES, ensure_audit_schema
from praxis.paths import default_root


DEFAULT_ROOT = default_root()
DEFAULT_DB = DEFAULT_ROOT / "kg" / "skill_graph.sqlite"
DEFAULT_EXPORT = DEFAULT_ROOT / "exports" / "skill_graph_overview.md"


def connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def safe_mermaid_id(node_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", node_id)
    if cleaned and cleaned[0].isdigit():
        cleaned = f"n_{cleaned}"
    return cleaned or "node"


def mermaid_label(text: str) -> str:
    return text.replace('"', "'")


def live_edge_clause(include_inactive: bool) -> str:
    if include_inactive:
        return ""
    statuses = ", ".join(repr(status) for status in LIVE_STATUSES)
    return (
        f"WHERE edge_status IN ({statuses}) "
        f"AND source_status IN ({statuses}) "
        f"AND target_status IN ({statuses}) "
        f"AND (evidence_status IS NULL OR evidence_status IN ({statuses}))"
    )


def export_markdown(connection: sqlite3.Connection, out_path: Path, limit_edges: int, include_inactive: bool) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = ["# SkillGraph Overview", ""]

    lines.append("## Counts")
    for table in (
        "nodes",
        "edges",
        "evidence",
        "aliases",
        "source_registry",
        "source_captures",
        "graph_update_proposals",
        "watchlist_runs",
        "research_hits",
    ):
        row = connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
        lines.append(f"- {table}: {row['count']}")

    lines.extend(["", "## Node Types"])
    for row in connection.execute("SELECT type, COUNT(*) AS count FROM nodes GROUP BY type ORDER BY count DESC, type"):
        lines.append(f"- {row['type']}: {row['count']}")

    lines.extend(["", "## Relations"])
    for row in connection.execute("SELECT relation, COUNT(*) AS count FROM edges GROUP BY relation ORDER BY count DESC, relation"):
        lines.append(f"- {row['relation']}: {row['count']}")

    lines.extend(["", "## High-Signal Edges"])
    rows = connection.execute(
        """
        SELECT *
        FROM edge_view
        {where}
        ORDER BY
          CASE confidence WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
          relation,
          source_name,
          target_name
        LIMIT ?
        """.format(where=live_edge_clause(include_inactive)),
        (limit_edges,),
    ).fetchall()
    for row in rows:
        lines.append(f"- `{row['source_id']}` --{row['relation']}--> `{row['target_id']}`")
        if row["summary"]:
            lines.append(f"  {row['summary']}")
        if row["evidence_title"]:
            lines.append(f"  Evidence: {row['evidence_title']}")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def export_mermaid(connection: sqlite3.Connection, out_path: Path, relation: str | None, limit_edges: int, include_inactive: bool) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    params: list[object] = []
    clauses = []
    if relation:
        clauses.append("relation = ?")
        params.append(relation)
    if not include_inactive:
        statuses = ", ".join(repr(status) for status in LIVE_STATUSES)
        clauses.append(f"edge_status IN ({statuses})")
        clauses.append(f"source_status IN ({statuses})")
        clauses.append(f"target_status IN ({statuses})")
        clauses.append(f"(evidence_status IS NULL OR evidence_status IN ({statuses}))")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit_edges)
    rows = connection.execute(
        f"""
        SELECT *
        FROM edge_view
        {where}
        ORDER BY relation, source_name, target_name
        LIMIT ?
        """,
        params,
    ).fetchall()

    seen_nodes: dict[str, str] = {}
    lines = ["flowchart LR"]
    for row in rows:
        for node_id, name, node_type in (
            (row["source_id"], row["source_name"], row["source_type"]),
            (row["target_id"], row["target_name"], row["target_type"]),
        ):
            if node_id not in seen_nodes:
                mermaid_id = safe_mermaid_id(node_id)
                seen_nodes[node_id] = mermaid_id
                lines.append(f'  {mermaid_id}["{mermaid_label(name)}<br/>{node_type}"]')
        lines.append(
            f"  {seen_nodes[row['source_id']]} -- {row['relation']} --> {seen_nodes[row['target_id']]}"
        )

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Path to SkillGraph SQLite database")
    parser.add_argument("--out", default=str(DEFAULT_EXPORT), help="Output path")
    parser.add_argument("--format", choices=["markdown", "mermaid"], default="markdown")
    parser.add_argument("--relation", help="Mermaid only: restrict to one relation")
    parser.add_argument("--limit-edges", type=int, default=80)
    parser.add_argument("--include-inactive", action="store_true", help="Include deprecated/reverted graph objects.")
    args = parser.parse_args()

    with connect(Path(args.db)) as connection:
        ensure_audit_schema(connection)
        if args.format == "markdown":
            export_markdown(connection, Path(args.out), args.limit_edges, args.include_inactive)
        else:
            export_mermaid(connection, Path(args.out), args.relation, args.limit_edges, args.include_inactive)

    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
