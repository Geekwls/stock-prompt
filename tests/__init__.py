"""
tests package initialization.

Guarantees full isolation from production user storage (~/.stock-prompt)
during test runs (unittest / pytest) if STOCK_PROMPT_HOME is not explicitly set.
"""

import atexit
import os
import shutil
import tempfile

if "STOCK_PROMPT_HOME" not in os.environ:
    _SESSION_DIR = tempfile.mkdtemp(prefix="sp-test-session-")
    os.environ["STOCK_PROMPT_HOME"] = _SESSION_DIR

    def _cleanup():
        shutil.rmtree(_SESSION_DIR, ignore_errors=True)

    atexit.register(_cleanup)
