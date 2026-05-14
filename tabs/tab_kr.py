"""
tabs/tab_kr.py
국내(KRX) 단기 트레이딩 스크리닝 탭.
실제 스크리닝 로직은 modules/screener_kr.py 에 있다.
기술적 분석 로직은 modules/technical_kr.py 에 분리 — 수정 시 이 파일 무관.
"""

import streamlit as st


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
        with st.spinner("데이터 수집 및 AI 분석 중..."):
            try:
                from modules.screener_kr import run_screening
                results = run_screening(top_n=top_n, sentiment_min=sentiment_min)
                _render_results(results)
            except ImportError:
                st.warning("screener_kr 모듈 준비 중입니다. Phase 2에서 연동됩니다.")
                _render_placeholder()
    else:
        st.caption("조건을 설정하고 '지금 스크리닝' 버튼을 누르세요.")


def _render_results(results: list[dict]):
    if not results:
        st.warning("현재 조건에 맞는 종목이 없습니다.")
        return

    st.success(f"조건 충족 종목 {len(results)}개")

    for i, r in enumerate(results, 1):
        with st.expander(
            f"**{i}. {r.get('name','—')} ({r.get('ticker','—')})** — AI 점수 {r.get('score',0)}점",
            expanded=(i == 1),
        ):
            c1, c2, c3 = st.columns(3)
            c1.metric("거래대금 증가율", r.get("volume_ratio", "—"))
            c2.metric("뉴스 감성점수", r.get("sentiment", "—"))
            c3.metric("현재가", r.get("price", "—"))

            st.markdown(f"**테마·재료**: {r.get('theme', '—')}")
            st.markdown(f"**차트 상태**: {r.get('chart_status', '—')}")

            if r.get("risk"):
                st.error(f"⚠️ 리스크: {r['risk']}")

            col_a, col_b = st.columns(2)
            col_a.markdown(f"**목표가**: {r.get('target_price', '—')}")
            col_b.markdown(f"**손절가**: {r.get('stop_loss', '—')}")

            st.caption("_AI 분석은 참고용입니다. 최종 매매 판단은 직접 하세요._")


def _render_placeholder():
    """스크리닝 모듈 연동 전 UI 구조 확인용 플레이스홀더."""
    sample = [
        {"name": "샘플종목A", "ticker": "000000", "score": 78,
         "volume_ratio": "+42%", "sentiment": 74, "price": "12,500원",
         "theme": "AI반도체", "chart_status": "5일선 위, 전고점 돌파 중",
         "risk": "단기 과열 가능성", "target_price": "14,000원", "stop_loss": "11,500원"},
    ]
    _render_results(sample)
