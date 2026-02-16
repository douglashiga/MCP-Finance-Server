import requests
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Origin": "https://www.avanza.se",
    "Referer": "https://www.avanza.se/borshandlade-produkter/optioner-terminer/lista.html?underlyingId=5447"
}

ABB_ID = "5447" # Avanza ID for ABB

def test_endpoint(name, url, method="POST", payload=None, params=None):
    logger.info(f"--- Testing {name} ---")
    logger.info(f"URL: {url}")
    try:
        if method == "POST":
            resp = requests.post(url, json=payload, headers=HEADERS, timeout=5)
            logger.info(f"Payload: {json.dumps(payload)}")
        else:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=5)
            logger.info(f"Params: {params}")
        
        logger.info(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            try:
                data = resp.json()
                logger.info("Success! Response keys: " + str(list(data.keys())))
                logger.info("Sample: " + str(data)[:200])
                return data
            except:
                logger.info("Response text (not JSON): " + resp.text[:200])
        else:
            logger.info("Error Response: " + resp.text[:200])
    except Exception as e:
        logger.error(f"Failed: {e}")
    return None

def main():
    # 1. Try filter-options (User suggestion)
    # Trying GET first
    url_filter = "https://www.avanza.se/_api/market-option-future-forward-list/filter-options"
    test_endpoint("Filter Options (GET)", url_filter, method="GET", params={"underlyingId": ABB_ID})
    
    # Trying POST
    test_endpoint("Filter Options (POST)", url_filter, method="POST", payload={"underlyingOrderbookId": ABB_ID})
    test_endpoint("Filter Options (POST v2)", url_filter, method="POST", payload={"id": ABB_ID})
    
    # 2. Try Matrix with various payloads
    url_matrix = "https://www.avanza.se/_api/market-option-future-forward-list/matrix"
    
    # Payload Variation A: "underlyingOrderbookId"
    payload_a = {
        "underlyingOrderbookId": ABB_ID,
        "sortField": "STRIKE_PRICE",
        "sortOrder": "ASCENDING",
        "instrumentType": "OPTION_STOCK"
    }
    test_endpoint("Matrix (Payload A)", url_matrix, method="POST", payload=payload_a)

    # Payload Variation B: "orderbookId"
    payload_b = {
        "orderbookId": ABB_ID,
        "instrumentType": "OPTION_STOCK"
    }
    test_endpoint("Matrix (Payload B)", url_matrix, method="POST", payload=payload_b)
    
    # Payload Variation C: Mimic browser filter state
    payload_c = {
        "underlyingOrderbookId": int(ABB_ID),
        "sortField": "STRIKE_PRICE",
        "sortOrder": "ASCENDING",
        "validForDate": "2024-03-15" # Random future date guess
    }
    test_endpoint("Matrix (Payload C)", url_matrix, method="POST", payload=payload_c)

    # 3. Try Market Guide Stock
    url_stock = f"https://www.avanza.se/_api/market-guide/stock/{ABB_ID}"
    stock_data = test_endpoint("Market Guide Stock", url_stock, method="GET")
    if stock_data:
        logger.info("Stock Data DUMP:")
        logger.info(json.dumps(stock_data, indent=2))
        
    # return # Stop here to analyze

    # 4. Try Financial Activity (sometimes lists related instruments)
    # url_fin = f"https://www.avanza.se/_api/financial-activity/list/{ABB_ID}"
    # test_endpoint("Financial Activity", url_fin, method="GET")
    
    # 5. Try to list options via market-guide/option? (Guessing)
    # Some APIs use /_api/market-guide/option/list with POST ids, but maybe GET works for underlying?
    # url_opt_guide = f"https://www.avanza.se/_api/market-guide/option/underlying/{ABB_ID}"
    # test_endpoint("Market Guide Option Underlying (Guess)", url_opt_guide, method="GET")

    # 6. Retry Matrix with data from filter-options if possible
    # We need to get valid filter values first.
    # The user suggested /filter-options. Let's see if we can make it work.
    # It might need query params for GET.
    # url_filter = "https://www.avanza.se/_api/market-option-future-forward-list/filter-options"
    # Try with underlyingId param (standard for GET)
    # filter_data = test_endpoint("Filter Options (GET params)", url_filter, method="GET", params={"underlyingOrderbookId": ABB_ID})
    
    # if not filter_data:
    #     filter_data = test_endpoint("Filter Options (GET params v2)", url_filter, method="GET", params={"orderbookId": ABB_ID})

    # if filter_data:
    #     logger.info("Got filter data! dumps:")
    #     logger.info(json.dumps(filter_data, indent=2))
        
    #     # Print option types to see potential values
    #     logger.info("Option Types: " + json.dumps(filter_data.get("optionTypes", []), indent=2))

    #     # Dictionary of end dates: value -> displayName
    #     end_dates = filter_data.get("endDates", [])

    #     if end_dates:
    #         # Get a specific date from children
    #         month_obj = end_dates[0]
    #         month_val = month_obj.get("value")
    #         children = month_obj.get("children", [])
    #         specific_date = children[0].get("value") if children else month_val
            
    #         logger.info(f"Testing with month: {month_val} and specific date: {specific_date}")

    #         # Payload H: Specific Date, 'endDate' key
    #         payload_h = {
    #             "underlyingOrderbookId": int(ABB_ID),
    #             "sortField": "STRIKE_PRICE",
    #             "sortOrder": "ASCENDING",
    #             "endDate": specific_date,
    #             "callIndicator": "CALL"
    #         }
    #         test_endpoint("Matrix (Payload H - endDate specific)", url_matrix, method="POST", payload=payload_h)
            
    #         # Payload M: With optionType
    #         payload_m = {
    #             "underlyingOrderbookId": int(ABB_ID),
    #             "sortField": "STRIKE_PRICE",
    #             "sortOrder": "ASCENDING",
    #             "expiryDate": specific_date,
    #             "callIndicator": "CALL",
    #             "optionType": "STANDARD"
    #         }
    #         test_endpoint("Matrix (Payload M - with optionType)", url_matrix, method="POST", payload=payload_m)

    #         # Payload O: Filter wrapper with LISTS
    #         payload_o = {
    #             "filter": {
    #                 "underlyingOrderbookId": int(ABB_ID),
    #                 "expiryDate": [specific_date],
    #                 "callIndicator": ["CALL"],
    #                 "optionType": ["STANDARD"]
    #             },
    #             "sortField": "STRIKE_PRICE",
    #             "sortOrder": "ASCENDING"
    #         }
    #         test_endpoint("Matrix (Payload O - Lists)", url_matrix, method="POST", payload=payload_o)

    #         # Payload P: Filter wrapper with GROUP DATE
    #         payload_p = {
    #             "filter": {
    #                 "underlyingOrderbookId": int(ABB_ID),
    #                 "validForDate": month_val, # 2026-02
    #                 "callIndicator": "CALL",
    #                 "optionType": "STANDARD"
    #             },
    #             "sortField": "STRIKE_PRICE",
    #             "sortOrder": "ASCENDING"
    #         }
    #         test_endpoint("Matrix (Payload P - Group Date)", url_matrix, method="POST", payload=payload_p)

    #         # Payload Q: orderbookId instead of underlying
    #         payload_q = {
    #             "filter": {
    #                 "orderbookId": int(ABB_ID),
    #                 "expiryDate": specific_date,
    #                 "callIndicator": "CALL"
    #             },
    #             "sortField": "STRIKE_PRICE",
    #             "sortOrder": "ASCENDING"
    #         }
    #         test_endpoint("Matrix (Payload Q - orderbookId)", url_matrix, method="POST", payload=payload_q)

    #         # Payload S: Plural keys matching filter-options keys
    #         payload_s = {
    #             "filter": {
    #                 "underlyingInstruments": [str(ABB_ID)], # Value in response was string "5447"
    #                 "optionTypes": ["STANDARD"],
    #                 "callIndicators": ["CALL"],
    #                 "endDates": [month_val] # Group value "2026-02"
    #             },
    #             "sortField": "STRIKE_PRICE",
    #             "sortOrder": "ASCENDING"
    #         }
    #         test_endpoint("Matrix (Payload S - Plural Keys Group Date)", url_matrix, method="POST", payload=payload_s)
            
    #         # Payload V: Matrix with pagination
    #         payload_v = {
    #             "filter": {
    #                 "underlyingOrderbookId": int(ABB_ID)
    #             },
    #             "pagination": {
    #                 "size": 20,
    #                 "page": 0
    #             },
    #             "sortField": "STRIKE_PRICE",
    #             "sortOrder": "ASCENDING"
    #         }
    #         test_endpoint("Matrix (Payload V - Pagination)", url_matrix, method="POST", payload=payload_v)

    #         # TRY POST /list
    #         url_list = "https://www.avanza.se/_api/market-option-future-forward-list/list"
    #         test_endpoint("List (Payload A)", url_list, method="POST", payload=payload_v)
    #         test_endpoint("List (Payload B - Minimal)", url_list, method="POST", payload={"filter": {"underlyingOrderbookId": int(ABB_ID)}})
            
    #         # Payload T: Plural keys with specific date
    #         payload_t = {
    #             "filter": {
    #                 "underlyingInstruments": [str(ABB_ID)],
    #                 "optionTypes": ["STANDARD"],
    #                 "callIndicators": ["CALL"],
    #                 "endDates": [specific_date] 
    #             },
    #             "sortField": "STRIKE_PRICE",
    #             "sortOrder": "ASCENDING"
    #         }
    #         test_endpoint("Matrix (Payload T - Plural Keys Specific Date)", url_matrix, method="POST", payload=payload_t)
            
    #         # Payload U: Plural keys with integers? (Response had string "5447")
    #         # But underlyingInstruments in payload is probably looking for IDs.


    # Payload V: Matrix with pagination
    payload_v = {
        "filter": {
            "underlyingOrderbookId": int(ABB_ID)
        },
        "pagination": {
            "size": 20,
            "page": 0
        },
        "sortField": "STRIKE_PRICE",
        "sortOrder": "ASCENDING"
    }
    test_endpoint("Matrix (Payload V - Pagination)", url_matrix, method="POST", payload=payload_v)

    # TRY POST /list
    url_list = "https://www.avanza.se/_api/market-option-future-forward-list/list"
    test_endpoint("List (Payload A)", url_list, method="POST", payload=payload_v)
    test_endpoint("List (Payload B - Minimal)", url_list, method="POST", payload={"filter": {"underlyingOrderbookId": int(ABB_ID)}})

if __name__ == "__main__":
    main()
