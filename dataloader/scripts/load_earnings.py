#!/usr/bin/env python3
"""
Load Earnings — Fetches 10-year earnings history + upcoming calendar events.
Uses yfinance.
"""
import sys
import os
import argparse
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dataloader.database import SessionLocal, init_db
from dataloader.models import Stock, HistoricalEarnings, EarningsCalendar


def fetch_earnings_data(symbol: str, years: int = 10):
    """Fetch historical earnings and upcoming calendar."""
    import yfinance as yf
    
    ticker = yf.Ticker(symbol)
    
    # 1. Historical Earnings (EPS Surprise)
    hist_earnings = []
    try:
        # yfinance modern earnings history
        df = ticker.earnings_history
        if df is not None and not df.empty:
            cutoff = datetime.now() - timedelta(days=years*365)
            for date_idx, row in df.iterrows():
                # date_idx is typically the earnings report date
                if date_idx < cutoff:
                    continue
                
                hist_earnings.append({
                    "date": date_idx.date() if hasattr(date_idx, 'date') else date_idx,
                    "eps_estimate": row.get("EPS Estimate"),
                    "eps_actual": row.get("EPS Actual"),
                    "surprise_percent": row.get("Surprise(%)"),
                })
    except Exception as e:
        print(f"  ⚠️  Error fetching history for {symbol}: {e}")

    # 2. Upcoming Calendar
    calendar_data = None
    try:
        cal = ticker.calendar
        if cal is not None:
            # cal is often a dict or DataFrame with 'Earnings Date', 'Earnings Average', etc.
            # Handle different yfinance versions/formats
            e_date = None
            if isinstance(cal, dict):
                e_dates = cal.get('Earnings Date')
                if e_dates and isinstance(e_dates, list):
                    e_date = e_dates[0].date() if hasattr(e_dates[0], 'date') else e_dates[0]
                
                calendar_data = {
                    "earnings_date": e_date,
                    "earnings_average": cal.get('Earnings Average'),
                    "earnings_low": cal.get('Earnings Low'),
                    "earnings_high": cal.get('Earnings High'),
                    "revenue_average": cal.get('Revenue Average'),
                    "revenue_low": cal.get('Revenue Low'),
                    "revenue_high": cal.get('Revenue High'),
                }
            elif hasattr(cal, 'get'): # DataFrame style
                # Some versions return a DataFrame with rows like 'Earnings Date'
                # This varies a lot, using a safe get pattern
                try:
                    e_date_row = cal.loc['Earnings Date']
                    if hasattr(e_date_row, 'iloc'):
                        e_date = e_date_row.iloc[0].date()
                    else:
                        e_date = e_date_row[0].date()
                        
                    calendar_data = {
                        "earnings_date": e_date,
                        "earnings_average": cal.loc['Earnings Average'].iloc[0] if 'Earnings Average' in cal.index else None,
                        "revenue_average": cal.loc['Revenue Average'].iloc[0] if 'Revenue Average' in cal.index else None,
                    }
                except:
                    pass
    except Exception as e:
         pass # Calendar often fails for international stocks

    return hist_earnings, calendar_data


def main(years=None):
    if years is None:
        parser = argparse.ArgumentParser()
        parser.add_argument("--years", type=int, default=10, help="Number of years of history to fetch")
        args, _ = parser.parse_known_args()
        years = args.years
    
    init_db()
    session = SessionLocal()
    count_hist = 0
    count_cal = 0
    errors = 0

    try:
        stocks = session.query(Stock).all()
        total = len(stocks)
        print(f"[EARNINGS] Fetching {years}-year data for {total} stocks...")

        for i, stock in enumerate(stocks, 1):
            try:
                print(f"  [{i}/{total}] {stock.symbol}...", end=" ", flush=True)
                hist, cal = fetch_earnings_data(stock.symbol, years=years)
                
                # Update history
                if hist:
                    for h in hist:
                        existing = session.query(HistoricalEarnings).filter_by(
                            stock_id=stock.id,
                            date=h["date"]
                        ).first()
                        if not existing:
                            session.add(HistoricalEarnings(stock_id=stock.id, **h))
                            count_hist += 1
                
                # Update calendar
                if cal and cal.get("earnings_date"):
                    existing_cal = session.query(EarningsCalendar).filter_by(stock_id=stock.id).first()
                    if existing_cal:
                        for key, val in cal.items():
                            setattr(existing_cal, key, val)
                    else:
                        session.add(EarningsCalendar(stock_id=stock.id, **cal))
                    count_cal += 1
                
                print(f"OK ({len(hist)} hist, {'CAL' if cal else 'no cal'})")
                time.sleep(0.5)
                
            except Exception as e:
                print(f"ERROR: {e}")
                errors += 1
                continue

        session.commit()
        print(f"\n[EARNINGS] Done: {count_hist} history records, {count_cal} calendar updates, {errors} errors")
        print(f"RECORDS_AFFECTED={count_hist + count_cal}")

    except Exception as e:
        session.rollback()
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
