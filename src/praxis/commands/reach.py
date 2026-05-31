#!/usr/bin/env python3
"""Praxis Reach commands for zero-copy live operational context."""

from __future__ import annotations

import argparse
from pathlib import Path

from praxis.agency.clients import list_clients, load_client, validate_client
from praxis.paths import default_root
from praxis.reach.connectors import available_connectors
from praxis.reach.context import build_context_pack
from praxis.reach.core_capture import write_evidence_source
from praxis.reach.date_ranges import build_date_params
from praxis.reach.evidence import list_evidence, load_evidence
from praxis.reach.freshness import computed_freshness_status, with_computed_freshness
from praxis.reach.cli_output import (
    print_connector_check,
    print_connector_discovery,
    print_evidence_detail,
    print_evidence_list,
    print_manifest_summary,
    print_query_result,
    print_stale_evidence,
)
from praxis.reach.manifests import list_manifests, load_manifest, seed_builtin_manifests, validate_manifests
from praxis.reach.ontology import seed_ontology
from praxis.reach.query_runner import run_manifest
from praxis.reach.storage import ensure_reach_workspace
from research_source import capture_source


def configured_connector(root: Path, provider: str, client_id: str):
    registry = available_connectors()
    if provider not in registry:
        raise SystemExit(f"Unknown connector: {provider}")
    capsule = load_client(root, client_id)
    if provider not in capsule.providers():
        raise RuntimeError(f"Client {capsule.client_id} does not configure provider {provider}.")
    return capsule, registry[provider]()


def cmd_init(args: argparse.Namespace) -> int:
    root = Path(args.root)
    ensure_reach_workspace(root)
    written = seed_builtin_manifests(root)
    ontology_written = seed_ontology(root)
    print("# Praxis Reach init")
    print(f"workspace: {root / 'reach'}")
    print(f"agency_clients: {root / 'agency' / 'clients'}")
    print(f"query_manifests_seeded: {len(written)}")
    print(f"ontology_seeded: {len(ontology_written)}")
    print("status: ok")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    root = Path(args.root)
    print("# Praxis Reach doctor")
    for path in [
        root / "reach",
        root / "reach" / "query_manifests",
        root / "reach" / "evidence",
        root / "reach" / "context_packs",
        root / "agency" / "clients",
    ]:
        status = "ok" if path.exists() else "optional-missing"
        print(f"{status}: {path}")
    print(f"ok: connectors: {', '.join(sorted(available_connectors()))}")
    print(f"ok: query manifests: {len(list_manifests(root))}")
    errors = validate_manifests(root)
    for error in errors:
        print(f"warning: {error}")
    client_errors = []
    for capsule in list_clients(root):
        capsule_errors = validate_client(capsule)
        if capsule_errors:
            client_errors.extend(f"{capsule.client_id}: {error}" for error in capsule_errors)
        else:
            print(f"ok: client capsule: {capsule.client_id}")
    for error in client_errors:
        print(f"warning: {error}")
    all_errors = errors + client_errors
    print(f"status: {'ok' if not all_errors else 'needs-attention'}")
    return 0 if not all_errors else 1


def cmd_connectors_list(args: argparse.Namespace) -> int:
    print("# Reach connectors\n")
    for name, connector_type in sorted(available_connectors().items()):
        capabilities = connector_type().capabilities()
        print(f"- {name}")
        print(f"  kind: {capabilities.get('kind')}")
        print(f"  status: {capabilities.get('status', 'available')}")
    return 0


def cmd_connectors_inspect(args: argparse.Namespace) -> int:
    registry = available_connectors()
    if args.provider not in registry:
        raise SystemExit(f"Unknown connector: {args.provider}")
    connector = registry[args.provider]()
    print(f"# {args.provider}\n")
    for key, value in sorted(connector.capabilities().items()):
        print(f"- {key}: {value}")
    return 0


def cmd_connectors_test(args: argparse.Namespace) -> int:
    root = Path(args.root)
    capsule, connector = configured_connector(root, args.provider, args.client)
    check_setup = getattr(connector, "check_setup", None)
    if check_setup is None:
        print(f"provider: {args.provider}")
        print("status: unknown")
        print("message: connector does not implement setup checks")
        return 1
    check = check_setup(capsule, live=args.live)
    print_connector_check(check, client_id=capsule.client_id)
    return 0 if check.status in {"ok", "configured"} else 1


def cmd_connectors_discover(args: argparse.Namespace) -> int:
    root = Path(args.root)
    capsule, connector = configured_connector(root, args.provider, args.client)
    discover = getattr(connector, "discover_resources", None)
    if discover is None:
        print(f"provider: {args.provider}")
        print("status: unavailable")
        print("message: connector does not implement discovery")
        return 1
    result = discover(capsule, live=args.live)
    print_connector_discovery(result, client_id=capsule.client_id)
    return 0 if result.status in {"ok", "configured"} else 1


def cmd_query_list(args: argparse.Namespace) -> int:
    root = Path(args.root)
    print("# Reach query manifests\n")
    for manifest in list_manifests(root):
        print_manifest_summary(manifest)
    return 0


def cmd_query_run(args: argparse.Namespace) -> int:
    root = Path(args.root)
    ensure_reach_workspace(root)
    capsule = load_client(root, args.client)
    manifest = load_manifest(root, args.manifest)
    params = {
        "client_id": capsule.client_id,
        **build_date_params(
            args.days,
            args.start_date,
            args.end_date,
            partial_range_message="--start-date and --end-date must be provided together.",
        ),
    }
    card = run_manifest(root, capsule, manifest, params)
    print_query_result(card)
    return 0


def cmd_evidence_list(args: argparse.Namespace) -> int:
    cards = list_evidence(Path(args.root), client_id=args.client)
    print_evidence_list(cards)
    return 0


def cmd_evidence_show(args: argparse.Namespace) -> int:
    root = Path(args.root)
    card = load_evidence(root, args.evidence_id)
    manifest = load_manifest(root, card.query_id)
    card = with_computed_freshness(card, manifest)
    print_evidence_detail(card)
    return 0


def cmd_evidence_capture(args: argparse.Namespace) -> int:
    root = Path(args.root)
    card = load_evidence(root, args.evidence_id)
    source_path = write_evidence_source(root, card)
    capture = capture_source(
        root=root,
        source=str(source_path),
        title=f"Reach Evidence: {card.query_id} / {card.client_id}",
        source_type="reach_evidence",
        source_id=f"src:reach-evidence:{card.query_id}:{card.client_id}:{card.query_hash}",
        freshness_window_days=args.freshness_window_days,
        notes="Captured from a Praxis Reach evidence card.",
    )
    print(f"source_id: {capture['source_id']}")
    print(f"capture_id: {capture['capture_id']}")
    print(f"source_file: {source_path}")
    return 0


def cmd_evidence_refresh(args: argparse.Namespace) -> int:
    root = Path(args.root)
    card = load_evidence(root, args.evidence_id)
    capsule = load_client(root, card.client_id)
    manifest = load_manifest(root, card.query_id)
    if not card.params:
        raise RuntimeError("Evidence card has no stored params and cannot be refreshed.")
    refreshed = run_manifest(root, capsule, manifest, dict(card.params))
    print(f"evidence_id: {refreshed.evidence_id}")
    print(f"fresh_at: {refreshed.fresh_at}")
    print(f"row_count: {refreshed.row_count}")
    return 0


def cmd_stale_list(args: argparse.Namespace) -> int:
    root = Path(args.root)
    stale = []
    for card in list_evidence(root, client_id=args.client):
        manifest = load_manifest(root, card.query_id)
        status = computed_freshness_status(card, manifest)
        if status == "stale" or args.all:
            stale.append((card, manifest, status))
    print_stale_evidence(stale)
    return 0


def cmd_context_build(args: argparse.Namespace) -> int:
    path = build_context_pack(Path(args.root), client_id=args.client, template=args.template, query_id=args.query)
    print(f"context_pack: {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="praxis reach", description=__doc__)
    parser.add_argument("--root", default=str(default_root()), help="Praxis checkout/workspace root.")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create Reach workspace folders and seed built-in manifests.")
    init.set_defaults(func=cmd_init)

    doctor = sub.add_parser("doctor", help="Check the Reach workspace and installed connectors.")
    doctor.set_defaults(func=cmd_doctor)

    connectors = sub.add_parser("connectors", help="Inspect Reach connectors.")
    connectors_sub = connectors.add_subparsers(dest="connectors_command", required=True)
    connectors_list = connectors_sub.add_parser("list", help="List installed connectors.")
    connectors_list.set_defaults(func=cmd_connectors_list)
    connectors_inspect = connectors_sub.add_parser("inspect", help="Inspect one connector.")
    connectors_inspect.add_argument("provider")
    connectors_inspect.set_defaults(func=cmd_connectors_inspect)
    connectors_test = connectors_sub.add_parser("test", help="Check one connector for a client without running a query.")
    connectors_test.add_argument("provider")
    connectors_test.add_argument("--client", required=True, help="Agency client id.")
    connectors_test.add_argument("--live", action="store_true", help="Call the provider API to verify credentials and read scopes.")
    connectors_test.set_defaults(func=cmd_connectors_test)
    connectors_discover = connectors_sub.add_parser("discover", help="Discover account/property resources for one configured connector.")
    connectors_discover.add_argument("provider")
    connectors_discover.add_argument("--client", required=True, help="Agency client id.")
    connectors_discover.add_argument("--live", action="store_true", help="Call the provider API to discover accessible resources.")
    connectors_discover.set_defaults(func=cmd_connectors_discover)

    query = sub.add_parser("query", help="List and run approved query manifests.")
    query_sub = query.add_subparsers(dest="query_command", required=True)
    query_list = query_sub.add_parser("list", help="List query manifests.")
    query_list.set_defaults(func=cmd_query_list)
    query_run = query_sub.add_parser("run", help="Run a query manifest for a client.")
    query_run.add_argument("manifest", help="Query manifest id.")
    query_run.add_argument("--client", required=True, help="Agency client id.")
    query_run.add_argument("--days", type=int, default=90, help="Lookback window for generated date params.")
    query_run.add_argument("--start-date", help="Explicit start date in YYYY-MM-DD format.")
    query_run.add_argument("--end-date", help="Explicit end date in YYYY-MM-DD format.")
    query_run.set_defaults(func=cmd_query_run)

    evidence = sub.add_parser("evidence", help="Inspect evidence cards.")
    evidence_sub = evidence.add_subparsers(dest="evidence_command", required=True)
    evidence_list = evidence_sub.add_parser("list", help="List evidence cards.")
    evidence_list.add_argument("--client", help="Filter by client id.")
    evidence_list.set_defaults(func=cmd_evidence_list)
    evidence_show = evidence_sub.add_parser("show", help="Show an evidence card.")
    evidence_show.add_argument("evidence_id")
    evidence_show.set_defaults(func=cmd_evidence_show)
    evidence_capture = evidence_sub.add_parser("capture", help="Capture an evidence card into Praxis Core source memory.")
    evidence_capture.add_argument("evidence_id")
    evidence_capture.add_argument("--freshness-window-days", type=int, default=7)
    evidence_capture.set_defaults(func=cmd_evidence_capture)
    evidence_refresh = evidence_sub.add_parser("refresh", help="Refresh an evidence card by rerunning its query manifest.")
    evidence_refresh.add_argument("evidence_id")
    evidence_refresh.set_defaults(func=cmd_evidence_refresh)

    stale = sub.add_parser("stale", help="Inspect stale Reach evidence.")
    stale_sub = stale.add_subparsers(dest="stale_command", required=True)
    stale_list = stale_sub.add_parser("list", help="List stale evidence cards.")
    stale_list.add_argument("--client", help="Filter by client id.")
    stale_list.add_argument("--all", action="store_true", help="Show fresh and stale evidence.")
    stale_list.set_defaults(func=cmd_stale_list)

    context = sub.add_parser("context", help="Build source-linked context packs from evidence.")
    context_sub = context.add_subparsers(dest="context_command", required=True)
    context_build = context_sub.add_parser("build", help="Build a context pack from latest evidence.")
    context_build.add_argument("template", help="Context pack template/name.")
    context_build.add_argument("--client", required=True, help="Agency client id.")
    context_build.add_argument("--query", help="Use latest evidence for this query id.")
    context_build.set_defaults(func=cmd_context_build)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except (KeyError, RuntimeError) as exc:
        print(f"error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
