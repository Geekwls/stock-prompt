#!/usr/bin/env python3
"""将公共研究契约同步到四个可独立安装的 Skill。"""

import argparse
import difflib
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "contracts" / "common-research-contract.md"
TARGETS = tuple(
    ROOT / ".agents" / "skills" / name / "references" / "common-research-contract.md"
    for name in ("daily-review", "market-prediction", "sector-rotation", "stock-analysis")
)


def expected_text():
    return "<!-- 由 contracts/common-research-contract.md 自动生成，请勿单独修改。 -->\n\n" + SOURCE.read_text(encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="同步公共研究契约")
    parser.add_argument("--check", action="store_true", help="仅检查漂移")
    args = parser.parse_args()
    expected = expected_text()
    drifted = 0
    for target in TARGETS:
        actual = target.read_text(encoding="utf-8") if target.exists() else ""
        label = target.relative_to(ROOT)
        if actual == expected:
            print(f"[OK] {label}")
            continue
        drifted += 1
        if args.check:
            print(f"[DRIFT] {label}")
            for line in list(difflib.unified_diff(actual.splitlines(), expected.splitlines(), lineterm=""))[:12]:
                print(line)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(expected, encoding="utf-8")
            print(f"[SYNC] {label}")
    if args.check and drifted:
        return 1
    print("[SUCCESS] 公共研究契约同步检查通过" if args.check else "[SUCCESS] 公共研究契约已同步")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
