# -*- coding: utf-8 -*-
"""네이버 카페 글쓰기 인코딩 진단 도구.

짧은 테스트 글 4개를 서로 다른 인코딩 방식으로 올려봅니다.
실행 후 카페에 가서 4개 글 중 한글이 정상으로 보이는 게 있는지 확인하고,
그 글의 라벨(A/B/C/D)을 알려주세요 — 그걸로 정확한 인코딩 방식을 확정합니다.

사용법: python test_naver_encoding.py
"""
import urllib.error
import urllib.request
from urllib.parse import quote, urlencode

import requests

import config
from naver_cafe import _get_access_token, load_tokens, refresh_access_token

TEST_KOREAN = "가나다라마 자동차산업 테스트"


def enc_utf8_single(text: str) -> str:
    return quote(text.encode("utf-8"), safe="")


def enc_cp949_single(text: str) -> str:
    return quote(text.encode("cp949", errors="replace"), safe="")


def enc_utf8_double(text: str) -> str:
    once = quote(text.encode("utf-8"), safe="")
    return quote(once, safe="")  # 퍼센트 인코딩된 문자열을 한 번 더 인코딩


def enc_cp949_double(text: str) -> str:
    once = quote(text.encode("cp949", errors="replace"), safe="")
    return quote(once, safe="")


VARIANTS = {
    "A-UTF8-1회": enc_utf8_single,
    "B-CP949-1회": enc_cp949_single,
    "C-UTF8-2회": enc_utf8_double,
    "D-CP949-2회": enc_cp949_double,
}


def _post_urlencoded(label: str, encode_fn) -> str:
    url = (f"https://openapi.naver.com/v1/cafe/{config.NAVER_CAFE_CLUB_ID}"
           f"/menu/{config.NAVER_CAFE_MENU_ID}/articles")
    subject = f"[TEST-{label}]"
    content = f"[TEST-{label}] {TEST_KOREAN}"
    payload = f"subject={encode_fn(subject)}&content={encode_fn(content)}"

    def _send(token):
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        return requests.post(url, data=payload.encode("utf-8"), headers=headers, timeout=60)

    return _do(_send)


def _post_multipart(label: str) -> str:
    """이미지 없이도 강제로 multipart/form-data 로 전송 — 퍼센트 인코딩을 아예 안 씀."""
    url = (f"https://openapi.naver.com/v1/cafe/{config.NAVER_CAFE_CLUB_ID}"
           f"/menu/{config.NAVER_CAFE_MENU_ID}/articles")
    subject = f"[TEST-{label}]"
    content = f"[TEST-{label}] {TEST_KOREAN}"

    def _send(token):
        headers = {"Authorization": f"Bearer {token}"}
        # (None, value) 형태로 넘기면 파일이 아니라 순수 텍스트 필드로 취급되어
        # requests 가 multipart/form-data 로 보냄 (UTF-8, 퍼센트 인코딩 없음)
        files = {
            "subject": (None, subject),
            "content": (None, content),
        }
        return requests.post(url, files=files, headers=headers, timeout=60)

    return _do(_send)


def _post_urllib(label: str) -> str:
    """requests 대신 urllib.request + urlencode() 로 보내는 방식 (사용자 제안).
    urlencode() 는 내부적으로 quote_plus 를 한 번만 적용 — enc_utf8_single 과
    거의 같은 인코딩 결과지만, 헤더 처리 등 라이브러리 차이가 있어 별도로 검증."""
    url = (f"https://openapi.naver.com/v1/cafe/{config.NAVER_CAFE_CLUB_ID}"
           f"/menu/{config.NAVER_CAFE_MENU_ID}/articles")
    subject = f"[TEST-{label}]"
    content = f"[TEST-{label}] {TEST_KOREAN}"
    data = urlencode({"subject": subject, "content": content}).encode("utf-8")

    def _send(token):
        request = urllib.request.Request(url, data=data, method="POST")
        request.add_header("Authorization", f"Bearer {token}")
        request.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with urllib.request.urlopen(request, timeout=60) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    status, body = _send(_get_access_token())
    if status == 401:
        tokens = refresh_access_token(load_tokens())
        status, body = _send(tokens["access_token"])

    if status != 200:
        return f"❌ 실패 (HTTP {status}): {body.decode('utf-8', errors='replace')[:200]}"

    import json
    result = json.loads(body.decode("utf-8")).get("message", {}).get("result", {})
    return f"✅ {result.get('articleUrl') or result.get('cafeUrl') or '(URL 확인 불가)'}"


def _do(send_fn) -> str:
    token = _get_access_token()
    resp = send_fn(token)
    if resp.status_code == 401:
        tokens = refresh_access_token(load_tokens())
        resp = send_fn(tokens["access_token"])

    if resp.status_code != 200:
        return f"❌ 실패 (HTTP {resp.status_code}): {resp.text[:200]}"

    result = resp.json().get("message", {}).get("result", {})
    return f"✅ {result.get('articleUrl') or result.get('cafeUrl') or '(URL 확인 불가)'}"


def main():
    print(f"테스트 문자열: {TEST_KOREAN}\n")
    for label, fn in VARIANTS.items():
        print(f"[{label}] 게시 중...")
        print("  →", _post_urlencoded(label, fn))

    print("[E-멀티파트] 게시 중...")
    print("  →", _post_multipart("E-멀티파트"))

    print("[F-urllib] 게시 중...")
    print("  →", _post_urllib("F-urllib"))

    print("\n위 글들을 카페에서 열어보고, 한글이 정상으로 보이는 게 있으면")
    print("그 라벨(A/B/C/D/E/F)을 알려주세요. 전부 깨져 있으면 그것도 알려주세요.")


if __name__ == "__main__":
    main()
