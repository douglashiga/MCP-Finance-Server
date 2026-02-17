import requests
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Standard headers for Nasdaq
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.nasdaq.com",
    "Referer": "https://www.nasdaq.com/"
}

import sys
import os
# Ensure dataloader is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dataloader.database import SessionLocal
from dataloader.models import Stock

def get_omx_stocks():
    session = SessionLocal()
    try:
        stocks = session.query(Stock).filter(Stock.exchange == 'OMX').all()
        # Return list of tuples (symbol, name) to match previous logic
        return [(s.symbol, s.name) for s in stocks]
    except Exception as e:
        logger.error(f"DB Error: {e}")
        return []
    finally:
        session.close()

def test_nasdaq_endpoint():
    # 1. Fetch stocks from DB
    stocks = get_omx_stocks()
    logger.info(f"Found {len(stocks)} OMX stocks in DB.")
    
    search_url = "https://api.nasdaq.com/api/search/stocks"
    mapping = {}
    
    # Limit to first 5 for testing, or user can remove limit
    failed_count = 0
    
    # Create valid list to iterate (maybe just first 5 for now to test the loop works)
    test_batch = stocks[:5] 
    
    for symbol, name in test_batch:
        logger.info(f"Searching for {symbol} ({name})...")
        
        # Nasdaq search seems to like the Symbol or Name
        # clean symbol? "ABB.ST" -> "ABB"
        clean_symbol = symbol.split(".")[0]
        
        try:
            resp = requests.get(search_url, headers=HEADERS, params={"q": clean_symbol, "limit": 5}, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                # logger.info(f"Result: {str(data)[:100]}...")
                
                # Logic to find the right ID from search results
                # Look for exact symbol match or close name match in Nordic market?
                # The response structure needs to be analyzed from previous dumps.
                # Assuming data['data']['rows'] ...
                
                # For now just dump the raw search to see what we get for these real stocks
                mapping[symbol] = data
            else:
                logger.warning(f"Failed search for {symbol}: {resp.status_code}")
                failed_count += 1
            
            # Be nice to the API
            time.sleep(1)
            
        except Exception as e:
            logger.error(f"Error searching {symbol}: {e}")
            
    # Save results
    with open("nasdaq_mappings_debug.json", "w") as f:
        json.dump(mapping, f, indent=2)
    logger.info("Saved mappings to nasdaq_mappings_debug.json")

    # 2. Test Option Chain (Keep the hardcoded one for now to ensure chain functionality still verified)
    # ... (rest of function)

    # 2. Test Option Chain
    url = "https://api.nasdaq.com/api/nordic/instruments/TX291/option-chain"
    params = {
        "tableonly": "false",
        "returndynamicfilters": "false",
        "lang": "en"
    }

    logger.info(f"Testing Chain URL: {url}")
    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=10)
        logger.info(f"Status Code: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            rows = data.get("data", {}).get("instrumentListing", {}).get("rows", [])
            
            # Check for non-empty bids
            valid_bids = [r for r in rows if r.get("bidPrice")]
            logger.info(f"Total Rows: {len(rows)}")
            logger.info(f"Rows with Bid: {len(valid_bids)}")
            if valid_bids:
                logger.info(f"Sample Valid Bid: {valid_bids[0]}")
            
            # Dump to file
            with open("nasdaq_debug.json", "w") as f:
                json.dump(data, f, indent=2)
                
            # 3. Test Detail for one option (if we have an ID)
            if rows:
                first_id = rows[0].get("orderbookId")
                # Try a detail endpoint guess
                detail_url = f"https://api.nasdaq.com/api/nordic/instruments/{first_id}/details" # Guess
                logger.info(f"Testing Detail URL (Guess): {detail_url}")
                try:
                    d_resp = requests.get(detail_url, headers=HEADERS, timeout=10)
                    if d_resp.status_code == 200:
                         logger.info("Detail Success! " + str(d_resp.json())[:200])
                    else:
                         logger.info(f"Detail Failed: {d_resp.status_code}")
                except:
                    pass

        else:
            logger.info(f"Failed with status {resp.status_code}")

    except Exception as e:
        logger.error(f"Error fetching data: {e}")

if __name__ == "__main__":
    test_nasdaq_endpoint()
