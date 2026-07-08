# -*- coding: utf-8 -*-
"""텔레그램 메시지 파싱 — 제목/본문/뉴스링크 분리.

규칙:
- 첫 줄이 "제목: ..." 형식이면 그 내용을 카페 글 제목으로 사용
- 아니면 첫 줄이 50자 이하일 때 제목으로 간주
- 본문에서 URL은 모두 추출해 별도 목록으로 반환 (본문에서는 제거)
"""
import re

URL_RE = re.compile(r"https?://[^\s<>\"]+")
TRAILING_PUNCT = ").,>]\"'”’"


def parse_message(text: str):
    """returns (title, body, links)"""
    links, seen = [], set()
    for raw in URL_RE.findall(text or ""):
        url = raw.rstrip(TRAILING_PUNCT)
        if url not in seen:
            seen.add(url)
            links.append(url)

    body = URL_RE.sub("", text or "")
    lines = [ln.strip() for ln in body.splitlines()]
    lines = [ln for ln in lines if ln]

    title = ""
    if lines:
        first = lines[0]
        if first.startswith("제목:") or first.startswith("제목 :"):
            title = first.split(":", 1)[1].strip()
            lines = lines[1:]
        elif len(first) <= 50:
            title = first
            lines = lines[1:]

    return title, "\n".join(lines), links
