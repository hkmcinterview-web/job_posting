# -*- coding: utf-8 -*-
"""카페 글(제목 + HTML 본문) 편집.

사용자가 직접 편집해서 보낸 텍스트의 레이아웃을 최대한 보존합니다:
- 줄바꿈은 그대로, 빈 줄은 여백으로
- 링크는 쓴 위치에서 클릭 가능한 링크로
- POST_HEADER / POST_FOOTER (.env) 가 본문 위/아래에 붙습니다
"""
import datetime as dt
import html
import re

import config

URL_RE = re.compile(r"https?://[^\s<>\"]+")
TRAILING_PUNCT = ").,>]\"'”’"


def _linkify(line: str) -> str:
    """한 줄 안의 URL 을 클릭 가능한 <a> 로, 나머지는 HTML 이스케이프."""
    out, last = [], 0
    for m in URL_RE.finditer(line):
        out.append(html.escape(line[last:m.start()]))
        url = m.group(0).rstrip(TRAILING_PUNCT)
        trail = m.group(0)[len(url):]
        out.append(f'<a href="{html.escape(url)}" target="_blank">{html.escape(url)}</a>')
        out.append(html.escape(trail))
        last = m.end()
    out.append(html.escape(line[last:]))
    return "".join(out)


def _body_html(body: str) -> list:
    parts = []
    for line in (body or "").replace("\r", "").split("\n"):
        if line.strip():
            parts.append(f"<p>{_linkify(line)}</p>")
        else:
            parts.append("<br>")
    return parts


def build_cafe_post(title: str, body: str) -> tuple:
    """returns (subject, content_html)"""
    today = dt.date.today().strftime("%Y.%m.%d")
    subject = title or f"[{today}] {config.BRAND_NAME} 뉴스 브리핑"

    parts = []
    if config.POST_HEADER:
        parts.append(config.POST_HEADER)
    parts.extend(_body_html(body))
    if config.POST_FOOTER:
        parts.append(config.POST_FOOTER)

    return subject, "\n".join(parts)


def build_job_post(job: dict, summary: str, url: str) -> tuple:
    """채용공고 카페 글. returns (subject, content_html)"""
    company = (job.get("company") or "").strip()
    title_one = " ".join(t.strip() for t in (job.get("title") or "").split("/") if t.strip())
    deadline = (job.get("deadline") or "").strip()

    subject = f"[채용] {title_one}" if title_one else f"[채용] {company} 채용공고"
    if company and company not in subject:
        subject = f"[채용] {company} — {title_one}"
    if deadline:
        subject += f" (~{deadline})"

    body = summary.strip()
    if url:
        body += f"\n\n▶ 공고 원문 / 지원하기\n{url}"

    parts = []
    if config.POST_HEADER:
        parts.append(config.POST_HEADER)
    parts.extend(_body_html(body))
    if config.POST_FOOTER:
        parts.append(config.POST_FOOTER)

    return subject, "\n".join(parts)
