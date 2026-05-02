.PHONY: help install up down logs ps migrate revision test api worker watcher seed demo clean nuke

help:
	@echo "Re-Tech Fusion Phase 2 — make targets"
	@echo "  install    Install Python deps (editable) with dev extras"
	@echo "  up         Start docker stack (postgres, redis, mosquitto)"
	@echo "  down       Stop docker stack"
	@echo "  logs       Tail docker logs"
	@echo "  ps         Show docker compose status"
	@echo "  migrate    Run alembic migrations to head"
	@echo "  revision   Generate a new alembic revision (use M=\"message\")"
	@echo "  test       Run pytest"
	@echo "  api        Start FastAPI dev server (port 8000)"
	@echo "  worker     Start RQ worker process"
	@echo "  watcher    Start drop-folder watcher"
	@echo "  seed       Seed the database with fixtures"
	@echo "  demo       Run the end-to-end demo script"
	@echo "  clean      Stop stack and prune unused volumes"
	@echo "  nuke       Stop stack and DELETE all volumes (destructive)"

install:
	pip install -e ".[dev]"

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

ps:
	docker compose ps

migrate:
	python -m alembic upgrade head

revision:
	python -m alembic revision -m "$(M)"

test:
	python -m pytest

api:
	python -m uvicorn retech_part2.api.main:app --reload --host 0.0.0.0 --port 8000

worker:
	python -m retech_part2.workers.run_worker

watcher:
	python -m retech_part2.ingestion.watcher

seed:
	python scripts/seed_db.py

demo:
	bash scripts/demo.sh

clean:
	docker compose down

nuke:
	docker compose down -v
