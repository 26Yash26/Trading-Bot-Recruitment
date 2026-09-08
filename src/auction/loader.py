"""Load a participant's ``Bot`` class from a .py file by path.

Used by ``run_local.py`` and (later) the evaluation harness. Phase 0.C does a
plain import; the sandbox in 1.A wraps the resulting class.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


def load_bot_class(path):
    """Import ``path`` and return its ``Bot`` class.

    Raises ``ValueError`` if the file has no class named ``Bot``.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)

    spec = importlib.util.spec_from_file_location(f"submission_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    bot_cls = getattr(module, "Bot", None)
    if bot_cls is None or not isinstance(bot_cls, type):
        raise ValueError(f"{path} does not define a class named 'Bot'")
    return bot_cls
