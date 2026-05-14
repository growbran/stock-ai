"""
app.py — AI 주식 분석 머신 메인 진입점

이 파일은 탭 라우팅만 담당한다.
비즈니스 로직은 tabs/ 와 modules/ 에만 존재한다.

실행: streamlit run app.py
"""

import streamlit as st

# ── 페이지 설정 ───────────────────────────────────────────
st.set_page_config(
    page_title="AI 주식 분석 머신",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 전역 스타일 ───────────────────────────────────────────
st.markdown("""
<style>
    .stApp { background: #F8F9FA; }
    .main .block-container {
        background: white;
        border-radius: 16px;
        padding: 2rem;
        max-width: 1600px !important;
        margin: 0.8rem auto !important;
        box-shadow: 0 4px 24px rgba(0,0,0,0.07);
    }
    section[data-testid="stSidebar"] { background: #F1F3F5; }
    .stChatMessage { border-radius: 12px; margin: 0.4rem 0; }
    footer { visibility: hidden; }
    .stMarkdown p, .stMarkdown li { font-size: 16px !important; line-height: 1.75 !important; }
    .stMarkdown h3 { font-size: 22px !important; border-bottom: 2px solid #1A73E8; padding-bottom: 6px; }
</style>
""", unsafe_allow_html=True)


# ── 사이드바 ──────────────────────────────────────────────
def render_sidebar():
    with st.sidebar:
        st.markdown("## 📈 AI 주식 분석 머신")
        st.caption("v2.0 — AI 분석·추천 → 사람 판단 → 직접 매매")
        st.divider()

        st.markdown("**운용 원칙**")
        st.info(
            "- AI는 분석·추천만\n"
            "- 최종 판단은 직접\n"
            "- 자동 체결 없음\n"
            "- 매매 사유 필수 입력",
            icon="🛡️",
        )
        st.divider()
        st.caption("기술적 분석 기준 변경 시\n`modules/technical_kr.py`\n`modules/technical_us.py`\n두 파일만 수정하세요.")


# ── 탭 라우팅 ─────────────────────────────────────────────
def main():
    render_sidebar()

    tabs = st.tabs([
        "🇰🇷 국내 스크리닝",
        "🇺🇸 미국 스크리닝",
        "⭐ 관심종목",
        "💼 투자종목",
        "📋 추천 이력",
    ])

    with tabs[0]:
        from tabs.tab_kr import render as render_kr
        render_kr()

    with tabs[1]:
        from tabs.tab_us import render as render_us
        render_us()

    with tabs[2]:
        from tabs.tab_watchlist import render as render_watchlist
        render_watchlist()

    with tabs[3]:
        from tabs.tab_portfolio import render as render_portfolio
        render_portfolio()

    with tabs[4]:
        from tabs.tab_history import render as render_history
        render_history()


if __name__ == "__main__":
    main()
