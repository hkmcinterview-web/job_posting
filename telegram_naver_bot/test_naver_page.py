# -*- coding: utf-8 -*-
"""카페 게시글 페이지를 직접 가져와서, 실제 글 내용이 담긴 iframe 안쪽 페이지까지
따라가 원본 바이트를 UTF-8 / CP949 양쪽으로 디코딩해봅니다.

사용법: python test_naver_page.py <게시글 URL>
예)     python test_naver_page.py https://cafe.naver.com/jobnyouofficial/2218
"""
import re
import sys
from urllib.parse import urljoin

import requests

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
}

IFRAME_RE = re.compile(r'<iframe[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)


def _declared_charset(resp) -> str:
    ct = resp.headers.get("Content-Type", "")
    m = re.search(r"charset=([\w-]+)", ct, re.IGNORECASE)
    return (m.group(1) if m else "utf-8").lower()


def _show(label: str, raw: bytes):
    print(f"\n===== {label} =====")
    for enc in ("utf-8", "cp949", "euc-kr"):
        print(f"--- {enc} ---")
        try:
            text = raw.decode(enc, errors="replace")
        except Exception as e:
            print(f"(디코딩 실패: {e})")
            continue
        idx = text.find("TEST-")
        if idx == -1:
            idx = text.find("<title>")
        snippet = text[max(0, idx - 20): idx + 150] if idx != -1 else text[:200]
        print(snippet.strip())


def fetch(url: str):
    resp = requests.get(url, headers=HEADERS, timeout=20)
    charset = _declared_charset(resp)
    print(f"[{url}]")
    print(f"HTTP {resp.status_code} | 서버가 밝힌 charset: {charset}")
    return resp, charset


def main():
    if len(sys.argv) < 2:
        print("사용법: python test_naver_page.py <게시글 URL>")
        return
    url = sys.argv[1]

    resp, charset = fetch(url)
    raw = resp.content
    _show("바깥 프레임 페이지", raw)

    # 서버가 밝힌 charset 기준으로 HTML을 디코딩해서 iframe 주소를 찾음
    html = raw.decode(charset, errors="replace")
    m = IFRAME_RE.search(html)
    if not m:
        print("\n⚠️ iframe 을 찾지 못했습니다 — 이 페이지가 이미 실제 내용 페이지일 수도 있고,"
              " 자바스크립트로 내용을 그리는 구조일 수도 있습니다.")
        return

    inner_url = urljoin(url, m.group(1))
    print(f"\n➡️ iframe 안쪽 주소 발견: {inner_url}")
    resp2, charset2 = fetch(inner_url)
    _show("iframe 안쪽(실제 글 내용) 페이지", resp2.content)


if __name__ == "__main__":
    main()
