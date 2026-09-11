#!/usr/bin/env python3
"""只读检查 stock-prompt 版本、Skill、MCP、日历与本地状态安全性。"""

import argparse
import importlib.util
import json
import os
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_version_parity import collect_errors
from project_registry import load_registry, resolve_path


ROOT = Path(__file__).resolve().parent.parent
REGISTRY = load_registry()
MANIFEST = ".stock-prompt-manifest.json"


def installed_roots():
    home = Path.home()
    codex_home = Path(os.environ.get("CODEX_HOME", home / ".codex"))
    return {
        "gemini": home / ".gemini" / "skills",
        "antigravity": home / ".gemini" / "antigravity" / "skills",
        "codex": codex_home / "skills",
        "workbuddy": home / ".workbuddy-ai" / "skills",
    }


def manifest_status(root):
    path = root / MANIFEST
    if not path.is_file():
        return {"installed": False, "version": None, "current": False}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"installed": True, "version": "unreadable", "current": False}
    version = payload.get("project_version", "legacy")
    return {"installed": True, "version": version, "current": version == REGISTRY["project"]["version"]}


def permission_status(path, expected):
    if not path.exists():
        return {"exists": False, "secure": True, "mode": None}
    mode = stat.S_IMODE(path.stat().st_mode)
    return {"exists": True, "secure": mode & ~expected == 0, "mode": oct(mode)}


def mcp_registered():
    home = Path.home()
    candidates = (
        home / ".gemini" / "antigravity" / "mcp_config.json",
        home / ".gemini" / "mcp_config.json",
        home / ".cursor" / "mcp.json",
        home / ".workbuddy-ai" / "mcp.json",
        Path(os.environ.get("CODEX_HOME", home / ".codex")) / "config.toml",
    )
    for path in candidates:
        try:
            if path.is_file() and "marketgraph" in path.read_text(encoding="utf-8", errors="ignore"):
                return True
        except OSError:
            continue
    return False


def calendar_status():
    path = ROOT / "data" / "a_share_trading_calendar.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        dates = sorted(payload.get("trading_days", []))
        closed = sorted(payload.get("closed_dates", []))
        covered_years = sorted(payload.get("covered_years", []))
        return {
            "available": bool(dates or closed),
            "precision": "calendar" if dates else "holiday_calendar" if covered_years else "closed_dates_only",
            "covered_years": covered_years,
            "last_trading_day": dates[-1] if dates else None,
            "last_closed_date": closed[-1] if closed else None,
        }
    except (OSError, ValueError, TypeError):
        return {"available": False, "precision": "unavailable", "covered_years": [], "last_trading_day": None, "last_closed_date": None}


def thesis_status(state_base):
    root = Path(os.environ.get("STOCK_PROMPT_THESIS_DIR") or (state_base / "theses"))
    total = 0
    pending = 0
    due_soon = 0
    if root.is_dir():
        from datetime import date, timedelta

        horizon = date.today() + timedelta(days=3)
        for path in root.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                continue
            total += 1
            for trigger in payload.get("next_triggers", []):
                if not isinstance(trigger, dict) or trigger.get("status") != "pending":
                    continue
                pending += 1
                deadline = str(trigger.get("deadline") or "")[:10]
                try:
                    if deadline and date.fromisoformat(deadline) <= horizon:
                        due_soon += 1
                except ValueError:
                    continue
    return {"total": total, "pending_triggers": pending, "due_soon": due_soon}


def collect_status():
    skills = {item["id"]: resolve_path(item["source"]).is_dir() for item in REGISTRY["skills"]}
    state_base = Path(os.environ.get("STOCK_PROMPT_STATE_HOME", Path.home() / ".stock-prompt"))
    parity_errors = collect_errors()
    return {
        "project_version": REGISTRY["project"]["version"],
        "version_parity": {"ok": not parity_errors, "errors": parity_errors},
        "skills": {"ready": sum(skills.values()), "total": len(skills), "details": skills},
        "installed_targets": {name: manifest_status(path) for name, path in installed_roots().items()},
        "mcp": {
            "entrypoint": str(resolve_path(REGISTRY["mcp"]["entrypoint"])),
            "entrypoint_exists": resolve_path(REGISTRY["mcp"]["entrypoint"]).is_file(),
            "registered": mcp_registered(),
            "tool_count": len(REGISTRY["mcp"]["tools"]),
        },
        "calendar": calendar_status(),
        "dependencies": {
            "Pillow": importlib.util.find_spec("PIL") is not None,
        },
        "theses": thesis_status(state_base),
        "state_permissions": {
            "state": permission_status(state_base / "state", 0o700),
            "eval": permission_status(state_base / "eval", 0o700),
            "theses": permission_status(state_base / "theses", 0o700),
        },
    }


def main():
    parser = argparse.ArgumentParser(description="诊断 stock-prompt 安装与运行环境（只读）")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    args = parser.parse_args()
    status = collect_status()
    if args.json:
        print(json.dumps(status, ensure_ascii=False, indent=2))
    else:
        print(f"stock-prompt {status['project_version']}")
        print(f"版本一致性: {'正常' if status['version_parity']['ok'] else '异常'}")
        print(f"项目 Skill: {status['skills']['ready']}/{status['skills']['total']}")
        for name, item in status["installed_targets"].items():
            label = "未安装" if not item["installed"] else ("最新版" if item["current"] else f"待更新 ({item['version']})")
            print(f"{name}: {label}")
        mcp = status["mcp"]
        print(f"MarketGraph MCP: {'已注册' if mcp['registered'] else '未检测到注册'}，工具 {mcp['tool_count']} 个")
        calendar = status["calendar"]
        years = ",".join(str(year) for year in calendar.get("covered_years", [])) or "N/A"
        print(f"交易日历: {'可用' if calendar['available'] else '不可用'}，精度 {calendar['precision']}，覆盖年份 {years}")
        print(f"报告卡依赖 Pillow: {'可用' if status['dependencies']['Pillow'] else '缺失（运行 pip install -r requirements.txt）'}")
        theses = status["theses"]
        thesis_line = f"个股 Thesis: {theses['total']} 只，待核验触发器 {theses['pending_triggers']} 条"
        if theses["due_soon"]:
            thesis_line += f"（3 日内到期 {theses['due_soon']} 条，运行 thesis due 查看）"
        print(thesis_line)
        insecure = [name for name, item in status["state_permissions"].items() if not item["secure"]]
        print(f"状态目录权限: {'安全' if not insecure else '需收紧 ' + ','.join(insecure)}")
    failed = not status["version_parity"]["ok"] or status["skills"]["ready"] != status["skills"]["total"]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
