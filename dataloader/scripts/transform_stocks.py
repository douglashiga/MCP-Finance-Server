#!/usr/bin/env python3
"""
Transform Stocks (ELT Transformer)
Reads from: raw_b3_stocks, raw_us_stocks, raw_omx_stocks
Writes to: stocks, index_components
"""
import sys
import os
import json
from datetime import datetime
from sqlalchemy.dialects.postgresql import insert

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dataloader.database import SessionLocal, init_db
from dataloader.models import Stock, IndexComponent, RawB3Stock, RawUSStock, RawOMXStock

# Exchange code mapping for US 'other' listed
EXCHANGE_MAP = {
    "N": "NYSE",
    "A": "AMEX",
    "P": "NYSE ARCA",
    "Z": "BATS",
    "V": "IEX",
}

def clean_b3_symbol(ticker):
    """Ensure B3 ticker has .SA suffix."""
    ticker = ticker.strip()
    if not ticker.endswith(".SA"):
        return f"{ticker}.SA"
    return ticker

def get_or_create_stock(session, symbol, name, exchange, sector=None, industry=None, currency="USD", country="USA"):
    """Upsert stock record."""
    stock = session.query(Stock).filter_by(symbol=symbol).first()
    if not stock:
        stock = Stock(
            symbol=symbol,
            name=name[:200], # Trucate to fit
            exchange=exchange,
            sector=sector,
            industry=industry,
            currency=currency,
            country=country
        )
        session.add(stock)
        session.flush()
        return stock, True
    else:
        # Update fields if changed (lightweight check)
        updated = False
        if stock.name != name[:200]:
            stock.name = name[:200]
            updated = True
        if sector and stock.sector != sector:
            stock.sector = sector
            updated = True
        return stock, updated

def add_index_membership(session, stock_id, index_name):
    """Ensure stock is in the index."""
    # First check pending objects in session to avoid unnecessary flushes/constraint errors
    for obj in session.new:
        if isinstance(obj, IndexComponent) and obj.stock_id == stock_id and obj.index_name == index_name:
            return

    # Then check database
    exists = session.query(IndexComponent).filter_by(stock_id=stock_id, index_name=index_name).first()
    if not exists:
        session.add(IndexComponent(stock_id=stock_id, index_name=index_name))

def process_b3(session):
    print("[TRANSFORM] Processing B3 stocks...")
    raw_rows = session.query(RawB3Stock).all()
    count = 0
    for row in raw_rows:
        try:
            data = json.loads(row.data)
            ticker = data.get("codNeg", "").strip()
            name = data.get("nomeCurto", "").strip()
            
            # Filter: Only stocks (usually ending in 3, 4, 11) per user original preference?
            # User later said "TODAS as acoes" (ALL stocks). 
            # But B3 list includes options, futures, etc?
            # The API description says "tickers-cash-market", so it should be spot market.
            # It includes ETFs (11), BDRs (34), Stocks (3, 4).
            # We will include ALL.
            
            symbol = clean_b3_symbol(ticker)
            stock, _ = get_or_create_stock(
                session, symbol, name, "B3",
                currency="BRL", country="Brazil"
            )
            add_index_membership(session, stock.id, "B3_ALL")
            
            # Rough heuristic for IBOV (not accurate, but useful for filtering)
            # if ticker.endswith("3") or ticker.endswith("4") or ticker.endswith("11"):
            #     pass 
            count += 1
        except Exception as e:
            print(f"Error processing B3 row {row.cod_neg}: {e}")
            continue
    print(f"[TRANSFORM] B3 processed: {count}")
    return count

def process_us(session):
    print("[TRANSFORM] Processing US stocks...")
    raw_rows = session.query(RawUSStock).all()
    count = 0
    for row in raw_rows:
        try:
            data = json.loads(row.data)
            symbol = row.symbol.strip()
            name = data.get("Security Name", "") or data.get("Security Name\r", "")
            
            # Clean name
            name = name.replace("\r", "").strip()
            
            exchange = "NASDAQ"
            if row.source == "OTHER":
                exch_code = data.get("Exchange") or data.get("Exchange\r")
                if exch_code:
                     exchange = EXCHANGE_MAP.get(exch_code.strip(), "NYSE")
                else:
                    exchange = "NYSE" # Default fallback
            
            stock, _ = get_or_create_stock(
                session, symbol, name, exchange,
                currency="USD", country="USA"
            )
            
            # Add to broad US index
            add_index_membership(session, stock.id, "US_ALL")
            
            # S&P500 approximation? No, let's just leave US_ALL for now.
            count += 1
        except Exception as e:
            print(f"Error processing US row {row.symbol}: {e}")
            continue
    print(f"[TRANSFORM] US processed: {count}")
    return count

def process_omx(session):
    print("[TRANSFORM] Processing OMX stocks...")
    raw_rows = session.query(RawOMXStock).all()
    count = 0
    for row in raw_rows:
        try:
            data = json.loads(row.data)
            symbol = row.symbol
            name = data.get("name", "")
            sector = data.get("sector")
            industry = data.get("industry")
            
            stock, _ = get_or_create_stock(
                session, symbol, name, "OMX",
                sector=sector, industry=industry,
                currency="SEK", country="Sweden"
            )
            
            add_index_membership(session, stock.id, "OMXS30") # Since our source IS OMXS30 list
            count += 1
        except Exception as e:
            print(f"Error processing OMX row {row.symbol}: {e}")
            continue
    print(f"[TRANSFORM] OMX processed: {count}")
    return count

def main():
    init_db()
    session = SessionLocal()
    
    try:
        total = 0
        total += process_omx(session)
        total += process_b3(session)
        total += process_us(session)
        
        session.commit()
        print(f"[TRANSFORM] Finished. Total processed: {total}")
        print(f"RECORDS_AFFECTED={total}")
        
    except Exception as e:
        session.rollback()
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        session.close()

if __name__ == "__main__":
    main()
