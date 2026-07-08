# -*- coding: utf-8 -*-
"""카드뉴스 이미지 렌더링 (1080x1080, Pillow).

한글 폰트(Noto Sans CJK KR)는 최초 실행 시 fonts/ 폴더에 자동 다운로드됩니다.
"""
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

import config

W, H = 1080, 1080
MARGIN = 90

BG = (16, 20, 28)          # #10141c — 잡앤유 다크 네이비
ACCENT = (47, 111, 237)    # #2f6fed — 브랜드 블루
TEXT = (245, 247, 250)
SUBTEXT = (174, 182, 196)

FONT_SOURCES = {
    "NotoSansCJKkr-Bold.otf": [
        "https://github.com/notofonts/noto-cjk/raw/main/Sans/OTF/Korean/NotoSansCJKkr-Bold.otf",
        "https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/OTF/Korean/NotoSansCJKkr-Bold.otf",
    ],
    "NotoSansCJKkr-Regular.otf": [
        "https://github.com/notofonts/noto-cjk/raw/main/Sans/OTF/Korean/NotoSansCJKkr-Regular.otf",
        "https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/OTF/Korean/NotoSansCJKkr-Regular.otf",
    ],
}


def _ensure_font(name: str) -> Path:
    config.FONTS_DIR.mkdir(parents=True, exist_ok=True)
    path = config.FONTS_DIR / name
    if path.exists() and path.stat().st_size > 1_000_000:
        return path
    last_err = None
    for url in FONT_SOURCES[name]:
        try:
            print(f"[card_news] 폰트 다운로드: {url}")
            r = requests.get(url, timeout=120)
            r.raise_for_status()
            path.write_bytes(r.content)
            return path
        except Exception as e:
            last_err = e
    raise RuntimeError(f"한글 폰트 다운로드 실패 — {name} 을 {config.FONTS_DIR} 에 직접 넣어주세요: {last_err}")


def _font(bold: bool, size: int) -> ImageFont.FreeTypeFont:
    name = "NotoSansCJKkr-Bold.otf" if bold else "NotoSansCJKkr-Regular.otf"
    return ImageFont.truetype(str(_ensure_font(name)), size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list:
    """한글은 글자 단위 줄바꿈 (픽셀 폭 기준)."""
    lines, cur = [], ""
    for ch in text:
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        if cur and draw.textlength(cur + ch, font=font) > max_width:
            lines.append(cur)
            cur = ch.lstrip()
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


def _draw_card(card: dict, source: str, index: int, total: int) -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    kicker_font = _font(True, 34)
    title_font = _font(True, 76)
    bullet_font = _font(False, 44)
    footer_font = _font(True, 36)
    max_width = W - MARGIN * 2

    # 좌측 상단 악센트 바 + 출처
    draw.rectangle([MARGIN, MARGIN, MARGIN + 14, MARGIN + 44], fill=ACCENT)
    draw.text((MARGIN + 36, MARGIN), (source or "NEWS")[:40], font=kicker_font, fill=ACCENT)

    # 헤드라인
    y = MARGIN + 110
    for line in _wrap(draw, card.get("title", ""), title_font, max_width)[:4]:
        draw.text((MARGIN, y), line, font=title_font, fill=TEXT)
        y += 100

    # 구분선
    y += 24
    draw.line([MARGIN, y, W - MARGIN, y], fill=(60, 68, 84), width=2)
    y += 50

    # 핵심 포인트
    footer_top = H - MARGIN - 60
    for bullet in card.get("bullets", [])[:4]:
        lines = _wrap(draw, bullet, bullet_font, max_width - 56)
        if y + len(lines) * 64 > footer_top - 20:
            break
        draw.ellipse([MARGIN + 4, y + 20, MARGIN + 22, y + 38], fill=ACCENT)
        for line in lines:
            draw.text((MARGIN + 56, y), line, font=bullet_font, fill=SUBTEXT)
            y += 64
        y += 22

    # 하단 브랜드 + 페이지 표시
    draw.text((MARGIN, footer_top), config.BRAND_NAME, font=footer_font, fill=TEXT)
    page = f"{index + 1} / {total}"
    page_w = draw.textlength(page, font=footer_font)
    draw.text((W - MARGIN - page_w, footer_top), page, font=footer_font, fill=SUBTEXT)

    return img


def render_cards(cards: list, source: str, out_prefix: str) -> list:
    """카드 목록을 PNG 로 렌더링하고 파일 경로 목록을 반환합니다."""
    config.CARDS_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    total = len(cards)
    for i, card in enumerate(cards):
        img = _draw_card(card, source, i, total)
        path = config.CARDS_DIR / f"{out_prefix}_{i + 1}.png"
        img.save(path, "PNG")
        paths.append(path)
    return paths
