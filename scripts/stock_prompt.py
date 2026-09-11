#!/usr/bin/env python3
"""stock-prompt 统一命令入口：聚合 artifact / handoff / thesis / eval / doctor / card / update 子命令。

子命令之后的参数原样转发给 scripts/ 下对应工具，保持各工具自有 CLI 与
参数不变；本入口只做发现与转发，便于全局安装用户一条命令直达。
"""

import json
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SCRIPTS_DIR = Path(__file__).resolve().parent

# 子命令 -> 目标脚本
SUBCOMMANDS = {
    "artifact": "artifact_store.py",
    "calculate": "calculate.py",
    "handoff": "handoff_store.py",
    "thesis": "thesis_store.py",
    "eval": "eval_tracker.py",
    "weekly": "weekly_digest.py",
    "doctor": "doctor.py",
    "card": "generate_report_card.py",
    "card-check": "check_schema_parity.py",
    "version-check": "check_version_parity.py",
    "update": "update_manager.py",
}

HELP = """stock-prompt 统一入口

用法: python scripts/stock_prompt.py <子命令> [参数原样转发]

子命令:
  artifact       标准研究 Artifact 校验/不可变写入/读取 (artifact_store.py)
  calculate      ATR/概率/机会分/板块/个股/评估纯函数 (calculate.py)
  handoff        交接摘要校验/写入/读取/清理 (handoff_store.py)
  thesis         个股长期 Thesis Ledger (thesis_store.py)
  eval           评估台账 record/result/replay/misses/report/report-mainline/migrate (eval_tracker.py)
  weekly         周度复盘摘要：预测质量+评分+主线+触发器 (weekly_digest.py)
  doctor         安装/版本/MCP/日历健康检查 (doctor.py)
  card           战报长图渲染 (generate_report_card.py)
  card-check     Schema 与运行时字段一致性检查 (check_schema_parity.py)
  version-check  版本一致性检查 (check_version_parity.py)
  update         检查、查看或安装新版本 (update_manager.py)
  --version      显示项目版本

示例:
  python scripts/stock_prompt.py artifact validate --input artifact.json
  python scripts/stock_prompt.py calculate calculate_atr_state --json '{"close": 101, "previous_close": 100, "atr14": 2}'
  python scripts/stock_prompt.py handoff latest --within-trading-days 3
  python scripts/stock_prompt.py eval replay --date 2026-09-08
  python scripts/stock_prompt.py weekly --days 7
  python scripts/stock_prompt.py doctor
  python scripts/stock_prompt.py update check
"""


def read_project_version():
    try:
        payload = json.loads((SCRIPTS_DIR.parent / "version.json").read_text(encoding="utf-8"))
        return str(payload.get("latest", "unknown"))
    except (OSError, ValueError):
        return "unknown"


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(HELP.strip())
        return 0
    if argv[0] == "--version":
        print(f"stock-prompt {read_project_version()}")
        return 0

    command, extra = argv[0], argv[1:]
    if command not in SUBCOMMANDS:
        print(f"[ERR] 未知子命令: {command}\n")
        print(HELP.strip())
        return 2
    target = SCRIPTS_DIR / SUBCOMMANDS[command]
    if not target.is_file():
        print(f"[ERR] 目标脚本不存在: {target}")
        return 1
    return subprocess.run([sys.executable, str(target)] + extra).returncode


if __name__ == "__main__":
    raise SystemExit(main())
