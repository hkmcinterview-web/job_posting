# 🚄 코레일(KTX) 취소표 예약 도우미 — 개인용

원하는 구간·날짜·시간대의 KTX 열차에 **빈자리(취소표)** 가 뜨는지 여유 있는 간격으로
확인하고, 자리가 나면 **예약(좌석 확보)까지 자동으로 수행**한 뒤 **텔레그램 메시지와
휴대폰 푸시 알림**을 보냅니다. 결제는 알림을 받고 **직접** 하면 됩니다 — 코레일은
예약 후 약 10분 안에 결제하면 되는 구조이기 때문입니다.

> ⚠️ **꼭 읽어주세요 — 사용 범위와 책임**
> - 이 도구는 **본인 계정, 본인 1인 개인 사용**을 전제로 합니다.
> - 코레일 이용약관은 자동화(매크로) 예매를 제한합니다. 조회 간격을 **사람이 하는
>   수준(기본 40초 + 랜덤)** 으로 유지하세요. 간격을 무리하게 줄이면 매크로로 차단되고
>   확률도 오르지 않습니다. **탐지를 우회하려는 목적으로 쓰지 마세요.**
> - 여러 명에게 배포하는 용도로 만들어지지 않았습니다. 배포 시 약관·법적 문제가
>   생길 수 있으며, 그 책임은 사용자에게 있습니다.
> - 결제·발권을 자동으로 하지 않습니다. 최종 확정은 반드시 본인이 앱/웹에서 합니다.

---

## 1. 설치

Python 3.10+ 권장.

```bash
cd korail_booking

# (중요) korail2 는 오래된 패키지라 최신 setuptools 에서 빌드가 실패합니다.
# 아래처럼 setuptools 를 먼저 낮춘 뒤 설치하세요.
pip install "setuptools<66"
pip install -r requirements.txt
```

## 2. 설정

```bash
cp config.example.yaml config.yaml
```

`config.yaml` 을 열어 값을 채웁니다. **이 파일에는 로그인 정보가 들어가므로 절대
공유·커밋하지 마세요** (`.gitignore` 에 이미 등록돼 있습니다).

| 항목 | 설명 |
|------|------|
| `korail.login_id` | 코레일 회원번호(8자리) / 이메일 / 휴대폰번호 |
| `korail.password` | 코레일 비밀번호 |
| `trip.dep` / `trip.arr` | 출발/도착역 (한글 역명, 예: `서울`, `부산`) |
| `trip.date` | 승차 날짜 `YYYYMMDD` |
| `trip.time_from` / `time_to` | 출발 시각 범위 `HHMMSS` (`time_to` 비우면 종일) |
| `trip.train_types` | `KTX`, `KTX_SANCHEON`, `ITX_SAEMAEUL`, `SAEMAEUL`, `MUGUNGHWA`, `ALL` 등 |
| `trip.adults` / `children` | 어른/어린이 인원 |
| `trip.seat_option` | `GENERAL_FIRST`(일반실 우선) / `SPECIAL_FIRST`(특실 우선) 등 |
| `polling.interval_seconds` | 조회 간격(초). **40초 이상 권장** |
| `polling.jitter_seconds` | 매 조회마다 더해지는 랜덤 시간(사람처럼 불규칙하게) |

### 텔레그램 알림 설정

1. 텔레그램에서 **@BotFather** 와 대화 → `/newbot` → 봇 생성 → **봇 토큰** 받기
2. 만든 봇과 대화방을 열고 아무 메시지나 한 번 전송
3. 브라우저에서 `https://api.telegram.org/bot<봇토큰>/getUpdates` 접속 →
   `chat.id` 값 확인
4. `config.yaml` 의 `notify.telegram.bot_token`, `chat_id` 에 입력

### 휴대폰 푸시(알람) 설정 — ntfy

서버가 필요 없는 무료 푸시 서비스입니다.

1. 휴대폰에 **ntfy** 앱 설치 (App Store / Play스토어)
2. 앱에서 **추측하기 어려운 토픽명**을 하나 구독 (예: `korail-a8f3k2-myseat`)
3. `config.yaml` 의 `notify.ntfy.topic` 에 같은 토픽명 입력
4. `priority: 5` 로 두면 잠금화면 + 소리로 크게 알림이 옵니다

> 토픽명은 아는 사람만 접근 가능하도록 아무나 못 맞힐 문자열로 정하세요.

## 3. 실행

```bash
python booker.py                 # config.yaml 사용
python booker.py -c other.yaml   # 다른 설정 파일 지정
```

- 빈자리가 나서 **예약에 성공하면** 텔레그램/폰으로 알림이 오고 프로그램이 종료됩니다.
- 알림을 받으면 **약 10분 내에** 코레일 앱/웹 `마이페이지 > 승차권 확인` 에서 결제하세요.
- 중단하려면 `Ctrl + C`.

### 계속 켜두고 싶다면

- **PC/노트북**: 터미널에서 그냥 실행해 둡니다.
- **라즈베리파이/미니 서버**: `nohup python booker.py &` 또는 `systemd`/`tmux`.
- **무료 클라우드**: 항상 켜지는 소형 VM 등. (지속 실행 시에도 간격을 넉넉히 유지)

## 3-1. 휴대폰에서 실행하기

이 프로그램은 파이썬 스크립트라 **PC/서버에서 켜두고 알림만 폰으로 받는 방식**이 가장
편하고 안정적입니다(알림은 어차피 텔레그램/ntfy로 폰에 옵니다). 하지만 폰에서 직접
돌리고 싶다면:

### 안드로이드 — Termux (가능, 권장)

1. **F-Droid** 에서 **Termux** 설치 (Play스토어 버전은 오래돼서 비권장)
2. Termux 에서:
   ```bash
   pkg update && pkg upgrade -y
   pkg install python git -y
   pip install "setuptools<66"
   git clone <이_저장소_주소>
   cd job_posting/korail_booking
   pip install -r requirements.txt
   cp config.example.yaml config.yaml
   nano config.yaml        # 값 채우고 Ctrl+O 저장, Ctrl+X 종료
   python booker.py
   ```
3. 화면을 꺼도 계속 돌게 하려면:
   - 실행 전에 `termux-wake-lock` (CPU 잠들지 않게)
   - 안드로이드 **설정 > 배터리 > Termux 최적화 예외** 로 지정
   - 부팅 시 자동 실행이 필요하면 **Termux:Boot** 애드온 설치

### 아이폰 (iOS) — 비권장

a-Shell/Pyto 같은 앱으로 스크립트 실행 자체는 되지만, iOS는 앱이 백그라운드로
가거나 화면이 꺼지면 **프로세스를 강제로 멈춥니다.** 몇 시간씩 조회를 계속 돌려야
하는 이 용도에는 맞지 않습니다. 아이폰 사용자는 아래 "항상 켜두는 방법"을 쓰세요.

### 항상 켜두는 방법 (가장 추천 — 폰은 알림만 받기)

폰에서 계속 켜두는 건 배터리/절전 때문에 잘 끊깁니다. 아래 중 하나에 올려두고
**알림만 폰으로** 받는 걸 추천합니다.

- **집에 있는 PC / 라즈베리파이**: `tmux` 안에서 `python booker.py` 실행 후 창 닫기
- **무료 클라우드 VM**: 예) Oracle Cloud 항상 무료 티어, GCP 프리티어 소형 VM
- **PythonAnywhere / Replit** 같은 상시 실행 서비스

## 4. 자주 겪는 문제

| 증상 | 해결 |
|------|------|
| `korail2` 설치 실패 (`install_layout`) | `pip install "setuptools<66"` 먼저 실행 |
| 로그인 실패 | 회원번호/비밀번호 확인. 코레일 홈페이지 로그인이 되는지 먼저 확인 |
| 알림이 안 옴 | 텔레그램 `chat_id`, ntfy `topic` 오타 확인. `enabled: true` 인지 확인 |
| 자꾸 매진됨 | 인기 구간은 원래 경쟁이 큽니다. 간격을 줄이지 말고, 코레일 공식 **예약 대기** 기능도 함께 쓰세요 |

## 파일 구성

```
korail_booking/
├─ booker.py            # 메인 로직 (조회 → 예약 → 알림)
├─ notifier.py          # 텔레그램 + ntfy 알림
├─ config.example.yaml  # 설정 예시 (복사해서 config.yaml 로 사용)
├─ requirements.txt
└─ .gitignore           # config.yaml(비밀정보) 커밋 방지
```
