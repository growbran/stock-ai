"""
modules/technical_us.py
미국(US) 스윙 트레이딩 기술적 분석 모듈.

★ 이 파일만 수정하면 됩니다 — app.py, 탭 파일 수정 불필요.
★ 함수 시그니처(run_technical_analysis)는 유지하고 내부 로직만 교체하세요.

현재: 스윙 트레이딩 기본 지표 뼈대 (모멘텀·RSI·52주 고점)
추후: 세밀한 스윙 매매 기준으로 교체 예정
"""

from __future__ import annotations
import pandas as pd


# ── 공개 인터페이스 (시그니처 고정) ─────────────────────────
def run_technical_analysis(df: pd.DataFrame) -> dict:
    """
    OHLCV DataFrame을 받아 스윙 트레이딩 기술적 분석 결과를 반환한다.

    Parameters
    ----------
    df : pd.DataFrame
        columns: date, open, high, low, close, volume (일봉 기준)

    Returns
    -------
    dict
        {
            "chart_status": str,
            "is_swing_candidate": bool,  # 스윙 진입 후보 여부
            "signal": str,               # "매수검토" | "관망" | "매도검토"
            "swing_setup": str,          # 스윙 셋업 유형
            "indicators": dict,
            "note": str,
        }
    """
    if df is None or df.empty:
        return _empty_result("데이터 없음")

    df = df.copy().sort_values("date").reset_index(drop=True)

    try:
        indicators = _calc_indicators(df)
        signal, status, setup = _judge_signal(indicators)

        return {
            "chart_status":       status,
            "is_swing_candidate": signal == "매수검토",
            "signal":             signal,
            "swing_setup":        setup,
            "indicators":         indicators,
            "note":               "technical_us.py — 교체 전 기본 버전",
        }

    except Exception as e:
        return _empty_result(f"분석 오류: {e}")


# ── 지표 계산 ───────────────────────────────────────────────
def _calc_indicators(df: pd.DataFrame) -> dict:
    close  = df["close"]
    volume = df["volume"]

    # 이동평균
    ma10 = close.rolling(10).mean()
    ma50 = close.rolling(50).mean()

    # RSI (14일)
    rsi = _calc_rsi(close, 14)

    # 52주 고점 대비
    high_252 = df["high"].rolling(min(252, len(df))).max().iloc[-1]
    current  = close.iloc[-1]
    from_high_pct = (current - high_252) / high_252 * 100

    # 거래량 비율
    vol_ratio = volume.rolling(5).mean().iloc[-1] / volume.rolling(20).mean().iloc[-1]

    # 모멘텀 (20일 수익률)
    momentum_20d = (current / close.iloc[-21] - 1) * 100 if len(close) > 21 else 0

    return {
        "current_price":  current,
        "ma10":           ma10.iloc[-1],
        "ma50":           ma50.iloc[-1],
        "above_ma10":     current > ma10.iloc[-1],
        "above_ma50":     current > ma50.iloc[-1],
        "rsi":            round(rsi, 1),
        "from_high_pct":  round(from_high_pct, 2),
        "near_52w_high":  from_high_pct >= -8,    # 52주 고점 8% 이내
        "vol_ratio":      round(vol_ratio, 2),
        "momentum_20d":   round(momentum_20d, 2), # % 단위
    }


def _calc_rsi(close: pd.Series, period: int = 14) -> float:
    delta  = close.diff()
    gain   = delta.clip(lower=0).rolling(period).mean()
    loss   = (-delta.clip(upper=0)).rolling(period).mean()
    rs     = gain / loss
    rsi    = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1]) if not rsi.empty else 50.0


def _judge_signal(ind: dict) -> tuple[str, str, str]:
    """
    스윙 신호 판단.
    ★ 추후 세밀한 스윙 매매 기준으로 이 함수를 교체하면 됩니다.
    """
    above_ma10  = ind.get("above_ma10", False)
    above_ma50  = ind.get("above_ma50", False)
    rsi         = ind.get("rsi", 50)
    near_high   = ind.get("near_52w_high", False)
    momentum    = ind.get("momentum_20d", 0)
    vol_ratio   = ind.get("vol_ratio", 1.0)

    # RSI 과매수 영역 제외 (70 이상)
    rsi_ok = 40 <= rsi <= 70

    if above_ma10 and above_ma50 and rsi_ok and near_high and momentum > 5:
        signal = "매수검토"
        setup  = "52주 신고가 돌파 모멘텀"
        status = f"MA10·MA50 위 · RSI {rsi} · 52주 고점 근접 · 20일 수익률 {momentum:.1f}%"
    elif above_ma10 and rsi_ok and vol_ratio >= 1.2:
        signal = "관망"
        setup  = "MA 정배열 확인 중"
        status = f"MA10 위 · RSI {rsi} · 추가 조건 확인 필요"
    else:
        signal = "관망"
        setup  = "진입 조건 미충족"
        status = f"MA 미정배열 또는 RSI 부적합 ({rsi})"

    return signal, status, setup


def _empty_result(reason: str) -> dict:
    return {
        "chart_status":       reason,
        "is_swing_candidate": False,
        "signal":             "관망",
        "swing_setup":        "—",
        "indicators":         {},
        "note":               reason,
    }
