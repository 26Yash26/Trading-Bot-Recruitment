"""Makes ``import src.auction...`` work when running pytest from the repo root.

Also points the server at a throwaway data directory *before* anything imports
``server.config``, which reads the environment at import time. Without this a
test run would open the real ``.local/quantguild.db`` and write test users,
sessions and submissions into it.
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

os.environ.setdefault("QG_DATA_DIR", tempfile.mkdtemp(prefix="quantguild-test-"))
os.environ.setdefault("QG_ADMIN_EMAILS", "admin@smail.iitm.ac.in")
os.environ.setdefault("QG_PUBLIC_ORIGIN", "http://localhost:8000")
