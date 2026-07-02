# korail_booking — 개발 인수인계 문서 (HANDOFF)

다른 개발자/LLM이 이 작업을 이어받을 수 있도록 지금까지의 목표·구조·진행상황·
막힌 지점을 정리한 문서입니다.

---

## 1. 원래 목표 (사용자 요청)

- 모바일에서 코레일(KTX) 취소표를 **매크로로 자동 예매**하고 싶다.
- PC 웹에서 5~10초마다 새로고침했더니 매크로로 인식돼 확률이 낮아졌다.
- 예매되면 **텔레그램 메시지 / 휴대폰 알람**으로 알림.
- 추후 **제한된 사람에게 배포**까지 고려.

## 2. 조정된 범위 (실제로 만든 것)

전체 자동화 대신, 아래로 범위를 좁혀 구현했다.

- **본인 계정, 개인 1인 사용** 전제.
- 원하는 구간/날짜/시간대의 빈자리(취소표)를 **여유 있는 간격**으로 조회 →
  자리 나면 **예약(좌석 확보)까지 자동** → **결제는 사용자가 직접**(코레일은 예약 후
  약 10분 내 결제 구조).
- 알림은 **텔레그램 + ntfy(폰 푸시/알람)**.
- **의도적으로 제외한 것**: 매크로 탐지 우회, 초단위 폴링, 다중 배포.
  (이유: 코레일 이용약관 위반, 계정 정지·법적 리스크, 다른 승객의 공정한 접근 침해.)

## 3. 저장소 / 브랜치

- repo: `hkmcinterview-web/job_posting` (원래는 무관한 Streamlit 채용공고 앱)
- 작업 브랜치: `claude/korail-booking-macro-o1vfyr`
- 코드 위치: `korail_booking/` 폴더 (기존 앱과 분리)

## 4. 파일 구성

```
korail_booking/
├─ booker.py            # 메인 로직: 조회 → 예약 → 알림 루프
├─ notifier.py          # 텔레그램 + ntfy 알림 (실패해도 루프 안 멈춤)
├─ login_test.py        # 로그인 실패 원인 진단 (코레일 raw 응답 출력)
├─ config.example.yaml  # 설정 예시 (복사해서 config.yaml 로 사용)
├─ config.yaml          # 실제 설정 (gitignore, 로그인정보 포함, 커밋 금지)
├─ requirements.txt     # korail2>=0.3.0, PyYAML>=6.0, requests>=2.31
├─ .gitignore
└─ README.md            # 설치/설정/실행/휴대폰(Termux) 안내
```

## 5. 기술 스택 / 라이브러리

- Python 3.10+ (테스트 환경은 Android Termux, Python 3.13).
- **korail2 0.4.0** — 코레일 비공식 파이썬 클라이언트.
  - 설치 시 최신 setuptools에서 빌드 실패(`install_layout` AttributeError).
    → **`pip install "setuptools<66"` 를 먼저** 실행하면 정상 빌드됨. (검증 완료)
  - 의존성: requests, PyCryptodome(AES), six 등.
- 알림: requests 로 Telegram Bot API / ntfy HTTP POST.

### 검증한 korail2 0.4.0 API 시그니처
- `Korail(korail_id, korail_pw, auto_login=True, want_feedback=False)`
- `Korail.login() -> bool`
- `search_train_allday(dep, arr, date=None, time=None, train_type=TrainType.ALL, passengers=None, include_no_seats=False)`
- `reserve(train, passengers=None, option=ReserveOption.GENERAL_FIRST, try_waiting=False)`
- Train 속성: `train_type_name, train_no, dep_name, arr_name, dep_time, arr_time`,
  메서드 `has_seat() / has_general_seat() / has_special_seat()`
- Enum: `TrainType.{KTX, KTX_SANCHEON, ITX_SAEMAEUL, SAEMAEUL, MUGUNGHWA, ALL, ...}`,
  `ReserveOption.{GENERAL_FIRST, GENERAL_ONLY, SPECIAL_FIRST, SPECIAL_ONLY}`
- 예외: `SoldOutError, NoResultsError, NeedToLoginError, KorailError`
- 로그인 엔드포인트: `smart.letskorail.com` (모바일 API), 로그인 시 `txtInputFlg`
  (2=회원번호 / 4=휴대폰 / 5=이메일), 비번은 서버가 준 키로 AES-CBC 암호화.

## 6. 설정(config.yaml) 스키마

```yaml
korail:   {login_id, password}
trip:     {dep, arr, date(YYYYMMDD), time_from(HHMMSS), time_to, train_types[], adults, children, seat_option}
polling:  {interval_seconds(기본30), jitter_seconds(기본15), stop_after_reserve(true), max_minutes(0=무제한)}
notify:
  telegram: {enabled, bot_token, chat_id}
  ntfy:     {enabled, server(https://ntfy.sh), topic, priority(5=최고)}
```
- 폰에서 nano로 여러 줄 붙여넣기 시 들여쓰기가 자주 깨짐. → **한 줄 `printf ... > config.yaml`**
  로 파일을 만들고, 값만 따옴표 안에서 수정하는 방식이 안정적이었음.
- 비밀번호에 `\` `"` 가 있으면 YAML 큰따옴표에서 깨질 수 있음 → 작은따옴표 권장.

## 7. 실행 환경 (Android / Termux)

1. F-Droid 에서 Termux 설치(Play스토어 버전 X). (부팅 자동실행 원하면 Termux:Boot)
2. `pkg install python git -y`
3. `pip install "setuptools<66"`
4. `git clone <repo>` (비공개면 GitHub PAT `repo` 스코프 필요) 또는 ZIP 다운로드
5. `cd job_posting/korail_booking` (작업 브랜치 checkout 필요) → `pip install -r requirements.txt`
6. `config.yaml` 작성 → `python booker.py`
7. 상시 실행: `termux-wake-lock` + 배터리 최적화 예외 + 충전기 연결.
   (더 안정적인 건 PC/라즈베리파이/무료 클라우드 VM 에 올리고 알림만 폰으로 받기.)

## 8. 알림 세팅 (동작 확인됨)

- **ntfy**: 폰에 ntfy 앱 설치 → 추측 어려운 topic 구독 → config `topic` 에 동일 입력.
  priority 5면 잠금화면/소리 알림. (사용자 폰에서 수신 확인 완료.)
- **텔레그램**: @BotFather 로 봇 생성 → 토큰, getUpdates 로 chat_id 확인.
  (이번엔 disabled 로 두고 ntfy만 사용.)

## 9. ⛔ 현재 막힌 지점 (핵심)

`login_test.py` 실행 결과, 코레일 서버가 로그인 단계에서 다음을 반환:

```
strResult = FAIL
h_msg_cd  = MACRO ERROR
h_msg_txt = 원활한 서비스 이용을 위해 앱을 최신 버전으로 업데이트한 뒤
            재실행 후 안정적인 환경에서 사용해 주시기 바랍니다.
```

- **원인**: 자격증명(회원번호/비번) 문제가 **아님**. 코레일 서버측 **매크로/자동화
  탐지**가 korail2 클라이언트를 봇으로 판정해 로그인 자체를 거부.
- korail2 는 이미 앱 버전을 최신인 척(`Version: 231231001`) 위장하지만 그래도 걸림.
  → 코레일이 버전 문자열이 아니라 **기기 무결성 / 요청 서명 / 앱 정품 인증** 등
  더 깊은 신호로 탐지 중임을 의미.
- 즉, **korail2 기반 자동 로그인·자동 예매는 현재 코레일에서 원천 차단된 상태.**

## 10. 이 문서의 범위/입장

- 이 프로젝트에서는 코레일의 `MACRO ERROR` 탐지를 **우회하는 방향은 다루지 않는다.**
  (약관·법적 리스크, 계정 정지 위험, 공정 접근 침해.)
- 자동화가 막힌 상황에서 취소표를 잡는 **정식 대안**:
  - **코레일 공식 "예약 대기"**: 매진 열차에 예약대기 신청 → 취소 발생 시 코레일이
    자동으로 좌석 배정. 매크로보다 안정적이고 차단 위험 없음.
  - 코레일톡 앱 알림 활용, SRT 등 대체편 병행.

## 11. 코드 자체의 남은 개선거리 (참고, 로그인 차단과 별개)

- 예약 성공 후 결제 마감시간 카운트다운 알림.
- 여러 구간/날짜를 하나의 설정으로 동시 감시.
- SRT(`SRT` 라이브러리) 지원 추가 — 구조는 booker.py 와 동일 패턴.
- 로그인 실패 유형별(자격증명 vs MACRO vs API변경) 분기 메시지.
