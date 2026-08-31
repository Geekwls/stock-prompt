#!/usr/bin/env python3
"""从项目 Skill 母本生成跨平台 Markdown Prompt，并检查内容漂移。"""

import argparse
import difflib
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MAPPINGS = {
    ROOT / ".agents/skills/daily-review/SKILL.md":
        ROOT / "prompts/daily-review/每天强势板块产业链共振分析.md",
    ROOT / ".agents/skills/market-prediction/SKILL.md":
        ROOT / "prompts/market-prediction/A股盘前全景策略研判.md",
    ROOT / ".agents/skills/sector-rotation/SKILL.md":
        ROOT / "prompts/sector-rotation/5日内板块轮动节奏分析.md",
}


def prompt_body(skill_text: str) -> str:
    """移除 SKILL.md 的 YAML frontmatter，保留完整 Markdown 正文。"""
    lines = skill_text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ValueError("SKILL.md 缺少起始 YAML frontmatter 分隔符")

    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            body = "".join(lines[index + 1:]).lstrip("\r\n").rstrip()
            if not body:
                raise ValueError("SKILL.md frontmatter 后没有 Markdown 正文")
            return body + "\n"
    raise ValueError("SKILL.md 缺少结束 YAML frontmatter 分隔符")


def sync(check_only: bool) -> int:
    drifted = 0
    for skill_path, prompt_path in MAPPINGS.items():
        expected = prompt_body(skill_path.read_text(encoding="utf-8"))
        actual = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
        label = prompt_path.relative_to(ROOT)

        if actual == expected:
            print(f"[OK] {label}")
            continue

        drifted += 1
        if check_only:
            print(f"[DRIFT] {label}")
            diff = difflib.unified_diff(
                actual.splitlines(), expected.splitlines(),
                fromfile=str(label), tofile=str(skill_path.relative_to(ROOT)),
                lineterm="",
            )
            for line in list(diff)[:20]:
                print(line)
        else:
            prompt_path.parent.mkdir(parents=True, exist_ok=True)
            prompt_path.write_text(expected, encoding="utf-8")
            print(f"[SYNC] {label} <- {skill_path.relative_to(ROOT)}")

    if check_only and drifted:
        print(f"[FAIL] {drifted} 份 Prompt 与 Skill 母本不一致")
        return 1
    print("[SUCCESS] Prompt 同步检查通过" if check_only else "[SUCCESS] 全部 Prompt 已同步")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="同步或检查 prompts/ 与 .agents/skills/ 的正文一致性")
    parser.add_argument("--check", action="store_true", help="只检查漂移，不修改文件")
    args = parser.parse_args()
    return sync(check_only=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
