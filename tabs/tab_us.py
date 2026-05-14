"""
tabs/tab_us.py
미국(US) 스윙 트레이딩 스크리닝 탭.
실제 스크리닝 로직은 modules/screener_us.py 에 있다.
기술적 분석 로직은 modules/technical_us.py 에 분리 — 수정 시 이 파일 무관.
"""

import streamlit as st


def render():
    st.subheader("🇺🇸 미국 스윙 트레이딩 — 종목 스크리닝")

    st.info(
        "**스크리닝 기준**\n"
        "1. 모멘텀 — 52주 신고가 근접 또는 상승 추세\n"
        "2. 실적 서프라이즈 — 어닝 비트 또는 가이던스 상향\n"
        "3. 섹터 강도 — 시장 대비 초과 상승 섹터 내 종목\n"
        "4. 뉴스 감성 70점 이상 + 수급 증가 추세\n\n"
        "_보유 기간 기준: 3일~3주 스윙_",
        icon="📋",
    )

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        sector = st.selectbox(
            "섹터 필터",
            ["전체", "Technology", "Energy", "Healthcare", "Financials",
             "Consumer Discretionary", "Industrials", "Materials"],
            key="us_sector",
        )
    with col2:
        sentiment_min = st.slider("감성점수 최소", 0, 100, 70, key="us_sentiment")
    with col3:
        run = st.button("🔍 지금 스크리닝", type="primary", key="us_run", use_container_width=True)

    st.divider()

    if run:
        with st.spinner("데이터 수집 및 AI 분석 중..."):
            try:
                from modules.screener_us import run_screening
                results = run_screening(sector=sector, sentiment_min=sentiment_min)
                _render_results(results)
            except ImportError:
                st.warning("screener_us 모듈 준비 중입니다. Phase 2에서 연동됩니다.")
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
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("현재가", r.get("price", "—"))
            c2.metric("52주 고점 대비", r.get("from_high", "—"))
            c3.metric("뉴스 감성점수", r.get("sentiment", "—"))
            c4.metric("섹터", r.get("sector", "—"))

            st.markdown(f"**모멘텀 근거**: {r.get('momentum_reason', '—')}")
            st.markdown(f"**실적 현황**: {r.get('earnings_status', '—')}")

            col_a, col_b, col_c = st.columns(3)
            col_a.markdown(f"**목표가**: {r.get('target_price', '—')}")
            col_b.markdown(f"**손절가**: {r.get('stop_loss', '—')}")
            col_c.markdown(f"**손익비**: {r.get('risk_reward', '—')}")

            if r.get("risk"):
                st.error(f"⚠️ 리스크: {r['risk']}")

            st.caption("_AI 분석은 참고용입니다. 최종 매매 판단은 직접 하세요._")


def _render_placeholder():
    sample = [
        {"name": "Sample Corp", "ticker": "SMPL", "score": 82,
         "price": "$245.30", "from_high": "-3.2%", "sentiment": 76, "sector": "Technology",
         "momentum_reason": "52주 신고가 근접, RSI 62로 과열 아님",
         "earnings_status": "최근 분기 EPS 예상 +12% 상회",
         "target_price": "$270", "stop_loss": "$228", "risk_reward": "1:2.1",
         "risk": "고PER 밸류에이션 부담, 달러 강세 리스크"},
    ]
    _render_results(sample)
