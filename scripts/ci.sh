#!/usr/bin/env bash
# Local mirror of the CI "Tests" job (.github/workflows/test.yml): the same
# steps with the same flags and the same locked tool versions. By default it
# runs the one leg that carries every gate — Python 3.13 with lint, format,
# types, tests under 100% coverage, the docs fences and the wheel budget —
# in about a minute. The other matrix legs (3.11, 3.12, 3.14) rerun the same
# tests to catch stdlib drift between Python versions; CI runs them on every
# push, so locally they are opt-in, for reproducing a red CI leg.
#
# Usage:
#   scripts/ci.sh              # the gate: Python 3.13
#   scripts/ci.sh 3.14         # one other leg (reproducing a CI failure)
#   scripts/ci.sh 3.11 3.12 3.13 3.14   # the whole CI matrix
#
# Each leg syncs an isolated environment under .venv-ci/<version> (the main
# .venv is never touched), so warm re-runs skip straight to the checks.
# Legs run to completion even after a failure (CI sets fail-fast: false);
# within a leg, a failing step ends the leg, exactly as CI steps do.
set -uo pipefail
cd "$(dirname "$0")/.."

VERSIONS=("$@")
[ ${#VERSIONS[@]} -eq 0 ] && VERSIONS=(3.13)
COVERAGE_LEG=3.13
WHEEL_BUDGET_MB=50  # half of PyPI's 100 MB file cap; publish.yml enforces the same budget

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

# Build the real release wheel and hold it under the declared budget. Runs on
# the coverage leg only (the wheel is abi3 — one artifact serves the matrix);
# the CI twin of this gate lives in publish.yml, not the Tests job. The build
# gets its own cargo target directory: sharing one with the per-leg sync made
# each build evict the other's output, so this step recompiled the crate
# (24 s) every run instead of reusing it (2 s).
check_wheel_size() {
    local out="target/wheels-ci"
    rm -rf "$out"
    CARGO_TARGET_DIR="target/wheel-size" uv build --wheel -o "$out" || return 1
    local whl size
    whl=$(echo "$out"/*.whl)
    size=$(wc -c < "$whl")
    echo "$(basename "$whl"): $((size / 1024 / 1024)) MB (budget ${WHEEL_BUDGET_MB} MB, PyPI cap 100 MB)"
    [ "$size" -le $((WHEEL_BUDGET_MB * 1024 * 1024)) ]
}

run_leg() {
    local v=$1
    export UV_PROJECT_ENVIRONMENT=".venv-ci/${v}"
    step "install (py${v})" uv sync --all-extras --group dev --group docs --python "$v" || return 1
    step "lint (py${v})" uv run --no-sync --python "$v" ruff check src/ tests/ || return 1
    step "format (py${v})" uv run --no-sync --python "$v" ruff format --check src/ tests/ || return 1
    if [ "$v" = "$COVERAGE_LEG" ]; then
        step "types (py${v})" uv run --no-sync --python "$v" ty check src/ tests/ || return 1
        step "tests+cov (py${v})" uv run --no-sync --python "$v" pytest --tb=short \
            --cov --cov-report=term-missing --cov-report=xml --cov-fail-under=100 || return 1
        step "docs examples (py${v})" uv run --no-sync --python "$v" ruff check conftest.py \
            && uv run --no-sync --python "$v" pytest docs README.md --tb=short -p no:cov -n 0 || return 1
        step "wheel size" check_wheel_size || return 1
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
    echo -e "${GREEN}${BOLD}All legs green — parity with the CI Tests job on these versions.${RESET}"
else
    echo -e "${RED}${BOLD}RED — fix before committing or pushing.${RESET}"
fi
exit "$overall"
