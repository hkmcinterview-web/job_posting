# -*- coding: utf-8 -*-
"""텔레그램 메시지 파싱.

- 맨 앞 키워드로 동작 구분: '카페' → 카페 글, '카드' → 카드뉴스
- 카페 글: 제목/본문 분리 (링크는 본문 위치 그대로 유지)
- 카드뉴스: 본문에서 뉴스 링크 추출
"""
import re

URL_RE = re.compile(r"https?://[^\s<>\"]+")
TRAILING_PUNCT = ").,>]\"'”’"

CAFE_WORDS = ("카페", "cafe", "글")
CARD_WORDS = ("카드", "card", "카드뉴스")
JOB_WORDS = ("채용", "채용공고", "job")
EXPAND_WORDS = ("펼치기", "펼침", "링크펼치기", "expand")
CANCEL_WORDS = ("취소", "중지", "정지", "그만", "stop", "cancel")
FINISH_WORDS = ("완료", "끝", "다됐어", "done", "finish")
NEWS_WORDS = ("뉴스", "뉴스검색", "이슈검색")
TREND_WORDS = ("트렌드", "트렌드검색")
DOMESTIC_ISSUE_WORDS = ("국내이슈", "국내핫이슈")
GLOBAL_ISSUE_WORDS = ("해외이슈", "글로벌이슈", "세계이슈", "전세계이슈", "해외핫이슈")
HEADLINE_WORDS = ("헤드라인", "톱뉴스", "탑뉴스", "newsapi", "headline")
LOGO_WORDS = ("로고", "logo")
LOGO_CLEAR_WORDS = ("로고삭제", "로고제거", "로고초기화", "로고끄기")


def detect_mode(text: str):
    """returns (mode, rest_text). mode ∈
    {'cafe','card','job','expand','cancel','finish','news','trend',
     'domestic_issue','global_issue','headline','logo','logo_clear',None}"""
    stripped = (text or "").lstrip()
    # 첫 토큰(공백/줄바꿈/콜론 전까지)
    head = re.split(r"[\s:：]", stripped, 1)[0].lower()
    rest = stripped[len(head):].lstrip(" :：\n\t")
    if head in CANCEL_WORDS:
        return "cancel", rest
    if head in FINISH_WORDS:
        return "finish", rest
    if head in NEWS_WORDS:
        return "news", rest
    if head in TREND_WORDS:
        return "trend", rest
    if head in DOMESTIC_ISSUE_WORDS:
        return "domestic_issue", rest
    if head in GLOBAL_ISSUE_WORDS:
        return "global_issue", rest
    if head in HEADLINE_WORDS:
        return "headline", rest
    if head in LOGO_CLEAR_WORDS:
        return "logo_clear", rest
    if head in LOGO_WORDS:
        return "logo", rest
    if head in CAFE_WORDS:
        return "cafe", rest
    if head in CARD_WORDS:
        return "card", rest
    if head in JOB_WORDS:
        return "job", rest
    if head in EXPAND_WORDS:
        return "expand", rest
    return None, text


def extract_links(text: str):
    links, seen = [], set()
    for raw in URL_RE.findall(text or ""):
        url = raw.rstrip(TRAILING_PUNCT)
        if url not in seen:
            seen.add(url)
            links.append(url)
    return links


def split_title_body(text: str):
    """카페 글용 — 첫 줄(또는 '제목:' 표기)을 제목으로, 나머지를 본문으로.
    본문의 링크는 그대로 둔다 (사용자가 편집한 레이아웃 보존)."""
    lines = (text or "").replace("\r", "").split("\n")
    # 앞쪽 빈 줄 제거
    while lines and not lines[0].strip():
        lines.pop(0)

    title = ""
    if lines:
        first = lines[0].strip()
        if first.startswith("제목:") or first.startswith("제목 :"):
            title = first.split(":", 1)[1].strip()
            lines = lines[1:]
        elif len(first) <= 50 and URL_RE.search(first) is None:
            title = first
            lines = lines[1:]

    # 제목 다음 빈 줄 제거
    while lines and not lines[0].strip():
        lines.pop(0)

    return title, "\n".join(lines)
