# -*- coding: utf-8 -*-
"""채용공고 카드 렌더링 (1080x1350, 흰 배경 정보정리형).

레이아웃 (APT_LAP 스타일 참고):
  ┌ 접수마감(좌상단, 빨강)          채용정보·브랜드(우상단) ┐
  │ 큰 제목 1~2줄 (검정 초굵게)                        │
  │ [빨간 뱃지] [빨간 뱃지]                             │
  │ 표: 모집분야 | 경력 | 인원  (머리글 아래 보라 굵은 줄) │
  │ 📌 핵심 포인트들 ({{...}} 는 연두 형광 강조)          │
  │                              ┌ 요약 미니표(우하단) ┐ │
  └──────────────────────────────┴───────────────────┴─┘
"""
import re

from PIL import Image, ImageDraw

import config
from card_news import _brand_font, _draw_youtube, _font

W, H = 1080, 1350
M = 64

BG = (255, 255, 255)
INK = (22, 22, 26)
RED = (222, 32, 38)
PURPLE = (94, 44, 150)
GREEN = (186, 242, 84)     # 연두 형광펜
GRAY = (108, 112, 120)
LINE = (154, 154, 160)
PIN = (32, 44, 78)         # 핀/네이비 포인트

_HL_RE = re.compile(r"\{\{(.+?)\}\}")


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


def _fit_font(draw, lines, max_width, start_size, min_size, bold=True):
    """모든 줄이 max_width 안에 들어가는 가장 큰 폰트를 찾는다."""
    size = start_size
    while size > min_size:
        f = _font(bold, size)
        if all(draw.textlength(ln, font=f) <= max_width for ln in lines):
            return f
        size -= 4
    return _font(bold, min_size)


def _draw_pin(draw, x, y, size=34):
    """압정 느낌 아이콘 — 머리(원) + 바늘(사선)."""
    r = size * 0.30
    hx, hy = x + size * 0.38, y + size * 0.34
    draw.ellipse([hx - r, hy - r, hx + r, hy + r], fill=PIN)
    draw.line([hx + r * 0.45, hy + r * 0.45, x + size * 0.98, y + size * 0.95],
              fill=PIN, width=5)


def _draw_point(draw, x, y, text, font, max_width, line_gap):
    """포인트 한 줄(들) — {{...}} 부분 뒤에 연두 형광 박스. returns 다음 y."""
    hl_start = hl_end = -1
    m = _HL_RE.search(text)
    if m:
        plain = text[:m.start()] + m.group(1) + text[m.end():]
        hl_start, hl_end = m.start(), m.start() + len(m.group(1))
    else:
        plain = text
    plain = _HL_RE.sub(lambda mm: mm.group(1), plain)  # 혹시 2개 이상이면 마커만 제거

    lines = _wrap_keep(draw, plain, font, max_width)[:2]  # 포인트는 최대 2줄
    offset = 0
    for i, line in enumerate(lines):
        lx = x if i == 0 else x  # 이어지는 줄도 같은 들여쓰기
        s, e = offset, offset + len(line)
        if hl_start >= 0 and max(hl_start, s) < min(hl_end, e):
            a, b = max(hl_start, s) - s, min(hl_end, e) - s
            x0 = lx + draw.textlength(line[:a], font=font)
            x1 = x0 + draw.textlength(line[a:b], font=font)
            bbox = draw.textbbox((lx, y), line, font=font)
            draw.rectangle([x0 - 4, bbox[1] - 5, x1 + 4, bbox[3] + 5], fill=GREEN)
        draw.text((lx, y), line, font=font, fill=INK)
        y += line_gap
        offset = e
    return y


def render_job_card(job: dict, out_name: str):
    """채용공고 카드 1장을 PNG 로 저장하고 경로를 반환합니다."""
    config.CARDS_DIR.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # ── 상단: 마감(좌) · 브랜드(우) ──
    top_y = 56
    deadline = (job.get("deadline") or "").strip()
    if deadline:
        f = _font(True, 36)
        draw.text((M, top_y), f"접수마감 : {deadline}"[:26], font=f, fill=RED)

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

    # ── 큰 제목 (1~2줄, 초굵게) ──
    title_lines = [t.strip() for t in (job.get("title") or "").split("/") if t.strip()][:2]
    if not title_lines:
        title_lines = [(job.get("company") or "채용공고")]
    tf = _fit_font(draw, title_lines, W - M * 2, 104, 64)
    y = 128
    for line in title_lines:
        draw.text((M, y), line, font=tf, fill=INK, stroke_width=3, stroke_fill=INK)
        y += int(tf.size * 1.38)  # 한글 글리프 실제 높이(어센더+디센더)를 고려한 줄 간격
    y += 8

    # ── 빨간 뱃지 ──
    badges = job.get("badges") or []
    if badges:
        f = _font(True, 34)
        bx = M
        for b in badges:
            tw = draw.textlength(b, font=f)
            pad, bh = 20, 58
            draw.rectangle([bx, y, bx + tw + pad * 2, y + bh], fill=RED)
            draw.text((bx + pad, y + bh / 2), b, font=f, fill=BG, anchor="lm")
            bx += tw + pad * 2 + 16
        y += 58 + 26
    else:
        y += 16

    # ── 모집 표 ──
    head = job.get("table_head") or []
    rows = job.get("table_rows") or []
    if head and rows:
        n = len(head)
        centers = [M + (W - M * 2) * (i + 0.5) / n for i in range(n)]
        hf = _font(True, 44)
        for i, h in enumerate(head):
            draw.text((centers[i], y), h[:6], font=hf, fill=INK, anchor="ma")
        y += 62
        draw.line([M, y, W - M, y], fill=PURPLE, width=9)
        y += 26

        rf = _font(True, 46)
        for row in rows:
            cell_f = rf
            longest = max(row, key=lambda c: draw.textlength(c, font=rf))
            if draw.textlength(longest, font=rf) > (W - M * 2) / n - 16:
                cell_f = _fit_font(draw, [longest], (W - M * 2) / n - 16, 46, 30)
            for i, cell in enumerate(row):
                draw.text((centers[i], y), cell, font=cell_f, fill=INK, anchor="ma")
            y += 70
        y += 24

    # ── 우하단 미니표 자리 먼저 계산 (포인트 줄바꿈 폭 결정용) ──
    infos = job.get("infos") or []
    info_row_h, info_label_w, info_val_w = 64, 195, 195
    info_w = info_label_w + info_val_w
    info_x0 = W - M - info_w
    info_y0 = H - 72 - len(infos) * info_row_h if infos else H

    # ── 📌 핵심 포인트 ──
    points = (job.get("points") or [])[:6]
    pf = _font(True, 36)
    line_gap = 50
    for p in points:
        # 미니표 세로 구간과 겹치면 좁게 줄바꿈
        max_w = (info_x0 - M - 40) if (infos and y > info_y0 - 100) else (W - M * 2)
        plain = _HL_RE.sub(lambda mm: mm.group(1), p)
        n_lines = min(2, len(_wrap_keep(draw, plain, pf, max_w - 48)))
        if y + n_lines * line_gap > H - 50:  # 이 포인트가 안 들어가면 종료
            break
        _draw_pin(draw, M, y + 2)
        y = _draw_point(draw, M + 48, y, p, pf, max_w - 48, line_gap)
        y += 14

    # ── 우하단 요약 미니표 ──
    if infos:
        f = _font(True, 33)
        for r, (k, v) in enumerate(infos):
            ry = info_y0 + r * info_row_h
            draw.rectangle([info_x0, ry, info_x0 + info_label_w, ry + info_row_h],
                           outline=LINE, width=2)
            draw.rectangle([info_x0 + info_label_w, ry, info_x0 + info_w, ry + info_row_h],
                           outline=LINE, width=2)
            key_color = RED if any(w in k for w in ("마감", "접수", "의무")) else INK
            draw.text((info_x0 + info_label_w / 2, ry + info_row_h / 2), k[:5],
                      font=f, fill=key_color, anchor="mm")
            vf = f
            if draw.textlength(v, font=f) > info_val_w - 16:
                vf = _fit_font(draw, [v], info_val_w - 16, 33, 22)
            draw.text((info_x0 + info_label_w + info_val_w / 2, ry + info_row_h / 2), v,
                      font=vf, fill=INK, anchor="mm")

    path = config.CARDS_DIR / f"{out_name}.png"
    img.save(path, "PNG")
    return path
