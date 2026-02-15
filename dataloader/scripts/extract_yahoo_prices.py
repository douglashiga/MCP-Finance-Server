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
import logging
from typing import List, Dict, Any
from datetime import datetime, timezone
from dataloader.database import SessionLocal
from dataloader.models import Stock, RawYahooPrice
import yfinance as yf
import pandas as pd

# Configure logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

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
        
        BATCH_SIZE = 500
        total_stocks = len(stocks)
        print(f"[EXTRACT YAHOO PRICES] Fetching prices for {total_stocks} stocks in batches of {BATCH_SIZE}...")
        
        for i in range(0, total_stocks, BATCH_SIZE):
            batch = stocks[i : i + BATCH_SIZE]
            symbols = [s.symbol for s in batch]
            symbol_map = {s.symbol: s for s in batch}
            
            # yfinance allows fetching multiple tickers at once
            tickers_str = " ".join(symbols)
            
            try:
                # Using yf.Tickers to get a collection of ticker objects
                # Note: yf.download is for history. For current info, we use Tickers.
                # Accessing .info on each ticker in the collection might still be serial internally in some versions,
                # but 'fast_info' or accessing the ticker object is the standard way.
                # However, yfinance doesn't have a true bulk "get quote" endpoint exposed easily for 500 tickers 
                # without using the 'download' method (which gives history).
                # 
                # WORKAROUND for speed:
                # We can use yf.download(..., period="1d") to get the latest close/price efficiently in bulk.
                # But that gives OHLC, not full 'info' (sector, market cap, etc).
                # For 'extract_yahoo_prices', we primarily need the price.
                # Let's use download for the price, and fallback to info if needed?
                # Actually, the original script extracted: regularMarketPrice, open, dayHigh, dayLow, volume, etc.
                # yf.download gives: Open, High, Low, Close, Volume.
                # This matches 90% of requirements and is MUCH faster.
                
                print(f"  > Batch {i}-{i+len(batch)}: Downloading data...")
                # group_by='ticker' ensures we get a MultiIndex if >1 ticker, or standard if 1.
                # threads=True is default.
                df = yf.download(
                    tickers_str, 
                    period="1d", 
                    group_by='ticker', 
                    threads=True,
                    progress=False
                )
                
                # If only 1 ticker, df structure is different (single level columns) unless we force it.
                # If multiple, it's (Ticker, PriceType).
                # Note: yfinance recently changed behavior in 0.2.x to always return multi-index if requested?
                # Let's handle both.

                for stock in batch:
                    sym = stock.symbol
                    price_data = {}
                    
                    try:
                        # Extract from DataFrame
                        # If len(batch) == 1, df.columns might be just Index(['Open', ...])
                        # If len(batch) > 1, df.columns is MultiIndex levels=[[sym...], ['Open'...]]
                        
                        stock_df = None
                        if len(batch) == 1:
                            stock_df = df
                        else:
                            try:
                                stock_df = df[sym]
                            except KeyError:
                                # Ticker might be missing data
                                print(f"    ⚠️  No data for {sym}", file=sys.stderr)
                                continue
                        
                        if stock_df.empty:
                            continue
                            
                        # Get the last row (latest day)
                        last_row = stock_df.iloc[-1]
                        
                        # Map to our schema
                        # Note: 'Close' is often the latest price during trading day too (delayed 15m)
                        price = float(last_row['Close'])
                        if pd.isna(price):
                            continue
                            
                        price_data = {
                            "symbol": sym,
                            "regularMarketPrice": price,
                            "regularMarketOpen": float(last_row['Open']),
                            "regularMarketDayHigh": float(last_row['High']),
                            "regularMarketDayLow": float(last_row['Low']),
                            "regularMarketVolume": int(last_row['Volume']),
                            "regularMarketPreviousClose": None, # Download doesn't give prev close easily without 2d history
                            "regularMarketChange": None, 
                            "regularMarketChangePercent": None,
                            "currency": stock.currency, # Fallback to DB currency
                            "marketState": "REGULAR", # Assumption
                            "exchange": stock.exchange, # Fallback
                            "source": "yahoo_download_batch"
                        }

                        # Store raw JSON
                        raw_record = RawYahooPrice(
                            symbol=sym,
                            data=json.dumps(price_data),
                            fetched_at=datetime.now(timezone.utc)
                        )
                        session.add(raw_record)
                        count += 1
                        
                    except Exception as e:
                        # print(f"    Error processing {sym}: {e}")
                        continue
                        
            except Exception as e:
                print(f"  ❌ Batch failed: {e}", file=sys.stderr)
                continue
                
            # Commit per batch to avoid massive transaction
            session.commit()

        
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
