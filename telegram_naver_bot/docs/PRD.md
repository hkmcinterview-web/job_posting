# 텔레그램 콘텐츠 봇 — 제품/설계 문서 (PRD + 재사용 가이드)

> **이 문서의 목적**: 지금까지 "취업(공대생 취준생)" 테마로 만든 이 봇의 구조·기능·기술패턴을
> 한곳에 정리해서, **다른 사업 테마(예: 재테크/투자)로 그대로 복제**할 수 있게 한다.
> Claude(또는 개발자)가 이 문서만 읽고도 새 테마 버전을 빠르게 만들 수 있도록,
> **"도메인 무관 엔진"과 "테마별로 바꾸는 부분"을 명확히 분리**해 기술한다.

---

## 1. 제품 한 줄 정의

**텔레그램으로 링크/텍스트/이미지를 던지면, AI가 인스타 카드뉴스·정보카드를 만들고
네이버 카페에 자동 게시해주는, 1인 콘텐츠 채널 운영 자동화 봇.**

핵심 가치 루프:
```
소재 발굴(뉴스/커뮤니티/트렌드) → 카드 생성(멀티 모델 중 택1) → 검수/확인 → 카페·SNS 배포
```

현재 테마: 취업("공대생현직자 잡앤유"). 대상 = 이공계 취준생.
→ **테마만 바꾸면** 재테크·부동산·건강 등 어떤 "정보 큐레이션 채널"에도 그대로 쓸 수 있다.

---

## 2. 아키텍처 개요

```
                 ┌──────────────── Telegram (long-polling) ─────────────────┐
                 │  getUpdates 루프 (main.py)                                 │
                 │   - 텍스트 메시지 / 사진(photo) / 파일(document) 수신        │
                 │   - media_group(앨범) 묶기, 캡션 파싱                        │
                 └───────────────┬───────────────────────┬──────────────────┘
                                 │ 텍스트                  │ 사진/파일(캡션)
                                 ▼                        ▼
                 ┌──────────── detect_mode() ────────────┐   (message_parser.py)
                 │  맨 앞 키워드로 명령 분기               │   '카드','채용','커뮤니티',...
                 └───────────────┬───────────────────────┘
                                 ▼
                 ┌──────── 워커 스레드 + 취소 (_start_work) ────────┐
                 │  무거운 작업(AI/렌더/게시)을 백그라운드로 실행     │
                 │  '취소' 언제든 즉시 중단 (_CancelTG)              │
                 └──────┬───────────────┬───────────────┬──────────┘
                        ▼               ▼               ▼
                  카드 생성         공고/정보카드      카페 게시
                  (summarize.py    (job_summary.py    (naver_cafe.py
                   + card_news.py)   + job_card.py)     + editor.py)
                        │               │
                        └──── AI 제공자 계층 (summarize.py) ────┐
                              Gemini → Groq → OpenRouter → Ollama → 휴리스틱
                              (텍스트 생성 / 비전 OCR / 멀티모델 비교)
```

**설계 원칙**
- **키워드-우선 라우팅**: 모든 기능은 메시지 맨 앞 한 단어로 진입. 새 기능 = 키워드 1개 추가.
- **워커 스레드 + 취소**: 폴링 루프는 절대 막히지 않게, 무거운 작업은 스레드로. '취소'는 항상 즉시 반응.
- **상태머신으로 다단계 대화**: 선택/확인/이미지 대기 등은 chat_id별 상태 딕셔너리로.
- **AI는 다중 폴백**: 한 모델이 막혀도(429/404) 자동으로 다음 모델. 무료 우선.
- **네트워크는 다 불안정하다고 가정**: 재시도·타임아웃·"실패 시 복붙 텍스트 반환" 폴백.

---

## 3. ⭐ 도메인 무관 엔진 vs 테마별 커스터마이즈 (가장 중요)

새 테마를 만들 때 **아래 "엔진"은 그대로 두고 "테마" 부분만 바꾸면 된다.**

### 3-1. 그대로 재사용하는 엔진 (거의 안 바뀜)
| 영역 | 파일 | 재사용 포인트 |
|------|------|--------------|
| 텔레그램 폴링·라우팅·워커·취소 | `main.py`, `telegram_client.py`, `message_parser.py` | 구조 그대로. 키워드 목록만 추가/변경 |
| AI 제공자 계층·폴백·비전 OCR·멀티모델 비교 | `summarize.py` | `_gemini/_groq/_openrouter/_ollama_generate`, `_compare_models`, `ocr_comments`, `_has_language_drift` 전부 도메인 무관 |
| 카드뉴스 캐러셀 렌더링 | `card_news.py` | 뉴스/커뮤니티 카드 렌더는 도메인 무관 (문구만 프롬프트가 정함) |
| 네이버 카페 게시 (OAuth·인코딩·999 처리) | `naver_cafe.py`, `naver_auth.py`, `editor.py` | 카페 API·한글 인코딩·스팸필터 대응 그대로 |
| 기사/이미지 수집·단축주소 | `article.py`, `linkutil.py` | 그대로 |
| 뉴스/트렌드/발굴 데이터 소스 | `trends.py` | Naver검색/랭킹/구글뉴스/Reddit/NewsAPI 호출부 그대로 |
| 로고 등록, 멀티모델 N-M 선택, 재시도, 확인 흐름 | `main.py` | 상태머신 패턴 그대로 |

### 3-2. 테마별로 바꾸는 부분 (여기만 손대면 됨)
| 바꿀 것 | 위치 | 취업 테마 → 재테크 예시 |
|---------|------|------------------------|
| 브랜드명 | `.env` `BRAND_NAME` | "공대생현직자 잡앤유" → "재테크 채널명" |
| 대상/톤 프롬프트 | `summarize.py` `_build_prompt`, `_build_community_prompt` | "이공계 취준생" → "재테크 초보/투자자" |
| **정보카드 도메인** (핵심) | `job_summary.py` `_build_prompt`+`_parse_job`, `job_card.py` | "채용공고 → 직무/자격/우대" → "종목/정책/상품 → 요약/조건/리스크" |
| **발굴 키워드** (관련성×공유성) | `trends.py` `_RELEVANCE_TERMS`, `_SHARE_TERMS`, `_SEED_QUERIES` | "현대차·반도체·채용·초봉" → "삼성전자·금리·배당·절세·연금·부동산" |
| 명령 키워드(원하면) | `message_parser.py` `*_WORDS` | "채용" → "종목"/"정책" 등 원하는 단어 |
| 카페 게시판 ID | `.env` `NAVER_CAFE_*_MENU_ID` | 재테크 카페/게시판 숫자 ID |

> 요약: **`summarize.py`의 프롬프트 문구 + `job_summary.py`/`job_card.py`의 "정보카드" 정의 +
> `trends.py`의 발굴 키워드**, 이 3곳이 테마의 90%다. 나머지는 엔진.

---

## 4. 기능/명령어 카탈로그

메시지 맨 앞 키워드로 진입 (`message_parser.detect_mode`).

| 명령어 | 기능 | 핵심 흐름 | 주요 파일 |
|--------|------|-----------|-----------|
| `카페` | 큐레이션 텍스트/뉴스를 카페에 게시 | 제목/본문 분리 → 단축주소 펼침 → HTML 인코딩 → 게시 (999면 복붙본 반환) | `editor.py`, `naver_cafe.py` |
| `카드` | 뉴스 링크 → 인스타 카드뉴스(캐러셀) | 기사수집 → **여러 모델이 헤드라인 후보** → `N-M` 선택 → 4장 렌더 | `article.py`, `summarize.py`, `card_news.py` |
| `채용` | 채용공고 → 정보카드 + 카페 게시 | **인식 보고 → 부족하면 이미지 요청 → 미리보기 → '네' 확인 → 게시** | `job_summary.py`, `job_card.py` |
| `커뮤니티` | 커뮤니티 글 → 카드(본문+댓글반응+포인트) | 본문/댓글 입력(복붙/스샷 OCR) → 배경 이미지 → `N-M` → 4장 | `summarize.py`, `card_news.py` |
| `카드이미지` | 뉴스 카드인데 **배경만 내 이미지** | 사진 캡션에 `카드이미지 [링크]` → 링크로 내용, 첨부로 배경 | `card_news.py` |
| `펼치기` | 단축주소(buly.kr 등)를 원본으로 펼쳐 반환 | 링크 확장만 | `linkutil.py` |
| `뉴스` | 키워드로 최근 화제 기사 검색(공식 API) | Naver 뉴스검색 → 언론사 보도수로 화제성 정렬 | `trends.py` |
| `발굴` | **대상 관심 뉴스를 점수화 추천** (키워드 불필요) | 씨앗 검색어 훑기 → 관련성×공유성+보도수+최신성 점수 | `trends.py` |
| `트렌드` | 구글 트렌드 실시간 검색어 | 비공식 RSS | `trends.py` |
| `국내이슈`/`해외이슈` | 네이버랭킹 / 구글뉴스 World | 키워드 없이 지금 화제 | `trends.py` |
| `헤드라인` | NewsAPI 국가/카테고리별 톱뉴스 | 키 필요, 무료 24h 지연 | `trends.py` |
| `비교` | 링크 하나로 모델별 헤드라인만 비교 | 카드 안 만들고 품질 비교용 | `summarize.py` |
| `로고`/`로고삭제` | 채용 카드 우상단 로고 등록/삭제 | 채팅별 저장 | `main.py` |
| `취소` | 진행 중 작업 즉시 중단 | 워커 취소 + 상태 초기화 | `main.py` |
| `재시도` | (카드 선택 중) 헤드라인 다시 뽑기 | 같은 소재로 재생성 | `main.py` |
| `완료`/`네`/`아니오` | (채용 확인 단계) 게시/취소 | | `main.py` |

---

## 5. 모듈 지도 (파일별 역할)

| 파일 | 역할 | 도메인 결합도 |
|------|------|--------------|
| `main.py` | 폴링 루프, 라우팅, 모든 핸들러, 상태머신, 워커/취소, HELP_TEXT | 중 (핸들러가 테마 로직 호출) |
| `message_parser.py` | `detect_mode()` 키워드→모드, `extract_links`, `split_title_body` | 낮음 (키워드 목록만) |
| `config.py` | `.env` 로드, 모든 설정값 | 낮음 |
| `summarize.py` | **AI 계층**: 제공자 호출·폴백, 카드 프롬프트, 멀티모델 비교, OCR, 언어이탈 감지 | 프롬프트 문구만 테마 |
| `card_news.py` | 카드뉴스 캐러셀 렌더(PIL): 헤드라인/요약/배경/댓글 슬라이드 | 낮음 (렌더 엔진) |
| `job_summary.py` | 공고 텍스트/이미지 → 구조화(`build_job_data`) | **높음 (테마 핵심)** |
| `job_card.py` | 정보카드(채용카드) PNG 렌더 | 중 (레이아웃은 재사용, 라벨은 테마) |
| `editor.py` | 카페 게시용 HTML 본문 생성(`build_cafe_post`, `build_job_post`) | 중 |
| `naver_cafe.py` | 네이버 카페 API: OAuth 토큰 갱신, 한글 HTML엔티티 인코딩, 999 에러 파싱, 레이트리밋 | 낮음 |
| `naver_auth.py` | 네이버 OAuth 최초 로그인 도우미 (1회) | 낮음 |
| `article.py` | 기사 본문/대표사진/출처 추출, `fetch_job_page`, `fetch_image_bytes` | 낮음 |
| `linkutil.py` | 단축주소 원본 확장 | 낮음 |
| `trends.py` | 뉴스/트렌드/발굴 데이터 소스 + **발굴 점수화** | 발굴 키워드만 테마 |
| `telegram_client.py` | 텔레그램 API 얇은 래퍼 (getUpdates/sendMessage/sendPhoto/download) | 낮음 |
| `cta_card.py` | CTA 슬라이드 렌더 보조 | 낮음 |
| `test_*.py` | 카페/네이버/Gemini 점검 스크립트 | 낮음 |

---

## 6. 핵심 기술 패턴 & 하드윈 교훈 (재현 시 반드시 지킬 것)

1. **키워드-우선 라우팅** — `detect_mode`는 맨 앞 토큰만 보고 모드 반환. 사진은 **캡션**으로 라우팅(예: `채용`, `로고`, `댓글`, `카드이미지`). 캡션 없는 사진은 "진행 중 상태"로 라우팅.

2. **워커 스레드 + 취소 신호** — `_start_work(target)`가 스레드로 실행, `_CancelTG` 래퍼가 매 전송 직전 취소 여부 확인. `_work_busy()`로 동시 실행 방지. '취소'는 폴링에서 항상 최우선 처리.

3. **상태머신으로 다단계 대화** (chat_id별 dict):
   - `PENDING_CARD` — 멀티모델 헤드라인 `N-M` 선택 대기 (news/community/news_img 공용, `kind`로 분기).
   - `JOB_FLOW` — 채용 대화형: `init→await_content→await_logo→await_confirm`.
   - `PENDING_COMMUNITY` — 커뮤니티: 본문/댓글 받고 배경 이미지 대기.

4. **AI 멀티모델 "비교" 패턴** — 같은 프롬프트를 여러 무료 모델에 **병렬** 호출(`_compare_models`), 각 모델 결과를 `N-M`(모델-헤드라인)으로 보여주고 사용자가 택1. 고른 모델의 요약/캡션 전체로 카드 완성. 실패 모델은 **사유와 함께 제외** 표시.

5. **AI 단일출력 폴백 체인** (`generate_text`): Gemini(무료) → Claude(유료) → Ollama(로컬) → 휴리스틱. `_gemini_generate`는 키 여러 개 × 모델 여러 개 순회(429/404/503 시 다음).

6. **언어 이탈 감지** (`_has_language_drift`) — 무료 모델이 중국어/일본어로 새면 결과 버리고 다음 모델. 한글 카드에 가나/과도한 한자 감지.

7. **마커 구분 출력 포맷** — JSON 대신 `<<<SUMMARY>>>...<<<END>>>`, `<<<CARD>>>`, 인라인 `{{강조}}`. 따옴표/문장부호로 파싱 깨지는 문제 원천 차단. 프롬프트가 이 포맷을 강제하고 정규식으로 추출.

8. **비전 OCR 폴백** (`ocr_comments`) — 댓글/공고 스크린샷을 Gemini → Groq비전 → OpenRouter비전 순으로 읽음. OpenAI 호환 `image_url` 포맷 + Gemini `inline_data`.

9. **네이버 카페 게시의 함정들** (naver_cafe.py):
   - 한글이 깨져서 → **HTML 숫자 엔티티(`&#44032;`)로 변환**해 ASCII만 전송 (구형 MS949 스킨 대응).
   - 이미지 없는 게시는 **직접 조립한 raw bytes**로 전송(딕셔너리로 주면 %가 이중 인코딩됨).
   - **999 = 스팸 필터** (토큰/권한 아님). 링크 많음·도배·계정 신뢰도. 재시도로 못 뚫음 → **복붙용 [제목]/[본문]을 사용자에게 반환**해 카페 웹에 직접 올리게.
   - 레이트리밋: 마지막 게시 후 최소 65초. 실패한 시도도 도배로 카운트됨.

10. **텔레그램 이미지 품질/타입** — '사진(photo)'은 **압축**, '파일(document, image/*)'은 **원본**. 카페에 고화질 첨부하려면 사용자에게 **파일로 보내라고 안내**. `media_group_id`로 앨범 묶기.

11. **이미지 배경 채우기** — 카드 배경은 프레임(1080×1350, 4:5)에 **cover(꽉 채움)**가 기본. contain+블러는 일반 사진엔 안 좋음(실험 후 롤백). 로고처럼 잘리면 안 되는 건 사용자 제공 이미지(`카드이미지`)로 해결.

12. **네트워크 방어** — 기사 수집은 (연결10s/읽기30s)+1회 재시도. 대형 유료매체(WaPo/NYT)·구글뉴스 리다이렉트는 실패 안내. **이 개발환경은 외부망이 막혀 있어 실제 응답은 사용자 PC에서 검증**해야 함(모든 네이버/구글 코드 공통).

13. **발굴 점수화** — "지금 뭘 올릴까"를 키워드 편견 대신 신호 합산으로: `보도 언론사 수(화제성) + 관련성 키워드 + 공유성 키워드 + 교집합 보너스 + 최신성`. **관련성 0이면 하드 제외**(off-topic 노이즈 차단). 장기적으로 인스타 인사이트(저장/공유수)로 가중치 학습 예정(2단계).

14. **재현성** — 공고 추출은 `temperature=0.0`(같은 입력=같은 결과). 카드 헤드라인은 다양성 위해 높게.

---

## 7. AI 제공자 계층 (summarize.py)

```
텍스트 생성:  generate_text() → Gemini → Claude → Ollama → "none"
카드 후보:    compare_card_options()/compare_community_options()
                → _compare_models(prompt, extras_fn): Gemini + Groq×N + OpenRouter×N 병렬
비전 OCR:     ocr_comments() → Gemini → Groq비전 → OpenRouter비전
```
- **Gemini**: 무료 등급. 키 여러 개(콤마) × 모델 여러 개 순회. 비전 지원.
- **Groq**: 무료 한도 넉넉·빠름·429 적음. OpenAI 호환. 비전 모델 별도(`GROQ_VISION_MODEL`).
- **OpenRouter**: 무료 모델 **자동 탐색**(`list_openrouter_free_models`, 가격 0 필터). ID 수시 변동 대응.
- **Ollama**: 완전 무료·오프라인·느림(CPU). 텍스트 전용.
- **Claude**: 유료. 폴백용.

프롬프트 출력 포맷(카드): `<<<SUMMARY>>> <<<CONTEXT>>> <<<OUTLOOK>>> <<<CAPTION>>> <<<CARD>>>(TAG/HIGHLIGHT/STYLE/HEADLINE) × N`.
커뮤니티: `<<<SUMMARY>>> <<<COMMENTS>>> <<<TAKEAWAY>>> <<<CAPTION>>> <<<CARD>>> × N`.

---

## 8. 데이터 모델 (핵심 딕셔너리)

```python
# 정보카드(현재=채용) — job_summary._parse_job
job = {"company","title","deadline","badges":[], "table_head":[], "table_rows":[[...]],
       "points":[...], "infos":[(k,v)], "brand_color"}
# 인식 충분 판정: title 있고 (table_rows 또는 points) 있으면 OK  (_job_has_substance)

# 카드뉴스 후보 — summarize._extract_cards
card = {"headline":"여러 줄\n가능", "tag":"이슈", "highlight":"강조할 한 줄", "style":"marker|color"}
# 캐러셀 재료(extras) — 뉴스: {summary, context, outlook[], caption}
#                       커뮤니티: {summary, comments, takeaway[], caption}

# 멀티모델 비교 결과
result = {"provider":"Gemini", "options":[card,...], "extras":{...}, "error":""}

# 상태머신
PENDING_CARD[chat_id] = {queue[], link_idx, made, stamp, article, choices[result], extras,
                         kind:"community|news_img|None", bg_image, source, post, comments}
JOB_FLOW[chat_id]     = {stage, page, images[(mime,b64)], photo_paths[], link, job, summary,
                         logo, card_path}
```

---

## 9. 환경변수 (.env)

```
TELEGRAM_BOT_TOKEN / TELEGRAM_ALLOWED_CHAT_IDS
NAVER_CLIENT_ID / NAVER_CLIENT_SECRET / NAVER_REDIRECT_URI
NAVER_CAFE_CLUB_ID / NAVER_CAFE_MENU_ID / NAVER_CAFE_JOB_MENU_ID   # 게시판 분리
NAVER_SEARCH_CLIENT_ID/SECRET      # '뉴스' 검색 (앱에 '검색' API 필요, 없으면 위 키 사용)
NEWSAPI_KEY                        # '헤드라인'
GEMINI_API_KEY(콤마로 여러개) / GEMINI_MODEL
ANTHROPIC_API_KEY / ANTHROPIC_MODEL
GROQ_API_KEY / GROQ_MODELS / GROQ_VISION_MODEL
OPENROUTER_API_KEY / OPENROUTER_MODELS(비우면 자동탐색) / OPENROUTER_VISION_MODEL
OLLAMA_MODEL / OLLAMA_HOST
BRAND_NAME / POST_HEADER / POST_FOOTER(비워두기 권장)
CAFE_LINKS_AS_ANCHOR / CAFE_EXPAND_SHORT_LINKS / MAX_LINKS / MAX_CARDS_PER_LINK
```

---

## 10. ⭐ 새 테마 적용 가이드 — 취업 → 재테크 (구체 매핑)

새 저장소로 복제 후 아래만 바꾸면 재테크 버전이 된다.

### 10-1. 브랜드/톤
- `.env` `BRAND_NAME` = 재테크 채널명.
- `summarize.py` 프롬프트의 대상 문구 일괄 치환: "공대생/이공계 취준생" → "재테크 초보·개인투자자". "취준생 관점" → "투자자 관점".

### 10-2. 정보카드(채용카드 → 재테크 정보카드)
`채용`의 대응물을 정한다. 예: **`종목`(종목 요약카드)**, **`정책`(부동산/세제 정책카드)**, **`상품`(예적금/연금 상품카드)**.
- `job_summary.py` `_build_prompt`: "채용공고에서 회사·직무·자격·우대·마감을 추출" → "종목/상품/정책에서 **핵심요약·조건·수익/리스크·체크포인트·일정**을 추출".
- `_parse_job`의 필드 라벨은 그대로 재사용 가능(`title`=종목/정책명, `table_rows`=조건표, `points`=체크포인트, `badges`=태그, `deadline`=일정/시행일).
- `job_card.py`: 레이아웃 그대로, 상단 라벨/색만 테마에 맞게. (예: "채용" 뱃지 → "종목/정책" 뱃지)
- `message_parser.py`: `JOB_WORDS = ("채용",...)` → `("종목","정책","상품",...)` 또는 원하는 단어. 핸들러 배선은 `main.py`에서 이름만.

### 10-3. 발굴 키워드 (trends.py — 가장 중요)
```python
_RELEVANCE_TERMS = (  # "우리 채널 주제인가"
  "코스피","코스닥","삼성전자","SK하이닉스","금리","환율","배당","ETF","반도체",
  "부동산","청약","전세","금리인하","연준","공모주","채권","리츠","연금","IRP","ISA", ...)
_SHARE_TERMS = (      # "저장·공유할 맛인가"
  "수익률","급등","폭락","배당","세금","절세","공제","환급","무료","꿀팁","전망","신고가", ...)
_SEED_QUERIES = ("배당주 추천","공모주 청약","금리 인하","부동산 정책","절세 방법","ETF 추천", ...)
```
`_KOREAN_FRIENDLY`(모델 선호)는 그대로. 점수 공식도 그대로.

### 10-4. 카드뉴스/커뮤니티 프롬프트 톤 (summarize.py)
- `_build_prompt`(뉴스카드): "자동차산업 취준생 대상" → "재테크 대상" 캐러셀. 규칙(요약/배경/전망/캡션/하이라이트)은 구조 유지.
- `_build_community_prompt`: 대상만 교체. 본문요약+댓글반응+투자자 포인트 구조 유지.
- **언어 강제/마커 포맷/드리프트 감지는 절대 건드리지 말 것** (엔진).

### 10-5. 카페/게시판
- 재테크 카페의 `NAVER_CAFE_CLUB_ID`, 일반글/정보글 `NAVER_CAFE_*_MENU_ID` 재설정.
- `editor.build_job_post`의 제목/문구 템플릿만 테마화.

### 10-6. 그대로 두는 것 (건드리지 말 것)
텔레그램 루프·라우팅·워커·취소, AI 제공자/폴백/비전/비교, 카드 렌더 엔진,
카페 API·인코딩·999 처리, 기사수집, 단축주소, 상태머신, 로고, N-M 선택, 재시도, 확인 흐름.

---

## 11. 새 명령 추가 레시피 (엔진에 기능 하나 붙이는 법)

1. `message_parser.py`: `XXX_WORDS = (...)` 추가 → `detect_mode`에 `if head in XXX_WORDS: return "xxx", rest`.
2. `main.py`: `def handle_xxx(tg, chat_id, content): ...` 작성. 무거우면 내부에서 상태머신/워커 활용.
3. `main.py` `handle_message`: `elif mode == "xxx": handle_xxx(...)`.
4. 사진 기반이면: `main()` 폴링의 `photo_groups` 루프에 캡션/상태 분기 추가.
5. `HELP_TEXT`에 사용법 한 줄.
6. `.env.example`에 새 설정 있으면 추가(빈값 기본).
7. **테스트**: mock으로 라우팅·핸들러·에러경로 검증(아래 관행).

---

## 12. 테스트/검증 관행

- **이 개발환경은 외부망(네이버/구글/텔레그램/AI)이 전부 막혀 있음.** 그래서 라이브 호출은
  전부 **mock으로 로직만 검증**하고, 실제 응답은 **사용자 PC에서 확인**한다(반복된 패턴).
- 새 코드는 항상 `python3 -m py_compile` → mock 단위테스트(라우팅/핸들러/에러경로) → 커밋.
- 대표 mock 대상: `requests.get/post`, `fetch_article`, `build_job_data`, `compare_*`,
  `_download_photos`, `PIL.Image.open`, `post_article`, `tg.send_message/send_photo`.
- 렌더 결과는 mock 배경으로 PNG를 실제로 그려 눈으로 확인(폰트는 fonts/ 자동 다운로드).

---

## 13. 알려진 제약 / 주의

- **네이버 카페 999(스팸필터)**: 재시도로 못 뚫음. 링크 줄이기·시간 두기·계정 신뢰도 쌓기.
  코드는 막히면 **복붙 텍스트를 반환**하는 게 최선.
- **무료 AI 모델 변동**: OpenRouter `:free`가 유료로 바뀌기도 함 → 자동 탐색으로 대응.
  Groq이 무료 안정성 가장 좋음.
- **텔레그램 압축**: 고화질 필요하면 '파일'로.
- **외부망 검증 불가**(개발환경): 실제 동작은 사용자 PC 재시작 후 확인.
- **콘텐츠 진정성**: 실제 인물/기관 사칭·허위 게시물 생성 금지(엔진 차원의 정책).

---

## 14. 로드맵 (미완/다음)

- 발굴 2단계: 인스타 인사이트(저장/공유수) 입력받아 발굴 점수 가중치 자동 학습.
- 링크 자동 N개 제한 옵션(999 예방).
- 테마 프리셋 파일화(`theme.py`)로 도메인 상수(키워드/프롬프트/라벨)를 한 파일에 모으면 복제가 더 쉬움 — **재테크 버전 만들 때 이 리팩터를 먼저 하는 걸 추천**.

---

*이 문서는 취업 테마 기준으로 작성됨. 재테크 등 새 테마는 3장·10장을 따라 "엔진 유지 + 테마 3곳(프롬프트/정보카드/발굴키워드) 교체"로 복제할 것.*
