#!/usr/bin/env python3
"""统一确定性计算 CLI；从 JSON 对象读取函数参数。"""

import argparse
import json
import sys
from pathlib import Path

script_path = Path(__file__).resolve()
for parent in script_path.parents:
    if (parent / "registry.json").is_file() or (parent / ".stock-prompt-runtime.json").is_file():
        sys.path.insert(0, str(parent))
        break
import tools.calculations as calculations


OPERATIONS = {name: getattr(calculations, name) for name in dir(calculations) if name.startswith("calculate_") or name == "validate_stock_hard_gate"}


def main(argv=None):
    parser = argparse.ArgumentParser(description="stock-prompt 确定性计算工具")
    parser.add_argument("operation", choices=sorted(OPERATIONS))
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", help="包含函数关键字参数的 JSON 文件")
    source.add_argument("--json", help="包含函数关键字参数的 JSON 字符串")
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.json) if args.json else json.loads(Path(args.input).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("输入必须为 JSON 对象")
        output = OPERATIONS[args.operation](**payload)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"[FAIL] {exc}")
        return 1
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
