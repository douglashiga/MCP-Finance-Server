#!/usr/bin/env python3
"""
Transform IBKR Prices — Normalizes raw IBKR price data into realtime_prices table.
Merges with Yahoo data (Yahoo is fallback if IBKR has no subscription).
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import json
from datetime import datetime
from dataloader.database import SessionLocal
from dataloader.models import Stock, RawIBKRPrice, RawYahooPrice, RealtimePrice


def main():
    session = SessionLocal()
    count = 0
    
    try:
        # Get the latest raw IBKR price record for each symbol
        latest_ibkr = session.query(RawIBKRPrice).order_by(
            RawIBKRPrice.symbol, RawIBKRPrice.fetched_at.desc()
        ).all()
        
        # Group by symbol and take only the most recent
        symbol_to_ibkr = {}
        for raw in latest_ibkr:
            if raw.symbol not in symbol_to_ibkr:
                symbol_to_ibkr[raw.symbol] = raw
        
        # Also get Yahoo data as fallback
        latest_yahoo = session.query(RawYahooPrice).order_by(
            RawYahooPrice.symbol, RawYahooPrice.fetched_at.desc()
        ).all()
        
        symbol_to_yahoo = {}
        for raw in latest_yahoo:
            if raw.symbol not in symbol_to_yahoo:
                symbol_to_yahoo[raw.symbol] = raw
        
        print(f"[TRANSFORM IBKR PRICES] Processing {len(symbol_to_ibkr)} IBKR symbols...")
        
        for symbol, raw_record in symbol_to_ibkr.items():
            try:
                # Parse JSON
                data = json.loads(raw_record.data)
                
                # Find corresponding stock
                stock = session.query(Stock).filter_by(symbol=symbol).first()
                if not stock:
                    print(f"  ⚠️  Stock {symbol} not found in database", file=sys.stderr)
                    continue
                
                # Use IBKR data if available, otherwise fallback to Yahoo
                price = data.get("price")
                close_price = data.get("close")
                
                # If IBKR has no data, try Yahoo fallback
                if not price and symbol in symbol_to_yahoo:
                    yahoo_data = json.loads(symbol_to_yahoo[symbol].data)
                    price = yahoo_data.get("regularMarketPrice")
                    close_price = yahoo_data.get("regularMarketPreviousClose")
                
                # Calculate change
                change = None
                change_percent = None
                if price and close_price:
                    change = price - close_price
                    change_percent = (change / close_price) * 100 if close_price != 0 else None
                
                # Upsert into realtime_prices
                realtime = session.query(RealtimePrice).filter_by(stock_id=stock.id).first()
                
                if realtime:
                    # Update existing
                    realtime.price = price
                    realtime.open = data.get("open") if "open" in data else realtime.open
                    realtime.high = data.get("high") if "high" in data else realtime.high
                    realtime.low = data.get("low") if "low" in data else realtime.low
                    realtime.volume = data.get("volume")
                    realtime.change = change
                    realtime.change_percent = change_percent
                    realtime.currency = data.get("currency")
                    realtime.market_state = "IBKR"
                    realtime.last_updated = raw_record.fetched_at
                else:
                    # Insert new
                    realtime = RealtimePrice(
                        stock_id=stock.id,
                        price=price,
                        open=data.get("open"),
                        high=data.get("high"),
                        low=data.get("low"),
                        volume=data.get("volume"),
                        change=change,
                        change_percent=change_percent,
                        currency=data.get("currency"),
                        market_state="IBKR",
                        last_updated=raw_record.fetched_at
                    )
                    session.add(realtime)
                
                count += 1
                
            except Exception as e:
                print(f"  ⚠️  Failed to transform {symbol}: {e}", file=sys.stderr)
                continue
        
        session.commit()
        print(f"[TRANSFORM IBKR PRICES] Transformed {count} price records")
        print(f"RECORDS_AFFECTED={count}")
        
    except Exception as e:
        session.rollback()
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
