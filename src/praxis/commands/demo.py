#!/usr/bin/env python3
"""Run small end-to-end demos for Praxis modules."""

from __future__ import annotations

import argparse
import shutil
from importlib import resources
from pathlib import Path

from praxis.cli import main as praxis_main
from praxis.paths import default_root, research_dir


MODULES = {
    "core": "Ingest a bundled Stack Overflow survey aggregate, index it, and search it with explanations.",
    "reach": "Create one fixture GTM client, produce evidence, and build a context pack.",
    "agency": "Create two fixture clients and run one workflow across both.",
    "all": "Run the Core, Reach, and Agency demos.",
}

CORE_DEMO_DATA = ("demo_data", "stackoverflow_developer_survey")
CORE_DEMO_SOURCE_ID = "src:stackoverflow-dev-survey-ai-tooling-mini"


def run_step(root: Path, label: str, args: list[str]) -> int:
    print(f"\n== {label} ==")
    print("praxis " + " ".join(args))
    code = praxis_main(["--root", str(root), *args])
    if code:
        print(f"stopped: {label} returned {code}")
    return int(code)


def copy_core_demo_dataset(root: Path) -> Path:
    target = research_dir(root) / "demo_sources" / "stackoverflow_developer_survey"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    data_root = resources.files("praxis").joinpath(*CORE_DEMO_DATA)
    for item in data_root.iterdir():
        if item.is_file():
            (target / item.name).write_bytes(item.read_bytes())
    return target


def demo_core(root: Path) -> int:
    print("# Praxis Core demo")
    print(
        "\nThis demo ingests a bundled Stack Overflow Developer Survey aggregate, writes provisional SkillGraph memory, chunks it, embeds it, and searches it."
    )
    source_path = copy_core_demo_dataset(root)
    steps = [
        ("Initialize relational DB", ["init-db"]),
        ("Initialize SkillGraph", ["init-graph"]),
        (
            "Ingest demo source",
            [
                "ingest",
                str(source_path),
                "--title",
                "Stack Overflow Developer Survey AI Tooling Mini Dataset",
                "--source-type",
                "survey",
                "--source-id",
                CORE_DEMO_SOURCE_ID,
                "--freshness-window-days",
                "365",
                "--notes",
                "Bundled aggregate demo dataset derived from official Stack Overflow Developer Survey 2024 and 2025 archive files.",
            ],
        ),
        ("Chunk changed sources", ["chunk", "--changed-only", "--no-runtimes", "--no-skills"]),
        ("Embed chunks locally", ["embed", "--provider", "local-hash"]),
        (
            "Search with explanations",
            ["search", "Stack Overflow developer survey AI tool adoption trust accuracy developer segments", "--explain", "--limit", "3"],
        ),
    ]
    for label, args in steps:
        code = run_step(root, label, args)
        if code:
            return code
    print(
        """
Core demo complete.

You saw the full source-to-search path:
  bundled aggregate survey data -> evidence archive -> provisional SkillGraph memory -> chunks -> embeddings -> explained search.

Try next:
  praxis changes list
  praxis conflicts list
  praxis export-skill-refs
""".strip()
    )
    return 0


def demo_reach(root: Path, client_id: str, profile: str) -> int:
    print("# Praxis Reach demo")
    print("\nThis demo uses fixture GTM data, so it does not need live credentials.")
    steps = [
        ("Initialize Reach", ["reach", "init"]),
        ("Create fixture client", ["agency", "fixture", "create", client_id, "--profile", profile, "--overwrite"]),
        ("Run weekly GTM review", ["agency", "run", "weekly_gtm_review", "--clients", client_id, "--context"]),
        ("List evidence", ["reach", "evidence", "list", "--client", client_id]),
        ("Check freshness", ["reach", "stale", "list", "--client", client_id, "--all"]),
    ]
    for label, args in steps:
        code = run_step(root, label, args)
        if code:
            return code
    print(
        f"""
Reach demo complete.

You saw the zero-copy evidence path:
  fixture systems -> query manifest -> evidence card -> context pack.

Try next:
  praxis reach evidence show "ev:..."
  praxis reach context build weekly_gtm_review --client {client_id}
""".strip()
    )
    return 0


def demo_agency(root: Path) -> int:
    print("# Praxis Reach for Agencies demo")
    print("\nThis demo creates two fixture clients and runs one GTM workflow across both.")
    steps = [
        ("Initialize Reach", ["reach", "init"]),
        ("Create Acme fixture client", ["agency", "fixture", "create", "acme", "--profile", "b2b-saas", "--overwrite"]),
        ("Create Beta fixture client", ["agency", "fixture", "create", "beta", "--profile", "local-services", "--overwrite"]),
        ("List clients", ["agency", "client", "list", "--include-archived"]),
        ("Run weekly GTM review across clients", ["agency", "run", "weekly_gtm_review", "--clients", "acme,beta", "--context"]),
        ("Show stale context report", ["agency", "stale-context-report", "--all"]),
    ]
    for label, args in steps:
        code = run_step(root, label, args)
        if code:
            return code
    print(
        """
Agency demo complete.

You saw the multi-client path:
  client capsules -> per-client fixture data -> shared workflow -> per-client evidence/context.

Try next:
  praxis agency client show acme
  praxis agency client show beta
  praxis agency client export acme
""".strip()
    )
    return 0


def list_demos() -> int:
    print("# Praxis demos\n")
    for module, description in MODULES.items():
        print(f"- {module}: {description}")
    print("\nRun one with:")
    print("  praxis demo core")
    print("  praxis demo reach")
    print("  praxis demo agency")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="praxis demo", description=__doc__)
    parser.add_argument("module", nargs="?", choices=sorted(MODULES), help="Demo module to run.")
    parser.add_argument("--root", default=str(default_root()), help="Praxis checkout/workspace root.")
    parser.add_argument("--client", default="demo", help="Client id for the Reach demo.")
    parser.add_argument("--profile", default="b2b-saas", choices=["b2b-saas", "local-services"], help="Fixture profile for the Reach demo.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not args.module:
        return list_demos()

    root = Path(args.root).expanduser().resolve()
    if args.module == "core":
        return demo_core(root)
    if args.module == "reach":
        return demo_reach(root, client_id=args.client, profile=args.profile)
    if args.module == "agency":
        return demo_agency(root)
    for runner in (
        demo_core,
        lambda value: demo_reach(value, client_id=args.client, profile=args.profile),
        demo_agency,
    ):
        code = runner(root)
        if code:
            return code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
