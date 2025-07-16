# FDD Pipeline Makefile
# Common development and deployment commands

.PHONY: help install install-dev test lint format check setup clean

# Default target
help:
	@echo "FDD Pipeline - Available Commands:"
	@echo "  install      Install production dependencies"
	@echo "  install-dev  Install development dependencies"
	@echo "  test         Run test suite"
	@echo "  lint         Run linting checks"
	@echo "  format       Format code with black"
	@echo "  check        Run all quality checks"
	@echo "  setup        Setup development environment"
	@echo "  clean        Clean temporary files"
	@echo "  config-check Validate configuration"

# Installation
install:
	uv pip sync requirements.txt

install-dev:
	uv pip sync requirements.txt
	uv pip install -r requirements-dev.txt
	pre-commit install

# Testing
test:
	pytest

test-cov:
	pytest --cov=src --cov-report=html --cov-report=term

# Code quality
lint:
	flake8 .
	mypy .

format:
	black .
	isort .

check: lint test
	@echo "All checks passed!"

# Setup
setup: install-dev
	@echo "Checking configuration..."
	python scripts/check_config.py
	@echo "Setup complete!"

# Database
db-migrate:
	supabase db push

db-reset:
	supabase db reset

# Prefect
prefect-start:
	prefect server start

prefect-deploy:
	prefect deployment build flows/scrape_mn.py:scrape_minnesota -n mn-weekly
	prefect deployment build flows/scrape_wi.py:scrape_wisconsin -n wi-weekly
	prefect deployment apply

# Cleanup
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf .coverage htmlcov/ .pytest_cache/