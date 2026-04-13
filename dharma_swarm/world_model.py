"""
DHARMA SWARM World Model

A system dynamics representation of the human-AI-biosphere coupled system.
This module defines the ontology, state storage, initial 2026 real-world data,
and the WorldModelAgent loop that continuously maintains it.
"""

from __future__ import annotations
import asyncio
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Any

StockDomain = Literal["biosphere", "human", "ai", "consciousness", "economic", "power"]
FlowDirection = Literal["inflow", "outflow", "transfer"]
LoopType = Literal["reinforcing", "balancing"]
Trajectory = Literal["rising", "falling", "oscillating", "critical", "unknown"]


@dataclass
class WorldStock:
    """A Forrester stock: an accumulation whose level matters."""
    id: str
    name: str
    domain: StockDomain
    current_value: float          # normalized 0-1 (0=depleted, 1=full/healthy)
    trajectory: Trajectory
    rate_of_change: float         # per year, normalized (-1 to +1)
    threshold_critical: float     # value below/above which system destabilizes
    telos_relevance: str          # DHARMA SWARM telos domain ID
    inflows: list[str] = field(default_factory=list)
    outflows: list[str] = field(default_factory=list)
    last_updated: str = ""
    evidence_sources: list[str] = field(default_factory=list)

@dataclass
class WorldFlow:
    """A dynamic rate variable connecting stocks."""
    id: str
    name: str
    direction: FlowDirection
    magnitude: float              # current rate, normalized 0-1
    driver_stocks: list[str] = field(default_factory=list)
    regulated_by: list[str] = field(default_factory=list)
    dharmic_alignment: float = 0.5  # 0-1: is this flow serving flourishing?
    agent_actionable: bool = False
    action_leverage: float = 0.0    # 0-1: how much can an agent move it?

@dataclass
class FeedbackLoop:
    """A causal cycle in the world system."""
    id: str
    name: str
    loop_type: LoopType
    nodes: list[str] = field(default_factory=list)
    current_strength: float = 0.5
    is_tipping_point_risk: bool = False
    intervention_points: list[str] = field(default_factory=list)
    telos_alignment: float = 0.5

@dataclass
class WorldModelState:
    """Complete world model snapshot. Immutable once written; new versions fork."""
    version: str
    timestamp: str
    stocks: dict[str, WorldStock] = field(default_factory=dict)
    flows: dict[str, WorldFlow] = field(default_factory=dict)
    feedback_loops: dict[str, FeedbackLoop] = field(default_factory=dict)
    telos_attractors: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    last_research_update: str = ""
    agent_action_queue: list[dict[str, Any]] = field(default_factory=list)

class WorldModelStore:
    """Persistence layer: ~/.dharma/world_model/ with versioned snapshots."""

    def __init__(self, base_path: Path | None = None):
        self.base = base_path or Path.home() / ".dharma" / "world_model"
        self.base.mkdir(parents=True, exist_ok=True)

    def save_snapshot(self, state: WorldModelState) -> Path:
        """Serializes and saves the world model state."""
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = self.base / f"snapshot_{ts}_{state.version}.json"
        
        state_dict = asdict(state)
        data = json.dumps(state_dict, indent=2)
        
        path.write_text(data)
        (self.base / "latest.json").write_text(data)
        return path

    def load_latest(self) -> WorldModelState | None:
        """Loads the most recent world model state if it exists."""
        latest = self.base / "latest.json"
        if not latest.exists():
            return None
            
        data = json.loads(latest.read_text())
        
        # Reconstruct dataclasses
        stocks = {k: WorldStock(**v) for k, v in data.get("stocks", {}).items()}
        flows = {k: WorldFlow(**v) for k, v in data.get("flows", {}).items()}
        loops = {k: FeedbackLoop(**v) for k, v in data.get("feedback_loops", {}).items()}
        
        state = WorldModelState(
            version=data.get("version", "0.0.0"),
            timestamp=data.get("timestamp", ""),
            stocks=stocks,
            flows=flows,
            feedback_loops=loops,
            telos_attractors=data.get("telos_attractors", []),
            confidence=data.get("confidence", 0.0),
            last_research_update=data.get("last_research_update", ""),
            agent_action_queue=data.get("agent_action_queue", [])
        )
        return state

def _build_initial_state() -> WorldModelState:
    """
    Constructs the seed state with real data from early 2026.
    Normalized values:
    S01: 429 ppm -> 0.28 (where 0 is 500ppm, 1 is 280ppm)
    S10: frontier models (GPT-5/Opus) approaching AGI capability
    S11: alignment lagging capability severely
    """
    ts = datetime.now(timezone.utc).isoformat()
    
    stocks = {
        "S01": WorldStock("S01", "Atmospheric CO2 Concentration", "biosphere", 0.28, "rising", -0.006, 0.15, "KALYAN", last_updated=ts, evidence_sources=["NOAA 2026 (429.35 ppm)"]),
        "S02": WorldStock("S02", "Ocean pH (Surface)", "biosphere", 0.35, "falling", -0.015, 0.20, "KALYAN", last_updated=ts),
        "S03": WorldStock("S03", "Terrestrial Biodiversity", "biosphere", 0.31, "falling", -0.025, 0.20, "KALYAN", last_updated=ts),
        "S04": WorldStock("S04", "Forest Cover", "biosphere", 0.65, "falling", -0.005, 0.50, "KALYAN", last_updated=ts),
        "S05": WorldStock("S05", "Freshwater Availability", "biosphere", 0.40, "falling", -0.012, 0.30, "KALYAN", last_updated=ts),
        "S06": WorldStock("S06", "Topsoil Depth", "biosphere", 0.50, "falling", -0.010, 0.30, "KALYAN", last_updated=ts),
        "S07": WorldStock("S07", "Global Social Trust", "human", 0.34, "falling", -0.005, 0.25, "NOOSPHERE", last_updated=ts),
        "S08": WorldStock("S08", "Wealth Equality", "human", 0.35, "falling", -0.008, 0.25, "KALYAN", last_updated=ts),
        "S09": WorldStock("S09", "Democratic Governance", "human", 0.45, "oscillating", -0.003, 0.35, "NOOSPHERE", last_updated=ts),
        "S10": WorldStock("S10", "AI Capability Level", "ai", 0.55, "rising", 0.10, 0.90, "SHAKTI", last_updated=ts, evidence_sources=["METR 2026 Task Completion Horizon"]),
        "S11": WorldStock("S11", "AI Alignment Maturity", "ai", 0.15, "rising", 0.03, 0.10, "VIVEKA", last_updated=ts),
        "S12": WorldStock("S12", "Autonomous Agent Density", "ai", 0.30, "rising", 0.15, 0.60, "SHAKTI", last_updated=ts),
        "S13": WorldStock("S13", "Human Wisdom/Contemplation", "consciousness", 0.10, "unknown", 0.01, 0.05, "VIVEKA", last_updated=ts),
        "S14": WorldStock("S14", "Renewable Energy Share", "economic", 0.35, "rising", 0.025, 0.50, "KALYAN", last_updated=ts),
        "S15": WorldStock("S15", "Military AI Autonomy", "power", 0.40, "rising", 0.08, 0.70, "SHAKTI", last_updated=ts)
    }
    
    flows = {
        "F01": WorldFlow("F01", "Fossil Fuel Emissions", "outflow", 0.75, ["S14"], [], 0.05, True, 0.3),
        "F02": WorldFlow("F02", "AI Compute Scaling", "inflow", 0.85, ["S10"], [], 0.40, False, 0.1),
        "F03": WorldFlow("F03", "Alignment Research", "inflow", 0.20, ["S10"], ["S11"], 0.95, True, 0.6),
        "F04": WorldFlow("F04", "Deforestation Rate", "outflow", 0.35, [], ["S04"], 0.05, True, 0.3),
        "F05": WorldFlow("F05", "Trust Erosion", "outflow", 0.60, ["S08"], ["S07"], 0.05, True, 0.4),
        "F06": WorldFlow("F06", "Agent Deployment", "inflow", 0.70, ["S10"], ["S12"], 0.30, False, 0.2),
        "F07": WorldFlow("F07", "Military AI Investment", "inflow", 0.65, ["S10", "S07"], ["S15"], 0.05, False, 0.1),
        "F08": WorldFlow("F08", "Renewable Deployment", "inflow", 0.45, ["S14"], ["S01"], 0.85, True, 0.3)
    }
    
    loops = {
        "L01": FeedbackLoop("L01", "Capability-Displacement-Instability", "reinforcing", ["S10", "S07", "S12"], 0.75, True, ["F06"], 0.15),
        "L02": FeedbackLoop("L02", "Carbon-Warming-Permafrost", "reinforcing", ["S01", "S04"], 0.80, True, ["F01", "F04"], 0.10),
        "L03": FeedbackLoop("L03", "AI Capability-Alignment Gap", "reinforcing", ["S10", "S11"], 0.85, True, ["F03"], 0.15),
        "L04": FeedbackLoop("L04", "Inequality-Distrust-Capture", "reinforcing", ["S08", "S07"], 0.70, True, ["F05"], 0.10),
        "L05": FeedbackLoop("L05", "Military AI-Arms Race", "reinforcing", ["S15", "S10", "S07"], 0.80, True, ["F07"], 0.05),
        "L06": FeedbackLoop("L06", "Renewable Scaling", "balancing", ["S14", "S01"], 0.40, False, ["F08"], 0.85)
    }
    
    return WorldModelState(
        version="0.1.0",
        timestamp=ts,
        stocks=stocks,
        flows=flows,
        feedback_loops=loops,
        confidence=0.6,
        last_research_update=ts
    )

INITIAL_WORLD_STATE = _build_initial_state()


def query_world_model(question: str) -> list[WorldStock | WorldFlow]:
    """
    Simple semantic match over the world model.
    In full implementation, uses memory_palace and LanceDB.
    """
    question_lower = question.lower()
    results: list[WorldStock | WorldFlow] = []
    
    for stock in INITIAL_WORLD_STATE.stocks.values():
        if question_lower in stock.name.lower() or question_lower in stock.domain.lower():
            results.append(stock)
            
    for flow in INITIAL_WORLD_STATE.flows.values():
        if question_lower in flow.name.lower():
            results.append(flow)
            
    return results

def update_stock(stock_id: str, new_value: float, evidence: list[str], source_url: str) -> dict[str, Any]:
    """
    Update a stock's value based on new research.
    Records evidence trail.
    """
    state = INITIAL_WORLD_STATE  # In real implementation, pass current state
    if stock_id not in state.stocks:
        raise ValueError(f"Stock {stock_id} not found")
        
    stock = state.stocks[stock_id]
    old_value = stock.current_value
    
    stock.current_value = new_value
    stock.last_updated = datetime.now(timezone.utc).isoformat()
    stock.evidence_sources.extend(evidence)
    stock.evidence_sources.append(source_url)
    
    # Simple trajectory inference
    if new_value > old_value + 0.01:
        stock.trajectory = "rising"
    elif new_value < old_value - 0.01:
        stock.trajectory = "falling"
        
    return {
        "stock_id": stock_id,
        "old_value": old_value,
        "new_value": new_value,
        "trajectory": stock.trajectory
    }

def assess_action_impact(action_description: str) -> dict[str, Any]:
    """
    Pre-action check to estimate how an agent's proposed action
    impacts the core structural stocks.
    """
    # Mock LLM/heuristic evaluation
    return {
        "action": action_description,
        "affected_stocks": {},  # Would contain e.g. {"S10": +0.02}
        "dharmic_alignment_score": 0.5,
        "recommendation": "review"
    }

def get_telos_pressure() -> dict[str, Any]:
    """
    Evaluates which stocks are closest to their critical thresholds,
    generating 'algedonic' (pain/alarm) pressure for the Swarm to prioritize.
    """
    pressures = {}
    for sid, stock in INITIAL_WORLD_STATE.stocks.items():
        # simplified check: distance to threshold based on trajectory
        if stock.trajectory == "falling" and stock.current_value < stock.threshold_critical + 0.1:
            pressures[sid] = {"name": stock.name, "severity": "high"}
        elif stock.trajectory == "rising" and stock.current_value > stock.threshold_critical - 0.1:
            pressures[sid] = {"name": stock.name, "severity": "high"}
            
    return pressures

class WorldModelAgent:
    """
    The 18th asyncio loop. Runs continuously to research stock values,
    detect loop anomalies, and update the Swarm's structural understanding.
    """
    
    def __init__(self, store: WorldModelStore, search_tool: Any, arxiv_tool: Any):
        self.store = store
        self.search = search_tool
        self.arxiv = arxiv_tool
        self._state: WorldModelState | None = None
        
    async def boot(self) -> None:
        """Load state from disk or initialize from seed."""
        self._state = self.store.load_latest() or INITIAL_WORLD_STATE
        
    async def run_loop(self) -> None:
        """Main execution cycle: research stocks, evaluate loops, sleep."""
        await self.boot()
        
        while True:
            # 1. Update stale stocks (simplified logic)
            # Find oldest updated stock
            if self._state:
                stale_stocks = sorted(
                    self._state.stocks.values(), 
                    key=lambda s: s.last_updated
                )
                
                # Mock update cycle
                for stock in stale_stocks[:2]:
                    # await self.search.query(f"{stock.name} current status 2026")
                    pass
                    
            # 2. Re-evaluate loops (check predictions vs reality)
            # 3. Sleep
            await asyncio.sleep(3600)  # Check hourly

