# -*- coding: utf-8 -*-
"""환경설정 로더 — .env 파일(있으면)과 환경변수에서 설정을 읽습니다."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _load_env_file():
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_env_file()

# ── 텔레그램 ──────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
# 콤마로 구분된 chat_id 목록. 비워두면 모든 채팅을 허용(테스트용)하되 경고를 출력합니다.
TELEGRAM_ALLOWED_CHAT_IDS = {
    int(x) for x in os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "").replace(" ", "").split(",") if x
}

# ── 네이버 (developers.naver.com 애플리케이션) ─────────────
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "")
NAVER_REDIRECT_URI = os.getenv("NAVER_REDIRECT_URI", "https://localhost/callback")
NAVER_CAFE_CLUB_ID = os.getenv("NAVER_CAFE_CLUB_ID", "")   # 카페 숫자 ID (clubid)
NAVER_CAFE_MENU_ID = os.getenv("NAVER_CAFE_MENU_ID", "")   # 게시판 숫자 ID (menuid)
# 채용공고 전용 게시판 menuid — 비우면 기본 게시판(NAVER_CAFE_MENU_ID)에 올라감
NAVER_CAFE_JOB_MENU_ID = os.getenv("NAVER_CAFE_JOB_MENU_ID", "")
NAVER_TOKEN_FILE = BASE_DIR / "naver_tokens.json"

# ── NewsAPI.org (선택 — '헤드라인' 명령용) ─────────────────
# newsapi.org 에서 무료 키 발급. 무료 등급은 하루 100회 + 기사 24시간 지연 제약이 있어
# '지금 뜨는' 용도로는 '해외이슈'(구글 뉴스 RSS)가 더 낫지만, 깨끗한 JSON·이미지 URL이
# 필요하면 이 키를 채워두면 '헤드라인' 명령으로 국가/카테고리별 톱뉴스를 받아옵니다.
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "").strip()

# ── AI 요약 (선택 — 없으면 og 메타데이터 기반 요약으로 대체) ──
# ① 구글 Gemini (무료 등급) — aistudio.google.com/apikey 에서 발급
# 여러 구글 계정으로 키를 여러 개 만들어 콤마로 나열하면, 한 키가 할당량 초과(429)일 때
# 봇이 자동으로 다음 키로 넘어가서 시도합니다 (무료 등급을 키 개수만큼 늘리는 효과).
# 예: GEMINI_API_KEY=키1,키2,키3
GEMINI_API_KEYS = [k.strip() for k in os.getenv("GEMINI_API_KEY", "").split(",") if k.strip()]
GEMINI_API_KEY = GEMINI_API_KEYS[0] if GEMINI_API_KEYS else ""   # 기존 코드 호환용(첫 키)
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
# ② Claude (유료)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-8")
# ③ 로컬 오픈소스 모델(Ollama) — Gemini/Claude 가 전부 막혔을 때 마지막 폴백.
# 완전 무료·오프라인이지만 이 PC 사양(내장그래픽)에서는 CPU로 돌아 카드 1장에
# 20~60초 정도 걸릴 수 있습니다. 이미지(공고 캡처) 분석은 지원하지 않고 텍스트만 처리합니다.
# 설치: 1) https://ollama.com 에서 Ollama 설치
#      2) cmd 에서 `ollama pull qwen2.5:7b-instruct` 실행 (모델 다운로드, 4GB 정도)
#      3) 아래 값을 채우면 자동으로 마지막 폴백에 사용됨. 비워두면 아예 시도 안 함.
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

# ── 게시글/카드 설정 ─────────────────────────────────────
BRAND_NAME = os.getenv("BRAND_NAME", "공대생현직자 잡앤유")
POST_HEADER = os.getenv("POST_HEADER", "")   # 카페 글 상단에 붙는 문구 (HTML 허용)
POST_FOOTER = os.getenv("POST_FOOTER", "")   # 카페 글 하단에 붙는 문구 (HTML 허용)
# 카페 글에서 링크를 클릭 가능한 <a> 태그로 넣을지(1) 순수 텍스트로 넣을지(0).
# 네이버 카페 API가 링크 태그가 많은 글을 스팸으로 보고 999로 막는 경우가 있어 기본 0.
CAFE_LINKS_AS_ANCHOR = os.getenv("CAFE_LINKS_AS_ANCHOR", "0") == "1"
# 단축주소(buly.kr 등)를 원본 주소로 펼쳐서 올릴지 — 카페 스팸필터(999) 회피용. 기본 켬.
CAFE_EXPAND_SHORT_LINKS = os.getenv("CAFE_EXPAND_SHORT_LINKS", "1") == "1"
MAX_LINKS = int(os.getenv("MAX_LINKS", "5"))              # 메시지당 처리할 최대 링크 수
MAX_CARDS_PER_LINK = int(os.getenv("MAX_CARDS_PER_LINK", "3"))  # 링크당 카드뉴스 장수(1~3)
SEND_CARDS_TO_TELEGRAM = os.getenv("SEND_CARDS_TO_TELEGRAM", "1") == "1"

CARDS_DIR = BASE_DIR / "cards"
FONTS_DIR = BASE_DIR / "fonts"


def naver_configured() -> bool:
    return bool(NAVER_CLIENT_ID and NAVER_CLIENT_SECRET
                and NAVER_CAFE_CLUB_ID and NAVER_CAFE_MENU_ID)
