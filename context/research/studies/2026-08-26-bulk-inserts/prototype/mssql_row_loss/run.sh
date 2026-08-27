#!/bin/zsh
# usage: run.sh <table-prefix> <script.py> [args...]
# Runs one probe under the project venv (uv sync --extra mssql --group dev first;
# docker compose -f docker/compose.test.yml up -d --wait mssql). Results append
# to results.jsonl beside the scripts.
HERE=${0:A:h}
ROOT=${HERE:h:h:h:h:h:h}
table=$1; shift; script=$1; shift
RL_TABLE=$table RL_RESULTS=$HERE/results.jsonl PYTHONPATH=$HERE uv run --no-sync --project $ROOT python $HERE/$script "$@" 2>&1 | grep -v "no effect when used outside"
