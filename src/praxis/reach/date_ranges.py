"""Date-window helpers shared by Reach and Agency query runners."""

from __future__ import annotations

from datetime import date, timedelta


def build_date_params(
    days: int,
    start_date: str | None = None,
    end_date: str | None = None,
    *,
    partial_range_message: str = "start_date and end_date must be provided together.",
) -> dict[str, str]:
    if bool(start_date) != bool(end_date):
        raise RuntimeError(partial_range_message)
    if start_date and end_date:
        return {"start_date": start_date, "end_date": end_date}
    end = date.today()
    start = end - timedelta(days=days)
    return {"start_date": start.isoformat(), "end_date": end.isoformat()}
