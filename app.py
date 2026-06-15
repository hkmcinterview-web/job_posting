# -*- coding: utf-8 -*-
"""
자동차 채용공고 아카이브 — 공개 열람 웹앱 (Streamlit)
같은 폴더의 data.json(번들 데이터)을 읽어 검색·필터·상세보기를 제공합니다.
Google Cloud/서비스계정 불필요.
"""
import json
import html as _html
import datetime as dt
from pathlib import Path

import pandas as pd
import streamlit as st

PAGE_TITLE = "🚗 자동차 채용공고 아카이브"
DATA_FILE = Path(__file__).parent / "data.json"
SECTIONS = {"조직소개", "직무상세", "주요업무", "주요 업무", "지원자격",
            "우대사항", "전형절차", "기타", "키워드", "모집분야"}

st.set_page_config(page_title=PAGE_TITLE, page_icon="🚗", layout="wide")

CSS = """
<style>
.block-container {max-width: 1100px;}
.job-card {background:#fff; border:1px solid #e7e9ee; border-radius:16px;
  padding:30px 34px; box-shadow:0 2px 14px rgba(20,30,60,.06);
  line-height:1.75; font-size:16px; color:#1f2430;}
.job-card .company {color:#5b6472; font-size:14px; font-weight:600; letter-spacing:.2px;}
.job-card .title {font-size:27px; font-weight:800; margin:4px 0 14px; color:#10141c; line-height:1.3;}
.job-card .badges {display:flex; flex-wrap:wrap; gap:8px; margin-bottom:8px;}
.job-card .badge {display:inline-block; padding:5px 12px; border-radius:999px;
  font-size:13px; font-weight:700; border:1px solid transparent;}
.badge.emp-res {background:#e8f0ff; color:#1c4fd6; border-color:#cfe0ff;}
.badge.emp-adm {background:#e7f7ee; color:#127a40; border-color:#c8eed8;}
.badge.fam {background:#f3f0ff; color:#5b3fd6; border-color:#e2dbff;}
.badge.loc {background:#f1f3f7; color:#3f4756;}
.badge.dday {background:#fff1e6; color:#c2410c; border-color:#ffd9bf;}
.job-card hr {border:none; border-top:1px solid #eef0f4; margin:20px 0;}
.sec {margin:18px 0 6px;}
.sec-h {font-size:15px; font-weight:800; color:#0b63d6; margin:0 0 8px;
  padding-left:11px; border-left:4px solid #2f6fed; letter-spacing:.3px;}
.job-card .subhead {font-weight:700; color:#222; margin:10px 0 4px;}
.job-card p {margin:6px 0;}
.job-card ul {margin:6px 0 6px 4px; padding-left:0; list-style:none;}
.job-card ul li {position:relative; padding-left:18px; margin:5px 0;}
.job-card ul li:before {content:"•"; color:#2f6fed; position:absolute; left:2px; font-weight:700;}
.job-card .note {color:#7a8496; font-size:13.5px; margin:8px 0;}
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


# ── 화면 ─────────────────────────────────────────────────────
st.markdown(CSS, unsafe_allow_html=True)
st.title(PAGE_TITLE)
st.caption("마감 후에도 직무기술서를 다시 볼 수 있도록 보관한 채용공고 아카이브입니다.")

df = load_data()
if df.empty:
    st.warning("data.json 을 찾을 수 없습니다. app.py 와 같은 폴더에 data.json 을 두세요.")
    st.stop()

c1, c2, c3 = st.columns(3)
c1.metric("전체 공고", f"{len(df)}건")
c2.metric("신입-관리직", f"{(df['employment_type'] == '신입-관리직').sum()}건")
c3.metric("신입-연구직", f"{(df['employment_type'] == '신입-연구직').sum()}건")

st.divider()

f1, f2, f3, f4 = st.columns([2, 1, 1, 1])
q = f1.text_input("🔎 검색 (회사·직무·본문 키워드)", "")


def opts(col):
    return sorted([x for x in df[col].unique() if str(x).strip()])


sel_emp = f2.multiselect("채용구분", opts("employment_type"))
sel_fam = f3.multiselect("직군", opts("job_family"))
sel_loc = f4.multiselect("근무지", opts("location"))

view = df.copy()
if q:
    ql = q.lower()
    view = view[view.apply(lambda r: ql in str(r.to_dict()).lower(), axis=1)]
if sel_emp:
    view = view[view["employment_type"].isin(sel_emp)]
if sel_fam:
    view = view[view["job_family"].isin(sel_fam)]
if sel_loc:
    view = view[view["location"].isin(sel_loc)]

st.markdown(f"**{len(view)}건** 표시 중")

cols = ["company", "title", "employment_type", "job_family", "location", "deadline", "D-day"]
st.dataframe(
    view[cols].rename(columns={
        "company": "회사", "title": "직무", "employment_type": "채용구분",
        "job_family": "직군", "location": "근무지", "deadline": "마감일",
    }),
    use_container_width=True, hide_index=True,
)

st.divider()
st.subheader("📄 상세 보기")
if len(view):
    idx = list(view.index)
    labels = view.apply(lambda r: f"{r['title']} · {r['employment_type']} · {r['business_unit']}", axis=1).tolist()
    pick = st.selectbox("공고 선택", options=idx, format_func=lambda i: labels[idx.index(i)])
    render_posting(view.loc[pick])
else:
    st.info("조건에 맞는 공고가 없습니다.")
