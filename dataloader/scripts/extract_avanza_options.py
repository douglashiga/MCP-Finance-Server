#!/usr/bin/env python3
import sys
import os
import json
import logging
import asyncio
import requests
from datetime import datetime, date
from typing import List, Dict, Any, Optional

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from dataloader.database import SessionLocal
from dataloader.models import Stock, OptionContract, OptionMetric

logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
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
        resp = requests.post(url, json=payload, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            logger.info(f"Avanza search for '{clean_query}' returned {len(data.get('hits', []))} hits")
            for hit in data.get("hits", []):
                logger.info(f"Hit: {hit.get('title')} | Type: {hit.get('type')} | ID: {hit.get('orderBookId')}")
                if hit.get("title", "").upper() == clean_query:
                    return hit.get("orderBookId")
            
            if data.get("hits"):
                first_hit = data["hits"][0]
                return first_hit.get("orderBookId")
        else:
            logger.error(f"Avanza search error: {resp.status_code} {resp.text}")
        return None
    except Exception as e:
        logger.error(f"Error searching Avanza ID for {query}: {e}")
        return None

def fetch_option_matrix(underlying_id: str) -> List[Dict[str, Any]]:
    """Fetch the option chain matrix for an underlying."""
    try:
        url = f"{AVANZA_API_BASE}/market-option-future-forward-list/matrix"
        payload = {"underlyingId": underlying_id}
        resp = requests.post(url, json=payload, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            # The matrix contains rows with call and put info
            # We need to extract the orderbookIds
            ids = []
            for row in data.get("matrix", {}).get("rows", []):
                for col in ["call", "put"]:
                    opt = row.get(col)
                    if opt and opt.get("orderbookId"):
                        ids.append(opt["orderbookId"])
            return ids
        return []
    except Exception as e:
        logger.error(f"Error fetching matrix for {underlying_id}: {e}")
        return []

def fetch_option_details(orderbook_ids: List[str]) -> List[Dict[str, Any]]:
    """Fetch detailed metrics (Greeks, etc.) for a list of option IDs."""
    if not orderbook_ids:
        return []
    
    results = []
    # Avanza allows batching in /list
    chunk_size = 50
    for i in range(0, len(orderbook_ids), chunk_size):
        chunk = orderbook_ids[i:i+chunk_size]
        ids_str = ",".join(chunk)
        url = f"{AVANZA_API_BASE}/market-guide/option/list?orderbookIds={ids_str}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                results.extend(resp.json())
        except Exception as e:
            logger.error(f"Error fetching option details chunk: {e}")
            
    return results

async def main(market="OMX", test=False):
    session = SessionLocal()
    count = 0
    try:
        # Get stocks for the market
        query = session.query(Stock).filter_by(exchange=market)
        if test:
            query = query.limit(1)
        
        stocks = query.all()
        logger.info(f"Processing {len(stocks)} stocks for {market} on Avanza...")
        
        for stock in stocks:
            # 1. Get Avanza ID
            # Use base symbol (e.g. ABB for ABB.ST)
            search_term = stock.symbol.split(".")[0]
            avanza_underlying_id = get_avanza_id(search_term)
            
            if not avanza_underlying_id:
                logger.warning(f"Could not find Avanza ID for {stock.symbol}")
                continue
                
            logger.info(f"Found Avanza ID {avanza_underlying_id} for {stock.symbol}. Fetching matrix...")
            
            # 2. Get Matrix (discover IDs)
            option_ids = fetch_option_matrix(avanza_underlying_id)
            if not option_ids:
                logger.info(f"No options found for {stock.symbol}")
                continue
            
            logger.info(f"Found {len(option_ids)} options for {stock.symbol}. Fetching details...")
            
            # 3. Get Details (Greeks, bid/ask)
            details = fetch_option_details(option_ids)
            
            count = 0
            for opt in details:
                # Map to our models
                # Avanza fields:
                # name: "ABB6C590"
                # strikePrice: 590
                # expirationDate: "2026-03-20"
                # instrumentType: "CALL_OPTION"
                # quote: { buy, sell, last, ... }
                # advancedOptionData: { greeks: { delta, gamma, theta, vega }, implicitVolatility }
                
                name = opt.get("name")
                strike = _to_float(opt.get("strikePrice"))
                expiry_str = opt.get("expirationDate")
                right = "CALL" if opt.get("instrumentType") == "CALL_OPTION" else "PUT"
                exchange = market
                
                if not name or not strike or not expiry_str:
                    continue
                    
                expiry = datetime.strptime(expiry_str, "%Y-%m-%d").date()
                
                # 1. Upsert OptionContract
                # We use provider='AVANZA' and con_id=orderbookId
                orderbook_id = int(opt["orderbookId"])
                
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
                        exchange=exchange,
                        currency="SEK" # Assuming OMX is SEK
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
            
            session.commit()
            logger.info(f"Updated {count} options for {stock.symbol} via Avanza")
        
        return count
            
    finally:
        session.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", default="OMX")
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()
    
    total = asyncio.run(main(market=args.market, test=args.test))
    print(f"RECORDS_AFFECTED={total}")
