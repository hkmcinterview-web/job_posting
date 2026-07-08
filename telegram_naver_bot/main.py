# -*- coding: utf-8 -*-
"""텔레그램 → 네이버카페 자동 게시 봇 (메인 루프).

흐름:
  1. 텔레그램 봇으로 온 메시지를 롱폴링으로 수신
  2. 메시지에서 제목/본문/뉴스링크 분리 (message_parser)
  3. 각 링크의 기사 내용을 수집 (article) → 링크당 1~3장 카드뉴스 생성 (summarize + card_news)
  4. 본문을 카페 글 형식으로 편집 (editor) → 카드 이미지와 함께 네이버카페에 게시 (naver_cafe)
  5. 결과(게시글 URL)와 카드 미리보기를 텔레그램으로 회신

실행: python main.py  (24시간 켜져 있는 서버/PC 에서 실행)
"""
import time
import traceback

import config
from article import fetch_article
from card_news import render_cards
from editor import build_post
from message_parser import parse_message
from naver_cafe import post_article
from summarize import build_cards
from telegram_client import TelegramClient


def process_text(tg: TelegramClient, chat_id: int, text: str):
    title, body, links = parse_message(text)
    links = links[: config.MAX_LINKS]
    tg.send_message(chat_id, f"⏳ 처리 시작 — 링크 {len(links)}개")

    articles, all_card_paths = [], []
    stamp = int(time.time())
    for idx, url in enumerate(links, 1):
        try:
            art = fetch_article(url)
        except Exception as e:
            tg.send_message(chat_id, f"⚠️ 링크 {idx} 수집 실패({url}): {e}")
            articles.append({"url": url, "title": url, "site": "", "description": "", "paragraphs": []})
            continue
        articles.append(art)

        try:
            cards = build_cards(art, config.MAX_CARDS_PER_LINK)
            paths = render_cards(cards, art.get("site", ""), f"{stamp}_{idx}")
            all_card_paths.extend(paths)
            if config.SEND_CARDS_TO_TELEGRAM:
                for p in paths:
                    tg.send_photo(chat_id, p, caption=art.get("title", "")[:80])
        except Exception as e:
            tg.send_message(chat_id, f"⚠️ 링크 {idx} 카드뉴스 생성 실패: {e}")

    subject, content_html = build_post(title, body, articles)

    if not config.naver_configured():
        tg.send_message(chat_id, "ℹ️ 네이버 API 설정이 없어 카페 게시는 건너뜁니다. (카드뉴스만 생성)")
        return

    result = post_article(subject, content_html, all_card_paths)
    url = result.get("articleUrl") or "(URL 확인 불가)"
    tg.send_message(chat_id, f"✅ 카페 게시 완료!\n제목: {subject}\n카드뉴스: {len(all_card_paths)}장\n{url}")


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
                process_text(tg, chat_id, text)
            except Exception as e:
                traceback.print_exc()
                try:
                    tg.send_message(chat_id, f"❌ 처리 중 오류: {e}")
                except Exception:
                    pass


if __name__ == "__main__":
    main()
