#!/usr/bin/env python3
"""
Load Dividends — Fetches 5-year dividend history + current yield for all stocks.
Uses yfinance.
"""
import sys
import os
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from datetime import datetime
from dataloader.database import SessionLocal, init_db
from dataloader.models import Stock, Dividend


def fetch_dividends(symbol: str) -> list[dict]:
    """Fetch dividend history for a stock."""
    import yfinance as yf
    
    ticker = yf.Ticker(symbol)
    info = ticker.info
    
    current_yield = info.get("dividendYield")
    payout_ratio = info.get("payoutRatio")
    
    # Get dividend history (last 5 years)
    divs = ticker.dividends
    if divs is None or divs.empty:
        return []
    
    # Filter last 5 years
    from datetime import timedelta
    cutoff = datetime.now() - timedelta(days=5*365)
    divs = divs[divs.index >= cutoff.strftime("%Y-%m-%d")]
    
    results = []
    for date, amount in divs.items():
        results.append({
            "ex_date": date.date() if hasattr(date, 'date') else date,
            "amount": float(amount),
            "currency": info.get("currency", "USD"),
            "dividend_yield": current_yield,
            "payout_ratio": payout_ratio,
        })
    
    return results


def main():
    init_db()
    session = SessionLocal()
    count = 0
    errors = 0

    try:
        stocks = session.query(Stock).all()
        total = len(stocks)
        print(f"[DIVIDENDS] Fetching data for {total} stocks...")

        for i, stock in enumerate(stocks, 1):
            try:
                print(f"  [{i}/{total}] {stock.symbol}...", end=" ", flush=True)
                divs = fetch_dividends(stock.symbol)
                
                if divs:
                    for d in divs:
                        # Upsert: skip if already exists
                        existing = session.query(Dividend).filter_by(
                            stock_id=stock.id,
                            ex_date=d["ex_date"],
                            amount=d["amount"],
                        ).first()
                        
                        if not existing:
                            session.add(Dividend(stock_id=stock.id, **d))
                            count += 1
                    
                    print(f"OK ({len(divs)} records)")
                else:
                    print("no dividends")
                
                time.sleep(0.5)
                
            except Exception as e:
                print(f"ERROR: {e}")
                errors += 1
                continue

        session.commit()
        print(f"\n[DIVIDENDS] Done: {count} new records, {errors} errors")
        print(f"RECORDS_AFFECTED={count}")

    except Exception as e:
        session.rollback()
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
