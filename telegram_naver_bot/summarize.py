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
        "- ⚠️⚠️ 모든 출력(요약·배경·전망·캡션·헤드라인·해시태그)은 반드시 '한국어'로만 작성하세요. "
        "영어 고유명사/약어(AI, RX, SK, EV 등)는 그대로 써도 되지만, "
        "중국어(汉字 문장)·일본어(かな) 등 다른 언어는 절대 쓰지 마세요. "
        "기사가 외국어면 한국어로 번역해서 쓰고, 해시태그도 한국어로 다세요.\n"
        "- ⚠️ HEADLINE 아래에는 실제 헤드라인 문장만 한 줄씩 쓰고, "
        "'(첫째 줄)', '(둘째 줄)' 같은 표시/라벨은 절대 쓰지 마세요.\n"
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
        "헤드라인 첫 줄\n"
        "헤드라인 둘째 줄\n"
        "헤드라인 셋째 줄(필요할 때만)\n"
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
# 모델이 프롬프트의 자리표시자를 그대로 베낀 경우 제거 — 예: "(첫째 줄) 삼성전자," → "삼성전자,"
_LINE_MARKER_RE = re.compile(r"^\s*\((?:[^)]*줄[^)]*|헤드라인[^)]*)\)\s*")


def _clean_headline(headline: str) -> str:
    """헤드라인 각 줄에서 '(첫째 줄)' 류 표시 문구와 앞뒤 공백을 제거하고 빈 줄은 버린다."""
    out = []
    for ln in (headline or "").split("\n"):
        ln = _LINE_MARKER_RE.sub("", ln).strip()
        # 줄 전체가 '헤드라인 첫 줄' 같은 자리표시자면 버린다
        if ln and ln not in ("헤드라인 첫 줄", "헤드라인 둘째 줄", "헤드라인 셋째 줄",
                             "헤드라인 셋째 줄(필요할 때만)"):
            out.append(ln)
    return "\n".join(out)
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


def _extract_community_extras(text: str) -> dict:
    """커뮤니티 카드 재료: summary(본문 요약) / comments(댓글 반응 요약) / caption."""
    comments = " ".join(ln.strip() for ln in _extract_block(text, "COMMENTS").split("\n")
                        if ln.strip())
    return {
        "summary": _extract_summary(text),
        "comments": comments,
        "caption": _extract_block(text, "CAPTION"),
    }


def _build_community_prompt(post: str, comments: str, n_options: int) -> str:
    """커뮤니티 글 카드뉴스용 프롬프트 — 본문 요약(2장) + 댓글 반응 요약(3장) + 헤드라인 후보."""
    post = (post or "")[:5000]
    comments = (comments or "")[:4000]
    has_comments = bool(comments.strip())
    return (
        "다음은 온라인 커뮤니티 글의 '본문'과 그 아래 '댓글들'입니다.\n"
        "이걸로 공대생/이공계 취준생 대상 인스타 카드뉴스(캐러셀)를 만듭니다.\n"
        "뉴스가 아니라 '커뮤니티 화제글'이므로, 딱딱하지 않고 공감·재미 위주로.\n\n"
        f"같은 카드에 쓸 서로 다른 톤의 헤드라인 후보를 정확히 {n_options}개 만들어 주세요.\n\n"
        "본문 요약(SUMMARY, 2장 슬라이드용) 규칙:\n"
        "- 이 글이 무슨 얘기인지 4~6문장으로 자연스럽게 (핵심 상황·맥락)\n"
        "- 한 문장에 한 줄씩, 가장 핵심 1~2곳만 {{이렇게}} 감싸 강조\n\n"
        "댓글 반응 요약(COMMENTS, 3장 슬라이드용) 규칙:\n"
        "- 댓글들에서 드러나는 '사람들의 반응'을 2~4문장으로 정리 "
        "(공감이 몰린 의견, 갈리는 지점, 인상적/재치있는 반응 등)\n"
        "- 특정 댓글을 지어내지 말고 실제 댓글 흐름에 근거해서. 가장 인상적인 한 곳만 {{강조}}\n"
        + ("- ⚠️ 별도 [댓글들]이 없어도, 아래 [커뮤니티 본문]에 댓글/답글/반응이 함께 "
           "붙어있는 경우가 많습니다. 본문 뒷부분의 짧은 여러 반응들을 댓글로 보고 COMMENTS 를 "
           "꼭 채워주세요. 정말 반응이 하나도 없이 글만 있을 때만 COMMENTS 를 비우세요\n"
           if not has_comments else "")
        + "\n캡션(CAPTION, 인스타 게시글 본문용) 규칙:\n"
        "- 1~2문장 요약 + 취준생 관점 한마디, 마지막 줄에 해시태그 6~8개\n\n"
        "헤드라인/공통 규칙:\n"
        "- ⚠️⚠️ 모든 출력은 반드시 '한국어'로만. 영어 고유명사/약어는 OK지만 "
        "중국어(汉字 문장)·일본어(かな)는 절대 금지.\n"
        "- HEADLINE 아래에는 실제 문장만 한 줄씩. '(첫째 줄)' 같은 표시는 쓰지 말 것.\n"
        "- HEADLINE 은 2~3줄, 각 줄 8~14자, 위트있게(커뮤니티 감성). 제목 그대로 베끼지 말 것.\n"
        "- TAG: 2~4자 카테고리 (예: 이슈, 공감, 취업, 현직, 꿀팁, 논란)\n"
        "- HIGHLIGHT: HEADLINE 중 강조할 한 줄을 그대로 복사\n"
        "- STYLE: marker 또는 color 중 하나\n\n"
        "출력 형식 — 아래를 정확히 지켜서 다른 설명 없이 작성:\n"
        "<<<SUMMARY>>>\n(본문 요약, 한 문장에 한 줄)\n<<<END>>>\n\n"
        "<<<COMMENTS>>>\n(댓글 반응 요약)\n<<<END>>>\n\n"
        "<<<CAPTION>>>\n(캡션 본문)\n#해시태그 #들\n<<<END>>>\n\n"
        "<<<CARD>>>\nTAG: (태그)\nHIGHLIGHT: (강조할 한 줄)\nSTYLE: marker 또는 color\n"
        "HEADLINE:\n헤드라인 첫 줄\n헤드라인 둘째 줄\n<<<END>>>\n"
        f"(CARD 블록을 총 {n_options}번 반복)\n\n"
        f"[커뮤니티 본문]\n{post}\n\n"
        f"[댓글들]\n{comments if has_comments else '(별도로 주어지지 않음 — 위 본문 안에서 반응/댓글을 찾아 요약하세요)'}"
    )


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
        headline = _clean_headline(headline)

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


def _has_language_drift(text: str) -> bool:
    """생성 결과가 한국어를 벗어나 중국어(한자)/일본어(가나)로 흘렀는지 감지.
    한국어 카드에 일본어 가나가 나오거나, 한자가 한글 대비 과도하면 이탈로 본다."""
    if not text:
        return False
    hangul = cjk = kana = 0
    for ch in text:
        o = ord(ch)
        if 0xAC00 <= o <= 0xD7A3:
            hangul += 1
        elif 0x4E00 <= o <= 0x9FFF:      # CJK 한자 (주로 중국어)
            cjk += 1
        elif 0x3040 <= o <= 0x30FF:      # 일본어 히라가나/가타카나
            kana += 1
    if kana > 0:
        return True
    # 한자가 8자 이상이고 한글보다 절반 넘게 많으면 중국어로 이탈한 것으로 판단
    if cjk >= 8 and cjk > max(1, hangul) * 0.5:
        return True
    return False


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
            out = "".join(p.get("text", "") for p in parts)
            if _has_language_drift(out):
                # 이 모델이 중국어/일본어로 이탈 — 결과 버리고 다음 모델/키로 재시도
                last_err = f"키{ki} 모델 '{model}' 출력이 한국어를 벗어남(중국어/일본어)"
                print(f"[summarize] {last_err} — 다음 모델로 재시도")
                continue
            return out

    raise RuntimeError(last_err or "사용 가능한 Gemini 모델 없음")


def _build_cards_gemini(prompt: str):
    text = _gemini_generate(prompt)
    return _extract_extras(text), _extract_cards(text)


# ── OpenRouter (무료 오픈모델 — '비교' 전용) ──────────────────

def _openai_chat(url: str, api_key: str, model: str, prompt: str,
                 temperature: float, extra_headers: dict = None) -> str:
    """OpenAI 호환 chat/completions 엔드포인트(OpenRouter·Groq 공용) 호출."""
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    resp = requests.post(
        url,
        headers=headers,
        json={"model": model,
              "messages": [{"role": "user", "content": prompt}],
              "temperature": temperature},
        timeout=60,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
    choices = resp.json().get("choices", [])
    if not choices:
        raise RuntimeError("응답에 결과 없음(모델 사용량 초과/ID 변경 가능)")
    return choices[0].get("message", {}).get("content", "") or ""


def _openrouter_generate(prompt: str, model: str, temperature: float = 0.9) -> str:
    """OpenRouter 로 무료 오픈모델(Qwen·Llama·DeepSeek 등)에 프롬프트를 보낸다.
    model 은 ':free' 로 끝나는 무료 모델 ID 여야 과금 위험이 없다."""
    if not config.OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY 가 설정되지 않음")
    return _openai_chat("https://openrouter.ai/api/v1/chat/completions",
                        config.OPENROUTER_API_KEY, model, prompt, temperature,
                        {"X-Title": "jobnyou-cardnews-bot"})


def _groq_generate(prompt: str, model: str, temperature: float = 0.9) -> str:
    """Groq 로 무료 오픈모델(Llama·Gemma 등)에 프롬프트를 보낸다. 무료 한도가 넉넉하고 빠름."""
    if not config.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY 가 설정되지 않음")
    return _openai_chat("https://api.groq.com/openai/v1/chat/completions",
                        config.GROQ_API_KEY, model, prompt, temperature)


def _openrouter_label(model: str) -> str:
    return f"{model.split('/')[-1].replace(':free', '')} (OpenRouter)"


# 한국어가 상대적으로 좋은 오픈모델 계열 — 자동 탐색 시 우선순위
_KOREAN_FRIENDLY = ("qwen", "llama", "deepseek", "gemma", "mistral", "nemotron", "glm", "yi")


def list_openrouter_free_models(limit: int = 3) -> list:
    """OpenRouter 모델 목록 API 에서 '지금 가격이 0(무료)'인 모델만 골라 반환.
    무료 모델 ID 가 수시로 바뀌므로 하드코딩 대신 실시간으로 찾는다.
    한국어에 강한 계열(qwen·llama·deepseek·gemma…)을 우선, 컨텍스트 큰 순으로."""
    if not config.OPENROUTER_API_KEY:
        return []
    resp = requests.get(
        "https://openrouter.ai/api/v1/models",
        headers={"Authorization": f"Bearer {config.OPENROUTER_API_KEY}"},
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"모델 목록 조회 실패 (HTTP {resp.status_code})")

    ranked = []
    for m in resp.json().get("data", []):
        mid = m.get("id", "")
        pricing = m.get("pricing", {}) or {}
        try:
            p = float(pricing.get("prompt", "0"))
            c = float(pricing.get("completion", "0"))
        except (TypeError, ValueError):
            continue
        if not mid or p != 0 or c != 0:
            continue
        low = mid.lower()
        fam = next((len(_KOREAN_FRIENDLY) - i for i, f in enumerate(_KOREAN_FRIENDLY)
                    if f in low), 0)
        ctx = m.get("context_length") or 0
        ranked.append((fam, ctx, mid))

    ranked.sort(reverse=True)
    return [mid for _, _, mid in ranked[:limit]]


def _resolve_openrouter_models() -> list:
    """비교에 쓸 OpenRouter 모델 결정 — .env 에 지정했으면 그걸, 아니면 무료 자동 탐색."""
    if config.OPENROUTER_MODELS:
        return config.OPENROUTER_MODELS
    try:
        return list_openrouter_free_models(config.OPENROUTER_AUTO_COUNT)
    except Exception as e:
        print(f"[summarize] OpenRouter 무료 모델 자동 탐색 실패: {e}")
        return []


def _compare_models(prompt: str, extras_fn, n_options: int = 3) -> list:
    """주어진 프롬프트를 Gemini + Groq + OpenRouter 무료 모델들에 '병렬'로 돌려 비교.
    extras_fn(text) 로 모델별 캐러셀 재료(요약 등)를 뽑는다.
    returns [{"provider","options","extras","error"}]"""
    import concurrent.futures

    groq_models = config.GROQ_MODELS if config.GROQ_API_KEY else []
    or_models = _resolve_openrouter_models() if config.OPENROUTER_API_KEY else []

    jobs = []   # (label, callable)
    if config.GEMINI_API_KEY:
        jobs.append(("Gemini", lambda: _gemini_generate(prompt)))
    for model in groq_models:
        jobs.append((f"{model.split('/')[-1]} (Groq)",
                     lambda m=model: _groq_generate(prompt, m)))
    for model in or_models:
        jobs.append((_openrouter_label(model),
                     lambda m=model: _openrouter_generate(prompt, m)))

    def _run(label, fn):
        try:
            text = fn()
            if _has_language_drift(text):
                return {"provider": label, "options": [], "extras": {},
                        "error": "출력이 한국어를 벗어남(중국어/일본어)"}
            return {"provider": label, "options": _extract_cards(text),
                    "extras": extras_fn(text), "error": ""}
        except Exception as e:
            return {"provider": label, "options": [], "extras": {}, "error": str(e)}

    results = []
    if not jobs:
        return results
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(jobs)) as ex:
        futs = [ex.submit(_run, lbl, fn) for lbl, fn in jobs]
        for fut in concurrent.futures.as_completed(futs):
            results.append(fut.result())

    order = (["Gemini"]
             + [f"{m.split('/')[-1]} (Groq)" for m in groq_models]
             + [_openrouter_label(m) for m in or_models])
    results.sort(key=lambda r: order.index(r["provider"]) if r["provider"] in order else 99)
    return results


def compare_card_options(article: dict, n_options: int = 3) -> list:
    """뉴스 기사 카드 — 여러 모델로 헤드라인 후보를 비교."""
    n_options = max(2, min(3, n_options))
    return _compare_models(_build_prompt(article, n_options), _extract_extras, n_options)


def compare_community_options(post: str, comments: str, n_options: int = 3) -> list:
    """커뮤니티 글 카드 — 본문 요약(2장) + 댓글 반응 요약(3장)을 여러 모델로 비교."""
    n_options = max(2, min(3, n_options))
    return _compare_models(_build_community_prompt(post, comments, n_options),
                           _extract_community_extras, n_options)


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
