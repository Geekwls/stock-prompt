"""战报卡共享字体、指标卡和裁切辅助函数。"""

import os
import re

from PIL import ImageFont


def get_font(size=24, bold=False):
    font_candidates = [
        "C:\\Windows\\Fonts\\msyhbd.ttc" if bold else "C:\\Windows\\Fonts\\msyh.ttc",
        "C:\\Windows\\Fonts\\simhei.ttf",
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/arphic/uming.ttc",
    ]
    for path in font_candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def draw_pill(draw, text, xy, bg_color="#f1f5f9", text_color="#334155", font=None):
    font = font or get_font(14)
    bbox = font.getbbox(text)
    width = bbox[2] - bbox[0] + 16
    height = bbox[3] - bbox[1] + 8
    x, y = xy
    draw.rounded_rectangle([x, y, x + width, y + height], radius=4, fill=bg_color)
    draw.text((x + 8, y + 2), text, fill=text_color, font=font)
    return width, height


def score_ratio(value):
    match = re.search(r"(-?\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)", str(value))
    if not match:
        return None
    numerator, denominator = map(float, match.groups())
    if denominator <= 0:
        return None
    return max(0.0, min(1.0, numerator / denominator))


def draw_score_bar(draw, x, y, width, value, color, track_color):
    ratio = score_ratio(value)
    if ratio is None:
        return
    draw.rounded_rectangle([x, y, x + width, y + 5], radius=2, fill=track_color)
    if ratio > 0:
        draw.rounded_rectangle([x, y, x + max(5, int(width * ratio)), y + 5], radius=2, fill=color)


def draw_metric_cards(draw, metrics, width, y, bg_color, border_color, muted_color, font_label):
    gap = 10
    left = 60
    card_width = (width - 120 - gap * (len(metrics) - 1)) // len(metrics)
    for index, (label, value, color) in enumerate(metrics):
        x = left + index * (card_width + gap)
        draw.rounded_rectangle([x, y, x + card_width, y + 90], radius=8, fill=bg_color, outline=border_color, width=1)
        draw.text((x + 14, y + 12), label, fill=muted_color, font=font_label)
        value_text = str(value)
        for size in (19, 17, 15, 13):
            font_value = get_font(size, bold=True)
            bbox = font_value.getbbox(value_text)
            if bbox[2] - bbox[0] <= card_width - 24:
                break
        draw.text((x + 14, y + 38), value_text, fill=color, font=font_value)
        draw_score_bar(draw, x + 14, y + 77, card_width - 28, value, color, border_color)


def save_cropped_card(image, output_path, content_bottom, min_height=900):
    final_height = max(min_height, min(image.height, int(content_bottom)))
    image.crop((0, 0, image.width, final_height)).save(output_path, "PNG")
    return final_height

