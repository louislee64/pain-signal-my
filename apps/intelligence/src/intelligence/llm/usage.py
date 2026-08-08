"""AI cost tracking and budget enforcement (PROJECT_SPEC.md §44).

Two jobs:

1. Record every LLM call in `ai_usage` — successful or not. A failed call still
   consumed tokens and still cost money; omitting failures would make the ledger
   understate real spend exactly when something is going wrong.
2. Refuse to start a call that would exceed the configured daily or monthly
   budget. The check runs BEFORE the call, because a budget enforced after the
   spend has happened is a report, not a limit.
"""

import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from functools import lru_cache
from typing import Any

import yaml
from sqlalchemy import func, insert, select
from sqlalchemy.engine import Connection, Engine

from intelligence.db import ai_usage_table
from intelligence.observability import get_logger, log_event

logger = get_logger("intelligence.llm.usage")


class BudgetExceededError(RuntimeError):
    """Raised before a call that would breach the configured budget."""


@dataclass(frozen=True)
class LLMConfig:
    raw: dict[str, Any]

    @property
    def provider(self) -> str:
        return str(self.raw.get("provider", "anthropic"))

    @property
    def provider_config(self) -> dict[str, Any]:
        return dict(self.raw.get("provider_config") or {})

    @property
    def daily_budget_usd(self) -> float | None:
        value = (self.raw.get("budget") or {}).get("daily_usd")
        return float(value) if value is not None else None

    @property
    def monthly_budget_usd(self) -> float | None:
        value = (self.raw.get("budget") or {}).get("monthly_usd")
        return float(value) if value is not None else None

    @property
    def enabled(self) -> bool:
        """LLM extraction is OFF unless explicitly enabled.

        This is the safety default that matters most in this file: an
        accidentally-triggered pipeline run should cost nothing. Turning it on
        is a deliberate act in config/llm.yaml.
        """
        return bool(self.raw.get("enabled", False))

    @property
    def max_documents_per_run(self) -> int:
        return int(self.raw.get("max_documents_per_run", 50))

    @property
    def min_text_length(self) -> int:
        return int(self.raw.get("min_text_length", 80))

    @property
    def min_confidence(self) -> float:
        return float(self.raw.get("min_confidence", 0.5))


def load_llm_config(path: str | None = None) -> LLMConfig:
    path = path or os.environ.get("LLM_CONFIG_PATH", "/config/llm.yaml")
    try:
        with open(path) as f:
            return LLMConfig(raw=yaml.safe_load(f) or {})
    except FileNotFoundError:
        # Absent config means "not configured", which means disabled — the same
        # safe default as an explicit `enabled: false`.
        return LLMConfig(raw={})


@lru_cache(maxsize=1)
def get_llm_config() -> LLMConfig:
    return load_llm_config()


def spend_since(conn: Connection, since: datetime) -> float:
    total = conn.execute(
        select(func.coalesce(func.sum(ai_usage_table.c.estimated_cost), 0)).where(
            ai_usage_table.c.created_at >= since
        )
    ).scalar_one()
    return float(total)


def spend_today(conn: Connection, today: date | None = None) -> float:
    today = today or datetime.now(timezone.utc).date()
    return spend_since(conn, datetime(today.year, today.month, today.day, tzinfo=timezone.utc))


def spend_this_month(conn: Connection, today: date | None = None) -> float:
    today = today or datetime.now(timezone.utc).date()
    return spend_since(conn, datetime(today.year, today.month, 1, tzinfo=timezone.utc))


def check_budget(engine: Engine, config: LLMConfig, today: date | None = None) -> None:
    """Raise BudgetExceededError if either configured budget is already met.

    Checked before each call rather than once per run: a long run can cross the
    budget partway through, and stopping at that point is the whole purpose.
    """

    with engine.begin() as conn:
        daily = config.daily_budget_usd
        if daily is not None:
            spent = spend_today(conn, today)
            if spent >= daily:
                raise BudgetExceededError(
                    f"daily AI budget reached: ${spent:.4f} of ${daily:.2f} (§44)"
                )

        monthly = config.monthly_budget_usd
        if monthly is not None:
            spent = spend_this_month(conn, today)
            if spent >= monthly:
                raise BudgetExceededError(
                    f"monthly AI budget reached: ${spent:.4f} of ${monthly:.2f} (§44)"
                )


def record_usage(
    engine: Engine,
    *,
    provider: str,
    model: str,
    operation: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    estimated_cost: float = 0.0,
    document_id: str | None = None,
    prompt_version: str | None = None,
    processing_version: str | None = None,
    succeeded: bool = True,
    error: str | None = None,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            insert(ai_usage_table).values(
                provider=provider,
                model=model,
                operation=operation,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_cost=estimated_cost,
                currency="USD",
                document_id=document_id,
                prompt_version=prompt_version,
                processing_version=processing_version,
                succeeded=succeeded,
                error=error,
                created_at=datetime.now(timezone.utc),
            )
        )

    log_event(
        logger,
        "ai_usage.recorded",
        provider=provider,
        model=model,
        operation=operation,
        cost=round(estimated_cost, 6),
        succeeded=succeeded,
    )
