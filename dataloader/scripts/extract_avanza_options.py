#!/usr/bin/env python3
import sys
import os
import json
import logging
import asyncio
import requests
import time
from datetime import datetime, date
from typing import List, Dict, Any, Optional

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from dataloader.database import SessionLocal
from dataloader.models import Stock, OptionContract, OptionMetric

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger("extract_avanza_options")

AVANZA_API_BASE = "https://www.avanza.se/_api"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Content-Type": "application/json"
}

def _to_float(val):
    if val is None or val == "—": return None
    try:
        if isinstance(val, str):
            val = val.replace(",", ".").replace(" ", "")
        return float(val)
    except: return None

def _to_int(val):
    if val is None or val == "—": return None
    try:
        if isinstance(val, str):
            val = val.replace(" ", "")
        return int(val)
    except: return None

def fetch_with_retry(url, method="GET", payload=None, params=None, retries=3, backoff=2):
    for i in range(retries):
        try:
            if method == "POST":
                resp = requests.post(url, json=payload, headers=HEADERS, timeout=20)
            else:
                resp = requests.get(url, params=params, headers=HEADERS, timeout=20)
            
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 400:
                 logger.error(f"Bad Request (400) for {url}: {resp.text}")
                 return None
            else:
                logger.warning(f"Attempt {i+1} failed for {url}: Status {resp.status_code}")
        except Exception as e:
            logger.warning(f"Attempt {i+1} failed for {url}: {e}")
        
        if i < retries - 1:
            time.sleep(backoff * (i + 1))
    return None

def get_avanza_id(query: str) -> Optional[str]:
    """Search for the Avanza orderbookId for an underlying symbol."""
    try:
        url = f"{AVANZA_API_BASE}/search/filtered-search"
        clean_query = query.split(".")[0].upper()
        payload = {
            "query": clean_query,
            "searchFilter": {"types": ["STOCK"]},
            "screenSize": "DESKTOP",
            "pagination": {"from": 0, "size": 10}
        }
        data = fetch_with_retry(url, method="POST", payload=payload)
        if data:
            logger.info(f"Avanza search for '{clean_query}' returned {len(data.get('hits', []))} hits")
            for hit in data.get("hits", []):
                # Prefer exact ticker match or title match
                hit_title = hit.get("title", "").upper()
                if clean_query in hit_title:
                    logger.info(f"Selected Hit: {hit.get('title')} | ID: {hit.get('orderBookId')}")
                    return hit.get("orderBookId")
            
            if data.get("hits"):
                first_hit = data["hits"][0]
                return first_hit.get("orderBookId")
        return None
    except Exception as e:
        logger.error(f"Error searching Avanza ID for {query}: {e}")
        return None

def fetch_option_matrix(underlying_id: str) -> List[int]:
    """Fetch the option chain matrix orderbook IDs."""
    url = f"{AVANZA_API_BASE}/market-option-future-forward-list/matrix"
    # Try multiple payload variations based on debug findings
    payloads = [
        {"underlyingId": underlying_id},
        {"underlyingOrderbookId": int(underlying_id)},
        {"underlyingOrderbookId": int(underlying_id), "instrumentType": "OPTION_STOCK"}
    ]
    
    for payload in payloads:
        data = fetch_with_retry(url, method="POST", payload=payload, retries=1)
        if data:
            # The matrix can have 'matrix' key or be the root
            matrix_data = data.get("matrix", {}) if isinstance(data, dict) else {}
            rows = matrix_data.get("rows", [])
            if not rows and isinstance(data, list):
                rows = data
            
            ids = []
            for row in rows:
                for col in ["call", "put"]:
                    opt = row.get(col)
                    if opt and opt.get("orderbookId"):
                        ids.append(int(opt["orderbookId"]))
            if ids:
                return ids
    return []

def fetch_option_details(orderbook_ids: List[int]) -> List[Dict[str, Any]]:
    """Fetch detailed metrics (Greeks, etc.) for a list of option IDs."""
    if not orderbook_ids:
        return []
    
    results = []
    chunk_size = 50
    for i in range(0, len(orderbook_ids), chunk_size):
        chunk = orderbook_ids[i:i+chunk_size]
        ids_str = ",".join(map(str, chunk))
        # Try different formats for listing details
        url = f"{AVANZA_API_BASE}/market-guide/option/list?orderbookIds={ids_str}"
        data = fetch_with_retry(url, method="GET")
        if data:
            results.extend(data)
        else:
            # Try POST if GET fails
            url_post = f"{AVANZA_API_BASE}/market-guide/option/list"
            data_post = fetch_with_retry(url_post, method="POST", payload=chunk)
            if data_post:
                results.extend(data_post)
            
    return results

async def process_stock_options(session, stock, test=False):
    # 1. Get Avanza ID
    search_term = stock.symbol.split(".")[0]
    avanza_underlying_id = get_avanza_id(search_term)
    
    if not avanza_underlying_id:
        logger.warning(f"Could not find Avanza ID for {stock.symbol}")
        return 0
        
    logger.info(f"Found Avanza ID {avanza_underlying_id} for {stock.symbol}. Fetching matrix...")
    
    # 2. Get Matrix (discover IDs)
    option_ids = fetch_option_matrix(avanza_underlying_id)
    if not option_ids:
        logger.info(f"No options found for {stock.symbol}")
        return 0
    
    logger.info(f"Found {len(option_ids)} options for {stock.symbol}. Fetching details...")
    
    # 3. Get Details (Greeks, bid/ask)
    details = fetch_option_details(option_ids)
    
    count = 0
    for opt in details:
        try:
            name = opt.get("name")
            orderbook_id = int(opt["orderbookId"])
            strike = _to_float(opt.get("strikePrice"))
            expiry_str = opt.get("expirationDate")
            right = "CALL" if "CALL" in opt.get("instrumentType", "") else "PUT"
            
            if not name or not strike or not expiry_str:
                continue
                
            expiry = datetime.strptime(expiry_str, "%Y-%m-%d").date()
            
            # 1. Upsert OptionContract
            contract = session.query(OptionContract).filter_by(
                provider="AVANZA", con_id=orderbook_id
            ).first()
            
            if not contract:
                contract = OptionContract(
                    stock_id=stock.id,
                    provider="AVANZA",
                    con_id=orderbook_id,
                    symbol=stock.symbol,
                    local_symbol=name,
                    strike=strike,
                    right=right,
                    expiry=expiry,
                    exchange=stock.exchange,
                    currency="SEK"
                )
                session.add(contract)
                session.flush() # get ID
            
            # 2. Upsert OptionMetric
            quote = opt.get("quote", {})
            advanced = opt.get("advancedOptionData", {}) or {}
            greeks = advanced.get("greeks", {}) or {}
            
            m = {
                "stock_id": stock.id,
                "option_contract_id": contract.id,
                "option_symbol": name,
                "strike": strike,
                "right": right,
                "expiry": expiry,
                "bid": _to_float(quote.get("buy")),
                "ask": _to_float(quote.get("sell")),
                "last": _to_float(quote.get("last")),
                "volume": _to_int(quote.get("totalVolumeTraded")),
                "delta": _to_float(greeks.get("delta")),
                "gamma": _to_float(greeks.get("gamma")),
                "theta": _to_float(greeks.get("theta")),
                "vega": _to_float(greeks.get("vega")),
                "iv": _to_float(advanced.get("implicitVolatility")),
                "updated_at": datetime.utcnow()
            }
            
            existing = session.query(OptionMetric).filter_by(
                option_contract_id=contract.id
            ).first()
            
            if existing:
                for k, v in m.items():
                    setattr(existing, k, v)
            else:
                session.add(OptionMetric(**m))
            
            count += 1
        except Exception as e:
            logger.error(f"Error processing option {opt.get('name')}: {e}")
            continue
            
    session.commit()
    logger.info(f"Updated {count} options for {stock.symbol} via Avanza")
    return count

async def main(market="OMX", test=False, symbol=None):
    session = SessionLocal()
    total_count = 0
    try:
        # Get stocks for the market
        if symbol:
            stocks = session.query(Stock).filter(Stock.symbol.ilike(f"%{symbol}%")).all()
        else:
            stocks = session.query(Stock).filter_by(exchange=market).all()
            
        if test:
            stocks = stocks[:1]
        
        logger.info(f"Processing {len(stocks)} stocks for {market} on Avanza...")
        
        for stock in stocks:
            total_count += await process_stock_options(session, stock, test)
        
        return total_count
            
    finally:
        session.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", default="OMX")
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()
    
    total = asyncio.run(main(market=args.market, test=args.test, symbol=args.symbol))
    print(f"RECORDS_AFFECTED={total}")
