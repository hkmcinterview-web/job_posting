# -*- coding: utf-8 -*-
"""
현대자동차 채용 스크래퍼 (Playwright) - v4
talent.hyundai.com 목록(전체/월간)을 돌며 직무기술서를 읽어 data_hyundai.json 저장.
고용형태(신입/경력/인턴/계약직/기타) 자동 인식. 두 가지 카드 구조 모두 처리.

[설치]  pip install playwright  /  playwright install chromium
[실행]  python hyundai_scraper.py
0건/부족하면 debug_list.txt 를 채팅에 올려주세요.
"""
import json, re, time
from pathlib import Path
from playwright.sync_api import sync_playwright

LIST_URLS = [
    # 전체 채용 목록(신입/경력/인턴/계약직 등)
    "https://talent.hyundai.com/apply/applyList.hc?nfGubnC=ac85892205b92e8cecdc87185a3fbf039f04b2a7751ccf0e8a1f547d53b9945a&tagArray=&sortDataTagArray=&areaDataTagArray=&fieldDataTagArray=&occupDataTagArray=&intnsvYn=",
    # 월간 경력채용(경력 전부 확실히 확보용)
    "https://talent.hyundai.com/theme/hall.hc",
]

HERE = Path(__file__).parent
OUT = HERE / "data_hyundai.json"
DEBUG = HERE / "debug_list.txt"

FAMILY = {"연구개발": "R&D/설계", "생산/제조": "생산기술", "사업/기획": "사업/기획",
          "경영지원": "경영지원", "IT": "IT", "기타": "기타"}
META = {"북마크공유", "북마크", "공유", "전체", "분야", "직무", "공고명", "부문", "지역", "마감일순",
        "연구개발", "생산/제조", "사업/기획", "경영지원", "IT", "기타"}
EMP = {"신입", "경력", "인턴", "계약직", "기타", "장학생", "신입-현장직", "경력-현장직",
       "신입-관리직", "신입-연구직", "경력-관리직", "경력-연구직"}


def parse_list(text):
    lines = [l.strip() for l in text.replace("\r", "").split("\n")]
    hdr = 0
    for i, l in enumerate(lines):
        if "마감일순" in l or "채용공고가 진행" in l:
            hdr = i
    n = len(lines)
    cards, i = [], (hdr + 1 if hdr else 0)
    while i < n:
        if lines[i].startswith("#"):
            j = i
            run = []
            while j < n and lines[j].startswith("#"):
                run.append(lines[j]); j += 1
            fam = emp = loc = jik = ""
            last = run[-1].lstrip("#").strip()
            if run[-1].endswith("채용") and len(run) >= 4:          # 캠페인 태그(…채용)가 마지막
                fam = run[0].lstrip("#").strip()
                emp = run[-2].lstrip("#").strip()
                loc = run[-3].lstrip("#").strip() if len(run) >= 3 else ""
                jik = run[1].lstrip("#").strip() if len(run) >= 5 else fam
            elif last in EMP and len(run) >= 3:                    # 고용형태가 마지막(계약직/기타 등)
                fam = run[0].lstrip("#").strip()
                emp = last
                loc = run[-2].lstrip("#").strip()
                jik = run[1].lstrip("#").strip() if len(run) >= 4 else ""
            if emp:
                block, k = [], i - 1
                while k > hdr and not lines[k].startswith("#") and len(block) < 10:
                    if lines[k]:
                        block.append(lines[k])
                    k -= 1
                skip = {fam, jik, loc, emp} | META
                cand = [x for x in block if x not in skip and not re.fullmatch(r"D-\d+", x)
                        and not re.search(r"\d{1,2}\s*월.*채용", x)
                        and "상시" not in x and "채용시까지" not in x and "총" not in x
                        and "진행" not in x and "검색" not in x and "자세히" not in x
                        and "Filter" not in x and "초기화" not in x]
                title = max(cand, key=len) if cand else ""
                if title.startswith("[" + emp + "]"):
                    title = title[len("[" + emp + "]"):].strip()
                if title:
                    cards.append({"title": title, "bunya": fam, "jikmu": jik, "loc": loc, "emp": emp})
            i = j
        else:
            i += 1
    seen, uniq = set(), []
    for c in cards:
        if c["title"] and c["title"] not in seen:
            seen.add(c["title"]); uniq.append(c)
    return uniq


def parse_detail(text):
    t = text.replace("\r", "")
    idx = t.find("Come Grow with Us")
    b = t[idx + len("Come Grow with Us"):] if idx > -1 else t
    j = b.find("목록가기")
    if j > -1:
        b = b[:j]
    m = re.search(r"~\s*(\d{4}-\d{2}-\d{2})", b)
    deadline = m.group(1) if m else ""
    k = re.search(r"\n기타\n", b)
    if k:
        b = b[:k.start()]
    return deadline, b.strip()


def load_all(page):
    """더보기 클릭 + 스크롤로 모든 카드 로드."""
    for _ in range(60):
        clicked = False
        for label in ["더보기", "더 보기", "MORE"]:
            try:
                btn = page.get_by_text(label, exact=True)
                if btn.count() and btn.first.is_visible():
                    btn.first.click(); page.wait_for_timeout(1000); clicked = True; break
            except Exception:
                pass
        if clicked:
            continue
        before = page.evaluate("document.body.scrollHeight")
        try:
            page.keyboard.press("End")
        except Exception:
            pass
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(800)
        if page.evaluate("document.body.scrollHeight") == before:
            page.wait_for_timeout(700)
            if page.evaluate("document.body.scrollHeight") == before:
                break
    page.wait_for_timeout(1000)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        all_cards, dbg = [], []
        for lu in LIST_URLS:
            print(f"목록 여는 중: {lu[:60]}...")
            page.goto(lu, wait_until="domcontentloaded")
            try:
                page.wait_for_function("() => /채용공고|채용/.test(document.body.innerText)", timeout=25000)
            except Exception:
                pass
            page.wait_for_timeout(2500)
            load_all(page)
            body = page.inner_text("body")
            dbg.append(f"===== {lu} =====\n" + body)
            cards = parse_list(body)
            for c in cards:
                c["lu"] = lu
            print(f"  발견: {len(cards)}건")
            all_cards += cards
        DEBUG.write_text("\n\n".join(dbg), encoding="utf-8")

        seen, cards = set(), []
        for c in all_cards:
            if c["title"] not in seen:
                seen.add(c["title"]); cards.append(c)
        print(f"총 수집(중복 제거): {len(cards)}건")
        if not cards:
            print("0건입니다. debug_list.txt 를 채팅에 올려주세요.")
            browser.close(); return

        results = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else []
        done = {r["title"] for r in results}
        for idx, c in enumerate(cards, 1):
            if c["title"] in done:
                continue
            print(f"[{idx}/{len(cards)}] ({c['emp']}) {c['title']}")
            try:
                page.goto(c["lu"], wait_until="domcontentloaded")
                page.wait_for_timeout(1500)
                load_all(page)
                page.get_by_text(c["title"], exact=True).first.click(timeout=8000)
                page.wait_for_url("**/applyView.hc*", timeout=12000)
                page.wait_for_timeout(2800)
                deadline, bodytext = parse_detail(page.inner_text("body"))
                results.append({
                    "company": "현대자동차", "title": c["title"], "employment_type": c["emp"],
                    "business_unit": c["jikmu"], "job_category": f"{c['bunya']} / {c['jikmu']}",
                    "job_family": FAMILY.get(c["bunya"], c["bunya"]), "location": c["loc"],
                    "deadline": deadline, "status": "모집중",
                    "captured_date": time.strftime("%Y-%m-%d"),
                    "tags": [c["bunya"], c["jikmu"], c["loc"], c["emp"]],
                    "source_url": page.url, "body": bodytext,
                })
                OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception as e:
                print(f"   건너뜀: {e}")
                continue

        browser.close()
        print(f"\n완료! {len(results)}건 -> {OUT}")


if __name__ == "__main__":
    main()
