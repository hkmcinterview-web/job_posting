# -*- coding: utf-8 -*-
"""카페 글쓰기 999 오류 원인 진단.

짧은 글은 되는데 특정 글만 실패할 때, 그 글을 여러 조각으로 나눠 각각 올려보고
어느 요소(본문 길이/링크/HTML 링크태그 등)가 999 를 유발하는지 짚어냅니다.

사용법:
  1) 아래 FAILED_TITLE / FAILED_BODY 에 실패했던 글의 제목/본문을 붙여넣기
  2) python test_cafe_content.py
  각 조각 사이에 70초 간격을 자동으로 둡니다 (연속 등록 제한 회피).
"""
import re
import time

from editor import build_cafe_post
from naver_cafe import post_article

# ── 여기에 실패했던 글을 붙여넣으세요 ─────────────────────
FAILED_TITLE = "여기에 제목"
FAILED_BODY = """여기에
본문 전체를
그대로 붙여넣기
https://링크가 있으면 포함해서
"""
# ────────────────────────────────────────────────────

URL_RE = re.compile(r"https?://[^\s<>\"]+")


def _try(label: str, title: str, body: str):
    subject, content_html = build_cafe_post(f"[진단-{label}] {title}"[:80], body)
    try:
        result = post_article(subject, content_html, image_paths=None)
        print(f"  ✅ [{label}] 성공 → {result.get('articleUrl')}")
        return True
    except Exception as e:
        msg = str(e)[:120]
        print(f"  ❌ [{label}] 실패 → {msg}")
        return False


def main():
    body = FAILED_BODY.strip("\n")
    no_link_body = URL_RE.sub("(링크생략)", body)
    links = URL_RE.findall(body)
    short_body = body[:200]

    print("실패했던 글을 조각내어 하나씩 올려봅니다 (조각마다 70초 대기).\n")

    tests = [
        ("A-제목+짧은본문", FAILED_TITLE, "진단용 짧은 본문입니다."),
        ("B-링크제거전체", FAILED_TITLE, no_link_body),
        ("C-본문앞200자", FAILED_TITLE, short_body),
        ("D-전체원본", FAILED_TITLE, body),
    ]
    if links:
        tests.append(("E-링크만", FAILED_TITLE, "\n".join(links)))

    results = {}
    for i, (label, t, b) in enumerate(tests):
        if i > 0:
            print("  (70초 대기...)")
            time.sleep(70)
        print(f"[{label}] 게시 중... (본문 {len(b)}자, 링크 {len(URL_RE.findall(b))}개)")
        results[label] = _try(label, t, b)

    print("\n===== 결과 요약 =====")
    for label, ok in results.items():
        print(f"  {'✅' if ok else '❌'} {label}")
    print("\n해석:")
    print("  · A 성공 + D 실패 → 글 내용 문제 확정")
    print("  · B(링크제거) 성공 + D 실패 → '링크'가 원인")
    print("  · C(앞200자) 성공 + D 실패 → '본문 길이'가 원인")
    print("  · E(링크만) 실패 → 링크 개수/도메인이 원인")


if __name__ == "__main__":
    main()
