#!/usr/bin/env python3
"""List or mark research sources whose freshness window has elapsed."""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

from research_common import DEFAULT_ROOT, connect, utc_now


def parse_time(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def is_stale(last_checked_at: str | None, window_days: int, now: dt.datetime) -> bool:
    checked = parse_time(last_checked_at)
    if checked is None:
        return True
    return checked + dt.timedelta(days=window_days) <= now


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="Praxis root")
    parser.add_argument("--topic", help="Filter sources by title/type/notes/canonical ref containing topic text")
    parser.add_argument("--mark-stale", action="store_true", help="Update stale active sources to stale_pending_refresh")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    db_path = Path(args.root) / "kg" / "skill_graph.sqlite"
    now = dt.datetime.now(dt.UTC)
    params: list[object] = []
    topic_clause = ""
    if args.topic:
        like = f"%{args.topic}%"
        topic_clause = """
        AND (
          title LIKE ? OR source_type LIKE ? OR notes LIKE ? OR canonical_ref LIKE ?
        )
        """
        params.extend([like, like, like, like])
    params.append(args.limit)

    with connect(db_path) as connection:
        rows = connection.execute(
            f"""
            SELECT *
            FROM source_registry
            WHERE status IN ('active', 'stale_pending_refresh')
            {topic_clause}
            ORDER BY last_checked_at IS NOT NULL, last_checked_at, title
            LIMIT ?
            """,
            params,
        ).fetchall()
        stale = [
            row for row in rows
            if is_stale(row["last_checked_at"], int(row["freshness_window_days"]), now)
        ]

        print("# Stale Sources\n")
        if not stale:
            print("No stale sources found.")
            return 0

        for row in stale:
            print(f"## {row['title']}")
            print(f"- id: `{row['id']}`")
            print(f"- type: {row['source_type']}")
            print(f"- ref: {row['canonical_ref'] or row['url']}")
            print(f"- last_checked_at: {row['last_checked_at'] or 'never'}")
            print(f"- freshness_window_days: {row['freshness_window_days']}")
            print(f"- status: {row['status']}")
            print()

        if args.mark_stale:
            ids = [row["id"] for row in stale if row["status"] == "active"]
            for source_id in ids:
                connection.execute(
                    """
                    UPDATE source_registry
                    SET status = 'stale_pending_refresh',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (source_id,),
                )
            print(f"Marked stale: {len(ids)} at {utc_now()}")

        print("Refresh one with:")
        print('  python3.12 "scripts/research_source.py" "<source url/path>"')
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
