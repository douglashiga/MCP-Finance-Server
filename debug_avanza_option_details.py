import requests
import json

orderbook_id = "2328630" # ABB6Q800
url = f"https://www.avanza.se/_api/market-guide/option/{orderbook_id}"
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json"
}

print(f"Fetching details for option {orderbook_id}...")
resp = requests.get(url, headers=headers)
print(f"Status: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    print(json.dumps(data, indent=2))
else:
    print(f"Error: {resp.text}")
