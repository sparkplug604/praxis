#!/usr/bin/env python3
"""Export Praxis database content into skill/reference Markdown."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from conflict_ledger import open_conflict_count, open_conflict_rows
from praxis.paths import default_root


DEFAULT_ROOT = default_root()
DEFAULT_SKILL = DEFAULT_ROOT / "skills" / "praxis-memory"


def connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def export_top_sources(connection: sqlite3.Connection, out_dir: Path) -> None:
    rows = connection.execute(
        """
        SELECT *
        FROM sources
        ORDER BY agent_relevance DESC, engineering_relevance DESC, evidence_strength DESC, year DESC
        LIMIT 25
        """
    ).fetchall()
    lines = [
        "# Top Agent Research Sources",
        "",
        "Ranked by agent relevance, engineering relevance, evidence strength, and recency.",
        "",
    ]
    for index, row in enumerate(rows, start=1):
        lines.extend(
            [
                f"## {index}. {row['title']} ({row['year'] or 'n.d.'})",
                f"- id: `{row['id']}`",
                f"- type: {row['source_type']}",
                f"- focus: {row['primary_focus']}",
                f"- url: {row['url']}",
                f"- repo: {row['repo_url'] or 'n/a'}",
                f"- scores: agent={row['agent_relevance']} engineering={row['engineering_relevance']} evidence={row['evidence_strength']} reproducibility={row['reproducibility']} safety={row['safety_relevance']}",
                f"- summary: {row['summary']}",
                f"- critical notes: {row['critical_notes']}",
                "",
            ]
        )
    write(out_dir / "top_25_agent_research_sources.md", "\n".join(lines))


def export_patterns(connection: sqlite3.Connection, out_dir: Path, skill_refs: Path) -> None:
    rows = connection.execute(
        """
        SELECT *
        FROM patterns
        ORDER BY category, name
        """
    ).fetchall()
    lines = ["# Agent Patterns Catalog", ""]
    current = None
    for row in rows:
        if row["category"] != current:
            current = row["category"]
            lines.extend([f"## {current.title()}", ""])
        lines.extend(
            [
                f"### {row['name']}",
                f"- id: `{row['id']}`",
                f"- maturity: {row['maturity']}",
                f"- description: {row['description']}",
                f"- Agent rule: {row['agent_rule']}",
                f"- Runtime rule: {row['runtime_rule'] or 'n/a'}",
                "",
            ]
        )
    text = "\n".join(lines)
    write(out_dir / "agent_patterns_catalog.md", text)
    write(skill_refs / "agent_patterns_catalog.md", text)


def export_failure_modes(connection: sqlite3.Connection, out_dir: Path, skill_refs: Path) -> None:
    rows = connection.execute(
        """
        SELECT *
        FROM failure_modes
        ORDER BY severity DESC, name
        """
    ).fetchall()
    lines = ["# Agent Failure Modes", ""]
    for row in rows:
        lines.extend(
            [
                f"## {row['name']}",
                f"- id: `{row['id']}`",
                f"- severity: {row['severity']}",
                f"- description: {row['description']}",
                f"- detection: {row['detection']}",
                f"- mitigation: {row['mitigation']}",
                "",
            ]
        )
    text = "\n".join(lines)
    write(out_dir / "agent_failure_modes.md", text)
    write(skill_refs / "agent_failure_modes.md", text)


def export_benchmarks(connection: sqlite3.Connection, out_dir: Path, skill_refs: Path) -> None:
    rows = connection.execute("SELECT * FROM benchmarks ORDER BY name").fetchall()
    lines = ["# Benchmark Map", ""]
    for row in rows:
        lines.extend(
            [
                f"## {row['name']}",
                f"- id: `{row['id']}`",
                f"- domain: {row['domain']}",
                f"- url: {row['url']}",
                f"- measures: {row['measures']}",
                f"- strengths: {row['strengths']}",
                f"- limitations: {row['limitations']}",
                f"- Agent use: {row['agent_use']}",
                "",
            ]
        )
    text = "\n".join(lines)
    write(out_dir / "benchmark_map.md", text)
    write(skill_refs / "evaluation_benchmarks.md", text)


def export_agent_practices(connection: sqlite3.Connection, out_dir: Path, skill_refs: Path) -> None:
    rows = connection.execute("SELECT * FROM agent_practices ORDER BY name").fetchall()
    lines = ["# Agent Operating Principles", ""]
    for row in rows:
        lines.extend(
            [
                f"## {row['name']}",
                f"- trigger: {row['trigger']}",
                f"- practice: {row['practice']}",
                f"- anti-pattern: {row['anti_pattern']}",
                f"- evidence basis: {row['evidence_basis']}",
                "",
            ]
        )
    text = "\n".join(lines)
    write(out_dir / "agent_operating_principles.md", text)
    write(skill_refs / "agent_operating_principles.md", text)


def export_skill_design(connection: sqlite3.Connection, out_dir: Path, skill_refs: Path) -> None:
    rows = connection.execute(
        """
        SELECT *
        FROM patterns
        WHERE category = 'skills'
        ORDER BY name
        """
    ).fetchall()
    lines = [
        "# Skill Design Lessons",
        "",
        "Skills are durable procedural memory: concise triggers, lightweight workflow, deeper references, deterministic scripts, and validation.",
        "",
    ]
    for row in rows:
        lines.extend(
            [
                f"## {row['name']}",
                f"- description: {row['description']}",
                f"- Agent rule: {row['agent_rule']}",
                f"- Runtime rule: {row['runtime_rule'] or 'n/a'}",
                "",
            ]
        )
    text = "\n".join(lines)
    write(out_dir / "skill_design_lessons.md", text)
    write(skill_refs / "skill_design_lessons.md", text)


def export_architecture_ref(connection: sqlite3.Connection, skill_refs: Path) -> None:
    rows = connection.execute(
        """
        SELECT *
        FROM patterns
        WHERE category IN ('architecture', 'planning', 'memory', 'tool-use', 'multi-agent', 'safety', 'observability')
        ORDER BY category, name
        """
    ).fetchall()
    lines = [
        "# Agent Architecture Reference",
        "",
        "Use this when designing or operating autonomous/coding-agent workflows.",
        "",
    ]
    current = None
    for row in rows:
        if row["category"] != current:
            current = row["category"]
            lines.extend([f"## {current.title()}", ""])
        lines.extend(
            [
                f"### {row['name']}",
                f"- description: {row['description']}",
                f"- Agent rule: {row['agent_rule']}",
                "",
            ]
        )
    write(skill_refs / "agent_architecture.md", "\n".join(lines))


def export_conflict_notes(kg_db: Path, skill_refs: Path) -> int:
    if not kg_db.exists():
        return 0
    with sqlite3.connect(kg_db) as connection:
        connection.row_factory = sqlite3.Row
        rows = open_conflict_rows(connection, limit=50)
    if not rows:
        return 0
    lines = [
        "# Open Praxis Conflict Warnings",
        "",
        "These records indicate unresolved knowledge conflicts or dedupe candidates in the SkillGraph.",
        "",
    ]
    for row in rows:
        lines.append(f"- `{row['id']}` ({row['conflict_type']}, {row['severity']}): {row['summary']}")
    write(skill_refs / "open_conflict_warnings.md", "\n".join(lines) + "\n")
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="Praxis root")
    parser.add_argument("--skill", default=str(DEFAULT_SKILL), help="skill folder to update with generated references")
    parser.add_argument("--kg-db", default="", help="SkillGraph DB used for conflict safety checks.")
    parser.add_argument("--fail-on-open-conflicts", action="store_true", help="Refuse skill export when unresolved conflicts exist.")
    parser.add_argument("--include-conflict-notes", action="store_true", help="Write open conflict warnings into skill references.")
    args = parser.parse_args()

    root = Path(args.root)
    skill = Path(args.skill)
    db_path = root / "db" / "praxis.sqlite"
    kg_db = Path(args.kg_db) if args.kg_db else root / "kg" / "skill_graph.sqlite"
    out_dir = root / "exports"
    skill_refs = skill / "references"

    conflict_count = 0
    if kg_db.exists():
        with sqlite3.connect(kg_db) as connection:
            connection.row_factory = sqlite3.Row
            conflict_count = open_conflict_count(connection)
    if conflict_count and args.fail_on_open_conflicts:
        print(f"Refusing skill export because {conflict_count} unresolved conflict(s) exist.")
        print("Run `praxis conflicts list` to inspect them, or export without --fail-on-open-conflicts.")
        return 2

    with connect(db_path) as connection:
        export_top_sources(connection, out_dir)
        export_patterns(connection, out_dir, skill_refs)
        export_failure_modes(connection, out_dir, skill_refs)
        export_benchmarks(connection, out_dir, skill_refs)
        export_agent_practices(connection, out_dir, skill_refs)
        export_skill_design(connection, out_dir, skill_refs)
        export_architecture_ref(connection, skill_refs)

    if args.include_conflict_notes:
        written = export_conflict_notes(kg_db, skill_refs)
        if written:
            print(f"Included {written} open conflict warning(s) in skill references.")
    elif conflict_count:
        print(f"warning: {conflict_count} unresolved conflict(s) exist.")

    print(f"Exported Markdown to {out_dir}")
    print(f"Updated skill references in {skill_refs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
