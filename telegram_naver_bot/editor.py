# -*- coding: utf-8 -*-
"""텔레그램 메시지를 카페 게시글(제목 + HTML 본문)로 편집합니다.

편집 규칙은 이 파일에서 자유롭게 수정하세요:
- POST_HEADER / POST_FOOTER (.env) 가 본문 위/아래에 붙습니다
- 본문 문단은 <p> 로 감싸고, 링크는 "관련 뉴스" 목록으로 정리합니다
"""
import datetime as dt
import html

import config


def build_post(title: str, body: str, articles: list) -> tuple:
    """returns (subject, content_html)"""
    today = dt.date.today().strftime("%Y.%m.%d")
    subject = title or f"[{today}] {config.BRAND_NAME} 뉴스 브리핑"

    parts = []
    if config.POST_HEADER:
        parts.append(config.POST_HEADER)

    for line in (body or "").splitlines():
        line = line.strip()
        if line:
            parts.append(f"<p>{html.escape(line)}</p>")

    if articles:
        parts.append("<br><p><b>&#128240; 관련 뉴스</b></p>")
        for i, art in enumerate(articles, 1):
            t = html.escape(art.get("title", art["url"]))
            u = html.escape(art["url"])
            site = html.escape(art.get("site", ""))
            suffix = f" - {site}" if site else ""
            parts.append(f'<p>{i}. <a href="{u}" target="_blank">{t}</a>{suffix}</p>')

    if config.POST_FOOTER:
        parts.append(config.POST_FOOTER)

    return subject, "\n".join(parts)
