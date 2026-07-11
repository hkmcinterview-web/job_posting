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
  └ → 각 링크를 카드뉴스로 만들어 텔레그램으로 회신

실행: python main.py  (24시간 켜져 있는 서버/PC 에서 실행)
"""
import time
import traceback

import config
from article import fetch_article
from card_news import render_cards
from editor import build_cafe_post
from message_parser import detect_mode, extract_links, split_title_body
from naver_cafe import post_article
from summarize import build_cards
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
    "  예)\n"
    "  카드\n"
    "  https://n.news...\n"
    "  https://n.news..."
)


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


# ── 카드뉴스 제작 ────────────────────────────────────────

def handle_card(tg: TelegramClient, chat_id: int, content: str):
    links = extract_links(content)[: config.MAX_LINKS]
    if not links:
        tg.send_message(chat_id, "⚠️ '카드' 아래에 뉴스 링크(1~3개)를 함께 보내주세요.")
        return

    tg.send_message(chat_id, f"⏳ 카드뉴스 만드는 중 — 링크 {len(links)}개")
    stamp = int(time.time())
    made = 0
    for idx, url in enumerate(links, 1):
        try:
            art = fetch_article(url)
        except Exception as e:
            tg.send_message(chat_id, f"⚠️ 링크 {idx} 수집 실패({url}): {e}")
            continue
        try:
            cards, engine, err = build_cards(art, config.MAX_CARDS_PER_LINK)
            if engine == "heuristic" and (config.GEMINI_API_KEY or config.ANTHROPIC_API_KEY):
                # AI 키를 넣었는데 제목 그대로 나왔다면 이유를 알려줌
                tg.send_message(chat_id, f"⚠️ AI 요약 실패로 제목을 사용했어요.\n사유: {err}")
            paths = render_cards(cards, art, f"{stamp}_{idx}")
            for p in paths:
                tg.send_photo(chat_id, p, caption=art.get("title", "")[:80])
            made += len(paths)
        except Exception as e:
            tg.send_message(chat_id, f"⚠️ 링크 {idx} 카드뉴스 생성 실패: {e}")

    tg.send_message(chat_id, f"✅ 카드뉴스 {made}장 완성!")


# ── 메인 루프 ────────────────────────────────────────────

def handle_message(tg: TelegramClient, chat_id: int, text: str):
    mode, content = detect_mode(text)
    if mode == "cafe":
        handle_cafe(tg, chat_id, content)
    elif mode == "card":
        handle_card(tg, chat_id, content)
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
                handle_message(tg, chat_id, text)
            except Exception as e:
                traceback.print_exc()
                try:
                    tg.send_message(chat_id, f"❌ 처리 중 오류: {e}")
                except Exception:
                    pass


if __name__ == "__main__":
    main()
