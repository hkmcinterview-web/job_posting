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
import time
import traceback

import config
from article import fetch_article, fetch_job_page
from card_news import render_cards
from editor import build_cafe_post, build_job_post
from job_card import render_job_card
from job_summary import build_job_data
from message_parser import detect_mode, extract_links, split_title_body
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
    "  첫 줄에 '채용' 이라고 쓰고, 채용공고 링크를 넣으세요.\n"
    "  (링크가 안 읽히는 사이트면 공고 내용을 통째로 복사해 붙여도 됩니다)\n"
    "  예)\n"
    "  채용\n"
    "  https://recruit..."
)

# 링크당 카드 선택 후보 개수 (2~3)
N_OPTIONS = max(2, min(3, config.MAX_CARDS_PER_LINK or 3))

# chat_id 별로 "카드 후보 선택 대기" 상태를 들고 있음 (봇 재시작 시 초기화됨)
# {chat_id: {"queue": [url, ...], "link_idx": int, "made": int, "stamp": int,
#            "article": dict|None, "options": list|None, "summary": str|None}}
PENDING_CARD: dict = {}


# ── 카페 글 게시 ─────────────────────────────────────────

def handle_cafe(tg: TelegramClient, chat_id: int, content: str):
    title, body = split_title_body(content)
    if not (title or body.strip()):
        tg.send_message(chat_id, "⚠️ '카페' 아래에 올릴 내용을 함께 보내주세요.")
        return

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


def _handle_one_job(tg: TelegramClient, chat_id: int, page: dict, idx: int):
    job, summary, engine, err = build_job_data(page)
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
    try:
        # 카드 이미지를 첨부해서 게시 시도 → 실패하면 텍스트만으로 재시도
        try:
            result = post_article(subject, content_html, image_paths=[path],
                                  menu_id=config.NAVER_CAFE_JOB_MENU_ID)
        except Exception as e:
            print(f"[main] 이미지 첨부 게시 실패, 텍스트만 재시도: {e}")
            result = post_article(subject, content_html, image_paths=None,
                                  menu_id=config.NAVER_CAFE_JOB_MENU_ID)
        url = result.get("articleUrl") or "(URL 확인 불가)"
        tg.send_message(chat_id, f"✅ 카페 게시 완료!\n제목: {subject}\n{url}")
    except Exception as e:
        tg.send_message(chat_id, f"⚠️ 카페 게시 실패: {e}")


def handle_job(tg: TelegramClient, chat_id: int, content: str):
    links = extract_links(content)[: config.MAX_LINKS]

    if links:
        for i, url in enumerate(links, 1):
            tg.send_message(chat_id, f"⏳ 채용공고 {i}/{len(links)} 분석 중...")
            try:
                page = fetch_job_page(url)
                if len(page.get("text") or "") < 150:
                    tg.send_message(chat_id,
                                    f"⚠️ 링크 {i} 페이지에서 내용을 거의 못 읽었어요 "
                                    "(스크립트로만 그려지는 사이트일 수 있음).\n"
                                    "공고 내용을 복사해서 '채용' 뒤에 붙여 보내면 처리됩니다.")
                    continue
                _handle_one_job(tg, chat_id, page, i)
            except Exception as e:
                tg.send_message(chat_id, f"⚠️ 채용공고 {i} 처리 실패: {e}")
        return

    # 링크 없이 공고 본문을 직접 붙여넣은 경우
    if len(content.strip()) >= 80:
        tg.send_message(chat_id, "⏳ 붙여넣은 채용공고 내용 분석 중...")
        page = {"url": "", "title": "", "description": "", "text": content.strip()[:9000]}
        _handle_one_job(tg, chat_id, page, 1)
        return

    tg.send_message(chat_id, "⚠️ '채용' 아래에 채용공고 링크(또는 공고 내용 전체)를 함께 보내주세요.")


# ── 카드뉴스 제작 (헤드라인 후보 선택 방식) ─────────────────

def _format_options(options: list) -> str:
    lines = ["📝 헤드라인 후보 — 숫자로 답장해서 골라주세요:"]
    for i, opt in enumerate(options, 1):
        headline = (opt.get("headline") or "").replace("\n", " / ")
        tag = f"[{opt['tag']}] " if opt.get("tag") else ""
        lines.append(f"{i}. {tag}{headline}")
    return "\n".join(lines)


def _send_summary_text(tg: TelegramClient, chat_id: int, art: dict, summary: str):
    """카드뉴스 업로드 시 캡션으로 바로 쓸 수 있게, 제목 + 요약 + 출처 링크를 별도 메시지로 전송."""
    parts = []
    title = art.get("title") or ""
    if title:
        parts.append(f"📰 {title}")
    if summary:
        parts.append(f"📝 요약\n{summary}")
    url = art.get("url", "")
    if url:
        parts.append(f"\n출처: {url}")
    if parts:
        tg.send_message(chat_id, "\n".join(parts))


def _finish_link(tg: TelegramClient, chat_id: int, card: dict, art: dict, state: dict):
    """선택(또는 자동 확정)된 카드 1장을 렌더링해서 보내고 다음 링크로 진행."""
    try:
        paths = render_cards([card], art, f"{state['stamp']}_{state['link_idx']}")
        for p in paths:
            tg.send_photo(chat_id, p, caption=art.get("title", "")[:80])
        state["made"] += len(paths)
        _send_summary_text(tg, chat_id, art, state.get("summary") or "")
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
    state["summary"] = None

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
        options, engine, err, summary = build_card_options(art, N_OPTIONS)
    except Exception as e:
        tg.send_message(chat_id, f"⚠️ 링크 {state['link_idx']} 요약 실패: {e}")
        _advance(tg, chat_id)
        return

    state["summary"] = summary

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
        "summary": None,
    }
    tg.send_message(chat_id, f"⏳ 카드뉴스 준비 중 — 링크 {len(links)}개")
    _advance(tg, chat_id)


def _try_resolve_selection(tg: TelegramClient, chat_id: int, text: str) -> bool:
    """대기 중인 후보 선택에 대한 답장이면 처리하고 True, 아니면 False."""
    state = PENDING_CARD.get(chat_id)
    if not state or not state.get("options"):
        return False

    m = re.match(r"\s*([1-9])", text.strip())
    options = state["options"]
    if not m or int(m.group(1)) > len(options):
        return False

    chosen = options[int(m.group(1)) - 1]
    art = state["article"]
    _finish_link(tg, chat_id, chosen, art, state)
    return True


# ── 메인 루프 ────────────────────────────────────────────

def handle_message(tg: TelegramClient, chat_id: int, text: str):
    mode, content = detect_mode(text)
    if mode == "cafe":
        handle_cafe(tg, chat_id, content)
    elif mode == "card":
        handle_card(tg, chat_id, content)
    elif mode == "job":
        handle_job(tg, chat_id, content)
    else:
        tg.send_message(chat_id, HELP_TEXT)


def main():
    if not config.TELEGRAM_BOT_TOKEN:
        raise SystemExit(".env 에 TELEGRAM_BOT_TOKEN 을 설정하세요. (@BotFather 에서 발급)")
    if not config.TELEGRAM_ALLOWED_CHAT_IDS:
        print("⚠️ TELEGRAM_ALLOWED_CHAT_IDS 가 비어 있어 모든 채팅을 허용합니다. "
              "봇에게 아무 메시지나 보내면 chat_id 가 로그에 출력되니 그 값을 .env 에 넣으세요.")

    tg = TelegramClient(config.TELEGRAM_BOT_TOKEN)
    offset = None
    print("🤖 봇 시작 — 텔레그램 메시지를 기다립니다...")

    while True:
        try:
            updates = tg.get_updates(offset=offset)
        except Exception as e:
            print(f"getUpdates 오류, 5초 후 재시도: {e}")
            time.sleep(5)
            continue

        for upd in updates:
            offset = upd["update_id"] + 1
            msg = upd.get("message") or {}
            chat_id = (msg.get("chat") or {}).get("id")
            text = msg.get("text") or msg.get("caption") or ""
            if chat_id is None or not text.strip():
                continue
            print(f"[main] 메시지 수신 chat_id={chat_id}")
            if config.TELEGRAM_ALLOWED_CHAT_IDS and chat_id not in config.TELEGRAM_ALLOWED_CHAT_IDS:
                print(f"[main] 허용되지 않은 chat_id={chat_id} — 무시")
                continue
            try:
                # 카드 후보 선택 대기 중이면 숫자 답장인지 먼저 확인
                if chat_id in PENDING_CARD and _try_resolve_selection(tg, chat_id, text):
                    continue
                if chat_id in PENDING_CARD and PENDING_CARD[chat_id].get("options"):
                    tg.send_message(chat_id, "⚠️ 진행 중이던 선택은 취소하고 새 요청을 처리할게요. "
                                             "(후보를 고르려면 숫자만 답장해주세요)")
                    PENDING_CARD.pop(chat_id, None)
                handle_message(tg, chat_id, text)
            except Exception as e:
                traceback.print_exc()
                try:
                    tg.send_message(chat_id, f"❌ 처리 중 오류: {e}")
                except Exception:
                    pass


if __name__ == "__main__":
    main()
