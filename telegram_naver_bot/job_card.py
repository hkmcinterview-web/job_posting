# -*- coding: utf-8 -*-
"""채용공고 카드 렌더링 (1080x1350, 밝은 배경 정보정리형).

디자인:
  - 배경: 밝은 회백색 + 은은한 도트 패턴, 최상단에 브랜드 컬러 바
  - 포인트 컬러: 회사 브랜드 색 (AI 가 공고 회사에 맞춰 제안, 기본은 레드)
  - 제목: 도현체 (또렷하지만 뭉개지지 않는 익숙한 제목 폰트)
  - 우상단: 회사 로고 (이미지를 못 구하면 회사명 뱃지로 대체)
  - 표: 흰색 라운드 패널 위에 (머리글 아래 브랜드 컬러 줄)
  - 📌 포인트: 한 줄에 들어가도록 글자 크기 자동 축소 ({{...}} 는 연두 형광)
  - 우하단 요약 미니표: 라벨 칸은 브랜드 컬러 연한 톤
"""
import re

from PIL import Image, ImageDraw, ImageFilter, ImageFont

import config
from card_news import _brand_font, _draw_youtube, _ensure_font, _font

W, H = 1080, 1350
M = 64

BG = (243, 244, 248)        # 밝은 회백색 종이
DOT = (223, 226, 234)       # 도트 패턴
PANEL = (255, 255, 255)     # 표 패널
PANEL_LINE = (226, 229, 236)
INK = (24, 24, 30)
GREEN = (186, 242, 84)      # 연두 형광펜 (강조)
GRAY = (108, 112, 120)
LINE = (168, 170, 178)
PIN = (32, 44, 78)          # 핀 아이콘 네이비

DEFAULT_ACCENT = (222, 32, 38)   # 브랜드 색 없을 때 기본(레드)

_HL_RE = re.compile(r"\{\{(.+?)\}\}")
_HEX_RE = re.compile(r"^[0-9a-fA-F]{6}$")


def _accent_color(job: dict):
    """AI 가 제안한 회사 브랜드 색(#RRGGBB) → RGB. 없거나 이상하면 기본 레드."""
    s = (job.get("brand_color") or "").strip().lstrip("#")
    if not _HEX_RE.match(s):
        return DEFAULT_ACCENT
    rgb = tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    # 너무 밝아서 흰 글자가 안 보이는 색이면 어둡게 보정
    lum = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
    if lum > 190:
        rgb = tuple(int(c * 0.62) for c in rgb)
    return rgb


def _tint(rgb, ratio=0.88):
    """흰색과 섞어 연한 톤 생성 (미니표 라벨 칸 배경 등)."""
    return tuple(int(c * (1 - ratio) + 255 * ratio) for c in rgb)


def _display_font(size: int) -> ImageFont.FreeTypeFont:
    """제목용 도현체 — 실패 시 기본 볼드로 대체."""
    try:
        return ImageFont.truetype(str(_ensure_font("DoHyeon-Regular.ttf")), size)
    except Exception as e:
        print(f"[job_card] 제목 폰트 로드 실패, 기본 폰트 사용: {e}")
        return _font(True, size)


def _wrap_keep(draw, text, font, max_width):
    """줄바꿈 — 문자를 버리지 않아 원문 인덱스가 보존됨(형광 강조 계산용).
    줄이 넘칠 때 가까운 공백이 있으면 거기서 끊어 단어 중간 분리를 피한다."""
    lines, cur = [], ""
    for ch in text:
        if cur and draw.textlength(cur + ch, font=font) > max_width:
            sp = cur.rfind(" ")
            if sp > 0 and len(cur) - sp <= 12:  # 너무 멀지 않은 공백에서만
                lines.append(cur[:sp + 1])
                cur = cur[sp + 1:] + ch
            else:
                lines.append(cur)
                cur = ch
        else:
            cur += ch
    lines.append(cur)
    return lines


def _fit_font_size(draw, text, max_width, start, minimum, font_fn):
    """text 가 max_width 한 줄에 들어가는 가장 큰 크기 (없으면 minimum)."""
    size = start
    while size > minimum:
        if draw.textlength(text, font=font_fn(size)) <= max_width:
            return size
        size -= 2
    return minimum


def _make_aurora_bg(accent) -> Image.Image:
    """감각적인 그라데이션 블롭(오로라) 배경 — 브랜드 컬러의 파스텔 톤 원을
    모서리에 크게 깔고 강하게 블러 처리해 부드럽게 번지는 느낌을 만든다."""
    bg = Image.new("RGB", (W, H), (250, 251, 253))
    d = ImageDraw.Draw(bg)
    strong = _tint(accent, 0.74)   # 연한 파스텔 (은은하게)
    soft = _tint(accent, 0.85)
    faint = _tint(accent, 0.92)
    d.ellipse([W - 560, -320, W + 300, 440], fill=strong)      # 우상단 큰 블롭
    d.ellipse([-380, -240, 260, 320], fill=faint)              # 좌상단 은은하게
    d.ellipse([-320, H - 460, 340, H + 280], fill=soft)        # 좌하단
    d.ellipse([W - 420, H - 260, W + 260, H + 340], fill=faint)  # 우하단 살짝
    return bg.filter(ImageFilter.GaussianBlur(130))


def _draw_pin(draw, x, y, size=32):
    """압정 느낌 아이콘 — 머리(원) + 바늘(사선)."""
    r = size * 0.30
    hx, hy = x + size * 0.38, y + size * 0.34
    draw.ellipse([hx - r, hy - r, hx + r, hy + r], fill=PIN)
    draw.line([hx + r * 0.45, hy + r * 0.45, x + size * 0.98, y + size * 0.95],
              fill=PIN, width=5)


def _draw_logo(card: Image.Image, draw, logo, company, accent, box):
    """우상단 회사 로고. 이미지가 없으면 회사명 뱃지로 대체."""
    x0, y0, x1, y1 = box
    if logo is not None:
        logo = logo.convert("RGBA")
        logo.thumbnail((x1 - x0, y1 - y0), Image.LANCZOS)
        lx = x1 - logo.width                      # 오른쪽 정렬
        ly = y0 + ((y1 - y0) - logo.height) // 2
        card.paste(logo, (lx, ly), logo)
        return
    if not company:
        return
    f_size = _fit_font_size(draw, company, (x1 - x0) - 44, 40, 24, lambda s: _font(True, s))
    f = _font(True, f_size)
    tw = draw.textlength(company, font=f)
    bh = f_size + 34
    bx1, bx0 = x1, x1 - (tw + 44)
    by0 = y0 + ((y1 - y0) - bh) // 2
    draw.rounded_rectangle([bx0, by0, bx1, by0 + bh], radius=16, fill=accent)
    draw.text(((bx0 + bx1) / 2, by0 + bh / 2), company, font=f, fill=(255, 255, 255),
              anchor="mm")


def _draw_point(draw, x, y, text, font, max_width, line_gap):
    """포인트 텍스트 — {{...}} 부분 뒤에 연두 형광 박스. returns 다음 y."""
    hl_start = hl_end = -1
    m = _HL_RE.search(text)
    if m:
        hl_start, hl_end = m.start(), m.start() + len(m.group(1))
    plain = _HL_RE.sub(lambda mm: mm.group(1), text)

    lines = _wrap_keep(draw, plain, font, max_width)[:2]
    offset = 0
    for line in lines:
        s, e = offset, offset + len(line)
        if hl_start >= 0 and max(hl_start, s) < min(hl_end, e):
            a, b = max(hl_start, s) - s, min(hl_end, e) - s
            x0 = x + draw.textlength(line[:a], font=font)
            x1 = x0 + draw.textlength(line[a:b], font=font)
            bbox = draw.textbbox((x, y), line, font=font)
            draw.rectangle([x0 - 4, bbox[1] - 5, x1 + 4, bbox[3] + 5], fill=GREEN)
        draw.text((x, y), line, font=font, fill=INK)
        y += line_gap
        offset = e
    return y


def render_job_card(job: dict, out_name: str, logo: Image.Image = None):
    """채용공고 카드 1장을 PNG 로 저장하고 경로를 반환합니다."""
    config.CARDS_DIR.mkdir(parents=True, exist_ok=True)
    accent = _accent_color(job)

    img = _make_aurora_bg(accent)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, W, 14], fill=accent)   # 최상단 브랜드 컬러 바

    # ── 상단: 마감(좌) · 브랜드(우) ──
    top_y = 56
    deadline = (job.get("deadline") or "").strip()
    if deadline:
        draw.text((M, top_y), f"접수마감 : {deadline}"[:26], font=_font(True, 36), fill=accent)

    brand = config.BRAND_NAME
    bf = _brand_font(34)
    icon_h = 28
    icon_w = round(icon_h * 1.42)
    gap = 10
    bw = draw.textlength(brand, font=bf)
    bx = W - M - (icon_w + gap + bw)
    _draw_youtube(draw, bx, top_y + 4, icon_w, icon_h)
    draw.text((bx + icon_w + gap, top_y + 4 + icon_h / 2), brand, font=bf,
              fill=INK, anchor="lm")

    # ── 우상단 회사 로고 (브랜드명 아래) ──
    logo_box = (W - M - 300, 122, W - M, 232)
    _draw_logo(img, draw, logo, (job.get("company") or "").strip(), accent, logo_box)

    # ── 큰 제목 (도현체, 1~2줄) ──
    title_lines = [t.strip() for t in (job.get("title") or "").split("/") if t.strip()][:2]
    if not title_lines:
        title_lines = [(job.get("company") or "채용공고")]
    title_max_w = W - M * 2 - 300   # 우측 로고 자리 확보
    size = 96
    while size > 56 and any(draw.textlength(ln, font=_display_font(size)) > title_max_w
                            for ln in title_lines):
        size -= 4
    tf = _display_font(size)
    y = 132
    for line in title_lines:
        draw.text((M, y), line, font=tf, fill=INK)
        y += int(size * 1.24)   # 도현체는 자간이 좁아 1.24 배면 충분
    y += 14

    # ── 뱃지 (브랜드 컬러) ──
    badges = job.get("badges") or []
    if badges:
        f = _font(True, 33)
        bx = M
        for b in badges:
            tw = draw.textlength(b, font=f)
            pad, bh = 20, 56
            draw.rounded_rectangle([bx, y, bx + tw + pad * 2, y + bh], radius=10, fill=accent)
            draw.text((bx + pad, y + bh / 2), b, font=f, fill=(255, 255, 255), anchor="lm")
            bx += tw + pad * 2 + 16
        y += 56 + 30
    else:
        y += 16

    # ── 모집 표 (흰색 라운드 패널) ──
    head = job.get("table_head") or []
    rows = job.get("table_rows") or []
    if head and rows:
        n = len(head)
        pad_v = 34
        panel_h = pad_v + 70 + 28 + len(rows) * 68 + pad_v - 14
        draw.rounded_rectangle([M - 20, y, W - M + 20, y + panel_h], radius=22,
                               fill=PANEL, outline=PANEL_LINE, width=2)
        ty = y + pad_v
        centers = [M + (W - M * 2) * (i + 0.5) / n for i in range(n)]
        hf = _font(True, 42)
        for i, h in enumerate(head):
            draw.text((centers[i], ty), h[:6], font=hf, fill=INK, anchor="ma")
        ty += 70   # 머리글 글자 높이(디센더 포함)보다 넉넉하게 — 밑줄과 겹치지 않도록
        draw.line([M + 4, ty, W - M - 4, ty], fill=accent, width=7)
        ty += 28

        rf = _font(True, 44)
        for row in rows:
            cell_f = rf
            longest = max(row, key=lambda c: draw.textlength(c, font=rf))
            if draw.textlength(longest, font=rf) > (W - M * 2) / n - 16:
                fit = _fit_font_size(draw, longest, (W - M * 2) / n - 16, 44, 28,
                                     lambda s: _font(True, s))
                cell_f = _font(True, fit)
            for i, cell in enumerate(row):
                draw.text((centers[i], ty), cell, font=cell_f, fill=INK, anchor="ma")
            ty += 68
        y += panel_h + 34

    # ── 우하단 미니표 자리 먼저 계산 ──
    infos = job.get("infos") or []
    info_row_h, info_label_w, info_val_w = 62, 190, 196
    info_w = info_label_w + info_val_w
    info_x0 = W - M - info_w
    info_y0 = H - 66 - len(infos) * info_row_h if infos else H

    # ── 📌 핵심 포인트 (한 줄에 맞게 크기 자동 조절) ──
    points = (job.get("points") or [])[:6]
    for p in points:
        max_w = ((info_x0 - M - 44) if (infos and y > info_y0 - 96) else (W - M * 2)) - 46
        plain = _HL_RE.sub(lambda mm: mm.group(1), p)
        fit = _fit_font_size(draw, plain, max_w, 36, 27, lambda s: _font(True, s))
        pf = _font(True, fit)
        n_lines = min(2, len(_wrap_keep(draw, plain, pf, max_w)))
        line_gap = fit + 15
        if y + n_lines * line_gap > H - 44:   # 이 포인트가 안 들어가면 종료
            break
        _draw_pin(draw, M, y + 2)
        y = _draw_point(draw, M + 46, y, p, pf, max_w, line_gap)
        y += 16

    # ── 우하단 요약 미니표 (라벨 칸은 브랜드 컬러 연한 톤) ──
    if infos:
        f = _font(True, 32)
        label_bg = _tint(accent, 0.88)
        for r, (k, v) in enumerate(infos):
            ry = info_y0 + r * info_row_h
            draw.rectangle([info_x0, ry, info_x0 + info_label_w, ry + info_row_h],
                           fill=label_bg, outline=LINE, width=2)
            draw.rectangle([info_x0 + info_label_w, ry, info_x0 + info_w, ry + info_row_h],
                           fill=PANEL, outline=LINE, width=2)
            key_color = accent if any(w in k for w in ("마감", "접수", "의무")) else INK
            draw.text((info_x0 + info_label_w / 2, ry + info_row_h / 2), k[:5],
                      font=f, fill=key_color, anchor="mm")
            vf = f
            if draw.textlength(v, font=f) > info_val_w - 16:
                vf = _font(True, _fit_font_size(draw, v, info_val_w - 16, 32, 22,
                                                lambda s: _font(True, s)))
            draw.text((info_x0 + info_label_w + info_val_w / 2, ry + info_row_h / 2), v,
                      font=vf, fill=INK, anchor="mm")

    path = config.CARDS_DIR / f"{out_name}.png"
    img.save(path, "PNG")
    return path
