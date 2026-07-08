# -*- coding: utf-8 -*-
"""네이버 OAuth 최초 로그인 도우미 (1회만 실행).

사용법:
  1. developers.naver.com 에서 애플리케이션 등록 (사용 API: 카페, 네이버 로그인)
     - Callback URL 에 NAVER_REDIRECT_URI 값(기본 https://localhost/callback)을 등록
  2. .env 에 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 설정
  3. python naver_auth.py 실행 → 출력된 URL 을 브라우저에서 열어 로그인/동의
  4. 리다이렉트된 주소창의 전체 URL(또는 code 값)을 붙여넣기
  → naver_tokens.json 이 생성되고, 이후 봇이 자동으로 토큰을 갱신합니다.
"""
import secrets
import time
from urllib.parse import urlencode, urlparse, parse_qs

import requests

import config
from naver_cafe import save_tokens

AUTH_URL = "https://nid.naver.com/oauth2.0/authorize"
TOKEN_URL = "https://nid.naver.com/oauth2.0/token"


def main():
    if not (config.NAVER_CLIENT_ID and config.NAVER_CLIENT_SECRET):
        raise SystemExit(".env 에 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 을 먼저 설정하세요.")

    state = secrets.token_urlsafe(16)
    url = AUTH_URL + "?" + urlencode({
        "response_type": "code",
        "client_id": config.NAVER_CLIENT_ID,
        "redirect_uri": config.NAVER_REDIRECT_URI,
        "state": state,
    })
    print("\n1) 아래 URL 을 브라우저에서 열고 네이버 로그인 후 동의해 주세요:\n")
    print(url)
    print("\n2) 로그인 후 이동된 주소(에러 페이지여도 무관)의 전체 URL 또는 code 값을 붙여넣으세요.")
    raw = input("\ncode 또는 URL: ").strip()

    if raw.startswith("http"):
        qs = parse_qs(urlparse(raw).query)
        code = (qs.get("code") or [""])[0]
    else:
        code = raw
    if not code:
        raise SystemExit("code 값을 찾지 못했습니다.")

    r = requests.get(TOKEN_URL, params={
        "grant_type": "authorization_code",
        "client_id": config.NAVER_CLIENT_ID,
        "client_secret": config.NAVER_CLIENT_SECRET,
        "code": code,
        "state": state,
    }, timeout=20)
    r.raise_for_status()
    data = r.json()
    if "access_token" not in data:
        raise SystemExit(f"토큰 발급 실패: {data}")

    save_tokens({
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
        "obtained_at": int(time.time()),
    })
    print(f"\n✅ 토큰 저장 완료: {config.NAVER_TOKEN_FILE}")
    print("이제 `python main.py` 로 봇을 실행할 수 있습니다.")


if __name__ == "__main__":
    main()
