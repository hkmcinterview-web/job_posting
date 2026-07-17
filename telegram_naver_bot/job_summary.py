# -*- coding: utf-8 -*-
"""채용공고 페이지 텍스트 → 카드/카페글용 구조화 데이터 추출 (AI).

카드 구성(정보정리형 카드, APT_LAP 스타일 참고):
  - deadline : 좌상단 빨간 글씨 (접수 마감)
  - title    : 큰 제목 1~2줄 (회사명 + 채용 성격)
  - badges   : 빨간 뱃지 1~2개 (신입/정규직 등)
  - table    : 모집분야 표 (머리글 + 최대 5줄)
  - points   : 📌 핵심 포인트 (지원자격/절차 등, {{...}} 는 형광 강조)
  - infos    : 우하단 요약 미니표 (고용형태/근무지/마감 등)
  - summary  : 카페 게시글 본문용 정리 텍스트

뉴스 카드와 동일하게 마커 구분 텍스트 포맷을 사용해 따옴표 등에 안전합니다.
"""
import re

from summarize import generate_text

_JOB_BLOCK_RE = re.compile(r"<{2,3}\s*JOB\s*>{2,3}(.*?)<{2,3}\s*END\s*>{2,3}",
                           re.DOTALL | re.IGNORECASE)
_SUMMARY_BLOCK_RE = re.compile(r"<{2,3}\s*SUMMARY\s*>{2,3}(.*?)<{2,3}\s*END\s*>{2,3}",
                               re.DOTALL | re.IGNORECASE)
_FIELD_RE = re.compile(r"^\s*(COMPANY|TITLE|DEADLINE|BADGE|TABLE_HEAD|TABLE_ROW|POINT|INFO|COLOR)"
                       r"\s*:\s*(.*)$", re.IGNORECASE)


def _build_prompt(page: dict, with_images: bool = False) -> str:
    intro = ("다음은 기업 채용공고 내용입니다. 이걸로 SNS용 '채용공고 카드' 이미지 1장과\n"
             "네이버 카페 게시글을 만들 겁니다. 아래 마커 형식을 정확히 지켜 출력하세요.\n"
             "다른 인사말/설명 없이 형식만 출력합니다.\n\n")
    if with_images:
        intro = ("첨부한 이미지는 기업 채용공고를 캡처한 것입니다. 이미지 속 내용을 꼼꼼히 읽고,\n"
                 "SNS용 '채용공고 카드'와 네이버 카페 게시글용으로 아래 마커 형식에 맞춰 추출하세요.\n"
                 "다른 인사말/설명 없이 형식만 출력합니다.\n\n")
    return intro + (
        "<<<JOB>>>\n"
        "COMPANY: 회사명 (간결하게, 예: 현대자동차)\n"
        "TITLE: 카드 큰 제목 1~2줄 — 줄 구분은 / (각 줄 4~12자, 회사명 포함, 예: 현대자동차/신입 채용)\n"
        "DEADLINE: 접수 마감 (예: 7.31(금) 17:00 — 없으면 '상시채용', 마감된 공고면 실제 마감일)\n"
        "BADGE: 빨간 뱃지 1~2개, | 구분, 각 2~5자 (예: 신입|정규직)\n"
        "TABLE_HEAD: 모집 표 머리글 2~4개, | 구분 (예: 구분|직무|근무지 — 공고 내용에 맞게 조정)\n"
        "TABLE_ROW: 표 한 줄, | 구분, 머리글과 개수 일치. ⚠️ 공고에 나온 모집분야/직무를\n"
        "          하나도 빠짐없이 전부 나열할 것 (임의로 합치거나 생략 금지). 공고에 5개면 5줄,\n"
        "          7개면 7줄. 원문에 적힌 직무명·근무지를 그대로 쓰고, 지어내지 말 것 (각 칸 2~12자)\n"
        "POINT: 핵심 정보 한 줄씩 3~5개 (지원자격/전형절차/우대사항/근무조건/일정 등, 각 12~26자)\n"
        "       가장 중요한 부분은 {{이렇게}} 감싸서 강조 (전체에서 1~2곳만)\n"
        "INFO: 우하단 요약표 '항목|값' 형태 2~4개 (항목 2~5자, 값 2~8자. 예: 고용형태|정규직)\n"
        "COLOR: 이 회사의 공식 브랜드 대표색 1개를 #RRGGBB hex 로 (확실히 알 때만. 모르면 이 줄 생략)\n"
        "<<<END>>>\n\n"
        "<<<SUMMARY>>>\n"
        "(카페 게시글 본문 — 이모지/해시태그 없이 아래 구성으로)\n"
        "회사와 이번 채용을 소개하는 1~2문장\n"
        "■ 모집분야 : ...\n"
        "■ 지원자격 : ...\n"
        "■ 전형절차 : ...\n"
        "■ 접수기간 : ...\n"
        "■ 근무조건 : ... (공고에 있는 항목만, 없는 건 빼기)\n"
        "<<<END>>>\n\n"
        "규칙: 공고에 없는 내용을 지어내지 말 것. 숫자/날짜는 원문 그대로.\n\n"
        f"[페이지 제목] {page.get('title', '')}\n"
        f"[설명] {page.get('description', '')}\n"
        f"[페이지 내용]\n{page.get('text', '')}"
    )


def _parse_job(text: str) -> dict:
    m = _JOB_BLOCK_RE.search(text or "")
    if not m:
        return {}
    job = {"company": "", "title": "", "deadline": "", "badges": [],
           "table_head": [], "table_rows": [], "points": [], "infos": [],
           "brand_color": ""}
    for line in m.group(1).split("\n"):
        fm = _FIELD_RE.match(line)
        if not fm:
            continue
        key, value = fm.group(1).upper(), fm.group(2).strip()
        if not value:
            continue
        if key == "COMPANY":
            job["company"] = value
        elif key == "TITLE":
            job["title"] = value
        elif key == "DEADLINE":
            job["deadline"] = value
        elif key == "BADGE":
            job["badges"] = [b.strip() for b in value.split("|") if b.strip()][:2]
        elif key == "TABLE_HEAD":
            job["table_head"] = [c.strip() for c in value.split("|") if c.strip()][:4]
        elif key == "TABLE_ROW":
            job["table_rows"].append([c.strip() for c in value.split("|")])
        elif key == "POINT":
            job["points"].append(value)
        elif key == "COLOR":
            job["brand_color"] = value
        elif key == "INFO":
            kv = [c.strip() for c in value.split("|")]
            if len(kv) >= 2 and kv[0] and kv[1]:
                job["infos"].append((kv[0], kv[1]))

    # 표 정합성 — 머리글 개수에 맞게 자르거나 채움 (모든 직무를 담기 위해 최대 8줄)
    ncol = len(job["table_head"])
    if ncol:
        rows = []
        for row in job["table_rows"][:8]:
            row = (row + [""] * ncol)[:ncol]
            rows.append(row)
        job["table_rows"] = rows
    else:
        job["table_rows"] = []
    job["points"] = job["points"][:6]
    job["infos"] = job["infos"][:4]
    return job


def build_job_data(page: dict, images=None):
    """returns (job_dict|None, summary, engine, error)

    images: [(mime_type, base64), ...] — 채용공고 캡처 사진 (링크 대신 사진으로 받은 경우)"""
    prompt = _build_prompt(page, with_images=bool(images))
    # temperature=0 — 같은 공고는 항상 같은 결과가 나오도록 (매번 다르게 묶이는 문제 방지)
    text, engine, error = generate_text(prompt, temperature=0.0, images=images)
    if not text:
        return None, "", engine, error

    job = _parse_job(text)
    summary_m = _SUMMARY_BLOCK_RE.search(text)
    summary = summary_m.group(1).strip() if summary_m else ""

    if not job or not job.get("title"):
        return None, summary, engine, "AI 응답에서 채용 정보를 추출하지 못함"
    return job, summary, engine, ""
