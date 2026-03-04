#!/usr/bin/env bash
# Quality Gates for dharma_swarm integration build.
# Run all 7 gates sequentially. Fail-fast on gates 1-5.
# Gates 6-7 are advisory (warn but don't block).

set -e
cd ~/dharma_swarm

echo "========================================="
echo "QUALITY GATES - $(date)"
echo "========================================="

# GATE 1: Import Resolution
echo ""
echo "[GATE 1/7] Import Resolution..."
python3 -c "
import importlib, sys
modules = [
    'dharma_swarm.darwin.archive',
    'dharma_swarm.darwin.selector',
    'dharma_swarm.darwin.elegance',
    'dharma_swarm.darwin.fitness_predictor',
    'dharma_swarm.darwin.evolution_v3',
    'dharma_swarm.infra.canonical_memory',
    'dharma_swarm.infra.file_lock',
    'dharma_swarm.infra.residual_stream',
    'dharma_swarm.infra.systemic_monitor',
    'dharma_swarm.infra.anomaly_detection',
    'dharma_swarm.research.fidelity',
    'dharma_swarm.research.brain',
    'dharma_swarm.research.ssc_mathematical_core',
]
failed = []
for mod in modules:
    try:
        importlib.import_module(mod)
        print(f'  OK: {mod}')
    except Exception as e:
        print(f'  FAIL: {mod} -- {e}')
        failed.append(mod)
if failed:
    print(f'\nGATE 1 FAILED: {len(failed)} modules failed to import')
    sys.exit(1)
print('GATE 1 PASSED')
"

# GATE 2: Existing 202 Tests Pass
echo ""
echo "[GATE 2/7] Baseline Regression Check (203 tests)..."
python3 scripts/regression_guard.py

# GATE 3: New Module Tests Pass
echo ""
echo "[GATE 3/7] New Module Unit Tests..."
NEW_TESTS=""
for f in tests/test_systemic_monitor.py tests/test_anomaly_detection.py \
         tests/test_fidelity.py tests/test_brain.py \
         tests/test_ssc_mathematical_core.py tests/test_evolution_v3.py; do
    if [ -f "$f" ]; then
        NEW_TESTS="$NEW_TESTS $f"
    fi
done

if [ -n "$NEW_TESTS" ]; then
    python3 -m pytest $NEW_TESTS -v --tb=short
    echo "GATE 3 PASSED"
else
    echo "GATE 3 SKIPPED: No new test files found yet"
fi

# GATE 4: Integration Tests Pass
echo ""
echo "[GATE 4/7] Integration Tests..."
INT_TESTS=""
for f in tests/test_integration_darwin.py tests/test_integration_memory_lock.py \
         tests/test_integration_gates.py tests/test_integration_orchestrator.py; do
    if [ -f "$f" ]; then
        INT_TESTS="$INT_TESTS $f"
    fi
done

if [ -n "$INT_TESTS" ]; then
    python3 -m pytest $INT_TESTS -v --tb=short
    echo "GATE 4 PASSED"
else
    echo "GATE 4 SKIPPED: No integration test files found yet"
fi

# GATE 5: Security Scan
echo ""
echo "[GATE 5/7] Security Scan..."
python3 -c "
import re, sys
from pathlib import Path

patterns = [
    (r'sk-ant-[a-zA-Z0-9]{20,}', 'Anthropic API key'),
    (r'sk-[a-zA-Z0-9]{20,}', 'OpenAI API key'),
    (r'ghp_[a-zA-Z0-9]{36}', 'GitHub token'),
    (r'-----BEGIN (RSA |EC )?PRIVATE KEY', 'Private key'),
    (r'password\s*=\s*[\"'\''][^\"'\'']+[\"'\'']', 'Hardcoded password'),
    (r'ANTHROPIC_API_KEY\s*=\s*[\"'\''][^\"'\'']+[\"'\'']', 'Hardcoded API key'),
]

scan_dirs = [
    Path('dharma_swarm/darwin'),
    Path('dharma_swarm/infra'),
    Path('dharma_swarm/research'),
]

violations = []
for d in scan_dirs:
    if not d.exists():
        continue
    for f in d.rglob('*.py'):
        content = f.read_text(errors='ignore')
        for pattern, desc in patterns:
            matches = re.findall(pattern, content)
            if matches:
                violations.append(f'{f}: {desc} ({len(matches)} match(es))')

if violations:
    print('SECURITY VIOLATIONS:')
    for v in violations:
        print(f'  {v}')
    sys.exit(1)
print('GATE 5 PASSED: No hardcoded secrets found')
"

# GATE 6: Type Checking (advisory)
echo ""
echo "[GATE 6/7] Type Checking (advisory)..."
if command -v pyright &> /dev/null; then
    pyright dharma_swarm/darwin/ dharma_swarm/infra/ dharma_swarm/research/ 2>&1 || echo "GATE 6: Type errors found (non-blocking)"
else
    echo "GATE 6 SKIPPED: pyright not installed"
fi

# GATE 7: Complexity Check (advisory)
echo ""
echo "[GATE 7/7] Cyclomatic Complexity (advisory)..."
python3 -c "
import ast, sys
from pathlib import Path

class ComplexityVisitor(ast.NodeVisitor):
    def __init__(self):
        self.functions = {}
        self._current = None
        self._complexity = 1

    def visit_FunctionDef(self, node):
        old = (self._current, self._complexity)
        self._current = node.name
        self._complexity = 1
        self.generic_visit(node)
        self.functions[f'{node.name}:{node.lineno}'] = self._complexity
        self._current, self._complexity = old

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_If(self, node): self._complexity += 1; self.generic_visit(node)
    def visit_For(self, node): self._complexity += 1; self.generic_visit(node)
    def visit_While(self, node): self._complexity += 1; self.generic_visit(node)
    def visit_ExceptHandler(self, node): self._complexity += 1; self.generic_visit(node)
    def visit_BoolOp(self, node): self._complexity += len(node.values) - 1; self.generic_visit(node)

violations = []
for d in ['dharma_swarm/darwin', 'dharma_swarm/infra', 'dharma_swarm/research']:
    p = Path(d)
    if not p.exists():
        continue
    for f in p.rglob('*.py'):
        if f.name == '__init__.py':
            continue
        try:
            tree = ast.parse(f.read_text())
            v = ComplexityVisitor()
            v.visit(tree)
            for func, cc in v.functions.items():
                if cc > 10:
                    violations.append(f'{f}:{func} complexity={cc}')
        except SyntaxError:
            violations.append(f'{f}: SYNTAX ERROR')

if violations:
    print('COMPLEXITY WARNINGS (>10):')
    for v in violations:
        print(f'  {v}')
    print(f'WARNING: {len(violations)} functions exceed complexity 10')
else:
    print('GATE 7 PASSED: All functions within complexity limit')
"

echo ""
echo "========================================="
echo "ALL GATES PASSED - $(date)"
echo "========================================="
