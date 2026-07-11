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
NAVER_TOKEN_FILE = BASE_DIR / "naver_tokens.json"

# ── AI 요약 (선택 — 없으면 og 메타데이터 기반 요약으로 대체) ──
# ① 구글 Gemini (무료 등급) — aistudio.google.com/apikey 에서 발급
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
# ② Claude (유료)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-8")

# ── 게시글/카드 설정 ─────────────────────────────────────
BRAND_NAME = os.getenv("BRAND_NAME", "공대생현직자 잡앤유")
POST_HEADER = os.getenv("POST_HEADER", "")   # 카페 글 상단에 붙는 문구 (HTML 허용)
POST_FOOTER = os.getenv("POST_FOOTER", "")   # 카페 글 하단에 붙는 문구 (HTML 허용)
MAX_LINKS = int(os.getenv("MAX_LINKS", "5"))              # 메시지당 처리할 최대 링크 수
MAX_CARDS_PER_LINK = int(os.getenv("MAX_CARDS_PER_LINK", "3"))  # 링크당 카드뉴스 장수(1~3)
SEND_CARDS_TO_TELEGRAM = os.getenv("SEND_CARDS_TO_TELEGRAM", "1") == "1"

CARDS_DIR = BASE_DIR / "cards"
FONTS_DIR = BASE_DIR / "fonts"


def naver_configured() -> bool:
    return bool(NAVER_CLIENT_ID and NAVER_CLIENT_SECRET
                and NAVER_CAFE_CLUB_ID and NAVER_CAFE_MENU_ID)
