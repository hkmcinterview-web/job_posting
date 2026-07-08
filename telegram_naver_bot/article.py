# -*- coding: utf-8 -*-
"""뉴스 링크에서 제목/요약/본문 문단을 추출합니다 (og 메타태그 + <p> 태그)."""
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept-Language": "ko,en;q=0.8",
}


def fetch_article(url: str) -> dict:
    resp = requests.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    def og(prop):
        tag = soup.find("meta", property=f"og:{prop}") or soup.find("meta", attrs={"name": prop})
        return (tag.get("content") or "").strip() if tag and tag.get("content") else ""

    title = og("title")
    if not title and soup.title:
        title = soup.title.get_text(strip=True)
    description = og("description")
    site = og("site_name") or urlparse(url).netloc

    paragraphs = []
    for p in soup.find_all("p"):
        text = p.get_text(" ", strip=True)
        if len(text) >= 40:
            paragraphs.append(text)
        if len(paragraphs) >= 15:
            break

    return {
        "url": url,
        "title": title or url,
        "description": description,
        "site": site,
        "paragraphs": paragraphs,
    }
