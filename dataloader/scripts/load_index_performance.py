#!/usr/bin/env python3
"""
Load Index Performance — Fetches daily data for market indices.
Covers: ^BVSP (Ibovespa), ^OMX (OMXS30), ^OMXSPI.
"""
import sys
import os
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from datetime import datetime
from dataloader.database import SessionLocal, init_db
from dataloader.models import IndexPerformance

INDICES = [
    {"symbol": "^BVSP", "name": "Ibovespa"},
    {"symbol": "^OMX", "name": "OMXS30"},
    {"symbol": "^OMXSPI", "name": "OMX Stockholm PI"},
]


def fetch_index_data(symbol: str, period: str = "5y") -> list[dict]:
    """Fetch historical data for a market index."""
    import yfinance as yf
    
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period=period, interval="1d")
    
    if hist is None or hist.empty:
        return []
    
    results = []
    for date, row in hist.iterrows():
        results.append({
            "date": date.date() if hasattr(date, 'date') else date,
            "open": float(row.get("Open", 0)) if row.get("Open") is not None else None,
            "high": float(row.get("High", 0)) if row.get("High") is not None else None,
            "low": float(row.get("Low", 0)) if row.get("Low") is not None else None,
            "close": float(row.get("Close", 0)) if row.get("Close") is not None else None,
            "volume": float(row.get("Volume", 0)) if row.get("Volume") is not None else None,
        })
    
    return results


def main():
    init_db()
    session = SessionLocal()
    count = 0
    errors = 0

    try:
        for idx in INDICES:
            symbol = idx["symbol"]
            name = idx["name"]
            
            try:
                print(f"[INDEX] Fetching {name} ({symbol})...", end=" ", flush=True)
                data = fetch_index_data(symbol)
                
                if data:
                    new_count = 0
                    for d in data:
                        existing = session.query(IndexPerformance).filter_by(
                            index_symbol=symbol, date=d["date"]
                        ).first()
                        
                        if not existing:
                            session.add(IndexPerformance(
                                index_symbol=symbol,
                                index_name=name,
                                **d
                            ))
                            new_count += 1
                        else:
                            existing.close = d["close"]
                            existing.open = d["open"]
                            existing.high = d["high"]
                            existing.low = d["low"]
                            existing.volume = d["volume"]
                    
                    count += new_count
                    print(f"OK ({len(data)} days, {new_count} new)")
                else:
                    print("no data")
                
                time.sleep(1)
                
            except Exception as e:
                print(f"ERROR: {e}")
                errors += 1
                continue

        session.commit()
        print(f"\n[INDEX] Done: {count} new records, {errors} errors")
        print(f"RECORDS_AFFECTED={count}")

    except Exception as e:
        session.rollback()
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
