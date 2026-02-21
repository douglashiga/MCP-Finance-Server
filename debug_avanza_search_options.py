import requests
import json

base_url = "https://www.avanza.se/_api/search/filtered-search"
payload = {
    "query": "ABB",
    "searchFilter": {"types": ["OPTION"]},
    "screenSize": "DESKTOP",
    "pagination": {"from": 0, "size": 20}
}
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Content-Type": "application/json"
}

print(f"Searching for ABB options...")
resp = requests.post(base_url, json=payload, headers=headers)
print(f"Status: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    hits = data.get("hits", [])
    print(f"Found {len(hits)} hits")
    for hit in hits:
        print(f"- {hit.get('title')} (ID: {hit.get('orderBookId')})")
        # Try to find underlying info in the hit
        # (Though hits usually don't have underlying info)
else:
    print(f"Error: {resp.text}")
