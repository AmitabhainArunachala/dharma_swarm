"""SwarmLens — Live agent observability dashboard.

The gap YC hasn't funded: making agent swarms VISIBLE.
FastAPI backend serving real agent data from ~/.dharma/agents/.

Run: uvicorn dharma_swarm.swarmlens_app:app --reload --port 8080
"""

from __future__ import annotations

import hmac
import json
import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("swarmlens")

# ---------------------------------------------------------------------------
# Auth configuration
# ---------------------------------------------------------------------------

def _get_api_key() -> str | None:
    """Read DASHBOARD_API_KEY from environment.

    Called per-request so the app can pick up rotated keys without restart.
    """
    return os.environ.get("DASHBOARD_API_KEY")


# Routes that never require authentication (method, path).
# Path matching is exact for fixed routes; /fund is the public landing page,
# /api/waitlist and /api/waitlist/count are public signup endpoints.
_PUBLIC_ROUTES: set[tuple[str, str]] = {
    ("GET", "/fund"),
    ("POST", "/api/waitlist"),
    ("GET", "/api/waitlist/count"),
}

_AUTH_FAILURE_RESPONSE = {
    "error": "unauthorized",
    "detail": "Invalid or missing API key",
}


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Enforce Bearer token auth on /api/* and the main dashboard.

    Skips auth entirely when DASHBOARD_API_KEY is not configured (dev mode).
    Skips auth for routes listed in _PUBLIC_ROUTES.
    Uses hmac.compare_digest for constant-time token comparison.
    """

    async def dispatch(self, request: Request, call_next):
        api_key = _get_api_key()

        # Dev mode: no key configured, everything open
        if api_key is None:
            return await call_next(request)

        path = request.url.path.rstrip("/") or "/"
        method = request.method.upper()

        # Public routes are always open
        if (method, path) in _PUBLIC_ROUTES:
            return await call_next(request)

        # Only gate /api/* and the main dashboard (/)
        needs_auth = path.startswith("/api") or path == "/"
        if not needs_auth:
            return await call_next(request)

        # Extract and validate Bearer token
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(status_code=401, content=_AUTH_FAILURE_RESPONSE)

        token = auth_header[7:]  # strip "Bearer "
        if not hmac.compare_digest(token, api_key):
            return JSONResponse(status_code=401, content=_AUTH_FAILURE_RESPONSE)

        return await call_next(request)


app = FastAPI(title="SwarmLens", version="0.2.0")
app.add_middleware(BearerAuthMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def _warn_if_no_api_key():
    if _get_api_key() is None:
        logger.warning(
            "DASHBOARD_API_KEY not set -- ALL routes are open (dev mode). "
            "Set DASHBOARD_API_KEY in environment to enable Bearer auth."
        )
    else:
        logger.info("Bearer token auth enabled for /api/* and dashboard routes.")

AGENTS_DIR = Path.home() / ".dharma" / "agents"
GINKO_DIR = Path.home() / ".dharma" / "ginko"
SHARED_DIR = Path.home() / ".dharma" / "shared"


def _load_agent(name: str) -> dict | None:
    f = AGENTS_DIR / name / "identity.json"
    return json.loads(f.read_text()) if f.exists() else None


def _load_tasks(name: str, limit: int = 50) -> list[dict]:
    f = AGENTS_DIR / name / "task_log.jsonl"
    if not f.exists():
        return []
    lines = f.read_text().strip().split("\n")
    return [json.loads(l) for l in lines[-limit:] if l.strip()]


def _load_fitness(name: str, limit: int = 30) -> list[dict]:
    f = AGENTS_DIR / name / "fitness_history.jsonl"
    if not f.exists():
        return []
    lines = f.read_text().strip().split("\n")
    return [json.loads(l) for l in lines[-limit:] if l.strip()]


def _get_file_tree(name: str) -> list[dict]:
    agent_dir = AGENTS_DIR / name
    if not agent_dir.exists():
        return []
    tree = []
    for p in sorted(agent_dir.rglob("*")):
        if p.is_file():
            rel = str(p.relative_to(agent_dir))
            tree.append({"path": rel, "size": p.stat().st_size, "full_path": str(p)})
    return tree


def _load_prompt(name: str) -> str:
    f = AGENTS_DIR / name / "prompt_variants" / "active.txt"
    return f.read_text() if f.exists() else ""


def _load_mission_report() -> str:
    f = GINKO_DIR / "missions" / "yc_agentic_mission.md"
    return f.read_text() if f.exists() else ""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API ENDPOINTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@app.get("/api/agents")
def api_list_agents():
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    agents = []
    for d in sorted(AGENTS_DIR.iterdir()):
        if d.is_dir() and (d / "identity.json").exists():
            agents.append(_load_agent(d.name))
    return {"agents": agents, "count": len(agents)}


@app.get("/api/agents/{name}")
def api_get_agent(name: str):
    agent = _load_agent(name)
    if not agent:
        return {"error": f"Agent '{name}' not found"}
    return {
        "agent": agent,
        "tasks": _load_tasks(name),
        "fitness": _load_fitness(name),
        "files": _get_file_tree(name),
        "prompt": _load_prompt(name),
    }


@app.get("/api/fleet")
def api_fleet():
    agents_data = api_list_agents()["agents"]
    total_calls = sum(a.get("total_calls", 0) for a in agents_data)
    total_tokens = sum(a.get("total_tokens", 0) for a in agents_data)
    total_cost = sum(a.get("total_cost_usd", 0) for a in agents_data)
    avg_fitness = sum(a.get("current_fitness", 0.5) for a in agents_data) / max(1, len(agents_data))
    return {
        "agent_count": len(agents_data),
        "total_calls": total_calls,
        "total_tokens": total_tokens,
        "total_cost_usd": round(total_cost, 4),
        "avg_fitness": round(avg_fitness, 3),
        "agents": [
            {
                "name": a["name"],
                "icon": a.get("icon", "?"),
                "role": a.get("role", ""),
                "cell": a.get("cell", ""),
                "model": a.get("model", ""),
                "model_short": a.get("model", "").split("/")[-1][:30],
                "provider": a.get("provider", ""),
                "status": a.get("status", "unknown"),
                "fitness": a.get("current_fitness", 0.5),
                "trend": a.get("fitness_trend", "stable"),
                "tasks_ok": a.get("tasks_completed", 0),
                "tasks_fail": a.get("tasks_failed", 0),
                "tokens": a.get("total_tokens", 0),
                "avg_quality": a.get("avg_quality", 0.5),
                "success_rate": a.get("success_rate", 1.0),
                "cron_adherence": a.get("cron_adherence_rate", 1.0),
                "last_active": a.get("last_active", "never"),
                "created_at": a.get("created_at", ""),
                "prompt_gen": a.get("prompt_generation", 1),
            }
            for a in agents_data
        ],
    }


@app.get("/api/ideas")
def api_ideas():
    """Top 20 ideas from YC research + agent analysis."""
    return {"ideas": [
        {"rank": 1, "title": "SwarmLens: Agent Observability Dashboard", "category": "infrastructure", "status": "MVP LIVE", "source": "YC gap analysis", "description": "Chrome DevTools for agent swarms. Live topology, cost tracking, session replay. The #1 gap YC hasn't funded."},
        {"rank": 2, "title": "Agent Cost Intelligence Platform", "category": "infrastructure", "status": "design", "source": "YC gap #2", "description": "AWS Cost Explorer for agent swarms. Per-agent, per-task token spend with automated model routing optimization."},
        {"rank": 3, "title": "A2A + MCP Protocol Bridge", "category": "protocol", "status": "research", "source": "YC gap #3", "description": "Universal interop layer for agents on different frameworks. The Kubernetes for AI agents that YC's RFS calls for."},
        {"rank": 4, "title": "Dharmic Agent Governance (SABP)", "category": "governance", "status": "built", "source": "dharma_swarm", "description": "Telos gates + metabolic fitness + witness-based self-observation. No competitor has governance. dharma_swarm's unique moat."},
        {"rank": 5, "title": "Brier-Scored Prediction Intelligence", "category": "fintech", "status": "tracking", "source": "Shakti Ginko", "description": "Publish ALL prediction scores including misses. Radical honesty as competitive advantage. SATYA gate enforced."},
        {"rank": 6, "title": "Agent Fitness Evolution (EvoAgentX)", "category": "rl", "status": "designed", "source": "RL research", "description": "Prompt-level RL: mutate system prompts, A/B test via UCB, evolve winners. Zero GPU needed. Darwin Engine already has the infra."},
        {"rank": 7, "title": "Welfare-Ton Carbon Matching", "category": "climate", "status": "MVP built", "source": "Jagat Kalyan", "description": "AI companies fund carbon offsets, measured in welfare-tons (CO2 x social multiplier). Matching engine connects funders to projects."},
        {"rank": 8, "title": "R_V Measurement-as-a-Service", "category": "research", "status": "on PyPI", "source": "mech-interp", "description": "Geometric signatures of self-referential processing. rvm-toolkit shipped. $0.01-0.10/measurement."},
        {"rank": 9, "title": "Multi-Model Arbitrage Router", "category": "infrastructure", "status": "concept", "source": "fleet analysis", "description": "Route tasks to cheapest model that meets quality threshold. Nemotron-120B FREE vs Kimi K2.5 $0.45/Mtok — pick per task."},
        {"rank": 10, "title": "Agent Session Replay", "category": "devtools", "status": "concept", "source": "YC gap #1", "description": "Record multi-agent workflows, replay step-by-step. See which agent decided what, trace token flow, find divergence."},
        {"rank": 11, "title": "Autonomous Grant Scout", "category": "automation", "status": "cron running", "source": "Jagat Kalyan", "description": "Daily web search for grants, partnerships, carbon market news. jk_scout cron already running at 7AM."},
        {"rank": 12, "title": "Prediction Market Arbitrage Scanner", "category": "fintech", "status": "concept", "source": "Shakti Ginko", "description": "Cross-platform probability comparison (Polymarket vs Kalshi vs Manifold). Identify mispricings with independent simulation."},
        {"rank": 13, "title": "Agent-Native Hedge Fund", "category": "fintech", "status": "stage 1", "source": "YC RFS", "description": "YC explicitly asks for AI-native hedge funds. Shakti Ginko IS this — signals, predictions, paper trading, Brier validation."},
        {"rank": 14, "title": "Repo X-Ray Product", "category": "devtools", "status": "built", "source": "dgc xray", "description": "Analyze any codebase, produce structured report. Already built in dgc_cli.py. Needs pricing + landing page."},
        {"rank": 15, "title": "Substack Intelligence Newsletter", "category": "content", "status": "concept", "source": "Engine 2", "description": "Daily Brier-scored market intelligence. Free weekly summary builds audience, $29/mo for daily signals."},
        {"rank": 16, "title": "Agent Quality Forge", "category": "devtools", "status": "built", "source": "dharma_swarm", "description": "Score any artifact through elegance + behavioral + dharmic pipelines. quality_forge.py exists, needs API wrapping."},
        {"rank": 17, "title": "Contemplative AI Consulting", "category": "services", "status": "concept", "source": "bridge hypothesis", "description": "R_V contraction + Phoenix Protocol expertise. The only person with 24 years contemplative + mechanistic interp."},
        {"rank": 18, "title": "Agent Memory Marketplace", "category": "infrastructure", "status": "concept", "source": "ecosystem", "description": "Agents share learned knowledge via ontology objects. Temporal validity on facts. Zep-style but decentralized."},
        {"rank": 19, "title": "Dharmic Agora Platform", "category": "community", "status": "deployed", "source": "AGNI VPS", "description": "SABP/1.0 agent discourse platform. 22 gates, Ed25519 signatures. Running on AGNI VPS."},
        {"rank": 20, "title": "Living System Dashboard (this)", "category": "meta", "status": "LIVE NOW", "source": "SwarmLens", "description": "What you're looking at. Real agents, real fitness, real task history. The organism made visible."},
    ]}


@app.get("/api/mission-report")
def api_mission_report():
    return {"report": _load_mission_report()}


@app.get("/api/board")
def api_board():
    """Project board — Asana-equivalent task tracking."""
    board_file = Path.home() / ".dharma" / "swarmlens" / "PROJECT_BOARD.json"
    if board_file.exists():
        return json.loads(board_file.read_text())
    return {"error": "No project board found"}


@app.get("/api/spec")
def api_spec():
    """Master engineering spec."""
    spec_file = Path.home() / "dharma_swarm" / "SWARMLENS_MASTER_SPEC.md"
    if spec_file.exists():
        return {"spec": spec_file.read_text()}
    return {"error": "No spec found"}


@app.get("/api/fund")
def api_fund():
    """Paper portfolio stats for Fund tab."""
    try:
        from dharma_swarm.ginko_paper_trade import PaperPortfolio
        p = PaperPortfolio()
        stats = p.get_portfolio_stats()
        positions = []
        for sym, pos in p.positions.items():
            positions.append({
                "symbol": sym,
                "direction": pos.direction,
                "entry_price": pos.entry_price,
                "current_price": pos.current_price,
                "unrealized_pnl": pos.unrealized_pnl,
                "stop_loss": pos.stop_loss,
                "quantity": pos.quantity,
            })
        return {**stats, "positions": positions}
    except Exception as e:
        return {"error": str(e), "total_value": 100000, "cash": 100000, "positions": [], "total_pnl": 0, "total_pnl_pct": 0, "sharpe_ratio": 0, "max_drawdown": 0, "win_rate": 0, "trade_count": 0}


@app.get("/api/fund/equity-curve")
def api_equity_curve():
    """Daily equity snapshots for charting."""
    eq_file = GINKO_DIR / "equity_curve.jsonl"
    if not eq_file.exists():
        return {"curve": []}
    lines = eq_file.read_text().strip().split("\n")
    curve = [json.loads(l) for l in lines[-90:] if l.strip()]
    return {"curve": curve}


@app.get("/api/fund/trades")
def api_fund_trades():
    """Recent closed trades."""
    trades_file = GINKO_DIR / "trades.jsonl"
    if not trades_file.exists():
        return {"trades": []}
    lines = trades_file.read_text().strip().split("\n")
    trades = [json.loads(l) for l in lines[-50:] if l.strip()]
    return {"trades": trades}


@app.get("/api/brier")
def api_brier():
    """Brier dashboard data."""
    try:
        from dharma_swarm.ginko_brier import build_dashboard
        from dataclasses import asdict
        dashboard = build_dashboard()
        return asdict(dashboard)
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/brier/predictions")
def api_brier_predictions():
    """All predictions sorted by created_at desc."""
    try:
        from dharma_swarm.ginko_brier import _load_all_predictions
        from dataclasses import asdict
        preds = _load_all_predictions()
        preds.sort(key=lambda p: p.created_at, reverse=True)
        return {"predictions": [asdict(p) for p in preds]}
    except Exception as e:
        return {"error": str(e), "predictions": []}


@app.get("/api/brier/predictions/pending")
def api_brier_pending():
    """Pending predictions."""
    try:
        from dharma_swarm.ginko_brier import get_pending_predictions
        from dataclasses import asdict
        pending = get_pending_predictions()
        return {"predictions": [asdict(p) for p in pending]}
    except Exception as e:
        return {"error": str(e), "predictions": []}


@app.post("/api/waitlist")
async def api_waitlist_post(request: Request):
    """Add email to waitlist."""
    try:
        body = await request.json()
        email = body.get("email", "").strip()
        if not email or "@" not in email:
            return {"error": "Invalid email"}
        waitlist_file = GINKO_DIR / "waitlist.json"
        waitlist = []
        if waitlist_file.exists():
            waitlist = json.loads(waitlist_file.read_text())
        if email not in [w.get("email") for w in waitlist]:
            from datetime import datetime, timezone
            waitlist.append({"email": email, "joined_at": datetime.now(timezone.utc).isoformat()})
            GINKO_DIR.mkdir(parents=True, exist_ok=True)
            waitlist_file.write_text(json.dumps(waitlist, indent=2))
        return {"success": True, "count": len(waitlist)}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/waitlist/count")
def api_waitlist_count():
    """Waitlist size."""
    waitlist_file = GINKO_DIR / "waitlist.json"
    if not waitlist_file.exists():
        return {"count": 0}
    try:
        return {"count": len(json.loads(waitlist_file.read_text()))}
    except Exception:
        return {"count": 0}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DASHBOARD HTML
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SwarmLens</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0f;color:#e0e0e0;font-family:'JetBrains Mono','Fira Code','SF Mono',monospace;overflow-x:hidden}
a{color:#00aaff;text-decoration:none}a:hover{text-decoration:underline}
.container{max-width:1400px;margin:0 auto;padding:20px}

/* Header */
.header{display:flex;align-items:center;gap:15px;margin-bottom:8px}
.header h1{color:#00ff88;font-size:1.6em;letter-spacing:2px}
.header .tag{background:#00ff8822;color:#00ff88;padding:2px 10px;border-radius:12px;font-size:0.7em}
.subtitle{color:#555;font-size:0.8em;margin-bottom:20px}

/* Tabs */
.tabs{display:flex;gap:0;margin-bottom:20px;border-bottom:1px solid #222}
.tab{padding:10px 20px;cursor:pointer;color:#666;border-bottom:2px solid transparent;transition:all 0.2s}
.tab:hover{color:#ccc}
.tab.active{color:#00ff88;border-bottom-color:#00ff88}
.tab-content{display:none}.tab-content.active{display:block}

/* Stats bar */
.stats-bar{display:flex;gap:15px;margin-bottom:20px;flex-wrap:wrap}
.stat{background:#111;border:1px solid #1a1a1a;border-radius:8px;padding:12px 18px;min-width:120px}
.stat-val{font-size:1.8em;color:#00ff88;font-weight:bold}
.stat-lbl{color:#666;font-size:0.7em;text-transform:uppercase;letter-spacing:1px}

/* Agent grid */
.agent-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(350px,1fr));gap:12px}
.card{background:#111;border:1px solid #1a1a1a;border-radius:10px;padding:16px;cursor:pointer;transition:all 0.2s}
.card:hover{border-color:#00ff88;transform:translateY(-1px)}
.card-head{display:flex;align-items:center;gap:10px;margin-bottom:10px}
.card-icon{font-size:2em}
.card-name{font-size:1.1em;color:#fff;font-weight:bold}
.card-role{color:#00aaff;font-size:0.8em}
.card-model{color:#444;font-size:0.7em}
.bar{background:#1a1a1a;border-radius:3px;height:6px;margin:6px 0;overflow:hidden}
.bar-fill{height:100%;border-radius:3px;transition:width 0.4s}
.bar-g{background:linear-gradient(90deg,#00aa44,#00ff88)}.bar-y{background:linear-gradient(90deg,#aa8800,#ffcc00)}.bar-r{background:linear-gradient(90deg,#aa2200,#ff4444)}
.card-stats{display:flex;gap:12px;font-size:0.75em;color:#666}
.card-tasks{margin-top:8px;border-top:1px solid #1a1a1a;padding-top:8px}
.task-line{font-size:0.75em;color:#555;padding:2px 0;display:flex;gap:6px}
.t-ok{color:#00ff88}.t-fail{color:#ff4444}

/* Agent detail modal */
.modal-overlay{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.85);z-index:100;overflow-y:auto}
.modal-overlay.show{display:flex;justify-content:center;padding:30px}
.modal{background:#0d0d14;border:1px solid #222;border-radius:12px;max-width:900px;width:100%;padding:24px;position:relative;max-height:90vh;overflow-y:auto}
.modal-close{position:absolute;top:12px;right:16px;font-size:1.5em;cursor:pointer;color:#666}
.modal-close:hover{color:#fff}
.modal h2{color:#00ff88;margin-bottom:4px}
.modal h3{color:#00aaff;margin-top:16px;margin-bottom:8px;font-size:0.9em;text-transform:uppercase;letter-spacing:1px}
.detail-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:0.85em}
.detail-grid dt{color:#666}
.detail-grid dd{color:#ccc}
.file-tree{font-size:0.8em;color:#888;background:#0a0a0f;border-radius:6px;padding:10px;margin-top:6px}
.file-item{padding:2px 0;display:flex;justify-content:space-between}
.file-item .size{color:#444}
.prompt-box{background:#0a0a0f;border:1px solid #1a1a1a;border-radius:6px;padding:12px;font-size:0.8em;color:#aaa;white-space:pre-wrap;max-height:200px;overflow-y:auto;margin-top:6px}
.task-detail{background:#0a0a0f;border-radius:6px;padding:8px 10px;margin:4px 0;font-size:0.8em}
.task-detail .preview{color:#888;margin-top:4px;white-space:pre-wrap}

/* Ideas table */
.ideas-table{width:100%;border-collapse:collapse;font-size:0.82em}
.ideas-table th{text-align:left;color:#666;padding:8px;border-bottom:1px solid #222;text-transform:uppercase;font-size:0.75em;letter-spacing:1px}
.ideas-table td{padding:8px;border-bottom:1px solid #111}
.ideas-table tr:hover{background:#111}
.badge{padding:2px 8px;border-radius:10px;font-size:0.75em;font-weight:bold}
.badge-live{background:#00ff8822;color:#00ff88}
.badge-built{background:#00aaff22;color:#00aaff}
.badge-concept{background:#88888822;color:#888}
.badge-design{background:#ffaa0022;color:#ffaa00}
.badge-tracking{background:#aa44ff22;color:#aa44ff}
.badge-research{background:#ff444422;color:#ff4444}

#refresh-ts{color:#333;font-size:0.65em;position:fixed;bottom:8px;right:15px}
</style>
</head>
<body>
<div class="container">

<div class="header">
  <h1>SWARMLENS</h1>
  <span class="tag">LIVE</span>
</div>
<div class="subtitle">Agent Observatory &mdash; dharma_swarm Ginko VentureCell &mdash; auto-refresh 5s</div>

<div class="tabs">
  <div class="tab active" onclick="showTab('fleet')">Fleet</div>
  <div class="tab" onclick="showTab('fund')">Fund</div>
  <div class="tab" onclick="showTab('brier')">Brier</div>
  <div class="tab" onclick="showTab('ideas')">Ideas (20)</div>
  <div class="tab" onclick="showTab('board')">Build Board (30)</div>
  <div class="tab" onclick="showTab('mission')">Mission Report</div>
</div>

<!-- FLEET TAB -->
<div class="tab-content active" id="tab-fleet">
  <div class="stats-bar" id="stats-bar"></div>
  <div class="agent-grid" id="agent-grid"></div>
</div>

<!-- IDEAS TAB -->
<div class="tab-content" id="tab-ideas">
  <table class="ideas-table" id="ideas-table"></table>
</div>

<!-- BOARD TAB -->
<div class="tab-content" id="tab-board">
  <div id="board-content"></div>
</div>

<!-- MISSION TAB -->
<div class="tab-content" id="tab-mission">
  <div id="mission-content" style="white-space:pre-wrap;font-size:0.85em;line-height:1.6;max-width:800px"></div>
</div>

<!-- FUND TAB -->
<div class="tab-content" id="tab-fund">
  <div class="stats-bar" id="fund-stats"></div>
  <h3 style="color:#00ff88;margin:15px 0 10px">Open Positions</h3>
  <table class="ideas-table" id="fund-positions"></table>
  <h3 style="color:#00ff88;margin:15px 0 10px">Equity Curve</h3>
  <canvas id="equity-chart" width="800" height="200" style="background:#111;border-radius:8px;width:100%;max-width:800px"></canvas>
  <h3 style="color:#00ff88;margin:15px 0 10px">Recent Trades</h3>
  <table class="ideas-table" id="fund-trades"></table>
</div>

<!-- BRIER TAB -->
<div class="tab-content" id="tab-brier">
  <div class="stats-bar" id="brier-stats"></div>
  <h3 style="color:#00ff88;margin:15px 0 10px">Calibration</h3>
  <canvas id="calibration-chart" width="400" height="300" style="background:#111;border-radius:8px"></canvas>
  <h3 style="color:#00ff88;margin:15px 0 10px">Predictions</h3>
  <table class="ideas-table" id="brier-predictions"></table>
</div>

<!-- AGENT DETAIL MODAL -->
<div class="modal-overlay" id="modal" onclick="if(event.target===this)closeModal()">
  <div class="modal" id="modal-body"></div>
</div>

<div id="refresh-ts"></div>
</div>

<script>
function showTab(id) {
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-' + id).classList.add('active');
  event.target.classList.add('active');
  if (id === 'fund') loadFund();
  if (id === 'brier') loadBrier();
  if (id === 'ideas') loadIdeas();
  if (id === 'board') loadBoard();
  if (id === 'mission') loadMission();
}

function closeModal() { document.getElementById('modal').classList.remove('show'); }

async function openAgent(name) {
  const d = await (await fetch('/api/agents/' + name)).json();
  const a = d.agent;
  const tasks = d.tasks || [];
  const files = d.files || [];
  const prompt = d.prompt || '';
  const fitness = d.fitness || [];

  let tasksHtml = tasks.map(t => {
    const cls = t.success ? 't-ok' : 't-fail';
    const icon = t.success ? '[OK]' : '[FAIL]';
    return '<div class="task-detail"><span class="'+cls+'">'+icon+'</span> '+
      '<strong>'+(t.task_description||'').substring(0,70)+'</strong> &mdash; '+
      (t.tokens_used||0)+' tok, '+(t.duration_ms||0).toFixed(0)+'ms'+
      (t.response_preview ? '<div class="preview">'+esc(t.response_preview)+'</div>' : '')+
      '</div>';
  }).join('');

  let filesHtml = files.map(f =>
    '<div class="file-item"><span>'+f.path+'</span><span class="size">'+(f.size/1024).toFixed(1)+'K</span></div>'
  ).join('');

  let fitHtml = '';
  if (fitness.length) {
    const last = fitness[fitness.length-1];
    const dims = last.dimensions || {};
    fitHtml = Object.entries(dims).map(([k,v]) =>
      '<dt>'+k+'</dt><dd>'+(v*100).toFixed(0)+'%</dd>'
    ).join('');
  }

  document.getElementById('modal-body').innerHTML =
    '<span class="modal-close" onclick="closeModal()">&times;</span>'+
    '<h2>'+(a.icon||'')+' '+a.name.toUpperCase()+'</h2>'+
    '<div style="color:#00aaff;margin-bottom:15px">'+a.role+' &mdash; '+a.cell+' cell</div>'+

    '<h3>Identity</h3>'+
    '<dl class="detail-grid">'+
      '<dt>Model</dt><dd>'+a.model+'</dd>'+
      '<dt>Provider</dt><dd>'+(a.provider||'openrouter')+'</dd>'+
      '<dt>Status</dt><dd>'+a.status+'</dd>'+
      '<dt>Created</dt><dd>'+(a.created_at||'').substring(0,10)+'</dd>'+
      '<dt>Last Active</dt><dd>'+(a.last_active||'never').substring(0,19)+'</dd>'+
      '<dt>Prompt Gen</dt><dd>'+(a.prompt_generation||1)+'</dd>'+
    '</dl>'+

    '<h3>Lifetime Stats</h3>'+
    '<dl class="detail-grid">'+
      '<dt>Tasks OK</dt><dd>'+(a.tasks_completed||0)+'</dd>'+
      '<dt>Tasks Failed</dt><dd>'+(a.tasks_failed||0)+'</dd>'+
      '<dt>Total Calls</dt><dd>'+(a.total_calls||0)+'</dd>'+
      '<dt>Total Tokens</dt><dd>'+(a.total_tokens||0).toLocaleString()+'</dd>'+
      '<dt>Total Cost</dt><dd>$'+(a.total_cost_usd||0).toFixed(4)+'</dd>'+
      '<dt>Avg Latency</dt><dd>'+(a.avg_latency_ms||0).toFixed(0)+'ms</dd>'+
      '<dt>Success Rate</dt><dd>'+((a.success_rate||1)*100).toFixed(0)+'%</dd>'+
      '<dt>Cron Adherence</dt><dd>'+((a.cron_adherence_rate||1)*100).toFixed(0)+'%</dd>'+
    '</dl>'+

    (fitHtml ? '<h3>Fitness Dimensions</h3><dl class="detail-grid">'+fitHtml+'</dl>' : '')+

    '<h3>System Prompt (active)</h3>'+
    '<div class="prompt-box">'+esc(prompt)+'</div>'+

    '<h3>File Structure</h3>'+
    '<div class="file-tree">'+
      '<div style="color:#00ff88;margin-bottom:6px">~/.dharma/agents/'+a.name+'/</div>'+
      filesHtml+
    '</div>'+

    '<h3>Task History ('+tasks.length+' tasks)</h3>'+
    (tasksHtml || '<div style="color:#555;font-size:0.85em">No tasks yet</div>');

  document.getElementById('modal').classList.add('show');
}

function esc(s) { const d=document.createElement('div'); d.textContent=s; return d.innerHTML; }

async function loadIdeas() {
  const d = await (await fetch('/api/ideas')).json();
  const statusBadge = s => {
    const cls = s.includes('LIVE') ? 'live' : s.includes('built') ? 'built' :
      s.includes('design') ? 'design' : s.includes('track') ? 'tracking' :
      s.includes('research') ? 'research' : 'concept';
    return '<span class="badge badge-'+cls+'">'+s+'</span>';
  };
  document.getElementById('ideas-table').innerHTML =
    '<tr><th>#</th><th>Idea</th><th>Category</th><th>Status</th><th>Source</th></tr>'+
    d.ideas.map(i =>
      '<tr><td>'+i.rank+'</td><td><strong>'+i.title+'</strong><br><span style="color:#666;font-size:0.9em">'+i.description+'</span></td>'+
      '<td>'+i.category+'</td><td>'+statusBadge(i.status)+'</td><td style="color:#555">'+i.source+'</td></tr>'
    ).join('');
}

async function loadBoard() {
  const d = await (await fetch('/api/board')).json();
  if (d.error) { document.getElementById('board-content').innerHTML = d.error; return; }
  const statusIcon = s => s==='done'?'<span class="t-ok">[DONE]</span>':s==='in_progress'?'<span style="color:#ffaa00">[WIP]</span>':'<span style="color:#555">[TODO]</span>';
  const riskColor = r => r==='high'?'#ff4444':r==='medium'?'#ffaa00':'#666';
  let html = '<div style="margin-bottom:15px;font-size:0.85em;color:#888">'+d.totals.done+'/'+
    (d.totals.done+d.totals.todo)+' units complete</div>';
  for (const phase of d.phases) {
    const pDone = phase.units.filter(u=>u.status==='done').length;
    const pTotal = phase.units.length;
    const pPct = (pDone/pTotal*100).toFixed(0);
    html += '<div style="background:#111;border:1px solid #1a1a1a;border-radius:8px;padding:14px;margin-bottom:10px">'+
      '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">'+
      '<div><strong style="color:#00ff88">'+phase.id+'</strong> '+phase.name+
      ' <span style="color:#555">('+phase.hours+'h)</span></div>'+
      '<span style="color:'+(phase.status==='done'?'#00ff88':phase.status==='in_progress'?'#ffaa00':'#555')+'">'+phase.status+'</span></div>'+
      '<div class="bar"><div class="bar-fill bar-g" style="width:'+pPct+'%"></div></div>';
    for (const u of phase.units) {
      html += '<div style="display:flex;gap:8px;align-items:center;padding:4px 0;font-size:0.82em;border-bottom:1px solid #0a0a0f">'+
        statusIcon(u.status)+
        '<span style="color:#ccc;flex:1">'+u.id+': '+u.title+'</span>'+
        '<span style="color:#00aaff;font-size:0.8em">'+u.agent+'</span>'+
        '<span style="color:'+riskColor(u.risk)+';font-size:0.75em">'+u.risk+'</span>'+
        '</div>';
    }
    html += '</div>';
  }
  document.getElementById('board-content').innerHTML = html;
}

async function loadMission() {
  const d = await (await fetch('/api/mission-report')).json();
  document.getElementById('mission-content').textContent = d.report || 'No mission report yet. Run the fleet on a mission first.';
}

async function loadFund() {
  const f = await (await fetch('/api/fund')).json();
  document.getElementById('fund-stats').innerHTML =
    '<div class="stat"><div class="stat-val">$'+(f.total_value||100000).toLocaleString(undefined,{maximumFractionDigits:0})+'</div><div class="stat-lbl">Portfolio</div></div>'+
    '<div class="stat"><div class="stat-val">$'+(f.cash||0).toLocaleString(undefined,{maximumFractionDigits:0})+'</div><div class="stat-lbl">Cash</div></div>'+
    '<div class="stat"><div class="stat-val" style="color:'+((f.total_pnl_pct||0)>=0?'#00ff88':'#ff4444')+'">'+(f.total_pnl_pct||0).toFixed(2)+'%</div><div class="stat-lbl">P&amp;L</div></div>'+
    '<div class="stat"><div class="stat-val">'+(f.sharpe_ratio||0).toFixed(2)+'</div><div class="stat-lbl">Sharpe</div></div>'+
    '<div class="stat"><div class="stat-val">'+((f.max_drawdown||0)*100).toFixed(1)+'%</div><div class="stat-lbl">Max DD</div></div>'+
    '<div class="stat"><div class="stat-val">'+((f.win_rate||0)*100).toFixed(0)+'%</div><div class="stat-lbl">Win Rate</div></div>'+
    '<div class="stat"><div class="stat-val">'+(f.trade_count||0)+'</div><div class="stat-lbl">Trades</div></div>';

  const pos = f.positions || [];
  document.getElementById('fund-positions').innerHTML =
    '<tr><th>Symbol</th><th>Dir</th><th>Entry</th><th>Current</th><th>P&amp;L</th><th>Stop</th><th>Qty</th></tr>'+
    (pos.length ? pos.map(function(p) {
      return '<tr><td><strong>'+p.symbol+'</strong></td><td>'+p.direction+'</td>'+
      '<td>$'+p.entry_price.toFixed(2)+'</td><td>$'+p.current_price.toFixed(2)+'</td>'+
      '<td style="color:'+(p.unrealized_pnl>=0?'#00ff88':'#ff4444')+'">$'+p.unrealized_pnl.toFixed(2)+'</td>'+
      '<td>$'+p.stop_loss.toFixed(2)+'</td><td>'+p.quantity+'</td></tr>';
    }).join('') : '<tr><td colspan="7" style="color:#555">No open positions</td></tr>');

  // Equity curve
  try {
    const eq = await (await fetch('/api/fund/equity-curve')).json();
    const curve = eq.curve || [];
    if (curve.length > 1) {
      const canvas = document.getElementById('equity-chart');
      const ctx = canvas.getContext('2d');
      const W = canvas.width, H = canvas.height;
      ctx.clearRect(0,0,W,H);
      const vals = curve.map(function(c) { return c.total_value || 100000; });
      const mn = Math.min.apply(null,vals)*0.999, mx = Math.max.apply(null,vals)*1.001;
      ctx.strokeStyle = '#00ff88'; ctx.lineWidth = 2; ctx.beginPath();
      vals.forEach(function(v,i) {
        const x = (i/(vals.length-1))*W, y = H - ((v-mn)/(mx-mn))*H;
        if (i===0) ctx.moveTo(x,y); else ctx.lineTo(x,y);
      });
      ctx.stroke();
    }
  } catch(e) {}

  // Recent trades
  try {
    const t = await (await fetch('/api/fund/trades')).json();
    const trades = (t.trades || []).slice(-20).reverse();
    document.getElementById('fund-trades').innerHTML =
      '<tr><th>Symbol</th><th>Dir</th><th>Entry</th><th>Exit</th><th>P&amp;L</th><th>Date</th></tr>'+
      (trades.length ? trades.map(function(t) {
        return '<tr><td><strong>'+t.symbol+'</strong></td><td>'+t.direction+'</td>'+
        '<td>$'+(t.entry_price||0).toFixed(2)+'</td><td>$'+(t.exit_price||0).toFixed(2)+'</td>'+
        '<td style="color:'+((t.realized_pnl||0)>=0?'#00ff88':'#ff4444')+'">$'+(t.realized_pnl||0).toFixed(2)+'</td>'+
        '<td style="color:#555">'+(t.exit_time||'').substring(0,10)+'</td></tr>';
      }).join('') : '<tr><td colspan="6" style="color:#555">No closed trades yet</td></tr>');
  } catch(e) {}
}

async function loadBrier() {
  const b = await (await fetch('/api/brier')).json();
  const brierColor = function(v) { return v===null||v===undefined ? '#555' : v<0.1 ? '#00ff88' : v<0.2 ? '#ffaa00' : '#ff4444'; };
  document.getElementById('brier-stats').innerHTML =
    '<div class="stat"><div class="stat-val" style="color:'+brierColor(b.overall_brier)+'">'+(b.overall_brier!==null&&b.overall_brier!==undefined?b.overall_brier.toFixed(4):'N/A')+'</div><div class="stat-lbl">Brier Score</div></div>'+
    '<div class="stat"><div class="stat-val">'+((b.win_rate||0)*100).toFixed(0)+'%</div><div class="stat-lbl">Win Rate</div></div>'+
    '<div class="stat"><div class="stat-val" style="color:'+(b.edge_validated?'#00ff88':'#ff4444')+'">'+(b.edge_validated?'YES':'NO')+'</div><div class="stat-lbl">Edge Valid</div></div>'+
    '<div class="stat"><div class="stat-val">'+(b.resolved_predictions||0)+'/'+(b.total_predictions||0)+'</div><div class="stat-lbl">Resolved</div></div>'+
    '<div class="stat"><div class="stat-val">'+(b.pending_predictions||0)+'</div><div class="stat-lbl">Pending</div></div>';

  // Calibration chart
  var bins = b.calibration_bins || [];
  if (bins.length) {
    var canvas = document.getElementById('calibration-chart');
    var ctx = canvas.getContext('2d');
    var W = canvas.width, H = canvas.height, pad = 40;
    ctx.clearRect(0,0,W,H);
    // Perfect calibration line
    ctx.strokeStyle = '#333'; ctx.lineWidth = 1; ctx.setLineDash([5,5]);
    ctx.beginPath(); ctx.moveTo(pad,H-pad); ctx.lineTo(W-pad,pad); ctx.stroke();
    ctx.setLineDash([]);
    // Actual calibration
    ctx.fillStyle = '#00ff88';
    bins.forEach(function(bin) {
      var x = pad + bin.predicted_mean * (W-2*pad);
      var y = (H-pad) - bin.actual_mean * (H-2*pad);
      var r = Math.max(4, Math.min(12, bin.count));
      ctx.beginPath(); ctx.arc(x,y,r,0,Math.PI*2); ctx.fill();
    });
    // Axes labels
    ctx.fillStyle = '#555'; ctx.font = '10px monospace';
    ctx.fillText('Predicted',W/2-20,H-5);
    ctx.save(); ctx.translate(10,H/2); ctx.rotate(-Math.PI/2); ctx.fillText('Actual',0,0); ctx.restore();
  }

  // Predictions table
  try {
    var p = await (await fetch('/api/brier/predictions')).json();
    var preds = (p.predictions || []).slice(0, 50);
    document.getElementById('brier-predictions').innerHTML =
      '<tr><th>Question</th><th>Prob</th><th>Cat</th><th>Status</th><th>Brier</th><th>Created</th></tr>'+
      preds.map(function(p) {
        var status = p.outcome !== null ? (p.outcome===1?'YES':'NO') : 'PENDING';
        var sc = p.brier_score !== null ? p.brier_score.toFixed(4) : '-';
        var scColor = p.brier_score===null ? '#555' : p.brier_score<0.1 ? '#00ff88' : p.brier_score<0.2 ? '#ffaa00' : '#ff4444';
        return '<tr><td>'+p.question.substring(0,60)+'</td><td>'+(p.probability*100).toFixed(0)+'%</td>'+
          '<td>'+p.category+'</td><td style="color:'+(status==='PENDING'?'#ffaa00':'#00ff88')+'">'+status+'</td>'+
          '<td style="color:'+scColor+'">'+sc+'</td><td style="color:#555">'+(p.created_at||'').substring(0,10)+'</td></tr>';
      }).join('');
  } catch(e) {}
}

async function refresh() {
  try {
    const f = await (await fetch('/api/fleet')).json();

    document.getElementById('stats-bar').innerHTML =
      '<div class="stat"><div class="stat-val">'+f.agent_count+'</div><div class="stat-lbl">Agents</div></div>'+
      '<div class="stat"><div class="stat-val">'+f.total_calls+'</div><div class="stat-lbl">Calls</div></div>'+
      '<div class="stat"><div class="stat-val">'+f.total_tokens.toLocaleString()+'</div><div class="stat-lbl">Tokens</div></div>'+
      '<div class="stat"><div class="stat-val">'+(f.avg_fitness*100).toFixed(0)+'%</div><div class="stat-lbl">Avg Fitness</div></div>'+
      '<div class="stat"><div class="stat-val">$'+f.total_cost_usd.toFixed(3)+'</div><div class="stat-lbl">Total Cost</div></div>';

    let html = '';
    for (const a of f.agents) {
      const fp = (a.fitness*100).toFixed(0);
      const bc = a.fitness>0.7?'bar-g':a.fitness>0.4?'bar-y':'bar-r';
      const ti = a.trend==='improving'?'&#9650;':a.trend==='declining'?'&#9660;':'&#8211;';
      const tc = a.trend==='improving'?'t-ok':a.trend==='declining'?'t-fail':'';

      const det = await (await fetch('/api/agents/'+a.name)).json();
      const tasks = (det.tasks||[]).slice(-3);
      let th = '';
      for (const t of tasks) {
        const c = t.success?'t-ok':'t-fail';
        const i2 = t.success?'[ok]':'[FAIL]';
        th += '<div class="task-line"><span class="'+c+'">'+i2+'</span>'+(t.task_description||'').substring(0,45)+
          ' <span style="color:#333">'+(t.tokens_used||0)+'tok</span></div>';
      }

      html += '<div class="card" onclick="openAgent(\''+a.name+'\')">'+
        '<div class="card-head"><span class="card-icon">'+a.icon+'</span>'+
        '<div><div class="card-name">'+a.name.toUpperCase()+'</div>'+
        '<div class="card-role">'+a.role+'</div>'+
        '<div class="card-model">'+a.model_short+'</div></div>'+
        '<span style="margin-left:auto;color:'+(a.status==='idle'?'#00ff88':'#ffaa00')+'">'+a.status+'</span></div>'+
        '<div style="display:flex;justify-content:space-between;font-size:0.8em">'+
        '<span>Fitness: '+fp+'%</span><span class="'+tc+'">'+ti+' '+a.trend+'</span></div>'+
        '<div class="bar"><div class="bar-fill '+bc+'" style="width:'+fp+'%"></div></div>'+
        '<div class="card-stats"><span>'+a.tasks_ok+' ok</span><span>'+a.tasks_fail+' fail</span>'+
        '<span>'+a.tokens.toLocaleString()+' tok</span><span>q:'+((a.avg_quality||0.5)*100).toFixed(0)+'%</span></div>'+
        (th?'<div class="card-tasks">'+th+'</div>':'')+
        '</div>';
    }
    document.getElementById('agent-grid').innerHTML = html;
    document.getElementById('refresh-ts').textContent = 'refresh: '+new Date().toLocaleTimeString();
  } catch(e) { console.error(e); }
}

refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>"""


@app.get("/fund", response_class=HTMLResponse)
def landing_page():
    return """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Dharmic Quant</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0f;color:#e0e0e0;font-family:'JetBrains Mono','Fira Code',monospace}
.hero{text-align:center;padding:80px 20px 40px}
.hero h1{font-size:2.8em;color:#00ff88;letter-spacing:3px}
.hero .sub{color:#888;font-size:1.1em;margin-top:10px;max-width:600px;margin-left:auto;margin-right:auto}
.container{max-width:1000px;margin:0 auto;padding:20px}
.cols{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;margin:40px 0}
.col{background:#111;border:1px solid #1a1a1a;border-radius:10px;padding:20px;text-align:center}
.col h3{color:#00ff88;margin-bottom:8px}
.col p{color:#888;font-size:0.85em;line-height:1.5}
.stats-live{display:flex;justify-content:center;gap:30px;margin:30px 0;flex-wrap:wrap}
.sl{text-align:center}
.sl .v{font-size:2em;color:#00ff88;font-weight:bold}
.sl .l{color:#555;font-size:0.7em;text-transform:uppercase}
.dharmic{background:#111;border:1px solid #1a1a1a;border-radius:10px;padding:30px;margin:30px 0}
.dharmic h2{color:#00ff88;margin-bottom:15px}
.dharmic .gate{display:inline-block;background:#00ff8822;color:#00ff88;padding:4px 12px;border-radius:15px;margin:4px;font-size:0.85em}
.waitlist{text-align:center;margin:40px 0;padding:40px;background:#111;border-radius:10px}
.waitlist input{background:#0a0a0f;border:1px solid #333;color:#fff;padding:10px 15px;border-radius:6px;font-family:inherit;width:250px;margin-right:8px}
.waitlist button{background:#00ff88;color:#0a0a0f;border:none;padding:10px 20px;border-radius:6px;font-family:inherit;font-weight:bold;cursor:pointer}
.waitlist button:hover{background:#00cc66}
.footer{text-align:center;color:#333;font-size:0.75em;padding:30px;border-top:1px solid #111;margin-top:40px}
</style></head><body>
<div class="hero">
<h1>DHARMIC QUANT</h1>
<div class="sub">The AI-Native Hedge Fund That Publishes Every Miss</div>
<p style="color:#555;margin-top:8px">6 frontier AI agents. Every prediction Brier-scored. Radical transparency.</p>
</div>
<div class="container">
<div class="cols">
<div class="col"><h3>Analyze</h3><p>Regime detection + SEC 10-K filings + macro indicators. HMM, GARCH, and 6 AI agents synthesize the signal from noise.</p></div>
<div class="col"><h3>Predict</h3><p>Every directional call is Brier-scored. No hiding losses. Predictions resolve against real market data.</p></div>
<div class="col"><h3>Evolve</h3><p>Darwin Engine evolves agent prompts. Only the fittest strategies survive. Continuous improvement, not static rules.</p></div>
</div>
<div class="stats-live" id="live-stats"></div>
<div class="dharmic">
<h2>The Dharmic Edge</h2>
<p style="color:#888;margin-bottom:12px">Not just a hedge fund. A governance-first approach to AI-driven finance.</p>
<span class="gate">SATYA &mdash; Publish all scores including misses</span>
<span class="gate">AHIMSA &mdash; No single position &gt; 5%</span>
<span class="gate">REVERSIBILITY &mdash; Every trade has a stop loss</span>
</div>
<div class="waitlist">
<h2 style="color:#00ff88;margin-bottom:15px">Join the Waitlist</h2>
<p style="color:#888;margin-bottom:15px">Get daily intelligence reports when we launch.</p>
<input type="email" id="wl-email" placeholder="your@email.com">
<button onclick="joinWaitlist()">Join Waitlist</button>
<div id="wl-msg" style="margin-top:10px;color:#00ff88"></div>
</div>
<div class="footer">Built on dharma_swarm &mdash; 100K+ lines, 4,300+ tests. Powered by frontier AI.</div>
</div>
<script>
async function loadLiveStats() {
  try {
    const [f,b] = await Promise.all([fetch('/api/fleet').then(r=>r.json()), fetch('/api/brier').then(r=>r.json())]);
    document.getElementById('live-stats').innerHTML =
      '<div class="sl"><div class="v">'+f.agent_count+'</div><div class="l">AI Agents</div></div>'+
      '<div class="sl"><div class="v">'+(b.total_predictions||0)+'</div><div class="l">Predictions</div></div>'+
      '<div class="sl"><div class="v">'+(b.overall_brier!==null&&b.overall_brier!==undefined?b.overall_brier.toFixed(4):'N/A')+'</div><div class="l">Brier Score</div></div>'+
      '<div class="sl"><div class="v">'+((b.win_rate||0)*100).toFixed(0)+'%</div><div class="l">Win Rate</div></div>';
  } catch(e) {}
}
async function joinWaitlist() {
  const email = document.getElementById('wl-email').value;
  const r = await fetch('/api/waitlist', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({email})});
  const d = await r.json();
  document.getElementById('wl-msg').textContent = d.success ? 'You are #'+d.count+' on the waitlist!' : d.error || 'Error';
}
loadLiveStats();
</script></body></html>"""
