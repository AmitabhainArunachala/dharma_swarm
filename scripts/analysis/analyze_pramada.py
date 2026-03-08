#!/usr/bin/env python3
"""Analyze pramāda patterns in JIKOKU logs.

Identifies:
1. Outlier spans (>3σ from mean)
2. Gap patterns (idle time between spans)
3. Sequential vs parallel opportunities
"""

import json
from pathlib import Path
from datetime import datetime
import statistics


def load_spans(log_path: Path) -> list:
    """Load all spans from JSONL log."""
    spans = []
    if not log_path.exists():
        return spans

    with open(log_path) as f:
        for line in f:
            if line.strip():
                spans.append(json.loads(line))
    return spans


def analyze_outliers(spans: list) -> None:
    """Find statistical outliers in span durations."""
    if not spans:
        return

    # Group by category
    by_category = {}
    for span in spans:
        cat = span['category']
        dur = span['duration_sec']
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(dur)

    print("OUTLIER ANALYSIS (durations >3σ from mean)")
    print("=" * 70)

    for category, durations in sorted(by_category.items()):
        if len(durations) < 3:
            continue  # Need at least 3 samples

        mean = statistics.mean(durations)
        stdev = statistics.stdev(durations)

        outliers = [d for d in durations if abs(d - mean) > 3 * stdev]
        if outliers:
            print(f"\n{category}:")
            print(f"  Mean: {mean*1000:.1f}ms, StdDev: {stdev*1000:.1f}ms")
            print(f"  Outliers: {len(outliers)}/{len(durations)}")
            for dur in sorted(outliers, reverse=True):
                sigma = (dur - mean) / stdev if stdev > 0 else 0
                print(f"    {dur*1000:.1f}ms ({sigma:.1f}σ)")


def analyze_gaps(spans: list) -> None:
    """Analyze idle time between consecutive spans."""
    if len(spans) < 2:
        return

    # Sort by start time
    sorted_spans = sorted(spans, key=lambda s: s['ts_start'])

    gaps = []
    for i in range(len(sorted_spans) - 1):
        end_time = datetime.fromisoformat(sorted_spans[i]['ts_end'])
        next_start = datetime.fromisoformat(sorted_spans[i+1]['ts_start'])
        gap = (next_start - end_time).total_seconds()

        if gap > 0.001:  # Only count gaps > 1ms
            gaps.append({
                'gap_sec': gap,
                'after': sorted_spans[i]['category'],
                'before': sorted_spans[i+1]['category'],
                'after_intent': sorted_spans[i]['intent'],
                'before_intent': sorted_spans[i+1]['intent'],
            })

    if not gaps:
        print("\nNO SIGNIFICANT GAPS DETECTED")
        print("=" * 70)
        print("All spans are tightly chained (<1ms gaps)")
        return

    print("\nGAP ANALYSIS (idle time between operations)")
    print("=" * 70)

    total_gap = sum(g['gap_sec'] for g in gaps)
    print(f"Total idle time: {total_gap*1000:.1f}ms across {len(gaps)} gaps")
    print(f"Average gap: {(total_gap/len(gaps))*1000:.1f}ms")
    print()

    # Top 5 largest gaps
    print("Largest gaps:")
    for i, gap in enumerate(sorted(gaps, key=lambda g: g['gap_sec'], reverse=True)[:5], 1):
        print(f"  {i}. {gap['gap_sec']*1000:.1f}ms")
        print(f"     After:  [{gap['after']}] {gap['after_intent'][:40]}")
        print(f"     Before: [{gap['before']}] {gap['before_intent'][:40]}")
        print()


def analyze_parallelization(spans: list) -> None:
    """Identify operations that could run in parallel."""
    if len(spans) < 2:
        return

    print("\nPARALLELIZATION OPPORTUNITIES")
    print("=" * 70)

    # Group sequential same-category operations
    sorted_spans = sorted(spans, key=lambda s: s['ts_start'])

    sequences = []
    current_seq = []
    current_cat = None

    for span in sorted_spans:
        cat = span['category']
        if cat == current_cat:
            current_seq.append(span)
        else:
            if len(current_seq) > 1:
                sequences.append((current_cat, current_seq))
            current_seq = [span]
            current_cat = cat

    if len(current_seq) > 1:
        sequences.append((current_cat, current_seq))

    if not sequences:
        print("No sequential same-category operations detected")
        return

    for category, seq in sequences:
        if len(seq) < 2:
            continue

        total_time = sum(s['duration_sec'] for s in seq)
        max_time = max(s['duration_sec'] for s in seq)
        speedup = total_time / max_time

        print(f"\n{category}: {len(seq)} sequential operations")
        print(f"  Sequential time: {total_time*1000:.1f}ms")
        print(f"  Parallel time: {max_time*1000:.1f}ms")
        print(f"  Potential speedup: {speedup:.2f}x")


def main():
    log_path = Path.home() / ".dharma" / "jikoku" / "baseline.jsonl"

    print("PRAMĀDA ANALYSIS")
    print("=" * 70)
    print(f"Log: {log_path}")
    print()

    spans = load_spans(log_path)
    if not spans:
        print("No spans found")
        return

    print(f"Total spans: {len(spans)}")
    print()

    analyze_outliers(spans)
    analyze_gaps(spans)
    analyze_parallelization(spans)

    print()
    print("=" * 70)
    print("ANALYSIS COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
