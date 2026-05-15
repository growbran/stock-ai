"""
modules/screener_kr.py
국내(KRX) 단기 트레이딩 종목 스크리닝 — KIS API 기반

조건 (우선순위):
1. 시가총액 1,000억 이상 + 주가 1,000원 이상 + 양봉
2. 전일 대비 7% 이상 상승 + 거래대금 3,000억 이상 or 상위 100위
3. 20일 이동평균선 우상향 + 현재가 20일선 위
4. 외국인 순매수 > 0 AND 기관 순매수 > 0 (양매수 필수)
"""

from __future__ import annotations
import requests
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta

# ── KIS API 설정 ──────────────────────────────────────────
KIS_BASE = "https://openapi.koreainvestment.com:9443"


def _get_kis_token(force_refresh: bool = False) -> str:
    """KIS 접근토큰 발급 (세션 캐싱 + 만료 시 자동 갱신)."""
    if not force_refresh and "kis_token" in st.session_state:
        return st.session_state["kis_token"]

    url = f"{KIS_BASE}/oauth2/tokenP"
    body = {
        "grant_type": "client_credentials",
        "appkey":     st.secrets["KIS_APP_KEY"],
        "appsecret":  st.secrets["KIS_APP_SECRET"],
    }
    resp = requests.post(url, json=body, timeout=10)

    if resp.status_code != 200:
        st.error(f"KIS 토큰 발급 실패: {resp.status_code} — {resp.text[:200]}")
        raise Exception("KIS 토큰 발급 실패")

    try:
        data = resp.json()
    except Exception:
        st.error(f"KIS 토큰 응답 파싱 실패: {resp.text[:200]}")
        raise

    if "access_token" not in data:
        st.error(f"KIS 토큰 응답 오류: {data}")
        raise Exception("access_token 없음")

    token = data["access_token"]
    st.session_state["kis_token"] = token
    return token


def _kis_headers(tr_id: str) -> dict:
    return {
        "content-type":  "application/json; charset=utf-8",
        "authorization": f"Bearer {_get_kis_token()}",
        "appkey":        st.secrets["KIS_APP_KEY"],
        "appsecret":     st.secrets["KIS_APP_SECRET"],
        "tr_id":         tr_id,
        "custtype":      "P",
    }


# ── 메인 스크리닝 ─────────────────────────────────────────
def run_screening(top_n: int = 100, sentiment_min: int = 65) -> list[dict]:
    try:
        with st.spinner("거래대금 상위 종목 조회 중..."):
            candidates = _get_volume_leaders(top_n)

        if not candidates:
            st.warning("거래대금 상위 종목을 가져오지 못했습니다.")
            return []

        results = []
        progress = st.progress(0, text="조건 필터링 중...")
        total = len(candidates)

        for idx, item in enumerate(candidates):
            ticker = item["ticker"]
            name   = item["name"]
            progress.progress((idx + 1) / total, text=f"분석 중: {name}")

            # 1. 기본 필터 (시총·주가·양봉·상승률)
            detail = _get_stock_detail(ticker)
            if detail is None:
                continue
            if not _pass_basic_filter(detail):
                continue

            # 2. 이동평균 필터 (20일선)
            price_df = _get_ohlcv(ticker)
            if price_df is None or len(price_df) < 21:
                continue
            if not _pass_ma_filter(price_df, detail["current"]):
                continue

            # 3. 외인·기관 양매수 필터
            supply = _get_investor_supply(ticker)
            if supply is None:
                continue
            if not (supply["외국인"] > 0 and supply["기관"] > 0):
                continue

            # 뉴스 감성
            sentiment_score, news_list = _get_news_sentiment(name)

            current = detail["current"]
            target  = round(current * 1.08, -1)
            stop    = round(current * 0.96, -1)

            results.append({
                "ticker":       ticker,
                "name":         name,
                "score":        _calc_score(detail, supply, sentiment_score),
                "price":        f"{int(current):,}원",
                "change_rate":  detail.get("change_rate", "—"),
                "trade_value":  item.get("trade_value", "—"),
                "sentiment":    sentiment_score,
                "theme":        _extract_theme(news_list),
                "chart_status": _chart_status(price_df, detail["current"]),
                "signal":       "매수검토",
                "risk":         _build_risk(detail, supply),
                "target_price": f"{int(target):,}원",
                "stop_loss":    f"{int(stop):,}원",
                "supply":       supply,
                "news":         news_list,
            })

        progress.empty()

        # Supabase 저장
        if results:
            _save_to_supabase(results)

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:5]

    except Exception as e:
        st.error(f"스크리닝 오류: {e}")
        return []


# ── 거래대금 상위 종목 ────────────────────────────────────
def _get_volume_leaders(top_n: int) -> list[dict]:
    """KIS 거래대금 순위 조회."""
    url = f"{KIS_BASE}/uapi/domestic-stock/v1/ranking/volume"
    params = {
        "fid_cond_mrkt_div_code": "J",
        "fid_cond_scr_div_code":  "20171",
        "fid_input_iscd":         "0000",
        "fid_rank_sort_cls_code": "0",
        "fid_input_cnt_1":        str(top_n),
        "fid_trgt_cls_code":      "0",
        "fid_trgt_exls_cls_code": "000000",
        "fid_div_cls_code":       "0",
        "fid_rsfl_rate1":         "0",
        "fid_rsfl_rate2":         "0",
    }
    try:
        resp = requests.get(
            url, headers=_kis_headers("FHPST01710000"), params=params, timeout=10
        )

        if resp.status_code != 200:
            st.error(f"KIS API 오류 ({resp.status_code}): {resp.text[:300]}")
            return []

        try:
            data = resp.json()
        except Exception:
            st.error(f"KIS 응답 파싱 실패 (빈 응답 또는 HTML): {resp.text[:300]}")
            return []

        rt_cd = data.get("rt_cd", "")
        if rt_cd != "0":
            # 토큰 만료 시 자동 갱신 후 1회 재시도
            if rt_cd == "1":
                st.info("KIS 토큰 만료 — 자동 갱신 중...")
                st.session_state.pop("kis_token", None)
                resp2 = requests.get(
                    url, headers=_kis_headers("FHPST01710000"), params=params, timeout=10
                )
                data = resp2.json()
            else:
                st.error(f"KIS API 응답 오류: {data.get('msg1', data)}")
                return []

        results = []
        for item in data.get("output", []):
            trade_val = int(item.get("acml_tr_pbmn", 0))
            if trade_val < 300_000_000_000:  # 3,000억 미만 제외
                continue
            results.append({
                "ticker":      item.get("mksc_shrn_iscd", ""),
                "name":        item.get("hts_kor_isnm", ""),
                "trade_value": f"{trade_val/1e8:.0f}억",
            })
        return results

    except Exception as e:
        st.warning(f"거래량 순위 조회 오류: {e}")
        return []


# ── 종목 상세 (현재가·시총·등락률·양봉) ──────────────────
def _get_stock_detail(ticker: str) -> dict | None:
    url = f"{KIS_BASE}/uapi/domestic-stock/v1/quotations/inquire-price"
    params = {
        "fid_cond_mrkt_div_code": "J",
        "fid_input_iscd": ticker,
    }
    try:
        resp = requests.get(
            url, headers=_kis_headers("FHKST01010100"), params=params, timeout=10
        )
        d = resp.json().get("output", {})
        current    = int(d.get("stck_prpr", 0))
        open_price = int(d.get("stck_oprc", 0))
        mkt_cap    = int(d.get("hts_avls", 0))         # 억원
        change_rt  = float(d.get("prdy_ctrt", 0))      # 등락률 %

        return {
            "current":     current,
            "open":        open_price,
            "mkt_cap":     mkt_cap,
            "change_rate": f"{change_rt:+.2f}%",
            "change_pct":  change_rt,
            "is_bullish":  current > open_price,        # 양봉
        }
    except Exception:
        return None


def _pass_basic_filter(d: dict) -> bool:
    """시총 1,000억↑ + 주가 1,000원↑ + 양봉 + 7%↑."""
    return (
        d["mkt_cap"] >= 1000 and
        d["current"] >= 1000 and
        d["is_bullish"] and
        d["change_pct"] >= 7.0
    )


# ── OHLCV (일봉) ─────────────────────────────────────────
def _get_ohlcv(ticker: str, count: int = 30) -> pd.DataFrame | None:
    url = f"{KIS_BASE}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
    today = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=60)).strftime("%Y%m%d")
    params = {
        "fid_cond_mrkt_div_code": "J",
        "fid_input_iscd":         ticker,
        "fid_input_date_1":       start,
        "fid_input_date_2":       today,
        "fid_period_div_code":    "D",
        "fid_org_adj_prc":        "0",
    }
    try:
        resp = requests.get(
            url, headers=_kis_headers("FHKST03010100"), params=params, timeout=10
        )
        output = resp.json().get("output2", [])
        if not output:
            return None
        df = pd.DataFrame(output)
        df = df.rename(columns={
            "stck_bsop_date": "date",
            "stck_oprc":      "open",
            "stck_hgpr":      "high",
            "stck_lwpr":      "low",
            "stck_clpr":      "close",
            "acml_vol":       "volume",
        })
        for c in ["open", "high", "low", "close", "volume"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        return df.sort_values("date").reset_index(drop=True)
    except Exception:
        return None


def _pass_ma_filter(df: pd.DataFrame, current: float) -> bool:
    """20일선 우상향 + 현재가 20일선 위."""
    ma20 = df["close"].rolling(20).mean()
    if ma20.iloc[-1] is None or pd.isna(ma20.iloc[-1]):
        return False
    uptrend = ma20.iloc[-1] > ma20.iloc[-5]   # 5일 전보다 올라야 우상향
    above   = current > ma20.iloc[-1]
    return uptrend and above


def _chart_status(df: pd.DataFrame, current: float) -> str:
    ma20 = df["close"].rolling(20).mean().iloc[-1]
    ma5  = df["close"].rolling(5).mean().iloc[-1]
    parts = []
    if current > ma5:  parts.append("5일선 위")
    if current > ma20: parts.append("20일선 위")
    high_52w = df["high"].max()
    from_high = (current - high_52w) / high_52w * 100
    if from_high >= -5: parts.append("전고점 근접")
    return " · ".join(parts) if parts else "추세 확인 필요"


# ── 외인·기관 수급 ────────────────────────────────────────
def _get_investor_supply(ticker: str) -> dict | None:
    """당일 투자자별 순매수 금액 조회."""
    url = f"{KIS_BASE}/uapi/domestic-stock/v1/trading/inquire-investor"
    params = {
        "fid_cond_mrkt_div_code": "J",
        "fid_input_iscd":         ticker,
    }
    try:
        resp = requests.get(
            url, headers=_kis_headers("FHKST01010900"), params=params, timeout=10
        )
        output = resp.json().get("output", [])
        if not output:
            return None

        result = {"외국인": 0, "기관": 0, "개인": 0}
        for item in output:
            investor = item.get("invst_nm", "")
            net = int(item.get("srtn_seln_qty", 0)) - int(item.get("srtn_shnu_qty", 0))
            if "외국인" in investor: result["외국인"] += net
            elif "기관" in investor: result["기관"]   += net
            elif "개인" in investor: result["개인"]   += net
        return result
    except Exception:
        return None


def get_supply_detail(ticker: str, days: int = 20) -> pd.DataFrame:
    """수급 차트용 날짜별 데이터 — KIS API 전용."""
    try:
        url = f"{KIS_BASE}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
        today = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=days * 2)).strftime("%Y%m%d")
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd":         ticker,
            "fid_input_date_1":       start,
            "fid_input_date_2":       today,
            "fid_period_div_code":    "D",
            "fid_org_adj_prc":        "0",
        }
        resp = requests.get(
            url, headers=_kis_headers("FHKST03010100"), params=params, timeout=10
        )
        if resp.status_code != 200:
            return pd.DataFrame()

        output = resp.json().get("output2", [])
        if not output:
            return pd.DataFrame()

        rows = []
        for item in output:
            rows.append({
                "date":   item.get("stck_bsop_date", ""),
                "외국인": int(item.get("frgn_ntby_qty", 0)),
                "기관":   int(item.get("orgn_ntby_qty", 0)),
                "개인":   int(item.get("indv_ntby_qty", 0)),
            })
        df = pd.DataFrame(rows).sort_values("date").tail(days)
        return df.reset_index(drop=True)

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
            f"'{name}' 종목 관련 뉴스 제목들을 투자 관점에서 0~100점으로 점수만 숫자로 답하세요.\n\n"
            + "\n".join(news_list[:5])
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
def _extract_theme(news_list: list[str]) -> str:
    keywords = ["AI", "반도체", "2차전지", "바이오", "전기차", "로봇", "방산", "수소", "태양광", "게임"]
    for kw in keywords:
        for n in news_list:
            if kw in n:
                return kw
    return "기타"


def _calc_score(detail: dict, supply: dict, sentiment: int) -> int:
    score = 0
    score += min(30, int(detail.get("change_pct", 0) * 2))  # 등락률
    score += 20 if supply.get("외국인", 0) > 0 else 0       # 외인 매수
    score += 20 if supply.get("기관", 0) > 0 else 0         # 기관 매수
    score += int(sentiment * 0.3)                            # 뉴스
    return min(100, max(0, score))


def _build_risk(detail: dict, supply: dict) -> str:
    risks = []
    if detail.get("change_pct", 0) >= 15:  risks.append("단기 급등 과열")
    if supply.get("개인", 0) > 0 and supply.get("외국인", 0) < 0:
        risks.append("개인 주도 상승 주의")
    if not risks: risks.append("단기 변동성 주의")
    return " · ".join(risks)
