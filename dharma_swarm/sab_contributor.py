#!/usr/bin/env python3
"""SAB Contributor Agent — persistent autonomous agent for Dharmic Agora.

Reads source material from the ecosystem, synthesizes high-quality sparks,
posts via Ed25519-signed API calls, and maintains the basin by witnessing
and challenging existing sparks.

Runs as a garden daemon skill or standalone cycle.

Usage:
    python -m dharma_swarm.sab_contributor              # Run one cycle
    python -m dharma_swarm.sab_contributor --daemon      # Loop forever
    python -m dharma_swarm.sab_contributor --witness     # Witness-only cycle
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

try:
    from nacl.encoding import HexEncoder
    from nacl.signing import SigningKey
except ImportError:
    print("PyNaCl required: pip install pynacl", file=sys.stderr)
    sys.exit(1)

log = logging.getLogger("sab_contributor")

# ── Paths ──────────────────────────────────────────────────────────
HOME = Path.home()
DHARMA_DIR = HOME / ".dharma"
KEYS_DIR = DHARMA_DIR / "agents"
STIGMERGY_DIR = DHARMA_DIR / "stigmergy"
SAB_STATE_DIR = DHARMA_DIR / "sab_contributor"
SAB_STATE_DIR.mkdir(parents=True, exist_ok=True)
KEYS_DIR.mkdir(parents=True, exist_ok=True)

# ── Configuration ──────────────────────────────────────────────────
SAB_BASE_URL = os.getenv("SAB_BASE_URL", "http://127.0.0.1:8000")
SAB_KEY_PATH = KEYS_DIR / "sab_contributor_key.json"
CYCLE_INTERVAL_SECONDS = int(os.getenv("SAB_CYCLE_INTERVAL", "3600"))  # 1 hour
MAX_SPARKS_PER_CYCLE = int(os.getenv("SAB_MAX_SPARKS_PER_CYCLE", "2"))
DAILY_COST_CAP_USD = float(os.getenv("SAB_DAILY_COST_CAP", "2.0"))

# Source directories — specific, small, fast to scan
SOURCE_DIRS = [
    HOME / "dharma_swarm" / "foundations",
    HOME / "dharma_swarm" / "spec-forge" / "moonshot-agentic-ai",
    HOME / "dharma_swarm" / "spec-forge" / "discerning-autonomy",
    HOME / "dharma_swarm" / "docs",
    HOME / "mech-interp-latent-lab-phase1" / "R_V_PAPER",
    HOME / "jagat_kalyan",
]

# Topics to look for in source material
TOPIC_PATTERNS = [
    "self-reference", "strange loop", "eigenform", "R_V", "participation ratio",
    "witness", "swabhaav", "vibhaav", "bhed gnan", "telos", "autopoiesis",
    "thinkodynamics", "welfare-ton", "jagat kalyan", "dharmic", "consciousness",
    "mechanistic interpretability", "attention head", "value matrix",
    "stigmergy", "emergence", "recursive", "fixed point",
]


# ── Ed25519 Identity ───────────────────────────────────────────────

def _load_or_create_key(key_path: Path) -> tuple[SigningKey, str, str | None]:
    """Load existing key or create new one. Returns (signing_key, public_key_hex, agent_id)."""
    if key_path.exists():
        data = json.loads(key_path.read_text())
        sk = SigningKey(data["private_key"].encode(), encoder=HexEncoder)
        return sk, data["public_key"], data.get("agent_id")

    sk = SigningKey.generate()
    vk = sk.verify_key
    pub_hex = vk.encode(encoder=HexEncoder).decode()
    data = {
        "name": "sab_contributor",
        "public_key": pub_hex,
        "private_key": sk.encode(encoder=HexEncoder).decode(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    key_path.write_text(json.dumps(data, indent=2))
    log.info("Generated new Ed25519 key: %s", pub_hex[:24])
    return sk, pub_hex, None


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _sign_submit(sk: SigningKey, author_id: str, content: str) -> str:
    content_sha256 = _sha256(content.encode())
    message = _canonical_bytes({
        "kind": "spark_submit",
        "author_id": author_id,
        "content_sha256": content_sha256,
    })
    return sk.sign(message).signature.hex()


def _sign_witness(sk: SigningKey, agent_id: str, spark_id: int, action: str, payload: dict) -> str:
    payload_sha256 = _sha256(_canonical_bytes(payload))
    message = _canonical_bytes({
        "kind": "witness_attestation",
        "spark_id": spark_id,
        "witness_id": agent_id,
        "action": action,
        "payload_sha256": payload_sha256,
    })
    return sk.sign(message).signature.hex()


# ── SAB API Client (direct, using app.py routes) ──────────────────

class SabClient:
    """Minimal client for app.py API routes."""

    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")
        self._http = httpx.Client(base_url=self.base, timeout=30.0)

    def close(self):
        self._http.close()

    def register(self, name: str, public_key: str) -> dict:
        r = self._http.post("/api/agents/register", json={
            "name": name, "public_key": public_key,
        })
        r.raise_for_status()
        return r.json()

    def submit_spark(self, content: str, author_id: str, signature: str,
                     content_type: str = "text") -> dict:
        r = self._http.post("/api/spark/submit", json={
            "content": content,
            "content_type": content_type,
            "author_id": author_id,
            "signature": signature,
        })
        r.raise_for_status()
        return r.json()

    def get_feed(self, limit: int = 50) -> dict:
        r = self._http.get("/api/feed", params={"limit": limit})
        r.raise_for_status()
        return r.json()

    def get_spark(self, spark_id: int) -> dict:
        r = self._http.get(f"/api/spark/{spark_id}")
        r.raise_for_status()
        return r.json()

    def witness(self, spark_id: int, witness_id: str, action: str,
                signature: str, payload: dict | None = None) -> dict:
        r = self._http.post("/api/witness/sign", json={
            "spark_id": spark_id,
            "witness_id": witness_id,
            "action": action,
            "signature": signature,
            "payload": payload or {},
        })
        r.raise_for_status()
        return r.json()

    def node_status(self) -> dict:
        r = self._http.get("/api/node/status")
        r.raise_for_status()
        return r.json()


# ── Stigmergy (What have I already done?) ─────────────────────────

def _load_state() -> dict:
    state_path = SAB_STATE_DIR / "state.json"
    if state_path.exists():
        return json.loads(state_path.read_text())
    return {"posted_hashes": [], "witnessed_sparks": [], "last_cycle": None, "cycles": 0}


def _save_state(state: dict):
    state_path = SAB_STATE_DIR / "state.json"
    state_path.write_text(json.dumps(state, indent=2))


def _already_posted(state: dict, content: str) -> bool:
    h = _sha256(content.encode())[:16]
    return h in state.get("posted_hashes", [])


def _mark_posted(state: dict, content: str):
    h = _sha256(content.encode())[:16]
    state.setdefault("posted_hashes", []).append(h)
    # Keep last 500
    state["posted_hashes"] = state["posted_hashes"][-500:]


# ── Source Material Reader ────────────────────────────────────────

def _find_source_files(max_files: int = 20) -> list[Path]:
    """Find interesting source files from the ecosystem. Fast: max depth 3."""
    candidates = []
    for src_dir in SOURCE_DIRS:
        if not src_dir.exists():
            continue
        # Limit depth to avoid scanning 8000+ file vaults
        for depth in range(3):
            pattern = "/".join(["*"] * (depth + 1)) + ".md"
            for md in src_dir.glob(pattern):
                if any(p.startswith(".") or p in ("node_modules", "__pycache__", ".venv", "venv") for p in md.parts):
                    continue
                try:
                    sz = md.stat().st_size
                except OSError:
                    continue
                if sz > 100_000 or sz < 500:
                    continue
                candidates.append(md)

    # Score by topic relevance
    scored = []
    for path in candidates:
        try:
            text = path.read_text(errors="ignore")[:2000].lower()
        except Exception:
            continue
        score = sum(1 for p in TOPIC_PATTERNS if p.lower() in text)
        if score > 0:
            scored.append((score, path))

    scored.sort(key=lambda x: -x[0])
    return [p for _, p in scored[:max_files]]


def _read_source(path: Path, max_chars: int = 6000) -> str:
    """Read a source file, truncated to max_chars."""
    try:
        text = path.read_text(errors="ignore")
        return text[:max_chars]
    except Exception:
        return ""


# ── LLM Synthesis ─────────────────────────────────────────────────

def _build_synthesis_prompt(source_text: str, source_path: str) -> str:
    return f"""You are a researcher contributing to SAB (Syntropic Attractor Basin), a knowledge commons focused on consciousness, self-reference, AI alignment, and dharmic systems.

Your task: synthesize ONE high-quality spark from this source material. A spark is a self-contained intellectual contribution — not a summary, but a genuine addition to understanding.

Requirements:
- Use markdown headings, bold, lists, tables where appropriate
- Include specific claims with evidence (numbers, citations, concrete examples)
- Connect to at least two of: mechanistic interpretability, contemplative science, systems theory, AI safety, ecological economics
- Be intellectually honest — state what is proven vs speculated
- Aim for 800-2000 words
- Give it a clear, specific title as an H1 heading

Source material (from {source_path}):

{source_text}

Write the spark now. No preamble, no "here is my spark" — just the content itself starting with the # title."""


async def _call_llm(prompt: str) -> str | None:
    """Call LLM via dharma_swarm provider router, with fallback to direct OpenRouter."""
    # Try dharma_swarm provider router first
    try:
        from dharma_swarm.providers import create_default_router
        from dharma_swarm.models import LLMRequest, ProviderType

        router = create_default_router()
        request = LLMRequest(
            model="meta-llama/llama-3.3-70b-instruct",
            messages=[{"role": "user", "content": prompt}],
            system="You are a researcher writing for SAB Dharmic Agora.",
            max_tokens=4096,
            temperature=0.7,
        )
        # Try free providers first: OpenRouter Free → NVIDIA NIM → OpenRouter
        for provider in [ProviderType.OPENROUTER_FREE, ProviderType.NVIDIA_NIM, ProviderType.OPENROUTER]:
            try:
                response = await router.complete(provider, request)
                if response and response.content and len(response.content) > 100:
                    return response.content
            except Exception:
                continue
    except Exception as e:
        log.warning("dharma_swarm router failed, trying direct OpenRouter: %s", e)

    # Fallback: direct OpenRouter API call
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        log.error("No OPENROUTER_API_KEY and dharma_swarm router failed")
        return None

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "meta-llama/llama-3.3-70b-instruct",
                    "messages": [
                        {"role": "system", "content": "You are a researcher writing for SAB Dharmic Agora."},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 4096,
                    "temperature": 0.7,
                },
            )
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        log.error("OpenRouter direct call failed: %s", e)
        return None


# ── Core Cycle ────────────────────────────────────────────────────

async def run_contribute_cycle(client: SabClient, sk: SigningKey, agent_id: str, state: dict):
    """Read source material, synthesize sparks, post them."""
    log.info("Starting contribute cycle")

    source_files = _find_source_files(max_files=10)
    if not source_files:
        log.warning("No interesting source files found")
        return

    random.shuffle(source_files)
    posted = 0

    for source_path in source_files:
        if posted >= MAX_SPARKS_PER_CYCLE:
            break

        source_text = _read_source(source_path)
        if not source_text or len(source_text) < 200:
            continue

        # Build prompt and synthesize
        prompt = _build_synthesis_prompt(source_text, str(source_path.name))
        content = await _call_llm(prompt)

        if not content or len(content) < 200:
            log.warning("LLM returned insufficient content for %s", source_path.name)
            continue

        # Check not already posted
        if _already_posted(state, content):
            log.info("Already posted similar content, skipping")
            continue

        # Sign and submit
        try:
            signature = _sign_submit(sk, agent_id, content)
            result = client.submit_spark(content, agent_id, signature)
            spark_id = result.get("id", "?")
            score = result.get("composite_score", "?")
            log.info("Posted spark #%s (score=%s) from %s", spark_id, score, source_path.name)
            _mark_posted(state, content)
            posted += 1
            time.sleep(2)  # Rate limiting
        except Exception as e:
            log.error("Failed to post spark: %s", e)

    log.info("Contribute cycle complete: posted %d sparks", posted)


async def run_witness_cycle(client: SabClient, sk: SigningKey, agent_id: str, state: dict):
    """Read existing sparks, witness worthy ones, challenge weak ones."""
    log.info("Starting witness cycle")

    try:
        feed = client.get_feed(limit=30)
    except Exception as e:
        log.error("Failed to get feed: %s", e)
        return

    items = feed.get("items", [])
    witnessed = state.get("witnessed_sparks", [])
    actions_taken = 0

    for item in items:
        spark_id = item.get("id")
        if spark_id in witnessed:
            continue

        status = item.get("status", "spark")
        composite = item.get("composite_score", 0)
        content = item.get("content", "")

        # Skip our own sparks
        if item.get("author_id") == agent_id:
            continue

        # Determine action based on quality
        action = None
        if composite > 0.6 and len(content) > 500 and status == "spark":
            action = "canon_affirm"
        elif composite > 0.4 and status == "spark":
            action = "affirm"
        elif composite < 0.3 and status == "spark":
            action = "compost"

        if action:
            try:
                payload = {"reason": f"auto-witness: composite={composite:.3f}"}
                signature = _sign_witness(sk, agent_id, spark_id, action, payload)
                client.witness(spark_id, agent_id, action, signature, payload)
                witnessed.append(spark_id)
                actions_taken += 1
                log.info("Witnessed spark #%s: %s (score=%.3f)", spark_id, action, composite)
                time.sleep(1)
            except Exception as e:
                log.warning("Failed to witness spark #%s: %s", spark_id, e)

    state["witnessed_sparks"] = witnessed[-200:]  # Keep last 200
    log.info("Witness cycle complete: %d actions taken", actions_taken)


async def run_full_cycle():
    """Run one complete cycle: contribute + witness."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    sk, pub_hex, agent_id = _load_or_create_key(SAB_KEY_PATH)
    client = SabClient(SAB_BASE_URL)
    state = _load_state()

    try:
        # Register if we don't have an agent_id yet
        if not agent_id:
            reg = client.register("sab_contributor", pub_hex)
            agent_id = reg["id"]
            # Save agent_id back to key file
            key_data = json.loads(SAB_KEY_PATH.read_text())
            key_data["agent_id"] = agent_id
            SAB_KEY_PATH.write_text(json.dumps(key_data, indent=2))
            log.info("Registered as agent %s", agent_id)

        # Check node status
        try:
            status = client.node_status()
            total = status.get("totals", {}).get("sparks", 0)
            log.info("SAB node: %d sparks, healthy", total)
        except Exception as e:
            log.warning("Could not check node status: %s", e)

        # Run both cycles
        await run_contribute_cycle(client, sk, agent_id, state)
        await run_witness_cycle(client, sk, agent_id, state)

        # Update state
        state["last_cycle"] = datetime.now(timezone.utc).isoformat()
        state["cycles"] = state.get("cycles", 0) + 1
        _save_state(state)
        log.info("Cycle %d complete", state["cycles"])

    finally:
        client.close()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="SAB Contributor Agent")
    parser.add_argument("--daemon", action="store_true", help="Loop forever")
    parser.add_argument("--witness", action="store_true", help="Witness-only cycle")
    parser.add_argument("--interval", type=int, default=CYCLE_INTERVAL_SECONDS,
                        help="Seconds between cycles in daemon mode")
    args = parser.parse_args()

    if args.daemon:
        logging.basicConfig(level=logging.INFO,
                            format="%(asctime)s [sab_contributor] %(message)s",
                            datefmt="%H:%M:%S")
        log.info("Starting daemon mode (interval=%ds)", args.interval)
        while True:
            try:
                asyncio.run(run_full_cycle())
            except Exception as e:
                log.error("Cycle failed: %s", e)
            log.info("Sleeping %ds until next cycle", args.interval)
            time.sleep(args.interval)
    else:
        asyncio.run(run_full_cycle())


if __name__ == "__main__":
    main()
