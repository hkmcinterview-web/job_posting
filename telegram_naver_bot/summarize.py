# -*- coding: utf-8 -*-
"""기사 내용을 카드뉴스용 헤드라인(1~3장)으로 요약합니다.

스타일: 사진 배경 위에 얹는 짧고 임팩트 있는 문장.
카드 1장 = {"headline": "줄바꿈(\\n)이 포함된 2~3줄 문장"}

요약 엔진 우선순위:
  1) GEMINI_API_KEY 있으면 → 구글 Gemini (무료 등급)
  2) ANTHROPIC_API_KEY 있으면 → Claude (유료)
  3) 둘 다 없으면 → 기사 제목 기반 휴리스틱 (무료)
"""
import json
import re

import requests

import config

# ── 공통 프롬프트 ────────────────────────────────────────

def _build_prompt(article: dict, max_cards: int) -> str:
    body = "\n".join(article.get("paragraphs", []))[:6000]
    return (
        "다음 뉴스 기사를 SNS 카드뉴스 헤드라인으로 만들어 주세요.\n"
        "기사 사진 위에 큰 글씨로 얹는 형식이라 문장이 짧고 눈에 확 들어와야 합니다.\n\n"
        "규칙:\n"
        "- ⚠️ 기사 제목을 그대로 베끼지 말 것! 본문 내용을 파악해서 새로 쓴 센스있는 문장이어야 함\n"
        f"- 기본은 카드 1장. 기사에 서로 다른 핵심 포인트가 여럿일 때만 최대 {max_cards}장\n"
        "- headline 은 2~3줄, 각 줄 8~14자, 줄바꿈 위치는 의미 단위로 자연스럽게 (\\n 사용)\n"
        "- 첫 줄은 후킹하는 한마디(반응/요점), 이어지는 줄에서 핵심 사실 전달\n"
        "- 커뮤니티 카드뉴스처럼 딱딱하지 않고 위트있게. 예시 톤:\n"
        '  "노동계 대폭발에 화들짝\\n\'성과급 지역화폐 지급법\'\\n법안 철회"\n'
        '  "미국산 칩 생산 드가자\\n브로드컴, 애플과 45조 원\\n계약에 주가 상승"\n'
        '  "일론 머스크 싫으면 빼줌\\n월가, 머스크 기업 제외한\\nETF 준비 중"\n'
        "- 위트는 살리되 과장/왜곡 없이 기사 사실만 담기. 핵심 숫자(금액, 퍼센트)는 살리기\n"
        "- tag: 기사 성격을 나타내는 2~4자 카테고리 (예: 이슈, 속보, 경제, 노동, 증시, 취업, 정치, 국제, IT)\n"
        "- highlight: headline 여러 줄 중 가장 강조하고 싶은 '한 줄'을 그대로 복사 (반드시 headline 안의 한 줄과 정확히 일치)\n"
        "- style: 강조 방식. 강렬한 이슈/속보는 \"marker\"(형광펜), 차분한 정보성은 \"color\"(포인트 컬러)\n"
        '- 반드시 아래 JSON 형식으로만 답하기 (다른 말 없이):\n'
        '  {"cards": [{"headline": "...", "tag": "...", "highlight": "...", "style": "marker"}]}\n\n'
        f"[기사 제목] {article.get('title', '')}\n"
        f"[요약] {article.get('description', '')}\n"
        f"[본문]\n{body}"
    )


def _extract_cards(text: str) -> list:
    """모델 응답 텍스트에서 JSON 을 뽑아 카드 목록을 반환."""
    text = (text or "").strip()
    # ```json ... ``` 코드블록 안에 넣는 모델 대비
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        text = m.group(0)
    # strict=False: 문자열 안에 실제 줄바꿈이 들어와도 허용
    data = json.loads(text, strict=False)
    return [c for c in data.get("cards", []) if c.get("headline", "").strip()]


def build_cards(article: dict, max_cards: int = 3):
    """returns (cards, engine, error)
    engine ∈ {'gemini','claude','heuristic'}, error 는 AI 실패 사유(없으면 "")."""
    max_cards = max(1, min(3, max_cards))
    prompt = _build_prompt(article, max_cards)
    error = ""

    if config.GEMINI_API_KEY:
        try:
            cards = _build_cards_gemini(prompt)
            if cards:
                return cards[:max_cards], "gemini", ""
            error = "Gemini 응답에 카드가 없음"
        except Exception as e:
            error = f"Gemini: {e}"
            print(f"[summarize] Gemini 요약 실패, 다음 방식으로 대체: {e}")

    if config.ANTHROPIC_API_KEY:
        try:
            cards = _build_cards_claude(prompt)
            if cards:
                return cards[:max_cards], "claude", ""
            error = error or "Claude 응답에 카드가 없음"
        except Exception as e:
            error = f"Claude: {e}"
            print(f"[summarize] Claude 요약 실패, 휴리스틱으로 대체: {e}")

    return _build_cards_heuristic(article, max_cards), "heuristic", error


# ── ① 구글 Gemini (무료 등급) ────────────────────────────

def _build_cards_gemini(prompt: str) -> list:
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.9},
    }
    # 설정 모델을 먼저 시도하고, 실패(404 등)하면 대체 모델들을 순서대로 시도
    models, seen = [], set()
    for m in [config.GEMINI_MODEL, "gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest"]:
        if m and m not in seen:
            seen.add(m)
            models.append(m)

    last_err = None
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        resp = requests.post(url, params={"key": config.GEMINI_API_KEY},
                             json=payload, timeout=40)
        if resp.status_code == 404:  # 모델 이름 문제 — 다음 후보로
            last_err = f"모델 '{model}' 없음(404)"
            continue
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise RuntimeError(f"응답 비어있음(안전필터 가능): {str(data)[:200]}")
        parts = candidates[0].get("content", {}).get("parts", [])
        return _extract_cards("".join(p.get("text", "") for p in parts))

    raise RuntimeError(last_err or "사용 가능한 Gemini 모델 없음")


# ── ② Claude API (유료) ──────────────────────────────────

def _build_cards_claude(prompt: str) -> list:
    import anthropic

    schema = {
        "type": "object",
        "properties": {
            "cards": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "headline": {"type": "string"},
                        "tag": {"type": "string"},
                        "highlight": {"type": "string"},
                        "style": {"type": "string", "enum": ["marker", "color"]},
                    },
                    "required": ["headline", "tag", "highlight", "style"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["cards"],
        "additionalProperties": False,
    }
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=config.ANTHROPIC_MODEL,
        max_tokens=2048,
        output_config={"format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": prompt}],
    )
    if response.stop_reason == "refusal":
        return []
    text = next((b.text for b in response.content if b.type == "text"), "")
    return _extract_cards(text)


# ── ③ 휴리스틱 (무료, AI 미사용) — 기사 제목을 줄 단위로 나눔 ──

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
    for sep in (" - ", " | ", " :: "):
        if sep in title:
            title = title.split(sep)[0].strip()
    return [{"headline": _break_lines(title)}]
