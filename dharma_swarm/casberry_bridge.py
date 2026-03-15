"""
Casberry Particle Visualization Bridge
=======================================

Generates Three.js particle function bodies from dharma_swarm's semantic graph.
These functions are compatible with Casberry's particle engine API:

  - `i` (int): particle index (0 to count-1)
  - `count` (int): total particles
  - `target` (THREE.Vector3): WRITE position via target.set(x,y,z)
  - `color` (THREE.Color): WRITE color via color.setHSL(h,s,l)
  - `time` (float): simulation time in seconds
  - `THREE`: Three.js library
  - `setInfo(title, desc)`: HUD update (call only when i===0)
  - `annotate(id, pos, label)`: 3D label (call only when i===0)
  - `addControl(id, label, min, max, initial)`: UI slider, returns current value

Performance: 20,000 particles × 60fps = 1.2M calls/sec. Zero allocations.
"""

from __future__ import annotations

import json
import math
import hashlib
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

VAULT_DIR = Path.home() / ".dharma" / "vault"
VIZ_DIR = Path.home() / ".dharma" / "visualizations"


@dataclass
class ConceptPoint:
    """A concept projected into 3D space for particle rendering."""
    name: str
    x: float
    y: float
    z: float
    category: str = "general"
    salience: float = 0.5
    edge_count: int = 0
    cluster_id: int = 0


@dataclass
class SemanticParticleConfig:
    """Full configuration for a Casberry particle visualization."""
    title: str
    description: str
    concepts: list[ConceptPoint] = field(default_factory=list)
    edge_pairs: list[tuple[int, int]] = field(default_factory=list)
    cluster_count: int = 1
    total_concepts: int = 0
    total_edges: int = 0


# ── Category → HSL hue mapping ──────────────────────────────────────────────

CATEGORY_HUES = {
    # Semantic graph categories (from concept_graph.json)
    "engineering":      0.55,   # cyan — implementation/code
    "measurement":      0.12,   # orange — metrics/scoring
    "coordination":     0.75,   # purple — orchestration/swarm
    "philosophical":    0.85,   # magenta — consciousness/telos
    "mathematical":     0.60,   # blue — formal structures
    "behavioral":       0.33,   # green — agent behavior
    "architectural":    0.08,   # gold — system design
    "security":         0.00,   # red — safety/gates
    "cognitive":        0.80,   # violet — memory/learning
    "evolutionary":     0.15,   # amber — darwin/mutation
    # Vault/display categories
    "core_pipeline":    0.55,   # cyan
    "knowledge_infra":  0.75,   # purple
    "consumer":         0.33,   # green
    "integration":      0.12,   # orange
    "concept":          0.60,   # blue
    "visualization":    0.85,   # magenta
    "kailash":          0.08,   # gold
    "general":          0.50,   # teal
}


def _hash_to_angle(name: str) -> float:
    """Deterministic angle from concept name."""
    h = int(hashlib.md5(name.encode()).hexdigest()[:8], 16)
    return (h / 0xFFFFFFFF) * math.pi * 2


def project_concepts_3d(config: SemanticParticleConfig) -> list[dict]:
    """
    Project concepts into 3D positions using a force-directed-like layout.
    Clusters form orbital shells, concepts within clusters spread by hash.
    """
    points = []
    for i, c in enumerate(config.concepts):
        # Cluster shell radius
        shell = 20 + c.cluster_id * 15
        # Spread within cluster
        angle = _hash_to_angle(c.name)
        phi = (i / max(len(config.concepts), 1)) * math.pi * 2
        theta = angle

        x = shell * math.sin(theta) * math.cos(phi)
        y = shell * math.sin(theta) * math.sin(phi)
        z = shell * math.cos(theta)

        # Salience pushes outward
        scale = 1.0 + c.salience * 0.5
        points.append({
            "name": c.name,
            "x": x * scale,
            "y": y * scale,
            "z": z * scale,
            "hue": CATEGORY_HUES.get(c.category, 0.5),
            "salience": c.salience,
            "edges": c.edge_count,
        })
    return points


def build_from_semantic_graph(graph_path: Optional[Path] = None) -> SemanticParticleConfig:
    """
    Build a particle config from the actual semantic concept graph.
    Reads the JSON graph produced by semantic_gravity.py.
    """
    if graph_path is None:
        # Find the latest semantic graph
        candidates = [
            Path.home() / ".dharma" / "semantic" / "concept_graph.json",
            Path.home() / ".dharma" / "semantic_graph.json",
            Path.home() / "dharma_swarm" / "semantic_concept_graph.json",
            Path.home() / "dharma_swarm" / "reports" / "dgc_self_proving_packet_20260313" / "semantic_graph.json",
        ]
        for p in candidates:
            if p.exists():
                graph_path = p
                break

    if graph_path is None or not graph_path.exists():
        return _build_from_vault()

    with open(graph_path) as f:
        data = json.load(f)

    concepts = []
    nodes = data.get("nodes", data.get("concepts", []))
    edges = data.get("edges", data.get("links", []))

    # Build ID→index mapping and count edges per node ID
    edge_counts: dict[str, int] = {}
    for e in edges:
        src = e.get("source_id", e.get("source", e.get("from", "")))
        tgt = e.get("target_id", e.get("target", e.get("to", "")))
        edge_counts[src] = edge_counts.get(src, 0) + 1
        edge_counts[tgt] = edge_counts.get(tgt, 0) + 1

    max_edges = max(edge_counts.values()) if edge_counts else 1

    # Category clustering — group by category for orbital shells
    cat_clusters: dict[str, int] = {}
    cluster_counter = 0

    id_to_idx: dict[str, int] = {}

    for i, node in enumerate(nodes):
        node_id = node.get("id", f"node_{i}")
        name = node.get("name", node_id)
        cat = node.get("category", node.get("type", "general"))
        norm_cat = _normalize_category(cat)

        if norm_cat not in cat_clusters:
            cat_clusters[norm_cat] = cluster_counter
            cluster_counter += 1

        ec = edge_counts.get(node_id, 0)
        sal = node.get("salience", ec / max_edges if max_edges > 0 else 0.5)
        # Boost salience by edge count
        sal = max(sal, ec / max_edges if max_edges > 0 else 0.0)

        id_to_idx[node_id] = i
        concepts.append(ConceptPoint(
            name=name[:40],  # truncate for display
            x=0, y=0, z=0,  # will be projected
            category=norm_cat,
            salience=min(sal, 1.0),
            edge_count=ec,
            cluster_id=cat_clusters[norm_cat],
        ))

    edge_pairs = []
    for e in edges:
        src = e.get("source_id", e.get("source", ""))
        tgt = e.get("target_id", e.get("target", ""))
        if src in id_to_idx and tgt in id_to_idx:
            edge_pairs.append((id_to_idx[src], id_to_idx[tgt]))

    # Downsample for Casberry performance (max ~300 concepts for 20K particles)
    MAX_CONCEPTS = 300
    if len(concepts) > MAX_CONCEPTS:
        # Keep the most connected concepts
        ranked = sorted(range(len(concepts)), key=lambda i: concepts[i].edge_count, reverse=True)
        keep_set = set(ranked[:MAX_CONCEPTS])
        old_to_new = {}
        filtered = []
        for old_idx in ranked[:MAX_CONCEPTS]:
            old_to_new[old_idx] = len(filtered)
            filtered.append(concepts[old_idx])
        # Remap edges
        filtered_edges = []
        for src, tgt in edge_pairs:
            if src in old_to_new and tgt in old_to_new:
                filtered_edges.append((old_to_new[src], old_to_new[tgt]))
        concepts = filtered
        edge_pairs = filtered_edges

    config = SemanticParticleConfig(
        title="DHARMA Semantic Field",
        description=f"{len(concepts)} concepts (top by connectivity) | {len(edge_pairs)} edges | {len(nodes)} total in graph",
        concepts=concepts,
        edge_pairs=edge_pairs,
        cluster_count=max(c.cluster_id for c in concepts) + 1 if concepts else 1,
        total_concepts=len(concepts),
        total_edges=len(edge_pairs),
    )
    return config


def _build_from_vault() -> SemanticParticleConfig:
    """Fallback: build config from vault markdown files."""
    concepts = []
    vault = VAULT_DIR
    if not vault.exists():
        return SemanticParticleConfig(
            title="DHARMA Semantic Field",
            description="No data — run dgc semantic digest first",
        )

    md_files = list(vault.rglob("*.md"))
    for i, f in enumerate(md_files):
        content = f.read_text(errors="ignore")
        # Count wikilinks as proxy for connectivity
        import re
        links = re.findall(r'\[\[([^\]]+)\]\]', content)
        # Determine category from path
        parts = f.relative_to(vault).parts
        cat = parts[0].lower().replace("-", "_") if len(parts) > 1 else "general"
        cat = _normalize_category(cat)

        concepts.append(ConceptPoint(
            name=f.stem,
            x=0, y=0, z=0,
            category=cat,
            salience=min(len(links) / 20.0, 1.0),
            edge_count=len(links),
            cluster_id=hash(cat) % 7,
        ))

    return SemanticParticleConfig(
        title="DHARMA Knowledge Vault",
        description=f"{len(concepts)} notes | vault-derived topology",
        concepts=concepts,
        total_concepts=len(concepts),
    )


def _normalize_category(cat: str) -> str:
    """Map various category names to our standard set."""
    cat = cat.lower().replace("-", "_").replace(" ", "_")
    mappings = {
        "00_architecture": "core_pipeline",
        "01_core_pipeline": "core_pipeline",
        "02_knowledge_infra": "knowledge_infra",
        "03_consumers": "consumer",
        "04_integration": "integration",
        "05_concepts": "concept",
        "06_visualization": "visualization",
        "07_kailash": "kailash",
        "class": "core_pipeline",
        "function": "core_pipeline",
        "module": "knowledge_infra",
        "formal_structure": "concept",
    }
    return mappings.get(cat, cat if cat in CATEGORY_HUES else "general")


# ── Particle Function Generator ─────────────────────────────────────────────

def generate_particle_function(config: SemanticParticleConfig) -> str:
    """
    Generate a Casberry-compatible JavaScript function body that visualizes
    the semantic graph as a living particle field.

    20,000 particles. Zero allocations. Pure math.
    """
    points = project_concepts_3d(config)
    n = len(points)

    if n == 0:
        return _generate_empty_viz()

    # Encode concept positions as flat arrays for O(1) lookup
    # We pack into the function as constants to avoid closures
    xs = [p["x"] for p in points]
    ys = [p["y"] for p in points]
    zs = [p["z"] for p in points]
    hues = [p["hue"] for p in points]
    sals = [p["salience"] for p in points]

    # Quantize to reduce code size
    def q(v): return round(v, 2)

    xs_str = ",".join(str(q(x)) for x in xs)
    ys_str = ",".join(str(q(y)) for y in ys)
    zs_str = ",".join(str(q(z)) for z in zs)
    hues_str = ",".join(str(q(h)) for h in hues)
    sals_str = ",".join(str(q(s)) for s in sals)

    # Edge pairs for trail rendering (limit to top 200 for performance)
    top_edges = config.edge_pairs[:200]
    edges_src = ",".join(str(e[0]) for e in top_edges)
    edges_tgt = ",".join(str(e[1]) for e in top_edges)

    # Find the hottest concept for annotation
    hottest_idx = max(range(n), key=lambda i: sals[i]) if n > 0 else 0
    hottest = points[hottest_idx] if n > 0 else {"name": "none", "x": 0, "y": 0, "z": 0}

    return f"""// DHARMA Semantic Field — {config.total_concepts} concepts, {config.total_edges} edges
// Generated by dharma_swarm/casberry_bridge.py

const spread = addControl("spread", "Semantic Spread", 10, 200, 80);
const drift = addControl("drift", "Drift Speed", 0.0, 3.0, 0.5);
const pulse = addControl("pulse", "Salience Pulse", 0.0, 1.0, 0.4);
const depth = addControl("depth", "Z Depth", 0.1, 3.0, 1.0);
const trailMix = addControl("trails", "Edge Trails", 0.0, 1.0, 0.3);

const N = {n};
const EDGE_COUNT = {len(top_edges)};
const CX = [{xs_str}];
const CY = [{ys_str}];
const CZ = [{zs_str}];
const HUE = [{hues_str}];
const SAL = [{sals_str}];
const E_SRC = [{edges_src}];
const E_TGT = [{edges_tgt}];

const t = i / count;
const conceptIdx = Math.floor(t * N) % N;

// Particles per concept — multiple particles orbit each concept node
const localIdx = i % Math.max(1, Math.floor(count / N));
const orbitPhase = localIdx * 6.2831853 / Math.max(1, Math.floor(count / N));

// Base position from pre-computed concept coordinates
const bx = CX[conceptIdx];
const by = CY[conceptIdx];
const bz = CZ[conceptIdx];
const sal = SAL[conceptIdx];

// Drift animation — concepts breathe based on salience
const phase = conceptIdx * 0.618033 + time * drift;
const breathe = sal * pulse * 3.0;

// Orbit around concept center — higher salience = tighter orbit
const orbitR = 2.0 + (1.0 - sal) * 4.0;
const ox = Math.cos(orbitPhase + time * drift * 0.7) * orbitR;
const oy = Math.sin(orbitPhase + time * drift * 0.5) * orbitR;
const oz = Math.sin(orbitPhase * 1.3 + time * drift * 0.3) * orbitR * 0.5;

// Edge trail particles — some particles flow between connected concepts
let fx = 0;
let fy = 0;
let fz = 0;

if (trailMix > 0.01 && EDGE_COUNT > 0) {{
    const edgeIdx = i % EDGE_COUNT;
    const src = E_SRC[edgeIdx];
    const tgt = E_TGT[edgeIdx];
    const flow = (time * drift * 0.3 + i * 0.001) % 1.0;
    fx = (CX[src] + (CX[tgt] - CX[src]) * flow) * trailMix;
    fy = (CY[src] + (CY[tgt] - CY[src]) * flow) * trailMix;
    fz = (CZ[src] + (CZ[tgt] - CZ[src]) * flow) * trailMix;
}}

const finalX = (bx + ox + Math.sin(phase) * breathe + fx) * spread * 0.01;
const finalY = (by + oy + Math.cos(phase * 1.3) * breathe + fy) * spread * 0.01;
const finalZ = (bz + oz + Math.sin(phase * 0.7) * breathe * 0.5 + fz) * spread * 0.01 * depth;

target.set(finalX, finalY, finalZ);

// Color: hue from concept category, lightness from salience, saturation high
const hue = HUE[conceptIdx];
const lightness = 0.25 + sal * 0.45 + Math.sin(time * 2.0 + conceptIdx) * pulse * 0.1;
const saturation = 0.7 + sal * 0.3;
color.setHSL(hue, saturation, lightness);

// HUD and annotations (i===0 only)
if (i === 0) {{
    setInfo("DHARMA Semantic Field", "{config.total_concepts} concepts | {config.total_edges} edges | drift: " + drift.toFixed(2));
    annotate("hottest", new THREE.Vector3({q(hottest['x'])} * spread * 0.01, {q(hottest['y'])} * spread * 0.01, {q(hottest['z'])} * spread * 0.01 * depth), "{config.concepts[hottest_idx].name if config.concepts else 'none'}");
}}"""


def _generate_empty_viz() -> str:
    """Fallback visualization when no data is available."""
    return """// DHARMA — No semantic data loaded
const spread = addControl("spread", "Spread", 10, 100, 50);
const speed = addControl("speed", "Speed", 0, 5, 1.0);
const t = i / count;
const angle = t * 6.2831853 * 20 + time * speed;
const r = 10 + t * spread;
target.set(Math.cos(angle) * r, Math.sin(angle) * r, (t - 0.5) * spread);
color.setHSL(t, 0.8, 0.5 + Math.sin(time + t * 10) * 0.2);
if (i === 0) setInfo("DHARMA Awaiting Data", "Run: dgc semantic digest");"""


# ── File Output ──────────────────────────────────────────────────────────────

def save_visualization(config: SemanticParticleConfig, name: str = "semantic_field") -> Path:
    """Save the particle function and config to disk."""
    VIZ_DIR.mkdir(parents=True, exist_ok=True)

    # Save the JS function body
    js_path = VIZ_DIR / f"{name}.js"
    js_code = generate_particle_function(config)
    js_path.write_text(js_code)

    # Save the config as JSON (for dashboard consumption)
    config_path = VIZ_DIR / f"{name}.json"
    config_data = {
        "title": config.title,
        "description": config.description,
        "total_concepts": config.total_concepts,
        "total_edges": config.total_edges,
        "cluster_count": config.cluster_count,
        "points": project_concepts_3d(config),
    }
    config_path.write_text(json.dumps(config_data, indent=2))

    return js_path


def generate_and_save() -> tuple[Path, str]:
    """One-shot: build from graph, generate JS, save, return path + code."""
    config = build_from_semantic_graph()
    path = save_visualization(config)
    code = generate_particle_function(config)
    return path, code


# ── Browser Injection ────────────────────────────────────────────────────────

async def inject_into_casberry(code: str) -> dict:
    """
    Use Playwright to inject a particle function into the live Casberry page.
    Returns screenshot path and page state.
    """
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-gpu'])
        page = await browser.new_page(viewport={'width': 1920, 'height': 1080})

        await page.goto('https://particles.casberry.in/', timeout=30000)
        await page.wait_for_timeout(3000)

        # Close the guide modal if present
        try:
            await page.click('button:has-text("INITIALIZE NEURAL LINK")', timeout=3000)
            await page.wait_for_timeout(500)
        except Exception:
            pass

        # Inject code into the custom code editor
        await page.fill('#customName', 'DHARMA SEMANTIC FIELD')
        await page.fill('#customCode', code)

        # Execute via runCustom
        await page.evaluate(f'''() => {{
            window.runCustom(document.getElementById('customCode').value, 'DHARMA SEMANTIC FIELD');
        }}''')

        # Let it render
        await page.wait_for_timeout(3000)

        # Screenshot
        ss_dir = Path.home() / ".dharma" / "visualizations" / "screenshots"
        ss_dir.mkdir(parents=True, exist_ok=True)
        ss_path = ss_dir / "semantic_field.png"
        await page.screenshot(path=str(ss_path))

        # Get HUD info
        hud = await page.evaluate('''() => {
            const title = document.getElementById('hud-title');
            const desc = document.getElementById('hud-desc');
            return {
                title: title ? title.textContent : '',
                desc: desc ? desc.textContent : ''
            };
        }''')

        await browser.close()

        return {
            "screenshot": str(ss_path),
            "hud": hud,
            "status": "rendered"
        }


# ── CLI Entry Point ──────────────────────────────────────────────────────────

def main():
    """Generate and optionally inject semantic visualization."""
    import sys

    config = build_from_semantic_graph()
    path = save_visualization(config)
    code = generate_particle_function(config)

    print(f"Generated: {path}")
    print(f"Concepts: {config.total_concepts}")
    print(f"Edges: {config.total_edges}")
    print(f"Clusters: {config.cluster_count}")
    print(f"Code length: {len(code)} chars")

    if "--inject" in sys.argv:
        import asyncio
        result = asyncio.run(inject_into_casberry(code))
        print(f"Screenshot: {result['screenshot']}")
        print(f"HUD: {result['hud']}")
    else:
        print(f"\nTo inject into Casberry:")
        print(f"  python -m dharma_swarm.casberry_bridge --inject")
        print(f"\nOr paste the code from: {path}")


if __name__ == "__main__":
    main()
