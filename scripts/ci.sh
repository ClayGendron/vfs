#!/usr/bin/env bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
BOLD='\033[1m'
RESET='\033[0m'

pass() { echo -e "${GREEN}${BOLD}PASS${RESET} $1"; }
fail() { echo -e "${RED}${BOLD}FAIL${RESET} $1"; exit 1; }

echo -e "${BOLD}Running CI checks...${RESET}\n"

echo "=> Lint"
uvx ruff check src/ tests/ && pass "ruff check" || fail "ruff check"

echo ""
echo "=> Format"
uvx ruff format --check src/ tests/ && pass "ruff format" || fail "ruff format"

echo ""
echo "=> Type check"
uvx ty check src/ && pass "ty check" || fail "ty check"

echo ""
echo "=> Tests + coverage (99%)"
uv run pytest --tb=short --cov --cov-report=term-missing --cov-fail-under=99 && pass "pytest" || fail "pytest"

echo ""
echo -e "${GREEN}${BOLD}All CI checks passed.${RESET}"
