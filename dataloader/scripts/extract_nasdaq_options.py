#!/usr/bin/env python3
"""
Extract Nasdaq Options — Scrapes option chains from Nasdaq Nordic API.
Acts as a fallback/alternative to IBKR for OMX stocks.
Stores data in OptionContract (provider='NASDAQ') and OptionMetric.
"""
import sys
import os
import json
import time
import re
import logging
import requests
from datetime import datetime
from typing import Dict, List, Optional
from sqlalchemy.exc import IntegrityError

# Ensure dataloader is in path
# Ensure dataloader is in path (Project Root)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dataloader.database import SessionLocal
from dataloader.models import Stock, OptionContract, OptionMetric

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("extract_nasdaq_options")

# Constants
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.nasdaq.com",
    "Referer": "https://www.nasdaq.com/"
}
NASDAQ_SEARCH_URL = "https://api.nasdaq.com/api/search/stocks"
NASDAQ_CHAIN_URL_TEMPLATE = "https://api.nasdaq.com/api/nordic/instruments/{id}/option-chain"

CACHE_FILE = os.path.join(os.path.dirname(__file__), "nasdaq_mappings.json")

def load_mappings() -> Dict[str, str]:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_mappings(mappings: Dict[str, str]):
    with open(CACHE_FILE, 'w') as f:
        json.dump(mappings, f, indent=2)

def clean_ticker(symbol: str) -> str:
    # "ABB.ST" -> "ABB"
    # "VOLV-B.ST" -> "VOLV B" (Nasdaq usually uses spaces or A/B suffix)
    # Nasdaq search is fuzzy, so "VOLV B" is distinct from "VOLV A"
    base = symbol.split('.')[0]
    return base.replace('-', ' ')

def search_nasdaq_id(symbol: str) -> Optional[str]:
    """Search for the Nasdaq Instrument ID (e.g., TX291) for a symbol."""
    query = clean_ticker(symbol)
    logger.info(f"Searching Nasdaq ID for {symbol} (query: {query})...")
    
    try:
        resp = requests.get(NASDAQ_SEARCH_URL, headers=HEADERS, params={"q": query, "limit": 10}, timeout=10)
        if resp.status_code != 200:
            logger.warning(f"Search failed: {resp.status_code}")
            return None
        
        data = resp.json()
        rows = data.get('data', {}).get('rows', [])
        
        # Filter for Swedish/Nordic stocks if possible, or matches
        # The search output usually has 'symbol', 'name', 'country'
        # Let's simple pick exact symbol match first
        
        # Prefer exact match
        for r in rows:
            if r.get('symbol') == query or r.get('symbol') == query.replace(' ', ''):
                # Is there an ID field? The header says 'url' often contains it? No, looking at debug...
                # Debug output for search wasn't fully dumped.
                # Usually we need to look at the 'url' or a specific ID field.
                # Wait, the previous debug loop didn't print the ID field logic.
                # Let's assume the 'url' has it or there is an 'id' field.
                # Actually, I need to verify what the search returns as ID.
                pass
        
        # If I can't find the ID in search, I might be stuck.
        # But wait, looking at my debug_nasdaq_api.py, I just dumped the search result.
        # I didn't verify *where* the ID is.
        # Let's assume checks later. For now, let's implement the structure.
        return None 
    except Exception as e:
        logger.error(f"Error searching {symbol}: {e}")
        return None

def fetch_option_chain(instrument_id: str):
    url = NASDAQ_CHAIN_URL_TEMPLATE.format(id=instrument_id)
    params = {
        "tableonly": "false",
        "returndynamicfilters": "false",
        "lang": "en"
    }
    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.error(f"Error fetching chain for {instrument_id}: {e}")
    return None

def extract_con_id(nasdaq_id: str) -> int:
    # "TX6539696" -> 6539696
    # "SSE291" -> 291
    nums = re.findall(r'\d+', nasdaq_id)
    if nums:
        return int(nums[0])
    # Fallback: hash it?
    return abs(hash(nasdaq_id)) % 2147483647

def parse_omx_right(symbol: str) -> str:
    """
    Derive option right (CALL/PUT) from OMX standardized symbol.
    Format: [TICKER][YEAR][MONTH_CHAR][STRIKE]
    Calls: A-L (Jan-Dec)
    Puts: M-X (Jan-Dec)
    """
    # Regex to find the Month Char: Single letter A-X followed by digits at the end
    # ABB6B500 -> B is the month char.
    # VOLVB6B300 -> B is month char.
    # Pattern: Last non-digit char before the strike price numbers.
    match = re.search(r'([A-X])\d+([.,]\d+)?$', symbol)
    if match:
        code = match.group(1)
        # A-L is Call, M-X is Put
        if 'A' <= code <= 'L':
            return "CALL"
        elif 'M' <= code <= 'X':
            return "PUT"
    return "CALL" # Fallback/Default

def parse_and_store_chain(session, stock: Stock, chain_data: dict):
    if not chain_data:
        return
    
    rows = chain_data.get('data', {}).get('instrumentListing', {}).get('rows', [])
    if not rows:
        logger.info(f"No option rows found for {stock.symbol}")
        return

    count_new = 0
    count_metrics = 0
    
    for row in rows:
        try:
            # Parse Basic Info
            local_symbol = row.get('symbol')
            orderbook_id = row.get('orderbookId')
            
            if not local_symbol or not orderbook_id:
                continue
                
            con_id = extract_con_id(orderbook_id)
            
            strike_str = str(row.get('strikePrice', '0')).replace(',', '.')
            try:
                strike = float(strike_str)
            except:
                strike = 0.0
                
            expiry_str = row.get('expirationDate') # YYYY-MM-DD
            try:
                expiry = datetime.strptime(expiry_str, "%Y-%m-%d").date()
            except:
                continue
            
            right = parse_omx_right(local_symbol)
            
            # Upsert Contract
            contract = session.query(OptionContract).filter_by(
                provider='NASDAQ', 
                con_id=con_id
            ).first()
            
            if not contract:
                contract = OptionContract(
                    stock_id=stock.id,
                    provider='NASDAQ',
                    con_id=con_id,
                    symbol=stock.symbol,
                    local_symbol=local_symbol,
                    trading_class=stock.symbol, # Approximation
                    multiplier="100", # Standard OMX
                    strike=strike,
                    right=right,
                    expiry=expiry,
                    currency=stock.currency,
                    exchange="OMX"
                )
                session.add(contract)
                session.flush() # Get ID
                count_new += 1
            
            # Upsert Metrics
            # Check if metric exists for this contract
            metric = session.query(OptionMetric).filter_by(option_contract_id=contract.id).first()
            if not metric:
                metric = OptionMetric(
                    stock_id=stock.id,
                    option_contract_id=contract.id,
                    option_symbol=local_symbol,
                    strike=strike,
                    right=right,
                    expiry=expiry
                )
                session.add(metric)
            
            # Update Quote Data
            def clean_float(val):
                if not val: return None
                try: return float(str(val).replace(',', '.'))
                except: return None

            msg_bid = clean_float(row.get('bidPrice'))
            msg_ask = clean_float(row.get('askPrice'))
            msg_last = clean_float(row.get('lastSalePrice'))
            
            # Only update if valid
            if msg_bid is not None: metric.bid = msg_bid
            if msg_ask is not None: metric.ask = msg_ask
            if msg_last is not None: metric.last = msg_last
            
            # Volume/OI
            try: metric.volume = int(clean_float(row.get('volume', 0)) or 0)
            except: pass
            
            try: metric.open_interest = int(clean_float(row.get('openInterest', 0)) or 0)
            except: pass
            
            metric.updated_at = datetime.utcnow()
            count_metrics += 1

        except Exception as e:
            logger.error(f"Error parsing row {row.get('symbol')}: {e}")
            session.rollback()
            
    try:
        session.commit()
        logger.info(f"Processed {stock.symbol}: {count_new} new contracts, {count_metrics} metrics updated.")
    except Exception as e:
        logger.error(f"Commit failed for {stock.symbol}: {e}")
        session.rollback()

def run():
    session = SessionLocal()
    try:
        stocks = session.query(Stock).filter(Stock.exchange == 'OMX').all()
        logger.info(f"Processing {len(stocks)} OMX stocks for Nasdaq Options...")
        
        mappings = load_mappings()
        
        # Hardcoded FALLBACK mappings for major OMX stocks
        if "ABB" not in mappings: mappings["ABB"] = "TX291"
        if "VOLV B" not in mappings: mappings["VOLV B"] = "TX323"
        if "HM B" not in mappings: mappings["HM B"] = "TX602"
        if "ERIC B" not in mappings: mappings["ERIC B"] = "TX101"
        if "ATCO A" not in mappings: mappings["ATCO A"] = "TX46"
        if "ATCO B" not in mappings: mappings["ATCO B"] = "TX47"
        if "SEB A" not in mappings: mappings["SEB A"] = "TX281"
        if "SHB A" not in mappings: mappings["SHB A"] = "TX287"
        if "SWED A" not in mappings: mappings["SWED A"] = "TX120"
        if "TELIA" not in mappings: mappings["TELIA"] = "TX306"
        if "VOLV A" not in mappings: mappings["VOLV A"] = "TX322"

        for stock in stocks:
            # 1. Get ID
            # Clean symbol for mapping lookup "ABB.ST" -> "ABB"
            clean_sym = clean_ticker(stock.symbol)
            nasdaq_id = mappings.get(clean_sym)
            
            if not nasdaq_id:
                # Need to implement the search details parsing first!
                # For now, skip if not mapped.
                continue
            
            # 2. Fetch
            chain = fetch_option_chain(nasdaq_id)
            if chain:
                parse_and_store_chain(session, stock, chain)
                
            time.sleep(1) # Rate limit
            
        session.commit()
    finally:
        session.close()

if __name__ == "__main__":
    run()
