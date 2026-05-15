"""
modules/screener_kr.py
국내(KRX) 단기 트레이딩 종목 스크리닝.

데이터 소스:
- pykrx : 주가·거래대금·수급(외국인·기관·개인)
- Naver 금융 크롤링 : 뉴스
- Gemini API : 뉴스 감성 분석

선정 조건 (우선순위):
1. 거래대금 급증 — 당일 상위 top_n 이내
2. 재료·테마 존재 — 뉴스 감성점수 sentiment_min 이상
3. 차트 우상향 — 5일선 위, 전고점 근접
"""

from __future__ import annotations
import pandas as pd
import requests
from datetime import datetime, timedelta
import streamlit as st

try:
    from pykrx import stock as krx
except ImportError:
    krx = None


# ── 메인 스크리닝 함수 ────────────────────────────────────
def run_screening(top_n: int = 30, sentiment_min: int = 65) -> list[dict]:
    """
    당일 기준 거래대금 상위 종목 중 조건 충족 종목 반환.
    Returns: list of dict (UI 렌더링용)
    """
    if krx is None:
        st.error("pykrx 패키지가 필요합니다. requirements.txt에 pykrx 추가 후 재배포하세요.")
        return []

    today = _get_trading_date()

    with st.spinner("거래대금 상위 종목 조회 중..."):
        volume_df = _get_top_volume(today, top_n)

    if volume_df.empty:
        st.warning("거래대금 데이터를 가져오지 못했습니다.")
        return []

    results = []
    progress = st.progress(0, text="종목 분석 중...")

    for i, row in volume_df.iterrows():
        ticker = row["ticker"]
        name   = row["name"]
        progress.progress((list(volume_df.index).index(i) + 1) / len(volume_df),
                          text=f"분석 중: {name} ({ticker})")

        # 주가 데이터
        price_df = _get_price_data(ticker, today)
        if price_df is None or len(price_df) < 6:
            continue

        # 기술적 분석
        try:
            from modules.technical_kr import run_technical_analysis
            tech = run_technical_analysis(price_df)
        except Exception:
            tech = {"is_uptrend": False, "chart_status": "분석 불가", "signal": "관망"}

        if not tech.get("is_uptrend", False):
            continue

        # 수급 데이터
        supply = _get_supply_data(ticker, today)

        # 뉴스 감성
        sentiment_score, news_list = _get_news_sentiment(name)
        if sentiment_score < sentiment_min:
            continue

        # 목표가·손절가 계산
        current = price_df["close"].iloc[-1]
        target  = round(current * 1.08, -1)
        stop    = round(current * 0.96, -1)

        results.append({
            "ticker":        ticker,
            "name":          name,
            "score":         _calc_score(tech, sentiment_score, supply),
            "price":         f"{int(current):,}원",
            "volume_ratio":  row.get("volume_ratio", "—"),
            "trade_value":   row.get("trade_value", "—"),
            "sentiment":     sentiment_score,
            "theme":         _extract_theme(news_list),
            "chart_status":  tech.get("chart_status", "—"),
            "signal":        tech.get("signal", "관망"),
            "risk":          _build_risk(tech, supply),
            "target_price":  f"{int(target):,}원",
            "stop_loss":     f"{int(stop):,}원",
            "supply":        supply,      # 수급 raw 데이터 (차트용)
            "news":          news_list,
        })

    progress.empty()
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:5]  # TOP 5만 반환


# ── 거래대금 상위 조회 ────────────────────────────────────
def _get_top_volume(date: str, top_n: int) -> pd.DataFrame:
    try:
        df = krx.get_market_trading_value_by_ticker(date, market="KOSPI")
        df2 = krx.get_market_trading_value_by_ticker(date, market="KOSDAQ")
        df = pd.concat([df, df2])

        # 거래대금 컬럼명 확인 후 정렬
        val_col = [c for c in df.columns if "거래대금" in c or "거래" in c]
        if not val_col:
            return pd.DataFrame()

        df = df.sort_values(val_col[0], ascending=False).head(top_n).reset_index()
        df.columns = [c if c != "티커" else "ticker" for c in df.columns]

        # 종목명 추가
        name_map = krx.get_market_ticker_name(date)
        df["name"]  = df["ticker"].map(name_map).fillna("—")

        # 거래량 비율 (5일 평균 대비)
        df["trade_value"]  = df[val_col[0]].apply(lambda x: f"{x/1e8:.0f}억")
        df["volume_ratio"] = "—"

        return df[["ticker", "name", "trade_value", "volume_ratio"]]

    except Exception as e:
        st.warning(f"거래대금 조회 오류: {e}")
        return pd.DataFrame()


# ── 주가 OHLCV ────────────────────────────────────────────
def _get_price_data(ticker: str, date: str) -> pd.DataFrame | None:
    try:
        start = (datetime.strptime(date, "%Y%m%d") - timedelta(days=120)).strftime("%Y%m%d")
        df = krx.get_market_ohlcv(start, date, ticker)
        if df.empty:
            return None
        df = df.reset_index()
        df.columns = ["date", "open", "high", "low", "close", "volume"]
        return df
    except Exception:
        return None


# ── 수급 데이터 (외국인·기관·개인) ───────────────────────
def get_supply_detail(ticker: str, days: int = 20) -> pd.DataFrame:
    """
    외국인·기관·개인 순매수 금액 반환.
    tab_kr.py 에서 차트 렌더링에 직접 사용.
    """
    try:
        today = _get_trading_date()
        start = (datetime.strptime(today, "%Y%m%d") - timedelta(days=days*2)).strftime("%Y%m%d")
        df = krx.get_market_trading_value_by_date(start, today, ticker)
        if df.empty:
            return pd.DataFrame()
        df = df.reset_index()
        # 컬럼명 정리
        col_map = {}
        for c in df.columns:
            if "외국인" in c: col_map[c] = "외국인"
            elif "기관" in c:  col_map[c] = "기관"
            elif "개인" in c:  col_map[c] = "개인"
            elif "날짜" in c or "date" in c.lower(): col_map[c] = "date"
        df = df.rename(columns=col_map)
        keep = [c for c in ["date", "외국인", "기관", "개인"] if c in df.columns]
        return df[keep].tail(days)
    except Exception:
        return pd.DataFrame()


def _get_supply_data(ticker: str, date: str) -> dict:
    """스크리닝용 수급 요약."""
    try:
        start = (datetime.strptime(date, "%Y%m%d") - timedelta(days=10)).strftime("%Y%m%d")
        df = krx.get_market_trading_value_by_date(start, date, ticker)
        if df.empty:
            return {}
        last = df.iloc[-1]
        result = {}
        for c in df.columns:
            if "외국인" in c: result["외국인"] = int(last[c] / 1e8)
            elif "기관" in c:  result["기관"]   = int(last[c] / 1e8)
            elif "개인" in c:  result["개인"]   = int(last[c] / 1e8)
        return result
    except Exception:
        return {}


# ── 뉴스 감성 분석 ───────────────────────────────────────
def _get_news_sentiment(name: str) -> tuple[int, list[str]]:
    """Naver 뉴스 크롤링 + Gemini 감성 분석."""
    news_list = _fetch_naver_news(name)
    if not news_list:
        return 50, []

    try:
        from utils.clients import get_gemini
        client = get_gemini()
        prompt = f"""다음은 '{name}' 종목 관련 최신 뉴스 제목들입니다.
투자 관점에서 긍정/부정을 종합해 0~100점으로 점수를 매겨주세요.
숫자만 답하세요.

뉴스:
{chr(10).join(news_list[:5])}"""

        resp = client.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents=[{"role": "user", "parts": [{"text": prompt}]}],
        )
        score = int("".join(filter(str.isdigit, resp.text[:5])))
        score = max(0, min(100, score))
        return score, news_list

    except Exception:
        return 50, news_list


def _fetch_naver_news(name: str) -> list[str]:
    """Naver 금융 뉴스 제목 크롤링."""
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        url = f"https://search.naver.com/search.naver?where=news&query={name}+주식&sort=1"
        resp = requests.get(url, headers=headers, timeout=5)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")
        titles = [a.get_text(strip=True) for a in soup.select(".news_tit")[:10]]
        return titles
    except Exception:
        return []


# ── 테마 추출 ────────────────────────────────────────────
def _extract_theme(news_list: list[str]) -> str:
    keywords = ["AI", "반도체", "2차전지", "바이오", "전기차", "로봇", "방산", "수소", "태양광", "게임"]
    for kw in keywords:
        for n in news_list:
            if kw in n:
                return kw
    return "기타"


# ── AI 종합 점수 ─────────────────────────────────────────
def _calc_score(tech: dict, sentiment: int, supply: dict) -> int:
    score = 0
    score += 40 if tech.get("is_uptrend") else 0
    score += int(sentiment * 0.4)
    foreign = supply.get("외국인", 0)
    if foreign > 0:   score += 15
    elif foreign < 0: score -= 5
    return min(100, max(0, score))


# ── 리스크 문구 ──────────────────────────────────────────
def _build_risk(tech: dict, supply: dict) -> str:
    risks = []
    ind = tech.get("indicators", {})
    if ind.get("rsi", 50) > 70:
        risks.append("RSI 과매수 구간")
    if supply.get("외국인", 0) < -50:
        risks.append("외국인 순매도")
    if supply.get("기관", 0) < -50:
        risks.append("기관 순매도")
    if not risks:
        risks.append("단기 변동성 주의")
    return " · ".join(risks)


# ── 날짜 유틸 ────────────────────────────────────────────
def _get_trading_date() -> str:
    """오늘 또는 가장 최근 거래일 반환 (YYYYMMDD)."""
    today = datetime.now()
    if today.weekday() == 5:  # 토
        today -= timedelta(days=1)
    elif today.weekday() == 6:  # 일
        today -= timedelta(days=2)
    return today.strftime("%Y%m%d")
