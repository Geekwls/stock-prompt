#!/usr/bin/env python3
"""安装、更新或校验 stock-prompt Skills。

默认安装到 Gemini、Antigravity 与 Codex。使用 manifest 只清理本项目曾经
安装、但新版本已删除的文件，不触碰用户自行添加的文件。
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


ROOT = Path(__file__).resolve().parent.parent
SOURCE_ROOT = ROOT / ".agents" / "skills"
SKILL_NAMES = ("daily-review", "market-prediction", "sector-rotation", "stock-analysis")
MANIFEST_NAME = ".stock-prompt-manifest.json"
# 母本位于 scripts/ 下的公共脚本，按 skill 捆绑分发（安装后每个技能目录自带可用副本）。
BUNDLED_SCRIPTS = {
    "generate_report_card.py": (ROOT / "scripts" / "generate_report_card.py", SKILL_NAMES),
    "eval_tracker.py": (ROOT / "scripts" / "eval_tracker.py", ("market-prediction", "daily-review")),
}
MCP_SERVER = ROOT / "mcp" / "marketgraph-mcp" / "server.py"
MCP_CONFIG_CANDIDATES = (
    Path.home() / ".gemini" / "antigravity" / "mcp_config.json",
    Path.home() / ".gemini" / "mcp_config.json",
    Path.home() / ".cursor" / "mcp.json",
    Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "config.toml",
)


def target_roots(target):
    home = Path.home()
    codex_root = Path(os.environ.get("CODEX_HOME", home / ".codex")) / "skills"
    roots = {
        "gemini": home / ".gemini" / "skills",
        "antigravity": home / ".gemini" / "antigravity" / "skills",
        "codex": codex_root,
    }
    if target == "all":
        return list(roots.items())
    if target == "workspace":
        return []
    return [(target, roots[target])]


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_files():
    files = {}
    for skill in SKILL_NAMES:
        skill_root = SOURCE_ROOT / skill
        if not skill_root.is_dir():
            raise FileNotFoundError(f"Skill 母本不存在: {skill_root}")
        for path in skill_root.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                relative = Path(skill) / path.relative_to(skill_root)
                files[relative.as_posix()] = path
    for name, (source, skills) in BUNDLED_SCRIPTS.items():
        if not source.is_file():
            raise FileNotFoundError(f"捆绑脚本母本不存在: {source}")
        for skill in skills:
            files[f"{skill}/scripts/{name}"] = source
    return files


def sync_workspace_scripts(dry_run=False):
    changed = 0
    for name, (source, skills) in BUNDLED_SCRIPTS.items():
        for skill in skills:
            destination = SOURCE_ROOT / skill / "scripts" / name
            if destination.exists() and file_hash(destination) == file_hash(source):
                continue
            changed += 1
            print(f"[SYNC] {destination.relative_to(ROOT)}")
            if not dry_run:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
    return changed


def load_manifest(root):
    path = root / MANIFEST_NAME
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        hashes = payload.get("hashes", {})
        if isinstance(hashes, dict):
            return hashes
        return {relative: None for relative in payload.get("managed_files", [])}
    except (OSError, ValueError, TypeError):
        print(f"[WARN] 无法读取旧 manifest，不执行旧文件清理: {path}")
        return {}


def write_manifest(root, files):
    payload = {
        "format": 1,
        "project": "stock-prompt",
        "managed_files": sorted(files),
        "hashes": {relative: file_hash(source) for relative, source in sorted(files.items())},
    }
    path = root / MANIFEST_NAME
    temporary = root / f"{MANIFEST_NAME}.tmp"
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def remove_empty_parents(path, stop):
    current = path.parent
    while current != stop and stop in current.parents:
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def install_to(label, root, files, dry_run=False):
    old_manifest = load_manifest(root)
    old_managed = set(old_manifest)
    new_managed = set(files)
    stale = sorted(old_managed - new_managed)
    changed = []

    for relative, source in files.items():
        destination = root / relative
        if not destination.exists() or file_hash(destination) != file_hash(source):
            changed.append((relative, source, destination))

    print(f"[*] {label}: 新增/更新 {len(changed)}，清理旧文件 {len(stale)}")
    for relative, _, _ in changed:
        print(f"  [WRITE] {relative}")
    for relative in stale:
        print(f"  [DELETE] {relative}")

    if dry_run:
        return

    root.mkdir(parents=True, exist_ok=True)
    backup_candidates = []
    for relative, _, destination in changed:
        if not destination.is_file():
            continue
        previous_hash = old_manifest.get(relative)
        if previous_hash is None or file_hash(destination) != previous_hash:
            backup_candidates.append((relative, destination))
    if backup_candidates:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_root = root / ".stock-prompt-backups" / stamp
        for relative, destination in backup_candidates:
            backup = backup_root / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(destination, backup)
        print(f"[BACKUP] 已备份 {len(backup_candidates)} 个用户修改或旧版文件到 {backup_root}")
    for _, source, destination in changed:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    for relative in stale:
        destination = root / relative
        if destination.is_file():
            destination.unlink()
            remove_empty_parents(destination, root)
    write_manifest(root, files)


def check_target(label, root, files):
    failures = 0
    for relative, source in files.items():
        destination = root / relative
        if not destination.is_file():
            print(f"[MISS] {label}/{relative}")
            failures += 1
        elif file_hash(destination) != file_hash(source):
            print(f"[DRIFT] {label}/{relative}")
            failures += 1
    for relative in sorted(set(load_manifest(root)) - set(files)):
        print(f"[STALE] {label}/{relative}")
        failures += 1
    if failures == 0:
        print(f"[OK] {label}: Skill 全量文件一致")
    return failures


def parse_args():
    parser = argparse.ArgumentParser(description="安装或校验 stock-prompt Skills")
    parser.add_argument("--check", action="store_true", help="只校验，不写入")
    parser.add_argument("--dry-run", action="store_true", help="显示计划，不写入")
    parser.add_argument(
        "--target",
        choices=("all", "gemini", "antigravity", "codex", "workspace"),
        default="all",
        help="安装目标；workspace 只同步仓库内报告卡脚本",
    )
    return parser.parse_args()


def mcp_registered():
    for config in MCP_CONFIG_CANDIDATES:
        try:
            if config.is_file() and "marketgraph" in config.read_text(encoding="utf-8", errors="ignore"):
                return True
        except OSError:
            continue
    return False


def print_post_install_guide():
    print()
    print("=" * 62)
    print("🚀 stock-prompt 四大技能已就绪 —— 30 秒快速上手")
    print("=" * 62)
    print("🗣 直接用自然语言提问，Agent 会自动激活对应技能：")
    print('   盘前 8:30-9:15 : "做一份今天的盘前全景预测"')
    print('   收盘 15:00 后  : "帮我深度复盘今天的强势板块与产业链共振"')
    print('   周五 / 周末    : "分析近 5 个交易日的板块轮动和主线节奏"')
    print('   任意时段       : "诊断 300308" / "中际旭创现在能买吗"')
    print("🎨 战报长图（仓库根目录运行）:")
    print("   python scripts/generate_report_card.py --demo --type stock")
    print("🔄 日常更新: bash scripts/update.sh （Windows: scripts\\update.bat）")
    print()
    if MCP_SERVER.is_file() and not mcp_registered():
        print("🔌 [建议] 尚未检测到 MarketGraph MCP 数据网关注册。")
        print("   配置后 stock-analysis 可自动通过行情硬门槛（120日K线/龙虎榜/财务排雷）：")
        print("   在宿主 MCP 配置（如 ~/.gemini/antigravity/mcp_config.json）加入：")
        print(f'     "marketgraph-data": {{"command": "python", "args": ["{MCP_SERVER}"]}}')
        print("   快速自测: python mcp/marketgraph-mcp/server.py --test get_stock_kline 贵州茅台")
        print("   完整说明: mcp/marketgraph-mcp/README.md")
    elif MCP_SERVER.is_file():
        print("🔌 已检测到 MarketGraph MCP 注册，个股诊断数据链路就绪。")


def main():
    args = parse_args()
    missing = [str(source) for source, _ in BUNDLED_SCRIPTS.values() if not source.is_file()]
    if missing:
        print(f"[ERR] 捆绑脚本母本不存在: {', '.join(missing)}")
        return 1

    if args.check:
        failures = 0
        for name, (source, skills) in BUNDLED_SCRIPTS.items():
            master_hash = file_hash(source)
            for skill in skills:
                bundled = SOURCE_ROOT / skill / "scripts" / name
                if not bundled.is_file() or file_hash(bundled) != master_hash:
                    print(f"[DRIFT] workspace/{skill}/scripts/{name}")
                    failures += 1
        files = source_files()
        for label, root in target_roots(args.target):
            failures += check_target(label, root, files)
        if failures:
            print(f"[FAIL] 共发现 {failures} 处缺失、漂移或残留")
            return 1
        print("[SUCCESS] Skill 一致性检查通过")
        return 0

    sync_workspace_scripts(args.dry_run)
    files = source_files()
    for label, root in target_roots(args.target):
        install_to(label, root, files, args.dry_run)
    if args.dry_run:
        print("[SUCCESS] 演练完成，未写入文件")
    else:
        print("[SUCCESS] Skill 安装/同步完成")
        if args.target != "workspace":
            print_post_install_guide()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
