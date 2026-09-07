import os
from datetime import datetime

from PIL import Image, ImageDraw

from report_card.common import (
    draw_metric_cards, draw_pill, draw_score_bar, get_font, save_cropped_card,
)


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
        ("风险暴露等级", data.get("position", "积极观察"), COLOR_WARN),
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
