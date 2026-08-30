#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股量化战报长图渲染引擎 (stock-prompt Report Card Generator)
支持将【盘前全景推演】、【每日收盘产业链复盘】、【5日板块轮动深度复盘】的三大场景全量数据渲染为高清极简金融研报长图。
"""

import os
import sys
import json
import argparse
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def get_font(size=24, bold=False):
    """跨平台中文字体加载"""
    font_candidates = [
        "C:\\Windows\\Fonts\\msyh.ttc",       # 微软雅黑
        "C:\\Windows\\Fonts\\msyhbd.ttc" if bold else "C:\\Windows\\Fonts\\msyh.ttc",
        "C:\\Windows\\Fonts\\simhei.ttf",      # 黑体
        "/System/Library/Fonts/PingFang.ttc",  # macOS 苹方
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc" # Linux
    ]
    for p in font_candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()

def draw_badge(draw, text, xy, bg_color="#e0f2fe", text_color="#0369a1", font=None):
    """绘制圆角徽章胶囊"""
    if font is None:
        font = get_font(16)
    bbox = font.getbbox(text)
    w = bbox[2] - bbox[0] + 16
    h = bbox[3] - bbox[1] + 10
    x, y = xy
    draw.rounded_rectangle([x, y, x + w, y + h], radius=5, fill=bg_color)
    draw.text((x + 8, y + 3), text, fill=text_color, font=font)
    return w, h

def render_daily_review_card(data=None, output_path="daily_review_card.png", theme="light"):
    """
    专门渲染【A股每日强势板块与产业链共振深度复盘】全量长图 (宽幅 1220px 版)
    """
    is_light = (theme == "light")

    if is_light:
        BG_PAGE = "#f8fafc"
        BG_CARD = "#ffffff"
        BG_INNER = "#f1f5f9"
        BG_ROW_ALT = "#f8fafc"
        BORDER_CARD = "#e2e8f0"
        BORDER_INNER = "#cbd5e1"
        TEXT_TITLE = "#0f172a"
        TEXT_H2 = "#1d4ed8"
        TEXT_BODY = "#1e293b"
        TEXT_MUTED = "#64748b"
        DIVIDER = "#e2e8f0"
        TOP_BAR = "#059669"
        BADGE_BG1 = "#dcfce7"
        BADGE_TXT1 = "#15803d"
        BADGE_BG2 = "#f1f5f9"
        BADGE_TXT2 = "#475569"
        COLOR_UP = "#dc2626"
        COLOR_DOWN = "#16a34a"
        COLOR_ACCENT = "#059669"
        COLOR_WARN = "#d97706"
    else:
        BG_PAGE = "#0b0f19"
        BG_CARD = "#131c2e"
        BG_INNER = "#0f172a"
        BG_ROW_ALT = "#111827"
        BORDER_CARD = "#1e293b"
        BORDER_INNER = "#1e293b"
        TEXT_TITLE = "#f8fafc"
        TEXT_H2 = "#34d399"
        TEXT_BODY = "#f8fafc"
        TEXT_MUTED = "#64748b"
        DIVIDER = "#1e293b"
        TOP_BAR = "#34d399"
        BADGE_BG1 = "#065f46"
        BADGE_TXT1 = "#d1fae5"
        BADGE_BG2 = "#1e293b"
        BADGE_TXT2 = "#94a3b8"
        COLOR_UP = "#f43f5e"
        COLOR_DOWN = "#4ade80"
        COLOR_ACCENT = "#34d399"
        COLOR_WARN = "#fbbf24"

    W = 1220
    H = 2600
    img = Image.new("RGBA", (W, H), BG_PAGE)
    draw = ImageDraw.Draw(img)

    for i in range(10):
        draw.line([(0, i), (W, i)], fill=TOP_BAR, width=1)

    font_title = get_font(34, bold=True)
    font_h2 = get_font(21, bold=True)
    font_h3 = get_font(18, bold=True)
    font_body = get_font(16)
    font_small = get_font(15)
    font_micro = get_font(13)

    if data is None:
        data = {}

    date_str = data.get("date", datetime.now().strftime("%Y-%m-%d"))

    # 1. 标题区
    draw.text((50, 42), "A股每日强势板块与产业链共振复盘报告", fill=TEXT_TITLE, font=font_title)
    draw_badge(draw, f"复盘时点: {date_str} 15:00 收盘", (W - 320, 46), bg_color=BADGE_BG2, text_color=BADGE_TXT2, font=font_small)
    draw_badge(draw, "收盘全景复盘", (W - 470, 46), bg_color=BADGE_BG1, text_color=BADGE_TXT1, font=font_small)
    draw.line([(50, 100), (W - 50, 100)], fill=DIVIDER, width=2)

    # 2. 30秒核心速览五宫格
    top_metrics = [
        ("Market Regime", data.get("regime", "S3 趋势启动 (过渡)"), COLOR_ACCENT),
        ("市场情绪总分", f"{data.get('sentiment_score', 78)}/100", COLOR_UP),
        ("第一核心主线", data.get("top_sector", "半导体/算力 [强化期]"), COLOR_ACCENT),
        ("资金留存率", f"{data.get('retention', '88%')} [高锁仓]", COLOR_WARN),
        ("综合机会评分", f"{data.get('opportunity_score', 86)}/100 [优良]", COLOR_UP),
    ]

    card_w = (W - 100 - 40) // 5
    card_y = 120
    for i, (label, val, col) in enumerate(top_metrics):
        cx = 50 + i * (card_w + 10)
        draw.rounded_rectangle([cx, card_y, cx + card_w, card_y + 95], radius=8, fill=BG_CARD, outline=BORDER_CARD, width=1)
        draw.text((cx + 12, card_y + 14), label, fill=TEXT_MUTED, font=font_micro)
        draw.text((cx + 12, card_y + 42), str(val), fill=col, font=get_font(19, bold=True))

    curr_y = 235

    # 3. 模块一：【市场情绪与资金总量定调】
    sec1_h = 320
    draw.rounded_rectangle([50, curr_y, W - 50, curr_y + sec1_h], radius=10, fill=BG_CARD, outline=BORDER_CARD, width=1)
    draw.text((70, curr_y + 16), "01 / 市场情绪打分、量能环境与 Market Regime 状态定调", fill=TEXT_H2, font=font_h2)

    col_w = (W - 140 - 20) // 2

    # 左栏：情绪明细五项打分
    draw.rounded_rectangle([70, curr_y + 55, 70 + col_w, curr_y + 295], radius=8, fill=BG_INNER, outline=BORDER_INNER, width=1)
    draw.text((90, curr_y + 70), "[情绪引擎评分拆解] 标准 0-100 量纲", fill=TEXT_H2, font=font_h3)

    sent_items = [
        ("• 涨跌家数比 (25分)", "上涨 3320 家 / 下跌 1850 家 (涨跌比 6.4:3.6) -> 得分: 18 / 25"),
        ("• 昨日涨停溢价 (20分)", "昨日涨停个股今日平均红盘率 74.2% -> 得分: 20 / 20"),
        ("• 连板晋级率 (20分)", "首板进二板晋级率 61.54% (接力健康) -> 得分: 20 / 20"),
        ("• 炸板率得分 (20分)", "全市场涨停 77 家，炸板 17 家 (炸板率 18.0%) -> 得分: 12 / 20"),
        ("• 两市总成交量 (15分)", "全天 2.12 万亿，较 5 日均量放量 +14.8% -> 得分: 8 / 15")
    ]
    for s_idx, (t, d) in enumerate(sent_items):
        sy = curr_y + 102 + s_idx * 37
        draw.text((90, sy), t, fill=COLOR_ACCENT, font=font_small)
        draw.text((90, sy + 18), d, fill=TEXT_BODY, font=font_micro)

    # 右栏：Market Regime 定调与量能
    rx = 70 + col_w + 20
    draw.rounded_rectangle([rx, curr_y + 55, rx + col_w, curr_y + 295], radius=8, fill=BG_INNER, outline=BORDER_INNER, width=1)
    draw.text((rx + 20, curr_y + 70), "[总量环境与 Regime 定调] 仓位指引", fill=TEXT_H2, font=font_h3)

    regime_details = [
        ("【Market Regime 定调】", "处于 S2 存量震荡 向 S3 趋势启动 过渡态"),
        ("【两市量价健康度】", "成交额突破 2.1 万亿，属于放量良性攻坚，无缩量诱多背离"),
        ("【主线资金集中度】", "前 3 大热点行业成交占比达 24.5%，主力做多合力高度聚焦"),
        ("【一日游风险体检】", "[低风险] 未触发偷尾盘、无连板等 6 大一日游刹车规则"),
        ("【条件化仓位导向】", "建议总仓位维持在 6 ～ 8 成 区间，积极参与核心主线低吸")
    ]
    for r_idx, (t, d) in enumerate(regime_details):
        ry = curr_y + 102 + r_idx * 37
        draw.text((rx + 20, ry), t, fill=COLOR_UP if "仓位" in t else (COLOR_ACCENT if "Regime" in t else COLOR_WARN), font=font_small)
        draw.text((rx + 20, ry + 18), d, fill=TEXT_BODY, font=font_micro)

    curr_y += sec1_h + 20

    # 4. 模块二：【强势板块主线定位与资金留存率 (Capital Retention)】
    sec2_h = 320
    draw.rounded_rectangle([50, curr_y, W - 50, curr_y + sec2_h], radius=10, fill=BG_CARD, outline=BORDER_CARD, width=1)
    draw.text((70, curr_y + 16), "02 / 强势板块定位、资金留存率 (Capital Retention) 与梯队质量", fill=TEXT_H2, font=font_h2)

    sec_headers = ["排名", "强势板块名称", "板块涨幅", "涨停家数", "成交额占比", "资金留存率 (Retention)", "驱动等级", "板块定位", "吸血与跷跷板判定"]
    sec_col_x = [70, 130, 290, 390, 490, 610, 780, 870, 990]
    th_y = curr_y + 54
    for h, x in zip(sec_headers, sec_col_x):
        draw.text((x, th_y), h, fill=TEXT_MUTED, font=font_micro)
    draw.line([(65, th_y + 22), (W - 65, th_y + 22)], fill=DIVIDER, width=1)

    sectors_daily = [
        ("1", "半导体/算力硬件", "+4.22%", "14 家", "11.5%", "88% [强沉淀锁仓]", "S 级 (行业革命)", "[核心主线]", "强吸血医药生物与新能源"),
        ("2", "农林牧渔/粮食安全", "+3.85%", "8 家", "6.2%", "92% [资金高留存]", "A 级 (国家战略)", "[独立防守]", "与大盘形成良性逆势对冲"),
        ("3", "基础化工/化肥农化", "+2.95%", "6 家", "4.8%", "72% [良性换手]", "B 级 (旺季催化)", "[结构补涨]", "承接高位科技分流溢出资金"),
        ("4", "医药生物/创新药", "-1.40%", "1 家", "3.1%", "42% [大幅流出]", "C 级 (常规轮动)", "[边缘退潮]", "受主线吸血严重失血阴跌")
    ]

    for row_idx, row in enumerate(sectors_daily):
        ry = th_y + 28 + row_idx * 52
        if row_idx % 2 == 1:
            draw.rectangle([65, ry - 6, W - 65, ry + 42], fill=BG_ROW_ALT)
        draw.text((sec_col_x[0], ry), row[0], fill=COLOR_ACCENT, font=font_small)
        draw.text((sec_col_x[1], ry), row[1], fill=TEXT_BODY, font=font_small)
        draw.text((sec_col_x[2], ry), row[2], fill=COLOR_UP if "+" in row[2] else COLOR_DOWN, font=font_small)
        draw.text((sec_col_x[3], ry), row[3], fill=TEXT_BODY, font=font_micro)
        draw.text((sec_col_x[4], ry), row[4], fill=COLOR_ACCENT, font=font_micro)
        draw.text((sec_col_x[5], ry), row[5], fill=COLOR_WARN, font=font_small)
        draw.text((sec_col_x[6], ry), row[6], fill=COLOR_UP, font=font_micro)
        draw.text((sec_col_x[7], ry), row[7], fill=COLOR_DOWN if "主线" in row[7] else (COLOR_WARN if "补涨" in row[7] else COLOR_UP), font=font_small)
        draw.text((sec_col_x[8], ry), row[8], fill=TEXT_MUTED, font=font_micro)

    curr_y += sec2_h + 20

    # 5. 模块三：【产业链深度共振质量与上中下游全景穿透】
    sec3_h = 390
    draw.rounded_rectangle([50, curr_y, W - 50, curr_y + sec3_h], radius=10, fill=BG_CARD, outline=BORDER_CARD, width=1)
    draw.text((70, curr_y + 16), "03 / 产业链深度共振评分 (0-100) 与上中下游全景穿透", fill=TEXT_H2, font=font_h2)

    res_w = (W - 140 - 30) // 4
    res_items = [
        ("细分上涨占比", "23 / 25 分", "92% 细分板块飘红", COLOR_UP),
        ("细分涨停广度", "32 / 35 分", "上中下游皆有涨停封板", COLOR_UP),
        ("放量扩散度", "22 / 25 分", "各环节成交量同步放大", COLOR_ACCENT),
        ("共振质量总分", "92 / 100 分", "【强产业链深度共振】", COLOR_UP)
    ]
    for r_i, (l, v, sub, c) in enumerate(res_items):
        rx_pos = 70 + r_i * (res_w + 10)
        draw.rounded_rectangle([rx_pos, curr_y + 55, rx_pos + res_w, curr_y + 150], radius=8, fill=BG_INNER, outline=BORDER_INNER, width=1)
        draw.text((rx_pos + 12, curr_y + 68), l, fill=TEXT_MUTED, font=font_micro)
        draw.text((rx_pos + 12, curr_y + 92), v, fill=c, font=get_font(20, bold=True))
        draw.text((rx_pos + 12, curr_y + 122), sub, fill=TEXT_BODY, font=font_micro)

    sub_y = curr_y + 170
    draw.rounded_rectangle([70, sub_y, W - 70, sub_y + 195], radius=8, fill=BG_INNER, outline=BORDER_INNER, width=1)
    draw.text((90, sub_y + 14), "[产业链穿透全景] 核心主线 [半导体/算力] 资金扩散映射", fill=TEXT_H2, font=font_h3)

    chain_details = [
        ("• 上游 (材料/EDA/设备)", "北方华创、中微公司、雅克科技 -> 资金温和放量布局，机构席位逆势净加仓，奠定底层基本面"),
        ("• 中游 (芯片/PCB/光模块)", "中际旭创 (成交280亿)、胜宏科技、新易盛 -> 产业链绝对爆发核心，资金留存率 88%，机构重仓锁仓"),
        ("• 下游 (算力服务器/AI应用)", "工业富联、浪潮信息、金山办公 -> 细分扩散良好，跟随中军放量共振，无单点一日游衰竭迹象")
    ]
    for c_i, (c_name, c_desc) in enumerate(chain_details):
        cy = sub_y + 45 + c_i * 48
        draw.text((90, cy), c_name, fill=COLOR_ACCENT, font=font_small)
        draw.text((90, cy + 20), c_desc, fill=TEXT_BODY, font=font_micro)

    curr_y += sec3_h + 20

    # 6. 模块四：【龙虎榜席位品质、筹码结构与核心股池矩阵】
    sec4_h = 320
    draw.rounded_rectangle([50, curr_y, W - 50, curr_y + sec4_h], radius=10, fill=BG_CARD, outline=BORDER_CARD, width=1)
    draw.text((70, curr_y + 16), "04 / 龙虎榜席位品质、筹码结构体检与核心股池交易结构", fill=TEXT_H2, font=font_h2)

    stock_headers = ["角色定位", "标的代码/名称", "今日涨跌幅", "筹码结构/换手特征", "龙虎榜席位品质", "交易结构建议 (优先/等待/避免)"]
    stock_col_x = [70, 220, 390, 520, 710, 930]
    th_y = curr_y + 54
    for h, x in zip(stock_headers, stock_col_x):
        draw.text((x, th_y), h, fill=TEXT_MUTED, font=font_micro)
    draw.line([(65, th_y + 22), (W - 65, th_y + 22)], fill=DIVIDER, width=1)

    stocks_data = [
        ("领航龙头", "寒武纪 (688256)", "+12.45%", "充分换手板，放量突破前期平台", "知名游资席位锁仓加持", "【优先】观察龙头封单，做先锋确认"),
        ("容量中军", "中际旭创 (300308)", "+8.65%", "全天成交280亿，机构锁仓良好", "机构净买入 2.53 亿元", "【等待】早盘分歧均线放量承接时低吸"),
        ("低位弹性", "胜宏科技 (300476)", "+15.20%", "20cm 放量突破，细分扩散弹性", "量化与机构混合合力", "【等待】逢回踩均线分歧低吸弹性先锋"),
        ("防守中军", "万向德农 (600371)", "+10.02%", "8天5板强势涨停，筹码高锁仓", "游资合力坚决封死涨停", "【避免】一致性大幅高开盲目无脑追涨")
    ]

    for row_idx, row in enumerate(stocks_data):
        ry = th_y + 28 + row_idx * 52
        if row_idx % 2 == 1:
            draw.rectangle([65, ry - 6, W - 65, ry + 42], fill=BG_ROW_ALT)
        draw.text((stock_col_x[0], ry), row[0], fill=COLOR_ACCENT, font=font_small)
        draw.text((stock_col_x[1], ry), row[1], fill=COLOR_WARN, font=font_small)
        draw.text((stock_col_x[2], ry), row[2], fill=COLOR_UP if "+" in row[2] else COLOR_DOWN, font=font_small)
        draw.text((stock_col_x[3], ry), row[3], fill=TEXT_BODY, font=font_micro)
        draw.text((stock_col_x[4], ry), row[4], fill=COLOR_DOWN, font=font_micro)
        draw.text((stock_col_x[5], ry), row[5], fill=COLOR_UP if "优先" in row[5] else (COLOR_ACCENT if "等待" in row[5] else COLOR_WARN), font=font_small)

    curr_y += sec4_h + 20

    # 7. 模块五：【综合机会评分仪表盘 & 次日推演三大情景】
    sec5_h = 330
    draw.rounded_rectangle([50, curr_y, W - 50, curr_y + sec5_h], radius=10, fill=BG_CARD, outline=BORDER_CARD, width=1)
    draw.text((70, curr_y + 16), "05 / 综合机会评分仪表盘 (Opportunity) 与次日推演三大情景", fill=TEXT_H2, font=font_h2)

    # 仪表盘总结栏
    dash_y = curr_y + 55
    draw.rounded_rectangle([70, dash_y, W - 70, dash_y + 80], radius=8, fill=BG_INNER, outline=BORDER_INNER, width=1)
    draw.text((90, dash_y + 15), "[综合机会评分] Opportunity Score: 86 / 100 分  |  当前生命周期: [强化期]  |  建议总仓位: 6 ～ 8 成", fill=TEXT_H2, font=font_h3)
    draw.text((90, dash_y + 45), "[核心策略定调] 主线资金留存率极高，量价配合健康，明日策略以【核心中军分歧放量承接时低吸】为主，禁止追高开。", fill=TEXT_BODY, font=font_small)

    # 三大情景推演卡片
    scenarios = [
        ("[情景 A] 强势主升延续", "触发条件：领航龙头竞价高开 > 3% 且 30 分钟内放量封板 -> 操作：积极持股做多核心中军"),
        ("[情景 B] 分歧转一致低吸", "触发条件：早盘微幅低开回踩 MA5 均线获大单放量承接 -> 操作：于分时均线附近分批逢低介入中军"),
        ("[情景 C] 退潮冲高回落防守", "触发条件：板块放量但后排大面积炸板，中军遭大额卖单砸盘 -> 操作：坚决逢高减仓，严禁逆势补仓")
    ]
    for sc_i, (sc_title, sc_desc) in enumerate(scenarios):
        sc_y = curr_y + 150 + sc_i * 48
        draw.rounded_rectangle([70, sc_y, W - 70, sc_y + 40], radius=6, fill=BG_ROW_ALT, outline=BORDER_INNER, width=1)
        draw.text((90, sc_y + 12), sc_title, fill=COLOR_DOWN if "A" in sc_title else (COLOR_ACCENT if "B" in sc_title else COLOR_UP), font=font_small)
        draw.text((290, sc_y + 12), sc_desc, fill=TEXT_BODY, font=font_micro)

    draw.text((70, curr_y + 300), "[风控纪律底线] 单票止损位严格锚定 MA5 均线或 -5%，严禁在一致性高潮日追涨跟风杂毛。", fill=COLOR_UP, font=font_micro)

    curr_y += sec5_h + 30

    # 8. 底部版权与免责声明
    draw.line([(50, curr_y), (W - 50, curr_y)], fill=DIVIDER, width=1)
    draw.text((50, curr_y + 15), "由 stock-prompt 每日产业链复盘引擎自动生成 | GitHub: Geekwls/stock-prompt", fill=TEXT_MUTED, font=font_small)
    draw.text((W - 380, curr_y + 15), "免责声明：仅供量化研究参考，不构成任何投资建议", fill=COLOR_UP, font=font_small)

    img.save(output_path, "PNG")
    print(f"Daily review report card generated: {os.path.abspath(output_path)}")
    return output_path

def render_sector_rotation_card(data=None, output_path="sector_rotation_card.png", theme="light"):
    """
    专门渲染【A股近5日板块轮动与节奏深度复盘】全量长图 (宽幅 1220px 版)
    """
    is_light = (theme == "light")

    if is_light:
        BG_PAGE = "#f8fafc"
        BG_CARD = "#ffffff"
        BG_INNER = "#f1f5f9"
        BG_ROW_ALT = "#f8fafc"
        BORDER_CARD = "#e2e8f0"
        BORDER_INNER = "#cbd5e1"
        TEXT_TITLE = "#0f172a"
        TEXT_H2 = "#1d4ed8"
        TEXT_BODY = "#1e293b"
        TEXT_MUTED = "#64748b"
        DIVIDER = "#e2e8f0"
        TOP_BAR = "#0284c7"
        BADGE_BG1 = "#e0f2fe"
        BADGE_TXT1 = "#0369a1"
        BADGE_BG2 = "#f1f5f9"
        BADGE_TXT2 = "#475569"
        COLOR_UP = "#dc2626"
        COLOR_DOWN = "#16a34a"
        COLOR_ACCENT = "#0284c7"
        COLOR_WARN = "#d97706"
    else:
        BG_PAGE = "#0b0f19"
        BG_CARD = "#131c2e"
        BG_INNER = "#0f172a"
        BG_ROW_ALT = "#111827"
        BORDER_CARD = "#1e293b"
        BORDER_INNER = "#1e293b"
        TEXT_TITLE = "#f8fafc"
        TEXT_H2 = "#38bdf8"
        TEXT_BODY = "#f8fafc"
        TEXT_MUTED = "#64748b"
        DIVIDER = "#1e293b"
        TOP_BAR = "#38bdf8"
        BADGE_BG1 = "#0369a1"
        BADGE_TXT1 = "#e0f2fe"
        BADGE_BG2 = "#1e293b"
        BADGE_TXT2 = "#94a3b8"
        COLOR_UP = "#f43f5e"
        COLOR_DOWN = "#4ade80"
        COLOR_ACCENT = "#38bdf8"
        COLOR_WARN = "#fbbf24"

    W = 1220
    H = 2600
    img = Image.new("RGBA", (W, H), BG_PAGE)
    draw = ImageDraw.Draw(img)

    for i in range(10):
        draw.line([(0, i), (W, i)], fill=TOP_BAR, width=1)

    font_title = get_font(34, bold=True)
    font_h2 = get_font(21, bold=True)
    font_h3 = get_font(18, bold=True)
    font_body = get_font(16)
    font_small = get_font(15)
    font_micro = get_font(13)

    draw.text((50, 42), "A股近 5 日板块轮动与节奏深度复盘", fill=TEXT_TITLE, font=font_title)
    draw_badge(draw, "分析区间: 8月24日(T-4) ~ 8月28日(T日)", (W - 380, 46), bg_color=BADGE_BG2, text_color=BADGE_TXT2, font=font_small)
    draw_badge(draw, "中期轮动推演", (W - 510, 46), bg_color=BADGE_BG1, text_color=BADGE_TXT1, font=font_small)
    draw.line([(50, 100), (W - 50, 100)], fill=DIVIDER, width=2)

    top_metrics = [
        ("总量环境定性", "【存量轮动】", COLOR_WARN),
        ("当前轮动状态", "State 2 畏高切低", COLOR_ACCENT),
        ("主线衰竭 SEI", "64 / 100 [严重衰竭]", COLOR_UP),
        ("收盘情绪温度", "30 / 100 [偏低分化]", COLOR_WARN),
        ("高低切流向", "农业种植 / 基础化工", COLOR_DOWN),
    ]

    card_w = (W - 100 - 40) // 5
    card_y = 120
    for i, (label, val, col) in enumerate(top_metrics):
        cx = 50 + i * (card_w + 10)
        draw.rounded_rectangle([cx, card_y, cx + card_w, card_y + 95], radius=8, fill=BG_CARD, outline=BORDER_CARD, width=1)
        draw.text((cx + 12, card_y + 14), label, fill=TEXT_MUTED, font=font_micro)
        draw.text((cx + 12, card_y + 42), str(val), fill=col, font=get_font(19, bold=True))

    curr_y = 235

    sec1_h = 320
    draw.rounded_rectangle([50, curr_y, W - 50, curr_y + sec1_h], radius=10, fill=BG_CARD, outline=BORDER_CARD, width=1)
    draw.text((70, curr_y + 16), "01 / 5 日成交额走势与主力资金行业流向定调", fill=TEXT_H2, font=font_h2)

    col_w = (W - 140 - 20) // 2

    draw.rounded_rectangle([70, curr_y + 55, 70 + col_w, curr_y + 295], radius=8, fill=BG_INNER, outline=BORDER_INNER, width=1)
    draw.text((90, curr_y + 70), "[5日量能走向] 近 5 个交易日两市成交额及环比", fill=TEXT_H2, font=font_h3)

    vol_headers = ["交易日", "日期", "两市成交额", "环比变化", "量能定性"]
    vol_x = [90, 160, 260, 360, 460]
    for h, x in zip(vol_headers, vol_x):
        draw.text((x, curr_y + 100), h, fill=TEXT_MUTED, font=font_micro)
    draw.line([(85, curr_y + 120), (70 + col_w - 15, curr_y + 120)], fill=DIVIDER, width=1)

    vol_data = [
        ("T-4", "8月24日 (周一)", "约 2.01 万亿", "放量 +1282亿", "放量杀跌"),
        ("T-3", "8月25日 (周二)", "约 1.84 万亿", "缩量 -1769亿", "缩量普涨"),
        ("T-2", "8月26日 (周三)", "约 1.82 万亿", "缩量 -231亿", "阶段地量"),
        ("T-1", "8月27日 (周四)", "约 2.13 万亿", "放量 +3172亿", "放量上攻"),
        ("T日", "8月28日 (周五)", "约 2.12 万亿", "缩量 -232亿", "缩量分化")
    ]
    for r_idx, r in enumerate(vol_data):
        vy = curr_y + 130 + r_idx * 30
        draw.text((vol_x[0], vy), r[0], fill=COLOR_ACCENT, font=font_micro)
        draw.text((vol_x[1], vy), r[1], fill=TEXT_BODY, font=font_micro)
        draw.text((vol_x[2], vy), r[2], fill=COLOR_UP if "放量" in r[4] else COLOR_DOWN, font=font_micro)
        draw.text((vol_x[3], vy), r[3], fill=TEXT_MUTED, font=font_micro)
        draw.text((vol_x[4], vy), r[4], fill=COLOR_WARN if "分化" in r[4] or "地量" in r[4] else TEXT_BODY, font=font_micro)

    rx = 70 + col_w + 20
    draw.rounded_rectangle([rx, curr_y + 55, rx + col_w, curr_y + 295], radius=8, fill=BG_INNER, outline=BORDER_INNER, width=1)
    draw.text((rx + 20, curr_y + 70), "[主力资金流向] 近 5 日净流入 Top3 vs 净流出 Top3", fill=TEXT_H2, font=font_h3)

    in_out_details = [
        ("[主力流入 Top1]", "基础化工：T日主力资金净流入居首，化肥农化集体走强"),
        ("[主力流入 Top2]", "专用设备：T-3日净流入41.54亿，智能制造底仓配置"),
        ("[主力流入 Top3]", "有色金属：T-2日净流入超百亿，大宗商品涨价驱动"),
        ("[主力流出 Top1]", "电子/半导体：T日电子净流出居首，科技硬件高潮次日大出逃"),
        ("[主力流出 Top2]", "电池/新能源：T-3日净流出26.16亿，反弹持续性不足"),
        ("[主力流出 Top3]", "工业金属：周期股冲高回落，获利盘集中兑现")
    ]
    for io_idx, (t, d) in enumerate(in_out_details):
        iy = curr_y + 102 + io_idx * 30
        draw.text((rx + 20, iy), t, fill=COLOR_UP if "流出" in t else COLOR_DOWN, font=font_micro)
        draw.text((rx + 155, iy), d, fill=TEXT_BODY, font=font_micro)

    curr_y += sec1_h + 20

    sec2_h = 320
    draw.rounded_rectangle([50, curr_y, W - 50, curr_y + sec2_h], radius=10, fill=BG_CARD, outline=BORDER_CARD, width=1)
    draw.text((70, curr_y + 16), "02 / 主线角逐与资金博弈 (机构趋势 vs 游资连板 & 跷跷板吸血)", fill=TEXT_H2, font=font_h2)

    draw.rounded_rectangle([70, curr_y + 55, 70 + col_w, curr_y + 295], radius=8, fill=BG_INNER, outline=BORDER_INNER, width=1)
    draw.text((90, curr_y + 70), "[机构趋势方向] 持续强化线与席位品质", fill=TEXT_H2, font=font_h3)

    inst_items = [
        ("• 农林牧渔 (+6.5%)", "本周涨幅居首，国家粮食安全战略深化催化"),
        ("• 煤炭行业 (+5.1%)", "连续 13 个交易日获主力净流入，高股息抱团"),
        ("• 基础化工 (+3.9%)", "T日主力净流入第一，化肥农化迎金秋旺季"),
        ("• 龙虎榜机构席位", "嘉立创(净买2.53亿)、肯特股份(净买6989万)获机构加仓"),
        ("• 机构风险预警", "[警示] 散户接盘：电子板块T-1大幅流入后T日即反手出货")
    ]
    for inst_idx, (t, d) in enumerate(inst_items):
        iy = curr_y + 105 + inst_idx * 36
        draw.text((90, iy), t, fill=COLOR_ACCENT if "农林" in t or "煤炭" in t or "化工" in t else (COLOR_UP if "警示" in t else COLOR_DOWN), font=font_small)
        draw.text((90, iy + 18), d, fill=TEXT_BODY, font=font_micro)

    draw.rounded_rectangle([rx, curr_y + 55, rx + col_w, curr_y + 295], radius=8, fill=BG_INNER, outline=BORDER_INNER, width=1)
    draw.text((rx + 20, curr_y + 70), "[游资连板穿越] 情绪高度 & 跷跷板吸血效应", fill=TEXT_H2, font=font_h3)

    hot_items = [
        ("• 深中华A (6连板)", "黄金概念领航龙头，高位换手穿越"),
        ("• 万向德农 (8天5板)", "农业种业连板龙头，T日继续涨停树立标杆"),
        ("• 汉森制药 (大面股)", "6连板后炸板直线跳水，T日再跌 -6.35%"),
        ("• 核心跷跷板拉锯", "科技成长 (半导体/CPO) vs 农业/化工/房地产"),
        ("• 资金吸血结论", "高位科技流出资金直接切换至低位农业化工，跷跷板极强")
    ]
    for hot_idx, (t, d) in enumerate(hot_items):
        hy = curr_y + 105 + hot_idx * 36
        draw.text((rx + 20, hy), t, fill=COLOR_UP if "面" in t else (COLOR_WARN if "跷跷板" in t or "吸血" in t else COLOR_ACCENT), font=font_small)
        draw.text((rx + 20, hy + 18), d, fill=TEXT_BODY, font=font_micro)

    curr_y += sec2_h + 20

    sec3_h = 390
    draw.rounded_rectangle([50, curr_y, W - 50, curr_y + sec3_h], radius=10, fill=BG_CARD, outline=BORDER_CARD, width=1)
    draw.text((70, curr_y + 16), "03 / 产业链传导与核心主线衰竭指数 (SEI) 深度量化", fill=TEXT_H2, font=font_h2)

    sei_w = (W - 140 - 30) // 4
    sei_items = [
        ("量价背离度得分", "28 / 40 分", "严重放量滞涨 / 阴跌", COLOR_UP),
        ("接力与炸板风险", "12 / 30 分", "高位松动 / 龙头断板", COLOR_WARN),
        ("资金溢出高低切", "24 / 30 分", "主力大幅撤离涌向低位", COLOR_UP),
        ("SEI 综合衰竭得分", "64 / 100 分", "【动能严重衰竭 / 高低切】", COLOR_UP)
    ]
    for s_i, (l, v, sub, c) in enumerate(sei_items):
        sx = 70 + s_i * (sei_w + 10)
        draw.rounded_rectangle([sx, curr_y + 55, sx + sei_w, curr_y + 150], radius=8, fill=BG_INNER, outline=BORDER_INNER, width=1)
        draw.text((sx + 12, curr_y + 68), l, fill=TEXT_MUTED, font=font_micro)
        draw.text((sx + 12, curr_y + 92), v, fill=c, font=get_font(20, bold=True))
        draw.text((sx + 12, curr_y + 122), sub, fill=TEXT_BODY, font=font_micro)

    sub_y = curr_y + 170
    draw.rounded_rectangle([70, sub_y, W - 70, sub_y + 195], radius=8, fill=BG_INNER, outline=BORDER_INNER, width=1)
    draw.text((90, sub_y + 14), "[产业链传导] 近 5 日三大产业链扩散全景对比", fill=TEXT_H2, font=font_h3)

    chains_data = [
        ("[强化主线] 农业产业链", "化肥/农药 -> 种植业/种业 -> 农产品加工", "李强总理调研 + APEC粮食安全会议，万向德农、敦煌种业涨停共振"),
        ("[脉冲退潮] 科技硬件链", "半导体材料/设备 -> 芯片/PCB/光模块 -> AI算力", "T-1日英伟达财报催化暴涨，T日即放量冲高回落见顶 (半导体-2.12%)，资金坚决派发"),
        ("[低位补涨] 基础化工链", "化学原料 -> 精细化学制品 -> 农化制品", "主力资金T日净流入居首，承接科技流出资金，呈现标准高低切补涨态势")
    ]
    for c_i, (c_name, c_path, c_desc) in enumerate(chains_data):
        cy = sub_y + 45 + c_i * 48
        draw.text((90, cy), c_name, fill=COLOR_DOWN if "农业" in c_name else (COLOR_UP if "科技" in c_name else COLOR_WARN), font=font_small)
        draw.text((310, cy), f"路径: {c_path}", fill=COLOR_ACCENT, font=font_micro)
        draw.text((90, cy + 20), f"实战: {c_desc}", fill=TEXT_BODY, font=font_micro)

    curr_y += sec3_h + 20

    sec4_h = 330
    draw.rounded_rectangle([50, curr_y, W - 50, curr_y + sec4_h], radius=10, fill=BG_CARD, outline=BORDER_CARD, width=1)
    draw.text((70, curr_y + 16), "04 / 5 日情绪指标走向与中军/龙头盘前观察锚点", fill=TEXT_H2, font=font_h2)

    sent_headers = ["交易日", "日期", "红盘率", "连板晋级率", "炸板率", "市场情绪定性", "情绪得分"]
    sent_x = [70, 150, 310, 440, 580, 720, 900]
    th_y = curr_y + 54
    for h, x in zip(sent_headers, sent_x):
        draw.text((x, th_y), h, fill=TEXT_MUTED, font=font_micro)
    draw.line([(65, th_y + 22), (W - 65, th_y + 22)], fill=DIVIDER, width=1)

    sent_data = [
        ("T-4", "8月24日 (周一)", "~27% (1460家红)", "36.36%", "26.0%", "冰点杀跌", "24 / 100"),
        ("T-3", "8月25日 (周二)", "~78% (4200家红)", "估算 ~35%", "估算 ~25%", "超跌修复", "68 / 100"),
        ("T-2", "8月26日 (周三)", "~55% (2946家红)", "估算 ~30%", "33.33%", "温和整理", "52 / 100"),
        ("T-1", "8月27日 (周四)", "~63% (3300家红)", "61.54%", "18.0%", "高潮加速", "82 / 100"),
        ("T日", "8月28日 (周五)", "~56% (3000家红)", "估算 ~30%", "估算 ~22%", "分化降温", "30 / 100")
    ]
    for s_idx, r in enumerate(sent_data):
        sy = th_y + 30 + s_idx * 32
        if s_idx % 2 == 1:
            draw.rectangle([65, sy - 6, W - 65, sy + 24], fill=BG_ROW_ALT)
        draw.text((sent_x[0], sy), r[0], fill=COLOR_ACCENT, font=font_micro)
        draw.text((sent_x[1], sy), r[1], fill=TEXT_BODY, font=font_micro)
        draw.text((sent_x[2], sy), r[2], fill=COLOR_UP if "78%" in r[2] or "63%" in r[2] else COLOR_DOWN, font=font_micro)
        draw.text((sent_x[3], sy), r[3], fill=COLOR_UP if "61%" in r[3] else TEXT_BODY, font=font_micro)
        draw.text((sent_x[4], sy), r[4], fill=COLOR_DOWN if "18%" in r[4] else COLOR_UP, font=font_micro)
        draw.text((sent_x[5], sy), r[5], fill=COLOR_WARN if "分化" in r[5] else (COLOR_UP if "高潮" in r[5] else TEXT_BODY), font=font_micro)
        draw.text((sent_x[6], sy), r[6], fill=COLOR_ACCENT, font=font_micro)

    anchor_y = curr_y + 240
    draw.rounded_rectangle([70, anchor_y, W - 70, anchor_y + 75], radius=6, fill=BG_INNER, outline=BORDER_INNER, width=1)
    draw.text((90, anchor_y + 14), "[机构中军锚点] 中际旭创(成交280亿) 若竞价低开 > -2%，确认机构继续派发；科技板块短期需坚决回避。", fill=COLOR_UP, font=font_micro)
    draw.text((90, anchor_y + 42), "[游资龙头锚点] 万向德农(8天5板) 若竞价高开 > 7% 并快速封板，确认农业情绪延续；若高开低走需防补涨熄火。", fill=COLOR_ACCENT, font=font_micro)

    curr_y += sec4_h + 20

    sec5_h = 320
    draw.rounded_rectangle([50, curr_y, W - 50, curr_y + sec5_h], radius=10, fill=BG_CARD, outline=BORDER_CARD, width=1)
    draw.text((70, curr_y + 16), "05 / 次日盘前重点跟踪矩阵与验证坐标 (Next Day Watchlist)", fill=TEXT_H2, font=font_h2)

    wl_headers = ["跟踪策略分类", "候选板块", "代表标的 (代码/名称)", "次日 9:25 集合竞价验证关注点", "操作策略导向"]
    wl_col_x = [70, 240, 420, 600, 970]
    th_y = curr_y + 54
    for h, x in zip(wl_headers, wl_col_x):
        draw.text((x, th_y), h, fill=TEXT_MUTED, font=font_micro)
    draw.line([(65, th_y + 22), (W - 65, th_y + 22)], fill=DIVIDER, width=1)

    watchlist_rotation = [
        ("高低切潜力主线", "农业种植 / 种业", "万向德农 (600371)", "竞价爆量比 >= 5% 且高开 > 3%，关注首板与20cm弹性", "确认强承接后分歧低吸"),
        ("低位补涨方向", "基础化工 / 化肥", "新赛股份 (600540)", "观察主力资金是否持续净流入，前排封单是否坚决", "寻找 1 进 2 晋级机会"),
        ("老主线止跌观察", "半导体 / 算力硬件", "中际旭创 (300308)", "观察 MA20 均线支撑能否守住，早盘是否缩量企稳", "观望为主，暂不盲目抄底"),
        ("高危回避方向", "高位连续加速题材", "汉森制药 (002412)", "警惕获利盘竞价核按钮抛压，断板后负反馈扩散", "坚决回避，逢反抽离场")
    ]

    for row_idx, row in enumerate(watchlist_rotation):
        ry = th_y + 28 + row_idx * 52
        if row_idx % 2 == 1:
            draw.rectangle([65, ry - 6, W - 65, ry + 42], fill=BG_ROW_ALT)
        draw.text((wl_col_x[0], ry), row[0], fill=TEXT_BODY, font=font_small)
        draw.text((wl_col_x[1], ry), row[1], fill=COLOR_ACCENT, font=font_small)
        draw.text((wl_col_x[2], ry), row[2], fill=COLOR_WARN, font=font_small)
        draw.text((wl_col_x[3], ry), row[3], fill=TEXT_BODY, font=font_micro)
        draw.text((wl_col_x[4], ry), row[4], fill=COLOR_UP if "回避" in row[0] else COLOR_DOWN, font=font_small)

    curr_y += sec5_h + 30

    draw.line([(50, curr_y), (W - 50, curr_y)], fill=DIVIDER, width=1)
    draw.text((50, curr_y + 15), "由 stock-prompt 量化研判引擎自动生成 | GitHub: Geekwls/stock-prompt", fill=TEXT_MUTED, font=font_small)
    draw.text((W - 380, curr_y + 15), "免责声明：仅供量化研究参考，不构成任何投资建议", fill=COLOR_UP, font=font_small)

    img.save(output_path, "PNG")
    print(f"Sector rotation report card generated: {os.path.abspath(output_path)}")
    return output_path

def render_report_card(data=None, output_path="report_card.png", theme="light"):
    """
    全量数据超高清长图渲染 (盘前预测版)
    """
    is_light = (theme == "light")

    if is_light:
        BG_PAGE = "#f8fafc"
        BG_CARD = "#ffffff"
        BG_INNER = "#f1f5f9"
        BG_ROW_ALT = "#f8fafc"
        BORDER_CARD = "#e2e8f0"
        BORDER_INNER = "#cbd5e1"
        TEXT_TITLE = "#0f172a"
        TEXT_H2 = "#1d4ed8"
        TEXT_BODY = "#1e293b"
        TEXT_MUTED = "#64748b"
        DIVIDER = "#e2e8f0"
        TOP_BAR = "#2563eb"
        BADGE_BG1 = "#e0f2fe"
        BADGE_TXT1 = "#0369a1"
        BADGE_BG2 = "#f1f5f9"
        BADGE_TXT2 = "#475569"
        COLOR_UP = "#dc2626"
        COLOR_DOWN = "#16a34a"
        COLOR_ACCENT = "#2563eb"
        COLOR_WARN = "#d97706"
    else:
        BG_PAGE = "#0b0f19"
        BG_CARD = "#131c2e"
        BG_INNER = "#0f172a"
        BG_ROW_ALT = "#111827"
        BORDER_CARD = "#1e293b"
        BORDER_INNER = "#1e293b"
        TEXT_TITLE = "#f8fafc"
        TEXT_H2 = "#38bdf8"
        TEXT_BODY = "#f8fafc"
        TEXT_MUTED = "#64748b"
        DIVIDER = "#1e293b"
        TOP_BAR = "#38bdf8"
        BADGE_BG1 = "#0369a1"
        BADGE_TXT1 = "#e0f2fe"
        BADGE_BG2 = "#1e293b"
        BADGE_TXT2 = "#94a3b8"
        COLOR_UP = "#f43f5e"
        COLOR_DOWN = "#4ade80"
        COLOR_ACCENT = "#38bdf8"
        COLOR_WARN = "#fbbf24"

    W = 1220
    H = 2640
    img = Image.new("RGBA", (W, H), BG_PAGE)
    draw = ImageDraw.Draw(img)

    for i in range(10):
        draw.line([(0, i), (W, i)], fill=TOP_BAR, width=1)

    font_title = get_font(34, bold=True)
    font_h2 = get_font(21, bold=True)
    font_h3 = get_font(18, bold=True)
    font_body = get_font(16)
    font_small = get_font(15)
    font_micro = get_font(13)

    if data is None:
        data = {}

    title_text = data.get("title", "A股盘前全景量化策略研判战报 (V3.0)")
    date_str = data.get("date", datetime.now().strftime("%Y-%m-%d"))
    report_type = data.get("type", "盘前全景推演 (8:30-9:15)")

    draw.text((50, 42), title_text, fill=TEXT_TITLE, font=font_title)
    draw_badge(draw, f"DATE: {date_str}", (W - 220, 46), bg_color=BADGE_BG2, text_color=BADGE_TXT2, font=font_small)
    draw_badge(draw, f"{report_type}", (W - 470, 46), bg_color=BADGE_BG1, text_color=BADGE_TXT1, font=font_small)

    draw.line([(50, 100), (W - 50, 100)], fill=DIVIDER, width=2)

    top_metrics = [
        ("Market Regime", data.get("regime", "S3 趋势启动"), COLOR_ACCENT),
        ("市场情绪分", f"{data.get('sentiment_score', 78)}/100", COLOR_UP),
        ("建议仓位区间", data.get("position", "6 ～ 8 成"), COLOR_WARN),
        ("综合机会评分", f"{data.get('opportunity_score', 85)}/100", COLOR_UP),
        ("第一核心主线", data.get("top_sector", "半导体/算力 [强化期]"), COLOR_ACCENT),
    ]

    card_w = (W - 100 - 40) // 5
    card_y = 120
    for i, (label, val, col) in enumerate(top_metrics):
        cx = 50 + i * (card_w + 10)
        draw.rounded_rectangle([cx, card_y, cx + card_w, card_y + 95], radius=8, fill=BG_CARD, outline=BORDER_CARD, width=1)
        draw.text((cx + 12, card_y + 14), label, fill=TEXT_MUTED, font=font_micro)
        draw.text((cx + 12, card_y + 42), str(val), fill=col, font=get_font(20, bold=True))

    curr_y = 235

    sec1_h = 245
    draw.rounded_rectangle([50, curr_y, W - 50, curr_y + sec1_h], radius=10, fill=BG_CARD, outline=BORDER_CARD, width=1)
    draw.text((70, curr_y + 16), "01 / 4 大独立证据簇与亚太早盘似然反馈 (8:30 黄金窗口)", fill=TEXT_H2, font=font_h2)

    ev_headers = ["证据簇分类", "代表核心指标实况", "证据属性", "似然倾斜 L(E|State)", "对今日A股开盘影响映射"]
    ev_col_x = [70, 240, 620, 750, 930]
    th_y = curr_y + 54
    for h, x in zip(ev_headers, ev_col_x):
        draw.text((x, th_y), h, fill=TEXT_MUTED, font=font_micro)
    draw.line([(65, th_y + 22), (W - 65, th_y + 22)], fill=DIVIDER, width=1)

    ev_data = data.get("evidence", [
        ("[1] 全球科技偏好簇", "纳指 +1.4%, SOX +2.1%, 日经 +0.8%, 三星/海力士高开", "【实时数据】", "P(E|Up) > P(E|Down)", "显著提振A股半导体与算力高开情绪"),
        ("[2] 宏观流动性与外汇", "富时A50 +0.65%, 离岸人民币 7.235 (企稳), 逆回购平稳", "【实时数据】", "P(E|Up) > P(E|Side)", "为大盘权重蓝筹提供流动性估值支撑"),
        ("[3] 国内产业政策催化", "国家粮食安全战略深化 + 算力基础设施扶持规划落地", "【部委政策】", "强催化倾斜", "农业与算力细分获明确政策溢价推动"),
        ("[4] A股内生量价结构", "T-1 两市 2.12万亿, 涨跌比 6:4, 连板晋级 61.5%, 炸板 18%", "【昨日收盘】", "P(E|Up) 支撑", "量能充沛，赚钱效应维持在良性主升")
    ])

    for row_idx, row in enumerate(ev_data):
        ry = th_y + 30 + row_idx * 38
        if row_idx % 2 == 1:
            draw.rectangle([65, ry - 6, W - 65, ry + 28], fill=BG_ROW_ALT)
        draw.text((ev_col_x[0], ry), row[0], fill=TEXT_BODY, font=font_small)
        draw.text((ev_col_x[1], ry), row[1], fill=TEXT_MUTED, font=font_micro)
        draw.text((ev_col_x[2], ry), row[2], fill=COLOR_ACCENT, font=font_micro)
        draw.text((ev_col_x[3], ry), row[3], fill=COLOR_UP, font=font_micro)
        draw.text((ev_col_x[4], ry), row[4], fill=TEXT_BODY, font=font_micro)

    curr_y += sec1_h + 20

    sec2_h = 320
    draw.rounded_rectangle([50, curr_y, W - 50, curr_y + sec2_h], radius=10, fill=BG_CARD, outline=BORDER_CARD, width=1)
    draw.text((70, curr_y + 16), "02 / 四大指数贝叶斯三态概率分布与五维空间点位 (Layer 1 市场预测)", fill=TEXT_H2, font=font_h2)

    idx_headers = ["指数名称", "当前Regime", "P(上涨)", "P(震荡)", "P(下跌)", "强阻力(R2)", "阻力位(R1)", "筹码中枢(P)", "支撑位(S1)", "强支撑(S2)", "上方剩余", "下方空间", "空间研判"]
    idx_col_x = [70, 185, 280, 345, 410, 485, 570, 660, 750, 835, 920, 1000, 1085]
    th_y = curr_y + 54
    for h, x in zip(idx_headers, idx_col_x):
        draw.text((x, th_y), h, fill=TEXT_MUTED, font=font_micro)
    draw.line([(65, th_y + 22), (W - 65, th_y + 22)], fill=DIVIDER, width=1)

    indices = data.get("indices_full", [
        ("上证指数", "S3 启动", "64%", "26%", "10%", "3880", "3850", "3825", "3800", "3770", "+1.4%", "-0.6%", "空间充沛"),
        ("深证成指", "S3 启动", "61%", "27%", "12%", "11250", "11100", "10950", "10820", "10700", "+1.8%", "-1.1%", "良性共振"),
        ("创业板指", "S4 主升", "72%", "20%", "8%", "2380", "2330", "2280", "2245", "2210", "+2.6%", "-1.5%", "主升突破"),
        ("中证1000", "S2 震荡", "52%", "33%", "15%", "6450", "6380", "6320", "6260", "6180", "+0.9%", "-0.9%", "结构分化")
    ])

    for row_idx, row in enumerate(indices):
        ry = th_y + 30 + row_idx * 40
        if row_idx % 2 == 1:
            draw.rectangle([65, ry - 6, W - 65, ry + 30], fill=BG_ROW_ALT)
        draw.text((idx_col_x[0], ry), row[0], fill=TEXT_BODY, font=font_small)
        draw.text((idx_col_x[1], ry), row[1], fill=COLOR_ACCENT, font=font_micro)
        draw.text((idx_col_x[2], ry), row[2], fill=COLOR_UP, font=font_small)
        draw.text((idx_col_x[3], ry), row[3], fill=COLOR_WARN, font=font_micro)
        draw.text((idx_col_x[4], ry), row[4], fill=COLOR_DOWN, font=font_micro)
        draw.text((idx_col_x[5], ry), row[5], fill=COLOR_UP, font=font_small)
        draw.text((idx_col_x[6], ry), row[6], fill=TEXT_BODY, font=font_small)
        draw.text((idx_col_x[7], ry), row[7], fill=COLOR_WARN, font=font_small)
        draw.text((idx_col_x[8], ry), row[8], fill=TEXT_BODY, font=font_small)
        draw.text((idx_col_x[9], ry), row[9], fill=COLOR_DOWN, font=font_small)
        draw.text((idx_col_x[10], ry), row[10], fill=COLOR_UP, font=font_micro)
        draw.text((idx_col_x[11], ry), row[11], fill=COLOR_DOWN, font=font_micro)
        draw.text((idx_col_x[12], ry), row[12], fill=COLOR_ACCENT, font=font_micro)

    draw.text((70, curr_y + 280), "[注] 空间点位优先级：期权 Wall -> 筹码 POC 峰 -> ATR 波动率极限 (空间充沛判定：距 R1 空间 > 1.2% 且 距 S1 下方安全垫厚实)", fill=TEXT_MUTED, font=font_micro)

    curr_y += sec2_h + 20

    sec3_h = 420
    draw.rounded_rectangle([50, curr_y, W - 50, curr_y + sec3_h], radius=10, fill=BG_CARD, outline=BORDER_CARD, width=1)
    draw.text((70, curr_y + 16), "03 / 核心主线状态机、资金留存率与机会函数 Opportunity (Layer 2 机会探测)", fill=TEXT_H2, font=font_h2)

    sec_headers = ["主线板块", "状态机定位", "静态质量", "资金留存率", "拥挤度", "Opportunity", "领航龙头", "容量中军", "交易结构建议"]
    sec_col_x = [70, 210, 320, 415, 515, 600, 705, 840, 995]
    th_y = curr_y + 54
    for h, x in zip(sec_headers, sec_col_x):
        draw.text((x, th_y), h, fill=TEXT_MUTED, font=font_micro)
    draw.line([(65, th_y + 22), (W - 65, th_y + 22)], fill=DIVIDER, width=1)

    sectors_full = data.get("sectors_full", [
        ("半导体/算力硬件", "[强化期]", "92/100", "88%", "45 (健康)", "88 分 [极高]", "寒武纪 / 胜宏科技", "中际旭创 / 新易盛", "优先核心中军，等分歧放量承接"),
        ("农业种植/粮食安全", "[启动期]", "84/100", "92%", "22 (极低)", "82 分 [优质]", "万向德农 / 敦煌种业", "隆平高科 / 大北农", "放量突破，关注首板/20cm弹性"),
        ("基础化工/化肥农化", "[补涨期]", "76/100", "72%", "38 (中等)", "73 分 [良好]", "新赛股份 / 华尔泰", "盐湖股份 / 云天化", "逢高减仓高位，切低分歧低吸"),
        ("医药生物/创新药", "[弱化期]", "58/100", "42%", "68 (偏高)", "46 分 [观望]", "汉森制药 (炸板)", "恒瑞医药 / 药明康德", "资金持续流出，降低优先级回避")
    ])

    for row_idx, row in enumerate(sectors_full):
        ry = th_y + 28 + row_idx * 46
        if row_idx % 2 == 1:
            draw.rectangle([65, ry - 6, W - 65, ry + 36], fill=BG_ROW_ALT)
        draw.text((sec_col_x[0], ry), row[0], fill=TEXT_BODY, font=font_small)
        draw.text((sec_col_x[1], ry), row[1], fill=COLOR_ACCENT, font=font_small)
        draw.text((sec_col_x[2], ry), row[2], fill=TEXT_BODY, font=font_small)
        draw.text((sec_col_x[3], ry), row[3], fill=COLOR_WARN, font=font_small)
        draw.text((sec_col_x[4], ry), row[4], fill=COLOR_DOWN, font=font_micro)
        draw.text((sec_col_x[5], ry), row[5], fill=COLOR_UP, font=font_small)
        draw.text((sec_col_x[6], ry), row[6], fill=TEXT_BODY, font=font_micro)
        draw.text((sec_col_x[7], ry), row[7], fill=COLOR_ACCENT, font=font_micro)
        draw.text((sec_col_x[8], ry), row[8], fill=TEXT_MUTED, font=font_micro)

    sub_y = curr_y + 250
    draw.rounded_rectangle([70, sub_y, W - 70, sub_y + 150], radius=8, fill=BG_INNER, outline=BORDER_INNER, width=1)
    draw.text((90, sub_y + 14), "[产业链穿透] 第一核心主线 [半导体/算力] 上中下游全景映射", fill=TEXT_H2, font=font_h3)

    chain_details = [
        ("• 上游 (材料/设备/EDA)", "北方华创、中微公司、雅克科技 -> 资金温和放量布局，机构席位逆势加仓"),
        ("• 中游 (芯片/PCB/光模块)", "中际旭创 (成交280亿)、胜宏科技、新易盛 -> 产业链绝对爆发核心，流动性容量极佳"),
        ("• 下游 (算力服务器/AI应用)", "工业富联、浪潮信息、金山办公 -> 细分扩散良好，跟随中军稳步放量共振")
    ]
    for c_idx, (layer, desc) in enumerate(chain_details):
        cy = sub_y + 45 + c_idx * 32
        draw.text((90, cy), layer, fill=COLOR_ACCENT, font=font_small)
        draw.text((290, cy), desc, fill=TEXT_BODY, font=font_micro)

    curr_y += sec3_h + 20

    sec4_h = 320
    draw.rounded_rectangle([50, curr_y, W - 50, curr_y + sec4_h], radius=10, fill=BG_CARD, outline=BORDER_CARD, width=1)
    draw.text((70, curr_y + 16), "04 / 龙虎榜席位品质、筹码结构体检与实战交易结构设计", fill=TEXT_H2, font=font_h2)

    col_w = (W - 140 - 20) // 2

    draw.rounded_rectangle([70, curr_y + 55, 70 + col_w, curr_y + 295], radius=8, fill=BG_INNER, outline=BORDER_INNER, width=1)
    draw.text((90, curr_y + 70), "[席位筹码体检] 龙虎榜主力资金结构", fill=TEXT_H2, font=font_h3)

    seat_items = [
        ("[机构主力动态]", "20只个股上榜，嘉立创(净买2.53亿)、肯特股份(净买6989万)，中军锁仓良性"),
        ("[游资合力方向]", "深中华A(6板获游资接力)、楚天龙(5板)，高标题材情绪穿越"),
        ("[风险预警席位]", "汉森制药炸板后拉萨席位大额对倒；电子板块高位获利盘部分兑现，警惕接盘")
    ]
    for s_idx, (t, d) in enumerate(seat_items):
        sy = curr_y + 105 + s_idx * 58
        draw.text((90, sy), t, fill=COLOR_UP if "机构" in t else (COLOR_WARN if "游资" in t else COLOR_DOWN), font=font_small)
        draw.text((90, sy + 22), d, fill=TEXT_BODY, font=font_micro)

    rx = 70 + col_w + 20
    draw.rounded_rectangle([rx, curr_y + 55, rx + col_w, curr_y + 295], radius=8, fill=BG_INNER, outline=BORDER_INNER, width=1)
    draw.text((rx + 20, curr_y + 70), "[交易结构设计] 优先/等待/避免 & 止损纪律", fill=TEXT_H2, font=font_h3)

    exec_items = [
        ("【优先标的】", "第一主线容量中军 (中际旭创) + 政策低位先锋 (万向德农)"),
        ("【等待条件】", "早盘前15分钟分歧释放完毕，分时均线上方放量二次站稳"),
        ("【坚决避免】", "一致性超预期高开盲目无脑追涨；后排缺乏基本面支撑的跟风杂毛"),
        ("【证伪与退出】", "上证跌破 S1 (3800) 且30分钟无法收回，或龙头炸板跌停，坚决执行止损")
    ]
    for e_idx, (t, d) in enumerate(exec_items):
        ey = curr_y + 105 + e_idx * 45
        draw.text((rx + 20, ey), t, fill=COLOR_ACCENT if "优先" in t else (COLOR_WARN if "等待" in t else COLOR_UP), font=font_small)
        draw.text((rx + 120, ey), d, fill=TEXT_BODY, font=font_micro)

    curr_y += sec4_h + 20

    sec5_h = 320
    draw.rounded_rectangle([50, curr_y, W - 50, curr_y + sec5_h], radius=10, fill=BG_CARD, outline=BORDER_CARD, width=1)
    draw.text((70, curr_y + 16), "05 / 09:25 集合竞价贝叶斯更新 & 次日盘前重点跟踪矩阵 (Next Day Watchlist)", fill=TEXT_H2, font=font_h2)

    wl_headers = ["跟踪策略分类", "候选板块", "代表标的 (代码/名称)", "竞价量能/价格特征", "贝叶斯更新判定", "实战应对策略"]
    wl_col_x = [70, 240, 425, 600, 815, 985]
    th_y = curr_y + 54
    for h, x in zip(wl_headers, wl_col_x):
        draw.text((x, th_y), h, fill=TEXT_MUTED, font=font_micro)
    draw.line([(65, th_y + 22), (W - 65, th_y + 22)], fill=DIVIDER, width=1)

    watchlist_full = data.get("watchlist_full", [
        ("高低切潜力主线", "农业种植 / 化工农化", "万向德农 (600371)", "竞价爆量比 >= 5% 且高开 > 3%", "[强确认做多]", "开盘分歧放量承接时逢低介入"),
        ("产业趋势强化", "半导体 / 算力硬件", "中际旭创 (300308)", "平开或小幅高开, 量能温和换手", "[主升延续]", "回踩分时均线低吸中军"),
        ("老主线止跌观察", "电子元器件 / PCB", "胜宏科技 (300476)", "低开 < -2% 但快速放量翻红", "[分歧转一致]", "观察 30 分钟承接力再定买点"),
        ("高危回避方向", "高位连续加速题材", "汉森制药 (002412)", "竞价大额低开核按钮抛压", "[逻辑证伪退潮]", "坚决回避，逢盘中反抽坚决清仓")
    ])

    for row_idx, row in enumerate(watchlist_full):
        ry = th_y + 28 + row_idx * 52
        if row_idx % 2 == 1:
            draw.rectangle([65, ry - 6, W - 65, ry + 42], fill=BG_ROW_ALT)
        draw.text((wl_col_x[0], ry), row[0], fill=TEXT_BODY, font=font_small)
        draw.text((wl_col_x[1], ry), row[1], fill=COLOR_ACCENT, font=font_small)
        draw.text((wl_col_x[2], ry), row[2], fill=COLOR_WARN, font=font_small)
        draw.text((wl_col_x[3], ry), row[3], fill=TEXT_MUTED, font=font_micro)
        draw.text((wl_col_x[4], ry), row[4], fill=COLOR_UP if "强确认" in row[4] else (COLOR_WARN if "分歧" in row[4] else COLOR_DOWN), font=font_small)
        draw.text((wl_col_x[5], ry), row[5], fill=TEXT_BODY, font=font_micro)

    curr_y += sec5_h + 20

    sec6_h = 210
    draw.rounded_rectangle([50, curr_y, W - 50, curr_y + sec6_h], radius=10, fill=BG_CARD, outline=BORDER_CARD, width=1)
    draw.text((70, curr_y + 16), "06 / 模型元状态、失效预警与 20 日量化评估闭环 (Brier / Sharpness / Calibration)", fill=TEXT_H2, font=font_h2)

    eval_items_full = [
        ("模型当前置信度", "88 / 100 分", "证据链完整度极高", COLOR_ACCENT),
        ("20日三态方向准确率", "76.2%", "基准预测表现优良", COLOR_UP),
        ("多分类 Brier Score", "0.138", "概率校准度佳 (<0.15)", COLOR_WARN),
        ("预测锐度 (Sharpness)", "0.824", "区分度强 (敢于明确判断)", COLOR_UP),
        ("主线 Top1 命中率", "84.0%", "20日主线捕捉胜率高", COLOR_DOWN)
    ]
    eval_w = (W - 140 - 40) // 5
    for i, (l, v, sub, c) in enumerate(eval_items_full):
        ex = 70 + i * (eval_w + 10)
        ey = curr_y + 55
        draw.rounded_rectangle([ex, ey, ex + eval_w, ey + 95], radius=8, fill=BG_INNER, outline=BORDER_INNER, width=1)
        draw.text((ex + 10, ey + 12), l, fill=TEXT_MUTED, font=font_micro)
        draw.text((ex + 10, ey + 38), v, fill=c, font=get_font(20, bold=True))
        draw.text((ex + 10, ey + 68), sub, fill=TEXT_MUTED, font=get_font(12))

    draw.text((70, curr_y + 165), "[风险预警] 最可能导致今日推演失效的单点变量：若早盘 USDCNH 汇率突发急贬 > 200 点 或 领航龙头开盘 10 分钟遭巨额砸盘。", fill=COLOR_UP, font=font_micro)

    curr_y += sec6_h + 30

    draw.line([(50, curr_y), (W - 50, curr_y)], fill=DIVIDER, width=1)
    draw.text((50, curr_y + 15), "由 stock-prompt 量化研判引擎全自动推演生成 | GitHub 开源体系: Geekwls/stock-prompt", fill=TEXT_MUTED, font=font_small)
    draw.text((W - 380, curr_y + 15), "免责声明：仅供量化研究参考，不构成任何投资建议", fill=COLOR_UP, font=font_small)

    img.save(output_path, "PNG")
    print(f"Comprehensive report card generated: {os.path.abspath(output_path)}")
    return output_path

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="生成 A 股全量量化战报长图")
    parser.add_argument("--demo", action="store_true", help="生成全量示例长图")
    parser.add_argument("--type", type=str, default="prediction", choices=["prediction", "rotation", "daily"], help="卡片类型 (prediction/rotation/daily)")
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
        else:
            out_file = "demo_report_card.png"

    if args.type == "rotation":
        render_sector_rotation_card(output_path=out_file, theme=args.theme)
    elif args.type == "daily":
        render_daily_review_card(output_path=out_file, theme=args.theme)
    else:
        if args.demo or not args.json:
            render_report_card(output_path=out_file, theme=args.theme)
        else:
            with open(args.json, "r", encoding="utf-8") as f:
                data = json.load(f)
            render_report_card(data, output_path=out_file, theme=args.theme)
