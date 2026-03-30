from __future__ import annotations

from pathlib import Path


def _read_script() -> str:
    script_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "start_psmv_hyperfile_branch.sh"
    )
    return script_path.read_text(encoding="utf-8")


def test_start_psmv_hyperfile_branch_uses_home_scoped_runtime_state() -> None:
    script = _read_script()

    assert 'STATE_DIR="${STATE_DIR:-${HOME}/.dharma/psmv_hyperfile_branch}"' in script
    assert 'STATE_DIR="${STATE_DIR:-${ROOT}/.dharma_psmv_hyperfile_branch}"' not in script
    assert 'STAGE_DIR="${STAGE_DIR:-${ROOT}/reports/psmv_hyperfiles_${DATE_TAG}}"' in script
