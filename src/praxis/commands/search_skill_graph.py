#!/usr/bin/env python3
"""Search and traverse the local SkillGraph."""

from __future__ import annotations

import argparse
import sqlite3
from collections import deque
from pathlib import Path

from praxis.paths import default_root


DEFAULT_DB = default_root() / "kg" / "skill_graph.sqlite"


def connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def resolve_node(connection: sqlite3.Connection, value: str) -> sqlite3.Row | None:
    row = connection.execute("SELECT * FROM nodes WHERE id = ?", (value,)).fetchone()
    if row:
        return row
    row = connection.execute("SELECT n.* FROM aliases a JOIN nodes n ON n.id = a.node_id WHERE a.alias = ?", (value,)).fetchone()
    if row:
        return row
    like = f"%{value}%"
    return connection.execute(
        """
        SELECT DISTINCT n.*
        FROM nodes n
        LEFT JOIN aliases a ON a.node_id = n.id
        WHERE n.name LIKE ? OR n.summary LIKE ? OR a.alias LIKE ?
        ORDER BY
          CASE WHEN n.name = ? THEN 0 WHEN n.name LIKE ? THEN 1 ELSE 2 END,
          n.type,
          n.name
        LIMIT 1
        """,
        (like, like, like, value, like),
    ).fetchone()


def node_tags(connection: sqlite3.Connection, node_id: str) -> str:
    row = connection.execute(
        """
        SELECT group_concat(t.name, ', ') AS tags
        FROM node_tags nt
        JOIN tags t ON t.id = nt.tag_id
        WHERE nt.node_id = ?
        """,
        (node_id,),
    ).fetchone()
    return row["tags"] or ""


def search_nodes(connection: sqlite3.Connection, query: str, node_type: str | None, limit: int) -> list[sqlite3.Row]:
    like = f"%{query}%"
    params: list[object] = [like, like, like, like]
    type_clause = ""
    if node_type:
        type_clause = "AND n.type = ?"
        params.append(node_type)
    params.append(limit)
    return connection.execute(
        f"""
        SELECT DISTINCT n.*
        FROM nodes n
        LEFT JOIN aliases a ON a.node_id = n.id
        LEFT JOIN node_tags nt ON nt.node_id = n.id
        LEFT JOIN tags t ON t.id = nt.tag_id
        WHERE (n.id LIKE ? OR n.name LIKE ? OR n.summary LIKE ? OR a.alias LIKE ?)
        {type_clause}
        ORDER BY n.type, n.name
        LIMIT ?
        """,
        params,
    ).fetchall()


def incident_edges(
    connection: sqlite3.Connection,
    node_id: str,
    direction: str,
    relation: str | None,
    limit: int,
) -> list[sqlite3.Row]:
    clauses = []
    params: list[object] = []
    if direction in ("out", "both"):
        clauses.append("source_id = ?")
        params.append(node_id)
    if direction in ("in", "both"):
        clauses.append("target_id = ?")
        params.append(node_id)

    relation_clause = ""
    if relation:
        relation_clause = "AND relation = ?"
        params.append(relation)
    params.append(limit)

    return connection.execute(
        f"""
        SELECT *
        FROM edge_view
        WHERE ({' OR '.join(clauses)})
        {relation_clause}
        ORDER BY relation, target_name, source_name
        LIMIT ?
        """,
        params,
    ).fetchall()


def all_adjacent(connection: sqlite3.Connection, node_id: str) -> list[tuple[str, sqlite3.Row]]:
    rows = connection.execute(
        "SELECT * FROM edge_view WHERE source_id = ? OR target_id = ?",
        (node_id, node_id),
    ).fetchall()
    out: list[tuple[str, sqlite3.Row]] = []
    for row in rows:
        neighbor = row["target_id"] if row["source_id"] == node_id else row["source_id"]
        out.append((neighbor, row))
    return out


def find_path(connection: sqlite3.Connection, start_id: str, end_id: str, max_depth: int) -> list[sqlite3.Row] | None:
    queue = deque([(start_id, [])])
    visited = {start_id}

    while queue:
        current, path = queue.popleft()
        if len(path) >= max_depth:
            continue
        for neighbor, edge in all_adjacent(connection, current):
            if neighbor in visited:
                continue
            new_path = path + [edge]
            if neighbor == end_id:
                return new_path
            visited.add(neighbor)
            queue.append((neighbor, new_path))
    return None


def print_nodes(connection: sqlite3.Connection, rows: list[sqlite3.Row]) -> None:
    print("# Nodes\n")
    if not rows:
        print("No matching nodes.\n")
        return
    for row in rows:
        print(f"## {row['name']}")
        print(f"- id: `{row['id']}`")
        print(f"- type: {row['type']}")
        print(f"- confidence: {row['confidence']}")
        tags = node_tags(connection, row["id"])
        if tags:
            print(f"- tags: {tags}")
        if row["source_ref"]:
            print(f"- source: {row['source_ref']}")
        print(f"- summary: {row['summary']}")
        print()


def print_edges(rows: list[sqlite3.Row], focus_id: str | None = None) -> None:
    print("# Edges\n")
    if not rows:
        print("No matching edges.\n")
        return
    for row in rows:
        print(f"## {row['source_name']} --{row['relation']}--> {row['target_name']}")
        print(f"- source: `{row['source_id']}`")
        print(f"- target: `{row['target_id']}`")
        print(f"- confidence: {row['confidence']}")
        if row["summary"]:
            print(f"- summary: {row['summary']}")
        if row["evidence_title"]:
            evidence = row["evidence_title"]
            locator = row["evidence_locator"]
            if locator:
                evidence = f"{evidence} ({locator})"
            print(f"- evidence: {evidence}")
        if focus_id:
            other = row["target_id"] if row["source_id"] == focus_id else row["source_id"]
            print(f"- neighbor: `{other}`")
        print()


def print_stats(connection: sqlite3.Connection) -> None:
    print("# SkillGraph Stats\n")
    for table in (
        "nodes",
        "edges",
        "evidence",
        "aliases",
        "tags",
        "node_tags",
        "source_registry",
        "source_captures",
        "graph_update_proposals",
        "refresh_queue",
        "watchlist_runs",
        "research_hits",
    ):
        row = connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
        print(f"- {table}: {row['count']}")
    print("\n## Node Types\n")
    for row in connection.execute("SELECT type, COUNT(*) AS count FROM nodes GROUP BY type ORDER BY count DESC, type"):
        print(f"- {row['type']}: {row['count']}")
    print("\n## Relations\n")
    for row in connection.execute("SELECT relation, COUNT(*) AS count FROM edges GROUP BY relation ORDER BY count DESC, relation"):
        print(f"- {row['relation']}: {row['count']}")


def cmd_search(args: argparse.Namespace) -> int:
    with connect(Path(args.db)) as connection:
        print_nodes(connection, search_nodes(connection, args.query, args.type, args.limit))
    return 0


def cmd_neighbors(args: argparse.Namespace) -> int:
    with connect(Path(args.db)) as connection:
        node = resolve_node(connection, args.node)
        if not node:
            print(f"Node not found: {args.node}")
            return 1
        print(f"# Neighbors For {node['name']}\n")
        print(f"- id: `{node['id']}`")
        print(f"- type: {node['type']}\n")
        rows = incident_edges(connection, node["id"], args.direction, args.relation, args.limit)
        print_edges(rows, focus_id=node["id"])
    return 0


def cmd_path(args: argparse.Namespace) -> int:
    with connect(Path(args.db)) as connection:
        start = resolve_node(connection, args.start)
        end = resolve_node(connection, args.end)
        if not start:
            print(f"Start node not found: {args.start}")
            return 1
        if not end:
            print(f"End node not found: {args.end}")
            return 1
        path = find_path(connection, start["id"], end["id"], args.max_depth)
        print(f"# Path: {start['name']} -> {end['name']}\n")
        if not path:
            print("No path found.")
            return 2
        current = start["id"]
        for idx, edge in enumerate(path, 1):
            if edge["source_id"] == current:
                print(f"{idx}. {edge['source_name']} --{edge['relation']}--> {edge['target_name']}")
                current = edge["target_id"]
            else:
                print(f"{idx}. {edge['target_name']} <--{edge['relation']}-- {edge['source_name']}")
                current = edge["source_id"]
            if edge["summary"]:
                print(f"   {edge['summary']}")
            if edge["evidence_title"]:
                print(f"   evidence: {edge['evidence_title']}")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    with connect(Path(args.db)) as connection:
        print_stats(connection)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Path to SkillGraph SQLite database")
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("search", help="Search nodes by text")
    search_parser.add_argument("query")
    search_parser.add_argument("--type", help="Restrict by node type")
    search_parser.add_argument("--limit", type=int, default=12)
    search_parser.set_defaults(func=cmd_search)

    neighbors_parser = subparsers.add_parser("neighbors", help="Show edges touching a node")
    neighbors_parser.add_argument("node", help="Node id, alias, or search text")
    neighbors_parser.add_argument("--direction", choices=["in", "out", "both"], default="both")
    neighbors_parser.add_argument("--relation")
    neighbors_parser.add_argument("--limit", type=int, default=30)
    neighbors_parser.set_defaults(func=cmd_neighbors)

    path_parser = subparsers.add_parser("path", help="Find a short undirected path between nodes")
    path_parser.add_argument("start")
    path_parser.add_argument("end")
    path_parser.add_argument("--max-depth", type=int, default=4)
    path_parser.set_defaults(func=cmd_path)

    stats_parser = subparsers.add_parser("stats", help="Show graph counts")
    stats_parser.set_defaults(func=cmd_stats)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
