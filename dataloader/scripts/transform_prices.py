#!/usr/bin/env python3
"""
Transform Prices — Normalizes raw Yahoo price data into realtime_prices table.
Triggered after extract_yahoo_prices.py completes.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import json
from datetime import datetime
from dataloader.database import SessionLocal
from dataloader.models import Stock, RawYahooPrice, RealtimePrice


def main():
    session = SessionLocal()
    count = 0
    
    try:
        # Get the latest raw price record for each symbol
        latest_raw_prices = session.query(RawYahooPrice).order_by(
            RawYahooPrice.symbol, RawYahooPrice.fetched_at.desc()
        ).all()
        
        # Group by symbol and take only the most recent
        symbol_to_raw = {}
        for raw in latest_raw_prices:
            if raw.symbol not in symbol_to_raw:
                symbol_to_raw[raw.symbol] = raw
        
        print(f"[TRANSFORM PRICES] Processing {len(symbol_to_raw)} symbols...")
        
        for symbol, raw_record in symbol_to_raw.items():
            try:
                # Parse JSON
                data = json.loads(raw_record.data)
                
                # Find corresponding stock
                stock = session.query(Stock).filter_by(symbol=symbol).first()
                if not stock:
                    print(f"  ⚠️  Stock {symbol} not found in database", file=sys.stderr)
                    continue
                
                # Calculate change
                price = data.get("regularMarketPrice")
                prev_close = data.get("regularMarketPreviousClose")
                change = None
                change_percent = None
                
                if price and prev_close:
                    change = price - prev_close
                    change_percent = (change / prev_close) * 100 if prev_close != 0 else None
                
                # Upsert into realtime_prices
                realtime = session.query(RealtimePrice).filter_by(stock_id=stock.id).first()
                
                if realtime:
                    # Update existing
                    realtime.price = price
                    realtime.open = data.get("regularMarketOpen")
                    realtime.high = data.get("regularMarketDayHigh")
                    realtime.low = data.get("regularMarketDayLow")
                    realtime.volume = data.get("regularMarketVolume")
                    realtime.change = change
                    realtime.change_percent = change_percent
                    realtime.currency = data.get("currency")
                    realtime.market_state = data.get("marketState")
                    realtime.last_updated = raw_record.fetched_at
                else:
                    # Insert new
                    realtime = RealtimePrice(
                        stock_id=stock.id,
                        price=price,
                        open=data.get("regularMarketOpen"),
                        high=data.get("regularMarketDayHigh"),
                        low=data.get("regularMarketDayLow"),
                        volume=data.get("regularMarketVolume"),
                        change=change,
                        change_percent=change_percent,
                        currency=data.get("currency"),
                        market_state=data.get("marketState"),
                        last_updated=raw_record.fetched_at
                    )
                    session.add(realtime)
                
                count += 1
                
            except Exception as e:
                print(f"  ⚠️  Failed to transform {symbol}: {e}", file=sys.stderr)
                continue
        
        session.commit()
        print(f"[TRANSFORM PRICES] Transformed {count} price records")
        print(f"RECORDS_AFFECTED={count}")
        
    except Exception as e:
        session.rollback()
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
