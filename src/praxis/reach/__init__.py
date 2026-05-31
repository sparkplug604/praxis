"""Praxis Reach: zero-copy live operational context primitives."""

from __future__ import annotations

from .evidence import EvidenceCard, create_evidence_card, latest_evidence
from .manifests import QueryManifest, builtin_manifests, load_manifest
from .models import ClientCapsule
from .ontology import CANONICAL_METRICS, CANONICAL_OBJECTS

__all__ = [
    "ClientCapsule",
    "CANONICAL_METRICS",
    "CANONICAL_OBJECTS",
    "EvidenceCard",
    "QueryManifest",
    "builtin_manifests",
    "create_evidence_card",
    "latest_evidence",
    "load_manifest",
]
