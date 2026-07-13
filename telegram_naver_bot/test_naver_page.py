# -*- coding: utf-8 -*-
"""카페 게시글 페이지를 직접 가져와서, 원본 응답을 UTF-8 / CP949 양쪽으로
디코딩해봅니다. 브라우저의 인코딩 추측 문제인지, 실제 저장 단계의 문제인지
이 스크립트 하나로 구분할 수 있습니다.

사용법: python test_naver_page.py <게시글 URL>
예)     python test_naver_page.py https://cafe.naver.com/jobnyouofficial/2218
"""
import sys

import requests

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
}


def main():
    if len(sys.argv) < 2:
        print("사용법: python test_naver_page.py <게시글 URL>")
        return
    url = sys.argv[1]

    resp = requests.get(url, headers=HEADERS, timeout=20)
    print(f"HTTP {resp.status_code}")
    print("서버가 밝힌 Content-Type:", resp.headers.get("Content-Type"))
    print("requests 가 추측한 encoding:", resp.encoding)
    print("chardet 등으로 추정한 encoding:", resp.apparent_encoding)
    print()

    raw = resp.content  # 디코딩 전 원본 바이트

    for enc in ("utf-8", "cp949", "euc-kr"):
        print(f"--- {enc} 로 디코딩 시도 ---")
        try:
            text = raw.decode(enc, errors="replace")
        except Exception as e:
            print(f"(디코딩 실패: {e})")
            continue
        idx = text.find("TEST-")
        if idx == -1:
            idx = text.find("<title>")
        snippet = text[max(0, idx - 20): idx + 120] if idx != -1 else text[:200]
        print(snippet)
        print()


if __name__ == "__main__":
    main()
