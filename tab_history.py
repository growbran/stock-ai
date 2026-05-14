"""
tabs/tab_history.py
AI 추천 이력 탭.
추천 vs 실제 결과를 누적해 적중률을 검증한다.
이 데이터가 Zone C(자동 체결) 도입 여부 판단의 근거가 된다.
"""

import streamlit as st
from utils.db import get_recommendations


def render():
    st.subheader("📋 AI 추천 이력 — 신뢰도 검증")

    st.info(
        "AI 추천의 실제 적중률을 3~6개월 누적합니다.\n"
        "이 데이터를 기반으로 Zone C(자동 체결) 도입 여부를 결정합니다.",
        icon="📊",
    )

    try:
        records = get_recommendations(limit=200)
    except Exception:
        records = []
        st.warning("Supabase 연결 후 이용 가능합니다.")

    # ── 요약 지표 ──
    total   = len(records)
    hit     = sum(1 for r in records if r.get("is_hit") is True)
    miss    = sum(1 for r in records if r.get("is_hit") is False)
    pending = total - hit - miss

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("총 추천", f"{total}건")
    c2.metric("적중", f"{hit}건", delta=f"{hit/total*100:.1f}%" if total else "—")
    c3.metric("미적중", f"{miss}건")
    c4.metric("결과 대기", f"{pending}건")

    if total > 0:
        hit_rate = hit / (hit + miss) * 100 if (hit + miss) > 0 else 0
        st.progress(int(hit_rate) / 100, text=f"적중률 {hit_rate:.1f}% (결과 확인된 건 기준)")

    st.divider()

    if not records:
        st.caption("아직 추천 이력이 없습니다. 스크리닝 후 추천이 기록됩니다.")
        _render_zone_c_status(0)
        return

    # ── 이력 테이블 ──
    import pandas as pd

    df = pd.DataFrame(records)
    display_cols = {
        "rec_date":       "추천일",
        "ticker":         "티커",
        "market":         "시장",
        "rec_type":       "추천유형",
        "reason_summary": "AI 근거 요약",
        "return_1w":      "1주 수익률",
        "return_1m":      "1개월 수익률",
        "is_hit":         "적중",
    }
    show_cols = [c for c in display_cols if c in df.columns]
    df_display = df[show_cols].rename(columns=display_cols)

    # 적중 여부 표시 변환
    if "적중" in df_display.columns:
        df_display["적중"] = df_display["적중"].map(
            {True: "✅", False: "❌", None: "⏳"}
        )

    st.dataframe(df_display, use_container_width=True, hide_index=True, height=320)

    _render_zone_c_status(total)


def _render_zone_c_status(total: int):
    """Zone C 도입 가능 여부를 누적 이력 기준으로 표시."""
    st.divider()
    st.markdown("#### Zone C (자동 체결) 도입 가능 여부")

    needed = 50  # 최소 추천 건수 기준 (조정 가능)
    months_needed = 3

    if total == 0:
        st.error(
            f"⛔ 도입 불가 — 추천 이력 0건\n\n"
            f"최소 {needed}건 이상, {months_needed}개월 이상 누적 후 검토 가능합니다."
        )
    elif total < needed:
        st.warning(
            f"⚠️ 도입 검토 불가 — 추천 이력 {total}건 ({needed}건 필요)\n\n"
            f"이력이 충분히 쌓인 후 적중률과 기간을 함께 검토하세요."
        )
    else:
        st.info(
            f"✅ 이력 {total}건 누적 완료 — 적중률과 보유 기간({months_needed}개월)을 "
            f"확인 후 Zone C 도입 여부를 직접 판단하세요."
        )
