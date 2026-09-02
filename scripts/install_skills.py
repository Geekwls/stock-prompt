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
GENERATOR = ROOT / "scripts" / "generate_report_card.py"
SKILL_NAMES = ("daily-review", "market-prediction", "sector-rotation", "stock-analysis")
MANIFEST_NAME = ".stock-prompt-manifest.json"


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
        files[f"{skill}/scripts/generate_report_card.py"] = GENERATOR
    return files


def sync_workspace_generator(dry_run=False):
    changed = 0
    for skill in SKILL_NAMES:
        destination = SOURCE_ROOT / skill / "scripts" / GENERATOR.name
        if destination.exists() and file_hash(destination) == file_hash(GENERATOR):
            continue
        changed += 1
        print(f"[SYNC] {destination.relative_to(ROOT)}")
        if not dry_run:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(GENERATOR, destination)
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


def main():
    args = parse_args()
    if not GENERATOR.is_file():
        print(f"[ERR] 报告卡母本不存在: {GENERATOR}")
        return 1

    if args.check:
        failures = 0
        master_hash = file_hash(GENERATOR)
        for skill in SKILL_NAMES:
            bundled = SOURCE_ROOT / skill / "scripts" / GENERATOR.name
            if not bundled.is_file() or file_hash(bundled) != master_hash:
                print(f"[DRIFT] workspace/{skill}/scripts/{GENERATOR.name}")
                failures += 1
        files = source_files()
        for label, root in target_roots(args.target):
            failures += check_target(label, root, files)
        if failures:
            print(f"[FAIL] 共发现 {failures} 处缺失、漂移或残留")
            return 1
        print("[SUCCESS] Skill 一致性检查通过")
        return 0

    sync_workspace_generator(args.dry_run)
    files = source_files()
    for label, root in target_roots(args.target):
        install_to(label, root, files, args.dry_run)
    print("[SUCCESS] 演练完成，未写入文件" if args.dry_run else "[SUCCESS] Skill 安装/同步完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
