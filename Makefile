PYTHON ?= python3
VENV = .venv/bin
.PHONY: setup check test run fixtures smoke
setup:
	$(PYTHON) -m venv .venv
	$(VENV)/python -m pip install -r requirements.txt
	$(VENV)/python -m pip install --no-build-isolation -e .
	cd frontend && npm ci
check:
	$(VENV)/ruff check backend scripts
	$(VENV)/mypy backend/whichcard
	$(MAKE) test
	cd frontend && npm run typecheck && npm test && npm run build
test:
	$(VENV)/pytest --cov=whichcard --cov-report=term-missing
run:
	test -d frontend/dist || (cd frontend && npm run build)
	$(VENV)/python -m whichcard.serve
fixtures:
	$(VENV)/python backend/scripts/gen_fixtures.py
smoke:
	$(VENV)/python scripts/smoke.py
