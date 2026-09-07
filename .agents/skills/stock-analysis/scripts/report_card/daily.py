import os
from datetime import datetime

from PIL import Image, ImageDraw

from report_card.common import (
    draw_metric_cards, draw_pill, draw_score_bar, get_font, save_cropped_card,
)


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
        ("风险暴露导向", "积极观察，重点验证核心主线分歧承接")
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
    draw.text((60, curr_y), data.get("opportunity_line", "[机会定调] Opportunity Score: 86 / 100 分  |  生命周期: [强化期]  |  风险暴露: 积极观察"), fill=TEXT_MAIN, font=font_h3)
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
