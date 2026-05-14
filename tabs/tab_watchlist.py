"""
tabs/tab_watchlist.py
관심종목 탭.
- 국내/미국 관심종목 등록·삭제
- 종목별 주가 기간별 차트 조회
- 해당 종목 뉴스 시황 + AI 챗봇 실시간 소통
"""

import streamlit as st
from utils.db import get_watchlist, add_watchlist, remove_watchlist


def render():
    st.subheader("⭐ 관심종목")

    market_tab_kr, market_tab_us = st.tabs(["🇰🇷 국내", "🇺🇸 미국"])

    with market_tab_kr:
        _render_market_section("KR")

    with market_tab_us:
        _render_market_section("US")


def _render_market_section(market: str):
    label = "국내" if market == "KR" else "미국"
    currency = "원" if market == "KR" else "USD"

    # ── 종목 추가 ──
    with st.expander(f"➕ {label} 관심종목 추가", expanded=False):
        c1, c2, c3 = st.columns([2, 3, 1])
        ticker_input = c1.text_input(
            "티커", placeholder="예: 005930" if market == "KR" else "예: NVDA",
            key=f"wl_ticker_{market}",
        )
        name_input = c2.text_input(
            "종목명", placeholder="예: 삼성전자" if market == "KR" else "예: NVIDIA Corp",
            key=f"wl_name_{market}",
        )
        if c3.button("추가", key=f"wl_add_{market}", use_container_width=True):
            if ticker_input and name_input:
                add_watchlist(ticker_input.upper(), name_input, market)
                st.success(f"{name_input} 추가됨")
                st.rerun()
            else:
                st.error("티커와 종목명을 입력하세요.")

    # ── 관심종목 목록 ──
    try:
        watchlist = get_watchlist(market)
    except Exception:
        watchlist = []
        st.warning("Supabase 연결 후 이용 가능합니다.")

    if not watchlist:
        st.caption(f"등록된 {label} 관심종목이 없습니다.")
        return

    # 종목 선택
    options = {f"{r['name']} ({r['ticker']})": r for r in watchlist}
    selected_label = st.selectbox(
        "종목 선택", list(options.keys()), key=f"wl_sel_{market}"
    )
    selected = options[selected_label]

    col_del, _ = st.columns([1, 5])
    if col_del.button("🗑 관심종목 삭제", key=f"wl_del_{market}"):
        remove_watchlist(selected["ticker"])
        st.success("삭제됨")
        st.rerun()

    st.divider()

    # ── 차트 + AI 챗봇 ──
    chart_col, chat_col = st.columns([3, 2])

    with chart_col:
        _render_chart_section(selected, market, currency)

    with chat_col:
        _render_ai_chat(selected, market)


def _render_chart_section(stock: dict, market: str, currency: str):
    st.markdown(f"**{stock['name']} ({stock['ticker']}) 주가 차트**")

    period = st.radio(
        "기간",
        ["1주", "1개월", "3개월", "6개월", "1년"],
        horizontal=True,
        key=f"chart_period_{market}_{stock['ticker']}",
    )

    try:
        from modules.chart_viewer import render_price_chart
        render_price_chart(stock["ticker"], market, period)
    except ImportError:
        # 모듈 연동 전 플레이스홀더
        st.info(f"📈 {stock['name']} — {period} 차트 (chart_viewer 연동 후 표시)")
        st.caption("Phase 2에서 실제 차트가 연동됩니다.")


def _render_ai_chat(stock: dict, market: str):
    st.markdown(f"**AI 챗봇 — {stock['name']}**")
    st.caption("뉴스 시황, 매수·매도 시점 등 자유롭게 물어보세요.")

    session_key = f"wl_chat_{market}_{stock['ticker']}"
    if session_key not in st.session_state:
        st.session_state[session_key] = []

    # 대화 출력
    chat_container = st.container(height=320)
    with chat_container:
        for msg in st.session_state[session_key]:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    # 입력창
    user_input = st.chat_input(
        f"{stock['name']} 관련 질문...",
        key=f"wl_input_{market}_{stock['ticker']}",
    )

    if user_input:
        st.session_state[session_key].append({"role": "user", "content": user_input})

        with st.spinner("AI 분석 중..."):
            response = _call_ai(user_input, stock, market)

        st.session_state[session_key].append({"role": "assistant", "content": response})
        st.rerun()


def _call_ai(question: str, stock: dict, market: str) -> str:
    """Gemini에 종목 컨텍스트를 포함해 질문한다."""
    try:
        from utils.clients import get_gemini
        client = get_gemini()

        system_prompt = f"""당신은 주식 분석 AI 어시스턴트입니다.
현재 분석 대상 종목: {stock['name']} ({stock['ticker']}) — {'국내(KRX)' if market == 'KR' else '미국(US)'}

규칙:
- 매매 추천 시 반드시 리스크 요인을 함께 명시하세요.
- AI 분석은 참고용이며, 최종 판단은 투자자가 직접 해야 함을 안내하세요.
- 수익 보장 표현을 절대 사용하지 마세요.
"""

        response = client.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents=[
                {"role": "user", "parts": [{"text": system_prompt + "\n\n" + question}]}
            ],
        )
        return response.text

    except Exception as e:
        return f"AI 응답 오류: {e}\n\nGemini API 연결을 확인하세요."
