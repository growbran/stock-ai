"""
utils/clients.py
모든 외부 API 클라이언트를 한 곳에서 초기화.
앱 전체에서 이 파일의 함수를 import해서 사용한다.
API 키는 .streamlit/secrets.toml 에서만 읽는다 — 절대 하드코딩 금지.
"""

import streamlit as st
from google import genai
from supabase import create_client, Client


# ── Gemini ──────────────────────────────────────────────
@st.cache_resource
def get_gemini() -> genai.Client:
    """Gemini genai.Client 싱글턴 반환. 반드시 이 함수만 사용."""
    return genai.Client(api_key=st.secrets["GEMINI_API_KEY"])


# ── Supabase ─────────────────────────────────────────────
@st.cache_resource
def get_supabase() -> Client:
    """Supabase 클라이언트 싱글턴 반환."""
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_KEY"],
    )


# ── KIS (한국투자증권) ────────────────────────────────────
def get_kis_headers() -> dict:
    """KIS REST API 공통 헤더. 토큰 발급은 kis_auth.py 에서 별도 처리 예정."""
    return {
        "content-type": "application/json; charset=utf-8",
        "appkey":    st.secrets["KIS_APP_KEY"],
        "appsecret": st.secrets["KIS_APP_SECRET"],
    }


KIS_BASE_URL = "https://openapi.koreainvestment.com:9443"


# ── Alpaca (미국 주식) ────────────────────────────────────
def get_alpaca_headers() -> dict:
    """Alpaca REST API 공통 헤더."""
    return {
        "APCA-API-KEY-ID":     st.secrets["ALPACA_API_KEY"],
        "APCA-API-SECRET-KEY": st.secrets["ALPACA_SECRET_KEY"],
    }


ALPACA_BASE_URL = "https://data.alpaca.markets"
