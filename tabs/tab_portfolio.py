"""
tabs/tab_portfolio.py
투자종목(실제 보유) 탭.
- 매수 등록 시 사유 강제 입력 (미입력 시 저장 불가 — 절대 규칙)
- 종목별 수익률 실시간 계산
- 주가 기간별 차트 조회
- 뉴스·매도 시점 AI 챗봇 실시간 소통
"""

import streamlit as st
from utils.db import get_portfolio, add_portfolio


def render():
    st.subheader("💼 투자종목")

    market_tab_kr, market_tab_us = st.tabs(["🇰🇷 국내", "🇺🇸 미국"])

    with market_tab_kr:
        _render_market_section("KR")

    with market_tab_us:
        _render_market_section("US")


def _render_market_section(market: str):
    label = "국내" if market == "KR" else "미국"

    # ── 매수 등록 ──
    with st.expander(f"➕ {label} 매수 등록", expanded=False):
        _render_buy_form(market)

    # ── 보유 종목 목록 ──
    try:
        portfolio = get_portfolio(market)
    except Exception:
        portfolio = []
        st.warning("Supabase 연결 후 이용 가능합니다.")

    if not portfolio:
        st.caption(f"보유 중인 {label} 종목이 없습니다.")
        return

    # 종목 선택
    options = {f"{r['name']} ({r['ticker']}) — 매수가 {r['buy_price']}": r for r in portfolio}
    selected_label = st.selectbox("종목 선택", list(options.keys()), key=f"pf_sel_{market}")
    selected = options[selected_label]

    st.divider()

    # ── 수익률 요약 ──
    _render_pnl_summary(selected, market)

    st.divider()

    # ── 차트 + AI 챗봇 ──
    chart_col, chat_col = st.columns([3, 2])

    with chart_col:
        _render_chart_section(selected, market)

    with chat_col:
        _render_ai_chat(selected, market)


def _render_buy_form(market: str):
    """매수 등록 폼. 매매 사유 미입력 시 저장 불가 — 절대 규칙."""
    with st.form(f"buy_form_{market}", clear_on_submit=True):
        c1, c2 = st.columns(2)
        ticker = c1.text_input(
            "티커", placeholder="005930" if market == "KR" else "NVDA",
            key=f"pf_ticker_{market}",
        )
        name = c2.text_input(
            "종목명", placeholder="삼성전자" if market == "KR" else "NVIDIA Corp",
            key=f"pf_name_{market}",
        )

        c3, c4, c5 = st.columns(3)
        buy_price = c3.number_input("매수가", min_value=0.0, format="%.2f", key=f"pf_price_{market}")
        buy_qty   = c4.number_input("수량", min_value=1, step=1, key=f"pf_qty_{market}")
        buy_date  = c5.date_input("매수일", key=f"pf_date_{market}")

        c6, c7 = st.columns(2)
        target_price = c6.number_input("목표가", min_value=0.0, format="%.2f", key=f"pf_target_{market}")
        stop_loss    = c7.number_input("손절가", min_value=0.0, format="%.2f", key=f"pf_stop_{market}")

        # 매매 사유 — 강제 입력 필드 (우회 UI 제안 금지)
        reason = st.text_area(
            "📝 매수 사유 *(필수)*",
            placeholder=(
                "예: 거래대금 급증 + AI반도체 테마 수혜 기대, "
                "5일선 위 우상향 차트에서 전고점 돌파 시도 중"
            ),
            height=100,
            key=f"pf_reason_{market}",
        )

        submitted = st.form_submit_button("매수 등록", type="primary", use_container_width=True)

        if submitted:
            if not reason.strip():
                st.error("⛔ 매수 사유는 필수입니다. 입력 후 다시 저장하세요.")
                return
            if not ticker or not name:
                st.error("티커와 종목명을 입력하세요.")
                return

            row = {
                "ticker":       ticker.upper(),
                "name":         name,
                "market":       market,
                "buy_price":    buy_price,
                "buy_qty":      int(buy_qty),
                "buy_date":     str(buy_date),
                "reason":       reason.strip(),
                "target_price": target_price if target_price > 0 else None,
                "stop_loss":    stop_loss if stop_loss > 0 else None,
            }
            add_portfolio(row)
            st.success(f"✅ {name} 매수 등록 완료")
            st.rerun()


def _render_pnl_summary(stock: dict, market: str):
    """현재가 조회 후 수익률 계산. 현재가 미조회 시 매수가만 표시."""
    buy_price = stock.get("buy_price", 0)
    buy_qty   = stock.get("buy_qty", 0)

    current_price = None
    try:
        from modules.chart_viewer import get_current_price
        current_price = get_current_price(stock["ticker"], market)
    except ImportError:
        pass

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("매수가", f"{buy_price:,.2f}")
    c2.metric("수량", f"{buy_qty:,}주")

    if current_price:
        pnl_pct = (current_price - buy_price) / buy_price * 100
        pnl_amt = (current_price - buy_price) * buy_qty
        c3.metric("현재가", f"{current_price:,.2f}", delta=f"{pnl_pct:+.2f}%")
        c4.metric("평가손익", f"{pnl_amt:+,.0f}")
    else:
        c3.metric("현재가", "조회 중...")
        c4.metric("매수 사유", stock.get("reason", "—")[:20] + "...")

    # 목표가·손절가 경고
    if current_price and stock.get("target_price"):
        if current_price >= stock["target_price"]:
            st.success("🎯 목표가 도달 — 매도 검토 시점입니다.")
    if current_price and stock.get("stop_loss"):
        if current_price <= stock["stop_loss"]:
            st.error("🚨 손절가 도달 — 매도 검토 시점입니다.")


def _render_chart_section(stock: dict, market: str):
    st.markdown(f"**{stock['name']} ({stock['ticker']}) 주가 차트**")

    period = st.radio(
        "기간",
        ["1주", "1개월", "3개월", "6개월", "1년"],
        horizontal=True,
        key=f"pf_period_{market}_{stock['ticker']}",
    )

    try:
        from modules.chart_viewer import render_price_chart
        render_price_chart(stock["ticker"], market, period)
    except ImportError:
        st.info(f"📈 {stock['name']} — {period} 차트 (chart_viewer 연동 후 표시)")
        st.caption("Phase 2에서 실제 차트가 연동됩니다.")


def _render_ai_chat(stock: dict, market: str):
    st.markdown(f"**AI 챗봇 — {stock['name']}**")
    st.caption("뉴스 시황, 매도 시점, 추가 매수 여부 등 자유롭게 물어보세요.")

    session_key = f"pf_chat_{market}_{stock['ticker']}"
    if session_key not in st.session_state:
        st.session_state[session_key] = []

    chat_container = st.container(height=280)
    with chat_container:
        for msg in st.session_state[session_key]:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    user_input = st.chat_input(
        f"{stock['name']} 관련 질문...",
        key=f"pf_input_{market}_{stock['ticker']}",
    )

    if user_input:
        st.session_state[session_key].append({"role": "user", "content": user_input})

        with st.spinner("AI 분석 중..."):
            response = _call_ai(user_input, stock, market)

        st.session_state[session_key].append({"role": "assistant", "content": response})
        st.rerun()


def _call_ai(question: str, stock: dict, market: str) -> str:
    try:
        from utils.clients import get_gemini
        client = get_gemini()

        buy_price    = stock.get("buy_price", 0)
        target_price = stock.get("target_price", "미설정")
        stop_loss    = stock.get("stop_loss", "미설정")
        reason       = stock.get("reason", "—")

        system_prompt = f"""당신은 주식 분석 AI 어시스턴트입니다.

현재 분석 대상:
- 종목: {stock['name']} ({stock['ticker']}) — {'국내(KRX)' if market == 'KR' else '미국(US)'}
- 매수가: {buy_price}
- 목표가: {target_price} / 손절가: {stop_loss}
- 매수 사유: {reason}

규칙:
- 매도 검토 시 반드시 리스크와 긍정 요인을 모두 제시하세요.
- 수익 보장 표현은 절대 사용하지 마세요.
- 최종 판단은 투자자가 직접 해야 함을 안내하세요.
"""

        response = client.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents=[
                {"role": "user", "parts": [{"text": system_prompt + "\n\n" + question}]}
            ],
        )
        return response.text

    except Exception as e:
        return f"AI 응답 오류: {e}"
