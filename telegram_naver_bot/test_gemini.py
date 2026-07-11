# -*- coding: utf-8 -*-
"""Gemini API 키가 제대로 되는지만 빠르게 확인하는 도구.

사용법:  python test_gemini.py
(.env 의 GEMINI_API_KEY / GEMINI_MODEL 을 읽어서 실제로 한 번 호출해봅니다)
"""
import requests

import config


def main():
    key = config.GEMINI_API_KEY
    if not key:
        print("❌ .env 의 GEMINI_API_KEY 가 비어 있습니다. 키를 넣어주세요.")
        return
    print(f"🔑 키 확인: {key[:6]}...{key[-4:]} (길이 {len(key)})")
    print(f"📦 설정 모델: {config.GEMINI_MODEL}\n")

    payload = {"contents": [{"parts": [{"text": "한국어로 '테스트 성공' 이라고만 답해줘"}]}]}
    models, seen = [], set()
    for m in [config.GEMINI_MODEL, "gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest"]:
        if m and m not in seen:
            seen.add(m)
            models.append(m)

    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        try:
            r = requests.post(url, params={"key": key}, json=payload, timeout=30)
        except Exception as e:
            print(f"[{model}] 네트워크 오류: {e}")
            continue

        print(f"[{model}] HTTP {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            cand = (data.get("candidates") or [{}])[0]
            txt = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []))
            print(f"\n✅ Gemini 정상 작동! 응답: {txt.strip()[:100]}")
            print("→ 봇에서도 위트있는 카드가 나올 거예요.")
            return
        elif r.status_code in (401, 403):
            print(f"   ❌ 키 인증 실패 — 키가 틀렸거나 권한이 없습니다.\n   {r.text[:300]}")
            print("\n→ https://aistudio.google.com/apikey 에서 키를 다시 발급받아 .env 에 넣어주세요.")
            return
        elif r.status_code == 400:
            print(f"   ⚠️ 요청 오류(400) — 키 형식/설정 확인 필요.\n   {r.text[:300]}")
        elif r.status_code == 404:
            print("   모델을 못 찾음 → 다음 모델로 재시도...")
        elif r.status_code == 429:
            print(f"   ⚠️ 사용량 초과(429) — 잠시 뒤 다시 시도하세요.\n   {r.text[:200]}")
            return
        else:
            print(f"   기타 오류:\n   {r.text[:300]}")

    print("\n❌ 사용 가능한 모델을 찾지 못했습니다. 위 오류 내용을 알려주세요.")


if __name__ == "__main__":
    main()
