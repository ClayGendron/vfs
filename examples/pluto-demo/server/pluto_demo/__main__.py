"""``python -m pluto_demo`` serves the workspace on http://127.0.0.1:8765."""

from __future__ import annotations

import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run("pluto_demo.server:app", host="127.0.0.1", port=int(os.environ.get("PLUTO_PORT", "8765")), reload=False)
