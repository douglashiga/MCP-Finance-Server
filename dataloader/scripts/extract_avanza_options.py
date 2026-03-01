#!/usr/bin/env python3
import sys
import os
import json
import logging
import asyncio
import httpx
import time
from datetime import datetime, date
from typing import List, Dict, Any, Optional

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from dataloader.database import SessionLocal
from dataloader.models import Stock, OptionContract, OptionMetric, Job
from services.data_quality_service import DataQualityService

# Configure logging to be simpler for job logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger("extract_avanza_options")

AVANZA_API_BASE = "https://www.avanza.se/_api"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Origin": "https://www.avanza.se",
    "Referer": "https://www.avanza.se/borshandlade-produkter/optioner-terminer/lista.html"
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

async def fetch_with_retry_async(client, url, method="GET", payload=None, params=None, retries=3, backoff=1):
    for i in range(retries):
        try:
            if method == "POST":
                resp = await client.post(url, json=payload, params=params, timeout=20.0)
            else:
                resp = await client.get(url, params=params, timeout=20.0)
            
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
            await asyncio.sleep(backoff * (i + 1))
    return None

async def get_avanza_id(client: httpx.AsyncClient, query: str) -> Optional[str]:
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
        data = await fetch_with_retry_async(client, url, method="POST", payload=payload)
        if data:
            for hit in data.get("hits", []):
                # Prefer exact ticker match or title match
                hit_title = hit.get("title", "").upper()
                if clean_query in hit_title:
                    return hit.get("orderBookId")
            
            if data.get("hits"):
                return data["hits"][0].get("orderBookId")
        return None
    except Exception as e:
        logger.error(f"Error searching Avanza ID for {query}: {e}")
        return None

async def fetch_option_matrix(client: httpx.AsyncClient, underlying_id: str) -> List[int]:
    """Fetch the option chain matrix orderbook IDs."""
    url = f"{AVANZA_API_BASE}/market-option-future-forward-list/matrix"
    
    payload = {
        "filter": {
            "underlyingInstruments": [str(underlying_id)],
            "optionTypes": [],
            "endDates": [],
            "callIndicators": []
        },
        "offset": 0,
        "limit": 500,  # Increased limit
        "sortBy": {
            "field": "strikePrice",
            "order": "desc"
        }
    }
    
    data = await fetch_with_retry_async(client, url, method="POST", payload=payload)
    if data:
        ids = []
        matched = data.get("matchedOptions", [])
        for row in matched:
            for col in ["call", "put"]:
                opt = row.get(col)
                if opt and opt.get("orderbookId"):
                    ids.append(int(opt["orderbookId"]))
        return ids
    return []

async def fetch_single_option(client: httpx.AsyncClient, oid: int, sem: asyncio.Semaphore) -> Optional[Dict[str, Any]]:
    async with sem:
        url = f"{AVANZA_API_BASE}/market-guide/option/{oid}"
        try:
            resp = await client.get(url, timeout=15.0)
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception as e:
            logger.debug(f"Error fetching option {oid}: {e}")
            return None

async def fetch_option_details(client: httpx.AsyncClient, orderbook_ids: List[int]) -> List[Dict[str, Any]]:
    """Fetch detailed metrics (Greeks, etc.) for a list of option IDs in parallel."""
    if not orderbook_ids:
        return []
    
    sem = asyncio.Semaphore(10) # 10 concurrent requests max
    tasks = [fetch_single_option(client, oid, sem) for oid in orderbook_ids]
    results = await asyncio.gather(*tasks)
    return [r for r in results if r]

def get_job_id(session):
    job = session.query(Job).filter_by(name='Extract Avanza Options').first()
    return job.id if job else None

async def process_stock_options(client, session, stock, job_id, run_id=None):
    # 1. Get Avanza ID
    search_term = stock.symbol.split(".")[0]
    avanza_underlying_id = await get_avanza_id(client, search_term)
    
    if not avanza_underlying_id:
        DataQualityService.log_issue(
            job_id=job_id, run_id=run_id, stock_id=stock.id,
            issue_type="missing_provider_id", severity="warning",
            description=f"Could not find Avanza ID for ticker {stock.symbol}"
        )
        return 0
        
    logger.info(f"Found Avanza ID {avanza_underlying_id} for {stock.symbol}. Fetching matrix...")
    
    # 2. Get Matrix (discover IDs)
    option_ids = await fetch_option_matrix(client, avanza_underlying_id)
    if not option_ids:
        DataQualityService.log_issue(
            job_id=job_id, run_id=run_id, stock_id=stock.id,
            issue_type="no_options_found", severity="info",
            description=f"No options found in Avanza matrix for {stock.symbol}"
        )
        return 0
    
    logger.info(f"Found {len(option_ids)} options for {stock.symbol}. Fetching detailed prices...")
    
    # 3. Get Details (singular parallel calls)
    details = await fetch_option_details(client, option_ids)
    
    count = 0
    for opt in details:
        try:
            name = opt.get("name")
            orderbook_id = int(opt["orderbookId"])
            
            # Key indicators structure in singular response
            ki = opt.get("keyIndicators", {})
            strike = _to_float(ki.get("strikePrice"))
            expiry_str = ki.get("endDate")
            
            # Avanza singular response doesn't always have instrumentType in root, 
            # check name or callIndicator
            call_ind = ki.get("callIndicator", "").upper()
            right = "CALL" if "KÖP" in call_ind or "CALL" in call_ind else "PUT"
            
            if not name or not strike or not expiry_str:
                continue
                
            expiry = datetime.strptime(expiry_str, "%Y-%m-%d").date()
            
            # 1. Upsert OptionContract
            contract = session.query(OptionContract).filter_by(
                provider="AVANZA", con_id=orderbook_id
            ).first()
            
            if not contract:
                contract = OptionContract(
                    stock_id=stock.id, provider="AVANZA", con_id=orderbook_id,
                    symbol=stock.symbol, local_symbol=name, strike=strike,
                    right=right, expiry=expiry, exchange=stock.exchange, currency="SEK"
                )
                session.add(contract)
                session.flush()
            
            # 2. Upsert OptionMetric
            quote = opt.get("quote", {})
            bid = _to_float(quote.get("buy") or quote.get("bid"))
            ask = _to_float(quote.get("sell") or quote.get("ask"))
            
            # Advanced data (Greeks) might be null or in advancedOptionData
            advanced = opt.get("advancedOptionData", {}) or {}
            greeks = advanced.get("greeks", {}) or {}
            
            m = {
                "stock_id": stock.id,
                "option_contract_id": contract.id,
                "option_symbol": name,
                "strike": strike,
                "right": right,
                "expiry": expiry,
                "bid": bid,
                "ask": ask,
                "last": _to_float(quote.get("last")),
                "volume": _to_int(quote.get("totalVolumeTraded")),
                "delta": _to_float(greeks.get("delta")),
                "gamma": _to_float(greeks.get("gamma")),
                "theta": _to_float(greeks.get("theta")),
                "vega": _to_float(greeks.get("vega")),
                "iv": _to_float(advanced.get("implicitVolatility")),
                "updated_at": datetime.utcnow()
            }
            
            existing = session.query(OptionMetric).filter_by(option_contract_id=contract.id).first()
            if existing:
                for k, v in m.items(): setattr(existing, k, v)
            else:
                session.add(OptionMetric(**m))
            
            count += 1
        except Exception as e:
            logger.error(f"Error processing option {opt.get('orderbookId')}: {e}")
            continue
            
    session.commit()
    logger.info(f"Updated {count} options for {stock.symbol} via Avanza")
    return count

async def main(market="OMX", test=False, symbol=None):
    session = SessionLocal()
    total_count = 0
    run_id = os.environ.get("RUN_ID")
    if run_id: run_id = int(run_id)
    
    try:
        job_id = get_job_id(session)
        query = session.query(Stock).filter(Stock.is_active == True)
        
        if symbol:
            query = query.filter(Stock.symbol.ilike(f"%{symbol}%"))
        else:
            query = query.filter(Stock.exchange == market, Stock.track_options == True)
            
        stocks = query.all()
        if test: stocks = stocks[:1]
        
        logger.info(f"Processing {len(stocks)} stocks for {market} on Avanza...")
        
        async with httpx.AsyncClient(headers=HEADERS, timeout=30.0) as client:
            for stock in stocks:
                total_count += await process_stock_options(client, session, stock, job_id, run_id)
        
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
