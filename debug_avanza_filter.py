import requests
import json

base_url = "https://www.avanza.se/_api/market-option-future-forward-list/filter-options"
payload = {
    "anyUnderlyingOrderbookIds": [5447],
    "instrumentType": "OPTION",
    "sortField": "NAME",
    "sortOrder": "ASCENDING"
}
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Content-Type": "application/json"
}

print(f"Fetching from: {base_url} (POST)")
resp = requests.post(base_url, json=payload, headers=headers)
print(f"Status: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    instruments = data.get("instruments", [])
    print(f"Found {len(instruments)} instruments")
    if instruments:
        print("First instrument preview:")
        print(json.dumps(instruments[0], indent=2))
        
        # Print a few more to see the names
        for i in range(min(5, len(instruments))):
             print(f"- {instruments[i].get('name')} (ID: {instruments[i].get('orderbookId')})")
else:
    print(f"Error: {resp.text}")
