# -*- coding: utf-8 -*-
"""카드뉴스 이미지 렌더링 (1080x1350, Pillow).

스타일: 기사 대표사진을 배경으로 깔고 어둡게 처리한 뒤,
하단에 그라데이션 + 흰색 볼드 헤드라인 2~3줄을 얹습니다.
사진이 없으면 브랜드 컬러 배경으로 대체합니다.

한글 폰트(Noto Sans CJK KR)는 최초 실행 시 fonts/ 폴더에 자동 다운로드됩니다.
"""
import io
import re
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

import config
from article import fetch_image_bytes

# 파일명 끝에 크기가 박힌 CDN(예: ..._290.jpg) 대응 — 더 큰 사이즈로 치환 시도
_SIZE_SUFFIX_RE = re.compile(r"(_)(\d{2,4})(\.\w+)(\?.*)?$")

W, H = 1080, 1350
MARGIN = 70

FALLBACK_BG = (16, 20, 28)   # #10141c — 사진 없을 때 배경
WHITE = (255, 255, 255)
SUBTEXT = (210, 214, 222)
ACCENT = (255, 61, 87)       # 포인트 레드 (카테고리 태그)
HILITE = (255, 224, 82)      # 형광펜/포인트 옐로 (핵심 강조)
DARK = (20, 20, 20)

FONT_SOURCES = {
    "NotoSansCJKkr-Bold.otf": [
        "https://github.com/notofonts/noto-cjk/raw/main/Sans/OTF/Korean/NotoSansCJKkr-Bold.otf",
        "https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/OTF/Korean/NotoSansCJKkr-Bold.otf",
    ],
    "NotoSansCJKkr-Regular.otf": [
        "https://github.com/notofonts/noto-cjk/raw/main/Sans/OTF/Korean/NotoSansCJKkr-Regular.otf",
        "https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/OTF/Korean/NotoSansCJKkr-Regular.otf",
    ],
    # 브랜드명 전용 — 주아체(귀엽고 친근한 폰트)
    "Jua-Regular.ttf": [
        "https://raw.githubusercontent.com/google/fonts/main/ofl/jua/Jua-Regular.ttf",
        "https://github.com/google/fonts/raw/main/ofl/jua/Jua-Regular.ttf",
    ],
}
BRAND_FONT_FILE = "Jua-Regular.ttf"


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


def _brand_font(size: int) -> ImageFont.FreeTypeFont:
    """브랜드명 전용 폰트(주아체). 실패 시 기본 볼드로 대체."""
    try:
        return ImageFont.truetype(str(_ensure_font(BRAND_FONT_FILE)), size)
    except Exception as e:
        print(f"[card_news] 브랜드 폰트 로드 실패, 기본 폰트 사용: {e}")
        return _font(True, size)


# 원본이 이보다 작으면 억지로 늘려 쓰지 않고 깔끔한 단색 배경으로 대체
MIN_SOURCE_WIDTH = 640
MIN_SOURCE_HEIGHT = 500


def _size_suffix_variants(url: str) -> list:
    """'..._290.jpg' 처럼 파일명 끝에 크기가 박힌 CDN URL 에서, 더 큰 사이즈 후보를 만든다."""
    m = _SIZE_SUFFIX_RE.search(url)
    if not m:
        return []
    cur = int(m.group(2))
    variants = []
    for size in (720, 960, 1200):
        if size > cur:
            variants.append(url[:m.start(2)] + str(size) + url[m.end(2):])
    return variants


def _download(url: str, referer: str) -> Image.Image:
    try:
        raw = fetch_image_bytes(url, referer=referer)
        return Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception as e:
        print(f"[card_news] 이미지 다운로드 실패({url}): {e}")
        return None


def _fetch_one_image(url: str, referer: str) -> Image.Image:
    """이미지를 받아 화질 기준을 통과하면 1080x1350 cover 크롭, 아니면 None.

    파일명에 크기가 박힌 CDN(예: ..._290.jpg)이면 더 큰 사이즈를 자동으로 시도한다."""
    img = _download(url, referer)
    if img is not None and (img.width < MIN_SOURCE_WIDTH or img.height < MIN_SOURCE_HEIGHT):
        print(f"[card_news] 이미지 해상도가 낮아({img.width}x{img.height}) — 더 큰 사이즈 시도: {url}")
        for bigger_url in _size_suffix_variants(url):
            bigger = _download(bigger_url, referer)
            if bigger is not None and bigger.width >= MIN_SOURCE_WIDTH and bigger.height >= MIN_SOURCE_HEIGHT:
                img = bigger
                break
        else:
            img = None

    if img is None:
        return None
    if img.width < MIN_SOURCE_WIDTH or img.height < MIN_SOURCE_HEIGHT:
        print(f"[card_news] 이미지 해상도가 낮아({img.width}x{img.height}) 건너뜀: {url}")
        return None

    scale = max(W / img.width, H / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    left = (img.width - W) // 2
    top = (img.height - H) // 2
    return img.crop((left, top, left + W, top + H))


def load_backgrounds(article: dict, count: int) -> list:
    """카드 수만큼 배경 이미지를 준비합니다.

    기사에서 찾은 사진 후보(image_urls)를 화질 기준으로 걸러 순서대로 시도하고,
    카드가 여러 장이면 서로 다른 사진을 배정합니다(사진이 부족하면 마지막 것을 반복).
    쓸 만한 사진이 하나도 없으면 전부 None(→ 단색 배경 폴백)을 반환합니다.
    """
    article = article or {}
    candidates = list(dict.fromkeys(article.get("image_urls") or
                                    ([article["image_url"]] if article.get("image_url") else [])))
    referer = article.get("url", "")

    good = []
    for url in candidates:
        img = _fetch_one_image(url, referer)
        if img is not None:
            good.append(img)
        if len(good) >= count:
            break

    if not good:
        return [None] * count
    return [good[min(i, len(good) - 1)] for i in range(count)]


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


def _emphasize(line: str, highlight: str) -> bool:
    """이 줄이 강조 대상인지 — highlight 와 겹치면 True."""
    line, highlight = line.strip(), (highlight or "").strip()
    if not highlight or not line:
        return False
    return highlight in line or line in highlight


def _draw_card(card, background: Image.Image, source: str,
               index: int, total: int) -> Image.Image:
    headline = card.get("headline") or card.get("title", "")
    tag = (card.get("tag") or "").strip()
    highlight = card.get("highlight") or ""
    style = card.get("style") or "marker"

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
    line_gap = 106

    # 하단 요소들의 세로 중앙 기준선
    footer_cy = H - 74

    # ── 상단 카테고리 태그(알약) ──
    if tag:
        _draw_tag(draw, MARGIN, 150, tag[:6])

    # ── 헤드라인 (하단 정렬, 살짝 위로 — 단 화면 중앙보다는 아래) ──
    lines = _wrap(draw, headline, headline_font, W - MARGIN * 2)[:4]
    text_bottom = footer_cy - 140
    y = text_bottom - len(lines) * line_gap
    for line in lines:
        emph = _emphasize(line, highlight)
        if emph and style == "marker":
            # 형광펜: 노란 박스 위에 어두운 글씨
            tw = draw.textlength(line, font=headline_font)
            draw.rounded_rectangle([MARGIN - 8, y + 14, MARGIN + tw + 18, y + 96],
                                   radius=10, fill=HILITE)
            draw.text((MARGIN, y), line, font=headline_font, fill=DARK)
        elif emph:
            # 포인트 컬러 글씨 (그림자로 가독성 확보)
            draw.text((MARGIN + 3, y + 3), line, font=headline_font, fill=(0, 0, 0))
            draw.text((MARGIN, y), line, font=headline_font, fill=HILITE)
        else:
            draw.text((MARGIN + 3, y + 3), line, font=headline_font, fill=(0, 0, 0))
            draw.text((MARGIN, y), line, font=headline_font, fill=WHITE)
        y += line_gap

    # ── 하단: 출처(좌) · 유튜브로고+브랜드(중앙) · 페이지(우) ──
    # anchor 로 세로 중앙(middle) 정렬해 로고와 글자 높이를 맞춘다
    src_font = _font(False, 24)
    if source:
        draw.text((MARGIN, footer_cy), f"@{source}"[:20], font=src_font,
                  fill=SUBTEXT, anchor="lm")
    if total > 1:
        page = f"{index + 1}/{total}"
        draw.text((W - MARGIN, footer_cy), page, font=src_font,
                  fill=SUBTEXT, anchor="rm")

    # 유튜브 로고 + 브랜드명 (하단 중앙, 세로 중앙 정렬) — 주아체
    brand = config.BRAND_NAME
    brand_font = _brand_font(32)   # 주아체는 같은 pt 에서 조금 작아 살짝 키움
    icon_h = 26
    icon_w = round(icon_h * 1.42)   # 유튜브 로고 가로:세로 ≈ 1.42
    gap = 11
    bw = draw.textlength(brand, font=brand_font)
    total_w = icon_w + gap + bw
    sx = (W - total_w) / 2
    _draw_youtube(draw, sx, footer_cy - icon_h / 2, icon_w, icon_h)
    draw.text((sx + icon_w + gap, footer_cy), brand, font=brand_font,
              fill=WHITE, anchor="lm")

    return img


def _draw_tag(draw: ImageDraw.ImageDraw, x, y, text: str):
    """상단 카테고리 태그(알약 모양)."""
    f = _brand_font(30)
    tw = draw.textlength(text, font=f)
    padx, h = 24, 52
    draw.rounded_rectangle([x, y, x + tw + padx * 2, y + h], radius=h // 2, fill=ACCENT)
    draw.text((x + padx, y + h / 2), text, font=f, fill=WHITE, anchor="lm")


def _draw_youtube(draw: ImageDraw.ImageDraw, x, y, w, h):
    """유튜브 로고(빨간 라운드 사각형 + 흰 재생 삼각형)를 그립니다."""
    draw.rounded_rectangle([x, y, x + w, y + h], radius=int(h * 0.28), fill=(255, 0, 0))
    tri = [
        (x + w * 0.40, y + h * 0.28),
        (x + w * 0.40, y + h * 0.72),
        (x + w * 0.64, y + h * 0.50),
    ]
    draw.polygon(tri, fill=(255, 255, 255))


def render_cards(cards: list, article: dict, out_prefix: str) -> list:
    """카드 목록을 PNG 로 렌더링하고 파일 경로 목록을 반환합니다."""
    config.CARDS_DIR.mkdir(parents=True, exist_ok=True)
    total = len(cards)
    backgrounds = load_backgrounds(article, total)
    source = (article or {}).get("source") or (article or {}).get("site", "")
    paths = []
    for i, card in enumerate(cards):
        img = _draw_card(card, backgrounds[i], source, i, total)
        path = config.CARDS_DIR / f"{out_prefix}_{i + 1}.png"
        img.save(path, "PNG")
        paths.append(path)
    return paths
