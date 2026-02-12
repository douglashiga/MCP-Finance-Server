#!/usr/bin/env python3
"""
Load Fundamentals — Fetches PE, EPS, revenue, margins, ROE, debt for all stocks.
Uses yfinance (free, no API key needed).
"""
import sys
import os
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from datetime import datetime
from dataloader.database import SessionLocal, init_db
from dataloader.models import Stock, Fundamental


def safe_get(info: dict, key: str, default=None):
    """Safely get a value from yfinance info dict."""
    val = info.get(key, default)
    if val is None or val == "":
        return default
    return val


def fetch_fundamentals(symbol: str) -> dict:
    """Fetch fundamental data for a single stock."""
    import yfinance as yf
    
    ticker = yf.Ticker(symbol)
    info = ticker.info
    
    if not info or info.get("regularMarketPrice") is None:
        return None
    
    total_debt = safe_get(info, "totalDebt", 0)
    total_cash = safe_get(info, "totalCash", 0)
    
    return {
        "market_cap": safe_get(info, "marketCap"),
        "enterprise_value": safe_get(info, "enterpriseValue"),
        "trailing_pe": safe_get(info, "trailingPE"),
        "forward_pe": safe_get(info, "forwardPE"),
        "trailing_eps": safe_get(info, "trailingEps"),
        "forward_eps": safe_get(info, "forwardEps"),
        "peg_ratio": safe_get(info, "pegRatio"),
        "price_to_book": safe_get(info, "priceToBook"),
        "revenue": safe_get(info, "totalRevenue"),
        "revenue_growth": safe_get(info, "revenueGrowth"),
        "gross_margin": safe_get(info, "grossMargins"),
        "operating_margin": safe_get(info, "operatingMargins"),
        "net_margin": safe_get(info, "profitMargins"),
        "roe": safe_get(info, "returnOnEquity"),
        "roa": safe_get(info, "returnOnAssets"),
        "debt_to_equity": safe_get(info, "debtToEquity"),
        "current_ratio": safe_get(info, "currentRatio"),
        "total_debt": total_debt,
        "total_cash": total_cash,
        "net_debt": (total_debt - total_cash) if total_debt and total_cash else None,
        "free_cash_flow": safe_get(info, "freeCashflow"),
        "ebitda": safe_get(info, "ebitda"),
    }


def main():
    init_db()
    session = SessionLocal()
    count = 0
    errors = 0

    try:
        stocks = session.query(Stock).all()
        total = len(stocks)
        print(f"[FUNDAMENTALS] Fetching data for {total} stocks...")

        for i, stock in enumerate(stocks, 1):
            try:
                print(f"  [{i}/{total}] {stock.symbol}...", end=" ", flush=True)
                data = fetch_fundamentals(stock.symbol)
                
                if data:
                    fund = Fundamental(stock_id=stock.id, fetched_at=datetime.utcnow(), **data)
                    session.add(fund)
                    count += 1
                    print(f"OK (PE={data.get('trailing_pe', 'N/A')})")
                else:
                    print("SKIP (no data)")
                
                # Rate limit: be nice to Yahoo
                time.sleep(0.5)
                
            except Exception as e:
                print(f"ERROR: {e}")
                errors += 1
                continue

        session.commit()
        print(f"\n[FUNDAMENTALS] Done: {count} loaded, {errors} errors")
        print(f"RECORDS_AFFECTED={count}")

    except Exception as e:
        session.rollback()
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
