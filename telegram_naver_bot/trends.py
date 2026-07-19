# -*- coding: utf-8 -*-
"""화제의 뉴스/검색어 찾기.

① 네이버 뉴스 검색 API — 키워드로 최근 기사를 모아, 여러 언론사가 같은 소식을
   다룬(=화제성이 높은) 순서로 정렬해서 상위 몇 개를 추천한다.
② 구글 트렌드 — 특정 산업에 한정되지 않는, 국내/해외 실시간 인기 검색어와
   관련 뉴스를 가져온다.

⚠️ 구글 트렌드는 공식 API 가 아니라 비공식 RSS 피드(trends.google.com)를 쓴다.
언제든 형식이 바뀔 수 있어, 실패하면 로그를 보고 파서를 조정해야 할 수 있다.
이 봇 개발 환경에서는 trends.google.com 접근이 막혀 있어 실제 응답으로
검증하지 못했다 — 처음 실행 시 결과가 이상하면 콘솔 로그를 확인해달라.
"""
import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

import requests

import config

_TAG_RE = re.compile(r"<[^>]+>")
_WORD_RE = re.compile(r"[^\w가-힣]+")

_TRENDS_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
}


def _clean(text: str) -> str:
    return html.unescape(_TAG_RE.sub("", text or "")).strip()


def _tokenize(title: str) -> set:
    return {w for w in _WORD_RE.split(title) if len(w) >= 2}


def search_naver_news(keyword: str, count: int = 8, hours: int = 48) -> list:
    """네이버 뉴스 검색 — keyword 관련 최근(hours 이내) 기사 중, 제목이 비슷한
    (=같은 소식을 여러 언론사가 다룬) 기사가 많을수록 화제성이 높다고 보고
    그 순서로 정렬해 상위 count 개를 반환한다.

    returns [{"title","link","count","pubDate"}]  (count = 비슷한 보도 개수)
    """
    if not (config.NAVER_CLIENT_ID and config.NAVER_CLIENT_SECRET):
        raise RuntimeError("NAVER_CLIENT_ID/SECRET 이 .env 에 설정되어 있지 않습니다.")

    headers = {
        "X-Naver-Client-Id": config.NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": config.NAVER_CLIENT_SECRET,
    }
    resp = requests.get(
        "https://openapi.naver.com/v1/search/news.json",
        params={"query": keyword, "display": 100, "start": 1, "sort": "date"},
        headers=headers, timeout=20,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"네이버 뉴스 검색 실패 (HTTP {resp.status_code}): {resp.text[:200]}")
    items = resp.json().get("items", [])

    now = datetime.now()
    candidates = []
    for it in items:
        pub = None
        try:
            pub = parsedate_to_datetime(it.get("pubDate", ""))
            if pub.tzinfo:
                pub = pub.replace(tzinfo=None)
        except Exception:
            pass
        if pub and (now - pub) > timedelta(hours=hours):
            continue   # 너무 오래된 기사는 화제성 판단에서 제외
        title = _clean(it.get("title", ""))
        link = it.get("link") or it.get("originallink") or ""
        if not title or not link:
            continue
        candidates.append({"title": title, "link": link, "pubDate": it.get("pubDate", "")})

    # 제목 단어 겹침으로 '같은 소식'을 묶어서, 커버리지(보도 언론사 수)로 화제성 근사
    clusters = []
    used = [False] * len(candidates)
    for i, a in enumerate(candidates):
        if used[i]:
            continue
        used[i] = True
        aw = _tokenize(a["title"])
        group = [a]
        for j in range(i + 1, len(candidates)):
            if used[j] or not aw:
                continue
            bw = _tokenize(candidates[j]["title"])
            if not bw:
                continue
            overlap = len(aw & bw) / max(1, min(len(aw), len(bw)))
            if overlap >= 0.5:
                group.append(candidates[j])
                used[j] = True
        rep = group[0]   # sort=date 순서라 그룹의 첫 기사가 가장 최신
        clusters.append({"title": rep["title"], "link": rep["link"],
                         "count": len(group), "pubDate": rep["pubDate"]})

    clusters.sort(key=lambda c: c["count"], reverse=True)
    return clusters[:count]


def fetch_google_trends(geo: str = "KR", count: int = 10) -> list:
    """구글 트렌드 일일 인기 검색어(비공식 RSS). 국내/해외 어떤 산업에도
    한정되지 않는 '지금 뜨는' 검색어 + 관련 뉴스 기사를 가져온다.

    returns [{"title","traffic","articles":[{"title","link","source"}, ...]}]
    """
    url = f"https://trends.google.com/trending/rss?geo={geo}"
    try:
        resp = requests.get(url, timeout=20, headers=_TRENDS_HEADERS)
    except Exception as e:
        raise RuntimeError(f"구글 트렌드 요청 실패: {e}")
    if resp.status_code != 200:
        raise RuntimeError(f"구글 트렌드 응답 실패 (HTTP {resp.status_code})")

    ns = {"ht": "https://trends.google.com/trends/trendingsearches/daily"}
    try:
        root = ET.fromstring(resp.content)
    except Exception as e:
        snippet = resp.content[:300]
        raise RuntimeError(f"구글 트렌드 RSS 파싱 실패(형식이 바뀌었을 수 있음): {e}\n{snippet}")

    results = []
    for item in root.iter("item"):
        title_el = item.find("title")
        title = (title_el.text or "").strip() if title_el is not None else ""
        if not title:
            continue
        traffic_el = item.find("ht:approx_traffic", ns)
        traffic = (traffic_el.text or "").strip() if traffic_el is not None else ""

        articles = []
        for news in item.findall("ht:news_item", ns):
            nt = news.find("ht:news_item_title", ns)
            nu = news.find("ht:news_item_url", ns)
            nsrc = news.find("ht:news_item_source", ns)
            if nt is not None and nu is not None and (nt.text or "").strip():
                articles.append({
                    "title": (nt.text or "").strip(),
                    "link": (nu.text or "").strip(),
                    "source": (nsrc.text or "").strip() if nsrc is not None else "",
                })

        results.append({"title": title, "traffic": traffic, "articles": articles[:3]})
        if len(results) >= count:
            break
    return results
