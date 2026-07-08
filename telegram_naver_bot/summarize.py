# -*- coding: utf-8 -*-
"""기사 내용을 카드뉴스용 콘텐츠(1~3장)로 요약합니다.

ANTHROPIC_API_KEY 가 설정되어 있으면 Claude API 로 요약하고,
없거나 호출에 실패하면 og:description / 본문 문단 기반 휴리스틱으로 대체합니다.

카드 1장 = {"title": 헤드라인, "bullets": [핵심 포인트 2~4개]}
"""
import json
import re

import config

CARD_SCHEMA = {
    "type": "object",
    "properties": {
        "cards": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "카드 상단 헤드라인 (25자 이내)"},
                    "bullets": {
                        "type": "array",
                        "items": {"type": "string", "description": "핵심 포인트 한 문장 (45자 이내)"},
                    },
                },
                "required": ["title", "bullets"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["cards"],
    "additionalProperties": False,
}


def build_cards(article: dict, max_cards: int = 3) -> list:
    max_cards = max(1, min(3, max_cards))
    if config.ANTHROPIC_API_KEY:
        try:
            cards = _build_cards_claude(article, max_cards)
            if cards:
                return cards[:max_cards]
        except Exception as e:
            print(f"[summarize] Claude 요약 실패, 휴리스틱으로 대체: {e}")
    return _build_cards_heuristic(article, max_cards)


# ── Claude API 요약 ──────────────────────────────────────

def _build_cards_claude(article: dict, max_cards: int) -> list:
    import anthropic

    body = "\n".join(article.get("paragraphs", []))[:6000]
    prompt = (
        "다음 뉴스 기사를 인스타그램 카드뉴스로 만들려고 합니다.\n"
        f"카드 1~{max_cards}장 분량으로 요약해 주세요. 기사 내용이 짧으면 1장으로 충분합니다.\n"
        "- 각 카드의 title 은 시선을 끄는 헤드라인으로 25자 이내\n"
        "- 각 카드의 bullets 는 핵심 포인트 2~4개, 각 45자 이내의 완결된 한 문장\n"
        "- 첫 카드는 기사 전체를 요약하고, 이후 카드는 세부 내용을 다룹니다\n"
        "- 취업준비생 독자에게 유용한 정보 위주로, 과장 없이 사실만 담습니다\n\n"
        f"[기사 제목] {article.get('title', '')}\n"
        f"[요약] {article.get('description', '')}\n"
        f"[본문]\n{body}"
    )

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=config.ANTHROPIC_MODEL,
        max_tokens=4096,
        output_config={"format": {"type": "json_schema", "schema": CARD_SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    )
    if response.stop_reason == "refusal":
        return []
    text = next((b.text for b in response.content if b.type == "text"), "")
    data = json.loads(text)
    cards = [c for c in data.get("cards", []) if c.get("title") and c.get("bullets")]
    return cards


# ── 휴리스틱 요약 (Claude 미사용 시) ─────────────────────

_SENT_SPLIT = re.compile(r"(?<=[.!?다요음됨함])\s+")


def _sentences(text: str):
    return [s.strip() for s in _SENT_SPLIT.split(text or "") if len(s.strip()) >= 10]


def _clip(s: str, limit: int) -> str:
    return s if len(s) <= limit else s[: limit - 1] + "…"


def _build_cards_heuristic(article: dict, max_cards: int) -> list:
    title = _clip(article.get("title", ""), 40)
    pool = _sentences(article.get("description", ""))
    for p in article.get("paragraphs", []):
        pool.extend(_sentences(p))
        if len(pool) >= max_cards * 4:
            break
    pool = [_clip(s, 60) for s in pool]

    if not pool:
        return [{"title": title or "뉴스 요약", "bullets": ["자세한 내용은 본문 링크를 확인해 주세요."]}]

    cards = []
    per_card = 3
    for i in range(0, min(len(pool), max_cards * per_card), per_card):
        bullets = pool[i:i + per_card]
        cards.append({
            "title": title if not cards else f"{_clip(title, 20)} ({len(cards) + 1})",
            "bullets": bullets,
        })
        if len(cards) >= max_cards:
            break
    return cards
