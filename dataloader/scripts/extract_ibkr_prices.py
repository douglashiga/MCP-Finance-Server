#!/usr/bin/env python3
"""
Extract IBKR Prices — Fetches real-time prices from IB Gateway and stores raw JSON.
Runs every minute for stocks that have IBKR market data subscriptions.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import argparse
import json
import asyncio
from datetime import datetime
from dataloader.database import SessionLocal
from dataloader.models import Stock, RawIBKRPrice
from core.connection import ib_conn
from services.market_service import MarketService


async def main_async():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Run in test mode (1 symbol)")
    args = parser.parse_args()
    
    session = SessionLocal()
    count = 0
    
    try:
        # Connect to IB Gateway
        await ib_conn.connect()
        
        # Get active stocks
        query = session.query(Stock)
        if args.test:
            query = query.limit(1)
        stocks = query.all()
        
        print(f"[EXTRACT IBKR PRICES] Fetching prices for {len(stocks)} stocks from IB Gateway...")
        
        for stock in stocks:
            try:
                # Resolve contract
                contract = await MarketService._resolve_contract(
                    stock.symbol, 
                    stock.exchange, 
                    stock.currency
                )
                
                if not contract or contract.conId == 0:
                    print(f"  ⚠️  Contract not found for {stock.symbol}", file=sys.stderr)
                    continue
                
                # Fetch market data
                mkt_data = await MarketService._fetch_market_data(contract)
                
                if not mkt_data or all(v is None for v in mkt_data.values()):
                    print(f"  ⚠️  No market data for {stock.symbol}", file=sys.stderr)
                    continue
                
                # Store raw JSON
                raw_data = {
                    "symbol": stock.symbol,
                    "conId": contract.conId,
                    "exchange": contract.exchange,
                    "primaryExchange": contract.primaryExchange,
                    "currency": contract.currency,
                    **mkt_data,
                }
                
                raw_record = RawIBKRPrice(
                    symbol=stock.symbol,
                    exchange=stock.exchange,
                    data=json.dumps(raw_data),
                    fetched_at=datetime.utcnow()
                )
                session.add(raw_record)
                count += 1
                
            except Exception as e:
                print(f"  ⚠️  Failed to fetch {stock.symbol}: {e}", file=sys.stderr)
                continue
        
        session.commit()
        print(f"[EXTRACT IBKR PRICES] Extracted {count} price records")
        print(f"RECORDS_AFFECTED={count}")
        
    except Exception as e:
        session.rollback()
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        await ib_conn.shutdown()
        session.close()


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
