SHELL=/bin/bash -e

help:
	@echo - make black      	Format code
	@echo - make isort      	Sort imports
	@echo - make lint       	Run linter
	@echo - make typecheck  	Check types
	@echo - make clean      	Clean the project directory
	@echo - make test       	Run tests
	@echo - make coverage   	Run tests with coverage
	@echo - make venv       	Create a virtual environment and install dependencies
	@echo - make readme-preview Preview README with grip

.PHONY: lint
lint:
	@uv run flake8 xferx

.PHONY: isort
isort:
	@uv run isort --profile black xferx.py xferx tests

.PHONY: black
black: isort
	@uv run black -S xferx.py xferx tests

.PHONY: typecheck
typecheck:
	@uv run mypy --strict --no-warn-unused-ignores xferx

.PHONY: clean
clean:
	-rm -rf build dist bin lib lib64 share pyvenv.cfg *.egg-info

.PHONY: test
test:
	@uv run pytest

.PHONY: coverage
coverage:
	@uv run pytest --cov --cov-report=term-missing

.PHONY: typecheck
venv:
	@uv venv
	@uv pip install -e .
	@uv pip install -e ".[dev]"

.PHONY: readme-preview
readme-preview:
	@uv run grip 0.0.0.0:8080
