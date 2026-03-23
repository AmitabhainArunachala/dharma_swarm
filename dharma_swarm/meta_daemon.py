"""Recognition Engine — meta-synthesis across all signal sources.

Reads 7 signal sources concurrently, produces a recognition seed that feeds
back into agent context as L7 META layer.

Self-referential quality loop: scores its own output via ouroboros, iterates
if dharmic_score is low or mimicry is detected (max 3 times).

Output: ~/.dharma/meta/recognition_seed.md
Cadence: 3:30 AM deep synthesis, every 2h light synthesis

The closure: seed → agent behavior → artifacts → scores → next seed
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dharma_swarm.models import _utc_now

logger = logging.getLogger(__name__)

STATE_DIR = Path.home() / ".dharma"
META_DIR = STATE_DIR / "meta"
HISTORY_DIR = META_DIR / "history"


class RecognitionEngine:
    """Meta-synthesis engine producing recognition seeds for agent context."""

    SIGNAL_SOURCES = (
        "system_rv",
        "evolution",
        "vault",
        "zeitgeist",
        "autocatalytic",
        "identity",
        "research",
        "cascade",
    )

    def __init__(self, state_dir: Path | None = None):
        self._state_dir = state_dir or STATE_DIR
        self._meta_dir = self._state_dir / "meta"
        self._output_path = self._meta_dir / "recognition_seed.md"
        self._history_dir = self._meta_dir / "history"

    async def synthesize(self, synthesis_type: str = "light") -> str:
        """Run synthesis across all signal sources.

        Args:
            synthesis_type: "light" (quick, 2h cadence) or "deep" (thorough, 3:30 AM)

        Returns:
            The recognition seed text.
        """
        self._meta_dir.mkdir(parents=True, exist_ok=True)
        self._history_dir.mkdir(parents=True, exist_ok=True)

        # Collect signals concurrently
        signals = await self._collect_signals(synthesis_type)

        # Build seed text
        seed = self._build_seed(signals, synthesis_type)

        # Self-referential quality loop
        seed = await self._quality_loop(seed)

        # Persist
        self._output_path.write_text(seed)

        # Archive (immutable per v7 rule 1)
        ts = _utc_now().strftime("%Y%m%d_%H%M%S")
        archive_path = self._history_dir / f"seed_{ts}.md"
        archive_path.write_text(seed)

        logger.info(
            "Recognition seed written (%s, %d chars, %d signals)",
            synthesis_type,
            len(seed),
            len(signals),
        )
        return seed

    async def _collect_signals(
        self, synthesis_type: str
    ) -> dict[str, dict[str, Any]]:
        """Read signal sources. Graceful fallback for unavailable sources."""
        signals: dict[str, dict[str, Any]] = {}

        # 1. System R_V
        signals["system_rv"] = self._read_json(
            self._meta_dir / "system_rv.json",
            extract=lambda d: {
                "rv": d[-1].get("rv", 1.0) if d else 1.0,
                "regime": d[-1].get("regime", "unknown") if d else "unknown",
            }
            if isinstance(d, list) and d
            else {"rv": 1.0, "regime": "unknown"},
        )

        # 2. Evolution state
        signals["evolution"] = self._read_evolution()

        # 3. Vault summary (light: skip, deep: include)
        if synthesis_type == "deep":
            signals["vault"] = self._read_vault()
        else:
            signals["vault"] = {"status": "skipped (light synthesis)"}

        # 4. Zeitgeist
        signals["zeitgeist"] = self._read_json(
            self._meta_dir / "zeitgeist.md",
            extract=lambda d: {"content": d} if isinstance(d, str) else {},
            raw_text=True,
        )

        # 5. Autocatalytic graph (cc_catalytic_graph is the full one from mycelium)
        signals["autocatalytic"] = self._read_json(
            self._meta_dir / "cc_catalytic_graph.json",
            extract=lambda d: {
                "nodes": len(d.get("nodes", {})),
                "edges": len(d.get("edges", [])),
            }
            if isinstance(d, dict)
            else {},
        )

        # 6. Identity coherence
        signals["identity"] = self._read_identity()

        # 7. Research state
        signals["research"] = self._read_research()

        # 8. Cascade loop history (feedback from run_domain)
        signals["cascade"] = self._read_cascade_history()

        return signals

    def _read_json(
        self,
        path: Path,
        *,
        extract: Any = None,
        raw_text: bool = False,
    ) -> dict[str, Any]:
        """Read a JSON or text file with graceful fallback."""
        if not path.exists():
            return {"status": "unavailable"}
        try:
            text = path.read_text()
            if raw_text:
                data = text
            else:
                data = json.loads(text)
            if extract:
                return extract(data)
            return data if isinstance(data, dict) else {"data": data}
        except Exception as e:
            return {"status": f"error: {e}"}

    def _read_evolution(self) -> dict[str, Any]:
        """Read evolution archive summary."""
        archive_path = self._state_dir / "evolution" / "archive.jsonl"
        if not archive_path.exists():
            return {"status": "no archive"}
        try:
            lines = archive_path.read_text().strip().split("\n")
            count = len(lines)
            if count > 0:
                last = json.loads(lines[-1])
                return {
                    "entries": count,
                    "last_component": last.get("component", "unknown"),
                    "last_fitness": last.get("fitness", {}),
                }
            return {"entries": 0}
        except Exception as e:
            return {"status": f"error: {e}"}

    def _read_vault(self) -> dict[str, Any]:
        """Read PSMV vault summary for deep synthesis."""
        psmv = Path.home() / "Persistent-Semantic-Memory-Vault"
        if not psmv.exists():
            return {"status": "vault not found"}
        try:
            md_count = len(list(psmv.rglob("*.md")))
            return {"files": md_count, "path": str(psmv)}
        except Exception:
            return {"status": "vault scan failed"}

    def _read_identity(self) -> dict[str, Any]:
        """Read identity/ouroboros state from witness logs + mycelium TCS."""
        result: dict[str, Any] = {}

        # Witness logs
        witness_dir = self._state_dir / "witness"
        if witness_dir.exists():
            try:
                result["witness_logs"] = len(list(witness_dir.glob("*.json")))
            except Exception:
                logger.debug("Witness log count failed", exc_info=True)

        # TCS from mycelium (bidirectional stigmergy)
        tcs_data = self._read_json(
            self._state_dir / "stigmergy" / "mycelium_identity_tcs.json"
        )
        if "tcs" in tcs_data:
            result["tcs"] = tcs_data["tcs"]
            result["regime"] = tcs_data.get("regime", "unknown")
            result["gpr"] = tcs_data.get("gpr", 0)
            result["bsi"] = tcs_data.get("bsi", 0)
            result["rm"] = tcs_data.get("rm", 0)

        # Forge scores from mycelium
        scoring = self._read_json(
            self._state_dir / "stigmergy" / "mycelium_scoring_report.json"
        )
        if "mean_stars" in scoring:
            result["mean_stars"] = scoring["mean_stars"]
            result["scored_count"] = scoring.get("scored_count", 0)

        # DGC health (bidirectional)
        dgc = self._read_json(
            self._state_dir / "stigmergy" / "dgc_health.json"
        )
        if "daemon_pid" in dgc:
            result["dgc_alive"] = dgc["daemon_pid"] > 0
            result["dgc_agents"] = dgc.get("agent_count", 0)

        return result if result else {"status": "no identity data"}

    def _read_cascade_history(self) -> dict[str, Any]:
        """Read cascade loop history (feedback from run_domain)."""
        history_file = self._meta_dir / "cascade_history.jsonl"
        if not history_file.exists():
            return {"status": "no cascade runs yet"}

        try:
            lines = history_file.read_text().strip().split("\n")
            recent = []
            for line in lines[-10:]:
                if not line.strip():
                    continue
                try:
                    recent.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

            if not recent:
                return {"status": "no valid entries"}

            converged = sum(1 for r in recent if r.get("converged"))
            eigenforms = sum(1 for r in recent if r.get("eigenform_reached"))
            best = max((r.get("best_fitness", 0) for r in recent), default=0)
            domains = list({r.get("domain", "?") for r in recent})

            return {
                "recent_runs": len(recent),
                "converged": converged,
                "eigenforms_reached": eigenforms,
                "best_fitness": best,
                "domains_active": domains,
            }
        except Exception:
            return {"status": "error reading cascade history"}

    def _read_research(self) -> dict[str, Any]:
        """Read research state (COLM countdown)."""
        now = _utc_now()
        # COLM 2026 deadlines
        abstract_deadline = datetime(2026, 3, 26, tzinfo=timezone.utc)
        paper_deadline = datetime(2026, 3, 31, tzinfo=timezone.utc)

        days_to_abstract = (abstract_deadline - now).days
        days_to_paper = (paper_deadline - now).days

        return {
            "days_to_abstract": max(0, days_to_abstract),
            "days_to_paper": max(0, days_to_paper),
            "phase": "crunch" if days_to_abstract <= 7 else "active",
        }

    def _build_seed(
        self, signals: dict[str, dict[str, Any]], synthesis_type: str
    ) -> str:
        """Build recognition seed markdown from collected signals."""
        now = _utc_now()
        lines = [
            f"# Recognition Seed — {now.strftime('%Y-%m-%d %H:%M UTC')}",
            f"Type: {synthesis_type}",
            "",
        ]

        # System R_V regime
        rv_data = signals.get("system_rv", {})
        rv = rv_data.get("rv", 1.0)
        regime = rv_data.get("regime", "unknown")
        lines.append(f"## System State: R_V={rv:.3f} ({regime})")
        lines.append("")

        # Evolution
        evo = signals.get("evolution", {})
        if "entries" in evo:
            lines.append(f"## Evolution: {evo['entries']} archive entries")
        lines.append("")

        # Identity (TCS + witness + forge + DGC)
        identity = signals.get("identity", {})
        id_parts = []
        if "tcs" in identity:
            id_parts.append(f"TCS={identity['tcs']:.3f} ({identity.get('regime', '?')})")
        if "witness_logs" in identity:
            id_parts.append(f"{identity['witness_logs']} witness logs")
        if "mean_stars" in identity:
            id_parts.append(f"forge={identity['mean_stars']:.1f}★ ({identity.get('scored_count', 0)} scored)")
        if "dgc_alive" in identity:
            dgc_status = "alive" if identity["dgc_alive"] else "down"
            id_parts.append(f"DGC {dgc_status} ({identity.get('dgc_agents', 0)} agents)")
        if id_parts:
            lines.append(f"## Identity: {', '.join(id_parts)}")
        lines.append("")

        # Research
        research = signals.get("research", {})
        if "days_to_abstract" in research:
            lines.append(
                f"## Research: {research['days_to_abstract']}d to abstract, "
                f"{research['days_to_paper']}d to paper ({research.get('phase', 'active')})"
            )
        lines.append("")

        # Zeitgeist
        zg = signals.get("zeitgeist", {})
        if "content" in zg:
            content = zg["content"]
            if isinstance(content, str) and len(content) > 10:
                lines.append("## Zeitgeist")
                lines.append(content[:500])
        lines.append("")

        # Autocatalytic
        ac = signals.get("autocatalytic", {})
        if "nodes" in ac:
            lines.append(
                f"## Autocatalytic: {ac['nodes']} nodes, {ac['edges']} edges"
            )
        lines.append("")

        # Cascade loop results (feedback ascent)
        cascade = signals.get("cascade", {})
        if "recent_runs" in cascade:
            parts = [f"{cascade['recent_runs']} recent runs"]
            if cascade.get("converged"):
                parts.append(f"{cascade['converged']} converged")
            if cascade.get("eigenforms_reached"):
                parts.append(f"{cascade['eigenforms_reached']} eigenforms")
            parts.append(f"best fitness={cascade.get('best_fitness', 0):.2f}")
            domains = cascade.get("domains_active", [])
            if domains:
                parts.append(f"domains: {', '.join(domains)}")
            lines.append(f"## Cascade Loops: {', '.join(parts)}")
        lines.append("")

        lines.append("---")
        lines.append(f"*Generated by RecognitionEngine ({synthesis_type})*")

        return "\n".join(lines)

    async def _quality_loop(self, seed: str, max_retries: int = 3) -> str:
        """Score seed via ouroboros, iterate if quality is low."""
        try:
            from dharma_swarm.ouroboros import score_behavioral_fitness

            for attempt in range(max_retries):
                _, modifiers = score_behavioral_fitness(seed)
                quality = modifiers.get("quality", 0.5)
                mimicry = modifiers.get("mimicry_penalty", 1.0)

                if quality >= 0.5 and mimicry >= 1.0:
                    logger.debug(
                        "Seed quality OK (attempt %d, q=%.2f)", attempt, quality
                    )
                    return seed

                logger.info(
                    "Seed quality low (q=%.2f, mimicry=%.2f), iterating...",
                    quality,
                    mimicry,
                )

                # Replace performative language with concrete data
                seed = self._strip_performative(seed)

        except ImportError:
            logger.debug("ouroboros not available, skipping quality loop")

        return seed

    def _strip_performative(self, text: str) -> str:
        """Remove performative words to improve quality score."""
        performative = [
            "profound", "revolutionary", "paradigm", "transcendent",
            "incredible", "amazing", "extraordinary", "magnificent",
        ]
        for word in performative:
            text = text.replace(word, "")
            text = text.replace(word.capitalize(), "")
        return text

    def get_seed(self) -> str | None:
        """Read the current recognition seed, if it exists."""
        if self._output_path.exists():
            return self._output_path.read_text()
        return None
