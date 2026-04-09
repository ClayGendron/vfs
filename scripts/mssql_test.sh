#!/usr/bin/env bash
set -euo pipefail

# Match tests/conftest.py::_MSSQL_DEFAULT_URL exactly; export so ad-hoc
# pytest invocations from this shell pick it up too.
export GROVER_MSSQL_URL="${GROVER_MSSQL_URL:-mssql+aioodbc://sa:Strong!Passw0rd@localhost:1433/grover_test?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes}"

echo "=> Running MSSQL backend tests against ${GROVER_MSSQL_URL%%@*}@..."
uv run pytest tests/test_mssql_backend.py --mssql "$@"
