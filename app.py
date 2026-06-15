# -*- coding: utf-8 -*-
"""
자동차 채용공고 아카이브 — 공개 열람 웹앱 (Streamlit)
같은 폴더의 data.json(번들 데이터)을 읽어 검색·필터·상세보기를 제공합니다.
Google Cloud/서비스계정 불필요. 공고가 바뀌면 data.json만 교체하면 됩니다.
"""
import json
import datetime as dt
from pathlib import Path

import pandas as pd
import streamlit as st

PAGE_TITLE = "🚗 자동차 채용공고 아카이브"
DATA_FILE = Path(__file__).parent / "data.json"

st.set_page_config(page_title=PAGE_TITLE, page_icon="🚗", layout="wide")


@st.cache_data
def load_data():
    if not DATA_FILE.exists():
        return pd.DataFrame()
    recs = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    df = pd.DataFrame(recs)
    for c in ["company", "title", "job_family", "employment_type", "business_unit",
              "job_category", "location", "status", "source_url", "deadline", "body"]:
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


st.title(PAGE_TITLE)
st.caption("마감 후에도 직무기술서를 다시 볼 수 있도록 보관한 채용공고 아카이브입니다.")

df = load_data()
if df.empty:
    st.warning("data.json 을 찾을 수 없습니다. app.py 와 같은 폴더에 data.json 을 두세요.")
    st.stop()

# 지표
c1, c2, c3 = st.columns(3)
c1.metric("전체 공고", f"{len(df)}건")
c2.metric("모집중", f"{(df['status'] == '모집중').sum()}건")
imminent = int(df["D-day"].str.match(r"D-([0-7])$").fillna(False).sum())
c3.metric("마감 임박(7일 이내)", f"{imminent}건")

st.divider()

# 필터
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

cols = ["company", "title", "employment_type", "job_family", "location", "deadline", "D-day", "status"]
st.dataframe(
    view[cols].rename(columns={
        "company": "회사", "title": "직무", "employment_type": "채용구분",
        "job_family": "직군", "location": "근무지", "deadline": "마감일", "status": "상태",
    }),
    use_container_width=True, hide_index=True,
)

st.divider()
st.subheader("📄 상세 보기")
if len(view):
    idx = list(view.index)
    labels = view.apply(lambda r: f"{r['company']} — {r['title']} ({r['employment_type']})", axis=1).tolist()
    pick = st.selectbox("공고 선택", options=idx, format_func=lambda i: labels[idx.index(i)])
    row = view.loc[pick]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("채용구분", row["employment_type"] or "-")
    m2.metric("직군", row["job_family"] or "-")
    m3.metric("근무지", row["location"] or "-")
    m4.metric("마감", f"{row['deadline']} ({row['D-day']})" if row["deadline"] else "-")
    if row.get("source_url"):
        st.link_button("🔗 원문 공고 보기", row["source_url"])
    st.markdown(row.get("body", ""))
else:
    st.info("조건에 맞는 공고가 없습니다.")
