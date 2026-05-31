"""Build compact context packs from Reach evidence cards."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .evidence import EvidenceCard, latest_evidence
from .context_templates import render_template
from .freshness import with_computed_freshness
from .manifests import load_manifest
from .storage import context_dir, slug, write_text_atomic


def render_context_pack(card: EvidenceCard, template: str) -> str:
    return render_template(card, template)


def build_context_pack(root: Path, client_id: str, template: str, query_id: str | None = None) -> Path:
    card = latest_evidence(root, client_id=client_id, query_id=query_id)
    if card is None:
        raise RuntimeError("No evidence card found. Run `praxis reach query run ...` first.")
    manifest = load_manifest(root, card.query_id)
    card = with_computed_freshness(card, manifest)
    out_dir = context_dir(root) / slug(client_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    built_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    timestamp_id = built_at.replace("+00:00", "Z").replace(":", "").replace("-", "").replace(".", "")
    build_id = f"{timestamp_id}-{uuid4().hex[:8]}"
    path = out_dir / f"{slug(template)}-{slug(card.evidence_id.replace(':', '-'))}-{build_id}.md"
    write_text_atomic(path, render_context_pack(card, template))
    return path
