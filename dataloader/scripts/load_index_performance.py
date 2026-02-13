#!/usr/bin/env python3
"""
Load Index Performance — Fetches daily data for market indices.
Covers: ^BVSP (Ibovespa), ^OMX (OMXS30), ^OMXSPI.
"""
import sys
import os
import time
import math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from datetime import datetime
from dataloader.database import SessionLocal, init_db
from dataloader.models import IndexPerformance, MarketIndex

FALLBACK_INDICES = [
    {"symbol": "^BVSP", "name": "Ibovespa"},
    {"symbol": "^OMX", "name": "OMXS30"},
    {"symbol": "^OMXSPI", "name": "OMX Stockholm PI"},
]


def _to_float(value):
    if value is None:
        return None
    try:
        val = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(val) or math.isinf(val):
        return None
    return val


def fetch_index_data(symbol: str, period: str = "5y") -> list[dict]:
    """Fetch historical data for a market index."""
    import yfinance as yf
    
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period=period, interval="1d")
    
    if hist is None or hist.empty:
        return []
    
    results = []
    for date, row in hist.iterrows():
        close_v = _to_float(row.get("Close"))
        if close_v is None or close_v <= 0:
            continue

        results.append({
            "date": date.date() if hasattr(date, 'date') else date,
            "open": _to_float(row.get("Open")),
            "high": _to_float(row.get("High")),
            "low": _to_float(row.get("Low")),
            "close": close_v,
            "volume": _to_float(row.get("Volume")),
        })
    
    return results


def main():
    init_db()
    session = SessionLocal()
    count = 0
    errors = 0

    try:
        idx_rows = session.query(MarketIndex).filter(MarketIndex.is_active == True).all()
        indices = [{"symbol": r.symbol, "name": r.name} for r in idx_rows] if idx_rows else FALLBACK_INDICES

        for idx in indices:
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
