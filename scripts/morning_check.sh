#!/usr/bin/env bash
# 4:30 AM daily checkpoint for dharma_swarm overnight builds.
# Quick health check: 30 seconds to know if the build is clean.

echo "========================================="
echo "DHARMA SWARM - 4:30 AM CHECKPOINT"
echo "$(date)"
echo "========================================="

# 1. Check for STOP_BUILD
if [ -f ~/.dharma/STOP_BUILD ]; then
    echo ""
    echo "*** BUILD WAS HALTED ***"
    cat ~/.dharma/STOP_BUILD
    echo ""
fi

# 2. Test baseline
echo ""
echo "--- Test Status ---"
if [ -f ~/.dharma/test_baseline.json ]; then
    python3 -c "
import json
d = json.loads(open('$HOME/.dharma/test_baseline.json').read())
print(f\"  Tests passed: {d['passed']} (baseline: {d['baseline']})\")
print(f\"  Failed: {d.get('failed', 0)}\")
print(f\"  Regression: {'YES' if d['regression'] else 'No'}\")
print(f\"  Last run: {d['timestamp']}\")
"
else
    echo "  No test baseline file found. Running tests now..."
    cd ~/dharma_swarm && python3 -m pytest tests/ -q --tb=no 2>&1 | tail -3
fi

# 3. Alerts summary
echo ""
echo "--- Alerts ---"
ALERT_COUNT=$(ls ~/.dharma/alerts/*.json 2>/dev/null | wc -l | tr -d ' ')
if [ "$ALERT_COUNT" -gt "0" ]; then
    echo "  $ALERT_COUNT alert(s):"
    for f in $(ls -t ~/.dharma/alerts/*.json 2>/dev/null | head -5); do
        python3 -c "
import json
d = json.loads(open('$f').read())
print(f\"    [{d['severity'].upper()}] {d['message']} ({d['timestamp'][:19]})\")
"
    done
else
    echo "  No alerts. Clean build."
fi

# 4. New test count
echo ""
echo "--- Test Count ---"
cd ~/dharma_swarm
TOTAL=$(python3 -m pytest tests/ --co -q 2>&1 | tail -1 | grep -oE '^[0-9]+')
echo "  Total tests collected: $TOTAL"
echo "  Baseline: 203"
if [ -n "$TOTAL" ]; then
    echo "  New tests added: $((TOTAL - 203))"
fi

# 5. Sentinel status
echo ""
echo "--- Sentinel ---"
if [ -f ~/.dharma/sentinel.pid ]; then
    PID=$(cat ~/.dharma/sentinel.pid)
    if kill -0 "$PID" 2>/dev/null; then
        echo "  Sentinel RUNNING (PID $PID)"
    else
        echo "  Sentinel DEAD (PID $PID was not found)"
    fi
else
    echo "  No sentinel PID file found"
fi

echo ""
echo "========================================="
echo "Quick smoke: cd ~/dharma_swarm && python3 -m pytest tests/test_models.py tests/test_telos_gates.py -q"
echo "Full gates:  bash ~/dharma_swarm/scripts/quality_gates.sh"
echo "========================================="
