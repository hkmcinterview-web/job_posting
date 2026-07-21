# -*- coding: utf-8 -*-
"""네이버 카페 글쓰기 API 클라이언트.

- 공식 카페 API (openapi.naver.com/v1/cafe/...) 사용 — 네이버 아이디/비번을 저장하지 않습니다.
- access_token 은 1시간마다 만료되므로 refresh_token 으로 자동 갱신합니다.
- 최초 1회 `python naver_auth.py` 로 로그인해 naver_tokens.json 을 생성해야 합니다.
"""
import json
import time
from urllib.parse import quote

import requests

import config

TOKEN_URL = "https://nid.naver.com/oauth2.0/token"


def load_tokens() -> dict:
    if not config.NAVER_TOKEN_FILE.exists():
        raise RuntimeError("naver_tokens.json 이 없습니다. 먼저 `python naver_auth.py` 를 실행해 네이버 로그인을 완료하세요.")
    return json.loads(config.NAVER_TOKEN_FILE.read_text(encoding="utf-8"))


def save_tokens(tokens: dict):
    config.NAVER_TOKEN_FILE.write_text(json.dumps(tokens, ensure_ascii=False, indent=2), encoding="utf-8")


def refresh_access_token(tokens: dict) -> dict:
    r = requests.get(TOKEN_URL, params={
        "grant_type": "refresh_token",
        "client_id": config.NAVER_CLIENT_ID,
        "client_secret": config.NAVER_CLIENT_SECRET,
        "refresh_token": tokens["refresh_token"],
    }, timeout=20)
    r.raise_for_status()
    data = r.json()
    if "access_token" not in data:
        raise RuntimeError(f"네이버 토큰 갱신 실패: {data}")
    tokens["access_token"] = data["access_token"]
    tokens["obtained_at"] = int(time.time())
    save_tokens(tokens)
    return tokens


def _get_access_token() -> str:
    tokens = load_tokens()
    # 발급 후 50분 지났으면 선제적으로 갱신
    if int(time.time()) - tokens.get("obtained_at", 0) > 50 * 60:
        tokens = refresh_access_token(tokens)
    return tokens["access_token"]


def _to_html_entities(text: str) -> str:
    """한글 등 비ASCII 문자를 전부 HTML 숫자 엔티티(&#44032;)로 변환.

    이 카페는 구형(MS949) 스킨이라 UTF-8 바이트로 보낸 한글을 서버가 잘못
    해석해 글자가 깨집니다. 엔티티로 바꾸면 전송 내용이 순수 ASCII 뿐이라
    인코딩 오해석이 원천적으로 불가능하고, 화면에서 브라우저가 한글로
    렌더링합니다 (제목/본문 모두 정상 표시되는 것을 실측으로 확인함)."""
    return "".join(c if ord(c) < 128 else f"&#{ord(c)};" for c in text or "")


def _encode_field(text: str) -> str:
    """subject/content 인코딩: HTML 엔티티 변환 후 퍼센트 인코딩 1회.
    (CP949·이중 퍼센트 인코딩은 HTTP 403/999로 거부되는 것을 실측으로 확인)"""
    return quote(_to_html_entities(text).encode("utf-8"), safe="")


# 연속 등록 제한(도배 방지) — 짧은 간격으로 연달아 올리면 HTTP 403/999 로
# 거부되는 것을 실측으로 확인함. 마지막 게시 후 최소 이 시간(초)을 확보한다.
_MIN_POST_INTERVAL = 65
_last_post_at = 0.0


def _respect_rate_limit():
    global _last_post_at
    wait = _MIN_POST_INTERVAL - (time.time() - _last_post_at)
    if wait > 0:
        print(f"[naver_cafe] 연속 등록 제한 회피 — {wait:.0f}초 대기...")
        time.sleep(wait)


# 네이버 카페 API 에러코드 → 사람이 읽을 수 있는 원인/해결 힌트
_NAVER_ERR_HINTS = {
    "024": "인증 실패 — access_token 이 유효하지 않아요. `python naver_auth.py` 로 다시 로그인해 토큰을 새로 발급하세요.",
    "028": "권한 없음 — 이 앱/토큰에 카페 글쓰기 권한이 없거나, 로그인한 네이버 계정이 이 게시판에 글 쓸 권한이 없어요.",
    "999": ("네이버 '스팸 필터'에 막혔어요 (토큰/권한 문제 아님). 흔한 원인: "
            "①본문에 링크가 많거나 단축주소(buly.kr 등)가 있음 ②짧은 시간에 여러 번 올림 "
            "③글쓰는 네이버 계정이 이 카페에서 활동이 적어 신뢰도가 낮음. "
            "→ 링크를 1개 이하로 줄이거나 빼고, 몇 분 뒤 다시 시도해보세요. "
            "그래도 막히면 같은 내용을 네이버 카페 웹에서 직접 올려보며 필터인지 확인하세요."),
    "403": "권한 없음/도배 제한 — 게시판 쓰기 권한 부족이거나, 짧은 시간에 너무 자주 올려 막혔을 수 있어요.",
    "haveto": "카페 등급/권한 부족 — 게시판이 요구하는 회원 등급을 아직 못 채웠거나, 매니저가 API 글쓰기를 막아둔 게시판일 수 있어요.",
}


def _format_post_error(resp) -> str:
    """네이버 403/오류 응답에서 에러코드·메시지를 뽑아 사람이 읽을 수 있게 정리."""
    code = msg = ""
    try:
        data = resp.json()
        # 네이버 응답 형식이 여러 가지라 두루 뒤진다.
        m = data.get("message", data)
        err = (m.get("error") if isinstance(m, dict) else None) or {}
        code = str(err.get("code") or data.get("errorCode") or "")
        msg = str(err.get("msg") or data.get("errorMessage") or "")
    except Exception:
        pass

    hint = ""
    for key, text in _NAVER_ERR_HINTS.items():
        if key and (key == code or key in (msg or "").lower()):
            hint = "\n➡️ " + text
            break
    if not hint and resp.status_code == 403:
        hint = ("\n➡️ 403 은 보통 ①토큰 만료/권한(→`python naver_auth.py` 재로그인) "
                "②도배 제한(잠시 후 재시도) ③게시판 쓰기 권한/등급 부족 중 하나예요.")

    detail = f"code={code} msg={msg}".strip() if (code or msg) else resp.text[:400]
    return f"카페 글쓰기 실패 (HTTP {resp.status_code}): {detail}{hint}"


def post_article(subject: str, content_html: str, image_paths=None,
                 menu_id: str = "") -> dict:
    """카페에 글을 작성하고 {'articleId': ..., 'articleUrl': ...} 를 반환합니다.

    subject/content 는 한글을 HTML 엔티티로 바꾼 뒤(_to_html_entities 참고)
    UTF-8 퍼센트 인코딩 1회만 적용해서 보냅니다 — 이 조합이 글자 깨짐 없이
    정상 표시되는 유일한 방식임을 실측으로 확인했습니다.

    ⚠️ 이미지 없이 보낼 때(x-www-form-urlencoded)는 이미 퍼센트 인코딩된 문자열을
    requests 의 data=dict 로 넘기면 안 됩니다 — requests 가 폼 인코딩 과정에서
    '%' 문자까지 다시 인코딩해버려 이중 인코딩되고, 네이버 서버가 이를 못 알아들어
    글 자체가 등록되지 않습니다. 그래서 문자열을 직접 조립해 raw bytes 로 보냅니다.
    이미지가 있으면(multipart) 이 문제가 없어 원본 텍스트를 그대로 보냅니다.
    """
    global _last_post_at
    token = _get_access_token()
    menu = menu_id or config.NAVER_CAFE_MENU_ID
    url = (f"https://openapi.naver.com/v1/cafe/{config.NAVER_CAFE_CLUB_ID}"
           f"/menu/{menu}/articles")
    print(f"[naver_cafe] 요청 URL: {url}  (clubid={config.NAVER_CAFE_CLUB_ID}, "
          f"menuid={menu})")
    _respect_rate_limit()

    def _send(access_token):
        headers = {"Authorization": f"Bearer {access_token}"}
        opened_files = []
        try:
            if image_paths:
                files = []
                for p in image_paths:
                    f = open(p, "rb")
                    opened_files.append(f)
                    mime = ("image/jpeg" if str(p).lower().endswith((".jpg", ".jpeg"))
                            else "image/png")
                    files.append(("image", (p.name, f, mime)))
                # 멀티파트도 한글 깨짐 방지를 위해 HTML 엔티티로 변환해서 보냄
                req_data = {"subject": _to_html_entities(subject),
                            "content": _to_html_entities(content_html)}
                return requests.post(url, data=req_data, files=files,
                                     headers=headers, timeout=60)

            # 이미지 없음 — 이중 퍼센트 인코딩을 피하기 위해
            # dict 가 아니라 완성된 문자열을 raw bytes 로 직접 전송
            payload = f"subject={_encode_field(subject)}&content={_encode_field(content_html)}"
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            return requests.post(url, data=payload.encode("utf-8"),
                                 headers=headers, timeout=60)
        finally:
            for f in opened_files:
                f.close()

    resp = _send(token)
    if resp.status_code == 401:  # 토큰 만료 — 갱신 후 1회 재시도
        tokens = refresh_access_token(load_tokens())
        resp = _send(tokens["access_token"])

    _last_post_at = time.time()  # 실패한 시도도 도배 방지 카운트에 걸릴 수 있어 항상 기록
    if resp.status_code != 200:
        raise RuntimeError(_format_post_error(resp))

    result = resp.json().get("message", {}).get("result", {})
    return {
        "articleId": result.get("articleId"),
        "articleUrl": result.get("articleUrl") or result.get("cafeUrl"),
        "raw": result,
    }
