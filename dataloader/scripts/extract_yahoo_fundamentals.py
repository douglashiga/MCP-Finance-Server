#!/usr/bin/env python3
"""
Extract Yahoo Fundamentals — Fetches fundamental data and stores raw JSON.
Runs daily to update company metrics.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import json
import time
from datetime import datetime
from dataloader.database import SessionLocal
from dataloader.models import Stock, RawYahooFundamental
import yfinance as yf


def main():
    session = SessionLocal()
    count = 0
    
    try:
        stocks = session.query(Stock).all()
        
        print(f"[EXTRACT YAHOO FUNDAMENTALS] Fetching fundamentals for {len(stocks)} stocks...")
        
        for stock in stocks:
            try:
                ticker = yf.Ticker(stock.symbol)
                info = ticker.info
                
                # Store the entire info dict as raw JSON
                raw_record = RawYahooFundamental(
                    symbol=stock.symbol,
                    data=json.dumps(info),
                    fetched_at=datetime.utcnow()
                )
                session.add(raw_record)
                count += 1
                
                # Rate limiting
                time.sleep(0.5)
                
            except Exception as e:
                print(f"  ⚠️  Failed to fetch {stock.symbol}: {e}", file=sys.stderr)
                continue
        
        session.commit()
        print(f"[EXTRACT YAHOO FUNDAMENTALS] Extracted {count} fundamental records")
        print(f"RECORDS_AFFECTED={count}")
        
    except Exception as e:
        session.rollback()
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
