"""Tests for the steelman gate module."""

from dharma_swarm.models import GateResult
from dharma_swarm.steelman_gate import SteelmanCheck, SteelmanResult, check_steelman


class TestSteelmanGate:
    """Tests for check_steelman decision logic."""

    def test_no_counterarguments_fails(self) -> None:
        check = SteelmanCheck(counterarguments=[])
        result = check_steelman(check)
        assert result.gate_result == GateResult.FAIL
        assert result.total_counterarguments == 0
        assert result.substantive_counterarguments == 0
        assert "No counterarguments provided" in result.reason

    def test_one_substantive_passes(self) -> None:
        check = SteelmanCheck(
            counterarguments=["This approach may fail under high concurrency loads"],
        )
        result = check_steelman(check)
        assert result.gate_result == GateResult.PASS
        assert result.substantive_counterarguments == 1

    def test_multiple_substantive_passes(self) -> None:
        check = SteelmanCheck(
            counterarguments=[
                "The latency impact could degrade user experience significantly",
                "Memory usage grows linearly with input size which is unsustainable",
                "This duplicates functionality already present in the core module",
            ],
        )
        result = check_steelman(check)
        assert result.gate_result == GateResult.PASS
        assert result.substantive_counterarguments == 3
        assert result.total_counterarguments == 3

    def test_short_counterarguments_warn(self) -> None:
        check = SteelmanCheck(counterarguments=["too short", "nope", "bad"])
        result = check_steelman(check)
        assert result.gate_result == GateResult.WARN
        assert result.total_counterarguments == 3
        assert result.substantive_counterarguments == 0
        assert "none are substantive" in result.reason

    def test_mixed_short_and_substantive(self) -> None:
        check = SteelmanCheck(
            counterarguments=[
                "no",
                "This alternative design reduces coupling between modules significantly",
            ],
        )
        result = check_steelman(check)
        assert result.gate_result == GateResult.PASS
        assert result.total_counterarguments == 2
        assert result.substantive_counterarguments == 1

    def test_whitespace_only_not_substantive(self) -> None:
        check = SteelmanCheck(counterarguments=["                         "])
        result = check_steelman(check)
        assert result.gate_result == GateResult.WARN
        assert result.substantive_counterarguments == 0

    def test_empty_string_not_substantive(self) -> None:
        check = SteelmanCheck(counterarguments=[""])
        result = check_steelman(check)
        assert result.gate_result == GateResult.WARN
        assert result.substantive_counterarguments == 0

    def test_custom_min_length(self) -> None:
        check = SteelmanCheck(
            counterarguments=["short but ok"],
            min_substantive_length=10,
        )
        result = check_steelman(check)
        assert result.gate_result == GateResult.PASS
        assert result.substantive_counterarguments == 1

    def test_result_counts_correct(self) -> None:
        check = SteelmanCheck(
            counterarguments=[
                "This is a substantive counterargument exceeding twenty characters",
                "tiny",
                "Another substantive point about the design tradeoffs involved",
                "",
            ],
        )
        result = check_steelman(check)
        assert result.total_counterarguments == 4
        assert result.substantive_counterarguments == 2
        assert result.gate_result == GateResult.PASS

    def test_exactly_at_threshold(self) -> None:
        # Exactly 20 characters after strip
        arg = "a" * 20
        assert len(arg.strip()) == 20
        check = SteelmanCheck(counterarguments=[arg])
        result = check_steelman(check)
        assert result.gate_result == GateResult.PASS
        assert result.substantive_counterarguments == 1
