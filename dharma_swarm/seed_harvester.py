"""
SEED HARVESTER — The Discerning Economic Organism's Input Layer

Scans all seed locations across the ecosystem, deduplicates, grades each seed
on the YSD (Yosemite Decimal System) scale, checks market reality, detects naff,
and outputs a ranked BACKLOG.json.

The organism's taste lives HERE. If this function can't tell a 5.9 from a 5.13,
the whole loop ships garbage.

Usage:
    python3 -m dharma_swarm.seed_harvester [--grade] [--output PATH]
"""

import json
import re
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# YSD Scale — Yosemite Decimal System for Ideas
# ---------------------------------------------------------------------------
# IMPORTANT: Climbing grades 5.6, 5.9, 5.11 don't work as floats (5.11 < 5.6).
# We use an internal 0-100 scale and display as YSD strings.

YSD_THRESHOLDS = [
    (0,  "KILL — below threshold, waste of compute"),
    (20, "NAFF — generic, no moat, commodity"),
    (40, "DECENT — ship only if <4 hours, test market"),
    (60, "GOOD — real differentiation, real market. BUILD."),
    (80, "EXCEPTIONAL — competitive moat. BUILD + PROTECT."),
    (90, "TRANSCENDENT — only-you-can-do-this. BUILD + FUND."),
]

# Display mapping: internal score → YSD display string
def internal_to_ysd_display(score: int) -> str:
    """Convert internal 0-100 to YSD display like '5.11a'."""
    if score < 20: return f"5.{6 + score // 5}"
    if score < 40: return f"5.{9}{'abc'[min(score-20, 2)//8:][0] if score > 25 else ''}"
    if score < 60: return f"5.10{'abcd'[min((score-40)//5, 3)]}"
    if score < 80: return f"5.11{'abcd'[min((score-60)//5, 3)]}"
    if score < 90: return f"5.13{'abcd'[min((score-80)//3, 3)]}"
    return f"5.14{'abcd'[min((score-90)//3, 3)]}"


def ysd_label(score: int) -> str:
    """Get action label from internal score."""
    result = YSD_THRESHOLDS[0][1]
    for threshold, label in YSD_THRESHOLDS:
        if score >= threshold:
            result = label
    return result


@dataclass
class Seed:
    """A single idea/project/product seed."""
    id: str
    name: str
    description: str
    source_file: str
    source_type: str  # lost_ideas | micro_saas | moonshot | scratch | core

    # Grading (filled by grade_seed) — internal 0-100 scale
    ysd_score: int = 0        # 0-100 internal score
    ysd_display: str = ""     # "5.11a" style display
    ysd_label: str = ""
    existing_code_pct: float = 0.0
    time_to_ship_hours: float = 999.0
    free_model_feasible: bool = True
    naff_score: float = 0.0      # 0 = not naff, 1 = pure commodity slop
    moat: str = ""
    first_dollar_path: str = ""
    revenue_model: str = ""
    market_signal: str = ""
    kill_history: int = 0
    kill_reasons: list = field(default_factory=list)
    status: str = "raw"  # raw | graded | dispatched | shipped | killed

    # Composite score for ranking
    composite_score: float = 0.0

    def to_dict(self):
        return asdict(self)


# ---------------------------------------------------------------------------
# SEED EXTRACTION — Parse seeds from each source format
# ---------------------------------------------------------------------------

def _make_id(name: str) -> str:
    """Deterministic ID from name for dedup."""
    return hashlib.sha256(name.lower().strip().encode()).hexdigest()[:12]


def extract_from_lost_ideas(path: Path) -> list[Seed]:
    """Parse LOST_IDEAS_RECOVERY.md format."""
    seeds = []
    if not path.exists():
        return seeds

    text = path.read_text()
    # Pattern: #### N.N Title\n**What:** description
    blocks = re.split(r'####\s+', text)
    for block in blocks[1:]:  # skip header
        lines = block.strip().split('\n')
        if not lines:
            continue
        name_line = lines[0].strip()
        # Extract name (remove numbering)
        name = re.sub(r'^\d+\.\d+\s+', '', name_line).strip()

        description = ""
        status = "raw"
        kill_count = 0
        kill_reasons = []
        revenue_model = ""

        for line in lines[1:]:
            if line.startswith('**What:**'):
                description = line.replace('**What:**', '').strip()
            elif '**Status:**' in line:
                if 'KILLED' in line.upper():
                    status = 'killed'
                    kill_count += 1
                elif 'COMPLETE' in line.upper() or 'BUILT' in line.upper():
                    status = 'built'
            elif '**Why killed' in line.lower():
                reason = line.split(':', 1)[-1].strip() if ':' in line else line
                kill_reasons.append(reason)
            elif '**Revenue' in line:
                revenue_model = line.split(':', 1)[-1].strip() if ':' in line else ""

        if name and description:
            seeds.append(Seed(
                id=_make_id(name),
                name=name,
                description=description,
                source_file=str(path),
                source_type="lost_ideas",
                status=status,
                kill_history=kill_count,
                kill_reasons=kill_reasons,
                revenue_model=revenue_model,
            ))
    return seeds


def extract_from_micro_saas(path: Path) -> list[Seed]:
    """Parse TOP_20_AI_AGENT_MICRO_SAAS_OPPORTUNITIES.md format."""
    seeds = []
    if not path.exists():
        return seeds

    text = path.read_text()
    # Pattern: ## #N. TITLE\n**Composite Score: X**
    blocks = re.split(r'## #\d+\.?\s+', text)
    for block in blocks[1:]:
        lines = block.strip().split('\n')
        if not lines:
            continue
        name = lines[0].strip()

        description = ""
        composite = 0.0
        market_size = ""

        for line in lines[1:]:
            if '**Composite Score:' in line:
                match = re.search(r'(\d+\.?\d*)', line)
                if match:
                    composite = float(match.group(1))
            elif line.startswith('**The Problem**:'):
                description = line.replace('**The Problem**:', '').strip()
            elif '**Market Size**:' in line:
                market_size = line.replace('**Market Size**:', '').strip()

        if name:
            seeds.append(Seed(
                id=_make_id(name),
                name=name,
                description=description or name,
                source_file=str(path),
                source_type="micro_saas",
                market_signal=market_size,
                composite_score=composite,
                revenue_model="SaaS subscription",
                first_dollar_path="Vertical micro-SaaS, $19-99/month",
            ))
    return seeds


def extract_from_moonshots(path: Path) -> list[Seed]:
    """Parse top-30-scored.md format."""
    seeds = []
    if not path.exists():
        return seeds

    text = path.read_text()
    # Pattern: ### #N — TITLE — Score: X.XX
    blocks = re.split(r'### #\d+\s*—\s*', text)
    for block in blocks[1:]:
        lines = block.strip().split('\n')
        if not lines:
            continue

        # First line: "TITLE — Score: X.XX"
        first = lines[0]
        parts = first.split('— Score:')
        name = parts[0].strip() if parts else first.strip()
        score = 0.0
        if len(parts) > 1:
            match = re.search(r'(\d+\.?\d*)', parts[1])
            if match:
                score = float(match.group(1))

        description = ""
        for line in lines[1:]:
            if line.startswith('**Evidence**:'):
                description = line.replace('**Evidence**:', '').strip()
                break
        if not description:
            # Use first non-table, non-empty line
            for line in lines[1:]:
                line = line.strip()
                if line and not line.startswith('|') and not line.startswith('---'):
                    description = line
                    break

        if name:
            seeds.append(Seed(
                id=_make_id(name),
                name=name,
                description=description or name,
                source_file=str(path),
                source_type="moonshot",
                composite_score=score,
            ))
    return seeds


def extract_from_scratch_dir(dir_path: Path) -> list[Seed]:
    """Scan scratch directory for idea-containing files."""
    seeds = []
    if not dir_path.exists():
        return seeds

    keywords = re.compile(
        r'(revenue|product|ship|build|idea|pipeline|business|market|monetiz|saas)',
        re.IGNORECASE
    )
    for f in dir_path.glob('*.md'):
        try:
            text = f.read_text(errors='replace')[:5000]  # First 5K chars
            if keywords.search(text):
                # Extract first heading as name
                heading = ""
                for line in text.split('\n'):
                    if line.startswith('#'):
                        heading = line.lstrip('#').strip()
                        break
                if heading:
                    first_para = ""
                    for line in text.split('\n'):
                        line = line.strip()
                        if line and not line.startswith('#') and len(line) > 20:
                            first_para = line[:200]
                            break
                    seeds.append(Seed(
                        id=_make_id(heading),
                        name=heading,
                        description=first_para or heading,
                        source_file=str(f),
                        source_type="scratch",
                    ))
        except Exception:
            continue
    return seeds


# ---------------------------------------------------------------------------
# NAFF DETECTOR — The Taste Function
# ---------------------------------------------------------------------------

NAFF_PATTERNS = [
    (r'prompt\s*(library|collection|pack)', 0.8, "Generic prompt library"),
    (r'generic.*template', 0.7, "Generic templates"),
    (r'ai\s+power\s+prompts', 0.9, "AI power prompts = pure commodity"),
    (r'worldbuilding.*toolkit', 0.4, "Niche but undifferentiated"),
    (r'(chatbot|assistant)\s+for\s+', 0.5, "Chatbot for X = crowded"),
    (r'todo\s*(app|list|manager)', 0.9, "Todo app = ultimate naff"),
    (r'blog.*generator', 0.6, "Blog generators everywhere"),
]

MOAT_BOOSTERS = [
    (r'r_v|rv.metric|contraction|geometric', -0.5, "R_V is unique research"),
    (r'dharma_swarm|telos.gate|darwin.engine', -0.4, "dharma_swarm stack is unique"),
    (r'welfare.ton|jagat.kalyan', -0.4, "JK is unique framing"),
    (r'contemplat|witness|swabhaav', -0.3, "Contemplative computing is unique"),
    (r'phoenix|ura|phase.transition', -0.3, "Behavioral research is unique"),
]


def compute_naff_score(seed: Seed) -> float:
    """0.0 = not naff, 1.0 = pure commodity slop."""
    text = f"{seed.name} {seed.description}".lower()
    score = 0.0

    for pattern, weight, _ in NAFF_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            score += weight

    for pattern, weight, _ in MOAT_BOOSTERS:
        if re.search(pattern, text, re.IGNORECASE):
            score += weight  # weight is negative, so this reduces naff

    # Previously killed = naff signal
    if seed.kill_history > 0:
        score += 0.2 * seed.kill_history

    return max(0.0, min(1.0, score))


def compute_moat(seed: Seed) -> str:
    """What makes this OURS?"""
    text = f"{seed.name} {seed.description}".lower()
    moats = []
    for pattern, _, label in MOAT_BOOSTERS:
        if re.search(pattern, text, re.IGNORECASE):
            moats.append(label)
    return "; ".join(moats) if moats else "No clear moat"


# ---------------------------------------------------------------------------
# YSD GRADING — The Core Judgment
# ---------------------------------------------------------------------------

def grade_seed(seed: Seed) -> Seed:
    """Apply YSD grading to a seed. Internal 0-100 scale. Mutates and returns."""

    naff = compute_naff_score(seed)
    seed.naff_score = naff
    seed.moat = compute_moat(seed)

    # Base score from source type (0-100 scale)
    base = {
        'micro_saas': 50,    # Market-validated = start at DECENT
        'moonshot': 55,      # Scored ideas = slightly higher
        'lost_ideas': 35,    # Mixed bag = start at NAFF boundary
        'scratch': 25,       # Unvalidated = NAFF territory
        'core': 45,          # Protocols = near DECENT
    }.get(seed.source_type, 25)

    # Adjust for naff (high naff = major penalty)
    score = base - int(naff * 30)

    # Adjust for moat (having unique advantages boosts significantly)
    if seed.moat != "No clear moat":
        moat_count = seed.moat.count(';') + 1
        score += moat_count * 12  # Each moat adds ~12 points

    # Adjust for existing composite score from source research
    if seed.composite_score > 0:
        if seed.source_type == 'micro_saas':
            score += int((seed.composite_score / 120) * 25)  # Up to +25
        elif seed.source_type == 'moonshot':
            score += int((seed.composite_score / 10) * 25)  # Up to +25

    # Kill history penalty
    if seed.kill_history > 0:
        score -= seed.kill_history * 8  # -8 per kill

    # Already built bonus
    if seed.status == 'built':
        score += 15
        seed.time_to_ship_hours = 8.0

    # Clamp 0-100
    score = max(0, min(100, score))
    seed.ysd_score = score
    seed.ysd_display = internal_to_ysd_display(score)
    seed.ysd_label = ysd_label(score)

    # Composite for ranking (weighted blend)
    ship_factor = max(0.01, 1.0 / max(seed.time_to_ship_hours, 1))
    seed.composite_score = (
        score * 1.0 +
        (1 - naff) * 20 +
        ship_factor * 10 +
        (5 if seed.free_model_feasible else 0)
    )

    return seed


# ---------------------------------------------------------------------------
# HARVESTER — Scan, Deduplicate, Grade, Rank
# ---------------------------------------------------------------------------

def harvest(output_path: Optional[Path] = None) -> list[Seed]:
    """Scan all seed sources, deduplicate, grade, rank."""
    home = Path.home()
    all_seeds: list[Seed] = []

    # Source 1: Lost Ideas Recovery
    lost = home / "agni-workspace" / "scratch" / "LOST_IDEAS_RECOVERY.md"
    all_seeds.extend(extract_from_lost_ideas(lost))
    logger.info(f"Lost ideas: {len(all_seeds)} seeds")

    # Source 2: Micro-SaaS research
    micro = home / "dharma_swarm" / "spec-forge" / "micro-saas-research" / "TOP_20_AI_AGENT_MICRO_SAAS_OPPORTUNITIES.md"
    micro_seeds = extract_from_micro_saas(micro)
    all_seeds.extend(micro_seeds)
    logger.info(f"Micro-SaaS: {len(micro_seeds)} seeds")

    # Source 3: Moonshot ideas
    moon = home / "dharma_swarm" / "spec-forge" / "moonshot-agentic-ai" / "01-top-30-scored.md"
    moon_seeds = extract_from_moonshots(moon)
    all_seeds.extend(moon_seeds)
    logger.info(f"Moonshots: {len(moon_seeds)} seeds")

    # Source 4: AGNI scratch directory
    scratch = home / "agni-workspace" / "scratch"
    scratch_seeds = extract_from_scratch_dir(scratch)
    all_seeds.extend(scratch_seeds)
    logger.info(f"Scratch: {len(scratch_seeds)} seeds")

    # Deduplicate by ID
    seen = {}
    unique = []
    for seed in all_seeds:
        if seed.id not in seen:
            seen[seed.id] = seed
            unique.append(seed)
        else:
            # Merge: keep higher-quality source
            existing = seen[seed.id]
            if seed.composite_score > existing.composite_score:
                seen[seed.id] = seed
                unique = [s for s in unique if s.id != seed.id] + [seed]

    logger.info(f"After dedup: {len(unique)} unique seeds")

    # Grade all
    for seed in unique:
        grade_seed(seed)

    # Sort by composite score descending
    unique.sort(key=lambda s: s.composite_score, reverse=True)

    # Output
    out = output_path or Path.home() / ".dharma" / "seeds" / "BACKLOG.json"
    out.parent.mkdir(parents=True, exist_ok=True)

    backlog = {
        'harvested_at': datetime.now(timezone.utc).isoformat(),
        'total_seeds': len(unique),
        'by_ysd_grade': {},
        'seeds': [s.to_dict() for s in unique],
    }

    # Count by grade
    for s in unique:
        label = s.ysd_label.split('—')[0].strip() if s.ysd_label else 'UNKNOWN'
        backlog['by_ysd_grade'][label] = backlog['by_ysd_grade'].get(label, 0) + 1

    out.write_text(json.dumps(backlog, indent=2))
    logger.info(f"Backlog written to {out} ({len(unique)} seeds)")

    # Print summary
    print(f"\n{'='*60}")
    print(f"SEED HARVESTER — {len(unique)} seeds graded")
    print(f"{'='*60}")
    print(f"\nYSD Distribution:")
    for label, count in sorted(backlog['by_ysd_grade'].items()):
        print(f"  {label}: {count}")
    print(f"\nTop 10 by composite score:")
    for i, s in enumerate(unique[:10], 1):
        naff_flag = " [NAFF]" if s.naff_score > 0.5 else ""
        print(f"  {i:2d}. [{s.ysd_display:>6s}] {s.name[:50]:50s} ({s.source_type}){naff_flag}")
    print(f"\nBacklog: {out}")
    return unique


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import argparse
    logging.basicConfig(level=logging.INFO, format='%(message)s')

    parser = argparse.ArgumentParser(description='Seed Harvester — The Discerning Economic Organism')
    parser.add_argument('--output', type=Path, default=None, help='Output path for BACKLOG.json')
    args = parser.parse_args()

    harvest(output_path=args.output)
