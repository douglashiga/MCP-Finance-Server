#!/usr/bin/env python3
"""
Load B3 Stocks (ELT Extractor)
Source: BrAPI (https://brapi.dev)
"""
import sys
import os
import json
import requests
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dataloader.database import SessionLocal, init_db
from dataloader.models import RawB3Stock

BRAPI_LIST_URL = "https://brapi.dev/api/quote/list"

def fetch_brapi_stocks():
    """Fetch all B3 stocks from BrAPI with pagination."""
    all_stocks = []
    types = ["stock", "fund", "bdr"]
    limit = 100 
    
    print(f"[LOADER-B3] Fetching from {BRAPI_LIST_URL}...")
    
    for t in types:
        page = 1
        print(f"  > Fetching type='{t}'...")
        while True:
            try:
                # print(f"    Page {page}...", end="\r")
                params = {"type": t, "limit": limit, "page": page}
                response = requests.get(BRAPI_LIST_URL, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()
                
                stocks = data.get("stocks", [])
                if not stocks:
                    break
                
                all_stocks.extend(stocks)
                
                if not data.get("hasNextPage"):
                    break
                
                page += 1
                # Respect potential rate limits
                time.sleep(0.1)
                
            except Exception as e:
                print(f"\n[ERROR] Failed to fetch B3 stocks (type={t}, page={page}): {e}")
                # Try next type if one fails
                break
        print(f"    Done {t}. Total so far: {len(all_stocks)}")
                
    return all_stocks

def main():
    init_db()
    session = SessionLocal()
    
    try:
        raw_data = fetch_brapi_stocks()
        if not raw_data:
            print("[LOADER-B3] No data fetched. Exiting.")
            sys.exit(1)

        print(f"[LOADER-B3] Processing {len(raw_data)} records...")
        
        count_new = 0
        count_updated = 0
        processed_cod_negs = set()
        
        for item in raw_data:
            # BrAPI returns "stock" as the ticker field name
            cod_neg = item.get("stock", "").strip()
            if not cod_neg:
                continue
            
            if cod_neg in processed_cod_negs:
                continue
            processed_cod_negs.add(cod_neg)
                
            # Store full JSON 
            json_str = json.dumps(item)
            
            existing = session.query(RawB3Stock).filter_by(cod_neg=cod_neg).first()
            if not existing:
                row = RawB3Stock(
                    cod_neg=cod_neg,
                    data=json_str,
                    fetched_at=datetime.now(timezone.utc)
                )
                session.add(row)
                count_new += 1
            else:
                existing.data = json_str
                existing.fetched_at = datetime.now(timezone.utc)
                count_updated += 1
        
        session.commit()
        print(f"[LOADER-B3] Finished. New: {count_new}, Updated: {count_updated}")
        print(f"RECORDS_AFFECTED={count_new + count_updated}")

    except Exception as e:
        session.rollback()
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        session.close()

if __name__ == "__main__":
    main()
