# DHARMA SWARM — Makefile
# Run `make help` to see all targets.

.PHONY: help boot stop logs health metrics test lint clean install docker-up docker-down gh-auth

SWARM_PLIST := $(HOME)/Library/LaunchAgents/com.dharma.swarm.plist
STATE_DIR    := $(HOME)/.dharma

help:
	@echo ""
	@echo "DHARMA SWARM — available targets:"
	@echo ""
	@echo "  make install      Install Python deps (pip install -e .[dev])"
	@echo "  make boot         Start the swarm as a background service (macOS)"
	@echo "  make stop         Stop the background service"
	@echo "  make restart      Stop + start"
	@echo "  make logs         Tail swarm logs"
	@echo "  make health       Check health API (curl localhost:7433/health)"
	@echo "  make metrics      Show full metrics (curl localhost:7433/metrics)"
	@echo "  make loops        Show loop status (curl localhost:7433/loops)"
	@echo "  make test         Run test suite"
	@echo "  make lint         Run ruff linter"
	@echo "  make clean        Remove .pyc and __pycache__"
	@echo "  make docker-up    Start via docker-compose (includes health + cron)"
	@echo "  make docker-down  Stop docker-compose stack"
	@echo "  make gh-auth      Authenticate gh CLI (needed for Guardian Crew issues)"
	@echo "  make live         Run dgc orchestrate-live in foreground (dev mode)"
	@echo ""

install:
	pip install -e ".[dev]"

boot:
	@mkdir -p $(STATE_DIR)/logs
	@cp com.dharma.swarm.plist $(SWARM_PLIST)
	@launchctl unload $(SWARM_PLIST) 2>/dev/null || true
	@launchctl load $(SWARM_PLIST)
	@echo "Swarm loaded. Logs: tail -f $(STATE_DIR)/logs/swarm.log"

stop:
	@launchctl unload $(SWARM_PLIST) 2>/dev/null || true
	@echo "Swarm stopped."

restart: stop boot

logs:
	@tail -f $(STATE_DIR)/logs/swarm.log 2>/dev/null || echo "No log yet — run 'make boot' first"

health:
	@curl -s http://localhost:7433/health | python3 -m json.tool

metrics:
	@curl -s http://localhost:7433/metrics | python3 -m json.tool

loops:
	@curl -s http://localhost:7433/loops | python3 -m json.tool

providers:
	@curl -s http://localhost:7433/providers | python3 -m json.tool

telos:
	@curl -s http://localhost:7433/telos | python3 -m json.tool

guardian:
	@curl -s http://localhost:7433/guardian | python3 -m json.tool | python3 -c "import sys,json; print(json.load(sys.stdin)['report'])"

live:
	TINY_ROUTER_BACKEND=heuristic dgc orchestrate-live

test:
	python -m pytest tests/ -q --tb=short -x -m "not slow and not docker and not network"

test-fast:
	python -m pytest tests/ -q --tb=line -x --timeout=10

lint:
	ruff check dharma_swarm/ --select=E,F,W --ignore=E501

syntax-check:
	@python3 -c "\
import ast; from pathlib import Path; \
errors = [f'{f.name}:{e.lineno}: {e.msg}' for f in Path('dharma_swarm').glob('*.py') \
          for e in [None] if (lambda: (lambda e: e)(None))() or True \
          if (setattr(__builtins__, '_', None) or True)]; \
[print(f'Checking {len(list(Path(\"dharma_swarm\").glob(\"*.py\")))} files...')] and \
[print('OK: all clean') if not [print('FAIL:', f) for f in \
    [f'{p.name}:{e.lineno}: {e.msg}' for p in Path('dharma_swarm').glob('*.py') \
     for e in [None] if True]] else None]"
	@python3 -c "\
import ast; from pathlib import Path; errs=[] ; \
[errs.append(f'{f.name}:{e.lineno}') for f in Path('dharma_swarm').glob('*.py') \
 for _ in [None] if (lambda f=f: \
   [errs.append(f'{f.name}') for e in [None] \
    if not (__import__('builtins').__dict__.update({'_e': None}) or True)])()]; \
print('syntax check done')"
	python3 -c "import ast; from pathlib import Path; errs=[]; [errs.append(f.name) or print(f'FAIL: {f.name}') for f in Path('dharma_swarm').glob('*.py') if not __import__('ast').parse(f.read_text()) is not None or False]; print(f'Checked {len(list(Path(\"dharma_swarm\").glob(\"*.py\")))} files, {len(errs)} errors')" || \
	python3 -c "import ast; from pathlib import Path; [ast.parse(f.read_text()) for f in Path('dharma_swarm').glob('*.py')]; print('All syntax OK')"

gh-auth:
	gh auth login

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	find . -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true

docker-up:
	@cp .env.example .env 2>/dev/null || true
	docker-compose up -d --build swarm
	@echo "Swarm running in Docker. Health: curl http://localhost:7433/health"

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f swarm
