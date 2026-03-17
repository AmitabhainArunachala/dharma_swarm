"""Provider contract scanner."""

from __future__ import annotations

import re
from pathlib import Path

from dharma_swarm.assurance.report_schema import Finding, ScanReport, Severity

KNOWN_PROVIDERS = {
    "anthropic",
    "openai",
    "openrouter",
    "nvidia_nim",
    "local",
    "claude_code",
    "codex",
    "openrouter_free",
    "ollama",
}
PROVIDER_PATTERN = re.compile(r"""ProviderType\.(\w+)""", re.IGNORECASE)
MODEL_STRING_PATTERN = re.compile(r"""["']?model["']?\s*[:=]\s*["']([^"']+)["']""")
MODEL_PROVIDER_MAP = {
    "claude-": "anthropic",
    "anthropic/": "anthropic",
    "openai/": "openai",
    "gpt-": "openai",
    "llama-": "openrouter",
    "mistral": "openrouter",
    "deepseek": "openrouter",
    "qwen": "openrouter",
    "gemma": "openrouter",
    "nemotron": "nvidia_nim",
}


def _infer_provider_from_model(model_str: str) -> str | None:
    lower = model_str.lower()
    for prefix, provider in MODEL_PROVIDER_MAP.items():
        if lower.startswith(prefix):
            return provider
    return None


def _resolve_target_files(
    *,
    repo_root: Path | None = None,
    changed_files: list[str] | None = None,
) -> tuple[Path, list[Path]]:
    root = repo_root or Path(__file__).resolve().parents[2]
    pkg_dir = root / "dharma_swarm"

    def _eligible(candidate: Path) -> bool:
        return (
            candidate.suffix == ".py"
            and "tests" not in candidate.parts
            and "assurance" not in candidate.parts
        )

    if changed_files:
        targets: list[Path] = []
        for raw in changed_files:
            candidate = Path(raw)
            if not candidate.is_absolute():
                candidate = root / candidate
            if _eligible(candidate):
                targets.append(candidate)
        return root, targets
    return root, [path for path in pkg_dir.rglob("*.py") if _eligible(path)]


def scan(
    *,
    repo_root: Path | None = None,
    changed_files: list[str] | None = None,
) -> ScanReport:
    report = ScanReport(scanner="provider_contract")
    findings: list[Finding] = []
    fid = 0
    root, target_files = _resolve_target_files(repo_root=repo_root, changed_files=changed_files)

    for pyfile in target_files:
        if not pyfile.exists():
            continue
        try:
            lines = pyfile.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue

        providers_in_file: list[tuple[int, str]] = []
        models_in_file: list[tuple[int, str]] = []
        for i, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for match in PROVIDER_PATTERN.finditer(line):
                providers_in_file.append((i, match.group(1).lower()))
            for match in MODEL_STRING_PATTERN.finditer(line):
                models_in_file.append((i, match.group(1)))

        for line_no, model_str in models_in_file:
            expected = _infer_provider_from_model(model_str)
            if expected is None:
                continue
            nearby = [(ln, p) for ln, p in providers_in_file if abs(ln - line_no) < 20]
            for provider_line, provider in nearby:
                if provider != expected and provider not in {"local", "ollama"}:
                    fid += 1
                    findings.append(Finding(
                        id=f"PC-{fid:03d}",
                        severity=Severity.HIGH,
                        category="provider_model_mismatch",
                        file=str(pyfile.relative_to(root)),
                        line=line_no,
                        description=(
                            f"Model '{model_str}' implies provider '{expected}' "
                            f"but ProviderType.{provider.upper()} declared at line {provider_line}"
                        ),
                        evidence=lines[line_no - 1].strip(),
                        proposed_fix=(
                            f"Change provider to ProviderType.{expected.upper()} or update the model string"
                        ),
                    ))

        for line_no, provider in providers_in_file:
            if provider not in KNOWN_PROVIDERS:
                fid += 1
                findings.append(Finding(
                    id=f"PC-{fid:03d}",
                    severity=Severity.MEDIUM,
                    category="unknown_provider",
                    file=str(pyfile.relative_to(root)),
                    line=line_no,
                    description=f"Unknown ProviderType '{provider}'",
                    evidence=lines[line_no - 1].strip(),
                    proposed_fix="Add the provider to the enum or fix the typo",
                ))

        for idx, line in enumerate(lines, start=1):
            if "ProviderType.CODEX" not in line:
                continue
            window = "\n".join(lines[idx - 1: min(len(lines), idx + 4)])
            if 'return "anthropic"' not in window:
                continue
            fid += 1
            findings.append(Finding(
                id=f"PC-{fid:03d}",
                severity=Severity.HIGH,
                category="provider_alias_mismatch",
                file=str(pyfile.relative_to(root)),
                line=idx,
                description=(
                    "ProviderType.CODEX resolves to the anthropic provider string, "
                    "so CODEX-labeled agents do not run on a distinct Codex lane"
                ),
                evidence=window.strip(),
                proposed_fix=(
                    "Route ProviderType.CODEX to its own provider string or rename the config "
                    "so labels match runtime behavior"
                ),
            ))
            break

    report.findings = findings
    report.recompute_summary()
    return report
