#!/usr/bin/env python3
"""Praxis agency commands for multi-client GTM operating context."""

from __future__ import annotations

import argparse
from pathlib import Path

from praxis.agency.cli_output import (
    print_agency_run,
    print_client_list,
    print_client_summary,
    print_delete_plan,
    print_field_map,
    print_metric_definitions,
)
from praxis.agency.clients import (
    create_client,
    list_clients,
    load_client,
    set_conversion_definition,
    set_field_mapping,
    set_metric_definition,
    validate_client,
)
from praxis.agency.fixtures import create_demo_client
from praxis.agency.lifecycle import (
    archive_client,
    create_delete_plan,
    delete_client,
    export_client,
    load_delete_plan,
    purge_quarantine,
)
from praxis.agency.runner import run_for_clients_report
from praxis.paths import default_root
from praxis.reach.evidence import list_evidence
from praxis.reach.freshness import computed_freshness_status, evidence_age_hours
from praxis.reach.manifests import load_manifest
from praxis.reach.storage import ensure_reach_workspace


def cmd_client_create(args: argparse.Namespace) -> int:
    root = Path(args.root)
    ensure_reach_workspace(root)
    capsule = create_client(
        root,
        args.client_id,
        name=args.name,
        timezone=args.timezone,
        currency=args.currency,
        crm=args.crm,
        ads=args.ads,
        analytics=args.analytics or None,
        warehouse=args.warehouse or None,
        overwrite=args.overwrite,
    )
    print(f"client_id: {capsule.client_id}")
    print(f"name: {capsule.name}")
    print(f"capsule: {root / 'agency' / 'clients' / capsule.client_id / 'client.json'}")
    return 0


def cmd_client_list(args: argparse.Namespace) -> int:
    root = Path(args.root)
    clients = list_clients(root, include_archived=args.include_archived)
    print_client_list(root, clients)
    return 0


def cmd_client_show(args: argparse.Namespace) -> int:
    root = Path(args.root)
    capsule = load_client(root, args.client_id)
    print_client_summary(root, capsule)
    return 0


def cmd_client_doctor(args: argparse.Namespace) -> int:
    capsule = load_client(Path(args.root), args.client_id)
    print(f"# Client doctor: {capsule.client_id}\n")
    errors = validate_client(capsule)
    ok = not errors
    for error in errors:
        print(f"warning: {error}")
    if ok:
        print("ok: capsule contract")
    providers = capsule.providers()
    if providers:
        print(f"ok: providers: {', '.join(providers)}")
    else:
        print("missing: no providers configured")
        ok = False
    print(f"status: {'ok' if ok else 'needs-attention'}")
    return 0 if ok else 1


def cmd_client_map_fields(args: argparse.Namespace) -> int:
    root = Path(args.root)
    if bool(args.field) != bool(args.source_field):
        raise RuntimeError("--field and --source-field must be provided together.")
    if args.object:
        set_field_mapping(
            root,
            args.client_id,
            object_id=args.object,
            source=args.source,
            field=args.field,
            source_field=args.source_field,
        )
    capsule = load_client(root, args.client_id)
    print_field_map(capsule)
    return 0


def cmd_client_metrics(args: argparse.Namespace) -> int:
    capsule = load_client(Path(args.root), args.client_id)
    print_metric_definitions(capsule)
    return 0


def cmd_client_define_metric(args: argparse.Namespace) -> int:
    source_priority = [item.strip() for item in args.source_priority.split(",") if item.strip()]
    set_metric_definition(
        Path(args.root),
        args.client_id,
        args.metric_id,
        canonical_object=args.canonical_object,
        description=args.description,
        source_priority=source_priority,
        definition=args.definition,
    )
    print(f"metric_id: {args.metric_id}")
    print("status: updated")
    return 0


def cmd_client_define_conversion(args: argparse.Namespace) -> int:
    set_conversion_definition(
        Path(args.root),
        args.client_id,
        args.conversion_id,
        source=args.source,
        source_name=args.source_name or "",
        source_id=args.source_id or "",
        canonical_metric=args.canonical_metric,
        weight=args.weight,
        primary=not args.secondary,
        description=args.description or "",
    )
    print(f"conversion_id: {args.conversion_id}")
    print(f"source: {args.source}")
    print("status: updated")
    return 0


def cmd_client_archive(args: argparse.Namespace) -> int:
    record = archive_client(
        Path(args.root),
        args.client_id,
        reason=args.reason,
        force=args.force,
        dry_run=args.dry_run,
    )
    print(f"client_id: {record['client_id']}")
    print(f"status: {record['status']}")
    print(f"archived_at: {record.get('archived_at', '')}")
    print(f"reason: {record.get('reason', '')}")
    if record.get("dry_run"):
        print(f"would_write: {record['would_write']}")
    return 0


def cmd_client_export(args: argparse.Namespace) -> int:
    path = export_client(
        Path(args.root),
        args.client_id,
        output=Path(args.output).expanduser() if args.output else None,
        redact=not args.no_redact,
    )
    print(f"client_id: {args.client_id}")
    print(f"export: {path}")
    print(f"redacted: {not args.no_redact}")
    return 0


def cmd_client_delete_plan(args: argparse.Namespace) -> int:
    plan = create_delete_plan(
        Path(args.root),
        args.client_id,
        reason=args.reason,
        require_archive=not args.no_archive_required,
    )
    print_delete_plan(plan)
    print('confirmation_required: --confirm-client {0} --confirm-delete "DELETE"'.format(plan["client_id"]))
    return 0


def cmd_client_delete_show_plan(args: argparse.Namespace) -> int:
    print_delete_plan(load_delete_plan(Path(args.root), args.plan))
    return 0


def cmd_client_delete(args: argparse.Namespace) -> int:
    receipt = delete_client(
        Path(args.root),
        plan_id=args.plan,
        confirm_client=args.confirm_client,
        confirm_delete=args.confirm_delete,
        no_archive=args.no_archive,
        reason=args.reason,
    )
    print(f"receipt_id: {receipt['receipt_id']}")
    print(f"client_id: {receipt['client_id']}")
    print(f"status: {receipt['status']}")
    print(f"moved: {len(receipt['moved'])}")
    print(f"missing: {len(receipt['missing'])}")
    print(f"quarantine_path: {receipt['quarantine_path']}")
    print("note: use `praxis agency client purge ...` to permanently remove quarantined files")
    return 0


def cmd_client_purge(args: argparse.Namespace) -> int:
    receipt = purge_quarantine(
        Path(args.root),
        receipt_id=args.receipt,
        confirm_delete=args.confirm_delete,
    )
    print(f"receipt_id: {receipt['receipt_id']}")
    print(f"client_id: {receipt['client_id']}")
    print(f"status: {receipt['status']}")
    print(f"purged_at: {receipt.get('purged_at', '')}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    root = Path(args.root)
    if args.all_clients and args.clients:
        raise RuntimeError("Use either --all-clients or --clients, not both.")
    client_ids = args.clients.split(",") if args.clients else []
    results = run_for_clients_report(
        root,
        args.manifest,
        client_ids=client_ids,
        all_clients=args.all_clients,
        days=args.days,
        start_date=args.start_date,
        end_date=args.end_date,
        build_context=args.context,
        continue_on_error=args.continue_on_error,
    )
    had_errors = print_agency_run(results)
    return 1 if had_errors else 0


def cmd_fixture_create(args: argparse.Namespace) -> int:
    root = Path(args.root)
    ensure_reach_workspace(root)
    fixture_dir = create_demo_client(root, args.client_id, profile=args.profile, overwrite=args.overwrite)
    print(f"client_id: {args.client_id}")
    print(f"fixture_dir: {fixture_dir}")
    print("status: created")
    return 0


def cmd_stale_context_report(args: argparse.Namespace) -> int:
    root = Path(args.root)
    print("# Agency stale context report\n")
    found = 0
    for capsule in list_clients(root):
        cards = list_evidence(root, client_id=capsule.client_id)
        if not cards:
            print(f"- {capsule.client_id}: no evidence")
            found += 1
            continue
        stale_cards = []
        for card in cards:
            manifest = load_manifest(root, card.query_id)
            if computed_freshness_status(card, manifest) == "stale":
                stale_cards.append((card, manifest))
        if stale_cards:
            found += 1
            print(f"- {capsule.client_id}: stale evidence")
            for card, manifest in stale_cards:
                print(f"  - {card.evidence_id}: {evidence_age_hours(card):.1f}h old / {manifest.freshness_sla_hours}h SLA")
        elif args.all:
            print(f"- {capsule.client_id}: fresh")
    if not found:
        print("No stale or missing client context found.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="praxis agency", description=__doc__)
    parser.add_argument("--root", default=str(default_root()), help="Praxis checkout/workspace root.")
    sub = parser.add_subparsers(dest="command", required=True)

    client = sub.add_parser("client", help="Manage agency client capsules.")
    client_sub = client.add_subparsers(dest="client_command", required=True)

    create = client_sub.add_parser("create", help="Create a client capsule.")
    create.add_argument("client_id")
    create.add_argument("--name", help="Human-readable client name.")
    create.add_argument("--timezone", default="UTC")
    create.add_argument("--currency", default="USD")
    create.add_argument("--crm", default="mock_crm", help="CRM provider id.")
    create.add_argument("--ads", default="mock_ads", help="Ads provider id.")
    create.add_argument("--analytics", default="", help="Optional analytics provider id, such as google_analytics.")
    create.add_argument("--warehouse", default="", help="Optional warehouse provider id, such as bigquery.")
    create.add_argument("--overwrite", action="store_true", help="Replace an existing capsule.")
    create.set_defaults(func=cmd_client_create)

    list_cmd = client_sub.add_parser("list", help="List client capsules.")
    list_cmd.add_argument("--include-archived", action="store_true", help="Include archived client capsules.")
    list_cmd.set_defaults(func=cmd_client_list)

    show = client_sub.add_parser("show", help="Show a client capsule summary.")
    show.add_argument("client_id")
    show.set_defaults(func=cmd_client_show)

    doctor = client_sub.add_parser("doctor", help="Check a client capsule.")
    doctor.add_argument("client_id")
    doctor.set_defaults(func=cmd_client_doctor)

    map_fields = client_sub.add_parser("map-fields", help="Show or update a client field map.")
    map_fields.add_argument("client_id")
    map_fields.add_argument("--object", help="Canonical object to update, such as opportunity.")
    map_fields.add_argument("--source", help="Source collection/path for the object, such as hubspot.deals.")
    map_fields.add_argument("--field", help="Canonical field to map.")
    map_fields.add_argument("--source-field", help="Source-system field path.")
    map_fields.set_defaults(func=cmd_client_map_fields)

    metrics = client_sub.add_parser("metrics", help="List client metric definitions.")
    metrics.add_argument("client_id")
    metrics.set_defaults(func=cmd_client_metrics)

    define_metric = client_sub.add_parser("define-metric", help="Create or update a client metric definition.")
    define_metric.add_argument("client_id")
    define_metric.add_argument("metric_id")
    define_metric.add_argument("--canonical-object", required=True)
    define_metric.add_argument("--description", required=True)
    define_metric.add_argument("--source-priority", default="crm,ads")
    define_metric.add_argument("--definition", required=True)
    define_metric.set_defaults(func=cmd_client_define_metric)

    define_conversion = client_sub.add_parser("define-conversion", help="Map a platform conversion/event to client business meaning.")
    define_conversion.add_argument("client_id")
    define_conversion.add_argument("conversion_id")
    define_conversion.add_argument("--source", required=True, help="Provider id, such as google_ads or google_analytics.")
    define_conversion.add_argument("--source-name", help="Platform conversion action name or GA4 event name.")
    define_conversion.add_argument("--source-id", help="Platform conversion action id/resource name when available.")
    define_conversion.add_argument("--canonical-metric", default="conversions", help="Canonical metric this conversion contributes to.")
    define_conversion.add_argument("--weight", type=float, default=1.0, help="Contribution weight for this conversion.")
    define_conversion.add_argument("--secondary", action="store_true", help="Mark this as secondary/non-primary context.")
    define_conversion.add_argument("--description", default="")
    define_conversion.set_defaults(func=cmd_client_define_conversion)

    archive = client_sub.add_parser("archive", help="Mark a client capsule archived and skip it from default agency runs.")
    archive.add_argument("client_id")
    archive.add_argument("--reason", required=True)
    archive.add_argument("--dry-run", action="store_true")
    archive.add_argument("--force", action="store_true", help="Update archive metadata if already archived.")
    archive.set_defaults(func=cmd_client_archive)

    export = client_sub.add_parser("export", help="Export a redacted client capsule and local Reach artifacts.")
    export.add_argument("client_id")
    export.add_argument("--output", help="Output .tar.gz path. Defaults to agency/lifecycle/archives/.")
    export.add_argument("--no-redact", action="store_true", help="Do not redact secret-like JSON fields in the export bundle.")
    export.set_defaults(func=cmd_client_export)

    delete_plan = client_sub.add_parser("delete-plan", help="Create a reviewed deletion plan for a client capsule.")
    delete_plan.add_argument("client_id")
    delete_plan.add_argument("--reason", default="")
    delete_plan.add_argument("--no-archive-required", action="store_true", help="Do not require an export before delete.")
    delete_plan.set_defaults(func=cmd_client_delete_plan)

    show_plan = client_sub.add_parser("show-delete-plan", help="Show a saved deletion plan.")
    show_plan.add_argument("plan")
    show_plan.set_defaults(func=cmd_client_delete_show_plan)

    delete = client_sub.add_parser("delete", help="Execute a saved client deletion plan after exact confirmations.")
    delete.add_argument("--plan", required=True, help="Deletion plan id from delete-plan.")
    delete.add_argument("--confirm-client", required=True, help="Must exactly match the client id in the plan.")
    delete.add_argument("--confirm-delete", required=True, help='Must exactly equal "DELETE".')
    delete.add_argument("--no-archive", action="store_true", help="Allow deletion without an export archive. Requires --reason.")
    delete.add_argument("--reason", default="")
    delete.set_defaults(func=cmd_client_delete)

    purge = client_sub.add_parser("purge", help="Permanently remove quarantined files for a deletion receipt.")
    purge.add_argument("--receipt", required=True, help="Deletion receipt id.")
    purge.add_argument("--confirm-delete", required=True, help='Must exactly equal "PURGE".')
    purge.set_defaults(func=cmd_client_purge)

    run = sub.add_parser("run", help="Run a Reach query manifest across agency clients.")
    run.add_argument("manifest", help="Reach query manifest id.")
    run.add_argument("--clients", help="Comma-separated client ids.")
    run.add_argument("--all-clients", action="store_true", help="Run across every client capsule.")
    run.add_argument("--days", type=int, default=90)
    run.add_argument("--start-date", help="Explicit start date in YYYY-MM-DD format.")
    run.add_argument("--end-date", help="Explicit end date in YYYY-MM-DD format.")
    run.add_argument("--context", action="store_true", help="Build context packs from the generated evidence.")
    run.add_argument("--continue-on-error", action="store_true", help="Run remaining clients when one client fails.")
    run.set_defaults(func=cmd_run)

    fixture = sub.add_parser("fixture", help="Generate demo clients and local fixture data.")
    fixture_sub = fixture.add_subparsers(dest="fixture_command", required=True)
    fixture_create = fixture_sub.add_parser("create", help="Create a fixture-backed demo client.")
    fixture_create.add_argument("client_id")
    fixture_create.add_argument("--profile", default="b2b-saas", choices=["b2b-saas", "local-services"])
    fixture_create.add_argument("--overwrite", action="store_true")
    fixture_create.set_defaults(func=cmd_fixture_create)

    stale = sub.add_parser("stale-context-report", help="Report clients with stale or missing Reach context.")
    stale.add_argument("--all", action="store_true", help="Also show fresh clients.")
    stale.set_defaults(func=cmd_stale_context_report)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except (KeyError, RuntimeError, FileExistsError) as exc:
        print(f"error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
