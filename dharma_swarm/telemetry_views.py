"""Read models over the canonical telemetry plane."""

from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass, field

from dharma_swarm.telemetry_plane import TelemetryPlaneStore


@dataclass(frozen=True)
class TelemetryOverview:
    agent_count: int
    active_agents: int
    team_count: int
    reward_event_count: int
    workflow_score_count: int
    routing_decision_count: int
    policy_decision_count: int
    intervention_count: int
    economic_event_count: int
    external_outcome_count: int
    total_cost_usd: float
    total_revenue_usd: float


@dataclass(frozen=True)
class RoutingSummary:
    total_decisions: int
    human_required_count: int
    path_counts: dict[str, int] = field(default_factory=dict)
    provider_counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class EconomicSummary:
    event_count: int
    total_cost_usd: float
    total_revenue_usd: float
    net_usd: float
    currency_breakdown: dict[str, float] = field(default_factory=dict)


class TelemetryViews:
    """Thin read models for Command Nexus and future telemetry APIs."""

    def __init__(self, telemetry: TelemetryPlaneStore) -> None:
        self.telemetry = telemetry

    async def overview(self) -> TelemetryOverview:
        await self.telemetry.init_db()
        return await asyncio.to_thread(self._overview_sync)

    async def routing_summary(self) -> RoutingSummary:
        await self.telemetry.init_db()
        return await asyncio.to_thread(self._routing_summary_sync)

    async def economic_summary(self) -> EconomicSummary:
        await self.telemetry.init_db()
        return await asyncio.to_thread(self._economic_summary_sync)

    # -- sync implementations (run via to_thread) --------------------------

    def _overview_sync(self) -> TelemetryOverview:
        with sqlite3.connect(str(self.telemetry.db_path)) as db:
            return TelemetryOverview(
                agent_count=self._count(db, "agent_identity"),
                active_agents=self._count(db, "agent_identity", " WHERE status = 'active'"),
                team_count=self._count_distinct(db, "team_roster", "team_id", " WHERE active = 1"),
                reward_event_count=self._count(db, "agent_reward_ledger"),
                workflow_score_count=self._count(db, "workflow_scores"),
                routing_decision_count=self._count(db, "routing_decisions"),
                policy_decision_count=self._count(db, "policy_decisions"),
                intervention_count=self._count(db, "intervention_outcomes"),
                economic_event_count=self._count(db, "economic_events"),
                external_outcome_count=self._count(db, "external_outcomes"),
                total_cost_usd=self._sum_amount(
                    db, "economic_events", "amount",
                    " WHERE event_kind = 'cost' AND currency = 'USD'",
                ),
                total_revenue_usd=self._sum_amount(
                    db, "economic_events", "amount",
                    " WHERE event_kind = 'revenue' AND currency = 'USD'",
                ),
            )

    def _routing_summary_sync(self) -> RoutingSummary:
        path_counts: dict[str, int] = {}
        provider_counts: dict[str, int] = {}
        with sqlite3.connect(str(self.telemetry.db_path)) as db:
            total_decisions = self._count(db, "routing_decisions")
            human_required_count = self._count(
                db, "routing_decisions", " WHERE requires_human = 1",
            )
            for path, count in db.execute(
                "SELECT route_path, COUNT(*) FROM routing_decisions GROUP BY route_path"
            ).fetchall():
                path_counts[str(path or "")] = int(count or 0)
            for provider, count in db.execute(
                "SELECT selected_provider, COUNT(*) FROM routing_decisions"
                " GROUP BY selected_provider"
            ).fetchall():
                provider_counts[str(provider or "")] = int(count or 0)
        return RoutingSummary(
            total_decisions=total_decisions,
            human_required_count=human_required_count,
            path_counts=path_counts,
            provider_counts=provider_counts,
        )

    def _economic_summary_sync(self) -> EconomicSummary:
        currency_breakdown: dict[str, float] = {}
        with sqlite3.connect(str(self.telemetry.db_path)) as db:
            event_count = self._count(db, "economic_events")
            total_cost_usd = self._sum_amount(
                db, "economic_events", "amount",
                " WHERE event_kind = 'cost' AND currency = 'USD'",
            )
            total_revenue_usd = self._sum_amount(
                db, "economic_events", "amount",
                " WHERE event_kind = 'revenue' AND currency = 'USD'",
            )
            for currency, total in db.execute(
                "SELECT currency, COALESCE(SUM(amount), 0.0)"
                " FROM economic_events GROUP BY currency"
            ).fetchall():
                currency_breakdown[str(currency or "")] = float(total or 0.0)
        return EconomicSummary(
            event_count=event_count,
            total_cost_usd=total_cost_usd,
            total_revenue_usd=total_revenue_usd,
            net_usd=round(total_revenue_usd - total_cost_usd, 6),
            currency_breakdown=currency_breakdown,
        )

    @staticmethod
    def _count(db: sqlite3.Connection, table: str, where: str = "") -> int:
        return int(db.execute(f"SELECT COUNT(*) FROM {table}{where}").fetchone()[0])

    @staticmethod
    def _count_distinct(
        db: sqlite3.Connection,
        table: str,
        field: str,
        where: str = "",
    ) -> int:
        return int(db.execute(f"SELECT COUNT(DISTINCT {field}) FROM {table}{where}").fetchone()[0])

    @staticmethod
    def _sum_amount(
        db: sqlite3.Connection,
        table: str,
        field: str,
        where: str = "",
    ) -> float:
        return float(db.execute(f"SELECT COALESCE(SUM({field}), 0.0) FROM {table}{where}").fetchone()[0])
