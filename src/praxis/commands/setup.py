#!/usr/bin/env python3
"""Guided setup wizard for Praxis."""

from __future__ import annotations

import argparse
from pathlib import Path

from praxis.cli import main as praxis_main
from praxis.paths import default_root


SETUP_PATHS = {
    "core": "Praxis Core: searchable knowledge and reusable skills",
    "reach-demo": "Praxis Reach demo: fixture GTM evidence with no live credentials",
    "agency-demo": "Praxis Agency demo: two fixture clients and one multi-client run",
    "hubspot": "Live HubSpot setup guide",
    "google-ads": "Live Google Ads setup guide",
    "ga4": "Live Google Analytics setup guide",
}


def run_step(root: Path, label: str, args: list[str]) -> int:
    print(f"\n== {label} ==")
    print("praxis " + " ".join(args))
    code = praxis_main(["--root", str(root), *args])
    if code:
        print(f"stopped: {label} returned {code}")
    return int(code)


def setup_core(root: Path) -> int:
    print("# Praxis Core setup\n")
    code = run_step(root, "Initialize Core", ["bootstrap"])
    if code:
        return code
    print(
        """
Core is ready.

Try:
  praxis ingest "https://example.com/source"
  praxis search "what did this source teach us?" --explain
""".strip()
    )
    return 0


def setup_reach_demo(root: Path, client_id: str, profile: str) -> int:
    print("# Praxis Reach fixture demo\n")
    steps = [
        ("Initialize Reach", ["reach", "init"]),
        ("Create fixture client", ["agency", "fixture", "create", client_id, "--profile", profile, "--overwrite"]),
        ("Run GTM review", ["agency", "run", "weekly_gtm_review", "--clients", client_id, "--context"]),
        ("List evidence", ["reach", "evidence", "list", "--client", client_id]),
    ]
    for label, args in steps:
        code = run_step(root, label, args)
        if code:
            return code
    print(
        f"""
Reach demo is ready.

You now have:
  - a fixture client capsule: {client_id}
  - local fixture CRM/ad data
  - one Reach evidence card
  - one generated context pack

Try:
  praxis reach evidence show "ev:..."
  praxis reach context build weekly_gtm_review --client {client_id}
""".strip()
    )
    return 0


def setup_agency_demo(root: Path) -> int:
    print("# Praxis Agency fixture demo\n")
    steps = [
        ("Initialize Reach", ["reach", "init"]),
        ("Create Acme fixture client", ["agency", "fixture", "create", "acme", "--profile", "b2b-saas", "--overwrite"]),
        ("Create Beta fixture client", ["agency", "fixture", "create", "beta", "--profile", "local-services", "--overwrite"]),
        ("Run multi-client GTM review", ["agency", "run", "weekly_gtm_review", "--clients", "acme,beta", "--context"]),
        ("Show stale context report", ["agency", "stale-context-report", "--all"]),
    ]
    for label, args in steps:
        code = run_step(root, label, args)
        if code:
            return code
    print(
        """
Agency demo is ready.

You now have:
  - two fixture client capsules
  - per-client evidence cards
  - per-client context packs
  - a stale/fresh context report

Try:
  praxis agency client list
  praxis reach evidence list --client acme
  praxis reach evidence list --client beta
""".strip()
    )
    return 0


def setup_live_guide(kind: str) -> int:
    docs = {
        "hubspot": "docs/connectors/hubspot.md",
        "google-ads": "docs/connectors/google-ads.md",
        "ga4": "docs/connectors/google-analytics.md",
    }
    print(f"# {SETUP_PATHS[kind]}\n")
    print("This path does not ask for credentials or call live APIs.")
    print(f"Read: {docs[kind]}")
    print("\nRecommended first commands:")
    print("  praxis reach init")
    if kind == "hubspot":
        print('  praxis agency client create acme --crm hubspot --ads mock_ads')
        print("  praxis reach connectors test hubspot --client acme")
    elif kind == "google-ads":
        print('  praxis agency client create acme --crm mock_crm --ads google_ads')
        print("  praxis reach connectors test google_ads --client acme")
    else:
        print('  praxis agency client create acme --crm mock_crm --ads mock_ads --analytics google_analytics')
        print("  praxis reach connectors test google_analytics --client acme")
    return 0


def choose_path() -> str:
    print("# Praxis setup\n")
    for index, (path, description) in enumerate(SETUP_PATHS.items(), start=1):
        print(f"{index}. {path}: {description}")
    choice = input("\nChoose a setup path: ").strip()
    if choice in SETUP_PATHS:
        return choice
    try:
        selected = list(SETUP_PATHS)[int(choice) - 1]
    except (ValueError, IndexError):
        raise RuntimeError(f"Unknown setup path: {choice}") from None
    return selected


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="praxis setup", description=__doc__)
    parser.add_argument("--root", default=str(default_root()), help="Praxis checkout/workspace root.")
    parser.add_argument("--path", choices=sorted(SETUP_PATHS), help="Setup path to run.")
    parser.add_argument("--non-interactive", action="store_true", help="Require --path and skip prompts.")
    parser.add_argument("--client", default="demo", help="Client id for reach-demo.")
    parser.add_argument("--profile", default="b2b-saas", choices=["b2b-saas", "local-services"], help="Fixture profile for reach-demo.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    if args.non_interactive and not args.path:
        print("error: --non-interactive requires --path")
        return 2
    try:
        path = args.path or choose_path()
        if path == "core":
            return setup_core(root)
        if path == "reach-demo":
            return setup_reach_demo(root, client_id=args.client, profile=args.profile)
        if path == "agency-demo":
            return setup_agency_demo(root)
        return setup_live_guide(path)
    except RuntimeError as exc:
        print(f"error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
