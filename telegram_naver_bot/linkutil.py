# -*- coding: utf-8 -*-
"""단축 URL 펼치기.

네이버 카페 API는 단축주소(buly.kr 등)가 든 글을 스팸으로 보고 999 로 거부하는
경우가 많습니다. 글을 올리기 직전에 단축주소를 따라가 '원본(최종) 주소'로 바꿔치기하면
- 신뢰 도메인(언론사/네이버뉴스)으로 바뀌어 스팸 필터를 통과할 확률이 높고
- 정보 손실도 없습니다.
"""
import re
from urllib.parse import urlparse

import requests

URL_RE = re.compile(r"https?://[^\s<>\"]+")
TRAILING_PUNCT = ").,>]\"'”’"

# 대표적인 단축 URL 도메인 — 이 도메인만 펼친다 (일반 링크는 그대로 둠)
SHORTENER_HOSTS = {
    "buly.kr", "bit.ly", "han.gl", "hxn.kr", "url.kr", "me2.do", "goo.gl",
    "t.co", "abr.ge", "c11.kr", "vo.la", "asq.kr", "abit.ly", "zrr.kr",
    "if.kr", "aa.gg", "muz.so", "tinyurl.com", "is.gd", "buly.co.kr",
}

_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
}


def _is_shortener(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    host = host[4:] if host.startswith("www.") else host
    return host in SHORTENER_HOSTS


def _resolve(url: str, timeout: int = 8) -> str:
    """단축주소를 따라가 최종 주소를 반환. 실패하면 원래 주소 그대로."""
    for method in ("head", "get"):
        try:
            r = requests.request(method, url, allow_redirects=True,
                                 timeout=timeout, headers=_HEADERS, stream=(method == "get"))
            final = r.url
            if method == "get":
                r.close()
            if final and final != url:
                return final
        except Exception:
            continue
    return url


def expand_short_links(text: str) -> str:
    """본문 속 단축주소를 전부 원본 주소로 펼친다 (같은 주소는 한 번만 조회)."""
    if not text:
        return text
    cache = {}

    def repl(m):
        raw = m.group(0)
        url = raw.rstrip(TRAILING_PUNCT)
        trail = raw[len(url):]
        if not _is_shortener(url):
            return raw
        if url not in cache:
            cache[url] = _resolve(url)
            print(f"[linkutil] 단축주소 펼침: {url} → {cache[url]}")
        return cache[url] + trail

    return URL_RE.sub(repl, text)
