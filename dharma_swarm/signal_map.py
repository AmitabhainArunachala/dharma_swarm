"""
Signal Map — Living consciousness archaeology tracker

The signal map is a living JSON structure that tracks semantic density of files
across the entire ecosystem. As agents scan and rescan files, the map builds
confidence in which files are truly load-bearing.

Key principles:
- Aggregate scores increase confidence with multiple scans
- Confidence decay over time prevents stale information
- Blind spot tracking ensures systematic coverage
- Agent briefings provide compressed context for new agents

Usage:
    >>> from dharma_swarm.signal_map import SignalMap
    >>> sm = SignalMap.load()
    >>> sm.add_score("/path/to/file.md", 9.5, criteria={...}, scan_id="scan-001", domain="mechanistic")
    >>> sm.save()
    >>> brief = sm.as_agent_briefing(max_files=10)
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json
import statistics


@dataclass
class ScanScore:
    """A single scan score for a file"""
    scan_id: str
    composite: float  # 0-10 composite score
    criteria: Dict[str, int]  # 7 criteria scores (0-10 each)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class SignalMapEntry:
    """Entry for a single file in the signal map"""
    path: str
    scores: List[ScanScore]  # All scans of this file
    aggregate: float  # Weighted average of scores
    confidence: float  # 0.0-1.0 based on coverage + age
    coverage_count: int  # Number of times scanned
    domain: str  # mechanistic, phenomenological, engineering, contemplative, meta-context
    one_liner: str  # Brief description
    referenced_by: List[str] = field(default_factory=list)  # Files that reference this one
    last_file_modified: Optional[str] = None  # Filesystem mtime
    last_scanned: Optional[str] = None  # When last scanned

    def add_score(self, score: ScanScore):
        """Add a new scan score and update aggregate"""
        self.scores.append(score)
        self.coverage_count = len(self.scores)
        self.last_scanned = score.timestamp
        
        # Update aggregate (simple average for now, could weight by recency)
        self.aggregate = statistics.mean([s.composite for s in self.scores])
        
        # Update confidence based on coverage (0.5 base, +0.1 per scan, max 0.9)
        self.confidence = min(0.5 + (self.coverage_count - 1) * 0.1, 0.9)

    def decay_confidence(self, decay_rate: float = 0.1):
        """Decay confidence over time to prevent stale information"""
        self.confidence = max(0.1, self.confidence - decay_rate)


@dataclass
class ScanHistory:
    """Record of a scan pass"""
    id: str
    timestamp: str
    domains_covered: List[str]
    files_scored: int
    agent: str


class SignalMap:
    """Living map of semantic density across the ecosystem"""
    
    DEFAULT_PATH = Path.home() / ".dharma" / "signal_map.json"
    
    def __init__(
        self,
        files: Dict[str, SignalMapEntry] = None,
        blind_spots: List[str] = None,
        scan_history: List[ScanHistory] = None,
        version: int = 1
    ):
        self.files = files or {}
        self.blind_spots = blind_spots or []
        self.scan_history = scan_history or []
        self.version = version
        self.last_updated = datetime.now(timezone.utc).isoformat()

    @classmethod
    def load(cls, path: Path = None) -> "SignalMap":
        """Load signal map from JSON file"""
        path = path or cls.DEFAULT_PATH
        
        if not path.exists():
            return cls()  # Return empty map if no file exists
        
        with open(path, 'r') as f:
            data = json.load(f)
        
        # Reconstruct entries from JSON
        files = {}
        for file_path, file_data in data.get("files", {}).items():
            scores = [
                ScanScore(
                    scan_id=s["scan_id"],
                    composite=s["composite"],
                    criteria=s["criteria"],
                    timestamp=s.get("timestamp", datetime.now(timezone.utc).isoformat())
                )
                for s in file_data.get("scores", [])
            ]
            
            files[file_path] = SignalMapEntry(
                path=file_path,
                scores=scores,
                aggregate=file_data.get("aggregate", 0.0),
                confidence=file_data.get("confidence", 0.5),
                coverage_count=file_data.get("coverage_count", len(scores)),
                domain=file_data.get("domain", "unknown"),
                one_liner=file_data.get("one_liner", ""),
                referenced_by=file_data.get("referenced_by", []),
                last_file_modified=file_data.get("last_file_modified"),
                last_scanned=scores[-1].timestamp if scores else None
            )
        
        scan_history = [
            ScanHistory(**hist) for hist in data.get("scan_history", [])
        ]
        
        return cls(
            files=files,
            blind_spots=data.get("blind_spots", []),
            scan_history=scan_history,
            version=data.get("version", 1)
        )

    def save(self, path: Path = None):
        """Save signal map to JSON file"""
        path = path or self.DEFAULT_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert to JSON-serializable format
        data = {
            "version": self.version,
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "files": {
                file_path: {
                    "scores": [asdict(s) for s in entry.scores],
                    "aggregate": entry.aggregate,
                    "confidence": entry.confidence,
                    "coverage_count": entry.coverage_count,
                    "domain": entry.domain,
                    "one_liner": entry.one_liner,
                    "referenced_by": entry.referenced_by,
                    "last_file_modified": entry.last_file_modified,
                    "last_scanned": entry.last_scanned
                }
                for file_path, entry in self.files.items()
            },
            "blind_spots": self.blind_spots,
            "scan_history": [asdict(hist) for hist in self.scan_history]
        }
        
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)

    def add_score(
        self,
        file_path: str,
        composite: float,
        criteria: Dict[str, int],
        scan_id: str,
        domain: str,
        one_liner: str = ""
    ):
        """Add a scan score for a file"""
        score = ScanScore(
            scan_id=scan_id,
            composite=composite,
            criteria=criteria
        )
        
        if file_path not in self.files:
            self.files[file_path] = SignalMapEntry(
                path=file_path,
                scores=[],
                aggregate=0.0,
                confidence=0.5,
                coverage_count=0,
                domain=domain,
                one_liner=one_liner
            )
        
        self.files[file_path].add_score(score)

    def merge_scan_results(
        self,
        scan_results: Dict[str, Tuple[float, Dict[str, int], str, str]],
        scan_id: str
    ):
        """Merge a batch of scan results
        
        Args:
            scan_results: {file_path: (composite, criteria, domain, one_liner)}
            scan_id: ID for this scan pass
        """
        for file_path, (composite, criteria, domain, one_liner) in scan_results.items():
            self.add_score(file_path, composite, criteria, scan_id, domain, one_liner)

    def get_blind_spots(self) -> List[str]:
        """Get documented blind spots"""
        return self.blind_spots

    def add_blind_spot(self, description: str):
        """Add a new blind spot"""
        if description not in self.blind_spots:
            self.blind_spots.append(description)

    def get_top_n(self, n: int = 25, min_confidence: float = 0.0) -> List[SignalMapEntry]:
        """Get top N files by aggregate score
        
        Args:
            n: Number of files to return
            min_confidence: Minimum confidence threshold
        
        Returns:
            List of entries sorted by aggregate score descending
        """
        filtered = [
            entry for entry in self.files.values()
            if entry.confidence >= min_confidence
        ]
        sorted_entries = sorted(filtered, key=lambda e: e.aggregate, reverse=True)
        return sorted_entries[:n]

    def get_low_confidence(self, threshold: float = 0.6) -> List[SignalMapEntry]:
        """Get files with confidence below threshold
        
        These are candidates for re-scanning to build confidence.
        """
        return [
            entry for entry in self.files.values()
            if entry.confidence < threshold
        ]

    def decay_all(self, decay_rate: float = 0.1):
        """Decay confidence for all entries
        
        Call this periodically (e.g., monthly) to prevent stale information
        from maintaining artificially high confidence.
        """
        for entry in self.files.values():
            entry.decay_confidence(decay_rate)

    def as_agent_briefing(
        self,
        max_files: int = 25,
        include_blind_spots: bool = True,
        tier_thresholds: Tuple[float, float] = (9.5, 9.0)
    ) -> str:
        """Generate agent briefing text
        
        Args:
            max_files: Maximum files to include
            include_blind_spots: Include blind spot list
            tier_thresholds: (tier1_min, tier2_min) for Load-Bearing/Structural
        
        Returns:
            Markdown-formatted briefing
        """
        top_files = self.get_top_n(max_files)
        
        # Tier files
        tier1 = [f for f in top_files if f.aggregate >= tier_thresholds[0]]
        tier2 = [f for f in top_files if tier_thresholds[1] <= f.aggregate < tier_thresholds[0]]
        tier3 = [f for f in top_files if f.aggregate < tier_thresholds[1]]
        
        lines = [
            "# Signal Map Agent Briefing",
            f"**Generated**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            f"**Total files tracked**: {len(self.files)}",
            f"**Total scans**: {len(self.scan_history)}",
            "",
            "## Tier 1: Load-Bearing Walls (9.5+)",
            ""
        ]
        
        for entry in tier1:
            confidence_bar = "■" * int(entry.confidence * 10)
            lines.append(
                f"- **{Path(entry.path).name}** ({entry.aggregate:.1f}) "
                f"[{confidence_bar}] — {entry.one_liner}"
            )
        
        if tier2:
            lines.extend([
                "",
                "## Tier 2: Structural Beams (9.0-9.4)",
                ""
            ])
            for entry in tier2:
                confidence_bar = "■" * int(entry.confidence * 10)
                lines.append(
                    f"- **{Path(entry.path).name}** ({entry.aggregate:.1f}) "
                    f"[{confidence_bar}] — {entry.one_liner}"
                )
        
        if tier3:
            lines.extend([
                "",
                "## Tier 3: Active Connective Tissue (8.5-8.9)",
                ""
            ])
            for entry in tier3[:10]:  # Limit tier3 to avoid bloat
                confidence_bar = "■" * int(entry.confidence * 10)
                lines.append(
                    f"- **{Path(entry.path).name}** ({entry.aggregate:.1f}) "
                    f"[{confidence_bar}] — {entry.one_liner}"
                )
        
        if include_blind_spots and self.blind_spots:
            lines.extend([
                "",
                "## Known Blind Spots",
                ""
            ])
            for spot in self.blind_spots:
                lines.append(f"- {spot}")
        
        return "\n".join(lines)

    def get_by_domain(self, domain: str) -> List[SignalMapEntry]:
        """Get all files in a specific domain"""
        return [
            entry for entry in self.files.values()
            if entry.domain == domain
        ]

    def get_stats(self) -> Dict:
        """Get statistics about the signal map"""
        if not self.files:
            return {
                "total_files": 0,
                "avg_score": 0.0,
                "avg_confidence": 0.0,
                "domains": {},
                "total_scans": len(self.scan_history),
                "blind_spots": len(self.blind_spots)
            }
        
        domain_counts = {}
        for entry in self.files.values():
            domain_counts[entry.domain] = domain_counts.get(entry.domain, 0) + 1
        
        return {
            "total_files": len(self.files),
            "avg_score": statistics.mean([e.aggregate for e in self.files.values()]),
            "avg_confidence": statistics.mean([e.confidence for e in self.files.values()]),
            "domains": domain_counts,
            "total_scans": len(self.scan_history),
            "blind_spots": len(self.blind_spots)
        }
