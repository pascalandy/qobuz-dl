# qobuz-dl project commands
# Use uv for Python environment management and command execution.

# List available commands
_default:
    @just --list

# Install project and development dependencies
sync:
    uv sync --dev

# Format source, tests, and docs-supporting Python files
fmt:
    uv run ruff format .

# Check formatting without writing changes
fmt-check:
    uv run ruff format --check .

# Run lint checks
lint:
    uv run ruff check .

# Run lint checks and apply safe fixes
lint-fix:
    uv run ruff check . --fix

# Run unit tests
test:
    uv run pytest

# Build source and wheel distributions
build:
    uv build

# Run CLI smoke checks
smoke:
    uv run qobuz-dl --help
    uv run qobuz-dl dl --help
    uv run qobuz-dl fun --help
    uv run qobuz-dl lucky --help

# Run all local quality gates
check:
    uv run ruff format --check .
    uv run ruff check .
    uv run pytest
    uv run qobuz-dl --help
    uv run qobuz-dl dl --help
    uv run qobuz-dl fun --help
    uv run qobuz-dl lucky --help
    uv build

# Alias for CI
ci: check
