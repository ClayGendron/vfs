#!/usr/bin/env bash
# The docs site: export the public API from the source, then preview, build or check the app.
#
# Usage:
#   scripts/docs.sh export   # write docs-app/src/lib/generated/api.json from the docstrings
#   scripts/docs.sh dev      # export, then serve the docs locally and reload on a changed page
#   scripts/docs.sh build    # export, then build the static site into docs-app/build
#   scripts/docs.sh check    # build, then the type check and the app's tests: the gate for a docs change
#
# The export runs with the docs dependency group alone, so it never builds the Rust extension.
# A changed docstring is picked up by running the command again. Needs uv and bun.
set -euo pipefail
cd "$(dirname "$0")/.."

export_api() {
    uv run --only-group docs python scripts/docs_export.py
}

install_app() {
    (cd docs-app && bun install --frozen-lockfile)
}

# A port the system has just handed out, so a server left on the default port cannot stop the browser tests.
free_port() {
    uv run --only-group docs python -c "import socket; s = socket.socket(); s.bind(('127.0.0.1', 0)); print(s.getsockname()[1])"
}

case "${1:-}" in
    export)
        export_api
        ;;
    dev)
        export_api
        install_app
        cd docs-app && exec bun run dev
        ;;
    build)
        export_api
        install_app
        cd docs-app && bun run build
        ;;
    check)
        export_api
        install_app
        VFS_DOCS_PORT="$(free_port)"
        export VFS_DOCS_PORT
        cd docs-app && bun run build && bun run check && bun run test
        ;;
    *)
        echo "usage: scripts/docs.sh export|dev|build|check" >&2
        exit 2
        ;;
esac
