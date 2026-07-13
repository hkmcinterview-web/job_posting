# -*- coding: utf-8 -*-
"""방금 올라간 글을 '브라우저 화면'이 아니라 'API 응답(JSON)'으로 직접 읽어봅니다.

브라우저가 인코딩을 잘못 추측해서 화면에만 깨져 보이는 건지,
아니면 서버에 실제로 깨진 채로 저장된 건지 구분하기 위한 진단 도구입니다.
JSON 은 항상 UTF-8 이라, 여기서 정상으로 보이면 '저장은 맞고 화면 표시만 문제'라는 뜻입니다.

사용법: python test_naver_read.py
"""
import requests

import config
from naver_cafe import _get_access_token, load_tokens, refresh_access_token


def main():
    token = _get_access_token()
    url = (f"https://openapi.naver.com/v1/cafe/{config.NAVER_CAFE_CLUB_ID}"
           f"/menu/{config.NAVER_CAFE_MENU_ID}/articles")

    def _get(access_token):
        return requests.get(url, headers={"Authorization": f"Bearer {access_token}"},
                            params={"perPage": 10}, timeout=20)

    resp = _get(token)
    if resp.status_code == 401:
        tokens = refresh_access_token(load_tokens())
        resp = _get(tokens["access_token"])

    print(f"HTTP {resp.status_code}")
    if resp.status_code != 200:
        print(resp.text[:1000])
        print("\n❌ 목록 조회 자체가 안 됩니다 — 이 방법으로는 확인이 어렵습니다.")
        return

    # requests 가 응답을 어떤 인코딩으로 읽었는지도 같이 확인
    print("응답 인코딩(추정):", resp.encoding)
    resp.encoding = "utf-8"  # JSON 은 항상 UTF-8 — 강제로 지정해서 재확인

    print("\n--- 최근 글 목록 (raw JSON 일부) ---")
    print(resp.text[:2000])


if __name__ == "__main__":
    main()
