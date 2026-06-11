#!/usr/bin/env python3
"""Promote a ranked watchlist hit into the SkillGraph research capture store."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

from research_common import (
    DEFAULT_ROOT,
    connect,
    credibility_score,
    infer_source_type,
    read_source,
    register_capture,
    register_source,
    sha256_text,
    slug,
    summarize_text,
    utc_now,
    write_json,
)
from praxis.paths import kg_dir, research_dir


def load_metadata(row: sqlite3.Row) -> dict[str, Any]:
    try:
        return json.loads(row["metadata_json"] or "{}")
    except json.JSONDecodeError:
        return {}


def list_hits(connection: sqlite3.Connection, *, watchlist: str, status: str, limit: int) -> list[sqlite3.Row]:
    clauses = []
    params: list[object] = []
    if watchlist:
        clauses.append("watchlist_name = ?")
        params.append(watchlist)
    if status:
        clauses.append("status = ?")
        params.append(status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    return connection.execute(
        f"""
        SELECT *
        FROM research_hits
        {where}
        ORDER BY score DESC, created_at DESC
        LIMIT ?
        """,
        params,
    ).fetchall()


def resolve_hit(connection: sqlite3.Connection, value: str) -> sqlite3.Row:
    row = connection.execute("SELECT * FROM research_hits WHERE id = ?", (value,)).fetchone()
    if row:
        return row
    like = f"%{value}%"
    row = connection.execute(
        """
        SELECT *
        FROM research_hits
        WHERE title LIKE ? OR url LIKE ? OR canonical_ref LIKE ?
        ORDER BY score DESC, created_at DESC
        LIMIT 1
        """,
        (like, like, like),
    ).fetchone()
    if row:
        return row
    raise SystemExit(f"No research hit matched: {value}")


def capture_url_for(row: sqlite3.Row, metadata: dict[str, Any]) -> str:
    canonical = row["canonical_ref"]
    external = metadata.get("external_ids")
    if isinstance(external, dict) and external.get("ArXiv"):
        return f"https://arxiv.org/abs/{external['ArXiv']}"
    if canonical.startswith("arxiv:"):
        return f"https://arxiv.org/abs/{canonical.split(':', 1)[1]}"
    open_access_pdf = metadata.get("open_access_pdf")
    if isinstance(open_access_pdf, dict) and open_access_pdf.get("url"):
        return str(open_access_pdf["url"])
    if row["url"] and "semanticscholar.org" not in row["url"]:
        return row["url"]
    if isinstance(external, dict) and external.get("DOI"):
        return f"https://doi.org/{external['DOI']}"
    if canonical.startswith("s2:"):
        return f"https://www.semanticscholar.org/paper/{canonical.split(':', 1)[1]}"
    if canonical.startswith(("http://", "https://")):
        return canonical
    if row["url"]:
        return row["url"]
    raise SystemExit(f"Research hit has no capturable URL: {row['id']}")


def source_type_for(row: sqlite3.Row, capture_url: str, text: str) -> str:
    if row["source_type"] in {"arxiv", "semantic_scholar"}:
        return "paper"
    if row["source_type"] == "blog":
        return "web"
    return infer_source_type(capture_url, text)


def print_hits(rows: list[sqlite3.Row]) -> None:
    if not rows:
        print("No matching research hits.")
        return
    for row in rows:
        print(f"[{row['score']:.1f}] {row['title']}")
        print(f"  id: {row['id']}")
        print(f"  status: {row['status']}")
        print(f"  url: {row['url'] or row['canonical_ref']}")
        if row["rank_reasons"]:
            print(f"  reasons: {row['rank_reasons']}")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("hit", nargs="?", help="Research hit id, title substring, URL substring, or canonical ref")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="Praxis root")
    parser.add_argument("--list", action="store_true", help="List ranked hits instead of capturing one")
    parser.add_argument("--watchlist", default="", help="Filter --list by watchlist name")
    parser.add_argument("--status", default="new", help="Filter --list by hit status. Use empty string for all statuses.")
    parser.add_argument("--limit", type=int, default=15)
    parser.add_argument("--source-id", help="Override captured source id")
    parser.add_argument("--freshness-window-days", type=int, default=30)
    parser.add_argument("--notes", default="")
    args = parser.parse_args()

    root = Path(args.root)
    db_path = kg_dir(root) / "skill_graph.sqlite"

    with connect(db_path) as connection:
        if args.list:
            print_hits(list_hits(connection, watchlist=args.watchlist, status=args.status, limit=args.limit))
            return 0
        if not args.hit:
            raise SystemExit("Provide a research hit id, or use --list.")
        row = resolve_hit(connection, args.hit)
        metadata = load_metadata(row)
        capture_url = capture_url_for(row, metadata)

    text, capture_metadata = read_source(capture_url)
    if not text.strip() and row["abstract"]:
        text = "\n\n".join(
            [
                f"# {title}",
                "",
                "## Watchlist Abstract",
                "",
                row["abstract"],
            ]
        )
        capture_metadata = {**capture_metadata, "fallback": "watchlist_abstract"}
    content_hash = sha256_text(text)
    source_type = source_type_for(row, capture_url, text)
    title = row["title"]
    source_id = args.source_id or f"src:{slug(title)}"
    capture_id = f"cap:{slug(source_id)}:{content_hash[:12]}"
    credibility = credibility_score(source_type, capture_metadata)

    captures_root = research_dir(root) / "captures"
    source_dir = captures_root / slug(source_id)
    source_dir.mkdir(parents=True, exist_ok=True)
    raw_path = source_dir / f"{slug(capture_id)}.raw.txt"
    summary_path = source_dir / f"{slug(capture_id)}.summary.md"
    metadata_path = source_dir / f"{slug(capture_id)}.metadata.json"

    raw_path.write_text(text, encoding="utf-8")
    summary = summarize_text(text)
    merged_metadata = {
        "hit_id": row["id"],
        "run_id": row["run_id"],
        "watchlist_name": row["watchlist_name"],
        "source_type_seen": row["source_type"],
        "canonical_ref": row["canonical_ref"],
        "published_at": row["published_at"],
        "authors": row["authors"],
        "venue": row["venue"],
        "score": row["score"],
        "rank_reasons": row["rank_reasons"],
        "hit_metadata": metadata,
        "capture_metadata": capture_metadata,
    }
    summary_path.write_text(
        "\n".join(
            [
                f"# {title}",
                "",
                f"- captured_from_hit: `{row['id']}`",
                f"- source: {capture_url}",
                f"- source_id: `{source_id}`",
                f"- capture_id: `{capture_id}`",
                f"- captured_at: {utc_now()}",
                f"- source_type: {source_type}",
                f"- content_hash: `{content_hash}`",
                f"- score: {row['score']}",
                f"- rank_reasons: {row['rank_reasons']}",
                "",
                "## Watchlist Abstract",
                "",
                row["abstract"] or "No abstract captured in watchlist hit.",
                "",
                "## Extractive Summary",
                "",
                summary,
                "",
            ]
        ),
        encoding="utf-8",
    )
    write_json(
        metadata_path,
        {
            "source": capture_url,
            "source_id": source_id,
            "capture_id": capture_id,
            "title": title,
            "source_type": source_type,
            "content_hash": content_hash,
            "credibility_score": credibility,
            "freshness_window_days": args.freshness_window_days,
            "raw_path": str(raw_path),
            "summary_path": str(summary_path),
            "metadata": merged_metadata,
        },
    )

    with connect(db_path) as connection:
        register_source(
            connection,
            source_id=source_id,
            url=capture_url,
            title=title,
            source_type=source_type,
            canonical_ref=row["canonical_ref"] or capture_url,
            freshness_window_days=args.freshness_window_days,
            credibility=credibility,
            notes=args.notes or f"Promoted from watchlist hit {row['id']}",
            metadata=merged_metadata,
        )
        register_capture(
            connection,
            capture_id=capture_id,
            source_id=source_id,
            content_hash=content_hash,
            raw_path=str(raw_path),
            summary_path=str(summary_path),
            metadata={"metadata_path": str(metadata_path), **merged_metadata},
        )
        updated_metadata = {**metadata, "captured_as": capture_id, "captured_at": utc_now()}
        connection.execute(
            """
            UPDATE research_hits
            SET status = 'captured', metadata_json = ?
            WHERE id = ?
            """,
            (json.dumps(updated_metadata, sort_keys=True), row["id"]),
        )

    print(f"Captured {title}")
    print(f"hit_id: {row['id']}")
    print(f"source_id: {source_id}")
    print(f"capture_id: {capture_id}")
    print(f"raw: {raw_path}")
    print(f"summary: {summary_path}")
    print()
    print("Next:")
    print(f"  python3.12 \"{root / 'scripts' / 'propose_graph_update.py'}\" {capture_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
