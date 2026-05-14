"""
modules/technical_kr.py
국내(KRX) 기술적 분석 모듈.

★ 이 파일만 수정하면 됩니다 — app.py, 탭 파일 수정 불필요.
★ 함수 시그니처(run_technical_analysis)는 유지하고 내부 로직만 교체하세요.

현재: 기본 지표 뼈대 (5일선·거래량 비율·전고점 돌파)
추후: 세밀한 매매 기준으로 교체 예정
"""

from __future__ import annotations
import pandas as pd


# ── 공개 인터페이스 (시그니처 고정) ─────────────────────────
def run_technical_analysis(df: pd.DataFrame) -> dict:
    """
    OHLCV DataFrame을 받아 기술적 분석 결과를 반환한다.

    Parameters
    ----------
    df : pd.DataFrame
        columns: date, open, high, low, close, volume (일봉 기준)

    Returns
    -------
    dict
        {
            "chart_status": str,     # 차트 상태 요약 (UI 표시용)
            "is_uptrend": bool,      # 우상향 여부 (스크리닝 통과 기준)
            "signal": str,           # "매수검토" | "관망" | "매도검토"
            "indicators": dict,      # 상세 지표값
            "note": str,             # 추가 설명 (선택)
        }
    """
    if df is None or df.empty:
        return _empty_result("데이터 없음")

    df = df.copy().sort_values("date").reset_index(drop=True)

    try:
        indicators = _calc_indicators(df)
        signal, status = _judge_signal(indicators)

        return {
            "chart_status": status,
            "is_uptrend":   indicators.get("above_ma5", False),
            "signal":       signal,
            "indicators":   indicators,
            "note":         "technical_kr.py — 교체 전 기본 버전",
        }

    except Exception as e:
        return _empty_result(f"분석 오류: {e}")


# ── 지표 계산 (내부 함수) ────────────────────────────────────
def _calc_indicators(df: pd.DataFrame) -> dict:
    close  = df["close"]
    volume = df["volume"]

    # 이동평균
    ma5  = close.rolling(5).mean()
    ma20 = close.rolling(20).mean()

    # 거래량 비율 (최근 5일 평균 / 20일 평균)
    vol_ratio = volume.rolling(5).mean().iloc[-1] / volume.rolling(20).mean().iloc[-1]

    # 전고점 (52주 / 250일 기준)
    high_250 = df["high"].rolling(min(250, len(df))).max().iloc[-1]
    current  = close.iloc[-1]
    from_high_pct = (current - high_250) / high_250 * 100

    return {
        "current_price":  current,
        "ma5":            ma5.iloc[-1],
        "ma20":           ma20.iloc[-1],
        "above_ma5":      current > ma5.iloc[-1],
        "above_ma20":     current > ma20.iloc[-1],
        "vol_ratio":      round(vol_ratio, 2),     # 1.0 이상 = 거래량 증가
        "from_high_pct":  round(from_high_pct, 2), # 음수 = 고점 대비 하락률
        "near_breakout":  from_high_pct >= -5,     # 전고점 5% 이내
    }


def _judge_signal(ind: dict) -> tuple[str, str]:
    """
    신호 판단 로직.
    ★ 추후 세밀한 매매 기준으로 이 함수를 교체하면 됩니다.
    """
    above_ma5    = ind.get("above_ma5", False)
    vol_ratio    = ind.get("vol_ratio", 1.0)
    near_breakout = ind.get("near_breakout", False)

    if above_ma5 and vol_ratio >= 1.3 and near_breakout:
        signal = "매수검토"
        status = f"5일선 위 · 거래량 {vol_ratio:.1f}배 · 전고점 근접 — 매수 검토 구간"
    elif above_ma5 and vol_ratio >= 1.1:
        signal = "관망"
        status = f"5일선 위 · 거래량 소폭 증가 — 추가 확인 필요"
    else:
        signal = "관망"
        status = "5일선 이탈 또는 거래량 부족 — 진입 조건 미충족"

    return signal, status


def _empty_result(reason: str) -> dict:
    return {
        "chart_status": reason,
        "is_uptrend":   False,
        "signal":       "관망",
        "indicators":   {},
        "note":         reason,
    }
