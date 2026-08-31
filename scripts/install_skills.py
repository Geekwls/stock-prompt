#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一键安装/同步 stock-prompt 核心技能到 Antigravity 全局与工作区环境

用法:
  python3 scripts/install_skills.py           安装/同步所有技能
  python3 scripts/install_skills.py --check   仅校验各副本与母本是否一致（防漂移），不写入
"""

import hashlib
import os
import sys
import shutil

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def install_skills(check_only=False):
    src_workspace_skills = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".agents", "skills"))
    generator_script = os.path.abspath(os.path.join(os.path.dirname(__file__), "generate_report_card.py"))

    destinations = [
        os.path.join(os.path.expanduser("~"), ".gemini", "skills"),
        os.path.join(os.path.expanduser("~"), ".gemini", "antigravity", "skills"),
    ]

    skill_names = ["daily-review", "market-prediction", "sector-rotation", "stock-analysis"]

    if check_only:
        return check_consistency(generator_script, src_workspace_skills, destinations, skill_names)

    print("[*] 开始安装 stock-prompt 量化 Skills 到全局与工作区环境...")

    for dest_root in destinations:
        os.makedirs(dest_root, exist_ok=True)
        for skill in skill_names:
            src_dir = os.path.join(src_workspace_skills, skill)
            dest_dir = os.path.join(dest_root, skill)
            if os.path.exists(src_dir):
                shutil.copytree(src_dir, dest_dir, dirs_exist_ok=True)
                # 确保内置脚本同步
                scripts_dir = os.path.join(dest_dir, "scripts")
                os.makedirs(scripts_dir, exist_ok=True)
                if os.path.exists(generator_script):
                    shutil.copy2(generator_script, os.path.join(scripts_dir, "generate_report_card.py"))
                print(f"[OK] 已安装: {skill} -> {dest_dir}")

    # 同时为工作区内部 skill 同步一份 scripts
    for skill in skill_names:
        workspace_scripts_dir = os.path.join(src_workspace_skills, skill, "scripts")
        os.makedirs(workspace_scripts_dir, exist_ok=True)
        if os.path.exists(generator_script):
            shutil.copy2(generator_script, os.path.join(workspace_scripts_dir, "generate_report_card.py"))

    print("\n[SUCCESS] 所有 3 大核心 Skills 均已成功安装到全局及工作区环境！")


def _md5(path):
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def check_consistency(generator_script, src_workspace_skills, destinations, skill_names):
    """校验母本与各 skill 副本的 generate_report_card.py 是否一致"""
    if not os.path.exists(generator_script):
        print(f"[ERR] 母本脚本不存在: {generator_script}")
        return 1

    master_md5 = _md5(generator_script)
    print(f"[*] 母本: {generator_script}\n    md5: {master_md5}\n")

    targets = []
    for skill in skill_names:
        targets.append((f"workspace/{skill}", os.path.join(src_workspace_skills, skill, "scripts", "generate_report_card.py")))
        for dest_root in destinations:
            targets.append((f"{os.path.basename(dest_root)}/{skill}", os.path.join(dest_root, skill, "scripts", "generate_report_card.py")))

    drifted = 0
    for label, path in targets:
        if not os.path.exists(path):
            print(f"[MISS] {label}: 副本不存在 -> {path}")
            drifted += 1
        elif _md5(path) != master_md5:
            print(f"[DRIFT] {label}: 与母本不一致 -> {path}")
            drifted += 1
        else:
            print(f"[OK] {label}: 一致")

    if drifted:
        print(f"\n[FAIL] {drifted} 处副本漂移或缺失。请修改后重新运行: python3 scripts/install_skills.py")
        return 1
    print("\n[SUCCESS] 所有副本与母本一致。")
    return 0


if __name__ == "__main__":
    install_skills(check_only="--check" in sys.argv)
