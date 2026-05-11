#!/usr/bin/env python3
"""Export Praxis database content into skill/reference Markdown."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="Praxis root")
    parser.add_argument("--skill", default=str(DEFAULT_SKILL), help="skill folder to update with generated references")
    args = parser.parse_args()

    root = Path(args.root)
    skill = Path(args.skill)
    db_path = root / "db" / "praxis.sqlite"
    out_dir = root / "exports"
    skill_refs = skill / "references"

    with connect(db_path) as connection:
        export_top_sources(connection, out_dir)
        export_patterns(connection, out_dir, skill_refs)
        export_failure_modes(connection, out_dir, skill_refs)
        export_benchmarks(connection, out_dir, skill_refs)
        export_agent_practices(connection, out_dir, skill_refs)
        export_skill_design(connection, out_dir, skill_refs)
        export_architecture_ref(connection, skill_refs)

    print(f"Exported Markdown to {out_dir}")
    print(f"Updated skill references in {skill_refs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
