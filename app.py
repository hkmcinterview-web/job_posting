# -*- coding: utf-8 -*-
"""
잡앤유 자동차산업 채용공고 아카이브 — 공개 열람 웹앱 (Streamlit)
같은 폴더의 data.json(번들 데이터)을 읽어 회사·직군 등으로 검색·필터하고
직무기술서 전문을 보여줍니다. Google Cloud/서비스계정 불필요.
"""
import json
import html as _html
import datetime as dt
from pathlib import Path

import pandas as pd
import streamlit as st

PAGE_TITLE = "잡앤유 자동차산업 채용공고 아카이브"
DATA_FILE = Path(__file__).parent / "data.json"
CONSULT_URL = "https://litt.ly/jobnyou"
SPEC_URL = "https://spec-dashboard-6bmjdppkw4ayr2w5q85gky.streamlit.app/"
YT_CHANNEL = "https://www.youtube.com/@잡앤유"
VIDEOS = [
    ("wicrZql_1JA", "현대자동차 서류합격을 원한다면 이렇게 써보세요! (합격자소서 분석 · 품질/구매/생기)"),
    ("Po__JFWKH_A", "현대자동차그룹 자기소개 PT면접 대비하기"),
    ("awI5xp4OMgQ", "최종면접 탈락, 후회말고 이렇게 준비해보세요!"),
]
SECTIONS = {"조직소개", "직무상세", "주요업무", "주요 업무", "지원자격",
            "우대사항", "전형절차", "기타", "키워드", "모집분야"}

st.set_page_config(page_title=PAGE_TITLE, page_icon="🚗", layout="wide")

CSS = """
<style>
.block-container {max-width: 1120px; padding-top: 2.2rem;}
/* 상세 카드 */
.job-card {background:#fff; border:1px solid #e7e9ee; border-radius:16px;
  padding:30px 34px; box-shadow:0 2px 14px rgba(20,30,60,.06);
  line-height:1.75; font-size:16px; color:#1f2430;}
.job-card .company {color:#5b6472; font-size:14px; font-weight:600;}
.job-card .title {font-size:26px; font-weight:800; margin:4px 0 14px; color:#10141c; line-height:1.3;}
.job-card .badges {display:flex; flex-wrap:wrap; gap:8px; margin-bottom:8px;}
.job-card .badge {display:inline-block; padding:5px 12px; border-radius:999px; font-size:13px; font-weight:700;}
.badge.emp-res {background:#e8f0ff; color:#1c4fd6;}
.badge.emp-adm {background:#e7f7ee; color:#127a40;}
.badge.fam {background:#f3f0ff; color:#5b3fd6;}
.badge.loc {background:#f1f3f7; color:#3f4756;}
.badge.dday {background:#fff1e6; color:#c2410c;}
.job-card hr {border:none; border-top:1px solid #eef0f4; margin:20px 0;}
.sec {margin:18px 0 6px;}
.sec-h {font-size:15px; font-weight:800; color:#0b63d6; margin:0 0 8px; padding-left:11px; border-left:4px solid #2f6fed;}
.job-card .subhead {font-weight:700; color:#222; margin:10px 0 4px;}
.job-card p {margin:6px 0;}
.job-card ul {margin:6px 0 6px 4px; padding-left:0; list-style:none;}
.job-card ul li {position:relative; padding-left:18px; margin:5px 0;}
.job-card ul li:before {content:"•"; color:#2f6fed; position:absolute; left:2px; font-weight:700;}
.job-card .note {color:#7a8496; font-size:13.5px; margin:8px 0;}
/* 유튜브 배너 */
.yt-wrap {background:#fbf7f7; border:1px solid #f1dada; border-radius:16px; padding:18px 20px; margin:6px 0 4px;}
.yt-head {font-size:15px; font-weight:800; color:#c4302b; margin-bottom:12px; display:flex; align-items:center; gap:8px;}
.yt-grid {display:grid; grid-template-columns:repeat(auto-fit, minmax(210px,1fr)); gap:14px;}
.yt-card {display:block; text-decoration:none; color:inherit; background:#fff; border:1px solid #eee; border-radius:12px; overflow:hidden; transition:transform .12s, box-shadow .12s;}
.yt-card:hover {transform:translateY(-2px); box-shadow:0 6px 18px rgba(0,0,0,.10);}
.yt-thumb {position:relative; width:100%; aspect-ratio:16/9; background:#000;}
.yt-thumb img {width:100%; height:100%; object-fit:cover; display:block;}
.yt-play {position:absolute; inset:0; margin:auto; width:46px; height:46px; border-radius:50%;
  background:rgba(196,48,43,.92); color:#fff; display:flex; align-items:center; justify-content:center; font-size:18px;}
.yt-title {padding:10px 12px 12px; font-size:13.5px; font-weight:600; line-height:1.45; color:#222;
  display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;}
/* 컨설팅 CTA */
.cta {display:flex; align-items:center; justify-content:space-between; gap:16px; flex-wrap:wrap;
  text-decoration:none; background:#10141c; border-radius:16px; padding:22px 26px; margin:8px 0 4px;}
.cta-t {color:#fff; font-size:19px; font-weight:800; line-height:1.35;}
.cta-s {color:#aeb6c4; font-size:14px; margin-top:4px;}
.cta-btn {background:#2f6fed; color:#fff; font-weight:800; font-size:15px; padding:13px 22px; border-radius:10px; white-space:nowrap;}
/* 모바일 */
@media (max-width:640px){
  .block-container {padding-top:1.4rem;}
  .job-card {padding:20px 18px; font-size:15px;}
  .job-card .title {font-size:21px;}
  .cta {padding:18px; }
  .cta-t {font-size:17px;}
  .cta-btn {width:100%; text-align:center;}
}
</style>
"""


@st.cache_data
def load_data():
    if not DATA_FILE.exists():
        return pd.DataFrame()
    recs = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    df = pd.DataFrame(recs)
    for c in ["company", "title", "job_family", "employment_type", "business_unit",
              "job_category", "location", "deadline", "body"]:
        if c not in df.columns:
            df[c] = ""
    df["deadline"] = df["deadline"].astype(str)
    today = dt.date.today()

    def dday(s):
        try:
            n = (dt.date.fromisoformat(str(s)[:10]) - today).days
            return f"D-{n}" if n >= 0 else "마감"
        except Exception:
            return ""

    df["D-day"] = df["deadline"].map(dday)
    return df


def body_to_html(body: str) -> str:
    out, listbuf, opened = [], [], False

    def flush():
        nonlocal listbuf
        if listbuf:
            out.append("<ul>" + "".join(f"<li>{_html.escape(x)}</li>" for x in listbuf) + "</ul>")
            listbuf = []

    for raw in (body or "").replace("\r", "").split("\n"):
        s = raw.strip()
        norm = s.lstrip("#").strip()
        if norm in SECTIONS:
            flush()
            if opened:
                out.append("</div>")
            out.append(f'<div class="sec"><div class="sec-h">{_html.escape(norm)}</div>')
            opened = True
            continue
        if not s:
            flush()
            continue
        if not opened:
            out.append('<div class="sec">')
            opened = True
        if s.startswith("- "):
            listbuf.append(s[2:].strip())
        elif s.startswith("["):
            flush()
            out.append(f'<div class="subhead">{_html.escape(s)}</div>')
        elif s.startswith("※"):
            flush()
            out.append(f'<div class="note">{_html.escape(s)}</div>')
        else:
            flush()
            out.append(f'<p>{_html.escape(s)}</p>')
    flush()
    if opened:
        out.append("</div>")
    return "".join(out)


def render_posting(row):
    emp = str(row.get("employment_type", ""))
    emp_cls = "emp-res" if "연구" in emp else "emp-adm"
    bu = str(row.get("business_unit", ""))
    comp = _html.escape(str(row.get("company", "")) + (f" · {bu}" if bu else ""))
    title = _html.escape(str(row.get("title", "")))
    badges = [f'<span class="badge {emp_cls}">{_html.escape(emp)}</span>']
    if row.get("job_family"):
        badges.append(f'<span class="badge fam">{_html.escape(str(row["job_family"]))}</span>')
    if row.get("location"):
        badges.append(f'<span class="badge loc">📍 {_html.escape(str(row["location"]))}</span>')
    if row.get("deadline"):
        badges.append(f'<span class="badge dday">🗓 마감 {_html.escape(str(row["deadline"]))} ({row.get("D-day","")})</span>')
    head = (f'<div class="company">{comp}</div><div class="title">{title}</div>'
            f'<div class="badges">{"".join(badges)}</div><hr/>')
    st.markdown(f'<div class="job-card">{head}{body_to_html(row.get("body",""))}</div>',
                unsafe_allow_html=True)


def youtube_banner():
    cards = []
    for vid, title in VIDEOS:
        url = f"https://youtu.be/{vid}"
        thumb = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
        cards.append(
            f'<a class="yt-card" href="{url}" target="_blank" rel="noopener" '
            f'style="text-decoration:none !important;">'
            f'<div class="yt-thumb"><img src="{thumb}" alt=""><span class="yt-play">&#9654;</span></div>'
            f'<div style="padding:10px 12px 12px; font-size:13.5px; font-weight:600; '
            f'line-height:1.45; color:#222 !important;">{_html.escape(title)}</div></a>'
        )
    st.markdown(
        f'<div class="yt-wrap"><div class="yt-head">&#9654; 잡앤유 유튜브 — 자동차산업 취업 노하우</div>'
        f'<div class="yt-grid">{"".join(cards)}</div></div>',
        unsafe_allow_html=True,
    )


def spec_banner():
    inner = (
        '<div style="display:flex; align-items:center; justify-content:space-between; '
        'gap:16px; flex-wrap:wrap; background:#10141c; border-radius:16px; padding:20px 26px;">'
        '<div style="text-align:left;">'
        '<div style="color:#ffffff !important; font-size:18px; font-weight:800; line-height:1.35;">'
        '📊 26년 상반기 현대차 서류합격 스펙분석</div>'
        '<div style="color:#aeb6c4 !important; font-size:13.5px; margin-top:4px;">'
        '합격자 스펙 데이터로 내 위치 확인하기</div></div>'
        '<div style="background:#2f6fed; color:#ffffff !important; font-weight:800; font-size:15px; '
        'padding:12px 22px; border-radius:10px; white-space:nowrap;">분석하러 가기 &rarr;</div></div>'
    )
    st.markdown(
        f'<a href="{SPEC_URL}" target="_blank" rel="noopener" '
        f'style="display:block; text-decoration:none !important; margin:4px 0 10px;">{inner}</a>',
        unsafe_allow_html=True,
    )


def consulting_banner():
    inner = (
        '<div style="display:flex; align-items:center; justify-content:space-between; '
        'gap:16px; flex-wrap:wrap; background:#10141c; border-radius:16px; padding:22px 26px;">'
        '<div style="text-align:left;">'
        '<div style="color:#ffffff !important; font-size:19px; font-weight:800; line-height:1.35;">'
        '자소서 첨삭 · 모의면접 1:1 컨설팅</div>'
        '<div style="color:#aeb6c4 !important; font-size:14px; margin-top:4px;">'
        '현직자 멘토와 함께 합격까지 — 잡앤유 컨설팅 바로가기</div></div>'
        '<div style="background:#2f6fed; color:#ffffff !important; font-weight:800; font-size:15px; '
        'padding:13px 22px; border-radius:10px; white-space:nowrap;">상담 신청하기 &rarr;</div></div>'
    )
    st.markdown(
        f'<a href="{CONSULT_URL}" target="_blank" rel="noopener" '
        f'style="display:block; text-decoration:none !important; margin:8px 0 4px;">{inner}</a>',
        unsafe_allow_html=True,
    )


# ── 화면 ─────────────────────────────────────────────────────
st.markdown(CSS, unsafe_allow_html=True)
st.title("🚗 " + PAGE_TITLE)
st.caption("자동차산업 채용공고를 기업별로 모아 보관합니다. 마감 후에도 직무기술서를 다시 볼 수 있어요.")

spec_banner()

df = load_data()
if df.empty:
    st.warning("data.json 을 찾을 수 없습니다. app.py 와 같은 폴더에 data.json 을 두세요.")
    st.stop()

c1, c2, c3 = st.columns(3)
c1.metric("전체 공고", f"{len(df)}건")
c2.metric("기업 수", f"{df['company'].nunique()}곳")
imminent = int(df["D-day"].str.match(r"D-([0-7])$").fillna(False).sum())
c3.metric("마감 임박(7일 이내)", f"{imminent}건")

st.divider()

q = st.text_input("🔎 검색 (회사·직무·본문 키워드)", "")
f1, f2, f3, f4 = st.columns(4)


def opts(col):
    return sorted([x for x in df[col].unique() if str(x).strip()])


sel_comp = f1.multiselect("기업", opts("company"))
sel_emp = f2.multiselect("채용구분", opts("employment_type"))
sel_fam = f3.multiselect("직군", opts("job_family"))
sel_loc = f4.multiselect("근무지", opts("location"))

view = df.copy()
if q:
    ql = q.lower()
    view = view[view.apply(lambda r: ql in str(r.to_dict()).lower(), axis=1)]
if sel_comp:
    view = view[view["company"].isin(sel_comp)]
if sel_emp:
    view = view[view["employment_type"].isin(sel_emp)]
if sel_fam:
    view = view[view["job_family"].isin(sel_fam)]
if sel_loc:
    view = view[view["location"].isin(sel_loc)]

view = view.sort_values(["company", "employment_type", "title"], kind="stable")
st.markdown(f"**{len(view)}건** 표시 중")

cols = ["company", "title", "employment_type", "job_family", "location", "deadline", "D-day"]
st.dataframe(
    view[cols].rename(columns={
        "company": "기업", "title": "직무", "employment_type": "채용구분",
        "job_family": "직군", "location": "근무지", "deadline": "마감일",
    }),
    use_container_width=True, hide_index=True,
)

# ── 유튜브 홍보 배너 (전체공고 ↔ 상세보기 사이) ──
youtube_banner()

st.divider()
st.subheader("📄 상세 보기")
if len(view):
    idx = list(view.index)
    labels = view.apply(lambda r: f"[{r['company']}] {r['title']} · {r['employment_type']}", axis=1).tolist()
    pick = st.selectbox("공고 선택", options=idx, format_func=lambda i: labels[idx.index(i)])
    render_posting(view.loc[pick])
else:
    st.info("조건에 맞는 공고가 없습니다.")

# ── 컨설팅 광고 배너 (상세보기 아래) ──
st.write("")
consulting_banner()
