# -*- coding: utf-8 -*-
"""카드뉴스 이미지 렌더링 (1080x1350, Pillow).

스타일: 기사 대표사진을 배경으로 깔고 어둡게 처리한 뒤,
하단에 그라데이션 + 흰색 볼드 헤드라인 2~3줄을 얹습니다.
사진이 없으면 브랜드 컬러 배경으로 대체합니다.

한글 폰트(Noto Sans CJK KR)는 최초 실행 시 fonts/ 폴더에 자동 다운로드됩니다.
"""
import io
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import config
from article import fetch_image_bytes

W, H = 1080, 1350
MARGIN = 70

FALLBACK_BG = (16, 20, 28)   # #10141c — 사진 없을 때 배경
WHITE = (255, 255, 255)
SUBTEXT = (210, 214, 222)

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
            if len(r.content) < 1_000_000:  # LFS 포인터 등 비정상 응답 방지
                raise RuntimeError(f"파일이 너무 작음 ({len(r.content)} bytes)")
            path.write_bytes(r.content)
            return path
        except Exception as e:
            last_err = e
    raise RuntimeError(f"한글 폰트 다운로드 실패 — {name} 을 {config.FONTS_DIR} 에 직접 넣어주세요: {last_err}")


def _font(bold: bool, size: int) -> ImageFont.FreeTypeFont:
    name = "NotoSansCJKkr-Bold.otf" if bold else "NotoSansCJKkr-Regular.otf"
    return ImageFont.truetype(str(_ensure_font(name)), size)


def _load_background(article: dict) -> Image.Image:
    """기사 대표사진을 1080x1350 에 꽉 차게(cover) 크롭. 실패 시 None."""
    image_url = (article or {}).get("image_url")
    if not image_url:
        return None
    try:
        raw = fetch_image_bytes(image_url, referer=article.get("url", ""))
        img = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception as e:
        print(f"[card_news] 대표사진 다운로드 실패({image_url}): {e}")
        return None

    # cover 크롭
    scale = max(W / img.width, H / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    left = (img.width - W) // 2
    top = (img.height - H) // 2
    img = img.crop((left, top, left + W, top + H))

    # 원본이 너무 작아 화질이 깨지면 살짝 블러로 완화
    if scale > 2.5:
        img = img.filter(ImageFilter.GaussianBlur(2))
    return img


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list:
    """이미 \\n 이 있으면 그대로 쓰고, 넘치는 줄만 글자 단위로 추가 줄바꿈."""
    lines = []
    for para in (text or "").split("\n"):
        cur = ""
        for ch in para:
            if cur and draw.textlength(cur + ch, font=font) > max_width:
                lines.append(cur)
                cur = ch.lstrip()
            else:
                cur += ch
        lines.append(cur)
    return [ln for ln in lines if ln != ""] or [""]


def _draw_card(headline: str, background: Image.Image, source: str,
               index: int, total: int) -> Image.Image:
    img = background.copy() if background is not None else Image.new("RGB", (W, H), FALLBACK_BG)
    if img.size != (W, H):
        img = img.resize((W, H), Image.LANCZOS)

    # ── 어둡게 + 하단 그라데이션 (텍스트 가독성) ──
    overlay = Image.new("L", (W, H), 60)  # 전체 약 24% 어둡게
    grad_top = int(H * 0.45)
    for y in range(grad_top, H):
        t = (y - grad_top) / (H - grad_top)
        overlay.paste(int(60 + t * 150), (0, y, W, y + 1))  # 하단으로 갈수록 최대 ~82%
    img = Image.composite(Image.new("RGB", (W, H), (0, 0, 0)), img, overlay)

    draw = ImageDraw.Draw(img)
    headline_font = _font(True, 78)
    footer_font = _font(True, 34)
    line_gap = 106

    # ── 헤드라인 (하단 정렬) ──
    lines = _wrap(draw, headline, headline_font, W - MARGIN * 2)[:4]
    footer_y = H - 96
    text_bottom = footer_y - 40
    y = text_bottom - len(lines) * line_gap
    for line in lines:
        # 살짝 그림자를 깔아 밝은 사진에서도 읽히게
        draw.text((MARGIN + 3, y + 3), line, font=headline_font, fill=(0, 0, 0))
        draw.text((MARGIN, y), line, font=headline_font, fill=WHITE)
        y += line_gap

    # ── 하단 중앙 브랜드, (여러 장일 때) 우측 페이지 표시 ──
    brand = config.BRAND_NAME
    bw = draw.textlength(brand, font=footer_font)
    draw.text(((W - bw) / 2, footer_y), brand, font=footer_font, fill=WHITE)
    if total > 1:
        page = f"{index + 1}/{total}"
        pw = draw.textlength(page, font=footer_font)
        draw.text((W - MARGIN - pw, footer_y), page, font=footer_font, fill=SUBTEXT)
    if source:
        draw.text((MARGIN, footer_y), source[:20], font=footer_font, fill=SUBTEXT)

    return img


def render_cards(cards: list, article: dict, out_prefix: str) -> list:
    """카드 목록을 PNG 로 렌더링하고 파일 경로 목록을 반환합니다."""
    config.CARDS_DIR.mkdir(parents=True, exist_ok=True)
    background = _load_background(article)
    source = (article or {}).get("site", "")
    paths = []
    total = len(cards)
    for i, card in enumerate(cards):
        headline = card.get("headline") or card.get("title", "")
        img = _draw_card(headline, background, source, i, total)
        path = config.CARDS_DIR / f"{out_prefix}_{i + 1}.png"
        img.save(path, "PNG")
        paths.append(path)
    return paths
