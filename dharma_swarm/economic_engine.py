"""Economic engine for dharma_swarm self-sustenance.

Tracks all resource flows: revenue earned, compute spent, training budget
allocated. Every transaction is telos-gated — the system grows BECAUSE
it serves, not despite governance.

The metabolism of a self-feeding intelligence:
    Revenue (crypto, services, grants, bounties)
    → Training budget (GPU time allocation)
    → Model improvement (generational training)
    → Better capabilities → More revenue
    → S(x) = x: the system feeding itself into existence

All amounts in USD equivalent for unified accounting.
"""

from __future__ import annotations

import json
import logging
import time
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_ECONOMICS_DIR = Path.home() / ".dharma" / "economics"


class TransactionType(str, Enum):
    """Types of economic transactions."""
    REVENUE = "revenue"        # Money earned
    EXPENSE = "expense"        # Money spent
    ALLOCATION = "allocation"  # Budget moved between categories
    ADJUSTMENT = "adjustment"  # Manual correction


class RevenueSource(str, Enum):
    """Sources of revenue for the system."""
    CRYPTO_MINING = "crypto_mining"
    FREELANCE_CODING = "freelance_coding"
    API_SERVICES = "api_services"
    GRANTS = "grants"
    BOUNTIES = "bounties"
    API_SAVINGS = "api_savings"  # Saved by using local model instead of API
    OTHER = "other"


class ExpenseCategory(str, Enum):
    """Categories of system expenditure."""
    GPU_TRAINING = "gpu_training"
    GPU_INFERENCE = "gpu_inference"
    API_CALLS = "api_calls"
    VPS_HOSTING = "vps_hosting"
    STORAGE = "storage"
    OTHER = "other"


class BudgetCategory(str, Enum):
    """Budget allocation categories."""
    TRAINING = "training"          # Model training GPU time
    INFERENCE = "inference"        # Model serving
    OPERATIONS = "operations"      # VPS, storage, misc
    RESERVE = "reserve"            # Emergency fund
    REINVESTMENT = "reinvestment"  # Growing capabilities


class Transaction(BaseModel):
    """A single economic transaction."""
    id: str = Field(default_factory=lambda: f"tx-{int(time.time()*1000) % 1_000_000_000}")
    timestamp: float = Field(default_factory=time.time)
    type: TransactionType
    amount_usd: float
    source: str = ""  # RevenueSource or ExpenseCategory
    category: str = ""  # BudgetCategory
    description: str = ""
    telos_approved: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class BudgetState(BaseModel):
    """Current state of budget allocations."""
    training: float = 0.0
    inference: float = 0.0
    operations: float = 0.0
    reserve: float = 0.0
    reinvestment: float = 0.0

    @property
    def total(self) -> float:
        return self.training + self.inference + self.operations + self.reserve + self.reinvestment


class EconomicSnapshot(BaseModel):
    """Point-in-time economic summary."""
    timestamp: float = Field(default_factory=time.time)
    total_revenue: float = 0.0
    total_expenses: float = 0.0
    net_balance: float = 0.0
    budget: BudgetState = Field(default_factory=BudgetState)
    revenue_by_source: dict[str, float] = Field(default_factory=dict)
    expenses_by_category: dict[str, float] = Field(default_factory=dict)
    transaction_count: int = 0
    model_generations_funded: int = 0


class EconomicEngine:
    """Tracks all resource flows for dharma_swarm self-sustenance.

    Usage:
        engine = EconomicEngine()

        # Record revenue
        engine.record_revenue(0.001, RevenueSource.CRYPTO_MINING, "Mined 0.001 ETH")

        # Record expense
        engine.record_expense(1.50, ExpenseCategory.GPU_TRAINING, "RunPod A100 1hr")

        # Allocate budget
        engine.allocate_budget(BudgetCategory.TRAINING, 10.0)

        # Check if we can afford training
        if engine.can_afford_training(cost=50.0):
            engine.record_expense(50.0, ExpenseCategory.GPU_TRAINING, "Gen 1 training")

        # Get snapshot
        snap = engine.snapshot()
    """

    def __init__(self, storage_dir: Optional[Path] = None) -> None:
        self._storage_dir = storage_dir or _ECONOMICS_DIR
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._transactions: list[Transaction] = []
        self._budget = BudgetState()
        self._tx_file = self._storage_dir / "transactions.jsonl"
        self._budget_file = self._storage_dir / "budget.json"
        self._load()

    @property
    def balance(self) -> float:
        """Net balance (total revenue - total expenses)."""
        revenue = sum(t.amount_usd for t in self._transactions if t.type == TransactionType.REVENUE)
        expenses = sum(t.amount_usd for t in self._transactions if t.type == TransactionType.EXPENSE)
        return revenue - expenses

    @property
    def budget(self) -> BudgetState:
        return self._budget

    @property
    def transaction_count(self) -> int:
        return len(self._transactions)

    # -- Revenue -----------------------------------------------------------

    def record_revenue(
        self,
        amount_usd: float,
        source: RevenueSource,
        description: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> Transaction:
        """Record revenue earned by the system."""
        tx = Transaction(
            type=TransactionType.REVENUE,
            amount_usd=amount_usd,
            source=source.value,
            description=description,
            metadata=metadata or {},
        )
        self._transactions.append(tx)
        self._persist_tx(tx)

        # Auto-allocate revenue: 60% training, 20% operations, 10% reserve, 10% reinvestment
        self._budget.training += amount_usd * 0.6
        self._budget.operations += amount_usd * 0.2
        self._budget.reserve += amount_usd * 0.1
        self._budget.reinvestment += amount_usd * 0.1
        self._save_budget()

        logger.info("Revenue: +$%.4f from %s (%s)", amount_usd, source.value, description)
        return tx

    def record_api_savings(
        self,
        saved_usd: float,
        description: str = "Local model used instead of API",
    ) -> Transaction:
        """Record API cost savings from using local model.

        These savings count as revenue because they free up budget
        that would have been spent on API calls.
        """
        return self.record_revenue(
            saved_usd, RevenueSource.API_SAVINGS, description,
        )

    # -- Expenses ----------------------------------------------------------

    def record_expense(
        self,
        amount_usd: float,
        category: ExpenseCategory,
        description: str = "",
        budget_source: BudgetCategory = BudgetCategory.TRAINING,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Transaction:
        """Record an expense. Deducts from the specified budget category."""
        tx = Transaction(
            type=TransactionType.EXPENSE,
            amount_usd=amount_usd,
            source=category.value,
            category=budget_source.value,
            description=description,
            metadata=metadata or {},
        )
        self._transactions.append(tx)
        self._persist_tx(tx)

        # Deduct from budget
        current = getattr(self._budget, budget_source.value, 0.0)
        setattr(self._budget, budget_source.value, max(current - amount_usd, 0.0))
        self._save_budget()

        logger.info("Expense: -$%.4f for %s from %s (%s)",
                     amount_usd, category.value, budget_source.value, description)
        return tx

    # -- Budget management -------------------------------------------------

    def allocate_budget(
        self,
        category: BudgetCategory,
        amount_usd: float,
        from_category: BudgetCategory = BudgetCategory.REINVESTMENT,
    ) -> Transaction:
        """Move budget between categories."""
        # Deduct from source
        source_balance = getattr(self._budget, from_category.value, 0.0)
        actual = min(amount_usd, source_balance)
        setattr(self._budget, from_category.value, source_balance - actual)

        # Add to target
        target_balance = getattr(self._budget, category.value, 0.0)
        setattr(self._budget, category.value, target_balance + actual)

        tx = Transaction(
            type=TransactionType.ALLOCATION,
            amount_usd=actual,
            source=from_category.value,
            category=category.value,
            description=f"Allocate ${actual:.2f} from {from_category.value} to {category.value}",
        )
        self._transactions.append(tx)
        self._persist_tx(tx)
        self._save_budget()
        return tx

    def can_afford_training(self, cost: float) -> bool:
        """Check if training budget can cover a cost."""
        return self._budget.training >= cost

    def training_budget_available(self) -> float:
        """Get available training budget."""
        return self._budget.training

    # -- Snapshot ----------------------------------------------------------

    def snapshot(self) -> EconomicSnapshot:
        """Get current economic state."""
        revenue_by_source: dict[str, float] = {}
        expenses_by_category: dict[str, float] = {}
        total_revenue = 0.0
        total_expenses = 0.0

        for tx in self._transactions:
            if tx.type == TransactionType.REVENUE:
                total_revenue += tx.amount_usd
                revenue_by_source[tx.source] = revenue_by_source.get(tx.source, 0) + tx.amount_usd
            elif tx.type == TransactionType.EXPENSE:
                total_expenses += tx.amount_usd
                expenses_by_category[tx.source] = expenses_by_category.get(tx.source, 0) + tx.amount_usd

        return EconomicSnapshot(
            total_revenue=round(total_revenue, 4),
            total_expenses=round(total_expenses, 4),
            net_balance=round(total_revenue - total_expenses, 4),
            budget=self._budget,
            revenue_by_source=revenue_by_source,
            expenses_by_category=expenses_by_category,
            transaction_count=len(self._transactions),
        )

    # -- Persistence -------------------------------------------------------

    def _persist_tx(self, tx: Transaction) -> None:
        try:
            with open(self._tx_file, "a") as f:
                f.write(tx.model_dump_json() + "\n")
        except OSError:
            logger.warning("Failed to persist transaction", exc_info=True)

    def _save_budget(self) -> None:
        try:
            self._budget_file.write_text(self._budget.model_dump_json(indent=2))
        except OSError:
            logger.warning("Failed to save budget", exc_info=True)

    def _load(self) -> None:
        # Load transactions
        if self._tx_file.exists():
            try:
                with open(self._tx_file) as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                self._transactions.append(Transaction.model_validate_json(line))
                            except Exception:
                                continue
            except OSError:
                pass

        # Load budget
        if self._budget_file.exists():
            try:
                self._budget = BudgetState.model_validate_json(self._budget_file.read_text())
            except Exception:
                pass
