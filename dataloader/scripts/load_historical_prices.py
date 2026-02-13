import sys
import os
import argparse
import time
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from datetime import datetime
from dataloader.database import SessionLocal, init_db
from dataloader.models import Stock, HistoricalPrice


def _to_float(value):
    """Convert value to finite float or None."""
    if value is None:
        return None
    try:
        val = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(val) or math.isinf(val):
        return None
    return val

def fetch_prices(symbol: str, period: str = "1y") -> list[dict]:
    """Fetch historical daily prices."""
    import yfinance as yf
    
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period=period, interval="1d")
    
    if hist is None or hist.empty:
        return []
    
    results = []
    for date, row in hist.iterrows():
        open_v = _to_float(row.get("Open"))
        high_v = _to_float(row.get("High"))
        low_v = _to_float(row.get("Low"))
        close_v = _to_float(row.get("Close"))
        volume_v = _to_float(row.get("Volume"))

        # Skip rows without a valid close. These rows poison technical metrics.
        if close_v is None or close_v <= 0:
            continue

        results.append({
            "date": date.date() if hasattr(date, 'date') else date,
            "open": open_v,
            "high": high_v,
            "low": low_v,
            "close": close_v,
            "volume": volume_v,
        })
    
    return results


def main(period=None):
    if period is None:
        parser = argparse.ArgumentParser()
        parser.add_argument("--period", type=str, default="1y", help="Historical period (e.g. 1mo, 1y, 5y, max)")
        args, _ = parser.parse_known_args()
        period = args.period
    
    init_db()
    session = SessionLocal()
    count = 0
    errors = 0

    try:
        stocks = session.query(Stock).all()
        total = len(stocks)
        print(f"[PRICES] Fetching {period} history for {total} stocks...")

        for i, stock in enumerate(stocks, 1):
            try:
                print(f"  [{i}/{total}] {stock.symbol}...", end=" ", flush=True)
                prices = fetch_prices(stock.symbol, period=period)
                
                if prices:
                    new_count = 0
                    for p in prices:
                        existing = session.query(HistoricalPrice).filter_by(
                            stock_id=stock.id, date=p["date"]
                        ).first()
                        
                        if not existing:
                            session.add(HistoricalPrice(stock_id=stock.id, **p))
                            new_count += 1
                        else:
                            # Update existing
                            existing.open = p["open"]
                            existing.high = p["high"]
                            existing.low = p["low"]
                            existing.close = p["close"]
                            existing.volume = p["volume"]
                    
                    count += new_count
                    print(f"OK ({len(prices)} days, {new_count} new)")
                else:
                    print("no data")
                
                time.sleep(0.3)
                
            except Exception as e:
                print(f"ERROR: {e}")
                errors += 1
                continue

        session.commit()
        print(f"\n[PRICES] Done: {count} new price records, {errors} errors")
        print(f"RECORDS_AFFECTED={count}")

    except Exception as e:
        session.rollback()
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
