"""Demo fixture generation for Praxis Reach agencies."""

from __future__ import annotations

from pathlib import Path

from praxis.agency.clients import create_client
from praxis.reach.storage import fixtures_dir, write_json


DEMO_PROFILES = {
    "b2b-saas": {
        "crm": {
            "summary": "Fixture CRM shows healthy pipeline but slower SQL conversion.",
            "metrics": {"leads": 96, "opportunities": 18, "pipeline_amount": 184000, "closed_won_revenue": 42000},
            "source_links": ["fixture://demo/crm/pipeline"],
            "row_count": 114,
        },
        "ads": {
            "summary": "Fixture ads shows paid reach down while spend is flat.",
            "metrics": {"spend": 28000, "reach": 73000, "impressions": 161000, "clicks": 5100, "leads": 141},
            "source_links": ["fixture://demo/ads/reach"],
            "warnings": ["Ad-platform leads are higher than CRM-confirmed leads."],
            "row_count": 90,
        },
    },
    "local-services": {
        "crm": {
            "summary": "Fixture CRM shows steady lead flow and modest opportunity value.",
            "metrics": {"leads": 54, "opportunities": 11, "pipeline_amount": 39000, "closed_won_revenue": 12000},
            "source_links": ["fixture://demo/crm/local-services"],
            "row_count": 65,
        },
        "ads": {
            "summary": "Fixture ads shows improving click volume with rising CPC.",
            "metrics": {"spend": 9100, "reach": 41000, "impressions": 88000, "clicks": 2400, "leads": 61},
            "source_links": ["fixture://demo/ads/local-services"],
            "warnings": ["CPC is rising faster than lead volume."],
            "row_count": 45,
        },
    },
}


def create_demo_client(root: Path, client_id: str, *, profile: str = "b2b-saas", overwrite: bool = False) -> Path:
    if profile not in DEMO_PROFILES:
        raise RuntimeError(f"Unknown fixture profile: {profile}")
    capsule = create_client(
        root,
        client_id,
        name=f"{client_id.title()} Demo",
        crm="fixture_crm",
        ads="fixture_ads",
        overwrite=overwrite,
    )
    out_dir = fixtures_dir(root) / capsule.client_id
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "fixture_crm.json", DEMO_PROFILES[profile]["crm"])
    write_json(out_dir / "fixture_ads.json", DEMO_PROFILES[profile]["ads"])
    return out_dir
