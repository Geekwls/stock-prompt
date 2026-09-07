#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股量化战报长图渲染引擎 (stock-prompt Ultra-Clean Report Card Generator)
极简高定金融研报风 (Clean Institutional Aesthetic)
去繁就简：去除多层嵌套框与斑马纹，采用彭博/高盛研报式排版、呼吸感留白与高辨识度数据网格。
"""

import json
import os
import sys
import argparse
from datetime import datetime
from pathlib import Path

# 自举：允许从任意目录以文件方式加载（skill 捆绑副本 / 测试加载器）时解析同目录包
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from report_card.validation import REQUIRED_FIELDS, validate_report_data
from report_card.prediction import render_report_card
from report_card.daily import render_daily_review_card
from report_card.rotation import render_sector_rotation_card
from report_card.stock import render_stock_analysis_card

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="生成 A 股全量极简量化战报长图")
    parser.add_argument("--demo", action="store_true", help="生成全量示例长图")
    parser.add_argument("--type", type=str, default="prediction", choices=["prediction", "rotation", "daily", "stock"], help="卡片类型 (prediction/rotation/daily/stock)")
    parser.add_argument("--theme", type=str, default="light", choices=["light", "dark"], help="卡片主题 (默认浅色 light)")
    parser.add_argument("--json", type=str, help="传入 JSON 结果数据文件路径")
    parser.add_argument("--output", type=str, help="输出图片路径")
    args = parser.parse_args()

    out_file = args.output
    if not out_file:
        if args.demo:
            if args.type == "rotation":
                out_file = "demo_sector_rotation_card.png"
            elif args.type == "daily":
                out_file = "demo_daily_review_card.png"
            elif args.type == "stock":
                out_file = "demo_stock_analysis_card.png"
            else:
                out_file = "demo_report_card.png"
        else:
            # 正式报告默认文件名带日期，避免覆盖历史战报
            out_file = f"report_{args.type}_{datetime.now().strftime('%Y%m%d')}.png"

    data = None
    if args.json and not args.demo:
        with open(args.json, "r", encoding="utf-8") as f:
            data = json.load(f)
        try:
            validate_report_data(args.type, data)
        except ValueError as exc:
            parser.error(str(exc))
    elif not args.demo:
        parser.error("正式报告必须传入 --json；如需内置示例数据，请显式使用 --demo")

    if args.type == "rotation":
        render_sector_rotation_card(data=data, output_path=out_file, theme=args.theme)
    elif args.type == "daily":
        render_daily_review_card(data=data, output_path=out_file, theme=args.theme)
    elif args.type == "stock":
        render_stock_analysis_card(data=data, output_path=out_file, theme=args.theme)
    else:
        render_report_card(data=data, output_path=out_file, theme=args.theme)
