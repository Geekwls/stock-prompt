#!/usr/bin/env python3
"""stock-prompt 版本检查、安全更新与非打扰提醒。仅使用 Python 标准库。"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


SCRIPT = Path(__file__).resolve()
DEFAULT_REPO = "Geekwls/stock-prompt"
CACHE_NAME = "update-status.json"
RELEASE_MANIFEST = ".stock-prompt-release.json"
INSTALL_MANIFEST = ".stock-prompt-manifest.json"


def discover_root():
    for candidate in (SCRIPT.parent.parent, SCRIPT.parent.parent.parent):
        if any((candidate / name).is_file() for name in ("version.json", "registry.json", ".stock-prompt-runtime.json")):
            return candidate
    return SCRIPT.parent.parent


ROOT = discover_root()


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {} if default is None else default


def runtime_metadata(root=ROOT):
    version = read_json(root / "version.json")
    registry = read_json(root / "registry.json") or read_json(root / ".stock-prompt-runtime.json")
    project = registry.get("project", {})
    repo = version.get("repo") or str(project.get("homepage", "")).removeprefix("https://github.com/") or DEFAULT_REPO
    return {
        "version": str(version.get("latest") or project.get("version") or "unknown"),
        "repo": repo.rstrip("/"),
        "channel": str(version.get("channel") or "stable"),
    }


def version_key(value):
    text = str(value).strip().lstrip("v").split("-", 1)[0]
    try:
        parts = tuple(int(part) for part in text.split("."))
    except ValueError:
        return ()
    return parts + (0,) * (3 - len(parts))


def cache_path():
    override = os.environ.get("STOCK_PROMPT_UPDATE_CACHE")
    if override:
        return Path(override)
    state = Path(os.environ.get("STOCK_PROMPT_STATE_HOME", Path.home() / ".stock-prompt"))
    return state / CACHE_NAME


def load_cache():
    return read_json(cache_path(), {})


def save_cache(payload):
    path = cache_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def parse_time(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def fetch_bytes(url, timeout=8):
    request = urllib.request.Request(url, headers={"User-Agent": "stock-prompt-updater/1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def remote_version_url(repo):
    override = os.environ.get("STOCK_PROMPT_VERSION_URL")
    if override:
        return override
    if (ROOT / ".git").exists():
        return f"https://raw.githubusercontent.com/{repo}/main/version.json"
    return f"https://api.github.com/repos/{repo}/releases/latest"


def check_update(force=False, max_age_hours=24):
    local = runtime_metadata()
    cached = load_cache()
    checked = parse_time(cached.get("checked_at"))
    now = datetime.now(timezone.utc)
    if (not force and checked and cached.get("local_version") == local["version"]
            and now - checked < timedelta(hours=max_age_hours)):
        return {**cached, "cached": True}
    try:
        remote = json.loads(fetch_bytes(remote_version_url(local["repo"])).decode("utf-8"))
        latest = str(remote.get("latest") or remote.get("tag_name") or "unknown").lstrip("v")
        result = {
            "checked_at": now.isoformat(timespec="seconds"),
            "local_version": local["version"],
            "latest_version": latest,
            "update_available": bool(version_key(latest) and version_key(latest) > version_key(local["version"])),
            "release_url": remote.get("release_url") or remote.get("html_url") or f"https://github.com/{local['repo']}/releases/tag/v{latest}",
            "channel": remote.get("channel") or local["channel"],
            "status": "ok",
            "cached": False,
        }
    except (OSError, ValueError, urllib.error.URLError) as exc:
        result = {
            "checked_at": now.isoformat(timespec="seconds"),
            "local_version": local["version"],
            "latest_version": cached.get("latest_version", "unknown"),
            "update_available": False,
            "status": "unavailable",
            "error": str(exc),
            "cached": False,
        }
    try:
        save_cache(result)
    except OSError:
        pass
    return result


def installed_status():
    local = runtime_metadata()
    manifests = []
    candidates = [ROOT / INSTALL_MANIFEST]
    home = Path.home()
    candidates.extend((home / ".gemini" / "skills" / INSTALL_MANIFEST,
                       home / ".gemini" / "antigravity" / "skills" / INSTALL_MANIFEST,
                       Path(os.environ.get("CODEX_HOME", home / ".codex")) / "skills" / INSTALL_MANIFEST))
    for path in candidates:
        if path.is_file():
            item = read_json(path)
            manifests.append({"path": str(path), "version": item.get("project_version") or "legacy",
                              "source": item.get("source_type", "legacy")})
    return {"project": local, "root": str(ROOT), "source": "git" if (ROOT / ".git").exists() else "zip",
            "installations": manifests, "cached_check": load_cache()}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_extract(archive, destination):
    destination = Path(destination).resolve()
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            target = (destination / member.filename).resolve()
            if target != destination and destination not in target.parents:
                raise ValueError(f"ZIP 包含非法路径: {member.filename}")
        bundle.extractall(destination)


def release_asset_urls(repo, version, skills_only=False):
    tag = f"v{str(version).lstrip('v')}"
    filename = f"stock-prompt-skills-{tag}.zip" if skills_only else f"stock-prompt-{tag}.zip"
    base = f"https://github.com/{repo}/releases/download/{tag}"
    return filename, f"{base}/{filename}", f"{base}/SHA256SUMS"


def verify_checksum(path, checksums, filename):
    expected = None
    for line in checksums.decode("utf-8").splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == filename:
            expected = parts[0].lower()
            break
    if not expected or sha256(path) != expected:
        raise ValueError(f"{filename} SHA-256 校验失败")


def copy_release(source, destination):
    source, destination = Path(source), Path(destination)
    old_manifest = read_json(destination / RELEASE_MANIFEST) or read_json(destination / INSTALL_MANIFEST)
    new_manifest = read_json(source / RELEASE_MANIFEST)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_root = destination / ".stock-prompt-backups" / "repository" / stamp
    copied = 0
    for item in source.rglob("*"):
        if not item.is_file() or ".git" in item.parts:
            continue
        relative = item.relative_to(source)
        target = destination / relative
        if target.is_file() and target.read_bytes() != item.read_bytes():
            backup = backup_root / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        copied += 1
    old_files = set(old_manifest.get("managed_files", []))
    new_files = set(new_manifest.get("managed_files", []))
    for relative in sorted(old_files - new_files):
        target = destination / relative
        expected = old_manifest.get("hashes", {}).get(relative)
        if target.is_file() and expected and sha256(target) == expected:
            target.unlink()
        elif target.is_file():
            print(f"[WARN] 保留用户修改的旧文件: {relative}")
    return copied, backup_root if backup_root.exists() else None


def apply_git(target):
    if subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout.strip():
        raise RuntimeError("仓库存在未提交修改，请先提交或备份")
    subprocess.run(["git", "fetch", "origin", "main"], cwd=ROOT, check=True)
    subprocess.run(["git", "pull", "--ff-only", "origin", "main"], cwd=ROOT, check=True)
    subprocess.run([sys.executable, str(ROOT / "scripts" / "install_skills.py"), "--target", target], cwd=ROOT, check=True)


def apply_zip(info, target):
    installed_bundle = (ROOT / ".stock-prompt-runtime.json").is_file() and not (ROOT / "version.json").is_file()
    filename, asset_url, sums_url = release_asset_urls(runtime_metadata()["repo"], info["latest_version"], installed_bundle)
    with tempfile.TemporaryDirectory() as temporary:
        temporary = Path(temporary)
        archive = temporary / filename
        archive.write_bytes(fetch_bytes(asset_url, timeout=30))
        verify_checksum(archive, fetch_bytes(sums_url), filename)
        extracted = temporary / "extracted"
        safe_extract(archive, extracted)
        entries = [path for path in extracted.iterdir()]
        source = entries[0] if len(entries) == 1 and entries[0].is_dir() else extracted
        copied, backup = copy_release(source, ROOT)
        print(f"[OK] ZIP 更新写入 {copied} 个文件")
        if backup:
            print(f"[BACKUP] 原文件已备份至 {backup}")
    if installed_bundle:
        release = read_json(ROOT / RELEASE_MANIFEST)
        release.update({
            "installed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "source_repo": runtime_metadata()["repo"],
            "source_channel": "stable",
            "source_type": "github-release",
        })
        (ROOT / INSTALL_MANIFEST).write_text(
            json.dumps(release, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (ROOT / RELEASE_MANIFEST).unlink(missing_ok=True)
    installer = ROOT / "scripts" / "install_skills.py"
    if installer.is_file():
        subprocess.run([sys.executable, str(installer), "--target", target], cwd=ROOT, check=True)


def cmd_check(args):
    result = check_update(force=args.force, max_age_hours=args.max_age_hours)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result["status"] != "ok":
        if not args.quiet:
            print("版本检查暂不可用，不影响 Skill 使用。")
    elif result["update_available"]:
        print(f"发现 stock-prompt v{result['latest_version']}（当前 v{result['local_version']}）")
        print("更新命令: python scripts/stock_prompt.py update apply --yes")
    elif not args.quiet:
        print(f"stock-prompt v{result['local_version']} 已是最新版")
    return 0


def cmd_status(args):
    payload = installed_status()
    print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else
          f"stock-prompt v{payload['project']['version']} | 来源 {payload['source']} | 安装记录 {len(payload['installations'])}")
    return 0


def cmd_apply(args):
    info = check_update(force=True, max_age_hours=0)
    if info["status"] != "ok":
        print("[ERR] 无法确认远端版本，更新已停止")
        return 1
    if not info["update_available"]:
        print(f"stock-prompt v{info['local_version']} 已是最新版")
        return 0
    source = args.source if args.source != "auto" else ("git" if (ROOT / ".git").exists() else "zip")
    print(f"计划更新 v{info['local_version']} -> v{info['latest_version']}，来源 {source}")
    if not args.yes:
        print("未执行：更新会修改本地文件，请确认后添加 --yes")
        return 2
    try:
        apply_git(args.target) if source == "git" else apply_zip(info, args.target)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError, urllib.error.URLError) as exc:
        print(f"[ERR] 更新失败: {exc}")
        return 1
    print(f"[SUCCESS] 已更新到 v{info['latest_version']}")
    return 0


def parser():
    root = argparse.ArgumentParser(description="stock-prompt 更新管理器")
    sub = root.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", aliases=["reminder"], help="检查新版本；默认 24 小时缓存")
    check.add_argument("--force", action="store_true")
    check.add_argument("--quiet", action="store_true")
    check.add_argument("--json", action="store_true")
    check.add_argument("--max-age-hours", type=float, default=24)
    check.set_defaults(func=cmd_check)
    status = sub.add_parser("status", help="查看本地与安装状态")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=cmd_status)
    apply_cmd = sub.add_parser("apply", help="确认并安装最新版本")
    apply_cmd.add_argument("--yes", action="store_true", help="确认修改文件并执行更新")
    apply_cmd.add_argument("--source", choices=("auto", "git", "zip"), default="auto")
    apply_cmd.add_argument("--target", choices=("all", "gemini", "antigravity", "codex", "workspace"), default="all")
    apply_cmd.set_defaults(func=cmd_apply)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
