PYTHON ?= python3
PYTEST ?= pytest
DASHBOARD_DIR ?= dashboard

.PHONY: help xray xray-json compile test-smoke test-all ci-local verify-humming dashboard-lint dashboard-build

help:
	@printf "Available targets:\n"
	@printf "  make xray            # static repo inventory\n"
	@printf "  make xray-json       # static repo inventory as JSON\n"
	@printf "  make compile         # Python bytecode sanity pass\n"
	@printf "  make test-smoke      # stop on first failing test\n"
	@printf "  make test-all        # full pytest suite\n"
	@printf "  make ci-local        # compile + smoke test + xray\n"
	@printf "  make verify-humming  # canonical humming verification lane\n"
	@printf "  make dashboard-lint  # lint Next dashboard\n"
	@printf "  make dashboard-build # build Next dashboard\n"

xray:
	$(PYTHON) scripts/repo_xray.py

xray-json:
	$(PYTHON) scripts/repo_xray.py --format json

compile:
	$(PYTHON) -m compileall dharma_swarm tests

test-smoke:
	$(PYTEST) -x --tb=short

test-all:
	$(PYTEST) -q

ci-local: compile test-smoke xray

verify-humming:
	$(PYTHON) scripts/verify_humming.py

dashboard-lint:
	npm --prefix $(DASHBOARD_DIR) run lint

dashboard-build:
	npm --prefix $(DASHBOARD_DIR) run build
