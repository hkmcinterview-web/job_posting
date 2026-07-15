# -*- coding: utf-8 -*-
"""카페 글쓰기 999 오류 — '링크 개수 임계값' 진단.

짧은 글은 되는데 링크 많은 글이 999 로 막힐 때, 링크 개수를 0→1→3→5→8→전체로
단계적으로 늘려가며 올려보고 '몇 개부터 막히는지'를 찾습니다.
또한 buly.kr 단축주소를 원본 주소로 펼친 버전도 따로 테스트합니다
(단축주소 도메인만 차단된 건지 확인).

사용법:
  1) 아래 FAILED_TITLE / FAILED_BODY 에 실패했던 글을 붙여넣기
  2) python test_cafe_content.py
  각 조각 사이에 70초 간격을 자동으로 둡니다 (연속 등록 제한 회피).
"""
import re
import time

import requests

from editor import build_cafe_post
from naver_cafe import post_article

# ── 여기에 실패했던 글을 붙여넣으세요 ─────────────────────
FAILED_TITLE = "2026.07.15 자동차산업 신문기사 정리"
FAILED_BODY = """07/15(수)

[완성차]
현대차그룹 '대형 전기SUV'로 국내 시장 판 키운다
https://buly.kr/15RHUPZ
"""
# ────────────────────────────────────────────────────

URL_RE = re.compile(r"https?://[^\s<>\"]+")


def _post(label: str, body: str) -> bool:
    subject, content_html = build_cafe_post(f"[진단-{label}] {FAILED_TITLE}"[:80], body)
    try:
        result = post_article(subject, content_html, image_paths=None)
        print(f"  ✅ [{label}] 성공 → {result.get('articleUrl')}")
        return True
    except Exception as e:
        print(f"  ❌ [{label}] 실패 → {str(e)[:110]}")
        return False


def _body_with_n_links(n: int) -> str:
    """본문에서 링크를 앞에서부터 n 개만 남기고 나머지 링크는 제거."""
    kept = 0
    out = []
    for line in FAILED_BODY.split("\n"):
        if URL_RE.search(line):
            if kept < n:
                out.append(line)
                kept += 1
            # n 개 넘으면 그 링크 줄은 통째로 생략
        else:
            out.append(line)
    return "\n".join(out)


def _expand_short(url: str) -> str:
    """buly.kr 등 단축주소를 따라가 최종(원본) 주소를 얻는다."""
    try:
        r = requests.head(url, allow_redirects=True, timeout=10)
        return r.url
    except Exception:
        try:
            r = requests.get(url, allow_redirects=True, timeout=10, stream=True)
            return r.url
        except Exception:
            return url


def main():
    all_links = URL_RE.findall(FAILED_BODY)
    total = len(all_links)
    print(f"본문 총 링크 수: {total}개\n")

    steps = [0, 1, 3, 5, 8, total]
    steps = sorted(set(s for s in steps if s <= total))

    results = {}
    first = True
    for n in steps:
        if not first:
            print("  (70초 대기...)")
            time.sleep(70)
        first = False
        body = _body_with_n_links(n)
        print(f"[링크{n}개] 게시 중...")
        results[f"링크{n}개"] = _post(f"링크{n}", body)

    # 단축주소를 원본으로 펼친 전체 버전도 테스트
    if total:
        print("  (70초 대기...)")
        time.sleep(70)
        print(f"[원본주소펼침-전체{total}개] 단축주소 펼치는 중...")
        expanded = FAILED_BODY
        for u in all_links:
            expanded = expanded.replace(u, _expand_short(u))
        print("[원본주소펼침] 게시 중...")
        results["원본주소펼침"] = _post("원본펼침", expanded)

    print("\n===== 결과 요약 =====")
    for label, ok in results.items():
        print(f"  {'✅' if ok else '❌'} {label}")
    print("\n해석:")
    print("  · 링크N개까지 성공하고 그 위부터 실패 → 그 N 이 본문 링크 허용 한도")
    print("  · '원본주소펼침'만 성공 → buly.kr 단축주소가 차단된 것 (원본으로 펼치면 해결)")
    print("  · 링크0개도 실패 → 링크가 아닌 다른 원인 (길이/금칙어 등)")


if __name__ == "__main__":
    main()
