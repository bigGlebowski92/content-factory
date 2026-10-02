"""Weekly spend reporting for Stage 2."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from content_factory.config import Settings
from content_factory.storage import Storage


def build_weekly_spend_report(
    storage: Storage,
    settings: Settings,
    *,
    direction: str | None = None,
    end: datetime | None = None,
) -> dict[str, Any]:
    """Aggregate model spend for the trailing 7 days."""
    end = end or datetime.utcnow()
    start = end - timedelta(days=7)

    stats = storage.get_spending_stats(
        start_date=start,
        end_date=end,
        direction=direction,
    )

    daily_limit = settings.daily_spend_limit_usd
    monthly_limit = settings.monthly_spend_limit_usd
    if direction:
        from content_factory.config import load_direction_profile

        profile = load_direction_profile(direction, settings.config_dir)
        if "daily_usd" in profile.limits:
            daily_limit = float(profile.limits["daily_usd"])
        if "monthly_usd" in profile.limits:
            monthly_limit = float(profile.limits["monthly_usd"])

    total = stats["total_cost_usd"]
    return {
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "direction": direction,
        "total_cost_usd": total,
        "by_stage": stats["by_stage"],
        "by_model": stats["by_model"],
        "limits": {
            "daily_usd": daily_limit,
            "monthly_usd": monthly_limit,
        },
        "summary_text": _format_summary(
            total=total,
            direction=direction,
            by_stage=stats["by_stage"],
            start=start,
            end=end,
        ),
    }


def _format_summary(
    *,
    total: float,
    direction: str | None,
    by_stage: dict[str, float],
    start: datetime,
    end: datetime,
) -> str:
    scope = direction or "все направления"
    lines = [
        f"Недельный отчёт расходов ({start.date()} → {end.date()})",
        f"Область: {scope}",
        f"Итого: ${total:.4f}",
    ]
    if by_stage:
        lines.append("По этапам:")
        for stage, cost in sorted(by_stage.items()):
            lines.append(f"  - {stage}: ${cost:.4f}")
    return "\n".join(lines)
