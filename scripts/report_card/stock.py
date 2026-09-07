import os
from datetime import datetime

from PIL import Image, ImageDraw

from report_card.common import (
    draw_metric_cards, draw_pill, draw_score_bar, get_font, save_cropped_card,
)


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
        ("公司风险", data.get("company_risk_status", "N/A"), COLOR_WARN),
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
        ["公司质量", "N/A [待补数据]"]
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
