#!/usr/bin/env python3
"""兼容 CLI：调用 tools.artifacts 的标准 Artifact 存储实现。"""

import sys
from pathlib import Path

script_path = Path(__file__).resolve()
for parent in script_path.parents:
    if (parent / "registry.json").is_file() or (parent / ".stock-prompt-runtime.json").is_file():
        sys.path.insert(0, str(parent))
        break

from tools.artifacts.store import main


if __name__ == "__main__":
    raise SystemExit(main())
