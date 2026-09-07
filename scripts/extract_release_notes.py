#!/usr/bin/env python3
"""从 CHANGELOG 提取指定版本段落。"""

import argparse
import re
from pathlib import Path


def extract(text, version):
    pattern = rf"(^## \[v{re.escape(version)}\][\s\S]*?)(?=^## \[v|\Z)"
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        raise ValueError(f"CHANGELOG 未找到 v{version}")
    return match.group(1).strip() + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    notes = extract(Path("CHANGELOG.md").read_text(encoding="utf-8"), args.version.lstrip("v"))
    Path(args.output).write_text(notes, encoding="utf-8")


if __name__ == "__main__":
    main()
