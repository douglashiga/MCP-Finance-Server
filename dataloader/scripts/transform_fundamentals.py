#!/usr/bin/env python3
"""
Transform Fundamentals — Normalizes raw Yahoo fundamental data into fundamentals table.
Triggered after extract_yahoo_fundamentals.py completes.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import json
from datetime import datetime
from dataloader.database import SessionLocal
from dataloader.models import Stock, RawYahooFundamental, Fundamental


def main():
    session = SessionLocal()
    count = 0
    
    try:
        # Get the latest raw fundamental record for each symbol
        latest_raw_fundamentals = session.query(RawYahooFundamental).order_by(
            RawYahooFundamental.symbol, RawYahooFundamental.fetched_at.desc()
        ).all()
        
        # Group by symbol and take only the most recent
        symbol_to_raw = {}
        for raw in latest_raw_fundamentals:
            if raw.symbol not in symbol_to_raw:
                symbol_to_raw[raw.symbol] = raw
        
        print(f"[TRANSFORM FUNDAMENTALS] Processing {len(symbol_to_raw)} symbols...")
        
        for symbol, raw_record in symbol_to_raw.items():
            try:
                # Parse JSON
                data = json.loads(raw_record.data)
                
                # Find corresponding stock
                stock = session.query(Stock).filter_by(symbol=symbol).first()
                if not stock:
                    print(f"  ⚠️  Stock {symbol} not found in database", file=sys.stderr)
                    continue
                
                # Calculate net debt
                total_debt = data.get("totalDebt")
                total_cash = data.get("totalCash")
                net_debt = None
                if total_debt is not None and total_cash is not None:
                    net_debt = total_debt - total_cash
                
                # Create new fundamental record
                fundamental = Fundamental(
                    stock_id=stock.id,
                    fetched_at=raw_record.fetched_at,
                    market_cap=data.get("marketCap"),
                    enterprise_value=data.get("enterpriseValue"),
                    trailing_pe=data.get("trailingPE"),
                    forward_pe=data.get("forwardPE"),
                    trailing_eps=data.get("trailingEps"),
                    forward_eps=data.get("forwardEps"),
                    peg_ratio=data.get("pegRatio"),
                    price_to_book=data.get("priceToBook"),
                    revenue=data.get("totalRevenue"),
                    revenue_growth=data.get("revenueGrowth"),
                    gross_margin=data.get("grossMargins"),
                    operating_margin=data.get("operatingMargins"),
                    net_margin=data.get("profitMargins"),
                    roe=data.get("returnOnEquity"),
                    roa=data.get("returnOnAssets"),
                    debt_to_equity=data.get("debtToEquity"),
                    current_ratio=data.get("currentRatio"),
                    total_debt=total_debt,
                    total_cash=total_cash,
                    net_debt=net_debt,
                    free_cash_flow=data.get("freeCashflow"),
                    ebitda=data.get("ebitda"),
                )
                
                session.add(fundamental)
                count += 1
                
            except Exception as e:
                print(f"  ⚠️  Failed to transform {symbol}: {e}", file=sys.stderr)
                continue
        
        session.commit()
        print(f"[TRANSFORM FUNDAMENTALS] Transformed {count} fundamental records")
        print(f"RECORDS_AFFECTED={count}")
        
    except Exception as e:
        session.rollback()
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
