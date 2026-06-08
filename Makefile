PYTHON ?= python
API_HOST ?= 127.0.0.1
API_PORT ?= 8000
DASHBOARD_PORT ?= 8501

.PHONY: install install-dev api dev dashboard eval test lint demo docker-up docker-down

install:
	$(PYTHON) -m pip install -e .

install-dev:
	$(PYTHON) -m pip install -e ".[dev]"

api:
	$(PYTHON) -m uvicorn app.main:app --reload --host $(API_HOST) --port $(API_PORT)

dev: api

dashboard:
	$(PYTHON) -m streamlit run dashboard/app.py --server.port $(DASHBOARD_PORT)

eval:
	$(PYTHON) -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check .

demo:
	$(PYTHON) -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4

docker-up:
	docker compose up --build

docker-down:
	docker compose down
