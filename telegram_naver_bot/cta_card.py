# -*- coding: utf-8 -*-
"""캐러셀 마지막(5장) CTA 카드 — 한 번만 만들어서 계속 재사용하는 고정 카드.

사용법: python cta_card.py  →  cards/cta_follow.png 생성
"""
from PIL import Image, ImageDraw

import config
from card_news import (FALLBACK_BG, HILITE, SUBTEXT, WHITE, _brand_font,
                       _draw_youtube, _font)

W, H = 1080, 1350
M = 70


def main():
    config.CARDS_DIR.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (W, H), FALLBACK_BG)
    draw = ImageDraw.Draw(img)

    # 은은한 링 장식
    for cx, cy, radii in ((W - 80, 140, (140, 200, 260)), (60, H - 140, (110, 160, 210))):
        for r in radii:
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(40, 48, 62), width=2)

    cy = 300
    f_top = _font(True, 46)
    draw.text((W / 2, cy), "자동차산업 뉴스,", font=f_top, fill=WHITE, anchor="mm")
    cy += 78
    draw.text((W / 2, cy), "매일 카드로 정리해드려요", font=f_top, fill=WHITE, anchor="mm")

    # 팔로우 버튼 느낌의 필
    cy += 150
    f_btn = _font(True, 52)
    label = "+ 팔로우"
    bw = draw.textlength(label, font=f_btn)
    padx, bh = 56, 108
    x0 = (W - (bw + padx * 2)) / 2
    draw.rounded_rectangle([x0, cy - bh / 2, x0 + bw + padx * 2, cy + bh / 2],
                           radius=bh // 2, fill=(255, 61, 87))
    draw.text((W / 2, cy), label, font=f_btn, fill=WHITE, anchor="mm")

    cy += 170
    draw.text((W / 2, cy), "놓치면 아쉬운 산업 이슈와 취업 인사이트를", font=_font(False, 34),
              fill=SUBTEXT, anchor="mm")
    cy += 56
    draw.text((W / 2, cy), "제일 빠르게 받아보세요", font=_font(False, 34),
              fill=SUBTEXT, anchor="mm")

    # 유튜브 안내
    cy += 170
    brand = config.BRAND_NAME
    bf = _brand_font(52)
    icon_h = 46
    icon_w = round(icon_h * 1.42)
    gap = 18
    bw = draw.textlength(brand, font=bf)
    sx = (W - (icon_w + gap + bw)) / 2
    _draw_youtube(draw, sx, cy - icon_h / 2, icon_w, icon_h)
    draw.text((sx + icon_w + gap, cy), brand, font=bf, fill=WHITE, anchor="lm")
    cy += 80
    draw.text((W / 2, cy), "유튜브에서 현직자의 더 깊은 이야기를 만나요", font=_font(False, 32),
              fill=SUBTEXT, anchor="mm")

    # 하단 공유 유도 (폰트에 이모지 글리프가 없어 텍스트로만)
    draw.text((W / 2, H - 150), "저장해두고, 취준 친구에게 공유해주세요!",
              font=_font(True, 36), fill=HILITE, anchor="mm")

    path = config.CARDS_DIR / "cta_follow.png"
    img.save(path, "PNG")
    print(f"저장 완료: {path}")
    return path


if __name__ == "__main__":
    main()
