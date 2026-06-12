"""CLI for the Praxis authority layer."""

from __future__ import annotations

import argparse
from pathlib import Path

from praxis.paths import default_root

from .adjudicator import adjudicate_request, list_adjudication_records, show_adjudication_record
from .models import AdjudicationRequest
from .registry import activate_bundle, compile_bundle, get_anchor, init_workspace, list_anchors, verify_registry


def active_root(args: argparse.Namespace) -> Path:
    return Path(args.root or default_root()).expanduser().resolve()


def cmd_init(args: argparse.Namespace) -> int:
    result = init_workspace(active_root(args), force=args.force)
    print("status: ok")
    print(f"bundle_path: {result['bundle_path']}")
    print(f"manifest_path: {result['manifest_path']}")
    return 0


def cmd_compile(args: argparse.Namespace) -> int:
    root = active_root(args)
    bundle_path = Path(args.bundle).expanduser().resolve() if args.bundle else None
    result = compile_bundle(root, bundle_path=bundle_path)
    print("status: ok")
    print(f"bundle_id: {result['bundle_id']}")
    print(f"bundle_hash: {result['bundle_hash']}")
    print(f"registry: {result['registry']}")
    return 0


def cmd_activate(args: argparse.Namespace) -> int:
    result = activate_bundle(active_root(args), Path(args.bundle))
    print("status: ok")
    print(f"active_bundle: {result['bundle_path']}")
    print(f"manifest_path: {result['manifest_path']}")
    print("next: run `praxis authority compile`")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    result = verify_registry(active_root(args), strict=args.strict)
    print(f"status: {result['status']}")
    print(f"ok: {str(result['ok']).lower()}")
    print(f"message: {result['message']}")
    if result.get("bundle_id"):
        print(f"bundle_id: {result['bundle_id']}")
    if result.get("expected_hash"):
        print(f"expected_hash: {result['expected_hash']}")
    if result.get("actual_hash"):
        print(f"actual_hash: {result['actual_hash']}")
    return 0 if result["ok"] else 2


def cmd_anchors_list(args: argparse.Namespace) -> int:
    anchors = list_anchors(active_root(args))
    if not anchors:
        print("No authority anchors compiled yet. Run `praxis authority compile`.")
        return 0
    for anchor in anchors:
        print(f"{anchor.anchor_id}: {anchor.scope} -> {anchor.authoritative_source} [{anchor.status}]")
    return 0


def cmd_anchors_show(args: argparse.Namespace) -> int:
    anchor = get_anchor(active_root(args), args.anchor_id)
    if anchor is None:
        print(f"Authority anchor not found: {args.anchor_id}")
        return 2
    print(f"id: {anchor.anchor_id}")
    print(f"description: {anchor.description}")
    print(f"scope: {anchor.scope}")
    print(f"authoritative_source: {anchor.authoritative_source}")
    print(f"fallback_sources: {', '.join(anchor.fallback_sources) or '-'}")
    print(f"forbidden_sources: {', '.join(anchor.forbidden_sources) or '-'}")
    print(f"freshness_sla_hours: {anchor.freshness_sla_hours}")
    print(f"conflict_behavior: {anchor.conflict_behavior}")
    print(f"required_evidence: {', '.join(anchor.required_evidence) or '-'}")
    print(f"safe_default: {anchor.safe_default}")
    print(f"status: {anchor.status}")
    return 0


def parse_metadata(items: list[str]) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Metadata must use KEY=VALUE format: {item}")
        key, value = item.split("=", 1)
        metadata[key.strip()] = value.strip()
    return metadata


def cmd_adjudicate(args: argparse.Namespace) -> int:
    try:
        metadata = parse_metadata(args.metadata)
    except ValueError as exc:
        print(str(exc))
        return 2
    request = AdjudicationRequest(
        claim_type=args.claim_type,
        source=args.source,
        client_id=args.client or "",
        evidence_id=args.evidence or "",
        fresh_at=args.fresh_at or "",
        metadata=metadata,
    )
    result = adjudicate_request(active_root(args), request, actor=args.actor, write_record=not args.no_record)
    print(f"decision: {result.decision}")
    print(f"reason: {result.reason}")
    print(f"anchor_id: {result.anchor_id or '-'}")
    print(f"bundle_id: {result.bundle_id or '-'}")
    print(f"bundle_hash: {result.bundle_hash or '-'}")
    print(f"safe_default: {result.safe_default}")
    if result.details:
        for key, value in result.details.items():
            print(f"{key}: {value}")
    return 0 if result.decision in {"allow", "warn", "unknown"} else 3


def cmd_records_list(args: argparse.Namespace) -> int:
    records = list_adjudication_records(active_root(args), limit=args.limit)
    if not records:
        print("No adjudication records yet.")
        return 0
    for record in records:
        print(
            f"{record['record_id']}: {record['decision']} {record['claim_type']} "
            f"from {record['source']} ({record['created_at']})"
        )
    return 0


def cmd_records_show(args: argparse.Namespace) -> int:
    record = show_adjudication_record(active_root(args), args.record_id)
    if record is None:
        print(f"Adjudication record not found: {args.record_id}")
        return 2
    for key in [
        "record_id",
        "decision",
        "reason",
        "claim_type",
        "source",
        "client_id",
        "evidence_id",
        "anchor_id",
        "bundle_id",
        "bundle_hash",
        "created_at",
        "actor",
    ]:
        print(f"{key}: {record.get(key) or '-'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="praxis authority",
        description="Manage authority anchors and adjudicate source-backed claims.",
    )
    parser.add_argument("--root", default=str(default_root()), help="Praxis workspace root.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create the authority workspace.")
    init_parser.add_argument("--force", action="store_true", help="Overwrite starter files.")
    init_parser.set_defaults(func=cmd_init)

    compile_parser = subparsers.add_parser("compile", help="Compile the active authority bundle, or compile a provided bundle without activating it.")
    compile_parser.add_argument("--bundle", help="Optional bundle JSON path.")
    compile_parser.set_defaults(func=cmd_compile)

    activate_parser = subparsers.add_parser("activate", help="Set the active authority bundle.")
    activate_parser.add_argument("bundle", help="Bundle JSON path to activate.")
    activate_parser.set_defaults(func=cmd_activate)

    verify_parser = subparsers.add_parser("verify", help="Verify the compiled registry matches the active bundle.")
    verify_parser.add_argument("--strict", action="store_true", help="Fail if the registry has not been compiled.")
    verify_parser.set_defaults(func=cmd_verify)

    anchors_parser = subparsers.add_parser("anchors", help="Inspect authority anchors.")
    anchors_subparsers = anchors_parser.add_subparsers(dest="anchors_command", required=True)
    anchors_list = anchors_subparsers.add_parser("list", help="List compiled anchors.")
    anchors_list.set_defaults(func=cmd_anchors_list)
    anchors_show = anchors_subparsers.add_parser("show", help="Show one compiled anchor.")
    anchors_show.add_argument("anchor_id")
    anchors_show.set_defaults(func=cmd_anchors_show)

    adjudicate_parser = subparsers.add_parser("adjudicate", help="Evaluate a claim source against authority anchors.")
    adjudicate_parser.add_argument("--claim-type", required=True)
    adjudicate_parser.add_argument("--source", required=True)
    adjudicate_parser.add_argument("--client")
    adjudicate_parser.add_argument("--evidence")
    adjudicate_parser.add_argument("--fresh-at")
    adjudicate_parser.add_argument("--metadata", action="append", default=[], help="Additional scope metadata as KEY=VALUE.")
    adjudicate_parser.add_argument("--actor", default="cli")
    adjudicate_parser.add_argument("--no-record", action="store_true", help="Do not write an adjudication record.")
    adjudicate_parser.set_defaults(func=cmd_adjudicate)

    records_parser = subparsers.add_parser("records", help="Inspect adjudication records.")
    records_subparsers = records_parser.add_subparsers(dest="records_command", required=True)
    records_list = records_subparsers.add_parser("list", help="List recent adjudications.")
    records_list.add_argument("--limit", type=int, default=20)
    records_list.set_defaults(func=cmd_records_list)
    records_show = records_subparsers.add_parser("show", help="Show one adjudication record.")
    records_show.add_argument("record_id")
    records_show.set_defaults(func=cmd_records_show)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
