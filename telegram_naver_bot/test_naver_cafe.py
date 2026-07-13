# -*- coding: utf-8 -*-
"""네이버 카페 API 진단 도구.

글쓰기(POST)가 실패하는 원인이 '카페 API 검수/권한 문제'인지 좁혀보기 위해,
읽기 전용(GET) API가 되는지 먼저 확인합니다.

사용법: python test_naver_cafe.py
"""
import requests

import config
from naver_cafe import _get_access_token


def main():
    try:
        token = _get_access_token()
    except Exception as e:
        print(f"❌ 토큰 로드 실패: {e}")
        return
    headers = {"Authorization": f"Bearer {token}"}

    print(f"clubid={config.NAVER_CAFE_CLUB_ID}  menuid={config.NAVER_CAFE_MENU_ID}\n")

    # 1) 카페의 게시판(메뉴) 목록 조회 — 참고용 (경로가 100% 확실친 않음, 404 여도 무방)
    url1 = f"https://openapi.naver.com/v1/cafe/{config.NAVER_CAFE_CLUB_ID}/menu/list.json"
    r1 = requests.get(url1, headers=headers, timeout=20)
    print(f"[1] 게시판 목록 조회(참고용) — HTTP {r1.status_code}")
    print(r1.text[:800])
    print()

    # 2) 글쓰기(POST)와 완전히 같은 경로를 GET 으로 호출 — 핵심 비교 지점
    #    같은 clubid/menuid 에 대해 '읽기'는 되는데 '쓰기'만 안 되는지 확인
    url2 = f"https://openapi.naver.com/v1/cafe/{config.NAVER_CAFE_CLUB_ID}/menu/{config.NAVER_CAFE_MENU_ID}/articles"
    r2 = requests.get(url2, headers=headers, params={"perPage": 5}, timeout=20)
    print(f"[2] 게시글 목록 조회(핵심) — HTTP {r2.status_code}")
    print(r2.text[:800])
    print()

    if r2.status_code == 200:
        print("✅ 읽기 API 는 됩니다 → 문제는 '글쓰기 권한'에 한정된 것으로 보입니다.")
        print("   (앱 검수/승인이 필요하거나, 계정에 그 게시판 쓰기 권한이 없을 가능성)")
    else:
        print("❌ 읽기 API 도 안 됩니다 → 앱 자체의 카페 API 접근 권한 문제일 가능성이 높습니다.")
        print("   개발자센터에서 '카페' API 설정/검수 상태를 확인해보세요.")


if __name__ == "__main__":
    main()
