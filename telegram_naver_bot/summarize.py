# -*- coding: utf-8 -*-
"""기사 내용으로 카드뉴스 1장(사진 배경 + 헤드라인)용 헤드라인 후보를 만듭니다.

흐름: 링크 하나당 서로 다른 톤의 헤드라인 후보를 여러 개 생성 → 사용자가 텔레그램에서
숫자로 하나를 고르면 그것으로 카드 1장을 렌더링합니다.

카드(후보) 1개 = {"headline": "...", "tag": "...", "highlight": "...", "style": "marker"}

모델 응답 포맷: JSON 대신 마커로 구분된 일반 텍스트를 씁니다.
  <<<CARD>>>
  TAG: 이슈
  HIGHLIGHT: 법안 철회
  STYLE: marker
  HEADLINE:
  노동계 대폭발에 화들짝
  '성과급 지역화폐 지급법'
  법안 철회
  <<<END>>>
JSON은 헤드라인 문장에 큰따옴표가 하나만 들어가도 파싱이 깨지는 문제가 반복돼서
(문장 안 인용부호 vs JSON 문자열 종료를 구분하기 어려움) 이 방식으로 바꿨습니다 —
HEADLINE 은 <<<END>>> 직전까지 전부 그대로 읽으므로 문장 안에 어떤 문자가 와도 안전합니다.

요약 엔진 우선순위:
  1) GEMINI_API_KEY 있으면 → 구글 Gemini (무료 등급)
  2) ANTHROPIC_API_KEY 있으면 → Claude (유료)
  3) 둘 다 없으면 → 기사 제목 기반 휴리스틱 (무료, 후보 1개만 — 고를 필요 없이 바로 사용)
"""
import re

import requests

import config

# ── 공통 프롬프트 ────────────────────────────────────────

def _build_prompt(article: dict, n_options: int) -> str:
    body = "\n".join(article.get("paragraphs", []))[:6000]
    return (
        "다음 뉴스 기사로 SNS 카드뉴스를 1장 만들 겁니다.\n"
        "기사 사진 위에 큰 글씨로 얹는 형식이라 문장이 짧고 눈에 확 들어와야 합니다.\n"
        f"같은 카드에 쓸 서로 다른 톤/문구의 헤드라인 후보를 정확히 {n_options}개 제안해 주세요.\n"
        "(순차적인 여러 포인트가 아니라, 같은 기사 내용을 표현하는 서로 다른 버전입니다)\n"
        "추가로, 카드뉴스와 함께 SNS(인스타그램 등)에 올릴 때 쓸 기사 요약문도 하나 만들어 주세요.\n\n"
        "이 카드뉴스는 자동차산업 취업준비생 대상 인스타그램 캐러셀(5장)입니다.\n"
        "1장은 헤드라인, 2장 핵심 요약, 3장 배경/맥락, 4장 전망, 5장 CTA 이며\n"
        "아래에서 SUMMARY(2장), CONTEXT(3장), OUTLOOK(4장), CAPTION(게시글 캡션)을 함께 만듭니다.\n\n"
        "요약문(SUMMARY, 2장 슬라이드용) 규칙:\n"
        "- 4~6문장으로 기사 핵심을 충분히 자세하게 (이 내용이 슬라이드에 그대로 실림)\n"
        "- 한 문장에 한 줄씩 (줄바꿈으로 구분), 숫자·날짜·회사명 등 구체적 정보 유지\n"
        "- ⚠️ 전체에서 가장 중요한 핵심 문장(또는 구절) 딱 1~2곳만 {{이렇게}} 감싸서 강조.\n"
        "  숫자라고 무조건 강조하지 말 것 — 정말 임팩트 있는 곳만 골라서. 나머지는 강조 금지\n"
        "- 해시태그나 이모지는 넣지 말 것 (텍스트만)\n\n"
        "배경(CONTEXT, 3장 슬라이드용) 규칙:\n"
        "- 이 뉴스가 왜 나왔는지 배경과 맥락을 친구에게 설명하듯 자연스러운 말투로 2~4문장\n"
        "- 딱딱 끊어지는 개조식 금지 — 자연스럽게 이어지는 하나의 이야기 문단으로\n"
        "- 예: '사실 이 갈등은 어제오늘 일이 아니에요. 작년 임금협상 때부터 ...'\n"
        "- 기사에 없는 내용을 지어내지 말고, 업계 일반 상식 수준의 맥락만 보태기\n"
        "- 가장 인상적인 한 구절만 {{이렇게}} 감싸서 강조 (많아야 1곳, 없어도 됨)\n\n"
        "전망(OUTLOOK, 4장 슬라이드용) 규칙:\n"
        "- 앞으로 지켜볼 포인트 2~3개, 각 줄 '- ' 로 시작 (각 18~45자)\n"
        "- 기사 흐름에서 자연스럽게 나오는 관전 포인트만 (일정, 경쟁 구도, 다음 단계 등)\n"
        "- 취업/취준생 얘기는 넣지 말 것\n"
        "- 전체 포인트 중 가장 중요한 한 곳만 {{이렇게}} 강조 (많아야 1곳, 없어도 됨)\n\n"
        "캡션(CAPTION, 인스타 게시글 본문용) 규칙:\n"
        "- 1~2문장 핵심 요약 + 취준생 관점 시사점 1문장\n"
        "- 마지막 줄에 검색용 해시태그 6~8개 (예: #자동차산업 #현대차 #취준 ...)\n\n"
        "내용 규칙:\n"
        "- ⚠️ 기사 제목을 그대로 베끼지 말 것! 본문 내용을 파악해서 새로 쓴 센스있는 문장이어야 함\n"
        "- HEADLINE 은 2~3줄, 각 줄 8~14자, 줄바꿈 위치는 의미 단위로 자연스럽게\n"
        "- 첫 줄은 후킹하는 한마디(반응/요점), 이어지는 줄에서 핵심 사실 전달\n"
        "- 커뮤니티 카드뉴스처럼 딱딱하지 않고 위트있게. 예시 톤:\n"
        "    노동계 대폭발에 화들짝\n"
        "    '성과급 지역화폐 지급법'\n"
        "    법안 철회\n"
        "- 위트는 살리되 과장/왜곡 없이 기사 사실만 담기. 핵심 숫자(금액, 퍼센트)는 살리기\n"
        f"- {n_options}개 후보는 서로 눈에 띄게 다른 각도/톤이어야 함 (예: 반응 위주 / 숫자 강조 / 임팩트 문구)\n"
        "- TAG: 기사 성격을 나타내는 2~4자 카테고리 (예: 이슈, 속보, 경제, 노동, 증시, 취업, 정치, 국제, IT)\n"
        "- HIGHLIGHT: HEADLINE 여러 줄 중 가장 강조하고 싶은 '한 줄'을 그대로 복사 (HEADLINE 안의 한 줄과 정확히 일치)\n"
        "- STYLE: marker(형광펜 — 강렬한 이슈/속보) 또는 color(포인트 컬러 — 차분한 정보성) 중 하나\n\n"
        "출력 형식 — 아래 형식을 정확히 지켜서, 다른 설명/인사말 없이 작성하세요.\n"
        "SUMMARY → CONTEXT → OUTLOOK → CAPTION 블록을 한 번씩 쓰고, 그 다음 CARD 블록을 후보 수만큼 반복하세요.\n"
        "각 CARD 블록은 반드시 TAG → HIGHLIGHT → STYLE → HEADLINE 순서이고, HEADLINE 은 항상 블록의 마지막이며\n"
        "<<<END>>> 바로 앞까지 나오는 모든 줄이 헤드라인 내용입니다 (따옴표 등 어떤 문장부호를 써도 됩니다):\n\n"
        "<<<SUMMARY>>>\n"
        "(4~6문장, 한 문장에 한 줄)\n"
        "<<<END>>>\n\n"
        "<<<CONTEXT>>>\n"
        "(자연스럽게 이어지는 배경 설명 문단)\n"
        "<<<END>>>\n\n"
        "<<<OUTLOOK>>>\n"
        "- (지켜볼 포인트 1)\n"
        "- (지켜볼 포인트 2)\n"
        "<<<END>>>\n\n"
        "<<<CAPTION>>>\n"
        "(캡션 본문)\n"
        "#해시태그 #들\n"
        "<<<END>>>\n\n"
        "<<<CARD>>>\n"
        "TAG: (태그)\n"
        "HIGHLIGHT: (강조할 한 줄)\n"
        "STYLE: marker 또는 color\n"
        "HEADLINE:\n"
        "(첫째 줄)\n"
        "(둘째 줄)\n"
        "(셋째 줄, 필요하면)\n"
        "<<<END>>>\n"
        f"(CARD 블록을 총 {n_options}번 반복)\n\n"
        f"[기사 제목] {article.get('title', '')}\n"
        f"[요약] {article.get('description', '')}\n"
        f"[본문]\n{body}"
    )


_CARD_BLOCK_RE = re.compile(r"<{2,3}\s*CARD\s*>{2,3}(.*?)<{2,3}\s*END\s*>{2,3}",
                            re.DOTALL | re.IGNORECASE)
_SUMMARY_BLOCK_RE = re.compile(r"<{2,3}\s*SUMMARY\s*>{2,3}(.*?)<{2,3}\s*END\s*>{2,3}",
                               re.DOTALL | re.IGNORECASE)
_HEADLINE_LABEL_RE = re.compile(r"HEADLINE\s*:\s*\n?", re.IGNORECASE)
_TAG_RE = re.compile(r"^\s*TAG\s*:\s*(.*)$", re.IGNORECASE)
_HIGHLIGHT_RE = re.compile(r"^\s*HIGHLIGHT\s*:\s*(.*)$", re.IGNORECASE)
_STYLE_RE = re.compile(r"^\s*STYLE\s*:\s*(.*)$", re.IGNORECASE)


def _extract_summary(text: str) -> str:
    """모델 응답에서 <<<SUMMARY>>>...<<<END>>> 블록을 뽑아 요약 텍스트로 반환."""
    m = _SUMMARY_BLOCK_RE.search(text or "")
    return m.group(1).strip() if m else ""


def _extract_block(text: str, name: str) -> str:
    m = re.search(rf"<{{2,3}}\s*{name}\s*>{{2,3}}(.*?)<{{2,3}}\s*END\s*>{{2,3}}",
                  text or "", re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _extract_extras(text: str) -> dict:
    """캐러셀 2~4장 + 캡션 재료: summary / context(문단) / outlook(list) / caption."""
    outlook = [ln.lstrip("-•· ").strip()
               for ln in _extract_block(text, "OUTLOOK").split("\n")
               if ln.strip().lstrip("-•· ").strip()]

    # 배경 문단 — 줄바꿈이 섞여 와도 하나의 흐르는 문단으로 합침
    context = " ".join(ln.strip() for ln in _extract_block(text, "CONTEXT").split("\n")
                       if ln.strip())

    return {
        "summary": _extract_summary(text),
        "context": context,
        "outlook": outlook[:3],
        "caption": _extract_block(text, "CAPTION"),
    }


def _extract_cards(text: str) -> list:
    """모델 응답에서 <<<CARD>>>...<<<END>>> 블록들을 뽑아 헤드라인 후보 목록으로 변환.

    JSON을 쓰지 않으므로 헤드라인 문장 안에 어떤 따옴표/문장부호가 있어도 깨지지 않는다.
    """
    cards = []
    for block_match in _CARD_BLOCK_RE.finditer(text or ""):
        block = block_match.group(1)
        head_label = _HEADLINE_LABEL_RE.search(block)
        meta = block[:head_label.start()] if head_label else block
        headline = block[head_label.end():].strip("\n").strip() if head_label else ""

        tag = highlight = style = ""
        for line in meta.split("\n"):
            line = line.strip()
            m = _TAG_RE.match(line)
            if m:
                tag = m.group(1).strip()
                continue
            m = _HIGHLIGHT_RE.match(line)
            if m:
                highlight = m.group(1).strip()
                continue
            m = _STYLE_RE.match(line)
            if m:
                style = m.group(1).strip()

        if headline:
            style_norm = style.strip().lower()
            cards.append({
                "headline": headline,
                "tag": tag,
                "highlight": highlight,
                "style": style_norm if style_norm in ("marker", "color") else "marker",
            })
    return cards


def build_card_options(article: dict, n_options: int = 3):
    """카드 1장에 쓸 헤드라인 후보 + 기사 요약문을 만든다.

    returns (options, engine, error, extras)
    extras = {'summary','insight','interview','caption'} — 캐러셀 2~4장 + 인스타 캡션 재료.
    engine ∈ {'gemini','claude','heuristic'}, error 는 AI 실패 사유(없으면 "").
    AI 를 못 쓰면 후보 1개(제목 기반)만 돌려준다 — 이 경우 호출 측에서 선택 없이 바로 사용하면 된다."""
    n_options = max(2, min(3, n_options))
    prompt = _build_prompt(article, n_options)
    error = ""

    if config.GEMINI_API_KEY:
        try:
            extras, options = _build_cards_gemini(prompt)
            if options:
                return options[:n_options], "gemini", "", extras
            error = "Gemini 응답에 후보가 없음"
        except Exception as e:
            error = f"Gemini: {e}"
            print(f"[summarize] Gemini 요약 실패, 다음 방식으로 대체: {e}")

    if config.ANTHROPIC_API_KEY:
        try:
            extras, options = _build_cards_claude(prompt)
            if options:
                return options[:n_options], "claude", "", extras
            error = error or "Claude 응답에 후보가 없음"
        except Exception as e:
            error = f"Claude: {e}"
            print(f"[summarize] Claude 요약 실패, 다음 방식으로 대체: {e}")

    if config.OLLAMA_MODEL:
        try:
            extras, options = _build_cards_ollama(prompt)
            if options:
                return options[:n_options], "ollama", "", extras
            error = error or "로컬 모델 응답에 후보가 없음"
        except Exception as e:
            error = f"로컬 모델: {e}"
            print(f"[summarize] Ollama 요약 실패, 휴리스틱으로 대체: {e}")

    heuristic_extras = {"summary": _heuristic_summary(article), "context": "",
                        "outlook": [], "caption": ""}
    return _build_cards_heuristic(article), "heuristic", error, heuristic_extras


# ── ① 구글 Gemini (무료 등급) ────────────────────────────

def _gemini_generate(prompt: str, temperature: float = 0.9, images=None) -> str:
    """Gemini 에 프롬프트를 보내 원문 텍스트를 받는다.

    키 여러 개(GEMINI_API_KEY 에 콤마로 나열) × 모델 여러 개를 순회해서,
    한 키/모델이 할당량 초과(429)여도 다음 키로 자동 대체합니다
    (무료 등급을 키 개수만큼 늘리는 효과).
    images: [(mime_type, base64문자열), ...] — 채용공고 캡처 등 이미지 입력 (비전)."""
    parts = [{"text": prompt}]
    for mime, b64 in (images or []):
        parts.append({"inline_data": {"mime_type": mime, "data": b64}})
    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {"temperature": temperature},
    }
    models, seen = [], set()
    # 할당량은 '모델별로 따로' 매겨지므로(quotaId 에 PerModel), 서로 다른 모델을
    # 최대한 많이 순회할수록 어느 한 모델이 소진돼도 다른 모델에 남은 할당량을 쓸 수 있다.
    # gemini-2.5-flash 는 실측 결과 이 API 표면에서 404(모델 없음)라 목록에서 제외.
    for m in [config.GEMINI_MODEL, "gemini-3.5-flash", "gemini-flash-latest",
              "gemini-2.0-flash", "gemini-2.0-flash-lite",
              "gemini-1.5-flash", "gemini-1.5-flash-8b"]:
        if m and m not in seen:
            seen.add(m)
            models.append(m)

    keys = config.GEMINI_API_KEYS or ([config.GEMINI_API_KEY] if config.GEMINI_API_KEY else [])
    if not keys:
        raise RuntimeError("GEMINI_API_KEY 가 설정되지 않음")

    last_err = None
    for ki, key in enumerate(keys, 1):
        for model in models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            resp = requests.post(url, params={"key": key}, json=payload, timeout=40)
            if resp.status_code == 404:  # 모델 이름 문제 — 다음 후보로
                last_err = f"모델 '{model}' 없음(404)"
                continue
            if resp.status_code == 429:  # 이 키/모델만 quota 초과일 수 있음 — 다음 후보로
                last_err = f"키{ki} 모델 '{model}' 사용량 초과(429)"
                continue
            if resp.status_code == 503:  # 모델 일시 과부하 — 다음 후보로
                last_err = f"모델 '{model}' 일시 과부하(503)"
                continue
            if resp.status_code != 200:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                raise RuntimeError(f"응답 비어있음(안전필터 가능): {str(data)[:200]}")
            parts = candidates[0].get("content", {}).get("parts", [])
            return "".join(p.get("text", "") for p in parts)

    raise RuntimeError(last_err or "사용 가능한 Gemini 모델 없음")


def _build_cards_gemini(prompt: str):
    text = _gemini_generate(prompt)
    return _extract_extras(text), _extract_cards(text)


# ── ② Claude API (유료) ──────────────────────────────────

def _claude_generate(prompt: str, images=None) -> str:
    import anthropic

    content = [{"type": "image",
                "source": {"type": "base64", "media_type": mime, "data": b64}}
               for mime, b64 in (images or [])]
    content.append({"type": "text", "text": prompt})

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=config.ANTHROPIC_MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": content}],
    )
    if response.stop_reason == "refusal":
        return ""
    return next((b.text for b in response.content if b.type == "text"), "")


def _build_cards_claude(prompt: str):
    text = _claude_generate(prompt)
    return _extract_extras(text), _extract_cards(text)


# ── ③ 로컬 오픈소스 모델 (Ollama) — Gemini/Claude 가 전부 막혔을 때 마지막 폴백 ──

def _ollama_generate(prompt: str, temperature: float = 0.4) -> str:
    """로컬에 설치된 Ollama 모델로 생성. 이미지(비전)는 지원하지 않음 — 텍스트 전용.
    Ollama 앱이 실행 중이어야 하며, 이 PC 는 내장그래픽이라 CPU 로 돌아 다소 느릴 수 있음."""
    url = f"{config.OLLAMA_HOST}/api/generate"
    payload = {
        "model": config.OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature},
    }
    try:
        resp = requests.post(url, json=payload, timeout=180)   # CPU 생성 대비 넉넉한 타임아웃
    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            "Ollama 에 연결할 수 없습니다 — Ollama 앱이 실행 중인지 확인해주세요 "
            f"(설치: https://ollama.com, 주소: {config.OLLAMA_HOST})")
    if resp.status_code == 404:
        raise RuntimeError(f"모델 '{config.OLLAMA_MODEL}' 이 없습니다. "
                           f"cmd 에서 `ollama pull {config.OLLAMA_MODEL}` 을 먼저 실행해주세요.")
    if resp.status_code != 200:
        raise RuntimeError(f"Ollama HTTP {resp.status_code}: {resp.text[:200]}")
    return resp.json().get("response", "")


def _build_cards_ollama(prompt: str):
    text = _ollama_generate(prompt)
    return _extract_extras(text), _extract_cards(text)


# ── 공용: 다른 기능(채용공고 등)에서도 같은 AI 폴백 체인을 쓰도록 공개 ──

def generate_text(prompt: str, temperature: float = 0.4, images=None):
    """프롬프트(+이미지)를 AI 에 보내 원문 텍스트를 받는다. returns (text, engine, error).

    images: [(mime_type, base64), ...] — 채용공고 캡처 사진 등 (로컬 모델은 이미지 미지원)."""
    error = ""
    if config.GEMINI_API_KEY:
        try:
            return _gemini_generate(prompt, temperature=temperature, images=images), "gemini", ""
        except Exception as e:
            error = f"Gemini: {e}"
            print(f"[summarize] Gemini 호출 실패: {e}")
    if config.ANTHROPIC_API_KEY:
        try:
            return _claude_generate(prompt, images=images), "claude", ""
        except Exception as e:
            error = f"Claude: {e}"
            print(f"[summarize] Claude 호출 실패: {e}")
    if config.OLLAMA_MODEL and not images:   # 로컬 모델은 이미지(비전) 미지원
        try:
            return _ollama_generate(prompt, temperature=temperature), "ollama", ""
        except Exception as e:
            error = f"로컬 모델: {e}"
            print(f"[summarize] Ollama 호출 실패: {e}")
    return "", "none", error or "AI 키(GEMINI_API_KEY 등)가 설정되지 않음"


# ── ③ 휴리스틱 (무료, AI 미사용) — 기사 제목을 줄 단위로 나눔, 후보 1개만 ──

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


def _build_cards_heuristic(article: dict) -> list:
    title = article.get("title", "") or "뉴스 요약"
    for sep in (" - ", " | ", " :: "):
        if sep in title:
            title = title.split(sep)[0].strip()
    return [{"headline": _break_lines(title)}]


def _heuristic_summary(article: dict) -> str:
    """AI 없이 요약문 대신 쓸 텍스트 — og:description 또는 본문 앞부분."""
    desc = (article.get("description") or "").strip()
    if desc:
        return desc[:300]
    joined = " ".join(article.get("paragraphs") or [])[:300].strip()
    return joined
