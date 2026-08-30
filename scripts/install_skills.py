#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一键安装/同步 stock-prompt 核心技能到 Antigravity 全局与工作区环境
"""

import os
import sys
import shutil

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def install_skills():
    src_workspace_skills = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".agents", "skills"))
    generator_script = os.path.abspath(os.path.join(os.path.dirname(__file__), "generate_report_card.py"))

    destinations = [
        os.path.expanduser(r"~\.gemini\skills"),
        os.path.expanduser(r"~\.gemini\antigravity\skills"),
    ]

    skill_names = ["daily-review", "market-prediction", "sector-rotation"]

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

if __name__ == "__main__":
    install_skills()
