"""
modules/screener_kr.py
국내(KRX) 단기 트레이딩 종목 스크리닝 — pykrx 기반

KIS API는 유동 IP 환경(Streamlit Cloud)에서 차단되므로
pykrx(KRX 공식 데이터 무료)를 사용합니다.
KIS API는 나중에 실제 주문 실행 기능에만 사용합니다.

선정 조건:
1. 거래대금 상위 top_n — 시총 1,000억 이상 + 주가 1,000원 이상 + 양봉
2. 외국인 순매수 > 0 AND 기관합계 순매수 > 0 (양매수)
3. 20일선 우상향 + 현재가 20일선 위
4. 뉴스 감성점수 sentiment_min 이상
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


# ── 메인 스크리닝 ─────────────────────────────────────────
def run_screening(top_n: int = 30, sentiment_min: int = 65) -> list[dict]:
    if krx is None:
        st.error("pykrx 패키지가 필요합니다.")
        return []

    date = _get_trading_date()

    with st.spinner("거래대금 상위 종목 조회 중..."):
        candidates = _get_top_by_trade_value(date, top_n)

    if candidates.empty:
        st.warning("거래대금 데이터를 가져오지 못했습니다.")
        return []

    # 외인·기관 수급 (당일 기준)
    with st.spinner("수급 데이터 조회 중..."):
        foreign_df = _get_net_purchase(date, "외국인")
        inst_df    = _get_net_purchase(date, "기관합계")

    results = []
    progress = st.progress(0, text="조건 필터링 중...")
    total = len(candidates)

    for idx, (ticker, row) in enumerate(candidates.iterrows()):
        name = row.get("name", ticker)
        progress.progress((idx + 1) / total, text=f"분석 중: {name}")

        # 1. 기본 필터 — 시총·주가·양봉
        if not _pass_basic_filter(row):
            continue

        # 2. 외인·기관 양매수 필터
        supply = _get_supply_summary(ticker, foreign_df, inst_df)
        if not (supply["외국인"] > 0 and supply["기관"] > 0):
            continue

        # 3. 이동평균 필터
        price_df = _get_ohlcv(ticker, date)
        if price_df is None or len(price_df) < 21:
            continue

        try:
            from modules.technical_kr import run_technical_analysis
            tech = run_technical_analysis(price_df)
        except Exception:
            tech = {"is_uptrend": False, "chart_status": "분석 불가",
                    "signal": "관망", "indicators": {}}

        if not tech.get("is_uptrend", False):
            continue

        # 4. 뉴스 감성
        sentiment_score, news_list = _get_news_sentiment(name)
        if sentiment_score < sentiment_min:
            continue

        current = float(row.get("종가", 0))
        target  = round(current * 1.08, -1)
        stop    = round(current * 0.96, -1)

        results.append({
            "ticker":       ticker,
            "name":         name,
            "score":        _calc_score(tech, sentiment_score, supply),
            "price":        f"{int(current):,}원",
            "change_rate":  f"{row.get('등락률', 0):+.2f}%" if "등락률" in row else "—",
            "trade_value":  f"{int(row.get('거래대금', 0)/1e8):.0f}억",
            "volume_ratio": _calc_volume_ratio(price_df),
            "sentiment":    sentiment_score,
            "theme":        _extract_theme(news_list),
            "chart_status": tech.get("chart_status", "—"),
            "signal":       tech.get("signal", "관망"),
            "risk":         _build_risk(tech, supply),
            "target_price": f"{int(target):,}원",
            "stop_loss":    f"{int(stop):,}원",
            "supply":       supply,
            "news":         news_list,
        })

    progress.empty()

    if results:
        _save_to_supabase(results)

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:5]


# ── 거래대금 상위 종목 ────────────────────────────────────
def _get_top_by_trade_value(date: str, top_n: int) -> pd.DataFrame:
    try:
        rows = []
        name_map = krx.get_market_ticker_name(date)

        for market in ["KOSPI", "KOSDAQ"]:
            df = krx.get_market_cap_by_ticker(date, market=market)
            if df is None or df.empty:
                continue
            df["name"]   = df.index.map(name_map)
            df["market"] = market
            rows.append(df)

        if not rows:
            return pd.DataFrame()

        combined = pd.concat(rows)

        # 거래대금 컬럼 확인
        if "거래대금" not in combined.columns:
            st.warning(f"거래대금 컬럼 없음. 컬럼 목록: {combined.columns.tolist()}")
            return pd.DataFrame()

        combined = combined.sort_values("거래대금", ascending=False).head(top_n)
        return combined

    except Exception as e:
        st.warning(f"거래대금 조회 오류: {e}")
        return pd.DataFrame()


# ── 기본 필터 ─────────────────────────────────────────────
def _pass_basic_filter(row: pd.Series) -> bool:
    """시총 1,000억↑ + 주가 1,000원↑ + 양봉."""
    try:
        mkt_cap = float(row.get("시가총액", 0))
        price   = float(row.get("종가", 0))
        open_p  = float(row.get("시가", 0)) if "시가" in row else price
        return mkt_cap >= 100_000_000_000 and price >= 1000 and price >= open_p
    except Exception:
        return False


# ── OHLCV ─────────────────────────────────────────────────
def _get_ohlcv(ticker: str, date: str) -> pd.DataFrame | None:
    try:
        start = (datetime.strptime(date, "%Y%m%d") - timedelta(days=120)).strftime("%Y%m%d")
        df = krx.get_market_ohlcv(start, date, ticker)
        if df is None or df.empty:
            return None
        df = df.reset_index()
        # 컬럼명 통일
        col_map = {}
        for c in df.columns:
            if "날짜" in c or "date" in c.lower(): col_map[c] = "date"
            elif "시가" in c:  col_map[c] = "open"
            elif "고가" in c:  col_map[c] = "high"
            elif "저가" in c:  col_map[c] = "low"
            elif "종가" in c:  col_map[c] = "close"
            elif "거래량" in c: col_map[c] = "volume"
        df = df.rename(columns=col_map)
        return df
    except Exception:
        return None


# ── 수급 (외인·기관) ──────────────────────────────────────
def _get_net_purchase(date: str, investor: str) -> pd.DataFrame:
    try:
        df_k = krx.get_market_net_purchases_of_equities_by_ticker(
            date, date, market="KOSPI", investor=investor
        )
        df_q = krx.get_market_net_purchases_of_equities_by_ticker(
            date, date, market="KOSDAQ", investor=investor
        )
        return pd.concat([df_k, df_q])
    except Exception:
        return pd.DataFrame()


def _get_supply_summary(ticker: str, foreign_df: pd.DataFrame,
                         inst_df: pd.DataFrame) -> dict:
    try:
        foreign_net = 0
        inst_net    = 0

        if not foreign_df.empty and ticker in foreign_df.index:
            col = [c for c in foreign_df.columns if "순매수" in c or "수량" in c]
            if col:
                foreign_net = int(foreign_df.loc[ticker, col[0]])

        if not inst_df.empty and ticker in inst_df.index:
            col = [c for c in inst_df.columns if "순매수" in c or "수량" in c]
            if col:
                inst_net = int(inst_df.loc[ticker, col[0]])

        return {"외국인": foreign_net, "기관": inst_net, "개인": 0}
    except Exception:
        return {"외국인": 0, "기관": 0, "개인": 0}


def get_supply_detail(ticker: str, days: int = 20) -> pd.DataFrame:
    """수급 차트용 날짜별 데이터 (tab_kr.py에서 사용)."""
    try:
        today = _get_trading_date()
        start = (datetime.strptime(today, "%Y%m%d") - timedelta(days=days * 2)).strftime("%Y%m%d")

        df = krx.get_market_trading_value_by_date(start, today, ticker)
        if df is None or df.empty:
            return pd.DataFrame()

        df = df.reset_index()
        col_map = {}
        for c in df.columns:
            if "외국인" in c:                         col_map[c] = "외국인"
            elif "기관" in c:                         col_map[c] = "기관"
            elif "개인" in c:                         col_map[c] = "개인"
            elif "날짜" in c or "date" in c.lower():  col_map[c] = "date"
        df = df.rename(columns=col_map)
        keep = [c for c in ["date", "외국인", "기관", "개인"] if c in df.columns]
        return df[keep].tail(days)
    except Exception:
        return pd.DataFrame()


# ── 뉴스 감성 ────────────────────────────────────────────
def _get_news_sentiment(name: str) -> tuple[int, list[str]]:
    news_list = _fetch_naver_news(name)
    if not news_list:
        return 50, []
    try:
        from utils.clients import get_gemini
        client = get_gemini()
        prompt = (
            f"'{name}' 종목 관련 뉴스 제목들을 투자 관점에서 0~100점으로 "
            f"점수만 숫자로 답하세요.\n\n" + "\n".join(news_list[:5])
        )
        resp = client.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents=[{"role": "user", "parts": [{"text": prompt}]}],
        )
        score = int("".join(filter(str.isdigit, resp.text[:5])))
        return max(0, min(100, score)), news_list
    except Exception:
        return 50, news_list


def _fetch_naver_news(name: str) -> list[str]:
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        url = f"https://search.naver.com/search.naver?where=news&query={name}+주식&sort=1"
        resp = requests.get(url, headers=headers, timeout=5)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")
        return [a.get_text(strip=True) for a in soup.select(".news_tit")[:10]]
    except Exception:
        return []


# ── Supabase 저장 ─────────────────────────────────────────
def _save_to_supabase(results: list[dict]):
    try:
        from utils.db import save_recommendation
        from datetime import timezone
        for r in results:
            save_recommendation({
                "ticker":         r["ticker"],
                "market":         "KR",
                "rec_type":       "주목",
                "reason_summary": f"거래대금:{r['trade_value']} | 수급:{r['supply']} | 테마:{r['theme']}",
                "rec_date":       datetime.now(timezone.utc).isoformat(),
            })
    except Exception:
        pass


# ── 유틸 ────────────────────────────────────────────────
def _calc_volume_ratio(price_df: pd.DataFrame) -> str:
    try:
        vol = price_df["volume"]
        ratio = vol.iloc[-5:].mean() / vol.iloc[-20:].mean()
        return f"+{(ratio-1)*100:.0f}%" if ratio > 1 else f"{(ratio-1)*100:.0f}%"
    except Exception:
        return "—"


def _extract_theme(news_list: list[str]) -> str:
    keywords = ["AI", "반도체", "2차전지", "바이오", "전기차",
                "로봇", "방산", "수소", "태양광", "게임"]
    for kw in keywords:
        for n in news_list:
            if kw in n:
                return kw
    return "기타"


def _calc_score(tech: dict, sentiment: int, supply: dict) -> int:
    score = 40 if tech.get("is_uptrend") else 0
    score += int(sentiment * 0.3)
    score += 20 if supply.get("외국인", 0) > 0 else 0
    score += 10 if supply.get("기관", 0) > 0 else 0
    return min(100, max(0, score))


def _build_risk(tech: dict, supply: dict) -> str:
    risks = []
    if tech.get("indicators", {}).get("rsi", 50) > 70:
        risks.append("RSI 과매수")
    if supply.get("외국인", 0) < 0:
        risks.append("외국인 순매도")
    if not risks:
        risks.append("단기 변동성 주의")
    return " · ".join(risks)


def _get_trading_date() -> str:
    today = datetime.now()
    if today.weekday() == 5:   today -= timedelta(days=1)
    elif today.weekday() == 6: today -= timedelta(days=2)
    return today.strftime("%Y%m%d")
