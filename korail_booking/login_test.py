# -*- coding: utf-8 -*-
"""로그인 진단 스크립트.

booker.py 의 로그인이 실패할 때, 원인이 (1) 회원번호/비밀번호 문제인지
(2) korail2 라이브러리가 오래돼 코레일 API가 바뀐 것인지 가려내기 위해
코레일 서버가 돌려주는 '실제 응답 메시지'를 그대로 보여줍니다.

    python login_test.py

비밀번호 자체는 화면에 찍지 않고 글자 수만 보여줍니다.
"""
from __future__ import annotations

import json
import sys

import yaml
from korail2 import Korail
from korail2.korail2 import KORAIL_LOGIN, EMAIL_REGEX, PHONE_NUMBER_REGEX

c = yaml.safe_load(open("config.yaml", encoding="utf-8"))
kid = str(c["korail"]["login_id"])
kpw = str(c["korail"]["password"])

print("불러온 login_id =", repr(kid))
print("비밀번호 글자수 =", len(kpw))

if EMAIL_REGEX.match(kid):
    flg, kind = "5", "이메일"
elif PHONE_NUMBER_REGEX.match(kid):
    flg, kind = "4", "휴대폰번호"
else:
    flg, kind = "2", "회원번호"
print("로그인 방식 판별 =", kind, f"(txtInputFlg={flg})")
print("-" * 40)

k = Korail(kid, kpw, auto_login=False)

try:
    enc = k._Korail__enc_password(kpw)  # noqa: SLF001 — 진단 목적
except Exception as e:  # noqa: BLE001
    print("[암호화 단계 실패]", type(e).__name__, e)
    print("→ 코레일 암호화 코드 요청 단계에서 실패. API 변경 가능성이 큽니다.")
    sys.exit(1)

data = {
    "Device": k._device,
    "Version": "231231001",
    "txtInputFlg": flg,
    "txtMemberNo": kid,
    "txtPwd": enc,
    "idx": k._idx,
}
r = k._session.post(KORAIL_LOGIN, data=data)

try:
    j = json.loads(r.text)
except Exception:  # noqa: BLE001
    print("[응답이 JSON 이 아님] HTTP", r.status_code)
    print(r.text[:500])
    sys.exit(1)

print("strResult =", j.get("strResult"))
print("h_msg_cd  =", j.get("h_msg_cd"))
print("h_msg_txt =", j.get("h_msg_txt"))
if j.get("strResult") == "SUCC":
    print("\n✅ 로그인 성공! 이제 booker.py 를 실행하면 됩니다.")
else:
    print("\n❌ 로그인 거절됨. 위 h_msg_txt 가 코레일이 알려준 실제 이유입니다.")
