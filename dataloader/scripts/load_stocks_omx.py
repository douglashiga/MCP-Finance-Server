#!/usr/bin/env python3
"""
Load OMX Stocks (ELT Extractor)
Source: Seed file (scraped from stockanalysis.com)
"""
import sys
import os
import json
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dataloader.database import SessionLocal, init_db
from dataloader.models import RawOMXStock

SEED_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "seeds", "omx_stocks_full.json")

def main():
    init_db()
    session = SessionLocal()
    
    count_new = 0
    count_updated = 0
    
    try:
        print(f"[LOADER-OMX] Loading stocks from {SEED_FILE_PATH}...")
        
        if not os.path.exists(SEED_FILE_PATH):
            print(f"[ERROR] Seed file not found at {SEED_FILE_PATH}")
            sys.exit(1)
            
        with open(SEED_FILE_PATH, "r") as f:
            stocks_data = json.load(f)
            
        print(f"[LOADER-OMX] Found {len(stocks_data)} records in seed file.")
        
        for item in stocks_data:
            # Normalize symbol for Yahoo Finance
            # StockAnalysis gives "AZN", "ABB", "INVE.A"
            # Yahoo expects "AZN.ST", "ABB.ST", "INVE-A.ST" (typically dot becomes dash in Yahoo for A/B shares, but let's check)
            # Actually, Yahoo often uses "INVE-B.ST". StockAnalysis uses "INVE.B".
            # Let's replace dot with dash and append .ST
            
            raw_symbol = item["symbol"]
            
            # Simple heuristic mapping for Yahoo Finance compliance
            # If it has a dot (e.g. INVE.B), replace with dash (INVE-B)
            # Then append .ST
            
            yahoo_symbol = raw_symbol.replace(".", "-") + ".ST"
            
            # Store the normalized symbol as the key
            # We also keep the original in the data json if needed
            item["yahoo_symbol"] = yahoo_symbol
            json_str = json.dumps(item)
            
            existing = session.query(RawOMXStock).filter_by(symbol=yahoo_symbol).first()
            if not existing:
                session.add(RawOMXStock(
                    symbol=yahoo_symbol,
                    data=json_str,
                    fetched_at=datetime.now(timezone.utc)
                ))
                count_new += 1
            else:
                existing.data = json_str
                existing.fetched_at = datetime.now(timezone.utc)
                count_updated += 1
        
        session.commit()
        print(f"[LOADER-OMX] Finished. New: {count_new}, Updated: {count_updated}")
        print(f"RECORDS_AFFECTED={count_new + count_updated}")

    except Exception as e:
        session.rollback()
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        session.close()

if __name__ == "__main__":
    main()
