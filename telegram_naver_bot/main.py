# -*- coding: utf-8 -*-
"""텔레그램 → 네이버카페 자동 게시 봇 (메인 루프).

사용법 (메시지 맨 앞 키워드로 동작 구분):

  ┌ "카페" 로 시작 ─────────────────────────────
  │ 카페
  │ 제목: 7월 첫째주 자동차산업 뉴스
  │ 이번 주 주요 뉴스입니다.
  │ https://n.news... (원하는 것만 남기고 나머지는 지워서 보내기)
  └ → 편집한 그대로 네이버 카페에 글로 게시

  ┌ "카드" 로 시작 ─────────────────────────────
  │ 카드
  │ https://n.news...   (1~3개)
  │ https://n.news...
  └ → 링크마다 헤드라인 후보를 2~3개 제안 → 숫자로 답장하면 그걸로 카드 1장 생성
      카드 뒤에는 기사 요약 + 출처 링크를 별도 메시지로 보내드립니다 (캡션용)
      (AI 가 없어서 후보가 1개뿐이면 고를 필요 없이 바로 생성)

실행: python main.py  (24시간 켜져 있는 서버/PC 에서 실행)
"""
import re
import sys
import threading
import time
import traceback

import config


class _Tee:
    """print 로 찍히는 모든 로그를 화면과 bot.log 파일에 동시에 남긴다.
    (PowerShell 창을 못 봐도 bot.log 를 메모장으로 열면 로그 확인 가능)"""

    def __init__(self, stream, path):
        self.stream = stream
        try:
            self.logfile = open(path, "a", encoding="utf-8", buffering=1)
        except Exception:
            self.logfile = None

    def write(self, data):
        self.stream.write(data)
        try:
            self.stream.flush()   # 버퍼링 때문에 터미널에 실시간으로 안 뜨는 문제 방지
        except Exception:
            pass
        if self.logfile:
            try:
                self.logfile.write(data)
                self.logfile.flush()
            except Exception:
                pass

    def flush(self):
        self.stream.flush()
        if self.logfile:
            try:
                self.logfile.flush()
            except Exception:
                pass


sys.stdout = _Tee(sys.stdout, config.BASE_DIR / "bot.log")
sys.stderr = _Tee(sys.stderr, config.BASE_DIR / "bot.log")

from article import fetch_article, fetch_job_page
from card_news import render_carousel, render_cards
from editor import build_cafe_post, build_job_post
from job_card import render_job_card
from job_summary import build_job_data
from linkutil import expand_short_links
from message_parser import URL_RE, detect_mode, extract_links, split_title_body
from trends import (fetch_google_trends, fetch_naver_news_ranking, fetch_reddit_top,
                    search_naver_news)
from naver_cafe import post_article
from summarize import build_card_options
from telegram_client import TelegramClient

HELP_TEXT = (
    "👋 사용법 — 메시지 맨 앞에 키워드를 붙여주세요.\n\n"
    "📝 카페 글 올리기:\n"
    "  첫 줄에 '카페' 라고 쓰고, 그 아래에 올릴 내용을 넣으세요.\n"
    "  (올리기 싫은 뉴스는 직접 지운 뒤 보내면 됩니다)\n"
    "  예)\n"
    "  카페\n"
    "  제목: 오늘의 뉴스\n"
    "  현대차 하반기 채용 확대\n"
    "  https://n.news...\n\n"
    "🖼 카드뉴스 만들기:\n"
    "  첫 줄에 '카드' 라고 쓰고, 링크 1~3개를 넣으세요.\n"
    "  링크마다 헤드라인 후보를 보여드리면 숫자로 골라주세요.\n"
    "  예)\n"
    "  카드\n"
    "  https://n.news...\n"
    "  https://n.news...\n\n"
    "💼 채용공고 카드 + 카페 게시:\n"
    "  ▸ 가장 추천: 공고 내용을 복사(Ctrl+A, Ctrl+C)해서 '채용' 뒤에 붙여넣고,\n"
    "    마지막 줄에 지원 링크도 함께 넣으세요 — 본문으로 카드를 만들고,\n"
    "    링크는 '공고 원문' 참고용으로만 씁니다 (AI 사용량 절약, 안티봇 회피).\n"
    "    표나 이미지로만 된 부분이 있으면, 텍스트 보낸 뒤 이어서 사진을 보내면\n"
    "    (캡션 없이 그냥 사진만) 합쳐서 반영합니다. 15초 안에 안 보내면\n"
    "    자동으로 진행하고, 바로 진행하려면 '완료' 라고 보내세요.\n"
    "  ▸ 링크만 있어도 자동으로 읽어보긴 하지만, 사이트에 따라 안 될 수 있어요.\n"
    "  ▸ 그래도 안 되면: 공고 화면을 캡처해서 '채용' 캡션과 함께 사진으로 (여러 장 가능)\n"
    "  예)\n"
    "  채용\n"
    "  (공고 내용 전체 붙여넣기)\n"
    "  https://recruit.../apply\n"
    "  → (필요하면 이어서 사진 전송) → '완료' (또는 자동 진행)\n\n"
    "🔗 단축주소 펼치기:\n"
    "  첫 줄에 '펼치기' 라고 쓰고, 단축주소(buly.kr 등)가 든 글을 넣으면\n"
    "  원본 주소로 펼친 전체 글을 그대로 돌려드립니다.\n\n"
    "📰 뉴스 검색 (산업/키워드 화제 기사 찾기):\n"
    "  '뉴스' + 키워드 — 최근 화제 기사를 언론사 보도 개수 순으로 추천합니다.\n"
    "  예) 뉴스 자동차산업\n\n"
    "🔥 실시간 트렌드 (분야 무관, 지금 뜨는 검색어):\n"
    "  '트렌드' (기본 국내) 또는 '트렌드 미국/일본/영국' 등\n"
    "  지금 인기 검색어와 관련 뉴스를 보여드립니다.\n\n"
    "🇰🇷 국내 핫이슈 (키워드 없이 지금 많이 읽히는 기사):\n"
    "  '국내이슈' 라고 보내면 네이버 뉴스 랭킹 상위 기사를 추천합니다.\n\n"
    "🌍 해외 핫이슈 (키워드 없이 지금 전세계 화제 뉴스):\n"
    "  '해외이슈' 라고 보내면 레딧 r/worldnews 인기글을 추천합니다.\n\n"
    "🛑 멈추기:\n"
    "  처리가 오래 걸리거나 멈춘 것 같으면 '취소' 라고 보내면 즉시 중단합니다."
)

# 링크당 카드 선택 후보 개수 (2~3)
N_OPTIONS = max(2, min(3, config.MAX_CARDS_PER_LINK or 3))

# chat_id 별로 "카드 후보 선택 대기" 상태를 들고 있음 (봇 재시작 시 초기화됨)
# {chat_id: {"queue": [url, ...], "link_idx": int, "made": int, "stamp": int,
#            "article": dict|None, "options": list|None, "extras": dict|None}}
PENDING_CARD: dict = {}

# 채용공고: 텍스트를 먼저 받고 "이어서 사진 보내주세요" 하며 잠깐 기다리는 상태.
# {chat_id: {"text", "link", "images": [...], "photo_paths": [...],
#            "created": float, "timer": threading.Timer|None, "extensions": int}}
PENDING_JOB: dict = {}
_pending_job_lock = threading.Lock()

JOB_WAIT_SECONDS = 15     # 텍스트만 온 뒤 이미지를 기다리는 시간(초)
JOB_WAIT_EXTEND = 10      # 이미지가 오면 추가로 더 기다려주는 시간(초)
JOB_MAX_EXTENSIONS = 3    # 이미지 배치를 몇 번까지 더 기다려줄지
JOB_MAX_WAIT = 60         # 첫 텍스트 이후 최대 총 대기 시간(초)

RAW_TG = None   # main() 에서 설정 — 타이머 콜백 등 워커 밖에서 쓸 원본 텔레그램 클라이언트


# ── 카페 글 게시 ─────────────────────────────────────────

def handle_cafe(tg: TelegramClient, chat_id: int, content: str):
    title, body = split_title_body(content)
    if not (title or body.strip()):
        tg.send_message(chat_id, "⚠️ '카페' 아래에 올릴 내용을 함께 보내주세요.")
        return

    # 단축주소(buly.kr 등)는 원본 주소로 펼친다 — 네이버 스팸필터(999) 회피
    if config.CAFE_EXPAND_SHORT_LINKS:
        try:
            body = expand_short_links(body)
        except Exception as e:
            print(f"[main] 단축주소 펼침 실패(무시): {e}")

    subject, content_html = build_cafe_post(title, body)

    if not config.naver_configured():
        tg.send_message(chat_id,
                        "ℹ️ 네이버 API 설정이 아직 없어 카페 게시를 건너뜁니다.\n"
                        f"(작성될 제목: {subject})\n"
                        "README 의 '네이버 API 준비' 를 마치면 자동 게시됩니다.")
        return

    tg.send_message(chat_id, "⏳ 카페에 글을 올리는 중...")
    result = post_article(subject, content_html, image_paths=None)
    url = result.get("articleUrl") or "(URL 확인 불가)"
    tg.send_message(chat_id, f"✅ 카페 게시 완료!\n제목: {subject}\n{url}")


# ── 단축주소 펼쳐서 되돌려주기 ────────────────────────────

def handle_expand(tg: TelegramClient, chat_id: int, content: str):
    """받은 글 속 단축주소를 원본 주소로 펼쳐서, 편집한 전체 글을 그대로 돌려준다."""
    if not content.strip():
        tg.send_message(chat_id, "⚠️ '펼치기' 아래에 단축주소가 든 글을 함께 보내주세요.")
        return
    tg.send_message(chat_id, "⏳ 단축주소를 펼치는 중...")
    try:
        expanded = expand_short_links(content)
    except Exception as e:
        tg.send_message(chat_id, f"⚠️ 펼치기 실패: {e}")
        return
    if expanded == content:
        tg.send_message(chat_id, "ℹ️ 펼칠 단축주소를 찾지 못했어요 (이미 원본 주소이거나 지원 안 하는 도메인).")
    tg.send_message(chat_id, expanded)


# ── 뉴스 검색 / 실시간 트렌드 ─────────────────────────────

def handle_news_search(tg: TelegramClient, chat_id: int, keyword: str):
    """네이버 뉴스 검색 — 키워드 관련 최근 화제 기사(여러 언론사가 다룬 순)를 추천."""
    keyword = keyword.strip()
    if not keyword:
        tg.send_message(chat_id, "⚠️ '뉴스' 뒤에 검색할 산업/키워드를 넣어주세요.\n예) 뉴스 자동차산업")
        return
    if not (config.NAVER_CLIENT_ID and config.NAVER_CLIENT_SECRET):
        tg.send_message(chat_id, "ℹ️ 네이버 API(NAVER_CLIENT_ID/SECRET)가 .env 에 없어 뉴스 검색을 할 수 없어요.")
        return

    tg.send_message(chat_id, f"⏳ '{keyword}' 관련 최근 화제 기사를 찾는 중...")
    try:
        results = search_naver_news(keyword, count=8)
    except Exception as e:
        tg.send_message(chat_id, f"⚠️ 뉴스 검색 실패: {e}")
        return
    if not results:
        tg.send_message(chat_id, f"최근 48시간 내 '{keyword}' 관련 기사를 찾지 못했어요. "
                                 "키워드를 좀 더 넓게 해보세요.")
        return

    lines = [f"📰 '{keyword}' 최근 화제 기사 (여러 언론사가 다룬 순)"]
    for i, r in enumerate(results, 1):
        tag = f" — 언론사 {r['count']}곳 보도" if r["count"] > 1 else ""
        lines.append(f"{i}. {r['title']}{tag}\n{r['link']}")
    lines.append("\n마음에 드는 링크를 복사해서 '카드' 또는 '채용' 뒤에 붙이면 바로 쓸 수 있어요.")
    tg.send_message(chat_id, "\n\n".join(lines))


_TREND_REGION_MAP = {
    "미국": "US", "일본": "JP", "영국": "GB", "독일": "DE", "인도": "IN",
    "프랑스": "FR", "브라질": "BR", "캐나다": "CA", "한국": "KR", "국내": "KR",
}


def handle_trends(tg: TelegramClient, chat_id: int, region_text: str):
    """구글 트렌드 — 특정 산업에 한정되지 않는 국내/해외 실시간 인기 검색어 + 관련 뉴스.
    ⚠️ 비공식 RSS 피드라 형식이 바뀌면 실패할 수 있음 (실패 시 로그를 보고 조정 필요)."""
    region_text = (region_text or "").strip()
    geo, geo_label = "KR", "국내"
    for name, code in _TREND_REGION_MAP.items():
        if name in region_text:
            geo, geo_label = code, name
            break

    tg.send_message(chat_id, f"⏳ 구글 트렌드({geo_label}) 확인 중...")
    try:
        trends = fetch_google_trends(geo=geo, count=8)
    except Exception as e:
        tg.send_message(chat_id, f"⚠️ 트렌드 조회 실패: {e}\n"
                                 "(구글 트렌드는 비공식 피드라 형식이 바뀌었을 수 있어요 — "
                                 "이 오류 내용을 보여주시면 바로 고칠게요)")
        return
    if not trends:
        tg.send_message(chat_id, "지금 트렌드 데이터를 가져오지 못했어요.")
        return

    lines = [f"🔥 지금 뜨는 검색어 ({geo_label})"]
    for i, t in enumerate(trends, 1):
        line = f"{i}. {t['title']}"
        if t.get("traffic"):
            line += f" ({t['traffic']})"
        if t.get("articles"):
            a = t["articles"][0]
            src = f" ({a['source']})" if a.get("source") else ""
            line += f"\n   → {a['title']}{src}\n   {a['link']}"
        lines.append(line)
    lines.append("\n마음에 드는 링크를 복사해서 '카드' 또는 '채용' 뒤에 붙이면 바로 쓸 수 있어요.")
    tg.send_message(chat_id, "\n\n".join(lines))


def handle_domestic_issues(tg: TelegramClient, chat_id: int, _rest: str):
    """네이버 뉴스 '많이 본 뉴스' — 키워드 없이 지금 국내에서 화제인 기사 자체를 추천."""
    tg.send_message(chat_id, "⏳ 국내 핫이슈(네이버 뉴스 랭킹) 확인 중...")
    try:
        results = fetch_naver_news_ranking(count=8)
    except Exception as e:
        tg.send_message(chat_id, f"⚠️ 국내 이슈 조회 실패: {e}\n"
                                 "(공식 API 가 아니라 페이지 구조 변경에 취약해요 — "
                                 "이 오류 내용을 보여주시면 바로 고칠게요)")
        return
    lines = ["🇰🇷 지금 국내에서 많이 읽히는 기사"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}\n{r['link']}")
    lines.append("\n마음에 드는 링크를 복사해서 '카드' 또는 '채용' 뒤에 붙이면 바로 쓸 수 있어요.")
    tg.send_message(chat_id, "\n\n".join(lines))


def handle_global_issues(tg: TelegramClient, chat_id: int, _rest: str):
    """레딧 r/worldnews 인기글 — 키워드 없이 지금 전세계에서 화제인 뉴스를 추천."""
    tg.send_message(chat_id, "⏳ 전세계 핫이슈(레딧 r/worldnews) 확인 중...")
    try:
        results = fetch_reddit_top(subreddit="worldnews", count=8)
    except Exception as e:
        tg.send_message(chat_id, f"⚠️ 해외 이슈 조회 실패: {e}\n"
                                 "(공식 API 가 아니라 레딧 정책 변경에 취약해요 — "
                                 "이 오류 내용을 보여주시면 바로 고칠게요)")
        return
    lines = ["🌍 지금 전세계에서 화제인 뉴스 (r/worldnews 인기글)"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']} (👍{r['score']:,} · {r['domain']})\n{r['link']}")
    lines.append("\n마음에 드는 링크를 복사해서 '카드' 또는 '채용' 뒤에 붙이면 바로 쓸 수 있어요.\n"
                "(영어 기사면 번역해서 카드를 만들어드릴 수도 있어요)")
    tg.send_message(chat_id, "\n\n".join(lines))


# ── 채용공고 카드 + 카페 게시 ─────────────────────────────

def _fetch_logo(page: dict):
    """공고 페이지에서 회사 로고 이미지를 받아온다 (실패하면 None → 회사명 뱃지로 대체)."""
    import io

    from PIL import Image

    from article import fetch_image_bytes
    for url in (page.get("logo_url"), page.get("og_image_url")):
        if not url:
            continue
        try:
            img = Image.open(io.BytesIO(fetch_image_bytes(url, referer=page.get("url", ""))))
            if img.width >= 48 and img.height >= 48:   # 파비콘급(16px)은 제외
                return img
        except Exception as e:
            print(f"[main] 로고 다운로드 실패({url}): {e}")
    return None


def _handle_one_job(tg: TelegramClient, chat_id: int, page: dict, idx: int,
                    images=None, photo_paths=None):
    """photo_paths: 사용자가 보낸 공고 캡처 원본 파일 — 카페 글에 함께 첨부"""
    job, summary, engine, err = build_job_data(page, images=images)
    if job is None:
        tg.send_message(chat_id, f"⚠️ 채용공고 {idx} 분석 실패: {err}")
        return

    # 1) 카드 렌더링 → 텔레그램 전송
    path = render_job_card(job, f"job_{int(time.time())}_{idx}", logo=_fetch_logo(page))
    caption = " ".join(t.strip() for t in (job.get("title") or "").split("/"))
    tg.send_photo(chat_id, path, caption=caption[:80])

    # 2) 정리 텍스트 (SNS 캡션/검수용)
    if summary:
        text = f"📝 채용 요약\n{summary}"
        if page.get("url"):
            text += f"\n\n공고 링크: {page['url']}"
        tg.send_message(chat_id, text)

    # 3) 카페 게시 (채용 게시판)
    if not config.naver_configured():
        tg.send_message(chat_id, "ℹ️ 네이버 API 설정이 없어 카페 게시는 건너뜁니다.")
        return
    if not config.NAVER_CAFE_JOB_MENU_ID:
        tg.send_message(chat_id,
                        "ℹ️ 채용 게시판(NAVER_CAFE_JOB_MENU_ID)이 .env 에 없어 "
                        "카페 게시를 건너뜁니다. 게시판 menuid 를 설정해주세요.")
        return

    tg.send_message(chat_id, "⏳ 카페(채용 게시판)에 올리는 중...")
    subject, content_html = build_job_post(job, summary, page.get("url", ""))
    # 첨부 이미지: 만든 카드 + 사용자가 보낸 공고 캡처 원본들
    cafe_images = [path] + list(photo_paths or [])
    try:
        # 이미지를 첨부해서 게시 시도 → 실패하면 텍스트만으로 재시도
        try:
            result = post_article(subject, content_html, image_paths=cafe_images,
                                  menu_id=config.NAVER_CAFE_JOB_MENU_ID)
        except Exception as e:
            print(f"[main] 이미지 첨부 게시 실패, 텍스트만 재시도: {e}")
            result = post_article(subject, content_html, image_paths=None,
                                  menu_id=config.NAVER_CAFE_JOB_MENU_ID)
        url = result.get("articleUrl") or "(URL 확인 불가)"
        tg.send_message(chat_id, f"✅ 카페 게시 완료!\n제목: {subject}\n{url}")
    except Exception as e:
        tg.send_message(chat_id, f"⚠️ 카페 게시 실패: {e}")


def _download_photos(tg, files: list, stamp: int):
    """files: [(file_id, mime_type), ...] — '사진'으로 보내든 '파일(문서)'로 보내든
    실제 mime_type 을 그대로 써서 내려받는다.
    returns (AI 비전용 base64 목록, 카페 첨부용 원본 파일 경로 목록)."""
    import base64

    config.CARDS_DIR.mkdir(parents=True, exist_ok=True)
    images, photo_paths = [], []
    for n, (fid, mime) in enumerate(files[:5], 1):
        try:
            raw = tg.download_file(fid)
            mime = mime or "image/jpeg"
            images.append((mime, base64.b64encode(raw).decode()))
            ext = ".png" if "png" in mime else ".jpg"
            p = config.CARDS_DIR / f"job_src_{stamp}_{n}{ext}"   # 카페 첨부용 원본 보관
            p.write_bytes(raw)
            photo_paths.append(p)
        except Exception as e:
            print(f"[main] 사진 다운로드 실패: {e}")
    return images, photo_paths


def _run_finalize_job(tg, chat_id, text: str, link: str, images: list, photo_paths: list):
    """모아둔 텍스트(+이미지)로 실제 카드 생성/카페 게시를 진행."""
    tg.send_message(chat_id, "⏳ 채용공고 분석 중...")
    page = {"url": link or "", "title": "", "description": "", "text": text[:9000]}
    _handle_one_job(tg, chat_id, page, 1, images=images or None, photo_paths=photo_paths or None)


def _cancel_pending_job(chat_id):
    """대기 중인 채용공고 큐를 취소하고, 있었으면 그 상태를 반환."""
    with _pending_job_lock:
        state = PENDING_JOB.pop(chat_id, None)
    if state and state.get("timer"):
        try:
            state["timer"].cancel()
        except Exception:
            pass
    return state


def _on_job_timer_fire(chat_id):
    """대기 시간이 끝났을 때 호출 — 지금까지 모인 내용으로 진행."""
    with _pending_job_lock:
        state = PENDING_JOB.pop(chat_id, None)
    if state is None:
        return   # 이미 취소됐거나 '완료'로 먼저 처리됨
    if _work_busy():
        # 다른 작업이 도는 중이면 잠깐 후 재시도
        with _pending_job_lock:
            PENDING_JOB[chat_id] = state
        retry = threading.Timer(3.0, _on_job_timer_fire, args=(chat_id,))
        retry.daemon = True
        state["timer"] = retry
        retry.start()
        return
    _start_work(RAW_TG, chat_id, _run_finalize_job,
               state["text"], state["link"], state["images"], state["photo_paths"])


def _queue_job_text(tg, chat_id, text: str, link: str):
    """공고 텍스트를 받으면 바로 만들지 않고, 이어서 올 사진을 잠깐 기다린다."""
    prev = _cancel_pending_job(chat_id)
    if prev:
        tg.send_message(chat_id, "⚠️ 대기 중이던 이전 채용공고 요청은 취소하고 새 내용으로 진행할게요.")

    with _pending_job_lock:
        PENDING_JOB[chat_id] = {"text": text, "link": link, "images": [], "photo_paths": [],
                                "created": time.time(), "timer": None, "extensions": 0}
    timer = threading.Timer(JOB_WAIT_SECONDS, _on_job_timer_fire, args=(chat_id,))
    timer.daemon = True
    with _pending_job_lock:
        if chat_id in PENDING_JOB:
            PENDING_JOB[chat_id]["timer"] = timer
    timer.start()
    tg.send_message(chat_id,
                    "✅ 텍스트 확인했어요. 표나 이미지로만 된 부분이 있으면 이어서 사진으로 보내주세요.\n"
                    f"{JOB_WAIT_SECONDS}초 안에 안 오면 자동으로 진행할게요. "
                    "(바로 진행하려면 '완료' 라고 보내주세요)")


def _append_pending_job_photos(tg, chat_id, file_ids: list):
    """대기 중인 채용공고에 이어서 온 사진을 추가하고, 대기 시간을 조금 더 늘린다."""
    with _pending_job_lock:
        exists = chat_id in PENDING_JOB
    if not exists:
        tg.send_message(chat_id, "ℹ️ 대기 중인 채용공고가 없어요. 먼저 '채용' + 내용을 보내주세요.")
        return

    new_images, new_paths = _download_photos(tg, file_ids, int(time.time()))
    if not new_images:
        tg.send_message(chat_id, "⚠️ 사진을 내려받지 못했어요. 다시 보내주세요.")
        return

    with _pending_job_lock:
        state = PENDING_JOB.get(chat_id)
        if state is None:
            state = None
        else:
            if state.get("timer"):
                try:
                    state["timer"].cancel()
                except Exception:
                    pass
            state["images"].extend(new_images)
            state["photo_paths"].extend(new_paths)
            state["extensions"] += 1
    if state is None:
        tg.send_message(chat_id, "ℹ️ 이미 처리가 진행돼서 이 사진은 반영하지 못했어요.")
        return

    elapsed = time.time() - state["created"]
    if state["extensions"] > JOB_MAX_EXTENSIONS or elapsed > JOB_MAX_WAIT:
        with _pending_job_lock:
            PENDING_JOB.pop(chat_id, None)
        tg.send_message(chat_id, f"🖼 이미지 {len(new_images)}장 받았어요. 바로 반영해서 만들게요.")
        _run_finalize_job(tg, chat_id, state["text"], state["link"],
                          state["images"], state["photo_paths"])
        return

    timer = threading.Timer(JOB_WAIT_EXTEND, _on_job_timer_fire, args=(chat_id,))
    timer.daemon = True
    with _pending_job_lock:
        if chat_id in PENDING_JOB:
            PENDING_JOB[chat_id]["timer"] = timer
    timer.start()
    tg.send_message(chat_id,
                    f"🖼 이미지 {len(new_images)}장 추가로 받았어요. {JOB_WAIT_EXTEND}초 더 기다렸다가 반영할게요.\n"
                    "(더 없으면 '완료' 라고 보내면 바로 진행해요)")


def _finish_pending_job_now(tg, chat_id):
    """'완료' 명령 — 대기 중인 채용공고를 기다리지 않고 바로 진행."""
    state = _cancel_pending_job(chat_id)
    if state is None:
        tg.send_message(chat_id, "대기 중인 채용공고가 없어요.")
        return
    if _work_busy():
        tg.send_message(chat_id, "⏳ 지금 다른 작업 중이라 완료 요청을 반영하지 못했어요. 잠시 후 다시 시도해주세요.")
        return
    _start_work(tg, chat_id, _run_finalize_job,
               state["text"], state["link"], state["images"], state["photo_paths"])


def handle_job(tg: TelegramClient, chat_id: int, content: str):
    links = extract_links(content)[: config.MAX_LINKS]

    # 링크와 함께 공고 본문도 넉넉히 붙여넣은 경우 — 본문으로 카드를 만들고,
    # 링크는 fetch/캡처 없이 '공고 원문' 참고용으로만 사용 (토큰 절약 + 안티봇 회피).
    # 표/이미지로만 된 부분이 있을 수 있으니, 곧바로 만들지 않고 이어서 올 사진을 잠깐 기다린다.
    text_without_links = URL_RE.sub("", content).strip()
    if links and len(text_without_links) >= 80:
        _queue_job_text(tg, chat_id, text_without_links, links[0])
        return

    if links:
        for i, url in enumerate(links, 1):
            tg.send_message(chat_id, f"⏳ 채용공고 {i}/{len(links)} 분석 중...")
            try:
                page = fetch_job_page(url)
                text_len = len(page.get("text") or "")

                # 텍스트를 충분히 못 읽었으면(안티봇/이미지 공고 등) 화면 캡처를
                # 시도하는 대신, 공고 내용을 복사해 붙이거나 사진으로 보내달라고 안내한다
                # — 자동 캡처는 안티봇 회피와 지연 로딩 콘텐츠 확보가 서로 충돌해 불안정했다.
                if text_len < 500:
                    try:
                        import playwright  # noqa: F401 — 설치 여부만 확인
                        hint = ("이 사이트는 자동으로 내용을 못 읽어요 (보안이 강하거나 이미지 공고).\n"
                                "공고 내용을 복사해서 '채용' 뒤에 붙이거나,\n"
                                "공고 화면을 캡처해서 '채용' 캡션과 함께 사진으로 보내주세요. (여러 장 가능)")
                    except ImportError:
                        hint = ("이런 사이트를 자동으로 읽으려면 명령창(cmd)에서 아래 두 줄을\n"
                                "한 번만 실행하고 봇을 재시작해주세요:\n"
                                "  pip install playwright\n"
                                "  playwright install chromium\n"
                                "또는 공고 내용을 복사해서 '채용' 뒤에 붙이거나,\n"
                                "공고 화면을 캡처해서 '채용' 캡션과 함께 사진으로 보내도 됩니다.")
                    tg.send_message(chat_id, f"⚠️ 링크 {i} 자동 분석에 실패했어요.\n{hint}")
                    continue
                _handle_one_job(tg, chat_id, page, i)
            except Exception as e:
                tg.send_message(chat_id, f"⚠️ 채용공고 {i} 처리 실패: {e}")
        return

    # 링크 없이 공고 본문을 직접 붙여넣은 경우 — 마찬가지로 이어서 올 사진을 잠깐 기다린다.
    if len(content.strip()) >= 80:
        _queue_job_text(tg, chat_id, content.strip(), "")
        return

    tg.send_message(chat_id, "⚠️ '채용' 아래에 채용공고 링크(또는 공고 내용 전체)를 함께 보내주세요.\n"
                             "공고가 이미지거나 링크가 안 읽히면, 공고 화면을 캡처해서\n"
                             "'채용' 캡션과 함께 사진으로 보내주세요.")


def handle_job_photos(tg: TelegramClient, chat_id: int, caption_rest: str, file_ids: list):
    """캡처 사진으로 받은 채용공고 — AI 비전으로 이미지에서 직접 추출."""
    tg.send_message(chat_id, f"⏳ 공고 사진 {len(file_ids)}장 분석 중...")
    images, photo_paths = _download_photos(tg, file_ids, int(time.time()))
    if not images:
        tg.send_message(chat_id, "⚠️ 사진을 내려받지 못했어요. 다시 보내주세요.")
        return

    page = {"url": "", "title": "", "description": "",
            "text": caption_rest.strip() or "(첨부 이미지 참조)"}
    _handle_one_job(tg, chat_id, page, 1, images=images, photo_paths=photo_paths)


# ── 카드뉴스 제작 (헤드라인 후보 선택 방식) ─────────────────

def _format_options(options: list) -> str:
    lines = ["📝 헤드라인 후보 — 숫자로 답장해서 골라주세요:"]
    for i, opt in enumerate(options, 1):
        headline = (opt.get("headline") or "").replace("\n", " / ")
        tag = f"[{opt['tag']}] " if opt.get("tag") else ""
        lines.append(f"{i}. {tag}{headline}")
    return "\n".join(lines)


def _send_caption_text(tg: TelegramClient, chat_id: int, art: dict, extras: dict):
    """인스타 업로드 시 바로 붙여넣을 캡션(+제목/출처)을 별도 메시지로 전송."""
    extras = extras or {}
    parts = []
    title = art.get("title") or ""
    if title:
        parts.append(f"📰 {title}")
    caption = (extras.get("caption") or "").strip()
    if caption:
        parts.append(f"📋 인스타 캡션 (복사해서 사용)\n{caption}")
    elif (extras.get("summary") or "").strip():
        parts.append(f"📝 요약\n{extras['summary']}")
    url = art.get("url", "")
    if url:
        parts.append(f"\n출처: {url}")
    if parts:
        tg.send_message(chat_id, "\n".join(parts))


def _finish_link(tg: TelegramClient, chat_id: int, card: dict, art: dict, state: dict):
    """선택(또는 자동 확정)된 헤드라인으로 캐러셀(1~4장)을 렌더링해서 보내고 다음 링크로 진행."""
    try:
        paths = render_carousel(card, art, state.get("extras") or {},
                                f"{state['stamp']}_{state['link_idx']}")
        for i, p in enumerate(paths, 1):
            tg.send_photo(chat_id, p, caption=f"{i}/{len(paths)}장" if len(paths) > 1 else "")
        state["made"] += len(paths)
        _send_caption_text(tg, chat_id, art, state.get("extras") or {})
    except Exception as e:
        tg.send_message(chat_id, f"⚠️ 링크 {state['link_idx']} 카드뉴스 생성 실패: {e}")
    _advance(tg, chat_id)


def _advance(tg: TelegramClient, chat_id: int):
    """대기열의 다음 링크를 처리 — 후보가 여럿이면 물어보고, 하나뿐이면 바로 생성."""
    state = PENDING_CARD.get(chat_id)
    if not state:
        return
    state["article"] = None
    state["options"] = None
    state["extras"] = None

    if not state["queue"]:
        tg.send_message(chat_id, f"✅ 카드뉴스 {state['made']}장 완성!")
        PENDING_CARD.pop(chat_id, None)
        return

    url = state["queue"].pop(0)
    state["link_idx"] += 1
    try:
        art = fetch_article(url)
    except Exception as e:
        tg.send_message(chat_id, f"⚠️ 링크 {state['link_idx']} 수집 실패({url}): {e}")
        _advance(tg, chat_id)
        return

    try:
        options, engine, err, extras = build_card_options(art, N_OPTIONS)
    except Exception as e:
        tg.send_message(chat_id, f"⚠️ 링크 {state['link_idx']} 요약 실패: {e}")
        _advance(tg, chat_id)
        return

    state["extras"] = extras

    if len(options) <= 1:
        # AI 를 못 썼거나 실패 — 고를 필요 없이 바로 그 하나로 카드 생성
        if engine == "heuristic" and (config.GEMINI_API_KEY or config.ANTHROPIC_API_KEY):
            tg.send_message(chat_id, f"⚠️ AI 요약 실패로 기본 제목을 사용해요.\n사유: {err}")
        card = options[0] if options else {"headline": art.get("title", "")[:40]}
        _finish_link(tg, chat_id, card, art, state)
        return

    state["article"] = art
    state["options"] = options
    tg.send_message(chat_id, f"[링크 {state['link_idx']}] " + _format_options(options))


def handle_card(tg: TelegramClient, chat_id: int, content: str):
    links = extract_links(content)[: config.MAX_LINKS]
    if not links:
        tg.send_message(chat_id, "⚠️ '카드' 아래에 뉴스 링크(1~3개)를 함께 보내주세요.")
        return

    PENDING_CARD[chat_id] = {
        "queue": links,
        "link_idx": 0,
        "made": 0,
        "stamp": int(time.time()),
        "article": None,
        "options": None,
        "extras": None,
    }
    tg.send_message(chat_id, f"⏳ 카드뉴스 준비 중 — 링크 {len(links)}개")
    _advance(tg, chat_id)


def _resolve_selection_work(tg, chat_id: int, text: str):
    """후보 선택 숫자 답장을 워커에서 처리 — 선택한 헤드라인으로 카드 생성."""
    state = PENDING_CARD.get(chat_id)
    if not state or not state.get("options"):
        return
    options = state["options"]
    m = re.match(r"\s*([1-9])", text.strip())
    if not m or int(m.group(1)) > len(options):
        tg.send_message(chat_id, f"1~{len(options)} 중에서 숫자로 골라주세요.")
        return
    chosen = options[int(m.group(1)) - 1]
    _finish_link(tg, chat_id, chosen, state["article"], state)


# ── 메인 루프 ────────────────────────────────────────────

def handle_message(tg: TelegramClient, chat_id: int, text: str):
    mode, content = detect_mode(text)
    if mode == "cafe":
        handle_cafe(tg, chat_id, content)
    elif mode == "card":
        handle_card(tg, chat_id, content)
    elif mode == "job":
        handle_job(tg, chat_id, content)
    elif mode == "expand":
        handle_expand(tg, chat_id, content)
    elif mode == "news":
        handle_news_search(tg, chat_id, content)
    elif mode == "trend":
        handle_trends(tg, chat_id, content)
    elif mode == "domestic_issue":
        handle_domestic_issues(tg, chat_id, content)
    elif mode == "global_issue":
        handle_global_issues(tg, chat_id, content)
    else:
        tg.send_message(chat_id, HELP_TEXT)


# ── 백그라운드 처리 + 취소 ────────────────────────────────
# 무거운 작업(공고 분석/카드 생성/카페 게시)을 워커 스레드로 돌려서,
# 처리 중에도 봇이 '취소' 메시지를 받아 멈출 수 있게 한다.

class _Cancelled(Exception):
    """작업이 취소됨 — 워커를 조용히 중단시키는 신호."""


class _CancelTG:
    """텔레그램 전송 직전마다 취소 여부를 확인하는 래퍼.
    취소되면 다음 전송 지점에서 _Cancelled 를 던져 작업을 중단시킨다."""

    def __init__(self, tg, cancel_event):
        self._tg = tg
        self._cancel = cancel_event

    def _check(self):
        if self._cancel.is_set():
            raise _Cancelled()

    def send_message(self, *a, **k):
        self._check()
        return self._tg.send_message(*a, **k)

    def send_photo(self, *a, **k):
        self._check()
        return self._tg.send_photo(*a, **k)

    def download_file(self, *a, **k):
        self._check()
        return self._tg.download_file(*a, **k)


WORK = {"thread": None, "cancel": None}


def _work_busy() -> bool:
    t = WORK.get("thread")
    return t is not None and t.is_alive()


def _start_work(tg, chat_id, target, *args):
    """target(ctg, chat_id, *args) 를 워커 스레드에서 실행."""
    cancel = threading.Event()
    ctg = _CancelTG(tg, cancel)

    def _run():
        try:
            target(ctg, chat_id, *args)
        except _Cancelled:
            print("[main] 작업이 사용자 요청으로 취소되었습니다.")
        except Exception as e:
            traceback.print_exc()
            try:
                tg.send_message(chat_id, f"❌ 처리 중 오류: {e}")
            except Exception:
                pass

    th = threading.Thread(target=_run, daemon=True)
    WORK["thread"] = th
    WORK["cancel"] = cancel
    th.start()


def _cancel_current(tg, chat_id):
    busy = _work_busy()
    if busy and WORK.get("cancel"):
        WORK["cancel"].set()          # 워커에게 중단 신호
    WORK["thread"] = None             # 슬롯을 즉시 비워 새 작업을 바로 받을 수 있게
    PENDING_CARD.pop(chat_id, None)
    had_pending_job = _cancel_pending_job(chat_id) is not None
    if busy:
        tg.send_message(chat_id, "🛑 진행 중이던 작업을 멈췄어요. 새로 시작하셔도 됩니다.")
    elif had_pending_job:
        tg.send_message(chat_id, "🛑 대기 중이던 채용공고 요청을 취소했어요.")
    else:
        tg.send_message(chat_id, "멈출 작업이 없어요. (이미 끝났거나 대기 중)")


def main():
    if not config.TELEGRAM_BOT_TOKEN:
        raise SystemExit(".env 에 TELEGRAM_BOT_TOKEN 을 설정하세요. (@BotFather 에서 발급)")
    if not config.TELEGRAM_ALLOWED_CHAT_IDS:
        print("⚠️ TELEGRAM_ALLOWED_CHAT_IDS 가 비어 있어 모든 채팅을 허용합니다. "
              "봇에게 아무 메시지나 보내면 chat_id 가 로그에 출력되니 그 값을 .env 에 넣으세요.")

    global RAW_TG
    tg = TelegramClient(config.TELEGRAM_BOT_TOKEN)
    RAW_TG = tg
    offset = None
    print("🤖 봇 시작 — 텔레그램 메시지를 기다립니다...")

    while True:
        try:
            updates = tg.get_updates(offset=offset)
        except Exception as e:
            print(f"getUpdates 오류, 5초 후 재시도: {e}")
            time.sleep(5)
            continue

        if updates:
            print(f"[main] getUpdates 로 {len(updates)}개 수신")
        for upd in updates:
            msg_dbg = upd.get("message") or {}
            kinds = [k for k in ("text", "photo", "document", "caption") if k in msg_dbg]
            print(f"[main] RAW update_id={upd.get('update_id')} 필드={kinds} "
                 f"mime={(msg_dbg.get('document') or {}).get('mime_type')}")

        # 같은 배치 안의 사진 앨범(media_group)을 하나로 묶는다
        photo_groups = {}   # group_key -> {"chat_id", "caption", "file_ids"}

        for upd in updates:
            offset = upd["update_id"] + 1
            msg = upd.get("message") or {}
            chat_id = (msg.get("chat") or {}).get("id")
            if chat_id is None:
                continue
            if config.TELEGRAM_ALLOWED_CHAT_IDS and chat_id not in config.TELEGRAM_ALLOWED_CHAT_IDS:
                print(f"[main] 허용되지 않은 chat_id={chat_id} — 무시")
                continue

            # 사진(압축) 또는 이미지 파일(문서로 첨부) 메시지 — 앨범 단위로 모아서 처리.
            # 텔레그램에서 클립 아이콘으로 '파일' 선택해 원본 그대로 보내면 photo 가 아니라
            # document 로 오는데, 이것도 이미지(mime_type 이 image/*)면 똑같이 인식한다.
            img_file = None
            if msg.get("photo"):
                img_file = (msg["photo"][-1]["file_id"], "image/jpeg")   # 압축 사진은 항상 JPEG
            else:
                doc = msg.get("document") or {}
                mime = doc.get("mime_type") or ""
                if doc.get("file_id") and mime.startswith("image/"):
                    img_file = (doc["file_id"], mime)

            if img_file:
                key = msg.get("media_group_id") or f"single_{msg.get('message_id')}"
                g = photo_groups.setdefault(key, {"chat_id": chat_id, "caption": "",
                                                  "file_ids": []})
                g["file_ids"].append(img_file)
                if msg.get("caption"):
                    g["caption"] = (g["caption"] + "\n" + msg["caption"]).strip()
                continue

            text = msg.get("text") or ""
            if not text.strip():
                continue
            print(f"[main] 메시지 수신 chat_id={chat_id}")
            try:
                mode0, _rest = detect_mode(text)

                # '취소'/'중지' — 처리 중에도 항상 즉시 반응 (봇이 안 멈춰있도록)
                if mode0 == "cancel":
                    _cancel_current(tg, chat_id)
                    continue

                # '완료' — 채용공고 사진을 기다리는 중이면 기다리지 않고 바로 진행
                if mode0 == "finish":
                    _finish_pending_job_now(tg, chat_id)
                    continue

                # 다른 작업이 도는 중이면 새 요청은 막고 안내
                if _work_busy():
                    tg.send_message(chat_id, "⏳ 지금 앞의 작업을 처리하고 있어요.\n"
                                             "멈추려면 '취소' 라고 보내주세요.")
                    continue

                # 카드 후보 선택 대기 중 — 숫자 답장이면 그 카드로 진행(워커에서)
                if chat_id in PENDING_CARD and PENDING_CARD[chat_id].get("options"):
                    if re.match(r"\s*[1-9]", text):
                        _start_work(tg, chat_id, _resolve_selection_work, text)
                    else:
                        PENDING_CARD.pop(chat_id, None)
                        tg.send_message(chat_id, "⚠️ 진행 중이던 선택은 취소하고 새 요청을 처리할게요. "
                                                 "(후보를 고르려면 숫자만 답장해주세요)")
                        _start_work(tg, chat_id, handle_message, text)
                    continue

                _start_work(tg, chat_id, handle_message, text)
            except Exception as e:
                traceback.print_exc()
                try:
                    tg.send_message(chat_id, f"❌ 처리 중 오류: {e}")
                except Exception:
                    pass

        # 모아둔 사진 앨범 처리 — '채용' 캡션이면 공고 사진으로 분석 (워커에서)
        for g in photo_groups.values():
            cid = g["chat_id"]
            print(f"[main] 사진 {len(g['file_ids'])}장 수신 chat_id={cid}")
            if _work_busy():
                tg.send_message(cid, "⏳ 지금 앞의 작업을 처리하고 있어요. 멈추려면 '취소' 라고 보내주세요.")
                continue
            mode, rest = detect_mode(g["caption"])
            if mode == "job":
                _start_work(tg, cid, handle_job_photos, rest, g["file_ids"])
            elif cid in PENDING_JOB:
                # 방금 보낸 채용공고 텍스트를 이어서 보충하는 사진 (캡션 없이 보내도 됨)
                _start_work(tg, cid, _append_pending_job_photos, g["file_ids"])
            else:
                tg.send_message(cid, "🖼 사진을 받았어요. 채용공고 캡처라면 사진에 "
                                     "'채용' 이라는 캡션(설명)을 달아서 다시 보내주세요.")


if __name__ == "__main__":
    main()
