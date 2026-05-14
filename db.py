"""
utils/db.py
Supabase CRUD 공통 함수.
Supabase 기본 조회 한도는 1,000행 — 대량 조회 시 반드시 paginate_all() 사용.
"""

from __future__ import annotations
from typing import Any
from utils.clients import get_supabase


# ── 페이지네이션 전체 조회 ────────────────────────────────
def paginate_all(table: str, *, query_fn=None, page_size: int = 1000) -> list[dict]:
    """
    Supabase 1,000행 제한을 우회해 테이블 전체를 가져온다.
    query_fn: 추가 필터가 필요하면 lambda q: q.eq("col","val") 형태로 전달.
    """
    sb = get_supabase()
    results: list[dict] = []
    offset = 0

    while True:
        q = sb.table(table).select("*").range(offset, offset + page_size - 1)
        if query_fn:
            q = query_fn(q)
        rows = q.execute().data
        if not rows:
            break
        results.extend(rows)
        if len(rows) < page_size:
            break
        offset += page_size

    return results


# ── 단건 upsert ──────────────────────────────────────────
def upsert_row(table: str, row: dict, on_conflict: str = "id") -> dict | None:
    sb = get_supabase()
    res = sb.table(table).upsert(row, on_conflict=on_conflict).execute()
    return res.data[0] if res.data else None


# ── 단건 삭제 ────────────────────────────────────────────
def delete_row(table: str, col: str, val: Any) -> bool:
    sb = get_supabase()
    sb.table(table).delete().eq(col, val).execute()
    return True


# ── 관심종목 ─────────────────────────────────────────────
def get_watchlist(market: str) -> list[dict]:
    """market: 'KR' | 'US'"""
    sb = get_supabase()
    return (
        sb.table("watchlist")
        .select("*")
        .eq("market", market)
        .order("added_at", desc=True)
        .execute()
        .data
    )


def add_watchlist(ticker: str, name: str, market: str) -> bool:
    sb = get_supabase()
    sb.table("watchlist").upsert(
        {"ticker": ticker, "name": name, "market": market},
        on_conflict="ticker",
    ).execute()
    return True


def remove_watchlist(ticker: str) -> bool:
    return delete_row("watchlist", "ticker", ticker)


# ── 투자종목 ─────────────────────────────────────────────
def get_portfolio(market: str) -> list[dict]:
    """market: 'KR' | 'US'"""
    sb = get_supabase()
    return (
        sb.table("portfolio")
        .select("*")
        .eq("market", market)
        .order("buy_date", desc=True)
        .execute()
        .data
    )


def add_portfolio(row: dict) -> bool:
    """
    row 예시:
    {ticker, name, market, buy_price, buy_qty, buy_date, reason, target_price, stop_loss}
    reason(매수 사유) 미입력 시 저장 불가 — UI 단에서 강제.
    """
    sb = get_supabase()
    sb.table("portfolio").insert(row).execute()
    return True


# ── 추천 이력 ────────────────────────────────────────────
def save_recommendation(row: dict) -> bool:
    """AI 추천을 기록한다. row: {ticker, market, rec_type, reason_summary, rec_date}"""
    sb = get_supabase()
    sb.table("recommendations").insert(row).execute()
    return True


def get_recommendations(limit: int = 100) -> list[dict]:
    sb = get_supabase()
    return (
        sb.table("recommendations")
        .select("*")
        .order("rec_date", desc=True)
        .limit(limit)
        .execute()
        .data
    )
