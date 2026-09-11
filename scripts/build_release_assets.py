#!/usr/bin/env python3
"""构建 GitHub Release 完整包、Skills 直装包与 SHA256SUMS。"""

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import install_skills
from project_registry import load_registry


ROOT = Path(__file__).resolve().parents[1]
RELEASE_MANIFEST = ".stock-prompt-release.json"


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            value.update(chunk)
    return value.hexdigest()


def write_zip(path, entries, prefix):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative, source in sorted(entries.items()):
            archive.write(source, f"{prefix}/{relative}")


def tracked_files():
    output = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True)
    return {relative: ROOT / relative for relative in output.splitlines() if (ROOT / relative).is_file()}


def release_manifest_file(output, name, version, entries):
    release_manifest = output / name
    release_manifest.write_text(json.dumps({
        "format": 1,
        "project": "stock-prompt",
        "project_version": version,
        "source_type": "github-release",
        "managed_files": sorted(entries),
        "hashes": {key: install_skills.file_hash(source) for key, source in sorted(entries.items())},
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return release_manifest


def skill_files(version, output):
    entries = dict(install_skills.source_files())
    release_manifest = release_manifest_file(output, "skills-release-manifest.json", version, entries)
    entries[release_manifest.name] = release_manifest
    return entries, release_manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description="构建 stock-prompt Release 资产")
    parser.add_argument("--output", default="dist")
    parser.add_argument("--version")
    args = parser.parse_args(argv)
    version = str(args.version or load_registry()["project"]["version"]).lstrip("v")
    tag = f"v{version}"
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    full = output / f"stock-prompt-{tag}.zip"
    skills = output / f"stock-prompt-skills-{tag}.zip"
    full_entries = tracked_files()
    full_manifest = release_manifest_file(output, "full-release-manifest.json", version, full_entries)
    full_entries[RELEASE_MANIFEST] = full_manifest
    write_zip(full, full_entries, f"stock-prompt-{tag}")
    entries, temporary_manifest = skill_files(version, output)
    entries[RELEASE_MANIFEST] = entries.pop(temporary_manifest.name)
    try:
        write_zip(skills, entries, f"stock-prompt-skills-{tag}")
    finally:
        temporary_manifest.unlink(missing_ok=True)
        full_manifest.unlink(missing_ok=True)
    sums = output / "SHA256SUMS"
    sums.write_text(f"{digest(full)}  {full.name}\n{digest(skills)}  {skills.name}\n", encoding="utf-8")
    print(full)
    print(skills)
    print(sums)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
