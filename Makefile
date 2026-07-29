.PHONY: install data train backtest reproduce train-all-states test up down logs clean help

help:
	@echo "Pricing the Heat - Available targets:"
	@echo "  make install    - Install backend dependencies"
	@echo "  make data       - Fetch and process raw data"
	@echo "  make train      - Train models"
	@echo "  make backtest   - Run backtests"
	@echo "  make reproduce  - Regenerate all artifacts from cached data"
	@echo "  make test       - Run unit and e2e tests"
	@echo "  make up         - Start docker-compose services"
	@echo "  make down       - Stop docker-compose services"
	@echo "  make logs       - Tail docker logs"
	@echo "  make clean      - Remove build artifacts and cache"

install:
	pip install -r backend/requirements-torch.txt
	pip install -r backend/requirements.txt
	cd frontend && npm ci

data:
	PYTHONPATH=. python -m backend.data.fetch_weather
	PYTHONPATH=. python -m backend.data.fetch_wages
	PYTHONPATH=. python -m backend.data.build_wage_loss

train:
	PYTHONPATH=. python -m models.stgcn.train
	PYTHONPATH=. python -m models.behavioral_agent.ppo_from_scratch
	PYTHONPATH=. python -m models.behavioral_agent.calibration
	PYTHONPATH=. python -m models.stgcn.evaluate_spatial
	PYTHONPATH=. python -m models.fusion.tevi
	PYTHONPATH=. python -m models.forecast.train

backtest:
	PYTHONPATH=. python -m backend.backtest.report
	PYTHONPATH=. python -m models.anomaly.train

# Order matters: build_wage_loss writes the literature-based wage_loss.parquet,
# then calibration.py overwrites it with the behaviorally-calibrated version
# (same schema) that Prompt 4 consumes as F_L. models.forecast.train needs
# mu_tevi.parquet (written by models.fusion.tevi, just before it). backtest.report
# writes claims.parquet, which models.anomaly.train needs -- so it must run
# after the replay, never before.
reproduce:
	PYTHONPATH=. python -m backend.data.build_wage_loss
	PYTHONPATH=. python -m models.stgcn.train
	PYTHONPATH=. python -m models.behavioral_agent.ppo_from_scratch
	PYTHONPATH=. python -m models.behavioral_agent.calibration
	PYTHONPATH=. python -m models.stgcn.evaluate_spatial
	PYTHONPATH=. python -m models.fusion.tevi
	PYTHONPATH=. python -m models.forecast.train
	PYTHONPATH=. python -m backend.backtest.report
	PYTHONPATH=. python -m models.anomaly.train

test:
	PYTHONPATH=. pytest tests/unit -q
	@echo "TODO: Implement e2e tests"

up:
	docker compose -f infra/docker-compose.yml up -d

down:
	docker compose -f infra/docker-compose.yml down

logs:
	docker compose -f infra/docker-compose.yml logs -f

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache
	@echo "Cleaned build artifacts"

# Resumable per-state batch (all states in config/wages_by_state.yaml). Pins
# .venv/bin/python explicitly so the canonical interpreter is inherited by every
# stage subprocess (never a bare python/python3 off PATH). Pass flags via ARGS:
#   make train-all-states ARGS="--states US-Arizona,IN-Assam --fail-fast"
train-all-states:
	PYTHONPATH=. .venv/bin/python -m backend.batch.train_all_states $(ARGS)
