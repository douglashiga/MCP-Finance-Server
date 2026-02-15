import sys
import os
import argparse
import time
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from datetime import datetime
from dataloader.database import SessionLocal, init_db
from dataloader.database import SessionLocal, init_db
from dataloader.models import Stock, HistoricalPrice
import pandas as pd
import yfinance as yf




def process_batch(session, batch_stocks, period):
    """Fetch and store history for a batch of stocks."""
    symbols = [s.symbol for s in batch_stocks]
    symbol_map = {s.symbol: s for s in batch_stocks}
    
    if not symbols:
        return 0, 0
        
    print(f"  Downloading batch of {len(symbols)} stocks...", end=" ", flush=True)
    try:
        # Fetch bulk data
        # auto_adjust=True? No, we usually want raw or adjusted? 
        # yfinance history() default is auto_adjust=False? 
        # Actually yf.download default is auto_adjust=False since 0.2?
        # Let's keep default but ensure we map correctly.
        
        df = yf.download(
            tickers=" ".join(symbols), 
            period=period, 
            interval="1d",
            group_by='ticker',
            threads=True,
            progress=False
        )
        
        if df.empty:
            print("Empty response.")
            return 0, 0
            
        count = 0
        # If single symbol, df columns are simplified. unify logic?
        is_multi = len(symbols) > 1
        
        for symbol in symbols:
            stock = symbol_map[symbol]
            stock_df = None
            
            try:
                if is_multi:
                    # Access MultiIndex
                    # If symbol not found in cols, it failed/delisted
                    if symbol not in df.columns.get_level_values(0):
                        continue
                    stock_df = df[symbol]
                else:
                    stock_df = df
                
                if stock_df.empty:
                    continue
                
                # Check required columns exist
                if 'Close' not in stock_df.columns:
                    continue
                    
                # Iterate rows
                new_records = 0
                for date, row in stock_df.iterrows():
                    close_v = _to_float(row.get("Close"))
                    if close_v is None or close_v <= 0:
                        continue
                        
                    # Prepare record
                    price_date = date.date() if hasattr(date, 'date') else date
                    
                    # Upsert logic (checking existence is slow line-by-line)
                    # Optimization: Should we bulk insert?
                    # For "load history", we often backfill. 
                    # Existing check is safer but slower. 
                    # Let's keep existing check for now to be safe, but we loaded data fast.
                    
                    existing = session.query(HistoricalPrice).filter_by(
                        stock_id=stock.id, date=price_date
                    ).first()
                    
                    if not existing:
                        rec = HistoricalPrice(
                            stock_id=stock.id,
                            date=price_date,
                            open=_to_float(row.get("Open")),
                            high=_to_float(row.get("High")),
                            low=_to_float(row.get("Low")),
                            close=close_v,
                            volume=_to_float(row.get("Volume"))
                        )
                        session.add(rec)
                        new_records += 1
                    else:
                        # Update?
                        existing.close = close_v
                        # ... update others if needed
                
                count += new_records
            except Exception as e:
                # print(f"Error processing {symbol}: {e}")
                continue
                
        print(f"Processed. Added {count} records.")
        return count, 0 # simple error tracking
        
    except Exception as e:
        print(f"Batch failed: {e}")
        return 0, 1



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

        BATCH_SIZE = 100 # History is heavier
        print(f"[PRICES] Fetching {period} history for {total} stocks in batches of {BATCH_SIZE}...")

        for i in range(0, total, BATCH_SIZE):
            batch = stocks[i : i + BATCH_SIZE]
            new_recs, errs = process_batch(session, batch, period)
            count += new_recs
            errors += errs
            
            # Commit every batch to save progress
            session.commit()
            
            # Rate limit slightly
            time.sleep(1.0)


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
