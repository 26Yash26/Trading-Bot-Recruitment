"""Run the whole stack locally:  python -m server

Serves the API *and* the static site on one port, so http://localhost:8000 is
the real site, same routes, same behaviour as production, minus nginx.
"""

from __future__ import annotations

import uvicorn

from . import config
from .app import app

if __name__ == "__main__":
    config.ensure_dirs()
    print(f"  Quant Guild dev server -> http://{config.HOST}:{config.PORT}")
    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="info")
