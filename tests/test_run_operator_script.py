from __future__ import annotations

from pathlib import Path


def _read_script() -> str:
    script_path = Path(__file__).resolve().parents[1] / "run_operator.sh"
    return script_path.read_text(encoding="utf-8")


def test_run_operator_exports_runtime_root_overrides() -> None:
    script = _read_script()

    assert 'export DHARMA_REPO_ROOT="${DHARMA_REPO_ROOT:-$SCRIPT_DIR}"' in script
    assert 'export DHARMA_HOME="${DHARMA_HOME:-${HOME}/.dharma}"' in script
    assert 'STATE_DIR="${DHARMA_HOME}"' in script
    assert 'RUNTIME_ENV_HELPER="${DHARMA_REPO_ROOT}/scripts/load_runtime_env.sh"' in script
    assert 'cd "$DHARMA_REPO_ROOT"' in script
