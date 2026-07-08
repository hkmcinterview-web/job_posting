# 텔레그램 → 네이버카페 자동 게시 봇 (+ 카드뉴스 생성)

내 텔레그램 봇으로 메시지를 보내면:

1. 메시지에서 **제목 / 본문 / 뉴스링크**를 분리하고
2. 본문을 카페 글 형식으로 **자동 편집**하고
3. 각 뉴스링크를 **1~3장의 카드뉴스 이미지**로 만들어
4. 카드뉴스와 함께 **네이버카페에 글을 자동 게시**한 뒤
5. 게시글 URL 과 카드 미리보기를 텔레그램으로 회신합니다.

```
텔레그램 메시지
   │
   ├─ 제목/본문 분리 ──────────────► 카페 글 편집 (editor.py)
   └─ 뉴스링크 추출 ─► 기사 수집 ─► 요약(Claude/휴리스틱) ─► 카드뉴스 PNG
                                                          │
                              네이버카페 글 게시 ◄─────────┘
```

## 1. 설치

24시간 켜져 있는 서버/PC(라즈베리파이, 클라우드 VM 등)에서:

```bash
cd telegram_naver_bot
pip install -r requirements.txt
cp .env.example .env   # 열어서 값 채우기
```

## 2. 텔레그램 봇 준비

1. 텔레그램에서 **@BotFather** 검색 → `/newbot` 으로 봇 생성 → 토큰 복사
2. `.env` 의 `TELEGRAM_BOT_TOKEN` 에 입력
3. `python main.py` 실행 후 봇에게 아무 메시지나 보내면 콘솔에 `chat_id` 가 출력됩니다
   → 그 값을 `TELEGRAM_ALLOWED_CHAT_IDS` 에 입력 (다른 사람이 봇을 악용하지 못하게 필수!)

## 3. 네이버 API 준비 (카페 게시용)

> 네이버 아이디/비밀번호를 저장하지 않고 **공식 카페 API + OAuth** 를 사용합니다.
> 자동화 로그인(셀레늄 등)은 캡차·약관 문제로 권장하지 않습니다.

1. [developers.naver.com](https://developers.naver.com/apps/#/register) → 애플리케이션 등록
   - **사용 API**: "네이버 로그인" + "카페" 선택 (카페 API 는 권한 신청이 필요할 수 있음)
   - **Callback URL**: `https://localhost/callback` (또는 `.env` 의 `NAVER_REDIRECT_URI` 와 동일하게)
2. 발급받은 Client ID / Secret 을 `.env` 에 입력
3. **카페 ID(clubid)** 찾기: 카페 관리 페이지 URL 이나 카페 글 URL 의
   `cafe.naver.com/ca-fe/cafes/12345678/...` 형태에서 숫자,
   **게시판 ID(menuid)** 는 게시판 URL 의 `menuid=` 뒤 숫자입니다 → `.env` 에 입력
4. 최초 1회 로그인:

```bash
python naver_auth.py
```

출력된 URL 을 브라우저에서 열어 로그인/동의 → 이동된 주소를 붙여넣으면
`naver_tokens.json` 이 생성됩니다. 이후에는 봇이 토큰을 자동 갱신합니다.

> ⚠️ 글을 쓰려는 계정이 해당 카페의 **멤버이고 그 게시판에 쓰기 권한**이 있어야 합니다.

## 4. (선택) Claude API — 카드뉴스 품질 향상

`.env` 에 `ANTHROPIC_API_KEY` 를 넣으면 기사를 Claude 가 읽고
헤드라인 + 핵심 포인트 형태로 요약해 카드에 담습니다.
키가 없으면 기사 og 메타데이터/본문 문장 기반의 간단 요약으로 대체됩니다.

## 5. 실행

```bash
python main.py
```

상시 실행하려면 (Linux):

```bash
nohup python main.py >> bot.log 2>&1 &
```

## 6. 메시지 작성법

봇에게 이렇게 보내면 됩니다:

```
제목: 7월 첫째주 자동차산업 뉴스 브리핑
이번 주 주요 뉴스를 정리했습니다.
하반기 채용 일정도 곧 공유드릴게요.

https://n.news.naver.com/article/...
https://n.news.naver.com/article/...
```

- 첫 줄 `제목:` → 카페 글 제목 (없으면 첫 줄이 50자 이하일 때 제목으로 사용,
  둘 다 아니면 `[날짜] 뉴스 브리핑` 자동 생성)
- 링크는 본문 어디에 있어도 자동 추출되어 "관련 뉴스" 목록으로 정리됩니다
- 링크당 카드뉴스 1~3장 생성 (내용이 짧으면 자동으로 1~2장)

## 파일 구성

| 파일 | 역할 |
|---|---|
| `main.py` | 메인 루프 (텔레그램 수신 → 처리 → 게시) |
| `message_parser.py` | 제목/본문/링크 분리 규칙 |
| `editor.py` | 카페 글 편집 규칙 (머리말/꼬리말, 링크 목록) — **편집 규칙 수정은 여기** |
| `article.py` | 뉴스 기사 수집 (og 태그 + 본문) |
| `summarize.py` | 카드 내용 요약 (Claude API 또는 휴리스틱) |
| `card_news.py` | 카드뉴스 PNG 렌더링 (1080×1080) — **디자인 수정은 여기** |
| `naver_cafe.py` | 카페 글쓰기 API + 토큰 자동 갱신 |
| `naver_auth.py` | 최초 1회 네이버 OAuth 로그인 |

## 알아둘 점

- 한글 폰트(Noto Sans CJK KR, 약 16MB×2)는 최초 실행 시 `fonts/` 에 자동 다운로드됩니다.
- `naver_tokens.json`, `.env` 에는 민감 정보가 있으니 절대 커밋하지 마세요 (`.gitignore` 처리됨).
- 네이버 refresh_token 도 장기간 미사용 시 만료될 수 있습니다 — 게시 실패 시 `python naver_auth.py` 재실행.
