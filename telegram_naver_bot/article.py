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

# 네이버/다음 등, 실제로 "기사 본문만" 담고 있다고 확신할 수 있는 컨테이너.
# 본문 속 사진(image_urls)은 여기서 매칭됐을 때만 긁어온다.
SPECIFIC_BODY_SELECTORS = "#dic_area, #newsct_article, #articleBodyContents, #article-view-content-div"
# 위에서 못 찾았을 때 텍스트 추출용으로만 쓰는 넓은 폴백 — <article> 태그는 사이드바의
# '관련기사' 추천 위젯까지 포함하는 경우가 많아, 사진 후보로는 신뢰하지 않는다.
GENERIC_BODY_SELECTOR = "article"

# 로고/아이콘/광고로 흔히 쓰이는 파일명 패턴 — 본문 이미지 후보에서 제외
_JUNK_IMG_RE = re.compile(r"(logo|icon|sprite|banner|ad_|_ad\.|btn_|blank\.gif|pixel\.gif)", re.I)


def _upsize_cdn_thumbnail(url: str) -> str:
    """네이버(pstatic) 등 주요 CDN 썸네일 URL 을 원본/고해상도로 변환 시도."""
    if not url:
        return url
    # 네이버 pstatic: ?type=w150 등 리사이즈 파라미터 제거하면 원본에 가까워짐
    if "pstatic.net" in url and "type=" in url:
        url = re.sub(r"([?&])type=[^&]*", "", url)
        url = re.sub(r"[?&]$", "", url).replace("?&", "?")
    return url


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

    # 대표사진(og:image) + 본문 안의 다른 사진들 — 카드가 여러 장일 때 서로 다른 사진을 쓰기 위함
    image_urls, seen_img = [], set()
    for src in ([image_url] if image_url else []):
        u = _upsize_cdn_thumbnail(src)
        if u and u not in seen_img:
            seen_img.add(u)
            image_urls.append(u)
    body_node = soup.select_one(SPECIFIC_BODY_SELECTORS)
    is_specific_body = body_node is not None
    if body_node is None:
        body_node = soup.select_one(GENERIC_BODY_SELECTOR)  # 텍스트 추출용 (사진 후보로는 안 씀)

    if is_specific_body:
        for img in body_node.find_all("img"):
            src = img.get("src") or img.get("data-src") or ""
            if not src or _JUNK_IMG_RE.search(src):
                continue
            if src.startswith("//"):
                src = "https:" + src
            src = _upsize_cdn_thumbnail(src)
            if src not in seen_img:
                seen_img.add(src)
                image_urls.append(src)
            if len(image_urls) >= 8:
                break

    # 출처(언론사명) — 실제 매체명(og:site_name)을 우선하고, 기자명 등은 최후 대체로만 사용
    source = _clean_source(og("site_name"))
    if not source or source.lower() in ("naver", "daum", "네이버", "다음"):
        source = _clean_source(
            og("article:author") or og("author")
            or (soup.find("meta", attrs={"name": "twitter:creator"}) or {}).get("content", "")
        )
    if not source:
        host = urlparse(url).netloc.replace("www.", "")
        source = host.split(".")[0]

    # 본문 — 언론사 본문 컨테이너 우선, 없으면 <p> 태그
    paragraphs = []
    if body_node:
        for line in body_node.get_text("\n", strip=True).split("\n"):
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
        "image_urls": image_urls,
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
