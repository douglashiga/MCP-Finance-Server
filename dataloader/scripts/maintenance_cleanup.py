#!/usr/bin/env python3
"""
Maintenance Cleanup — Performs periodic cleanup of data quality logs and deactivates dead instruments.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import argparse
import logging
from datetime import datetime, timedelta
from typing import List
from dataloader.database import SessionLocal
from dataloader.models import Stock, DataQualityLog, RawYahooPrice, OptionMetric, OptionContract

# Configure logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Don't perform deletions, just report")
    parser.add_argument("--days", type=int, default=3, help="Keep logs for this many days")
    args = parser.parse_args()
    
    session = SessionLocal()
    
    try:
        # 1. Identify stocks with consistent NaN prices
        # We look for stocks that have 'invalid_value' logs but NO successful 'RawYahooPrice' records.
        logger.info("Identifying stocks with chronic data quality issues...")
        
        problematic_stock_ids = session.query(DataQualityLog.stock_id).filter(
            DataQualityLog.issue_type == 'invalid_value'
        ).distinct().all()
        
        problematic_stock_ids = [r[0] for r in problematic_stock_ids if r[0] is not None]
        
        deactivated_count = 0
        for stock_id in problematic_stock_ids:
            stock = session.query(Stock).get(stock_id)
            if not stock or not stock.is_active:
                continue
            
            # Check if it ever had a successful price fetch
            has_success = session.query(RawYahooPrice).filter(RawYahooPrice.symbol == stock.symbol).limit(1).first()
            
            if not has_success:
                logger.info(f"Deactivating {stock.symbol}: No successful price history found and logging NaN.")
                if not args.dry_run:
                    stock.is_active = False
                    stock.track_prices = False
                    stock.track_options = False
                deactivated_count += 1
        
        # 2. Purge old logs
        cutoff = datetime.utcnow() - timedelta(days=args.days)
        logger.info(f"Purging logs older than {cutoff}...")
        
        if not args.dry_run:
            deleted_logs = session.query(DataQualityLog).filter(DataQualityLog.created_at < cutoff).delete()
            # Also purge any remaining 'invalid_value' for non-active stocks
            inactive_stock_ids = session.query(Stock.id).filter(Stock.is_active == False)
            extra_deleted = session.query(DataQualityLog).filter(
                DataQualityLog.stock_id.in_(inactive_stock_ids),
                DataQualityLog.issue_type == 'invalid_value'
            ).delete(synchronize_session=False)
            
            logger.info(f"Deleted {deleted_logs + extra_deleted} log records.")
        else:
            log_count = session.query(DataQualityLog).filter(DataQualityLog.created_at < cutoff).count()
            logger.info(f"[DRY RUN] Would delete {log_count} log records.")

        # 3. Clean up stale/invalid options
        # Remove OptionMetric entries that have NULL/NaN bid, ask AND last.
        logger.info("Cleaning up invalid option metrics (no market data)...")
        if not args.dry_run:
            invalid_options = session.query(OptionMetric).filter(
                OptionMetric.bid.is_(None),
                OptionMetric.ask.is_(None),
                OptionMetric.last.is_(None)
            ).delete()
            logger.info(f"Deleted {invalid_options} invalid option records.")
        
        session.commit()
        logger.info(f"Maintenance complete. Deactivated: {deactivated_count}")
        
    except Exception as e:
        session.rollback()
        logger.error(f"Maintenance error: {e}")
        sys.exit(1)
    finally:
        session.close()

if __name__ == "__main__":
    main()
