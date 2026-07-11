# -*- coding: utf-8 -*-
"""뉴스 링크에서 제목/요약/본문/대표사진/출처를 추출합니다."""
import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept-Language": "ko,en;q=0.8",
}

# 네이버/다음 등 주요 언론사 본문 컨테이너
BODY_SELECTORS = "#dic_area, #newsct_article, #articleBodyContents, #article-view-content-div, article"


def _clean_source(name: str) -> str:
    name = (name or "").strip()
    # "언론사명 | 네이버", "언론사명 - 네이버뉴스" 등에서 언론사명만
    name = re.split(r"[|·\-–:]", name)[0].strip()
    for junk in ("네이버뉴스", "네이버 뉴스", "네이버", "다음뉴스", "Daum", "NAVER"):
        name = name.replace(junk, "").strip()
    return name


def fetch_article(url: str) -> dict:
    resp = requests.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    def og(prop):
        tag = (soup.find("meta", property=f"og:{prop}")
               or soup.find("meta", attrs={"name": prop})
               or soup.find("meta", property=prop))
        return (tag.get("content") or "").strip() if tag and tag.get("content") else ""

    title = og("title")
    if not title and soup.title:
        title = soup.title.get_text(strip=True)
    description = og("description")
    site = og("site_name") or urlparse(url).netloc
    image_url = og("image")

    # 출처(언론사명) — 여러 위치를 시도
    source = _clean_source(
        og("article:author") or og("author")
        or (soup.find("meta", attrs={"name": "twitter:creator"}) or {}).get("content", "")
        or og("site_name")
    )
    if not source or source.lower() in ("naver", "daum"):
        host = urlparse(url).netloc.replace("www.", "")
        source = _clean_source(og("site_name")) or host.split(".")[0]

    # 본문 — 언론사 본문 컨테이너 우선, 없으면 <p> 태그
    paragraphs = []
    node = soup.select_one(BODY_SELECTORS)
    if node:
        for line in node.get_text("\n", strip=True).split("\n"):
            line = line.strip()
            if len(line) >= 25:
                paragraphs.append(line)
            if len(paragraphs) >= 20:
                break
    if len(paragraphs) < 2:
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
        "source": source,
        "image_url": image_url,
        "paragraphs": paragraphs,
    }


def fetch_image_bytes(image_url: str, referer: str = "") -> bytes:
    """기사 대표사진 다운로드 (일부 언론사는 Referer 를 요구)."""
    headers = dict(HEADERS)
    if referer:
        headers["Referer"] = referer
    resp = requests.get(image_url, headers=headers, timeout=20)
    resp.raise_for_status()
    return resp.content
