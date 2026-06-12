"""Health checks for Praxis Core governance."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from praxis.authority.registry import active_manifest_path, registry_path, verify_registry
from praxis.paths import kg_dir

from .models import GovernanceCheck
from .storage import governance_db_path, init_governance, verify_receipts


def blocking_governance_checks(
    checks: list[GovernanceCheck],
    *,
    threshold: str = "warn",
) -> list[GovernanceCheck]:
    """Return checks that should block a strict operation."""
    blocking = {"error"} if threshold == "error" else {"warn", "error"}
    return [check for check in checks if check.severity in blocking]


def _open_conflict_count(root: Path) -> int:
    db_path = kg_dir(root) / "skill_graph.sqlite"
    if not db_path.exists():
        return 0
    try:
        with sqlite3.connect(db_path) as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM conflict_records
                WHERE status IN ('open', 'acknowledged')
                """
            ).fetchone()
    except sqlite3.Error:
        return 0
    return int(row[0] if row else 0)


def run_governance_doctor(root: Path, *, initialize: bool = False) -> list[GovernanceCheck]:
    if initialize:
        init_governance(root)
    checks: list[GovernanceCheck] = []

    if governance_db_path(root).exists():
        ok, errors = verify_receipts(root)
        checks.append(
            GovernanceCheck(
                check_id="governance.ledger",
                severity="ok" if ok else "error",
                status="ok" if ok else "failed",
                summary="governance receipt chain is valid" if ok else "governance receipt chain is invalid",
                details={"errors": errors},
            )
        )
    else:
        checks.append(
            GovernanceCheck(
                check_id="governance.ledger",
                severity="warn",
                status="missing",
                summary="governance ledger has not been initialized",
            )
        )

    if active_manifest_path(root).exists():
        result = verify_registry(root, strict=True)
        checks.append(
            GovernanceCheck(
                check_id="governance.authority",
                severity="ok" if result["ok"] else "error",
                status=str(result["status"]),
                summary=str(result["message"]),
                details=result,
            )
        )
    elif registry_path(root).exists():
        checks.append(
            GovernanceCheck(
                check_id="governance.authority",
                severity="error",
                status="missing_manifest",
                summary="authority registry exists but active manifest is missing",
            )
        )
    else:
        checks.append(
            GovernanceCheck(
                check_id="governance.authority",
                severity="warn",
                status="not_configured",
                summary="authority anchors are not configured",
            )
        )

    conflict_count = _open_conflict_count(root)
    checks.append(
        GovernanceCheck(
            check_id="governance.conflicts",
            severity="warn" if conflict_count else "ok",
            status="open" if conflict_count else "ok",
            summary=f"{conflict_count} unresolved conflict(s)" if conflict_count else "no unresolved conflicts found",
            details={"open_conflicts": conflict_count},
        )
    )
    return checks
