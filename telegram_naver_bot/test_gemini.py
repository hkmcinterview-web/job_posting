# -*- coding: utf-8 -*-
"""Gemini API 키(들)가 제대로 되는지 확인하는 도구.

.env 의 GEMINI_API_KEY 에 등록된 키를 전부(콤마 구분) 하나씩 점검합니다.
키 여러 개가 전부 429(사용량 초과)로 뜬다면, 서로 다른 계정으로 만든 게 맞는지
quotaId 를 비교해서 확인할 수 있습니다 — 여러 키의 quotaId 가 똑같다면
사실 같은 프로젝트(같은 할당량 통)를 공유하고 있다는 뜻입니다.

사용법:  python test_gemini.py
"""
import requests

import config


def _check_one_key(key: str, label: str) -> dict:
    """returns {'ok': bool, 'quota_id': str|None, 'model': str|None}"""
    print(f"\n{'='*50}")
    print(f"🔑 {label}: {key[:6]}...{key[-4:]} (길이 {len(key)})")
    payload = {"contents": [{"parts": [{"text": "한국어로 '테스트 성공' 이라고만 답해줘"}]}]}
    models, seen = [], set()
    for m in [config.GEMINI_MODEL, "gemini-3.5-flash", "gemini-flash-latest",
              "gemini-2.5-flash", "gemini-2.0-flash"]:
        if m and m not in seen:
            seen.add(m)
            models.append(m)

    last_quota_id = None
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
            return {"ok": True, "quota_id": None, "model": model}
        elif r.status_code in (401, 403):
            print(f"      ❌ 키 인증 실패 — 키가 틀렸거나 권한이 없습니다.")
            return {"ok": False, "quota_id": None, "model": None}
        elif r.status_code == 404:
            continue
        elif r.status_code == 429:
            try:
                err = r.json().get("error", {})
                for detail in err.get("details", []):
                    if detail.get("@type", "").endswith("QuotaFailure"):
                        for v in detail.get("violations", []):
                            qid = v.get("quotaId")
                            print(f"      → 제한 항목(quotaId): {qid}")
                            last_quota_id = qid
            except Exception:
                pass
        else:
            print(f"      기타 오류: {r.text[:200]}")

    print(f"   ❌ 이 키로는 사용 가능한 모델을 찾지 못했습니다.")
    return {"ok": False, "quota_id": last_quota_id, "model": None}


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
            print(f"  ❌ 키{i} — 실패 (quotaId: {res['quota_id']})")

    if ok_any:
        print("\n→ 최소 1개 키가 정상이니 봇에서 자동으로 그 키를 씁니다.")
        return

    quota_ids = [r["quota_id"] for r in results if r["quota_id"]]
    if len(quota_ids) >= 2 and len(set(quota_ids)) == 1:
        print("\n⚠️ 모든 키의 quotaId 가 동일합니다 — 서로 다른 계정으로 만든 것 같아도")
        print("   실제로는 같은 프로젝트(같은 할당량 통)를 공유하고 있을 가능성이 높습니다.")
        print("   해결: 브라우저에서 완전히 로그아웃하거나 시크릿창으로 다른 구글 계정에")
        print("   로그인한 뒤, https://aistudio.google.com/apikey 에서 'Create API key in")
        print("   NEW PROJECT' 를 선택해 키를 새로 만들어보세요.")
    elif len(quota_ids) >= 2:
        print("\n모든 키가 각자 다른 quotaId 로 막혀 있습니다 — 계정은 잘 분리된 것 같고,")
        print("   단순히 오늘 테스트가 많아서 전부 소진된 것으로 보입니다. 내일 다시 시도하거나")
        print("   구글 계정을 하나 더 추가해보세요.")
    else:
        print("\n키 인증 자체가 실패했을 수 있습니다 — 위 로그의 상세 오류를 확인해주세요.")


if __name__ == "__main__":
    main()
