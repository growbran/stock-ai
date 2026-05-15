"""
tabs/tab_kr.py
국내(KRX) 단기 트레이딩 스크리닝 탭.
수급 데이터: 요약 텍스트 + 클릭 시 외국인·기관·개인 차트
"""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd


def render():
    st.subheader("🇰🇷 국내 단기 트레이딩 — 종목 스크리닝")

    st.info(
        "**선정 조건 (우선순위 순)**\n"
        "1. 거래대금 급증 — 조회 시점 당일 기준\n"
        "2. 재료·테마 존재 — 뉴스·공시 AI 분석\n"
        "3. 차트 우상향 — 5일선 위, 전고점 돌파 구간\n\n"
        "_세 조건 모두 충족한 종목만 추천 출력_",
        icon="📋",
    )

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        top_n = st.selectbox("거래대금 상위", [30, 50, 100], index=0, key="kr_top_n")
    with col2:
        sentiment_min = st.slider("감성점수 최소", 0, 100, 65, key="kr_sentiment")
    with col3:
        run = st.button("🔍 지금 스크리닝", type="primary", key="kr_run", use_container_width=True)

    st.divider()

    if run:
        try:
            from modules.screener_kr import run_screening
            results = run_screening(top_n=top_n, sentiment_min=sentiment_min)
            _render_results(results)
        except ImportError as e:
            st.error(f"모듈 로드 오류: {e}")
    else:
        st.caption("조건을 설정하고 '지금 스크리닝' 버튼을 누르세요.")


def _render_results(results: list[dict]):
    if not results:
        st.warning("현재 조건에 맞는 종목이 없습니다.")
        return

    st.success(f"✅ 조건 충족 종목 {len(results)}개")

    for i, r in enumerate(results, 1):
        with st.expander(
            f"**{i}. {r.get('name','—')} ({r.get('ticker','—')})** "
            f"— AI 점수 {r.get('score',0)}점 | {r.get('signal','—')}",
            expanded=(i == 1),
        ):
            # ── 기본 지표 ──
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("현재가",      r.get("price", "—"))
            c2.metric("거래대금",    r.get("trade_value", "—"))
            c3.metric("뉴스 감성점수", r.get("sentiment", "—"))
            c4.metric("거래량 증가율", r.get("volume_ratio", "—"))

            st.markdown(f"**테마·재료**: {r.get('theme', '—')}")
            st.markdown(f"**차트 상태**: {r.get('chart_status', '—')}")

            # ── 수급 요약 ──
            supply = r.get("supply", {})
            if supply:
                st.markdown("**수급 (당일 순매수)**")
                s1, s2, s3 = st.columns(3)
                foreign = supply.get("외국인", 0)
                inst    = supply.get("기관", 0)
                retail  = supply.get("개인", 0)
                s1.metric("외국인", f"{foreign:+,}억",
                          delta_color="normal" if foreign >= 0 else "inverse")
                s2.metric("기관",   f"{inst:+,}억",
                          delta_color="normal" if inst >= 0 else "inverse")
                s3.metric("개인",   f"{retail:+,}억",
                          delta_color="normal" if retail >= 0 else "inverse")

            # ── 수급 차트 (20일) ──
            with st.expander("📊 수급 차트 (최근 20일)", expanded=False):
                _render_supply_chart(r.get("ticker", ""), r.get("name", ""))

            # ── 리스크·손익 ──
            if r.get("risk"):
                st.error(f"⚠️ 리스크: {r['risk']}")

            col_a, col_b = st.columns(2)
            col_a.markdown(f"**목표가**: {r.get('target_price', '—')}")
            col_b.markdown(f"**손절가**: {r.get('stop_loss', '—')}")

            # ── 관련 뉴스 ──
            news = r.get("news", [])
            if news:
                with st.expander("📰 관련 뉴스", expanded=False):
                    for n in news[:5]:
                        st.caption(f"• {n}")

            st.caption("_AI 분석은 참고용입니다. 최종 매매 판단은 직접 하세요._")


def _render_supply_chart(ticker: str, name: str):
    """외국인·기관·개인 순매수 금액 막대 차트."""
    if not ticker:
        st.caption("티커 정보 없음")
        return

    try:
        from modules.screener_kr import get_supply_detail
        df = get_supply_detail(ticker, days=20)

        if df.empty:
            st.caption("수급 데이터를 가져올 수 없습니다.")
            return

        fig = go.Figure()

        colors = {"외국인": "#1f77b4", "기관": "#ff7f0e", "개인": "#2ca02c"}
        for col in ["외국인", "기관", "개인"]:
            if col in df.columns:
                fig.add_trace(go.Bar(
                    name=col,
                    x=df["date"].astype(str),
                    y=df[col] / 1e8,  # 억 단위
                    marker_color=colors.get(col, "gray"),
                ))

        fig.update_layout(
            title=f"{name} 수급 (억원)",
            barmode="group",
            height=300,
            margin=dict(l=20, r=20, t=40, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            yaxis_title="순매수 (억원)",
            xaxis_tickangle=-45,
        )
        st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.caption(f"차트 로드 오류: {e}")
