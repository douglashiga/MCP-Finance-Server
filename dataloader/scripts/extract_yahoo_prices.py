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
from dataloader.models import Stock, RawYahooPrice, Job
from services.data_quality_service import DataQualityService
import yfinance as yf
import pandas as pd

# Configure logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def get_job_id(session):
    job = session.query(Job).filter_by(name='Extract Yahoo Prices').first()
    return job.id if job else None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Run in test mode (1 symbol)")
    args = parser.parse_args()
    
    session = SessionLocal()
    count = 0
    run_id = os.environ.get("RUN_ID")
    if run_id: run_id = int(run_id)
    
    try:
        job_id = get_job_id(session)
        
        # Get active stocks with track_prices enabled
        query = session.query(Stock).filter(Stock.is_active == True, Stock.track_prices == True)
        if args.test:
            query = query.limit(5)
        stocks = query.all()
        
        print(f"[EXTRACT YAHOO PRICES] Fetching prices for {len(stocks)} stocks...")
        
        BATCH_SIZE = 100
        total_stocks = len(stocks)
        
        for i in range(0, total_stocks, BATCH_SIZE):
            batch = stocks[i : i + BATCH_SIZE]
            symbols = [s.symbol for s in batch]
            tickers_str = " ".join(symbols)
            
            print(f"  > Batch {i}-{i+len(batch)}: Downloading data...")
            try:
                df = yf.download(
                    tickers_str, 
                    period="1d", 
                    group_by='ticker', 
                    threads=True,
                    progress=False
                )
                
                for stock in batch:
                    sym = stock.symbol
                    try:
                        stock_df = None
                        if len(batch) == 1:
                            stock_df = df
                        else:
                            try:
                                stock_df = df[sym]
                            except KeyError:
                                DataQualityService.log_issue(
                                    job_id=job_id,
                                    run_id=run_id,
                                    stock_id=stock.id,
                                    issue_type="ticker_not_found",
                                    severity="warning",
                                    description=f"Yahoo Finance returned no data for {sym}"
                                )
                                continue
                        
                        if stock_df.empty:
                            DataQualityService.log_issue(
                                job_id=job_id,
                                run_id=run_id,
                                stock_id=stock.id,
                                issue_type="empty_response",
                                severity="info",
                                description=f"Empty DataFrame for {sym}"
                            )
                            continue
                            
                        last_row = stock_df.iloc[-1]
                        price = float(last_row['Close'])
                        
                        if pd.isna(price):
                            DataQualityService.log_issue(
                                job_id=job_id,
                                run_id=run_id,
                                stock_id=stock.id,
                                issue_type="invalid_value",
                                severity="warning",
                                description=f"NaN price for {sym}",
                                payload=last_row.to_dict()
                            )
                            continue
                            
                        price_data = {
                            "symbol": sym,
                            "regularMarketPrice": price,
                            "regularMarketOpen": float(last_row['Open']) if not pd.isna(last_row['Open']) else None,
                            "regularMarketDayHigh": float(last_row['High']) if not pd.isna(last_row['High']) else None,
                            "regularMarketDayLow": float(last_row['Low']) if not pd.isna(last_row['Low']) else None,
                            "regularMarketVolume": int(last_row['Volume']) if not pd.isna(last_row['Volume']) else None,
                            "currency": stock.currency,
                            "marketState": "REGULAR",
                            "exchange": stock.exchange,
                            "source": "yahoo_download_batch"
                        }

                        raw_record = RawYahooPrice(
                            symbol=sym,
                            data=json.dumps(price_data),
                            fetched_at=datetime.now(timezone.utc)
                        )
                        session.add(raw_record)
                        count += 1
                        
                    except Exception as e:
                        logger.error(f"Error processing {sym}: {e}")
                        continue
                        
            except Exception as e:
                logger.error(f"Batch failed: {e}")
                continue
                
            session.commit()

        print(f"[EXTRACT YAHOO PRICES] Extracted {count} price records")
        print(f"RECORDS_AFFECTED={count}")
        
    except Exception as e:
        session.rollback()
        logger.error(f"Main loop error: {e}")
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
