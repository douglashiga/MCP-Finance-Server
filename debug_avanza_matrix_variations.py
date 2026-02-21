import requests
import json

base_url = "https://www.avanza.se/_api/market-option-future-forward-list/matrix"
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Content-Type": "application/json"
}

def test_request(method, payload=None, params=None):
    print(f"\n--- Testing {method} with payload={payload}, params={params} ---")
    try:
        if method == "POST":
            resp = requests.post(base_url, json=payload, headers=headers)
        else:
            resp = requests.get(base_url, params=params, headers=headers)
            
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            # Check structure
            rows = data.get("rows", [])
            if not rows and isinstance(data, dict):
                 # maybe it's under 'matrix' key
                 rows = data.get("matrix", {}).get("rows", [])
            
            print(f"Found {len(rows)} rows in matrix")
            if rows:
                print("First row preview:")
                print(json.dumps(rows[0], indent=2))
        else:
            print(f"Error: {resp.text}")
    except Exception as e:
        print(f"Exception: {e}")

# Test Variations
test_request("POST", payload={"underlyingOrderId": 5447})
test_request("POST", payload={"underlyingId": "5447"})
test_request("POST", payload={"underlyingOrderbookId": 5447})
test_request("GET", params={"underlyingOrderId": 5447})
test_request("GET", params={"underlyingId": 5447})
test_request("GET", params={"ui": 5447})
