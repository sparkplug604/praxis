"""Multi-client runners for Praxis Reach agency workflows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from praxis.agency.clients import list_clients, load_client
from praxis.agency.lifecycle import is_archived
from praxis.reach.context import build_context_pack
from praxis.reach.date_ranges import build_date_params
from praxis.reach.evidence import EvidenceCard
from praxis.reach.manifests import load_manifest
from praxis.reach.query_runner import run_manifest


@dataclass(frozen=True)
class AgencyRunOutcome:
    client_id: str
    card: EvidenceCard | None = None
    context_path: Path | None = None
    error: str = ""


def selected_clients(root: Path, client_ids: list[str] | None = None, all_clients: bool = False):
    if all_clients:
        clients = list_clients(root)
    else:
        clients = [load_client(root, client_id) for client_id in (client_ids or [])]
    if not clients:
        raise RuntimeError("No clients selected.")
    archived = [capsule.client_id for capsule in clients if is_archived(root, capsule.client_id)]
    if archived:
        raise RuntimeError(f"Client is archived and cannot run Reach queries: {', '.join(archived)}")
    return clients


def run_for_clients(
    root: Path,
    manifest_id: str,
    *,
    client_ids: list[str] | None = None,
    all_clients: bool = False,
    days: int = 90,
    start_date: str | None = None,
    end_date: str | None = None,
    build_context: bool = False,
) -> list[tuple[EvidenceCard, Path | None]]:
    outcomes = run_for_clients_report(
        root,
        manifest_id,
        client_ids=client_ids,
        all_clients=all_clients,
        days=days,
        start_date=start_date,
        end_date=end_date,
        build_context=build_context,
        continue_on_error=False,
    )
    return [(outcome.card, outcome.context_path) for outcome in outcomes if outcome.card is not None]


def run_for_clients_report(
    root: Path,
    manifest_id: str,
    *,
    client_ids: list[str] | None = None,
    all_clients: bool = False,
    days: int = 90,
    start_date: str | None = None,
    end_date: str | None = None,
    build_context: bool = False,
    continue_on_error: bool = False,
) -> list[AgencyRunOutcome]:
    clients = selected_clients(root, client_ids=client_ids, all_clients=all_clients)
    manifest = load_manifest(root, manifest_id)
    window = build_date_params(days=days, start_date=start_date, end_date=end_date)
    outcomes: list[AgencyRunOutcome] = []
    for capsule in clients:
        try:
            card = run_manifest(
                root,
                capsule,
                manifest,
                {"client_id": capsule.client_id, **window},
            )
            context_path = None
            if build_context:
                context_path = build_context_pack(
                    root,
                    client_id=capsule.client_id,
                    template=manifest.context_template or manifest.manifest_id,
                    query_id=manifest.manifest_id,
                )
            outcomes.append(AgencyRunOutcome(client_id=capsule.client_id, card=card, context_path=context_path))
        except Exception as exc:
            if not continue_on_error:
                raise
            outcomes.append(AgencyRunOutcome(client_id=capsule.client_id, error=str(exc)))
    return outcomes
