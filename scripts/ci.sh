#!/usr/bin/env bash
# Local mirror of the CI "Tests" job (.github/workflows/test.yml): same steps,
# same flags, same locked tool versions, same Python matrix. Green here means
# green there (the only CI-exclusive step is the Codecov upload).
#
# Usage:
#   scripts/ci.sh              # full matrix: 3.11 3.12 3.13 3.14
#   scripts/ci.sh 3.14         # one leg
#   scripts/ci.sh 3.13 3.14    # any subset
#
# Each leg syncs an isolated environment under .venv-ci/<version> (the main
# .venv is never touched), so warm re-runs skip straight to the checks.
# Legs run to completion even after a failure (CI sets fail-fast: false);
# within a leg, a failing step ends the leg, exactly as CI steps do.
set -uo pipefail
cd "$(dirname "$0")/.."

VERSIONS=("$@")
[ ${#VERSIONS[@]} -eq 0 ] && VERSIONS=(3.11 3.12 3.13 3.14)
COVERAGE_LEG=3.13

RED='\033[0;31m'
GREEN='\033[0;32m'
BOLD='\033[1m'
RESET='\033[0m'

step() {
    local name=$1
    shift
    echo -e "\n${BOLD}--- ${name}${RESET}"
    "$@" && echo -e "${GREEN}${BOLD}PASS${RESET} ${name}" && return 0
    echo -e "${RED}${BOLD}FAIL${RESET} ${name}"
    leg_status="${name} failed"
    return 1
}

run_leg() {
    local v=$1
    export UV_PROJECT_ENVIRONMENT=".venv-ci/${v}"
    step "install (py${v})" uv sync --all-extras --group dev --python "$v" || return 1
    step "lint (py${v})" uv run --no-sync --python "$v" ruff check src/ tests/ || return 1
    step "format (py${v})" uv run --no-sync --python "$v" ruff format --check src/ tests/ || return 1
    if [ "$v" = "$COVERAGE_LEG" ]; then
        step "types (py${v})" uv run --no-sync --python "$v" ty check src/ tests/ || return 1
        step "tests+cov (py${v})" uv run --no-sync --python "$v" pytest --tb=short \
            --cov --cov-report=term-missing --cov-report=xml --cov-fail-under=100 || return 1
    else
        step "tests (py${v})" uv run --no-sync --python "$v" pytest --tb=short || return 1
    fi
}

overall=0
summary=()
for v in "${VERSIONS[@]}"; do
    echo -e "\n${BOLD}=== Python ${v} ===${RESET}"
    leg_status="green"
    run_leg "$v" || overall=1
    summary+=("$v: $leg_status")
done
unset UV_PROJECT_ENVIRONMENT

echo -e "\n${BOLD}=== Matrix summary ===${RESET}"
for line in "${summary[@]}"; do
    case "$line" in
        *green) echo -e "  ${GREEN}${line}${RESET}" ;;
        *) echo -e "  ${RED}${line}${RESET}" ;;
    esac
done
if [ "$overall" -eq 0 ]; then
    echo -e "${GREEN}${BOLD}All legs green — parity with the CI Tests job.${RESET}"
else
    echo -e "${RED}${BOLD}RED — fix before committing or pushing.${RESET}"
fi
exit "$overall"
