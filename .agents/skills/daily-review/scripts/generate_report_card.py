#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股量化战报长图渲染引擎 (stock-prompt Ultra-Clean Report Card Generator)
极简高定金融研报风 (Clean Institutional Aesthetic)
去繁就简：去除多层嵌套框与斑马纹，采用彭博/高盛研报式排版、呼吸感留白与高辨识度数据网格。
"""

import os
import sys
import json
import argparse
import re
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

REQUIRED_FIELDS = {
    "prediction": {
        "title", "date", "regime", "sentiment_score", "position",
        "opportunity_score", "top_sector", "evidence", "indices_full",
        "sectors_full", "chain_lines", "seat_lines", "trade_lines",
        "watchlist_full", "eval_summary", "risk_warning",
    },
    "daily": {
        "title", "date", "regime", "sentiment_score", "top_sector",
        "retention", "opportunity_score", "sentiment_breakdown",
        "regime_notes", "sectors_daily", "resonance_cards", "chain_lines",
        "stocks_pool", "opportunity_line", "strategy_line", "scenarios",
        "risk_line",
    },
    "rotation": {
        "title", "date_range", "summary", "volume_5d", "fund_flow",
        "institution_lines", "hotmoney_lines", "sei_breakdown",
        "chain_lines", "sentiment_5d", "zhongjun_anchor",
        "longtou_anchor", "watchlist",
    },
    "stock": {
        "stock_name", "stock_code", "date", "price", "coverage",
        "market_wind", "sector_role", "catalyst_level", "rs_rank",
        "wyckoff_phase", "position_status", "risk_reward_ratio",
        "logic_health", "structure_timing", "company_risk_status", "company_details",
        "confidence_level", "research_status", "core_logic", "market_details", "sector_details",
        "catalyst_details", "rs_details", "wyckoff_details", "position_table",
        "rr_details", "evidence_map", "fusion_scores",
        "trade_strategy", "exit_plan", "falsification_rule",
    },
}


def validate_report_data(report_type, data):
    """正式报告必须提供完整数据；演示默认值仅允许由 --demo 使用。"""
    if not isinstance(data, dict):
        raise ValueError("JSON 顶层必须是对象")
    missing = sorted(
        key for key in REQUIRED_FIELDS[report_type]
        if key not in data or data[key] is None or data[key] == "" or data[key] == []
    )
    if missing:
        raise ValueError(
            "正式报告缺少必要字段: " + ", ".join(missing)
            + "。请补齐真实数据；如需示例图请显式使用 --demo。"
        )

def get_font(size=24, bold=False):
    """跨平台中文字体加载"""
    font_candidates = [
        "C:\\Windows\\Fonts\\msyhbd.ttc" if bold else "C:\\Windows\\Fonts\\msyh.ttc",  # 微软雅黑
        "C:\\Windows\\Fonts\\simhei.ttf",      # 黑体
        "/System/Library/Fonts/PingFang.ttc",  # macOS 苹方
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",  # Linux Noto
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",  # Linux 文泉驿
        "/usr/share/fonts/truetype/arphic/uming.ttc",      # Linux AR PL
    ]
    for p in font_candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()

def draw_pill(draw, text, xy, bg_color="#f1f5f9", text_color="#334155", font=None):
    """绘制极简胶囊标签"""
    if font is None:
        font = get_font(14)
    bbox = font.getbbox(text)
    w = bbox[2] - bbox[0] + 16
    h = bbox[3] - bbox[1] + 8
    x, y = xy
    draw.rounded_rectangle([x, y, x + w, y + h], radius=4, fill=bg_color)
    draw.text((x + 8, y + 2), text, fill=text_color, font=font)
    return w, h


def _score_ratio(value):
    """从 `86/100` 等展示值提取 0-1 比例；非评分文本返回 None。"""
    match = re.search(r"(-?\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)", str(value))
    if not match:
        return None
    numerator, denominator = map(float, match.groups())
    if denominator <= 0:
        return None
    return max(0.0, min(1.0, numerator / denominator))


def draw_score_bar(draw, x, y, width, value, color, track_color):
    """为评分卡增加克制的进度条，强化数字层级。"""
    ratio = _score_ratio(value)
    if ratio is None:
        return
    draw.rounded_rectangle([x, y, x + width, y + 5], radius=2, fill=track_color)
    if ratio > 0:
        draw.rounded_rectangle([x, y, x + max(5, int(width * ratio)), y + 5], radius=2, fill=color)


def draw_metric_cards(draw, metrics, width, y, bg_color, border_color, muted_color, font_label):
    """绘制统一的顶部指标卡，并对 `x/100` 指标自动增加进度条。"""
    gap = 10
    left = 60
    card_width = (width - 120 - gap * (len(metrics) - 1)) // len(metrics)
    for index, (label, value, color) in enumerate(metrics):
        x = left + index * (card_width + gap)
        draw.rounded_rectangle(
            [x, y, x + card_width, y + 90], radius=8,
            fill=bg_color, outline=border_color, width=1,
        )
        draw.text((x + 14, y + 12), label, fill=muted_color, font=font_label)
        # 数值自适应缩放：多卡布局下长值先降字号，避免溢出卡片
        value_text = str(value)
        font_value = get_font(19, bold=True)
        for size in (19, 17, 15, 13):
            font_value = get_font(size, bold=True)
            bbox = font_value.getbbox(value_text)
            if bbox[2] - bbox[0] <= card_width - 24:
                break
        draw.text((x + 14, y + 38), value_text, fill=color, font=font_value)
        draw_score_bar(draw, x + 14, y + 77, card_width - 28, value, color, border_color)


def save_cropped_card(img, output_path, content_bottom, min_height=900):
    """根据实际内容裁切画布，移除固定高度造成的大面积底部空白。"""
    final_height = max(min_height, min(img.height, int(content_bottom)))
    img.crop((0, 0, img.width, final_height)).save(output_path, "PNG")
    return final_height

def render_report_card(data=None, output_path="report_card.png", theme="light"):
    """
    极简高定风【盘前全景推演】长图渲染
    """
    is_light = (theme == "light")

    if is_light:
        BG_PAGE = "#ffffff"
        BG_SECTION = "#fafbfc"
        BORDER_LIGHT = "#eef2f6"
        BORDER_DIVIDER = "#e2e8f0"
        TEXT_MAIN = "#0f172a"
        TEXT_MUTED = "#64748b"
        TEXT_SUB = "#475569"
        PRIMARY = "#1e40af"       # 经典深海军蓝
        COLOR_UP = "#dc2626"      # 红涨
        COLOR_DOWN = "#16a34a"    # 绿跌
        COLOR_WARN = "#d97706"    # 琥珀金
    else:
        BG_PAGE = "#090d16"
        BG_SECTION = "#0f172a"
        BORDER_LIGHT = "#1e293b"
        BORDER_DIVIDER = "#1e293b"
        TEXT_MAIN = "#f8fafc"
        TEXT_MUTED = "#64748b"
        TEXT_SUB = "#94a3b8"
        PRIMARY = "#38bdf8"
        COLOR_UP = "#f43f5e"
        COLOR_DOWN = "#4ade80"
        COLOR_WARN = "#fbbf24"

    W = 1200
    H = 4000
    img = Image.new("RGBA", (W, H), BG_PAGE)
    draw = ImageDraw.Draw(img)

    # 顶部极细装饰线
    draw.rectangle([0, 0, W, 4], fill=PRIMARY)

    font_title = get_font(32, bold=True)
    font_h2 = get_font(20, bold=True)
    font_h3 = get_font(17, bold=True)
    font_body = get_font(16)
    font_small = get_font(15)
    font_micro = get_font(13)

    if data is None:
        data = {}

    title_text = data.get("title", "A股盘前全景研判与概率推演战报")
    date_str = data.get("date", datetime.now().strftime("%Y-%m-%d"))

    # 1. 标题与状态栏
    draw.text((60, 36), title_text, fill=TEXT_MAIN, font=font_title)
    draw_pill(draw, f"DATE: {date_str}", (W - 200, 40), bg_color="#f8fafc" if is_light else "#1e293b", text_color=TEXT_MUTED, font=font_micro)
    draw_pill(draw, "盘前推演 (08:30-09:15)", (W - 400, 40), bg_color="#eff6ff" if is_light else "#0f2347", text_color=PRIMARY, font=font_micro)
    draw.line([(60, 85), (W - 60, 85)], fill=BORDER_DIVIDER, width=1)

    # 2. 5大核心速览卡片（扁平无边框极简风）
    top_metrics = [
        ("Market Regime", data.get("regime", "S3 趋势启动"), PRIMARY),
        ("市场情绪分", f"{data.get('sentiment_score', 78)}/100", COLOR_UP),
        ("建议仓位区间", data.get("position", "6 ～ 8 成"), COLOR_WARN),
        ("综合机会评分", f"{data.get('opportunity_score', 85)}/100", COLOR_UP),
        ("第一核心主线", data.get("top_sector", "半导体/算力 [强化期]"), PRIMARY),
    ]

    draw_metric_cards(draw, top_metrics, W, 105, BG_SECTION, BORDER_LIGHT, TEXT_MUTED, font_micro)

    curr_y = 220

    # 模块辅助函数：极简章节标题
    def draw_section_header(title_text, y):
        draw.rounded_rectangle([60, y - 5, W - 60, y + 31], radius=6, fill=BG_SECTION)
        draw.rectangle([60, y - 5, 65, y + 31], fill=PRIMARY)
        draw.text((78, y), title_text, fill=TEXT_MAIN, font=font_h2)
        draw.line([(60, y + 36), (W - 60, y + 36)], fill=BORDER_DIVIDER, width=1)
        return y + 50

    # 3. 模块 01：4大独立证据簇
    curr_y = draw_section_header("01  4 大独立证据簇与亚太早盘似然反馈 (8:30 黄金窗口)", curr_y)
    ev_col_x = [60, 230, 590, 720, 910]
    ev_headers = ["证据分类", "核心指标实况", "属性", "似然倾斜 L(E|State)", "今日开盘影响映射"]
    for h, x in zip(ev_headers, ev_col_x):
        draw.text((x, curr_y), h, fill=TEXT_MUTED, font=font_micro)
    curr_y += 24
    draw.line([(60, curr_y), (W - 60, curr_y)], fill=BORDER_LIGHT, width=1)
    curr_y += 10

    ev_data = data.get("evidence", [
        ("[1] 全球科技偏好簇", "纳指 +1.4%, SOX +2.1%, 日经 +0.8%, 三星/海力士高开", "【实时数据】", "P(E|Up) > P(E|Down)", "显著提振A股半导体与算力高开情绪"),
        ("[2] 宏观流动性与外汇", "富时A50 +0.65%, 离岸人民币 7.235 (企稳), 逆回购平稳", "【实时数据】", "P(E|Up) > P(E|Side)", "为大盘权重蓝筹提供流动性估值支撑"),
        ("[3] 国内产业政策催化", "国家粮食安全战略深化 + 算力基础设施扶持规划落地", "【部委政策】", "强催化倾斜", "农业与算力细分获明确政策溢价推动"),
        ("[4] A股内生量价结构", "T-1 两市 2.12万亿, 涨跌比 6:4, 连板晋级 61.5%, 炸板 18%", "【昨日收盘】", "P(E|Up) 支撑", "量能充沛，赚钱效应维持在良性主升")
    ])
    for row in ev_data:
        draw.text((ev_col_x[0], curr_y), row[0], fill=TEXT_MAIN, font=font_small)
        draw.text((ev_col_x[1], curr_y), row[1], fill=TEXT_MUTED, font=font_micro)
        draw.text((ev_col_x[2], curr_y), row[2], fill=PRIMARY, font=font_micro)
        draw.text((ev_col_x[3], curr_y), row[3], fill=COLOR_UP, font=font_micro)
        draw.text((ev_col_x[4], curr_y), row[4], fill=TEXT_MAIN, font=font_micro)
        curr_y += 28
        draw.line([(60, curr_y), (W - 60, curr_y)], fill=BORDER_LIGHT, width=1)
        curr_y += 8

    curr_y += 15

    # 4. 模块 02：四大指数三态贝叶斯概率与空间点位
    curr_y = draw_section_header("02  四大指数贝叶斯概率分布与五维空间点位 (Layer 1 市场预测)", curr_y)
    idx_col_x = [60, 170, 260, 325, 390, 460, 545, 630, 715, 800, 885, 965, 1050]
    idx_headers = ["指数", "Regime", "P(涨)", "P(震)", "P(跌)", "强阻R2", "阻力R1", "中枢P", "支撑S1", "强撑S2", "上剩余", "下空间", "空间研判"]
    for h, x in zip(idx_headers, idx_col_x):
        draw.text((x, curr_y), h, fill=TEXT_MUTED, font=font_micro)
    curr_y += 24
    draw.line([(60, curr_y), (W - 60, curr_y)], fill=BORDER_LIGHT, width=1)
    curr_y += 10

    indices = data.get("indices_full", [
        ("上证指数", "S3 启动", "64%", "26%", "10%", "3880", "3850", "3825", "3800", "3770", "+1.4%", "-0.6%", "空间充沛"),
        ("深证成指", "S3 启动", "61%", "27%", "12%", "11250", "11100", "10950", "10820", "10700", "+1.8%", "-1.1%", "良性共振"),
        ("创业板指", "S4 主升", "72%", "20%", "8%", "2380", "2330", "2280", "2245", "2210", "+2.6%", "-1.5%", "主升突破"),
        ("中证1000", "S2 震荡", "52%", "33%", "15%", "6450", "6380", "6320", "6260", "6180", "+0.9%", "-0.9%", "结构分化")
    ])
    for row in indices:
        draw.text((idx_col_x[0], curr_y), row[0], fill=TEXT_MAIN, font=font_small)
        draw.text((idx_col_x[1], curr_y), row[1], fill=PRIMARY, font=font_micro)
        draw.text((idx_col_x[2], curr_y), row[2], fill=COLOR_UP, font=font_small)
        draw.text((idx_col_x[3], curr_y), row[3], fill=COLOR_WARN, font=font_micro)
        draw.text((idx_col_x[4], curr_y), row[4], fill=COLOR_DOWN, font=font_micro)
        draw.text((idx_col_x[5], curr_y), row[5], fill=COLOR_UP, font=font_small)
        draw.text((idx_col_x[6], curr_y), row[6], fill=TEXT_MAIN, font=font_small)
        draw.text((idx_col_x[7], curr_y), row[7], fill=COLOR_WARN, font=font_small)
        draw.text((idx_col_x[8], curr_y), row[8], fill=TEXT_MAIN, font=font_small)
        draw.text((idx_col_x[9], curr_y), row[9], fill=COLOR_DOWN, font=font_small)
        draw.text((idx_col_x[10], curr_y), row[10], fill=COLOR_UP, font=font_micro)
        draw.text((idx_col_x[11], curr_y), row[11], fill=COLOR_DOWN, font=font_micro)
        draw.text((idx_col_x[12], curr_y), row[12], fill=PRIMARY, font=font_micro)
        curr_y += 28
        draw.line([(60, curr_y), (W - 60, curr_y)], fill=BORDER_LIGHT, width=1)
        curr_y += 8

    curr_y += 15

    # 5. 模块 03：核心主线状态机与产业链穿透
    curr_y = draw_section_header("03  核心主线状态机、资金延续评分与机会函数 (Layer 2 机会探测)", curr_y)
    sec_col_x = [60, 200, 310, 400, 500, 585, 685, 825, 975]
    sec_headers = ["主线板块", "状态机", "静态质量", "资金留存", "拥挤度", "Opportunity", "领航龙头", "容量中军", "交易结构建议"]
    for h, x in zip(sec_headers, sec_col_x):
        draw.text((x, curr_y), h, fill=TEXT_MUTED, font=font_micro)
    curr_y += 24
    draw.line([(60, curr_y), (W - 60, curr_y)], fill=BORDER_LIGHT, width=1)
    curr_y += 10

    sectors_full = data.get("sectors_full", [
        ("半导体/算力硬件", "[强化期]", "92/100", "88%", "45 (健康)", "88 分 [极高]", "寒武纪 / 胜宏科技", "中际旭创 / 新易盛", "优先核心中军，等分歧放量承接"),
        ("农业种植/粮食安全", "[启动期]", "84/100", "92%", "22 (极低)", "82 分 [优质]", "万向德农 / 敦煌种业", "隆平高科 / 大北农", "放量突破，关注首板/20cm弹性"),
        ("基础化工/化肥农化", "[补涨期]", "76/100", "72%", "38 (中等)", "73 分 [良好]", "新赛股份 / 华尔泰", "盐湖股份 / 云天化", "逢高减仓高位，切低分歧低吸"),
        ("医药生物/创新药", "[弱化期]", "58/100", "42%", "68 (偏高)", "46 分 [观望]", "汉森制药 (炸板)", "恒瑞医药 / 药明康德", "资金持续流出，降低优先级回避")
    ])
    for row in sectors_full:
        draw.text((sec_col_x[0], curr_y), row[0], fill=TEXT_MAIN, font=font_small)
        draw.text((sec_col_x[1], curr_y), row[1], fill=PRIMARY, font=font_small)
        draw.text((sec_col_x[2], curr_y), row[2], fill=TEXT_MAIN, font=font_small)
        draw.text((sec_col_x[3], curr_y), row[3], fill=COLOR_WARN, font=font_small)
        draw.text((sec_col_x[4], curr_y), row[4], fill=COLOR_DOWN, font=font_micro)
        draw.text((sec_col_x[5], curr_y), row[5], fill=COLOR_UP, font=font_small)
        draw.text((sec_col_x[6], curr_y), row[6], fill=TEXT_MAIN, font=font_micro)
        draw.text((sec_col_x[7], curr_y), row[7], fill=PRIMARY, font=font_micro)
        draw.text((sec_col_x[8], curr_y), row[8], fill=TEXT_MUTED, font=font_micro)
        curr_y += 28
        draw.line([(60, curr_y), (W - 60, curr_y)], fill=BORDER_LIGHT, width=1)
        curr_y += 8

    # 产业链穿透简明条目
    chain_lines = data.get("chain_lines", [
        "• 上游 (材料/设备/EDA): 北方华创、中微公司、雅克科技 -> 资金温和放量布局，机构席位逆势加仓",
        "• 中游 (芯片/PCB/光模块): 中际旭创 (成交280亿)、胜宏科技、新易盛 -> 产业链绝对爆发核心，流动性容量极佳",
        "• 下游 (算力/AI应用): 工业富联、浪潮信息、金山办公 -> 细分扩散良好，跟随中军稳步放量共振"
    ])
    curr_y += 6
    for line in chain_lines:
        draw.text((60, curr_y), line, fill=TEXT_SUB, font=font_micro)
        curr_y += 20
    curr_y += 10

    # 6. 模块 04：筹码体检与交易结构
    curr_y = draw_section_header("04  龙虎榜席位品质、筹码结构体检与实战交易结构设计", curr_y)
    col_w = (W - 120 - 40) // 2

    # 左侧：席位
    draw.text((60, curr_y), "[主力席位动态]", fill=PRIMARY, font=font_h3)
    seat_lines = data.get("seat_lines", [
        "机构加仓: 20只个股上榜，嘉立创(净买2.53亿)、肯特股份(净买6989万)",
        "游资连板: 深中华A(6板获游资接力)、楚天龙(5板)，高标题材情绪穿越",
        "风险预警: 汉森制药炸板后拉萨席位对倒；电子板块高位获利盘部分兑现"
    ])
    for s_i, line in enumerate(seat_lines):
        seat_color = COLOR_UP if ("风险" in line or "预警" in line or "炸板" in line) else TEXT_MAIN
        draw.text((60, curr_y + 24 + s_i * 20), line, fill=seat_color, font=font_micro)

    # 右侧：交易结构
    rx = 60 + col_w + 40
    draw.text((rx, curr_y), "[实战交易结构]", fill=PRIMARY, font=font_h3)
    trade_lines = data.get("trade_lines", [
        "优先标的: 第一主线容量中军 (中际旭创) + 政策低位先锋 (万向德农)",
        "等待条件: 早盘前15分钟分歧释放完毕，分时均线上方放量二次站稳",
        "止损纪律: 上证跌破 S1 (3800) 且30分钟无法收回，坚决执行止损"
    ])
    for t_i, line in enumerate(trade_lines):
        trade_color = COLOR_UP if ("止损" in line or "严禁" in line) else TEXT_MAIN
        draw.text((rx, curr_y + 24 + t_i * 20), line, fill=trade_color, font=font_micro)

    curr_y += 105

    # 7. 模块 05：09:25 集合竞价重点跟踪矩阵
    curr_y = draw_section_header("05  09:25 集合竞价贝叶斯更新 & 重点跟踪矩阵 (Next Day Watchlist)", curr_y)
    wl_col_x = [60, 230, 420, 600, 800, 970]
    wl_headers = ["策略分类", "候选板块", "代表标的", "竞价量能/价格特征", "贝叶斯更新判定", "实战应对策略"]
    for h, x in zip(wl_headers, wl_col_x):
        draw.text((x, curr_y), h, fill=TEXT_MUTED, font=font_micro)
    curr_y += 24
    draw.line([(60, curr_y), (W - 60, curr_y)], fill=BORDER_LIGHT, width=1)
    curr_y += 10

    watchlist_full = data.get("watchlist_full", [
        ("高低切潜力主线", "农业种植 / 化工农化", "万向德农 (600371)", "竞价爆量比 >= 5% 且高开 > 3%", "[强确认做多]", "开盘分歧放量承接时逢低介入"),
        ("产业趋势强化", "半导体 / 算力硬件", "中际旭创 (300308)", "平开或小幅高开, 量能温和换手", "[主升延续]", "回踩分时均线低吸中军"),
        ("老主线止跌观察", "电子元器件 / PCB", "胜宏科技 (300476)", "低开 < -2% 但快速放量翻红", "[分歧转一致]", "观察 30 分钟承接力再定买点"),
        ("高危回避方向", "高位连续加速题材", "汉森制药 (002412)", "竞价大额低开核按钮抛压", "[逻辑证伪退潮]", "坚决回避，逢盘中反抽坚决清仓")
    ])
    for row in watchlist_full:
        draw.text((wl_col_x[0], curr_y), row[0], fill=TEXT_MAIN, font=font_small)
        draw.text((wl_col_x[1], curr_y), row[1], fill=PRIMARY, font=font_small)
        draw.text((wl_col_x[2], curr_y), row[2], fill=COLOR_WARN, font=font_small)
        draw.text((wl_col_x[3], curr_y), row[3], fill=TEXT_MUTED, font=font_micro)
        draw.text((wl_col_x[4], curr_y), row[4], fill=COLOR_UP if "强确认" in row[4] else (COLOR_WARN if "分歧" in row[4] else COLOR_DOWN), font=font_small)
        draw.text((wl_col_x[5], curr_y), row[5], fill=TEXT_MAIN, font=font_micro)
        curr_y += 28
        draw.line([(60, curr_y), (W - 60, curr_y)], fill=BORDER_LIGHT, width=1)
        curr_y += 8

    curr_y += 15

    # 8. 模块 06：模型评估与免责
    curr_y = draw_section_header("06  模型元状态、失效预警与 20 日量化评估闭环", curr_y)
    eval_items_raw = data.get("eval_summary", [
        ("模型置信度", "88 / 100", "完整度极高"),
        ("三态准确率", "76.2%", "基准表现优良"),
        ("Brier Score", "0.138", "校准度佳(<0.15)"),
        ("预测锐度", "0.824", "区分度强"),
        ("主线命中率", "84.0%", "主线捕捉胜率高")
    ])
    eval_items_full = [
        (l, v, sub, COLOR_WARN if "Brier" in l else (COLOR_UP if ("命中" in l or "准确" in l or "锐度" in l) else PRIMARY))
        for l, v, sub in eval_items_raw
    ]
    eval_w = (W - 120 - 40) // 5
    for i, (l, v, sub, c) in enumerate(eval_items_full):
        ex = 60 + i * (eval_w + 10)
        draw.rounded_rectangle([ex, curr_y, ex + eval_w, curr_y + 75], radius=6, fill=BG_SECTION, outline=BORDER_LIGHT, width=1)
        draw.text((ex + 10, curr_y + 8), l, fill=TEXT_MUTED, font=font_micro)
        draw.text((ex + 10, curr_y + 26), v, fill=c, font=get_font(17, bold=True))
        draw.text((ex + 10, curr_y + 48), sub, fill=TEXT_MUTED, font=get_font(11))
        draw_score_bar(draw, ex + 10, curr_y + 66, eval_w - 20, v, c, BORDER_LIGHT)

    curr_y += 95
    draw.text((60, curr_y), data.get("risk_warning", "[失效风险预警] 若早盘 USDCNH 汇率突发急贬 > 200 点 或 领航龙头开盘遭巨额砸盘，即时触发风控防御。"), fill=COLOR_UP, font=font_micro)

    curr_y += 35
    draw.line([(60, curr_y), (W - 60, curr_y)], fill=BORDER_DIVIDER, width=1)
    draw.text((60, curr_y + 12), "stock-prompt 量化研判引擎 | GitHub: Geekwls/stock-prompt", fill=TEXT_MUTED, font=font_micro)
    draw.text((W - 360, curr_y + 12), "免责声明：仅供量化研究参考，不构成任何投资建议", fill=COLOR_UP, font=font_micro)

    final_height = save_cropped_card(img, output_path, curr_y + 58)
    print(f"Clean report card generated: {os.path.abspath(output_path)} ({W}x{final_height})")
    return output_path

def render_daily_review_card(data=None, output_path="daily_review_card.png", theme="light"):
    """
    极简高定风【每日收盘强势板块与产业链复盘】长图渲染
    """
    is_light = (theme == "light")

    if is_light:
        BG_PAGE = "#ffffff"
        BG_SECTION = "#fafbfc"
        BORDER_LIGHT = "#eef2f6"
        BORDER_DIVIDER = "#e2e8f0"
        TEXT_MAIN = "#0f172a"
        TEXT_MUTED = "#64748b"
        TEXT_SUB = "#475569"
        PRIMARY = "#059669"       # 翡翠绿/森林绿
        COLOR_UP = "#dc2626"
        COLOR_DOWN = "#16a34a"
        COLOR_WARN = "#d97706"
    else:
        BG_PAGE = "#090d16"
        BG_SECTION = "#0f172a"
        BORDER_LIGHT = "#1e293b"
        BORDER_DIVIDER = "#1e293b"
        TEXT_MAIN = "#f8fafc"
        TEXT_MUTED = "#64748b"
        TEXT_SUB = "#94a3b8"
        PRIMARY = "#34d399"
        COLOR_UP = "#f43f5e"
        COLOR_DOWN = "#4ade80"
        COLOR_WARN = "#fbbf24"

    W = 1200
    H = 4000
    img = Image.new("RGBA", (W, H), BG_PAGE)
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, W, 4], fill=PRIMARY)

    font_title = get_font(32, bold=True)
    font_h2 = get_font(20, bold=True)
    font_h3 = get_font(17, bold=True)
    font_body = get_font(16)
    font_small = get_font(15)
    font_micro = get_font(13)

    if data is None:
        data = {}

    date_str = data.get("date", datetime.now().strftime("%Y-%m-%d"))

    # 1. 标题
    draw.text((60, 36), data.get("title", "A股每日强势板块与产业链共振复盘"), fill=TEXT_MAIN, font=font_title)
    draw_pill(draw, f"复盘时点: {date_str} 15:00 收盘", (W - 280, 40), bg_color="#f8fafc" if is_light else "#1e293b", text_color=TEXT_MUTED, font=font_micro)
    draw_pill(draw, "收盘全景复盘", (W - 420, 40), bg_color="#ecfdf5" if is_light else "#064e3b", text_color=PRIMARY, font=font_micro)
    draw.line([(60, 85), (W - 60, 85)], fill=BORDER_DIVIDER, width=1)

    # 2. 5大核心速览
    top_metrics = [
        ("Market Regime", data.get("regime", "S3 趋势启动 (过渡)"), PRIMARY),
        ("市场情绪总分", f"{data.get('sentiment_score', 78)}/100", COLOR_UP),
        ("第一核心主线", data.get("top_sector", "半导体/算力 [强化期]"), PRIMARY),
        ("资金延续评分", f"{data.get('retention', 88)}/100", COLOR_WARN),
        ("综合机会评分", f"{data.get('opportunity_score', 86)}/100 [优良]", COLOR_UP),
    ]

    draw_metric_cards(draw, top_metrics, W, 105, BG_SECTION, BORDER_LIGHT, TEXT_MUTED, font_micro)

    curr_y = 220

    def draw_section_header(title_text, y):
        draw.rounded_rectangle([60, y - 5, W - 60, y + 31], radius=6, fill=BG_SECTION)
        draw.rectangle([60, y - 5, 65, y + 31], fill=PRIMARY)
        draw.text((78, y), title_text, fill=TEXT_MAIN, font=font_h2)
        draw.line([(60, y + 36), (W - 60, y + 36)], fill=BORDER_DIVIDER, width=1)
        return y + 50

    # 3. 模块 01：情绪打分与总量环境
    curr_y = draw_section_header("01  市场情绪打分、量能环境与 Market Regime 状态定调", curr_y)
    col_w = (W - 120 - 40) // 2

    # 左侧：打分
    draw.text((60, curr_y), "[情绪指标打分拆解]", fill=PRIMARY, font=font_h3)
    sent_items = data.get("sentiment_breakdown", [
        ("涨跌家数比 (25分)", "上涨 3320 家 / 下跌 1850 家 (涨跌比 6.4:3.6) -> 得分: 18 / 25"),
        ("昨日涨停溢价 (20分)", "昨日涨停个股今日平均红盘率 74.2% -> 得分: 20 / 20"),
        ("连板晋级率 (20分)", "首板进二板晋级率 61.54% (接力健康) -> 得分: 20 / 20"),
        ("炸板率得分 (20分)", "全市场涨停 77 家，炸板 17 家 (炸板率 18.0%) -> 得分: 12 / 20"),
        ("两市总成交量 (15分)", "全天 2.12 万亿，较 5 日均量放量 +14.8% -> 得分: 8 / 15")
    ])
    for s_i, (t, d) in enumerate(sent_items):
        sy = curr_y + 24 + s_i * 20
        draw.text((60, sy), f"• {t}: {d}", fill=TEXT_SUB, font=font_micro)

    # 右侧：Regime 定调
    rx = 60 + col_w + 40
    draw.text((rx, curr_y), "[总量环境与 Regime 定调]", fill=PRIMARY, font=font_h3)
    regime_details = data.get("regime_notes", [
        ("Market Regime", "处于 S2 存量震荡 向 S3 趋势启动 过渡态"),
        ("两市量价健康度", "成交额突破 2.1 万亿，属于放量良性攻坚，无缩量诱多背离"),
        ("主线资金集中度", "前 3 大热点行业成交占比达 24.5%，主力做多合力高度聚焦"),
        ("一日游风险体检", "[低风险] 未触发偷尾盘、无连板等 6 大一日游刹车规则"),
        ("建议仓位导向", "维持 6 ～ 8 成 区间，积极参与核心主线低吸")
    ])
    for r_i, (t, d) in enumerate(regime_details):
        ry = curr_y + 24 + r_i * 20
        draw.text((rx, ry), f"• {t}: {d}", fill=TEXT_SUB, font=font_micro)

    curr_y += 140

    # 4. 模块 02：强势板块定位与留存率
    curr_y = draw_section_header("02  强势板块定位、资金延续评分 (Capital Continuity) 与梯队质量", curr_y)
    sec_col_x = [60, 110, 270, 365, 465, 580, 750, 840, 970]
    sec_headers = ["排名", "板块名称", "涨幅", "涨停家数", "成交占比", "资金延续评分", "驱动等级", "板块定位", "吸血与跷跷板判定"]
    for h, x in zip(sec_headers, sec_col_x):
        draw.text((x, curr_y), h, fill=TEXT_MUTED, font=font_micro)
    curr_y += 24
    draw.line([(60, curr_y), (W - 60, curr_y)], fill=BORDER_LIGHT, width=1)
    curr_y += 10

    sectors_daily = data.get("sectors_daily", [
        ("1", "半导体/算力硬件", "+4.22%", "14 家", "11.5%", "88% [强沉淀锁仓]", "S 级 (行业革命)", "[核心主线]", "强吸血医药生物与新能源"),
        ("2", "农林牧渔/粮食安全", "+3.85%", "8 家", "6.2%", "92% [资金高留存]", "A 级 (国家战略)", "[独立防守]", "与大盘形成良性逆势对冲"),
        ("3", "基础化工/化肥农化", "+2.95%", "6 家", "4.8%", "72% [良性换手]", "B 级 (旺季催化)", "[结构补涨]", "承接高位科技分流溢出资金"),
        ("4", "医药生物/创新药", "-1.40%", "1 家", "3.1%", "42% [大幅流出]", "C 级 (常规轮动)", "[边缘退潮]", "受主线吸血严重失血阴跌")
    ])
    for row in sectors_daily:
        draw.text((sec_col_x[0], curr_y), row[0], fill=PRIMARY, font=font_small)
        draw.text((sec_col_x[1], curr_y), row[1], fill=TEXT_MAIN, font=font_small)
        draw.text((sec_col_x[2], curr_y), row[2], fill=COLOR_UP if "+" in row[2] else COLOR_DOWN, font=font_small)
        draw.text((sec_col_x[3], curr_y), row[3], fill=TEXT_MAIN, font=font_micro)
        draw.text((sec_col_x[4], curr_y), row[4], fill=PRIMARY, font=font_micro)
        draw.text((sec_col_x[5], curr_y), row[5], fill=COLOR_WARN, font=font_small)
        draw.text((sec_col_x[6], curr_y), row[6], fill=COLOR_UP, font=font_micro)
        draw.text((sec_col_x[7], curr_y), row[7], fill=COLOR_DOWN if "主线" in row[7] else (COLOR_WARN if "补涨" in row[7] else COLOR_UP), font=font_small)
        draw.text((sec_col_x[8], curr_y), row[8], fill=TEXT_MUTED, font=font_micro)
        curr_y += 28
        draw.line([(60, curr_y), (W - 60, curr_y)], fill=BORDER_LIGHT, width=1)
        curr_y += 8

    curr_y += 15

    # 5. 模块 03：产业链共振质量与穿透
    curr_y = draw_section_header("03  产业链深度共振评分 (0-100) 与上中下游全景穿透", curr_y)
    res_items = data.get("resonance_cards", [
        ("细分上涨占比", "23 / 25 分", "92% 细分板块飘红"),
        ("细分涨停广度", "32 / 35 分", "上中下游皆有涨停封板"),
        ("放量扩散度", "22 / 25 分", "各环节成交量同步放大"),
        ("共振质量总分", "92 / 100 分", "【强产业链深度共振】")
    ])
    res_w = (W - 120 - 30) // 4
    for r_i, (l, v, sub) in enumerate(res_items):
        card_color = COLOR_WARN if ("滞涨" in sub or "缩量" in sub or "单点" in sub) else (PRIMARY if "扩散" in l else COLOR_UP)
        rx_pos = 60 + r_i * (res_w + 10)
        draw.rounded_rectangle([rx_pos, curr_y, rx_pos + res_w, curr_y + 75], radius=6, fill=BG_SECTION, outline=BORDER_LIGHT, width=1)
        draw.text((rx_pos + 10, curr_y + 8), l, fill=TEXT_MUTED, font=font_micro)
        draw.text((rx_pos + 10, curr_y + 26), v, fill=card_color, font=get_font(17, bold=True))
        draw.text((rx_pos + 10, curr_y + 48), sub, fill=TEXT_MAIN, font=get_font(11))
        draw_score_bar(draw, rx_pos + 10, curr_y + 66, res_w - 20, v, card_color, BORDER_LIGHT)

    curr_y += 90
    chain_lines = data.get("chain_lines", [
        "• 上游 (材料/EDA/设备): 北方华创、中微公司、雅克科技 -> 资金温和放量布局，机构席位逆势净加仓",
        "• 中游 (芯片/PCB/光模块): 中际旭创 (成交280亿)、胜宏科技、新易盛 -> 产业链爆发核心，资金延续评分 88，机构锁仓",
        "• 下游 (算力/AI应用): 工业富联、浪潮信息、金山办公 -> 细分扩散良好，跟随中军放量共振，无单点一日游衰竭迹象"
    ])
    for line in chain_lines:
        draw.text((60, curr_y), line, fill=TEXT_SUB, font=font_micro)
        curr_y += 20
    curr_y += 10

    # 6. 模块 04：股池与席位交易结构
    curr_y = draw_section_header("04  龙虎榜席位品质、筹码结构体检与核心股池交易结构", curr_y)
    stock_col_x = [60, 200, 370, 500, 680, 910]
    stock_headers = ["角色定位", "标的代码/名称", "涨跌幅", "筹码结构/换手特征", "龙虎榜席位品质", "交易结构建议"]
    for h, x in zip(stock_headers, stock_col_x):
        draw.text((x, curr_y), h, fill=TEXT_MUTED, font=font_micro)
    curr_y += 24
    draw.line([(60, curr_y), (W - 60, curr_y)], fill=BORDER_LIGHT, width=1)
    curr_y += 10

    stocks_data = data.get("stocks_pool", [
        ("领航龙头", "寒武纪 (688256)", "+12.45%", "充分换手板，放量突破前期平台", "知名游资席位锁仓加持", "【优先】观察龙头封单，做先锋确认"),
        ("容量中军", "中际旭创 (300308)", "+8.65%", "全天成交280亿，机构锁仓良好", "机构净买入 2.53 亿元", "【等待】早盘分歧均线放量承接时低吸"),
        ("低位弹性", "胜宏科技 (300476)", "+15.20%", "20cm 放量突破，细分扩散弹性", "量化与机构混合合力", "【等待】逢回踩均线分歧低吸弹性先锋"),
        ("防守中军", "万向德农 (600371)", "+10.02%", "8天5板强势涨停，筹码高锁仓", "游资合力坚决封死涨停", "【避免】一致性大幅高开盲目无脑追涨")
    ])
    for row in stocks_data:
        draw.text((stock_col_x[0], curr_y), row[0], fill=PRIMARY, font=font_small)
        draw.text((stock_col_x[1], curr_y), row[1], fill=COLOR_WARN, font=font_small)
        draw.text((stock_col_x[2], curr_y), row[2], fill=COLOR_UP if "+" in row[2] else COLOR_DOWN, font=font_small)
        draw.text((stock_col_x[3], curr_y), row[3], fill=TEXT_MAIN, font=font_micro)
        draw.text((stock_col_x[4], curr_y), row[4], fill=COLOR_DOWN, font=font_micro)
        draw.text((stock_col_x[5], curr_y), row[5], fill=COLOR_UP if "优先" in row[5] else (PRIMARY if "等待" in row[5] else COLOR_WARN), font=font_small)
        curr_y += 28
        draw.line([(60, curr_y), (W - 60, curr_y)], fill=BORDER_LIGHT, width=1)
        curr_y += 8

    curr_y += 15

    # 7. 模块 05：机会评分与三大情景
    curr_y = draw_section_header("05  综合机会评分仪表盘 (Opportunity) 与次日推演三大情景", curr_y)
    draw.text((60, curr_y), data.get("opportunity_line", "[机会定调] Opportunity Score: 86 / 100 分  |  生命周期: [强化期]  |  建议仓位: 6 ～ 8 成"), fill=TEXT_MAIN, font=font_h3)
    curr_y += 28
    draw.text((60, curr_y), data.get("strategy_line", "[核心策略] 主线资金延续评分较高，次日只观察核心中军的分歧承接，避免追高。"), fill=TEXT_SUB, font=font_small)
    curr_y += 32

    scenarios = data.get("scenarios", [
        ("[情景 A] 强势主升延续", "触发条件: 领航龙头竞价高开 > 3% 且 30 分钟内放量封板 -> 积极持股做多核心中军"),
        ("[情景 B] 分歧转一致低吸", "触发条件: 早盘微幅低开回踩 MA5 均线获大单放量承接 -> 于分时均线附近分批逢低介入中军"),
        ("[情景 C] 退潮冲高回落防守", "触发条件: 板块放量但后排大面积炸板，中军遭大额卖单砸盘 -> 坚决逢高减仓，严禁逆势补仓")
    ])
    for sc_title, sc_desc in scenarios:
        sc_color = COLOR_UP if "延续" in sc_title else (PRIMARY if ("低吸" in sc_title or "分歧" in sc_title) else COLOR_DOWN)
        draw.text((60, curr_y), sc_title, fill=sc_color, font=font_small)
        draw.text((260, curr_y), sc_desc, fill=TEXT_MAIN, font=font_micro)
        curr_y += 24

    curr_y += 8
    draw.text((60, curr_y), data.get("risk_line", "[风控底线] 单票止损位严格锚定 MA5 均线或 -5%，严禁在一致性高潮日追涨跟风杂毛。"), fill=COLOR_UP, font=font_micro)

    curr_y += 35
    draw.line([(60, curr_y), (W - 60, curr_y)], fill=BORDER_DIVIDER, width=1)
    draw.text((60, curr_y + 12), "stock-prompt 每日产业链复盘引擎 | GitHub: Geekwls/stock-prompt", fill=TEXT_MUTED, font=font_micro)
    draw.text((W - 360, curr_y + 12), "免责声明：仅供量化研究参考，不构成任何投资建议", fill=COLOR_UP, font=font_micro)

    final_height = save_cropped_card(img, output_path, curr_y + 58)
    print(f"Clean daily review report card generated: {os.path.abspath(output_path)} ({W}x{final_height})")
    return output_path

def render_sector_rotation_card(data=None, output_path="sector_rotation_card.png", theme="light"):
    """
    极简高定风【5日板块轮动深度复盘】长图渲染
    """
    is_light = (theme == "light")

    if is_light:
        BG_PAGE = "#ffffff"
        BG_SECTION = "#fafbfc"
        BORDER_LIGHT = "#eef2f6"
        BORDER_DIVIDER = "#e2e8f0"
        TEXT_MAIN = "#0f172a"
        TEXT_MUTED = "#64748b"
        TEXT_SUB = "#475569"
        PRIMARY = "#0284c7"       # 天空天青蓝
        COLOR_UP = "#dc2626"
        COLOR_DOWN = "#16a34a"
        COLOR_WARN = "#d97706"
    else:
        BG_PAGE = "#090d16"
        BG_SECTION = "#0f172a"
        BORDER_LIGHT = "#1e293b"
        BORDER_DIVIDER = "#1e293b"
        TEXT_MAIN = "#f8fafc"
        TEXT_MUTED = "#64748b"
        TEXT_SUB = "#94a3b8"
        PRIMARY = "#38bdf8"
        COLOR_UP = "#f43f5e"
        COLOR_DOWN = "#4ade80"
        COLOR_WARN = "#fbbf24"

    W = 1200
    H = 4000
    img = Image.new("RGBA", (W, H), BG_PAGE)
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, W, 4], fill=PRIMARY)

    font_title = get_font(32, bold=True)
    font_h2 = get_font(20, bold=True)
    font_h3 = get_font(17, bold=True)
    font_body = get_font(16)
    font_small = get_font(15)
    font_micro = get_font(13)

    if data is None:
        data = {}

    # 1. 标题
    draw.text((60, 36), data.get("title", "A股近 5 日板块轮动与节奏深度复盘"), fill=TEXT_MAIN, font=font_title)
    draw_pill(draw, f"分析区间: {data.get('date_range', '8月24日(T-4) ~ 8月28日(T日)')}", (W - 350, 40), bg_color="#f8fafc" if is_light else "#1e293b", text_color=TEXT_MUTED, font=font_micro)
    draw_pill(draw, "中期轮动推演", (W - 470, 40), bg_color="#f0f9ff" if is_light else "#082f49", text_color=PRIMARY, font=font_micro)
    draw.line([(60, 85), (W - 60, 85)], fill=BORDER_DIVIDER, width=1)

    # 2. 5大核心速览
    summary_raw = data.get("summary", [
        ("总量环境定性", "【存量轮动】"),
        ("当前轮动状态", "State 2 畏高切低"),
        ("主线衰竭 SEI", "64 / 100 [严重衰竭]"),
        ("收盘情绪温度", "30 / 100 [偏低分化]"),
        ("高低切流向", "农业种植 / 基础化工")
    ])

    def _summary_color(label, val):
        if "SEI" in label:
            return COLOR_UP
        if "总量" in label:
            return COLOR_UP if "增量" in str(val) else COLOR_WARN
        if "轮动状态" in label:
            return PRIMARY if "主升" in str(val) else COLOR_WARN
        if "情绪" in label:
            return COLOR_WARN
        return COLOR_DOWN

    top_metrics = [(l, v, _summary_color(l, v)) for l, v in summary_raw]

    draw_metric_cards(draw, top_metrics, W, 105, BG_SECTION, BORDER_LIGHT, TEXT_MUTED, font_micro)

    curr_y = 220

    def draw_section_header(title_text, y):
        draw.rounded_rectangle([60, y - 5, W - 60, y + 31], radius=6, fill=BG_SECTION)
        draw.rectangle([60, y - 5, 65, y + 31], fill=PRIMARY)
        draw.text((78, y), title_text, fill=TEXT_MAIN, font=font_h2)
        draw.line([(60, y + 36), (W - 60, y + 36)], fill=BORDER_DIVIDER, width=1)
        return y + 50

    # 3. 模块 01：5日量能与资金流向
    curr_y = draw_section_header("01  5 日成交额走势与主力资金行业流向定调", curr_y)
    col_w = (W - 120 - 40) // 2

    # 左侧：5日量能
    draw.text((60, curr_y), "[5日量能走向] 两市成交额及环比", fill=PRIMARY, font=font_h3)
    vol_data = data.get("volume_5d", [
        ("T-4", "8月24日 (周一)", "约 2.01 万亿", "放量 +1282亿", "放量杀跌"),
        ("T-3", "8月25日 (周二)", "约 1.84 万亿", "缩量 -1769亿", "缩量普涨"),
        ("T-2", "8月26日 (周三)", "约 1.82 万亿", "缩量 -231亿", "阶段地量"),
        ("T-1", "8月27日 (周四)", "约 2.13 万亿", "放量 +3172亿", "放量上攻"),
        ("T日", "8月28日 (周五)", "约 2.12 万亿", "缩量 -232亿", "缩量分化")
    ])
    for v_i, r in enumerate(vol_data):
        vy = curr_y + 24 + v_i * 20
        draw.text((60, vy), f"{r[0]} ({r[1]}): {r[2]} | {r[3]} -> {r[4]}", fill=TEXT_SUB, font=font_micro)

    # 右侧：主力流入/流出
    rx = 60 + col_w + 40
    draw.text((rx, curr_y), "[主力资金流向] 净流入/流出 Top3", fill=PRIMARY, font=font_h3)
    in_out_details = data.get("fund_flow", [
        ("[流入 Top1]", "基础化工: T日主力资金净流入居首，化肥农化走强"),
        ("[流入 Top2]", "专用设备: T-3日净流入41.54亿，智能制造底仓"),
        ("[流入 Top3]", "有色金属: T-2日净流入超百亿，大宗商品涨价驱动"),
        ("[流出 Top1]", "电子/半导体: T日净流出居首，科技高潮次日大出逃"),
        ("[流出 Top2]", "电池/新能源: T-3日净流出26.16亿，反弹持续性不足")
    ])
    for io_i, (t, d) in enumerate(in_out_details):
        iy = curr_y + 24 + io_i * 20
        draw.text((rx, iy), f"• {t}: {d}", fill=TEXT_SUB, font=font_micro)

    curr_y += 140

    # 4. 模块 02：主线角逐与跷跷板
    curr_y = draw_section_header("02  主线角逐与资金博弈 (机构趋势 vs 游资连板 & 跷跷板吸血)", curr_y)
    draw.text((60, curr_y), "[机构趋势方向]", fill=PRIMARY, font=font_h3)
    institution_lines = data.get("institution_lines", [
        "农林牧渔(+6.5%)、煤炭(+5.1%)、基础化工(+3.9%) 获主力持续流入",
        "机构席位加仓: 嘉立创(净买2.53亿)、肯特股份(净买6989万)",
        "机构风险预警: 散户接盘：电子板块T-1大幅流入后T日即反手出货"
    ])
    for i_i, line in enumerate(institution_lines):
        inst_color = COLOR_UP if ("风险" in line or "预警" in line or "出货" in line) else TEXT_MAIN
        draw.text((60, curr_y + 24 + i_i * 20), line, fill=inst_color, font=font_micro)

    draw.text((rx, curr_y), "[游资连板穿越与跷跷板]", fill=PRIMARY, font=font_h3)
    hotmoney_lines = data.get("hotmoney_lines", [
        "连板标杆: 深中华A(6连板)、万向德农(8天5板涨停穿越)",
        "风险大面: 汉森制药(6连板炸板跳水，T日再跌 -6.35%)",
        "跷跷板拉锯: 高位科技成长派发流出，资金直接切换至低位农业/化工"
    ])
    for h_i, line in enumerate(hotmoney_lines):
        hot_color = COLOR_UP if ("风险" in line or "大面" in line or "炸板" in line) else (COLOR_WARN if "跷跷板" in line or "切换" in line else TEXT_MAIN)
        draw.text((rx, curr_y + 24 + h_i * 20), line, fill=hot_color, font=font_micro)

    curr_y += 105

    # 5. 模块 03：SEI 衰竭指数与产业链传导
    curr_y = draw_section_header("03  产业链传导与核心主线衰竭指数 (SEI) 深度量化", curr_y)
    sei_items = data.get("sei_breakdown", [
        ("量价背离度得分", "28 / 40 分", "严重放量滞涨 / 阴跌"),
        ("接力与炸板风险", "12 / 30 分", "高位松动 / 龙头断板"),
        ("资金溢出高低切", "24 / 30 分", "主力大幅撤离涌向低位"),
        ("SEI 综合衰竭得分", "64 / 100 分", "【动能严重衰竭 / 高低切】")
    ])
    sei_w = (W - 120 - 30) // 4
    for s_i, (l, v, sub) in enumerate(sei_items):
        sei_color = COLOR_UP if ("衰竭" in sub or "滞涨" in sub or "撤离" in sub or "阴跌" in sub) else COLOR_WARN
        sx = 60 + s_i * (sei_w + 10)
        draw.rounded_rectangle([sx, curr_y, sx + sei_w, curr_y + 75], radius=6, fill=BG_SECTION, outline=BORDER_LIGHT, width=1)
        draw.text((sx + 10, curr_y + 8), l, fill=TEXT_MUTED, font=font_micro)
        draw.text((sx + 10, curr_y + 26), v, fill=sei_color, font=get_font(17, bold=True))
        draw.text((sx + 10, curr_y + 48), sub, fill=TEXT_MAIN, font=get_font(11))
        draw_score_bar(draw, sx + 10, curr_y + 66, sei_w - 20, v, sei_color, BORDER_LIGHT)

    curr_y += 90
    chain_lines = data.get("chain_lines", [
        "• 农业产业链 (强化主线): 化肥/农药 -> 种植业/种业 -> 农产品加工 (高层调研+APEC催化，万向德农涨停)",
        "• 科技硬件链 (脉冲退潮): 材料设备 -> 芯片/PCB/光模块 -> AI算力 (英伟达催化后放量见顶，半导体-2.12% 坚决派发)",
        "• 基础化工链 (低位补涨): 化学原料 -> 精细化学制品 -> 农化制品 (主力T日净流入居首，承接科技流出资金)"
    ])
    for line in chain_lines:
        draw.text((60, curr_y), line, fill=TEXT_SUB, font=font_micro)
        curr_y += 20
    curr_y += 10

    # 6. 模块 04：5日情绪走向与锚点
    curr_y = draw_section_header("04  5 日情绪指标走向与中军/龙头盘前观察锚点", curr_y)
    sent_col_x = [60, 140, 290, 420, 560, 700, 880]
    sent_headers = ["交易日", "日期", "红盘率", "连板晋级率", "炸板率", "市场情绪定性", "情绪得分"]
    for h, x in zip(sent_headers, sent_col_x):
        draw.text((x, curr_y), h, fill=TEXT_MUTED, font=font_micro)
    curr_y += 24
    draw.line([(60, curr_y), (W - 60, curr_y)], fill=BORDER_LIGHT, width=1)
    curr_y += 10

    sent_data = data.get("sentiment_5d", [
        ("T-4", "8月24日 (周一)", "~27% (1460家红)", "36.36%", "26.0%", "冰点杀跌", "24 / 100"),
        ("T-3", "8月25日 (周二)", "~78% (4200家红)", "估算 ~35%", "估算 ~25%", "超跌修复", "68 / 100"),
        ("T-2", "8月26日 (周三)", "~55% (2946家红)", "估算 ~30%", "33.33%", "温和整理", "52 / 100"),
        ("T-1", "8月27日 (周四)", "~63% (3300家红)", "61.54%", "18.0%", "高潮加速", "82 / 100"),
        ("T日", "8月28日 (周五)", "~56% (3000家红)", "估算 ~30%", "估算 ~22%", "分化降温", "30 / 100")
    ])

    def _pct(text):
        num = ""
        for ch in str(text):
            if ch.isdigit() or ch == ".":
                num += ch
            elif num:
                break
        return float(num) if num else None

    for r in sent_data:
        hong, promote, zhaban = _pct(r[2]), _pct(r[3]), _pct(r[4])
        draw.text((sent_col_x[0], curr_y), r[0], fill=PRIMARY, font=font_micro)
        draw.text((sent_col_x[1], curr_y), r[1], fill=TEXT_MAIN, font=font_micro)
        draw.text((sent_col_x[2], curr_y), r[2], fill=COLOR_UP if (hong is not None and hong >= 50) else COLOR_DOWN, font=font_micro)
        draw.text((sent_col_x[3], curr_y), r[3], fill=COLOR_UP if (promote is not None and promote >= 40) else TEXT_MAIN, font=font_micro)
        draw.text((sent_col_x[4], curr_y), r[4], fill=COLOR_UP if (zhaban is not None and zhaban < 25) else COLOR_DOWN, font=font_micro)
        sent_color = COLOR_UP if ("高潮" in r[5] or "修复" in r[5]) else (COLOR_WARN if ("分化" in r[5] or "整理" in r[5] or "降温" in r[5]) else TEXT_MAIN)
        draw.text((sent_col_x[5], curr_y), r[5], fill=sent_color, font=font_micro)
        draw.text((sent_col_x[6], curr_y), r[6], fill=PRIMARY, font=font_micro)
        curr_y += 24
        draw.line([(60, curr_y), (W - 60, curr_y)], fill=BORDER_LIGHT, width=1)
        curr_y += 6

    curr_y += 10
    draw.text((60, curr_y), data.get("zhongjun_anchor", "[中军锚点] 中际旭创(成交280亿) 若竞价低开 > -2%，确认机构继续派发；科技板块短期需坚决回避。"), fill=COLOR_UP, font=font_micro)
    curr_y += 20
    draw.text((60, curr_y), data.get("longtou_anchor", "[龙头锚点] 万向德农(8天5板) 若竞价高开 > 7% 并快速封板，确认农业情绪延续；若高开低走需防补涨熄火。"), fill=PRIMARY, font=font_micro)
    curr_y += 30

    # 7. 模块 05：次日盘前重点跟踪矩阵
    curr_y = draw_section_header("05  次日盘前重点跟踪矩阵与验证坐标 (Next Day Watchlist)", curr_y)
    wl_col_x = [60, 220, 390, 560, 950]
    wl_headers = ["策略分类", "候选板块", "代表标的", "次日 9:25 集合竞价验证关注点", "操作策略导向"]
    for h, x in zip(wl_headers, wl_col_x):
        draw.text((x, curr_y), h, fill=TEXT_MUTED, font=font_micro)
    curr_y += 24
    draw.line([(60, curr_y), (W - 60, curr_y)], fill=BORDER_LIGHT, width=1)
    curr_y += 10

    watchlist_rotation = data.get("watchlist", [
        ("高低切潜力主线", "农业种植 / 种业", "万向德农 (600371)", "竞价爆量比 >= 5% 且高开 > 3%，关注首板与20cm弹性", "确认强承接后分歧低吸"),
        ("低位补涨方向", "基础化工 / 化肥", "新赛股份 (600540)", "观察主力资金是否持续净流入，前排封单是否坚决", "寻找 1 进 2 晋级机会"),
        ("老主线止跌观察", "半导体 / 算力硬件", "中际旭创 (300308)", "观察 MA20 均线支撑能否守住，早盘是否缩量企稳", "观望为主，暂不盲目抄底"),
        ("高危回避方向", "高位连续加速题材", "汉森制药 (002412)", "警惕获利盘竞价核按钮抛压，断板后负反馈扩散", "坚决回避，逢反抽离场")
    ])
    for row in watchlist_rotation:
        draw.text((wl_col_x[0], curr_y), row[0], fill=TEXT_MAIN, font=font_small)
        draw.text((wl_col_x[1], curr_y), row[1], fill=PRIMARY, font=font_small)
        draw.text((wl_col_x[2], curr_y), row[2], fill=COLOR_WARN, font=font_small)
        draw.text((wl_col_x[3], curr_y), row[3], fill=TEXT_MAIN, font=font_micro)
        draw.text((wl_col_x[4], curr_y), row[4], fill=COLOR_UP if "回避" in row[0] else COLOR_DOWN, font=font_small)
        curr_y += 28
        draw.line([(60, curr_y), (W - 60, curr_y)], fill=BORDER_LIGHT, width=1)
        curr_y += 8

    curr_y += 35
    draw.line([(60, curr_y), (W - 60, curr_y)], fill=BORDER_DIVIDER, width=1)
    draw.text((60, curr_y + 12), "stock-prompt 量化研判引擎 | GitHub: Geekwls/stock-prompt", fill=TEXT_MUTED, font=font_micro)
    draw.text((W - 360, curr_y + 12), "免责声明：仅供量化研究参考，不构成任何投资建议", fill=COLOR_UP, font=font_micro)

    final_height = save_cropped_card(img, output_path, curr_y + 58)
    print(f"Clean sector rotation report card generated: {os.path.abspath(output_path)} ({W}x{final_height})")
    return output_path

def render_stock_analysis_card(data=None, output_path="stock_analysis_card.png", theme="light"):
    """
    极简高定风【A股个股完整诊断与威科夫结构研判】长图渲染
    """
    is_light = (theme == "light")

    if is_light:
        BG_PAGE = "#ffffff"
        BG_SECTION = "#fafbfc"
        BORDER_LIGHT = "#eef2f6"
        BORDER_DIVIDER = "#e2e8f0"
        TEXT_MAIN = "#0f172a"
        TEXT_MUTED = "#64748b"
        TEXT_SUB = "#475569"
        PRIMARY = "#4f46e5"       # 经典靛蓝/紫蓝 (Individual Alpha)
        COLOR_UP = "#dc2626"
        COLOR_DOWN = "#16a34a"
        COLOR_WARN = "#d97706"
    else:
        BG_PAGE = "#090d16"
        BG_SECTION = "#0f172a"
        BORDER_LIGHT = "#1e293b"
        BORDER_DIVIDER = "#1e293b"
        TEXT_MAIN = "#f8fafc"
        TEXT_MUTED = "#64748b"
        TEXT_SUB = "#94a3b8"
        PRIMARY = "#818cf8"
        COLOR_UP = "#f43f5e"
        COLOR_DOWN = "#4ade80"
        COLOR_WARN = "#fbbf24"

    W = 1200
    H = 3200
    img = Image.new("RGBA", (W, H), BG_PAGE)
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, W, 4], fill=PRIMARY)

    font_title = get_font(28, bold=True)
    font_h2 = get_font(19, bold=True)
    font_h3 = get_font(16, bold=True)
    font_body = get_font(15)
    font_small = get_font(14)
    font_micro = get_font(12)

    if data is None:
        data = {}

    stock_name = data.get("stock_name", "紫光股份")
    stock_code = data.get("stock_code", "000938")
    date_str = data.get("date", datetime.now().strftime("%Y-%m-%d"))
    price_str = data.get("price", "28.50")
    coverage_str = str(data.get("coverage", "95%"))

    # 1. 标题与状态栏
    title_display = f"{stock_name} ({stock_code}) 个股完整诊断"
    draw.text((60, 36), title_display, fill=TEXT_MAIN, font=font_title)
    draw_pill(draw, f"现价: ¥{price_str}", (W - 190, 40), bg_color="#eef2ff" if is_light else "#1e1b4b", text_color=PRIMARY, font=font_micro)
    draw_pill(draw, f"基准: {date_str}", (W - 350, 40), bg_color="#f8fafc" if is_light else "#1e293b", text_color=TEXT_MUTED, font=font_micro)
    draw_pill(draw, f"Coverage: {coverage_str}", (W - 500, 40), bg_color="#ecfdf5" if is_light else "#064e3b", text_color=COLOR_DOWN, font=font_micro)
    draw.line([(60, 85), (W - 60, 85)], fill=BORDER_DIVIDER, width=1)

    # 2. 8大核心速览卡片
    top_metrics = [
        ("市场大势", data.get("market_wind", "顺风驱动 [顺]"), PRIMARY),
        ("板块主线", data.get("sector_role", "核心主线 [中军]"), COLOR_DOWN),
        ("催化等级", data.get("catalyst_level", "S级 [长周期]"), COLOR_UP),
        ("RS 强度", data.get("rs_rank", "Top 12% [极强]"), COLOR_UP),
        ("威科夫阶段", data.get("wyckoff_phase", "Markup 主升"), PRIMARY),
        ("位置状态", data.get("position_status", "安全支撑区 [优]"), COLOR_DOWN),
        ("公司风险", data.get("company_risk_status", "中性可控"), COLOR_WARN),
        ("赔率空间", data.get("risk_reward_ratio", "3.8 : 1 [优]"), COLOR_WARN),
    ]

    draw_metric_cards(
        draw,
        top_metrics,
        width=W,
        y=105,
        bg_color=BG_SECTION,
        border_color=BORDER_LIGHT,
        muted_color=TEXT_MUTED,
        font_label=font_micro,
    )

    # 核心状态定调横幅
    curr_y = 215
    draw.rounded_rectangle([60, curr_y, W - 60, curr_y + 72], radius=6, fill=BG_SECTION, outline=BORDER_LIGHT, width=1)
    logic_health = data.get("logic_health", "稳定")
    structure_timing = data.get("structure_timing", "等待确认")
    status_tag = data.get("research_status", f"【逻辑健康度：{logic_health}｜结构位置：{structure_timing}】")
    conf_level = str(data.get("confidence_level", "中"))
    core_logic_text = data.get("core_logic", "算力中军放量突破吸筹区间，缩量良性回踩 MA20 支撑，相对强度持续走强，具备非对称赔率空间。")
    draw.text((75, curr_y + 13), f"[双轴诊断] {status_tag}  |  [证据置信度] {conf_level}", fill=PRIMARY, font=font_small)
    draw.text((75, curr_y + 40), f"[核心逻辑] {core_logic_text}", fill=TEXT_SUB, font=font_micro)
    curr_y += 90

    def draw_section_header(title_text, y):
        draw.rectangle([60, y + 2, 64, y + 20], fill=PRIMARY)
        draw.text((74, y), title_text, fill=TEXT_MAIN, font=font_h2)
        draw.line([(60, y + 32), (W - 60, y + 32)], fill=BORDER_DIVIDER, width=1)
        return y + 45

    # 3. 模块 01：市场环境与板块共振
    curr_y = draw_section_header("01  市场环境、板块主线与驱动催化剂 (顺逆风·合力·驱动)", curr_y)
    col_w = (W - 120 - 40) // 2

    # 左侧：市场环境
    draw.text((60, curr_y), f"[市场大盘环境] {data.get('market_wind', 'N/A')}", fill=PRIMARY, font=font_h3)
    market_details = data.get("market_details", [
        ("指数趋势", "上证处于 MA20/MA60 多头排列上方，良性主升"),
        ("量能环境", "两市全天成交 2.12 万亿，增量攻坚资金充沛"),
        ("赚钱效应", "全市场涨跌比 6.4:3.6，连板接力晋级率 61.5%"),
        ("周期定位", "处于 S3 趋势启动向 S4 主升推进过渡态"),
        ("顺逆定调", "大盘为科技成长提供充足流动性与高风险偏好")
    ])
    for m_i, (t, d) in enumerate(market_details):
        my = curr_y + 24 + m_i * 20
        draw.text((60, my), f"• {t}: {d}", fill=TEXT_SUB, font=font_micro)

    # 右侧：板块共振
    rx = 60 + col_w + 40
    draw.text((rx, curr_y), f"[板块主线共振] {data.get('sector_role', 'N/A')}", fill=PRIMARY, font=font_h3)
    sector_details = data.get("sector_details", [
        ("所属行业", "通信设备 / ICT 算力设备与交换机龙头"),
        ("核心概念", "算力基础设施、AI 服务器、CPO 光通信"),
        ("板块强度", "近 5 日板块上涨 +4.22%，全市场行业排名 Top 5%"),
        ("生命周期", "处于 [强化期]，资金延续性 88 分 机构持续锁仓"),
        ("个股角色", "容量中军标的，与板块强共振，抗风险能力突出")
    ])
    for s_i, (t, d) in enumerate(sector_details):
        sy = curr_y + 24 + s_i * 20
        draw.text((rx, sy), f"• {t}: {d}", fill=TEXT_SUB, font=font_micro)

    # 驱动催化剂（全宽区块）
    catalyst_details = data.get("catalyst_details", [
        ("驱动类型", "产业趋势 + 政策驱动"),
        ("驱动等级", "S级 (国家算力战略，持续数周至数月)"),
        ("时效状态", "发酵中 (订单与业绩持续验证)"),
        ("交叉验证", "催化 + 量价共振，真主线特征"),
        ("证伪信号", "北美云厂商资本开支下修"),
    ]) or []
    if catalyst_details:
        cat_y = curr_y + 128
        draw.text((60, cat_y), "[驱动催化剂等级] 催化-量价交叉验证与时效状态", fill=PRIMARY, font=font_h3)
        for c_i, item in enumerate(catalyst_details):
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                draw.text((60, cat_y + 22 + c_i * 18), f"• {item[0]}: {item[1]}", fill=TEXT_SUB, font=font_micro)
        curr_y = cat_y + 22 + len(catalyst_details) * 18 + 16
    else:
        curr_y += 140

    # 公司质量与事件风险
    curr_y = draw_section_header("02  公司质量与事件风险 (财务·估值·治理·重大事项)", curr_y)
    company_details = data.get("company_details", [
        ("盈利质量", "N/A：待补最新定期报告及同比、环比口径"),
        ("现金流", "N/A：待核验经营现金流与净利润匹配度"),
        ("资产负债", "N/A：待核验应收、存货、商誉与有息负债"),
        ("估值位置", "N/A：待补历史与行业可比估值分位"),
        ("治理事件", "N/A：待检查减持、解禁、质押、问询与诉讼"),
    ])
    draw.text((60, curr_y), f"[公司风险定调] {data.get('company_risk_status', '暂不评级')}", fill=COLOR_WARN, font=font_h3)
    for c_i, item in enumerate(company_details):
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            draw.text((60, curr_y + 24 + c_i * 20), f"• {item[0]}: {item[1]}", fill=TEXT_SUB, font=font_micro)
    curr_y += 24 + len(company_details) * 20 + 20

    # 4. 模块 03：相对强度 (RS) 与动量引擎
    curr_y = draw_section_header("03  相对强度 (RS Engine) 与动量加速度深度量化", curr_y)
    rs_items = [
        ("RS 5D 超额", data.get("rs_5d", "N/A"), data.get("rs_5d_note", "缺少同期基准"), COLOR_WARN),
        ("RS 20D 超额", data.get("rs_20d", "N/A"), data.get("rs_20d_note", "缺少同期基准"), COLOR_WARN),
        ("全市场 RS 分位", data.get("rs_percentile", "N/A"), data.get("rs_percentile_note", "缺少横截面股票池"), PRIMARY),
        ("RS 加速度", data.get("rs_acc", "N/A"), data.get("rs_acc_note", "缺少完整历史行情"), COLOR_WARN)
    ]
    rs_w = (W - 120 - 30) // 4
    for r_i, (l, v, sub, c) in enumerate(rs_items):
        rx_pos = 60 + r_i * (rs_w + 10)
        draw.rounded_rectangle([rx_pos, curr_y, rx_pos + rs_w, curr_y + 65], radius=4, fill=BG_SECTION, outline=BORDER_LIGHT, width=1)
        draw.text((rx_pos + 10, curr_y + 8), l, fill=TEXT_MUTED, font=font_micro)
        draw.text((rx_pos + 10, curr_y + 26), v, fill=c, font=get_font(17, bold=True))
        draw.text((rx_pos + 10, curr_y + 48), sub, fill=TEXT_MAIN, font=get_font(11))

    curr_y += 80
    rs_narrative = data.get("rs_details", "【动量解读】过去 20 个交易日持续跑赢指数，近 5 日 RS 斜率进一步加速陡峭化，表明该股并非单纯依赖前期涨幅维持排名，而是有主力增量资金在持续主动建仓做多。")
    draw.text((60, curr_y), rs_narrative, fill=TEXT_SUB, font=font_micro)
    curr_y += 30

    # 5. 模块 03：量价行为与威科夫结构
    curr_y = draw_section_header("04  量价行为与威科夫结构深度解析 (Wyckoff & VSA 供求机制)", curr_y)
    wyckoff = data.get("wyckoff_details", {}) or {}
    phase = wyckoff.get("phase", "Markup 主升推进阶段 (突破蓄势中继)")
    events = wyckoff.get("events", "前期完成 Spring (Confirmed) 与 Test (Confirmed)，随后放量大阳线打出 SOS (Confirmed)")
    vsa = wyckoff.get("vsa", "突破阻力位时成交量显著放大(努力有结果)，随后回踩 MA20 极度缩量(供应枯竭，浮筹锁定)")
    narrative = wyckoff.get("narrative", "当前结构属于标准的突破后 LPS (Confirmed) 良性回踩蓄势，未见 UT 假突破或派发迹象")
    draw.text((60, curr_y), f"[宏观结构阶段] {phase}", fill=PRIMARY, font=font_h3)
    draw.text((60, curr_y + 24), f"• 关键事件识别 (证据等级): {events}", fill=TEXT_MAIN, font=font_micro)
    draw.text((60, curr_y + 44), f"• 努力与结果 (VSA): {vsa}", fill=TEXT_MAIN, font=font_micro)
    draw.text((60, curr_y + 64), f"• 市场行为叙事: {narrative}", fill=COLOR_DOWN, font=font_micro)

    curr_y += 100

    # 6. 模块 04：价格位置与过热惩罚体检
    curr_y = draw_section_header("05  价格位置与动态过热惩罚体检 (Position & Dynamic Overheat)", curr_y)
    pos_col_x = [60, 240, 420, 600, 800, 970]
    pos_headers = ["评估指标", "实际数值", "安全/过热阈值", "状态定性", "过热惩罚判定", "跟踪指引建议"]
    for h, x in zip(pos_headers, pos_col_x):
        draw.text((x, curr_y), h, fill=TEXT_MUTED, font=font_micro)
    curr_y += 24
    draw.line([(60, curr_y), (W - 60, curr_y)], fill=BORDER_LIGHT, width=1)
    curr_y += 10

    position_table = data.get("position_table", [
        ("MA20 偏离度 (Bias)", "+4.2%", "< 15.0%", "[正常支撑区]", "未触发过热惩罚", "均线支撑强劲，适合跟踪"),
        ("MA50 偏离度 (Bias)", "+11.8%", "< 25.0%", "[稳健推进]", "未触发过热惩罚", "中期趋势健康"),
        ("近 5 日累计涨幅", "+6.5%", "< 20.0%", "[温和换手]", "未触发过热惩罚", "无高位加速风险"),
        ("距前高 / POC 距离", "-18.5%", "空间充沛", "[阻力较远]", "上方空间广阔", "具备较高潜在上升弹性")
    ])
    for row in position_table:
        draw.text((pos_col_x[0], curr_y), row[0], fill=TEXT_MAIN, font=font_small)
        draw.text((pos_col_x[1], curr_y), row[1], fill=COLOR_UP if "+" in row[1] else COLOR_DOWN, font=font_small)
        draw.text((pos_col_x[2], curr_y), row[2], fill=TEXT_MUTED, font=font_micro)
        draw.text((pos_col_x[3], curr_y), row[3], fill=COLOR_DOWN, font=font_small)
        draw.text((pos_col_x[4], curr_y), row[4], fill=PRIMARY, font=font_micro)
        draw.text((pos_col_x[5], curr_y), row[5], fill=TEXT_MAIN, font=font_micro)
        curr_y += 28
        draw.line([(60, curr_y), (W - 60, curr_y)], fill=BORDER_LIGHT, width=1)
        curr_y += 8

    curr_y += 15

    # 7. 模块 05：风险收益结构与赔率测算
    curr_y = draw_section_header("06  风险收益结构与空间不对称性测算 (Risk / Reward & Asymmetry)", curr_y)
    rr_col_x = [60, 240, 420, 600, 800, 970]
    rr_headers = ["结构确认位", "假设失效位", "潜在上升空间", "潜在下行风险", "赔率 (R / R)", "盈亏比定性"]
    for h, x in zip(rr_headers, rr_col_x):
        draw.text((x, curr_y), h, fill=TEXT_MUTED, font=font_micro)
    curr_y += 24
    draw.line([(60, curr_y), (W - 60, curr_y)], fill=BORDER_LIGHT, width=1)
    curr_y += 10

    rr_data = data.get("rr_details", [
        ("29.20 元 (突破站稳)", "27.10 元 (MA20破位)", "+18.5% (目标33.8元)", "-4.9% (止损空间)", "3.78 : 1", "[极佳赔率区间]")
    ])
    for row in rr_data:
        draw.text((rr_col_x[0], curr_y), row[0], fill=COLOR_WARN, font=font_small)
        draw.text((rr_col_x[1], curr_y), row[1], fill=COLOR_DOWN, font=font_small)
        draw.text((rr_col_x[2], curr_y), row[2], fill=COLOR_UP, font=font_small)
        draw.text((rr_col_x[3], curr_y), row[3], fill=COLOR_DOWN, font=font_small)
        draw.text((rr_col_x[4], curr_y), row[4], fill=PRIMARY, font=font_small)
        draw.text((rr_col_x[5], curr_y), row[5], fill=COLOR_DOWN, font=font_small)
        curr_y += 28
        draw.line([(60, curr_y), (W - 60, curr_y)], fill=BORDER_LIGHT, width=1)
        curr_y += 8

    # 情景置信度评估
    conf_level = str(data.get("confidence_level", "中"))
    draw.text((60, curr_y + 6), f"[证据置信度] {conf_level}   (仅描述数据质量与可验证程度，不代表方向或上涨概率)", fill=COLOR_DOWN if conf_level == "高" else COLOR_WARN, font=font_small)
    curr_y += 32

    curr_y += 15

    # 8. 模块 07：8层证据采集与融合裁决
    curr_y = draw_section_header("07  8层证据采集与融合裁决 (8-Layer Decision & Tiered Exit)", curr_y)

    # 左右两栏布局：左侧加权融合评分表，右侧全景证据看板
    fusion_scores = data.get("fusion_scores", [
        ["L1 市场环境", "10%", "B (70–84)", "7.0–8.4"],
        ["L2 板块主线", "12%", "B (70–84)", "8.4–10.1"],
        ["L3 催化剂质量", "10%", "B (70–84)", "7.0–8.4"],
        ["L4 RS 强度", "10%", "B (70–84)", "7.0–8.4"],
        ["L5 威科夫量价", "18%", "C (55–69)", "9.9–12.4"],
        ["L6 位置过热", "10%", "B (70–84)", "7.0–8.4"],
        ["L7 赔率空间", "10%", "C (55–69)", "5.5–6.9"],
        ["L8 公司质量", "20%", "C (55–69)", "11.0–13.8"],
        ["加权融合总分", "100%", "区间评级", "62.8–76.8"]
    ])
    evidence_map = data.get("evidence_map", [
        ["市场环境", "顺风共振 [顺]"],
        ["板块主线", "核心主线 [中军]"],
        ["催化剂驱动", "S级发酵中 [强]"],
        ["相对强度", "极强 Top 12% [强]"],
        ["威科夫阶段", "Markup 主升推进"],
        ["量价特征", "供需健康 [健康]"],
        ["位置与过热", "安全支撑位 [优]"],
        ["赔率评估", "高赔率 >=3:1 [优]"],
        ["公司质量", "中性可控 [待跟踪]"]
    ])

    col_w = (W - 120 - 40) // 2

    # 左侧：8层加权融合评分表
    draw.text((60, curr_y), "[8 层加权融合评分] (A–E 区间 / 缺失=N/A)", fill=PRIMARY, font=font_h3)
    fu_y = curr_y + 22
    fu_col_x = [60, 200, 310, 440]
    for h, x in zip(["研判层级", "权重", "得分(定性)", "加权分"], fu_col_x):
        draw.text((x, fu_y), h, fill=TEXT_MUTED, font=font_micro)
    fu_y += 18
    for row in fusion_scores:
        if isinstance(row, (list, tuple)) and len(row) >= 4:
            is_total = "总分" in str(row[0])
            row_label_color = PRIMARY if is_total else TEXT_MAIN
            draw.text((fu_col_x[0], fu_y), str(row[0]), fill=row_label_color, font=font_micro)
            draw.text((fu_col_x[1], fu_y), str(row[1]), fill=TEXT_MUTED, font=font_micro)
            draw.text((fu_col_x[2], fu_y), str(row[2]), fill=TEXT_SUB, font=font_micro)
            draw.text((fu_col_x[3], fu_y), str(row[3]), fill=PRIMARY if is_total else TEXT_MAIN, font=font_micro)
        fu_y += 18

    # 右侧：8 维全景证据看板
    rx = 60 + col_w + 40
    draw.text((rx, curr_y), "[8 维全景证据看板]", fill=PRIMARY, font=font_h3)
    ev_y = curr_y + 22
    for ev in evidence_map:
        if isinstance(ev, (list, tuple)) and len(ev) >= 2:
            draw.text((rx, ev_y), str(ev[0]), fill=TEXT_MUTED, font=font_micro)
            draw.text((rx + 160, ev_y), str(ev[1]), fill=COLOR_DOWN, font=font_micro)
        ev_y += 18

    curr_y = max(fu_y, ev_y) + 15

    # 交易跟踪执行条件
    trade = data.get("trade_strategy", {
        "priority": "观察结构支撑区的量价反馈",
        "trigger": "收盘或约定周期有效站稳关键确认位，并出现量价匹配",
        "avoid": "证据未确认或流动性受限时扩大风险暴露"
    })
    priority = trade.get("priority", "观察结构支撑区的量价反馈")
    trigger = trade.get("trigger", "收盘或约定周期有效站稳关键确认位，并出现量价匹配")
    avoid = trade.get("avoid", "证据未确认或流动性受限时扩大风险暴露")
    draw.text((60, curr_y), f"[执行条件] 【优先观察】{priority}", fill=PRIMARY, font=font_small)
    curr_y += 24
    draw.text((60, curr_y), f"[确认触发] {trigger}", fill=TEXT_MAIN, font=font_small)
    curr_y += 24
    draw.text((60, curr_y), f"[规避动作] {avoid}", fill=COLOR_WARN, font=font_small)
    curr_y += 28

    # 分级退出纪律（预警/失效/时间止损/浮盈保护）
    exit_plan = data.get("exit_plan", {
        "warning": "量价效率下降或竞争假设证据增强",
        "invalidation": "有效跌破关键结构位并反抽失败",
        "time_stop": "在预设结构观察窗口内未出现确认信号则降级",
        "profit_protection": "按新结构上移研究失效位，不保证实际成交无损"
    })
    if exit_plan:
        draw.text((60, curr_y), "[分级退出纪律]", fill=PRIMARY, font=font_h3)
        curr_y += 22
        for label, key, color in [
            ("预警观察位(风险削减1/3~1/2)", "warning", COLOR_WARN),
            ("假设失效位(退出跟踪)", "invalidation", COLOR_UP),
            ("时间退出窗口(未推进即退出)", "time_stop", TEXT_MAIN),
            ("浮盈保护(+1R上移止损)", "profit_protection", TEXT_MAIN),
        ]:
            if exit_plan.get(key):
                draw.text((60, curr_y), f"• {label}: {exit_plan[key]}", fill=color, font=font_micro)
                curr_y += 18
        curr_y += 10

    draw.text((60, curr_y), data.get("falsification_rule", "[逻辑证伪底线] 若后市价格放量跌破关键失效位 27.10 元，表明威科夫支撑假设失效，必须坚决执行退出。"), fill=COLOR_UP, font=font_small)

    curr_y += 35
    draw.line([(60, curr_y), (W - 60, curr_y)], fill=BORDER_DIVIDER, width=1)
    draw.text((60, curr_y + 12), "stock-prompt A股个股诊断 | GitHub: Geekwls/stock-prompt", fill=TEXT_MUTED, font=font_micro)
    draw.text((W - 360, curr_y + 12), "免责声明：仅供量化研究参考，不构成任何投资建议", fill=COLOR_UP, font=font_micro)

    final_height = save_cropped_card(img, output_path, curr_y + 58)
    print(f"Clean stock analysis report card generated: {os.path.abspath(output_path)} ({W}x{final_height})")
    return output_path

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
        if args.type == "rotation":
            out_file = "demo_sector_rotation_card.png"
        elif args.type == "daily":
            out_file = "demo_daily_review_card.png"
        elif args.type == "stock":
            out_file = "demo_stock_analysis_card.png"
        else:
            out_file = "demo_report_card.png"

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
