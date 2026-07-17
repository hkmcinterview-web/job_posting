# -*- coding: utf-8 -*-
"""뉴스 링크에서 제목/요약/본문/대표사진/출처를 추출합니다."""
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept-Language": "ko,en;q=0.8",
}

# 네이버/다음 등, 실제로 "기사 본문만" 담고 있다고 확신할 수 있는 컨테이너.
# 본문 속 사진(image_urls)은 여기서 매칭됐을 때만 긁어온다.
SPECIFIC_BODY_SELECTORS = "#dic_area, #newsct_article, #articleBodyContents, #article-view-content-div"
# 위에서 못 찾았을 때 텍스트 추출용으로만 쓰는 넓은 폴백 — <article> 태그는 사이드바의
# '관련기사' 추천 위젯까지 포함하는 경우가 많아, 사진 후보로는 신뢰하지 않는다.
GENERIC_BODY_SELECTOR = "article"

# 로고/아이콘/광고로 흔히 쓰이는 파일명 패턴 — 본문 이미지 후보에서 제외
_JUNK_IMG_RE = re.compile(r"(logo|icon|sprite|banner|ad_|_ad\.|btn_|blank\.gif|pixel\.gif)", re.I)


def _upsize_cdn_thumbnail(url: str) -> str:
    """네이버(pstatic) 등 주요 CDN 썸네일 URL 을 원본/고해상도로 변환 시도."""
    if not url:
        return url
    # 네이버 pstatic: ?type=w150 등 리사이즈 파라미터 제거하면 원본에 가까워짐
    if "pstatic.net" in url and "type=" in url:
        url = re.sub(r"([?&])type=[^&]*", "", url)
        url = re.sub(r"[?&]$", "", url).replace("?&", "?")
    return url


def _clean_source(name: str) -> str:
    name = (name or "").strip()
    # "언론사명 | 네이버", "언론사명 - 네이버뉴스" 등에서 언론사명만
    name = re.split(r"[|·\-–:]", name)[0].strip()
    for junk in ("네이버뉴스", "네이버 뉴스", "네이버", "다음뉴스", "Daum", "NAVER"):
        name = name.replace(junk, "").strip()
    return name


def fetch_article(url: str) -> dict:
    resp = requests.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    def og(prop):
        tag = (soup.find("meta", property=f"og:{prop}")
               or soup.find("meta", attrs={"name": prop})
               or soup.find("meta", property=prop))
        return (tag.get("content") or "").strip() if tag and tag.get("content") else ""

    title = og("title")
    if not title and soup.title:
        title = soup.title.get_text(strip=True)
    description = og("description")
    site = og("site_name") or urlparse(url).netloc
    image_url = og("image")

    # 대표사진(og:image) + 본문 안의 다른 사진들 — 카드가 여러 장일 때 서로 다른 사진을 쓰기 위함
    image_urls, seen_img = [], set()
    for src in ([image_url] if image_url else []):
        u = _upsize_cdn_thumbnail(src)
        if u and u not in seen_img:
            seen_img.add(u)
            image_urls.append(u)
    body_node = soup.select_one(SPECIFIC_BODY_SELECTORS)
    is_specific_body = body_node is not None
    if body_node is None:
        body_node = soup.select_one(GENERIC_BODY_SELECTOR)  # 텍스트 추출용 (사진 후보로는 안 씀)

    if is_specific_body:
        for img in body_node.find_all("img"):
            src = img.get("src") or img.get("data-src") or ""
            if not src or _JUNK_IMG_RE.search(src):
                continue
            if src.startswith("//"):
                src = "https:" + src
            src = _upsize_cdn_thumbnail(src)
            if src not in seen_img:
                seen_img.add(src)
                image_urls.append(src)
            if len(image_urls) >= 8:
                break

    # 출처(언론사명) — 실제 매체명(og:site_name)을 우선하고, 기자명 등은 최후 대체로만 사용
    source = _clean_source(og("site_name"))
    if not source or source.lower() in ("naver", "daum", "네이버", "다음"):
        source = _clean_source(
            og("article:author") or og("author")
            or (soup.find("meta", attrs={"name": "twitter:creator"}) or {}).get("content", "")
        )
    if not source:
        host = urlparse(url).netloc.replace("www.", "")
        source = host.split(".")[0]

    # 본문 — 언론사 본문 컨테이너 우선, 없으면 <p> 태그
    paragraphs = []
    if body_node:
        for line in body_node.get_text("\n", strip=True).split("\n"):
            line = line.strip()
            if len(line) >= 25:
                paragraphs.append(line)
            if len(paragraphs) >= 20:
                break
    if len(paragraphs) < 2:
        for p in soup.find_all("p"):
            text = p.get_text(" ", strip=True)
            if len(text) >= 40:
                paragraphs.append(text)
            if len(paragraphs) >= 15:
                break

    return {
        "url": url,
        "title": title or url,
        "description": description,
        "site": site,
        "source": source,
        "image_url": image_url,
        "image_urls": image_urls,
        "paragraphs": paragraphs,
    }


def _shrink_screenshot(raw: bytes) -> bytes:
    """전체 화면 캡처가 너무 크면 AI 업로드가 수십 분씩 걸리며 멈춘 것처럼 보인다.
    가로 900px, 세로 최대 6000px 로 줄이고 JPEG 재압축해 크기를 확실히 제한한다."""
    import io

    from PIL import Image

    try:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        if img.width > 900:
            img = img.resize((900, round(img.height * 900 / img.width)), Image.LANCZOS)
        if img.height > 6000:   # 그 아래는 푸터/약관인 경우가 대부분
            img = img.crop((0, 0, img.width, 6000))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=72)
        out = buf.getvalue()
        print(f"[article] 캡처 축소: {len(raw)} → {len(out)} bytes ({img.width}x{img.height})")
        return out
    except Exception as e:
        print(f"[article] 캡처 축소 실패(원본 사용): {e}")
        return raw


def _rendered_page_text(url: str):
    """자바스크립트로만 그려지는 페이지 폴백 — 진짜 브라우저(Playwright)로 열어서
    렌더링이 끝난 뒤의 텍스트를 수집한다. returns (title, text, screenshot|None)

    - iframe 안쪽 문서까지 전부 뒤져서 텍스트를 모은다 (채용 사이트가 상세 내용을
      iframe 에 넣는 경우가 많음)
    - 그래도 텍스트가 거의 없으면(공고가 이미지인 경우) 페이지 전체 스크린샷을
      찍어서 반환 — AI 비전으로 이미지를 직접 읽게 한다
    - playwright 미설치면 빈 값 반환. 설치:  pip install playwright → playwright install chromium"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[article] playwright 미설치 — 브라우저 렌더링 폴백 생략")
        return "", "", None
    screenshot = None
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(user_agent=HEADERS["User-Agent"])
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(3000)   # 스크립트가 내용을 그릴 시간
                try:  # 지연 로딩 대비 스크롤
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                except Exception:
                    pass
                page.wait_for_timeout(2500)
                title = page.title() or ""
                texts = []
                for frame in page.frames:   # 메인 문서 + 모든 iframe
                    try:
                        t = frame.evaluate("() => document.body ? document.body.innerText : ''")
                        if t and t.strip():
                            texts.append(t)
                    except Exception:
                        pass
                text = "\n".join(texts)
                if len(" ".join(text.split())) < 600:
                    try:  # 텍스트가 부실 → 상세가 이미지일 가능성, 화면을 통째로 캡처
                        page.evaluate("window.scrollTo(0, 0)")
                        screenshot = page.screenshot(full_page=True, type="jpeg", quality=80)
                        print(f"[article] 텍스트가 부족해 전체 화면 캡처 ({len(screenshot)} bytes)")
                        screenshot = _shrink_screenshot(screenshot)
                    except Exception as e:
                        print(f"[article] 화면 캡처 실패: {e}")
            finally:
                browser.close()
    except Exception as e:
        print(f"[article] 브라우저 렌더링 실패({url}): {e}")
        return "", "", None

    lines, prev = [], None
    for raw in (text or "").split("\n"):
        line = " ".join(raw.split())
        if len(line) < 2 or line == prev:
            continue
        prev = line
        lines.append(line)
    return title, "\n".join(lines)[:9000], screenshot


def fetch_job_page(url: str) -> dict:
    """채용공고 페이지에서 눈에 보이는 텍스트를 폭넓게 수집합니다.

    채용 사이트는 뉴스처럼 정형화된 본문 컨테이너가 없어서,
    script/style 등을 제거한 뒤 페이지 전체 텍스트를 가져와 AI 에 넘깁니다."""
    resp = requests.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    def og(prop):
        tag = (soup.find("meta", property=f"og:{prop}")
               or soup.find("meta", attrs={"name": prop}))
        return (tag.get("content") or "").strip() if tag and tag.get("content") else ""

    title = og("title")
    if not title and soup.title:
        title = soup.title.get_text(strip=True)

    # 회사 로고 후보 — 카드 우상단에 사용 (apple-touch-icon 이 보통 고화질 정사각 로고)
    logo_url = ""
    for rel in ("apple-touch-icon", "apple-touch-icon-precomposed", "icon", "shortcut icon"):
        tag = soup.find("link", rel=lambda v: v and rel in (v if isinstance(v, str) else " ".join(v)).lower())
        if tag and tag.get("href"):
            logo_url = urljoin(url, tag["href"])
            break
    og_image = og("image")
    if og_image:
        og_image = urljoin(url, og_image)

    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()

    lines, prev = [], None
    for raw in (soup.body or soup).get_text("\n").split("\n"):
        line = " ".join(raw.split())
        if len(line) < 2 or line == prev:
            continue
        prev = line
        lines.append(line)
    text = "\n".join(lines)[:9000]

    # 내용이 부실하면 자바스크립트 렌더링 페이지로 보고 실제 브라우저로 재시도.
    # 채용공고는 상세를 이미지로 올리는 경우가 많아, 텍스트가 넉넉히 안 나오면
    # 전체 화면 캡처를 확보해 AI 비전으로 읽게 한다 (임계값을 넉넉히 600자로).
    screenshot = None
    if len(text) < 600:
        r_title, r_text, screenshot = _rendered_page_text(url)
        if len(r_text) > len(text):
            print(f"[article] 브라우저 렌더링으로 {len(r_text)}자 수집 (일반 방식: {len(text)}자)")
            text = r_text
            title = title or r_title
        if len(text) >= 600:
            screenshot = None   # 텍스트를 충분히 얻었으면 캡처는 불필요

    return {
        "url": url,
        "title": title,
        "description": og("description"),
        "site": og("site_name") or urlparse(url).netloc,
        "text": text,
        "logo_url": logo_url,      # link rel 아이콘 (있으면 우선)
        "og_image_url": og_image,  # og:image — 채용 사이트에선 보통 회사 로고
        "screenshot": screenshot,  # 텍스트를 못 읽었을 때의 전체 화면 캡처 (jpeg bytes)
    }


def fetch_image_bytes(image_url: str, referer: str = "") -> bytes:
    """기사 대표사진 다운로드 (일부 언론사는 Referer 를 요구)."""
    headers = dict(HEADERS)
    if referer:
        headers["Referer"] = referer
    resp = requests.get(image_url, headers=headers, timeout=20)
    resp.raise_for_status()
    return resp.content
