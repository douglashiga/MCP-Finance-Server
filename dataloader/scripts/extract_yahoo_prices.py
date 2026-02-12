#!/usr/bin/env python3
"""
Extract Yahoo Prices — Fetches current price data and stores raw JSON.
Runs every minute to keep realtime data fresh.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import argparse
import json
import time
from datetime import datetime
from dataloader.database import SessionLocal
from dataloader.models import Stock, RawYahooPrice
import yfinance as yf


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Run in test mode (1 symbol)")
    args = parser.parse_args()
    
    session = SessionLocal()
    count = 0
    
    try:
        # Get active stocks
        query = session.query(Stock)
        if args.test:
            query = query.limit(1)
        stocks = query.all()
        
        print(f"[EXTRACT YAHOO PRICES] Fetching prices for {len(stocks)} stocks...")
        
        for stock in stocks:
            try:
                # Fetch current price data from Yahoo
                ticker = yf.Ticker(stock.symbol)
                info = ticker.info
                
                # Extract relevant price fields
                price_data = {
                    "symbol": stock.symbol,
                    "regularMarketPrice": info.get("regularMarketPrice") or info.get("currentPrice"),
                    "regularMarketOpen": info.get("regularMarketOpen") or info.get("open"),
                    "regularMarketDayHigh": info.get("regularMarketDayHigh") or info.get("dayHigh"),
                    "regularMarketDayLow": info.get("regularMarketDayLow") or info.get("dayLow"),
                    "regularMarketVolume": info.get("regularMarketVolume") or info.get("volume"),
                    "regularMarketPreviousClose": info.get("regularMarketPreviousClose") or info.get("previousClose"),
                    "regularMarketChange": info.get("regularMarketChange"),
                    "regularMarketChangePercent": info.get("regularMarketChangePercent"),
                    "currency": info.get("currency"),
                    "marketState": info.get("marketState"),
                    "exchange": info.get("exchange"),
                }
                
                # Store raw JSON
                raw_record = RawYahooPrice(
                    symbol=stock.symbol,
                    data=json.dumps(price_data),
                    fetched_at=datetime.utcnow()
                )
                session.add(raw_record)
                count += 1
                
                # Rate limiting
                time.sleep(0.1)
                
            except Exception as e:
                print(f"  ⚠️  Failed to fetch {stock.symbol}: {e}", file=sys.stderr)
                continue
        
        session.commit()
        print(f"[EXTRACT YAHOO PRICES] Extracted {count} price records")
        print(f"RECORDS_AFFECTED={count}")
        
    except Exception as e:
        session.rollback()
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
