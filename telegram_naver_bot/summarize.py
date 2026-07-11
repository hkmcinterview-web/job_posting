# -*- coding: utf-8 -*-
"""기사 내용을 카드뉴스용 헤드라인(1~3장)으로 요약합니다.

스타일: 사진 배경 위에 얹는 짧고 임팩트 있는 문장.
카드 1장 = {"headline": "줄바꿈(\\n)이 포함된 2~3줄 문장"}

ANTHROPIC_API_KEY 가 설정되어 있으면 Claude API 로 요약하고,
없거나 호출에 실패하면 기사 제목 기반 휴리스틱으로 대체합니다.
"""
import json

import config

CARD_SCHEMA = {
    "type": "object",
    "properties": {
        "cards": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "headline": {
                        "type": "string",
                        "description": "카드에 크게 들어갈 문장. 2~3줄, 각 줄 8~14자, 줄바꿈은 \\n",
                    },
                },
                "required": ["headline"],
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
        "다음 뉴스 기사를 SNS 카드뉴스 헤드라인으로 만들어 주세요.\n"
        "기사 사진 위에 큰 글씨로 얹는 형식이라 문장이 짧고 눈에 확 들어와야 합니다.\n\n"
        "규칙:\n"
        f"- 기본은 카드 1장. 기사에 서로 다른 핵심 포인트가 여럿일 때만 최대 {max_cards}장\n"
        "- headline 은 2~3줄, 각 줄 8~14자, 줄바꿈 위치는 의미 단위로 자연스럽게 (\\n 사용)\n"
        "- 커뮤니티 카드뉴스처럼 딱딱하지 않고 위트있게. 예시 톤:\n"
        '  "노동계 대폭발에 화들짝\\n\'성과급 지역화폐 지급법\'\\n법안 철회"\n'
        '  "미국산 칩 생산 드가자\\n브로드컴, 애플과 45조 원\\n계약에 주가 상승"\n'
        '  "일론 머스크 싫으면 빼줌\\n월가, 머스크 기업 제외한\\nETF 준비 중"\n'
        "- 위트는 살리되 과장/왜곡 없이 기사 사실만 담기. 핵심 숫자(금액, 퍼센트)는 살리기\n\n"
        f"[기사 제목] {article.get('title', '')}\n"
        f"[요약] {article.get('description', '')}\n"
        f"[본문]\n{body}"
    )

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=config.ANTHROPIC_MODEL,
        max_tokens=2048,
        output_config={"format": {"type": "json_schema", "schema": CARD_SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    )
    if response.stop_reason == "refusal":
        return []
    text = next((b.text for b in response.content if b.type == "text"), "")
    data = json.loads(text)
    return [c for c in data.get("cards", []) if c.get("headline", "").strip()]


# ── 휴리스틱 요약 (Claude 미사용 시) — 기사 제목을 줄 단위로 나눔 ──

def _break_lines(text: str, per_line: int = 13, max_lines: int = 3) -> str:
    words = (text or "").split()
    lines, cur = [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > per_line:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
        if len(lines) >= max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    return "\n".join(lines) if lines else (text or "")[: per_line * max_lines]


def _build_cards_heuristic(article: dict, max_cards: int) -> list:
    title = article.get("title", "") or "뉴스 요약"
    # 언론사명 접미사 제거 (예: "제목 - 매일경제")
    for sep in (" - ", " | ", " :: "):
        if sep in title:
            title = title.split(sep)[0].strip()
    return [{"headline": _break_lines(title)}]
