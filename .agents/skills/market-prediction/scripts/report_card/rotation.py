import os
from datetime import datetime

from PIL import Image, ImageDraw

from report_card.common import (
    draw_metric_cards, draw_pill, draw_score_bar, get_font, save_cropped_card,
)


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
