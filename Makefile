# Incident Assistant — Common commands
# Usage: make [target]

.PHONY: api app cli install dev deploy help

api:
	python run.py api

app:
	python run.py app

cli:
	python run.py cli

install:
	pip install -r requirements-api.txt

dev: install
	@echo "Starting API and App in background..."
	@python run.py api &
	@sleep 2
	python run.py app

deploy:
	./scripts/deploy.sh

oracle:
	docker compose -f docker-compose.oracle.yml up -d

help:
	@echo "Incident Assistant — Available targets:"
	@echo "  make api     — Start FastAPI backend (port 8000)"
	@echo "  make app     — Start Streamlit frontend (port 8501)"
	@echo "  make cli     — Start CLI interface"
	@echo "  make install — Install dependencies"
	@echo "  make dev     — Install and run API + App"
	@echo "  make deploy  — Deploy with Docker Compose"
	@echo "  make oracle  — Deploy with Oracle/Ollama compose"
