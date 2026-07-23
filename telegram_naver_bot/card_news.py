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
from PIL import Image, ImageDraw, ImageFilter, ImageFont

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
    # 채용카드 제목용 — 도현체(익숙하고 시원한 제목 폰트, 배민 도현)
    "DoHyeon-Regular.ttf": [
        "https://raw.githubusercontent.com/google/fonts/main/ofl/dohyeon/DoHyeon-Regular.ttf",
        "https://github.com/google/fonts/raw/main/ofl/dohyeon/DoHyeon-Regular.ttf",
    ],
}
BRAND_FONT_FILE = "Jua-Regular.ttf"


def _ensure_font(name: str) -> Path:
    config.FONTS_DIR.mkdir(parents=True, exist_ok=True)
    path = config.FONTS_DIR / name
    if path.exists() and path.stat().st_size > 100_000:
        return path
    last_err = None
    for url in FONT_SOURCES[name]:
        try:
            print(f"[card_news] 폰트 다운로드: {url}")
            r = requests.get(url, timeout=120)
            r.raise_for_status()
            if len(r.content) < 100_000:  # LFS 포인터 등 비정상 응답 방지
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


# 이 크기 이상이면 선명하게(블러 없이) 사용
SHARP_MIN_WIDTH = 640
SHARP_MIN_HEIGHT = 500
# 이 크기 미만이면 아이콘/로고급으로 보고 아예 배경으로 쓰지 않음
HARD_MIN_WIDTH = 220
HARD_MIN_HEIGHT = 160


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


def _cover_crop(img: Image.Image) -> Image.Image:
    scale = max(W / img.width, H / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    left = (img.width - W) // 2
    top = (img.height - H) // 2
    return img.crop((left, top, left + W, top + H)), scale


def _fetch_one_image(url: str, referer: str) -> Image.Image:
    """이미지를 받아 배경으로 다듬어 반환. 실패/너무 작으면(아이콘급) None.

    - SHARP 기준(가로640·세로500) 이상: 선명하게 그대로 사용
    - 그보다 작지만 HARD 기준(220x160) 이상: 파일명에 크기가 박힌 CDN이면 더 큰 사이즈를
      먼저 시도하고, 그래도 작으면 화질 저하를 감추기 위해 의도적으로 블러 처리한
      '무드 배경'으로 사용 (요즘 카드뉴스에서 흔한 스타일)
    - HARD 기준 미만(아이콘/로고 크기): 배경으로 쓰지 않음
    """
    img = _download(url, referer)
    if img is None:
        return None

    if img.width < HARD_MIN_WIDTH or img.height < HARD_MIN_HEIGHT:
        print(f"[card_news] 이미지가 너무 작아({img.width}x{img.height}) 건너뜀: {url}")
        return None

    if img.width < SHARP_MIN_WIDTH or img.height < SHARP_MIN_HEIGHT:
        # 더 큰 버전이 있는지 먼저 시도
        for bigger_url in _size_suffix_variants(url):
            bigger = _download(bigger_url, referer)
            if bigger is not None and bigger.width >= SHARP_MIN_WIDTH and bigger.height >= SHARP_MIN_HEIGHT:
                img = bigger
                break

    cropped, _scale = _cover_crop(img)
    return cropped


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


_NO_LINE_START = ",.!?%)]」』”’·~…"   # 줄 맨 앞에 오면 어색한 문장부호


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list:
    """이미 \\n 이 있으면 그대로 쓰고, 넘치는 줄만 글자 단위로 추가 줄바꿈.
    문장부호가 줄 맨 앞에 오지 않도록 직전 줄에 붙인다."""
    lines = []
    for para in (text or "").split("\n"):
        cur = ""
        for ch in para:
            if cur and draw.textlength(cur + ch, font=font) > max_width:
                if ch in _NO_LINE_START:   # 부호는 넘치더라도 이번 줄 끝에 붙이고 줄바꿈
                    lines.append(cur + ch)
                    cur = ""
                    continue
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


def _apply_graduated_blur_dark(img: Image.Image, ramp_top: int, ramp_bottom: int) -> Image.Image:
    """ramp_top 위쪽은 원본 그대로(선명·안 어두움), ramp_top~ramp_bottom 구간에서
    블러와 어둡기가 함께 강해지고, ramp_bottom 아래는 최대 블러+어둡기를 유지한다."""
    ramp_top = max(0, min(H, ramp_top))
    ramp_bottom = max(ramp_top + 1, min(H, ramp_bottom))

    blurred = img.filter(ImageFilter.GaussianBlur(16))
    blur_mask = Image.new("L", (W, H), 0)
    dark_mask = Image.new("L", (W, H), 0)
    DARK_MAX = 210
    for y in range(H):
        if y < ramp_top:
            bv, dv = 0, 0
        elif y > ramp_bottom:
            bv, dv = 255, DARK_MAX
        else:
            t = (y - ramp_top) / (ramp_bottom - ramp_top)
            bv, dv = int(255 * t), int(DARK_MAX * t)
        blur_mask.paste(bv, (0, y, W, y + 1))
        dark_mask.paste(dv, (0, y, W, y + 1))

    img = Image.composite(blurred, img, blur_mask)
    img = Image.composite(Image.new("RGB", (W, H), (0, 0, 0)), img, dark_mask)
    return img


def _draw_card(card, background: Image.Image, source: str,
               index: int, total: int) -> Image.Image:
    headline = card.get("headline") or card.get("title", "")
    tag = (card.get("tag") or "").strip()
    highlight = card.get("highlight") or ""
    style = card.get("style") or "marker"

    img = background.copy() if background is not None else Image.new("RGB", (W, H), FALLBACK_BG)
    if img.size != (W, H):
        img = img.resize((W, H), Image.LANCZOS)

    headline_font = _font(True, 78)
    line_gap = 106
    footer_cy = H - 74  # 하단 요소들의 세로 중앙 기준선

    # 헤드라인 위치를 먼저 계산 — 배경의 블러/어둡기 시작 지점을 여기 맞추기 위해
    measure_draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    lines = _wrap(measure_draw, headline, headline_font, W - MARGIN * 2)[:4]
    text_bottom = footer_cy - 140
    text_top = text_bottom - len(lines) * line_gap

    # ── 상단은 선명하게, 글자 쪽으로 내려올수록 블러+어둡게 ──
    img = _apply_graduated_blur_dark(img, ramp_top=text_top - 110, ramp_bottom=text_top + 60)

    draw = ImageDraw.Draw(img)

    # ── 상단 카테고리 태그(알약) ──
    if tag:
        _draw_tag(draw, MARGIN, 150, tag[:6])

    # ── 헤드라인 ──
    y = text_top
    for line in lines:
        emph = _emphasize(line, highlight)
        if emph and style == "marker":
            # 형광펜: 실제 글자 잉크 영역(textbbox) 기준으로 위아래 여백을 동일하게
            bbox = draw.textbbox((MARGIN, y), line, font=headline_font)
            pad_x, pad_y = 12, 14
            draw.rectangle([bbox[0] - pad_x, bbox[1] - pad_y, bbox[2] + pad_x, bbox[3] + pad_y],
                          fill=HILITE)  # 직각 모서리
            draw.text((MARGIN, y), line, font=headline_font, fill=DARK)
        elif emph:
            # 포인트 컬러 글씨 (그림자로 가독성 확보)
            draw.text((MARGIN + 3, y + 3), line, font=headline_font, fill=(0, 0, 0))
            draw.text((MARGIN, y), line, font=headline_font, fill=HILITE)
        else:
            draw.text((MARGIN + 3, y + 3), line, font=headline_font, fill=(0, 0, 0))
            draw.text((MARGIN, y), line, font=headline_font, fill=WHITE)
        y += line_gap

    _draw_footer(draw, source, footer_cy)

    return img


def _draw_footer(draw: ImageDraw.ImageDraw, source: str, footer_cy: int):
    """하단 공통 footer — 출처(좌) · 유튜브로고+브랜드(중앙). 모든 장에서 재사용."""
    src_font = _font(False, 24)
    if source:
        draw.text((MARGIN, footer_cy), f"@{source}"[:20], font=src_font,
                  fill=SUBTEXT, anchor="lm")

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


# ── 캐러셀 2~4장 (요약 / 취준생 인사이트 / 면접 활용) ──────────

CAROUSEL_TOTAL = 5   # 인스타 캐러셀 총 장수 (5장 = 1후킹 + 2요약 + 3인사이트 + 4면접 + 5CTA)


def _content_bg(background: Image.Image) -> Image.Image:
    """2~4장 배경 — 1장과 같은 사진을 강하게 블러 + 전체적으로 어둡게."""
    img = background.copy() if background is not None else Image.new("RGB", (W, H), FALLBACK_BG)
    if img.size != (W, H):
        img = img.resize((W, H), Image.LANCZOS)
    if background is not None:
        img = img.filter(ImageFilter.GaussianBlur(18))
        img = Image.blend(img, Image.new("RGB", (W, H), (0, 0, 0)), 0.66)
    return img


_HL_RE = re.compile(r"\{\{(.+?)\}\}")


def _extract_highlight_spans(text: str):
    """{{...}} 마커를 제거한 평문과, 그 안에서 강조할 (start,end) 구간 목록을 반환.
    AI 가 정말 중요하다고 고른 곳만(보통 1~2곳) 강조하기 위함 — 숫자 전체를
    기계적으로 강조하던 이전 방식(_NUM_RE)을 대체."""
    parts, spans, pos, offset = [], [], 0, 0
    for m in _HL_RE.finditer(text or ""):
        pre = text[pos:m.start()]
        parts.append(pre)
        offset += len(pre)
        inner = m.group(1)
        spans.append((offset, offset + len(inner)))
        parts.append(inner)
        offset += len(inner)
        pos = m.end()
    parts.append(text[pos:])
    return "".join(parts), spans


def _wrap_keep(draw, text, font, max_width):
    """오프셋을 보존하는 줄바꿈(문자 손실 없음) — 강조 구간을 줄 단위로 매핑하기 위함.
    공백 근처에서 끊되, 그 공백은 버리지 않고 이번 줄 끝에 포함시킨다."""
    lines, cur = [], ""
    for ch in text:
        if cur and draw.textlength(cur + ch, font=font) > max_width:
            sp = cur.rfind(" ")
            if sp > 0 and len(cur) - sp <= 14:
                lines.append(cur[:sp + 1])
                cur = cur[sp + 1:] + ch
            else:
                lines.append(cur)
                cur = ch
        else:
            cur += ch
    lines.append(cur)
    return lines


def _draw_marked_paragraph(draw, x, y, text, font, max_width, gap, max_lines=16):
    """{{...}} 로 감싼 구간만 노란색으로, 나머지는 흰색으로 그리며 줄바꿈해서 그린다."""
    plain, spans = _extract_highlight_spans(text)
    lines = _wrap_keep(draw, plain, font, max_width)[:max_lines]
    offset = 0
    for line in lines:
        s, e = offset, offset + len(line)
        overlaps = sorted((max(a, s) - s, min(b, e) - s) for a, b in spans if max(a, s) < min(b, e))
        cx, pos = x, 0
        for a, b in overlaps:
            if a > pos:
                draw.text((cx, y), line[pos:a], font=font, fill=WHITE)
                cx += draw.textlength(line[pos:a], font=font)
            draw.text((cx, y), line[a:b], font=font, fill=HILITE)
            cx += draw.textlength(line[a:b], font=font)
            pos = b
        if pos < len(line):
            draw.text((cx, y), line[pos:], font=font, fill=WHITE)
        y += gap
        offset = e
    return lines


def _draw_panel(img: Image.Image, box, radius=22):
    """반투명 유리 패널 — 내용을 묶어서 '디자인된' 느낌을 준다."""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    d.rounded_rectangle(box, radius=radius, fill=(255, 255, 255, 22),
                        outline=(255, 255, 255, 48), width=2)
    img.alpha_composite(overlay)


def _draw_check(draw, x, y, size=34):
    """체크마크 (폰트 이모지 대신 직접 그림)."""
    draw.line([(x + 6, y + size * 0.55), (x + size * 0.38, y + size * 0.85),
               (x + size * 0.92, y + size * 0.12)], fill=HILITE, width=7, joint="curve")


def _slide_frame(background, page: int, label: str, title: str, source: str):
    """콘텐츠 장 공통 틀: 배경 + 페이지표시 + 라벨 칩 + 큰 제목 + 포인트 바 + footer.
    returns (img(RGBA), draw, 본문 시작 y)"""
    img = _content_bg(background).convert("RGBA")
    draw = ImageDraw.Draw(img)

    draw.text((W - MARGIN, 78), f"{page}/{CAROUSEL_TOTAL}", font=_font(False, 30),
              fill=SUBTEXT, anchor="ra")

    f_chip = _brand_font(32)
    tw = draw.textlength(label, font=f_chip)
    padx, ch = 26, 56
    draw.rounded_rectangle([MARGIN, 140, MARGIN + tw + padx * 2, 140 + ch],
                           radius=ch // 2, fill=ACCENT)
    draw.text((MARGIN + padx, 140 + ch / 2), label, font=f_chip, fill=WHITE, anchor="lm")

    draw.text((MARGIN, 230), title, font=_font(True, 58), fill=WHITE)
    draw.rectangle([MARGIN + 4, 318, MARGIN + 108, 327], fill=HILITE)   # 제목 아래 포인트 바

    _draw_footer(draw, source, H - 74)
    return img, draw, 380


def _slide_summary(background, summary: str, page: int, source: str) -> Image.Image:
    """2장 — 풀 요약을 이어지는 문단으로 하나의 유리 패널에 담는다 (크기 자동 축소)."""
    img, draw, y = _slide_frame(background, page, "핵심 요약", "한눈에 보는 핵심", source)
    # 문장들을 끊지 않고 하나의 흐르는 문단으로 합침
    text = " ".join(p.strip().lstrip("-•· ") for p in (summary or "").split("\n") if p.strip())
    plain, _ = _extract_highlight_spans(text)

    pad = 42
    for size in (42, 40, 38, 36, 34, 32, 30):
        f = _font(True, size)
        gap = size + 20
        inner_w = W - MARGIN * 2 - pad * 2
        lines = _wrap_keep(draw, plain, f, inner_w)
        panel_h = pad * 2 + len(lines) * gap - 10
        if y + panel_h <= H - 160:
            break

    _draw_panel(img, [MARGIN, y, W - MARGIN, y + panel_h])
    draw = ImageDraw.Draw(img)
    _draw_marked_paragraph(draw, MARGIN + pad, y + pad, text, f, inner_w, gap, max_lines=16)
    return img.convert("RGB")


def _slide_bullets(background, items: list, page: int, source: str,
                   label: str, title: str) -> Image.Image:
    """3장 — 인사이트 하나당 유리 패널 하나 + 노란 번호 뱃지."""
    img, draw, y = _slide_frame(background, page, label, title, source)
    f = _font(True, 40)
    gap, pad = 56, 34
    for i, item in enumerate(items[:3], 1):
        text = item.lstrip("-•· ").strip()
        plain, _ = _extract_highlight_spans(text)
        inner_w = W - MARGIN * 2 - pad * 2 - 76
        n = len(_wrap_keep(draw, plain, f, inner_w))
        ph = pad * 2 + n * gap - 12
        if y + ph > H - 170:
            break
        _draw_panel(img, [MARGIN, y, W - MARGIN, y + ph])
        draw = ImageDraw.Draw(img)
        # 번호 뱃지를 텍스트 '첫 줄'의 실제 글자 세로 중심에 맞춘다
        first_line = _wrap_keep(draw, plain, f, inner_w)[0]
        tx = MARGIN + pad + 76
        bbox = draw.textbbox((tx, y + pad), first_line, font=f)
        line_cy = (bbox[1] + bbox[3]) / 2
        r = 26
        draw.ellipse([MARGIN + pad, line_cy - r, MARGIN + pad + r * 2, line_cy + r], fill=HILITE)
        draw.text((MARGIN + pad + r, line_cy), str(i), font=_font(True, 32),
                  fill=DARK, anchor="mm")
        _draw_marked_paragraph(draw, tx, y + pad, text, f, inner_w, gap, max_lines=2)
        y += ph + 26
    return img.convert("RGB")


def _slide_context(background, context: str, page: int, source: str,
                   label: str = "배경 짚기", title: str = "왜 이런 일이?") -> Image.Image:
    """3장 — 이야기하듯 흐르는 문단으로. 좌측 노란 바 + 큰따옴표. (배경/댓글반응 공용)"""
    img, draw, y = _slide_frame(background, page, label, title, source)
    text = (context or "").strip()
    plain, _ = _extract_highlight_spans(text)

    pad = 42
    for size in (42, 40, 38, 36, 34):
        f = _font(True, size)
        gap = size + 22   # 이야기체는 줄간격을 여유있게
        inner_w = W - MARGIN * 2 - pad * 2
        lines = _wrap_keep(draw, plain, f, inner_w)
        panel_h = pad + 64 + len(lines) * gap + 66 + pad - 14   # +66 = 닫는 따옴표 공간
        if y + panel_h <= H - 160:
            break
    n_lines = len(lines[:14])

    _draw_panel(img, [MARGIN, y, W - MARGIN, y + panel_h])
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([MARGIN, y, MARGIN + 9, y + panel_h], radius=4, fill=HILITE)
    draw.text((MARGIN + pad - 6, y + pad - 28), "“", font=_font(True, 110), fill=HILITE)
    ty = y + pad + 64
    _draw_marked_paragraph(draw, MARGIN + pad, ty, text, f, inner_w, gap, max_lines=14)
    ty += n_lines * gap
    # 닫는 따옴표 — 여는 따옴표와 짝 맞춰 우하단에
    draw.text((W - MARGIN - pad + 6, ty - 26), "”", font=_font(True, 110),
              fill=HILITE, anchor="ra")
    return img.convert("RGB")


def render_carousel(card: dict, article: dict, extras: dict, out_prefix: str) -> list:
    """캐러셀 1~4장 렌더링. 1장은 후킹(기존 스타일), 2~4장은 같은 사진의
    블러+어둡게 배경 위에 요약/인사이트/면접활용. AI 데이터가 없는 장은 건너뜀."""
    config.CARDS_DIR.mkdir(parents=True, exist_ok=True)
    extras = extras or {}
    background = load_backgrounds(article, 1)[0]
    source = (article or {}).get("source") or (article or {}).get("site", "")

    slides = [_draw_card(card, background, source, 0, 1)]   # 1장 — 후킹

    if (extras.get("summary") or "").strip():
        slides.append(_slide_summary(background, extras["summary"], len(slides) + 1, source))
    if (extras.get("context") or "").strip():
        slides.append(_slide_context(background, extras["context"], len(slides) + 1, source))
    if extras.get("outlook"):
        slides.append(_slide_bullets(background, extras["outlook"], len(slides) + 1,
                                     source, "전망", "앞으로 지켜볼 포인트"))

    paths = []
    for i, img in enumerate(slides, 1):
        path = config.CARDS_DIR / f"{out_prefix}_{i}.png"
        img.save(path, "PNG")
        paths.append(path)
    return paths


def render_community_carousel(card: dict, background: Image.Image, extras: dict,
                              source: str, out_prefix: str) -> list:
    """커뮤니티 글 캐러셀 — 사용자가 준 이미지를 배경으로.
    1장 헤드라인 · 2장 본문 요약 · 3장 댓글 반응 요약."""
    config.CARDS_DIR.mkdir(parents=True, exist_ok=True)
    extras = extras or {}
    slides = [_draw_card(card, background, source, 0, 1)]

    if (extras.get("summary") or "").strip():
        slides.append(_slide_summary(background, extras["summary"], len(slides) + 1, source))
    if (extras.get("comments") or "").strip():
        slides.append(_slide_context(background, extras["comments"], len(slides) + 1, source,
                                     label="댓글 반응", title="사람들 반응은?"))

    paths = []
    for i, img in enumerate(slides, 1):
        path = config.CARDS_DIR / f"{out_prefix}_{i}.png"
        img.save(path, "PNG")
        paths.append(path)
    return paths


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
