#!/usr/bin/env python3
"""Economic Fitness Demo — Real $ ROI from code mutations.

Shows how dharma_swarm tracks the actual dollar value created by code changes
based on API cost savings, time savings, throughput gains, and maintenance costs.

Example outputs:
    - "$21,450/year — optimize loop mutation" (huge win!)
    - "-$8,200/year — added complexity regression" (costly mistake)
    - "$0/year — refactoring with no performance change" (neutral)
"""

from dharma_swarm.economic_fitness import (
    evaluate_economic_fitness,
    format_economic_report,
    EconomicMetrics,
)


def demo_huge_win():
    """Mutation that dramatically improves performance → big $ ROI."""
    print("\n" + "=" * 60)
    print("EXAMPLE 1: Huge Win — Vectorized Loop Optimization")
    print("=" * 60)

    # Before: naive Python loop
    baseline = {
        "wall_clock_ms": 1200,  # Slow
        "api_calls": 5,         # Many calls
    }

    # After: NumPy vectorization
    test = {
        "wall_clock_ms": 180,   # 6.6x speedup!
        "api_calls": 3,         # Fewer calls
        "diff": "- for i in range(len(data)):\n-     result.append(compute(data[i]))\n+ result = np.vectorize(compute)(data)"
    }

    fitness, metrics = evaluate_economic_fitness(
        baseline, test, usage_freq_per_day=1000
    )

    print(format_economic_report(metrics, usage_freq=1000))
    print(f"\n[Evolution Fitness Score: {fitness:.3f}/1.0]\n")


def demo_regression():
    """Mutation that makes things worse → negative $ ROI."""
    print("\n" + "=" * 60)
    print("EXAMPLE 2: Costly Regression — Added Unnecessary Complexity")
    print("=" * 60)

    # Before: simple, fast
    baseline = {
        "wall_clock_ms": 500,
        "api_calls": 2,
    }

    # After: slower, more complex
    test = {
        "wall_clock_ms": 1500,  # 3x slower!
        "api_calls": 5,         # More API calls
        "diff": "+ # Added 50 lines of unnecessary abstraction\n+ class AbstractFactoryBuilder:\n+     ...(45 more lines)"
    }

    fitness, metrics = evaluate_economic_fitness(
        baseline, test, usage_freq_per_day=1000
    )

    print(format_economic_report(metrics, usage_freq=1000))
    print(f"\n[Evolution Fitness Score: {fitness:.3f}/1.0]")
    print("[Darwin Engine would REJECT this mutation]\n")


def demo_neutral():
    """Refactoring with no performance change → neutral ROI."""
    print("\n" + "=" * 60)
    print("EXAMPLE 3: Neutral — Refactoring Without Performance Change")
    print("=" * 60)

    # Before
    baseline = {
        "wall_clock_ms": 800,
        "api_calls": 3,
    }

    # After: same performance, better readability
    test = {
        "wall_clock_ms": 810,   # Negligible difference
        "api_calls": 3,         # Same
        "diff": "+ # Extract function for readability\n+ def validate_input(data):\n+     return data is not None"
    }

    fitness, metrics = evaluate_economic_fitness(
        baseline, test, usage_freq_per_day=1000
    )

    print(format_economic_report(metrics, usage_freq=1000))
    print(f"\n[Evolution Fitness Score: {fitness:.3f}/1.0]")
    print("[Darwin Engine: NEUTRAL — keep if improves elegance/readability]\n")


def demo_custom_usage_frequency():
    """Show how usage frequency affects annual ROI."""
    print("\n" + "=" * 60)
    print("EXAMPLE 4: High-Frequency Code Path — 100K calls/day")
    print("=" * 60)

    baseline = {
        "wall_clock_ms": 100,
        "api_calls": 2,
    }

    test = {
        "wall_clock_ms": 50,    # 2x speedup
        "api_calls": 1,         # 1 fewer call
        "diff": "+ # Cached result\n+ @lru_cache(maxsize=1000)\n+ def expensive_compute(x):"
    }

    # High frequency = 100x bigger impact!
    fitness, metrics = evaluate_economic_fitness(
        baseline, test, usage_freq_per_day=100_000  # Hot path!
    )

    print(format_economic_report(metrics, usage_freq=100_000))
    print(f"\n[Evolution Fitness Score: {fitness:.3f}/1.0]")
    print("[Hot path optimization = HUGE business value]\n")


if __name__ == "__main__":
    print("\n" + "█" * 60)
    print("█" + " " * 58 + "█")
    print("█  DHARMA SWARM — Economic Fitness Demo" + " " * 18 + "█")
    print("█  Tracking Real $$$ ROI from Code Mutations" + " " * 15 + "█")
    print("█" + " " * 58 + "█")
    print("█" * 60)

    demo_huge_win()
    demo_regression()
    demo_neutral()
    demo_custom_usage_frequency()

    print("\n" + "=" * 60)
    print("KEY INSIGHT")
    print("=" * 60)
    print("""
Darwin Engine uses these metrics to select profitable mutations:
  • API cost savings → Fewer/cheaper LLM calls
  • Time savings → Faster wall clock execution
  • Throughput gains → Higher parallelism/utilization
  • Maintenance costs → Code complexity penalty

Result: The system evolves toward PROFITABLE code, not just "better" code.

Economic fitness is normalized to [0, 1]:
  • 0.0 = Lost $10K+/year (reject immediately)
  • 0.5 = Break-even (neutral)
  • 1.0 = Gained $10K+/year (strong selection pressure)

Combined with other fitness dimensions (correctness, dharmic alignment,
elegance, safety), this creates a multi-objective optimizer that finds
code that is both GOOD and PROFITABLE.
""")

    print("Run this demo with:")
    print("  .venv/bin/python scripts/economic_fitness_demo.py\n")
