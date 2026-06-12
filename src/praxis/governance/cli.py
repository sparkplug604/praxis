"""CLI for Praxis Core governance."""

from __future__ import annotations

import argparse
from pathlib import Path

from praxis.paths import default_root

from .doctor import run_governance_doctor
from .policy import evaluate_policy
from .storage import init_governance, list_events, show_event, verify_receipts


def active_root(args: argparse.Namespace) -> Path:
    return Path(args.root or default_root()).expanduser().resolve()


def cmd_init(args: argparse.Namespace) -> int:
    db_path = init_governance(active_root(args))
    print("status: ok")
    print(f"governance_db: {db_path}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    checks = run_governance_doctor(active_root(args), initialize=args.init)
    has_error = False
    for check in checks:
        print(f"{check.check_id}: {check.status} ({check.severity})")
        print(f"  {check.summary}")
        if check.severity == "error":
            has_error = True
    return 2 if has_error and args.strict else 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    metadata = {}
    for item in args.metadata:
        if "=" not in item:
            print(f"Metadata must use KEY=VALUE format: {item}")
            return 2
        key, value = item.split("=", 1)
        metadata[key.strip()] = value.strip()
    result = evaluate_policy(
        active_root(args),
        claim_type=args.claim_type,
        evidence_id=args.evidence,
        source=args.source or "",
        client_id=args.client or "",
        fresh_at=args.fresh_at or "",
        metadata=metadata,
        actor=args.actor,
        write_record=not args.no_record,
    )
    print(f"decision: {result.decision}")
    print(f"severity: {result.severity}")
    print(f"authority_decision: {result.authority_decision or '-'}")
    print(f"authority_reason: {result.authority_reason or '-'}")
    print(f"conflict_count: {result.conflict_count}")
    if result.evidence:
        print(f"evidence_exists: {str(result.evidence.exists).lower()}")
        print(f"evidence_kind: {result.evidence.source_kind or '-'}")
        print(f"evidence_status: {result.evidence.status or '-'}")
        if result.evidence.source_kind == "evidence_annotation":
            print(f"entity_resolution_status: {result.evidence.entity_resolution_status or '-'}")
            print(f"entity_resolution_confidence: {result.evidence.entity_resolution_confidence:.3f}")
            print(f"entity_resolution_method: {result.evidence.entity_resolution_method or '-'}")
            if result.evidence.resolved_entity_ids:
                print(f"resolved_entity_ids: {', '.join(result.evidence.resolved_entity_ids)}")
    for reason in result.reasons:
        print(f"- {reason}")
    return 0 if result.decision in {"allow", "warn"} else 3


def cmd_events_list(args: argparse.Namespace) -> int:
    events = list_events(active_root(args), limit=args.limit)
    if not events:
        print("No governance events found.")
        return 0
    for event in events:
        print(f"{event['event_id']}: {event['event_type']} {event['decision']} ({event['created_at']})")
    return 0


def cmd_events_show(args: argparse.Namespace) -> int:
    event = show_event(active_root(args), args.event_id)
    if event is None:
        print(f"Governance event not found: {args.event_id}")
        return 2
    for key in ["event_id", "event_type", "decision", "actor", "payload_hash", "previous_hash", "receipt_hash", "created_at"]:
        print(f"{key}: {event.get(key) or '-'}")
    return 0


def cmd_ledger_verify(args: argparse.Namespace) -> int:
    ok, errors = verify_receipts(active_root(args))
    print(f"ok: {str(ok).lower()}")
    if errors:
        for error in errors:
            print(f"- {error}")
    return 0 if ok else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Praxis Core governance.")
    parser.add_argument("--root", default=str(default_root()), help="Praxis workspace root.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize governance storage.")
    init_parser.set_defaults(func=cmd_init)

    doctor_parser = subparsers.add_parser("doctor", help="Run governance health checks.")
    doctor_parser.add_argument("--init", action="store_true", help="Initialize governance storage before checking.")
    doctor_parser.add_argument("--strict", action="store_true", help="Return nonzero on error checks.")
    doctor_parser.set_defaults(func=cmd_doctor)

    evaluate_parser = subparsers.add_parser("evaluate", help="Evaluate evidence for reuse.")
    evaluate_parser.add_argument("--claim-type", required=True)
    evaluate_parser.add_argument("--evidence", required=True)
    evaluate_parser.add_argument("--source")
    evaluate_parser.add_argument("--client")
    evaluate_parser.add_argument("--fresh-at")
    evaluate_parser.add_argument("--metadata", action="append", default=[])
    evaluate_parser.add_argument("--actor", default="cli")
    evaluate_parser.add_argument("--no-record", action="store_true")
    evaluate_parser.set_defaults(func=cmd_evaluate)

    events_parser = subparsers.add_parser("events", help="Inspect governance events.")
    events_subparsers = events_parser.add_subparsers(dest="events_command", required=True)
    events_list = events_subparsers.add_parser("list")
    events_list.add_argument("--limit", type=int, default=25)
    events_list.set_defaults(func=cmd_events_list)
    events_show = events_subparsers.add_parser("show")
    events_show.add_argument("event_id")
    events_show.set_defaults(func=cmd_events_show)

    ledger_parser = subparsers.add_parser("ledger", help="Inspect governance ledger receipts.")
    ledger_subparsers = ledger_parser.add_subparsers(dest="ledger_command", required=True)
    ledger_verify = ledger_subparsers.add_parser("verify")
    ledger_verify.set_defaults(func=cmd_ledger_verify)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
