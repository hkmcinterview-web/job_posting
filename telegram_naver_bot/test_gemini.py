# -*- coding: utf-8 -*-
"""Gemini API 키(들)가 제대로 되는지 확인하는 도구.

.env 의 GEMINI_API_KEY 에 등록된 키를 전부(콤마 구분) 하나씩, 여러 모델에 걸쳐 점검합니다.
※ quotaId(예: GenerateRequestsPerDayPerProjectPerModel-FreeTier)는 '할당량 종류의 이름'일
뿐이라 계정이 다르든 같든 항상 똑같이 나옵니다 — 이것만으로는 키가 같은 프로젝트를
공유하는지 구분할 수 없습니다. 이 도구는 대신 어떤 모델이 막혔는지, 어떤 모델은 아직
시도조차 안 됐는지(할당량이 남아있을 가능성)를 보여주는 데 씁니다.

사용법:  python test_gemini.py
"""
import requests

import config


def _check_one_key(key: str, label: str) -> dict:
    """모델을 하나씩 순서대로 시도 (성공하면 즉시 멈춤).
    returns {'ok': bool, 'model': str|None, 'blocked_models': [str,...]}"""
    print(f"\n{'='*50}")
    print(f"🔑 {label}: {key[:6]}...{key[-4:]} (길이 {len(key)})")
    payload = {"contents": [{"parts": [{"text": "한국어로 '테스트 성공' 이라고만 답해줘"}]}]}
    models, seen = [], set()
    for m in [config.GEMINI_MODEL, "gemini-3.5-flash", "gemini-flash-latest",
              "gemini-2.0-flash", "gemini-2.0-flash-lite",
              "gemini-1.5-flash", "gemini-1.5-flash-8b"]:
        if m and m not in seen:
            seen.add(m)
            models.append(m)

    blocked = []
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        try:
            r = requests.post(url, params={"key": key}, json=payload, timeout=30)
        except Exception as e:
            print(f"   [{model}] 네트워크 오류: {e}")
            continue

        print(f"   [{model}] HTTP {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            cand = (data.get("candidates") or [{}])[0]
            txt = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []))
            print(f"   ✅ 정상 작동! 응답: {txt.strip()[:80]}")
            return {"ok": True, "model": model, "blocked_models": blocked}
        elif r.status_code in (401, 403):
            print(f"      ❌ 키 인증 실패 — 키가 틀렸거나 권한이 없습니다.")
            return {"ok": False, "model": None, "blocked_models": blocked}
        elif r.status_code == 404:
            continue   # 이 모델 자체가 이 계정/API 에 없음 — 할당량과 무관
        elif r.status_code == 429:
            blocked.append(model)
            try:
                err = r.json().get("error", {})
                for detail in err.get("details", []):
                    if detail.get("@type", "").endswith("QuotaFailure"):
                        for v in detail.get("violations", []):
                            print(f"      → 제한 항목: {v.get('quotaId')}")
            except Exception:
                pass
        elif r.status_code == 503:
            print("      (일시적 서버 과부하 — 할당량과 무관, 잠시 후엔 될 수도 있음)")
        else:
            print(f"      기타 오류: {r.text[:200]}")

    print(f"   ❌ 이 키로는 사용 가능한 모델을 찾지 못했습니다.")
    return {"ok": False, "model": None, "blocked_models": blocked}


def main():
    keys = config.GEMINI_API_KEYS
    if not keys:
        print("❌ .env 의 GEMINI_API_KEY 가 비어 있습니다. 키를 넣어주세요.")
        return
    print(f"📦 설정 모델: {config.GEMINI_MODEL}")
    print(f"🔑 등록된 키 개수: {len(keys)}개")

    results = []
    for i, key in enumerate(keys, 1):
        results.append(_check_one_key(key, f"키{i}"))

    print(f"\n{'='*50}")
    print("===== 결과 요약 =====")
    ok_any = False
    for i, res in enumerate(results, 1):
        if res["ok"]:
            print(f"  ✅ 키{i} — 정상 (모델: {res['model']})")
            ok_any = True
        else:
            blocked = ", ".join(res["blocked_models"]) or "(없음)"
            print(f"  ❌ 키{i} — 실패 (할당량 초과 모델: {blocked})")

    if ok_any:
        print("\n→ 최소 1개 키가 정상이니 봇에서 자동으로 그 키를 씁니다.")
    else:
        print("\n등록된 키 전부, 이 목록의 모델을 전부 오늘 하루 다 써버린 상태입니다.")
        print("(참고: quotaId 는 계정과 무관하게 항상 같은 이름으로 나오는 '할당량 종류' 표시라,")
        print(" 이것만으로는 키들이 같은 프로젝트를 공유하는지는 알 수 없습니다.)")
        print("→ 내일(할당량은 매일 리셋) 다시 시도하거나, 구글 계정을 하나 더 추가하거나,")
        print("  Claude 를 유료 폴백으로 추가(.env 의 ANTHROPIC_API_KEY)하는 방법이 있습니다.")


if __name__ == "__main__":
    main()
