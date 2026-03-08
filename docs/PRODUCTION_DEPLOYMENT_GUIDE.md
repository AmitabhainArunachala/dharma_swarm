# Production Deployment Guide

**Version**: 1.0
**Date**: 2026-03-09
**Target**: Enterprise deployment of dharma_swarm with full Unassailable System guarantees

---

## Pre-Deployment Checklist

### Phase 1: System Validation

**Property-Based Tests**:
```bash
# Run all property tests (15 tests)
.venv/bin/python -m pytest tests/properties/ -v --hypothesis-profile=ci

# Expected: 15/15 passing, ~100 examples per test
```

**Formal Verification**:
```bash
# Verify task coordination protocol
cd specs
java -XX:+UseParallelGC -cp tla2tools.jar tlc2.TLC \
    -config TaskBoardCoordination.cfg \
    TaskBoardCoordination.tla

# Expected: 42K+ states, 0 errors, all invariants satisfied
```

**Economic Fitness**:
```bash
# Run economic fitness demo
.venv/bin/python scripts/economic_fitness_demo.py

# Expected: ROI calculations for all 4 scenarios
```

**Merkle Chain Integrity**:
```bash
# Verify cryptographic audit trail
dgc evolve verify

# Expected: "✓ Archive verified: N entries, Merkle root: ..."
```

**Test Suite**:
```bash
# Run full test suite (602 tests)
.venv/bin/python -m pytest tests/ -v

# Expected: 602 passing (or current count), 0 failures
```

### Phase 2: Security Hardening

**API Key Management**:
```bash
# Never commit API keys
grep -r "sk-" . --exclude-dir={.git,.venv,node_modules}
grep -r "ANTHROPIC_API_KEY\s*=" . --exclude-dir={.git,.venv}

# Expected: No matches (keys should be in .env only)
```

**Environment Variables**:
```bash
# Create production .env (template provided)
cp .env.template .env.production

# Fill in:
# - ANTHROPIC_API_KEY=sk-ant-...
# - OPENAI_API_KEY=sk-...
# - GITHUB_TOKEN=ghp_...
# - Other provider keys
```

**File Permissions**:
```bash
# Secure state directory
chmod 700 ~/.dharma
chmod 600 ~/.dharma/evolution/archive.jsonl
chmod 600 ~/.dharma/evolution/merkle_log.json

# Expected: Only owner can read/write
```

**Network Security**:
```bash
# Firewall rules (if applicable)
# Block all inbound except SSH/HTTPS
# Allow outbound to API providers only

# Example (ufw):
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow https
sudo ufw enable
```

### Phase 3: Compliance Documentation

**Evidence Package** (for auditors):
```
compliance_package/
├── system_description.md          # Architecture overview
├── control_implementation/
│   ├── telos_gates.py             # All 11 gates
│   ├── gate_decisions.jsonl       # Historical logs
│   └── test_evidence.txt          # Test results
├── formal_verification/
│   ├── TaskBoardCoordination.tla  # TLA+ spec
│   ├── tlc_output.log             # Verification proof
│   └── invariants_proven.md       # What was proven
├── audit_trail/
│   ├── archive.jsonl              # All mutations
│   ├── merkle_log.json            # Cryptographic proof
│   └── verification_procedure.md  # How to verify chain
└── risk_assessment/
    ├── risk_register.xlsx         # Identified risks
    ├── mitigation_plan.md         # How risks are mitigated
    └── incident_response.md       # Failure handling
```

**Generate Package**:
```bash
# Create compliance evidence package
dgc compliance export --output compliance_package/

# Verify completeness
ls -R compliance_package/

# Expected: All required files present
```

---

## Deployment Architecture

### Option A: Single-Machine Deployment (Development/Small Teams)

**Hardware Requirements**:
- CPU: 4+ cores (8 recommended)
- RAM: 16GB minimum (32GB for heavy workloads)
- Disk: 100GB SSD (for logs, archives, memory DB)
- OS: macOS, Linux (Ubuntu 22.04+)

**Installation**:
```bash
# 1. Clone repository
git clone https://github.com/yourusername/dharma_swarm.git
cd dharma_swarm

# 2. Create virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -e ".[dev]"

# 4. Configure environment
cp .env.template .env
# Edit .env with production API keys

# 5. Initialize state directory
mkdir -p ~/.dharma/{evolution,db,jikoku,shared,witness,traces}

# 6. Run initial health check
dgc health

# Expected: All systems green
```

**Service Setup** (systemd):
```bash
# Create service file: /etc/systemd/system/dharma-swarm.service
[Unit]
Description=Dharma Swarm Evolution System
After=network.target

[Service]
Type=simple
User=dharma
WorkingDirectory=/opt/dharma_swarm
Environment="PATH=/opt/dharma_swarm/.venv/bin"
ExecStart=/opt/dharma_swarm/.venv/bin/dgc run --daemon
Restart=on-failure
RestartSec=10s

[Install]
WantedBy=multi-user.target

# Enable and start
sudo systemctl enable dharma-swarm
sudo systemctl start dharma-swarm
sudo systemctl status dharma-swarm
```

---

### Option B: Distributed Deployment (Enterprise/High-Availability)

**Architecture**:
```
┌─────────────────────────────────────────────────────────┐
│                    Load Balancer                        │
│                   (HAProxy/Nginx)                       │
└────────────┬──────────────┬──────────────┬─────────────┘
             │              │              │
    ┌────────▼─────┐ ┌──────▼──────┐ ┌────▼─────────┐
    │ Swarm Node 1 │ │ Swarm Node 2│ │ Swarm Node 3 │
    │              │ │             │ │              │
    │ - Darwin Eng │ │ - Darwin Eng│ │ - Darwin Eng │
    │ - Task Board │ │ - Task Board│ │ - Task Board │
    │ - Memory DB  │ │ - Memory DB │ │ - Memory DB  │
    └──────┬───────┘ └──────┬──────┘ └──────┬───────┘
           │                │                │
           └────────────────┼────────────────┘
                            │
                  ┌─────────▼──────────┐
                  │  Shared Storage    │
                  │  (NFS/S3/GCS)      │
                  │                    │
                  │ - Evolution archive│
                  │ - Merkle log       │
                  │ - JIKOKU logs      │
                  └────────────────────┘
```

**Shared State Synchronization**:
```bash
# Use NFS for shared state
sudo mount -t nfs nfs-server:/dharma /opt/dharma_shared

# Or use S3 with sync daemon
aws s3 sync ~/.dharma/evolution s3://dharma-production/evolution --delete

# Configure in .env
DHARMA_STATE_DIR=/opt/dharma_shared
MERKLE_LOG_SYNC=s3://dharma-production/merkle_log.json
```

**High Availability**:
- **3+ nodes**: Survive single-node failure
- **Shared storage**: NFS, S3, or GCS for evolution archive
- **Load balancer**: Distribute task claiming across nodes
- **Health checks**: Auto-restart failed nodes

---

## Monitoring & Observability

### Metrics Collection

**Prometheus Integration**:
```python
# dharma_swarm/prometheus_exporter.py (add)
from prometheus_client import Counter, Histogram, Gauge, start_http_server

# Metrics
tasks_claimed = Counter('dharma_tasks_claimed_total', 'Tasks claimed by agents')
tasks_completed = Counter('dharma_tasks_completed_total', 'Tasks completed successfully')
tasks_failed = Counter('dharma_tasks_failed_total', 'Tasks failed')
mutation_fitness = Histogram('dharma_mutation_fitness', 'Fitness scores', buckets=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0])
gates_blocked = Counter('dharma_gates_blocked_total', 'Gate failures', ['gate_name'])

# Start exporter
start_http_server(9090)  # Expose metrics on :9090/metrics
```

**Grafana Dashboard** (metrics to visualize):
- Tasks claimed/completed/failed per hour
- Average mutation fitness over time
- Gate success/failure rates by gate type
- Economic value created ($$ ROI per day)
- Merkle chain length (audit trail growth)
- Agent health (alive/failed/working)

### Log Aggregation

**Structured Logging** (JSON):
```python
# Configure structured logging
import structlog

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ]
)

log = structlog.get_logger()
log.info("mutation_applied", mutation_id="abc123", fitness=0.84, economic_value=8400)
```

**Ship to Datadog/Splunk**:
```bash
# Datadog agent config
# /etc/datadog-agent/conf.d/dharma_swarm.d/conf.yaml
logs:
  - type: file
    path: "/var/log/dharma_swarm/*.log"
    service: dharma-swarm
    source: python

# Restart agent
sudo systemctl restart datadog-agent
```

### Alerting

**Critical Alerts** (PagerDuty/Opsgenie):
```yaml
# alerting_rules.yml
groups:
  - name: dharma_critical
    interval: 1m
    rules:
      - alert: GateFailureSpike
        expr: rate(dharma_gates_blocked_total[5m]) > 10
        for: 5m
        annotations:
          summary: "Dharmic gates blocking many mutations"
          description: "Gate {{ $labels.gate_name }} blocked {{ $value }} mutations/min"

      - alert: MerkleChainBroken
        expr: dharma_merkle_chain_valid == 0
        for: 1m
        annotations:
          summary: "Merkle chain integrity violated"
          description: "Cryptographic audit trail tampered or corrupted"

      - alert: AllAgentsFailed
        expr: sum(dharma_agent_state{state="alive"}) == 0
        for: 2m
        annotations:
          summary: "All agents failed - system down"
```

---

## Backup & Disaster Recovery

### What to Back Up

**Critical State** (must backup):
- `~/.dharma/evolution/archive.jsonl` — All mutation history
- `~/.dharma/evolution/merkle_log.json` — Cryptographic proof
- `~/.dharma/db/memory.db` — Agent memory
- `.env` — API keys (encrypted)

**Nice to Have** (optional):
- `~/.dharma/jikoku/JIKOKU_LOG.jsonl` — Performance metrics
- `~/.dharma/shared/` — Inter-agent messages
- `~/.dharma/witness/` — Gate decision logs

### Backup Strategy

**Daily Backups**:
```bash
#!/bin/bash
# backup.sh - Run daily via cron

BACKUP_DIR="/backups/dharma/$(date +%Y%m%d)"
mkdir -p "$BACKUP_DIR"

# Copy critical files
cp ~/.dharma/evolution/archive.jsonl "$BACKUP_DIR/"
cp ~/.dharma/evolution/merkle_log.json "$BACKUP_DIR/"
cp ~/.dharma/db/memory.db "$BACKUP_DIR/"

# Encrypt .env
gpg --encrypt --recipient ops@company.com .env > "$BACKUP_DIR/env.gpg"

# Verify Merkle chain before backup
dgc evolve verify || { echo "Merkle chain broken!"; exit 1; }

# Upload to S3
aws s3 sync "$BACKUP_DIR" s3://dharma-backups/$(date +%Y%m%d)/

# Retention: Keep 30 days
find /backups/dharma/ -type d -mtime +30 -exec rm -rf {} \;
```

**Cron Schedule**:
```bash
# Run backup at 2 AM daily
0 2 * * * /opt/dharma_swarm/scripts/backup.sh >> /var/log/dharma_backup.log 2>&1
```

### Disaster Recovery

**Recovery Procedure** (in case of total failure):

1. **Restore from Backup**:
```bash
# Download latest backup
aws s3 sync s3://dharma-backups/latest/ /tmp/restore/

# Restore files
cp /tmp/restore/archive.jsonl ~/.dharma/evolution/
cp /tmp/restore/merkle_log.json ~/.dharma/evolution/
cp /tmp/restore/memory.db ~/.dharma/db/

# Decrypt .env
gpg --decrypt /tmp/restore/env.gpg > .env
```

2. **Verify Integrity**:
```bash
# Verify Merkle chain
dgc evolve verify

# Expected: "✓ Archive verified: N entries, Merkle root: ..."
# If broken: Investigate tampering
```

3. **Test System**:
```bash
# Run health check
dgc health

# Run test suite
.venv/bin/python -m pytest tests/ -q

# Expected: All systems green, all tests passing
```

4. **Resume Operations**:
```bash
# Start swarm
dgc run --daemon

# Monitor for 1 hour
watch -n 60 'dgc status'
```

**Recovery Time Objective (RTO)**: 1 hour
**Recovery Point Objective (RPO)**: 24 hours (daily backups)

---

## Performance Tuning

### JIKOKU Optimization

**Enable JIKOKU** (if not already):
```bash
export JIKOKU_ENABLED=1
```

**Adjust Profiling** (reduce overhead):
```python
# dharma_swarm/jikoku_instrumentation.py
JIKOKU_SAMPLE_RATE = 0.1  # Sample 10% of operations (vs. 100%)
```

**Batch Writes**:
```python
# dharma_swarm/jikoku_samaya.py
JIKOKU_FLUSH_INTERVAL = 60  # Flush every 60 seconds (vs. every span)
```

### Darwin Engine Tuning

**Concurrent Evolution**:
```python
# dharma_swarm/evolution.py
MAX_CONCURRENT_PROPOSALS = 5  # Test 5 mutations in parallel
```

**Fitness Predictor** (reduce redundant evaluations):
```python
# dharma_swarm/fitness_predictor.py
PREDICTOR_CONFIDENCE_THRESHOLD = 0.8  # Skip evaluation if predicted fitness < 0.8
```

### Memory Database

**Periodic Cleanup**:
```sql
-- Remove old memory entries (> 90 days)
DELETE FROM memories WHERE created_at < datetime('now', '-90 days');

-- Vacuum to reclaim space
VACUUM;
```

**Index Optimization**:
```sql
-- Add indexes for common queries
CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at);
CREATE INDEX IF NOT EXISTS idx_traces_timestamp ON traces(timestamp);
```

---

## Security Best Practices

### API Key Rotation

**Monthly Rotation**:
```bash
# 1. Generate new API keys from providers
# 2. Update .env with new keys
# 3. Test system with new keys
dgc health

# 4. Revoke old keys from provider dashboards
# 5. Update backup encryption keys
```

### Access Control

**File Permissions**:
```bash
# State directory: Owner-only
chmod 700 ~/.dharma

# Evolution archive: Owner read-write
chmod 600 ~/.dharma/evolution/archive.jsonl

# Merkle log: Owner read-write
chmod 600 ~/.dharma/evolution/merkle_log.json
```

**User Separation** (multi-user systems):
```bash
# Create dedicated user
sudo useradd -r -s /bin/bash -d /opt/dharma_swarm dharma

# Transfer ownership
sudo chown -R dharma:dharma /opt/dharma_swarm
sudo chown -R dharma:dharma ~/.dharma

# Run as dharma user
sudo -u dharma dgc run --daemon
```

### Network Security

**Firewall Rules**:
```bash
# Allow only essential ports
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 443/tcp  # HTTPS (API calls)
sudo ufw deny 9090/tcp  # Block Prometheus externally (internal only)
sudo ufw enable
```

**API Provider Whitelist**:
```bash
# Only allow traffic to known API providers
# (Requires advanced firewall like pfSense)
# Whitelist:
# - api.anthropic.com (Anthropic)
# - api.openai.com (OpenAI)
# - openrouter.ai (OpenRouter)
```

---

## Cost Optimization

### API Usage Tracking

**Monitor Spend**:
```bash
# Check API call counts
dgc status | grep "api_calls"

# Calculate monthly cost
python -c "
api_calls_per_day = 1000
cost_per_call = 0.015
monthly_cost = api_calls_per_day * cost_per_call * 30
print(f'Estimated monthly cost: ${monthly_cost:.2f}')
"
```

**Set Budget Alerts**:
```bash
# Anthropic dashboard: Set budget limit ($500/month)
# OpenAI dashboard: Set budget limit ($300/month)
# Receive email when 80% spent
```

### Provider Selection

**Cost-Aware Routing** (use cheaper models when possible):
```python
# dharma_swarm/providers.py
PROVIDER_COSTS = {
    "claude-sonnet-4.6": 0.015,  # Premium
    "gpt-4o": 0.025,             # Premium
    "claude-haiku-4.5": 0.001,   # Budget
    "gpt-4o-mini": 0.002,        # Budget
}

def select_provider_by_budget(task_complexity: float):
    if task_complexity < 0.5:
        return "claude-haiku-4.5"  # Simple task = cheap model
    else:
        return "claude-sonnet-4.6"  # Complex task = premium model
```

---

## Compliance Operations

### Continuous Compliance

**Monthly Tasks**:
- [ ] Run full test suite → capture results for auditors
- [ ] Verify Merkle chain integrity →証明 tamper-free history
- [ ] Review gate failure logs → analyze rejection patterns
- [ ] Calculate economic ROI → demonstrate business value
- [ ] Backup compliance evidence → prepare for audit

**Quarterly Tasks**:
- [ ] Run TLA+ verification → prove distributed correctness
- [ ] Update risk register → identify new threats
- [ ] Review incident response logs → improve procedures
- [ ] Conduct internal security review → find vulnerabilities

**Annual Tasks**:
- [ ] External audit (ISO 27001, SOC 2)
- [ ] Recertification (if applicable)
- [ ] Update compliance documentation
- [ ] Train team on new controls

### Audit Preparation

**2 Weeks Before Audit**:
```bash
# Generate compliance package
dgc compliance export --output audit_package_$(date +%Y%m%d)/

# Verify all evidence is present
ls audit_package_*/

# Expected:
# - system_description.md
# - control_implementation/
# - formal_verification/
# - audit_trail/
# - risk_assessment/
```

**1 Week Before Audit**:
- Review compliance mapping document
- Prepare demo environment for auditor
- Identify SMEs for each control area
- Schedule auditor interviews

**During Audit**:
- Provide evidence package on day 1
- Demo live system verification (dgc evolve verify)
- Walk through TLA+ proof (specs/TaskBoardCoordination.tla)
- Explain dharmic gates (unique compliance moat)

---

## Troubleshooting

### Common Issues

**Issue**: Merkle chain verification fails
```bash
$ dgc evolve verify
✗ Merkle chain broken at index 42
```

**Solution**:
1. Check for file corruption: `ls -lh ~/.dharma/evolution/merkle_log.json`
2. Restore from backup if corrupted
3. If recent append failed, revert last entry
4. Report to security team (potential tampering)

---

**Issue**: All agents fail simultaneously
```bash
$ dgc status
[ERROR] All agents in failed state
```

**Solution**:
1. Check logs: `tail -100 ~/.dharma/logs/swarm.log`
2. Common causes: API rate limit, network failure, invalid API key
3. Restart swarm: `dgc shutdown && dgc run`
4. If persists, restore from backup

---

**Issue**: Property tests failing
```bash
$ pytest tests/properties/ -v
FAILED test_fitness_always_bounded - Fitness score 1.2 > 1.0
```

**Solution**:
1. **DO NOT DEPLOY** — property violation indicates bug
2. Fix the underlying issue (e.g., fitness calculation bug)
3. Re-run property tests until passing
4. Add regression test to prevent recurrence

---

## Next Steps

**Phase 4**: Monitoring Dashboard
- [ ] Set up Grafana with dharma_swarm metrics
- [ ] Configure alerting (PagerDuty/Opsgenie)
- [ ] Create on-call runbook

**Phase 5**: Scale Testing
- [ ] Load test with 1000+ tasks
- [ ] Benchmark mutation throughput
- [ ] Optimize bottlenecks

**Phase 6**: Enterprise Features
- [ ] Multi-tenancy support
- [ ] Role-based access control (RBAC)
- [ ] SSO integration (SAML/OAuth)

---

**JSCA!** — dharma_swarm is production-ready with Unassailable guarantees.
